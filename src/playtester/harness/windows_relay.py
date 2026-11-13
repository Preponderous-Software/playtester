"""The Windows driver's relay: holds one PowerShell helper for a whole session.

    python -m playtester.harness.windows_relay --control SOCK --log FILE [--powershell EXE] [--interop SOCK]...

Starting ``powershell.exe`` and compiling its user32 bindings costs about half
a second, and each ``pt`` command is a short-lived process. So ``pt start``
starts this relay, which starts the helper (``data/windows/pt_helper.ps1``)
once and keeps it:

- it listens on a TCP port on 127.0.0.1 and starts ``powershell.exe`` with a
  short bootstrap (``windows_driver.BOOTSTRAP``) that connects back to it and
  sends the session's random token; the relay sends the helper's script over
  that connection (it is too long for a Windows command line) and waits for
  its reply to ``ping``;
- if the helper does not answer, it tries again through the next WSL interop
  socket given with ``--interop`` (a wedged interop socket hangs every
  Windows program started through it, while the others keep working);
- it listens on ``--control`` (mode 0600) for ``pt`` commands, one at a time,
  and passes each JSON line to the helper, returning the helper's reply;
- ``{"op":"relay"}`` is answered by the relay itself;
- every line both ways goes to ``--log`` (``desktop.jsonl``).

It exits on SIGTERM, on ``{"op":"bye"}``, or when the helper exits.
Standard library only, single-threaded (``selectors``).
"""

import argparse
import json
import os
import secrets
import selectors
import signal
import socket
import subprocess
import sys
import time
from typing import List, Optional

from .strata_relay import listen, now_ms
from .windows_driver import helper_command, script_digest

HELPER_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "windows",
                             "pt_helper.ps1")
END_OF_SCRIPT = "#PT-END-OF-SCRIPT"
READY_TIMEOUT_SEC = 25.0
REPLY_TIMEOUT_SEC = 60.0


class Relay:
    def __init__(self, control_path: str, log_path: str, powershell: str, interop: List[str]):
        self.control_path = control_path
        self.log = open(log_path, "a", encoding="utf-8")
        self.powershell = powershell
        self.interop = interop or [os.environ.get("WSL_INTEROP", "")]
        self.helper = None  # type: Optional[subprocess.Popen]
        self.conn = None  # type: Optional[socket.socket]
        self.helper_buf = b""
        self.interop_used = None  # type: Optional[str]
        self.sel = selectors.DefaultSelector()
        self.control = None  # type: Any
        self.client = None  # type: Any
        self.client_buf = b""
        self.waiting_since = 0.0  # a reply owed by the helper
        self.closing = False
        self.running = True

    def record(self, direction: str, line: str) -> None:
        self.log.write(json.dumps({"t": now_ms(), "dir": direction, "line": line}, ensure_ascii=False) + "\n")
        self.log.flush()

    # --- the helper ----------------------------------------------------------

    def _spawn(self, interop: str) -> bool:
        """Starts the helper through ``interop`` and waits for it to connect and answer ping."""
        env = dict(os.environ)
        if interop:
            env["WSL_INTEROP"] = interop
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        token = secrets.token_hex(16)
        with open(HELPER_SCRIPT, encoding="utf-8") as f:
            script = f.read()
        cmd = helper_command(self.powershell, server.getsockname()[1], token, script_digest(script))
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                env=env, cwd="/", start_new_session=True)
        deadline = time.time() + READY_TIMEOUT_SEC
        conn = None
        try:
            while time.time() < deadline and conn is None:
                server.settimeout(max(0.1, min(1.0, deadline - time.time())))
                try:
                    candidate, _ = server.accept()
                except socket.timeout:
                    if proc.poll() is not None:
                        break
                    continue
                # each candidate has its own buffer and two seconds to say the token, so a stray
                # connection can neither corrupt the real helper's first line nor hold the loop
                self.helper_buf = b""
                if self._read_line(candidate, min(deadline, time.time() + 2.0)) == token:
                    conn = candidate
                else:
                    candidate.close()  # not our helper
            if conn is not None:
                conn.sendall(script.encode("utf-8") + b"\n" + END_OF_SCRIPT.encode() + b"\n" + b'{"op":"ping"}\n')
                reply = self._read_line(conn, deadline)
                try:
                    ok = bool(reply) and json.loads(reply).get("ok")
                except ValueError:
                    ok = False
                if ok:
                    conn.settimeout(None)
                    self.conn = conn
                    self.helper = proc
                    return True
                self.record("event", "helper's first line was not a ping reply: %r" % (reply or "")[:300])
                conn.close()
        except OSError as e:
            self.record("event", "helper connection failed: %s" % e)
        finally:
            server.close()
        self.record("event", "no helper through interop %r within %gs" % (interop, READY_TIMEOUT_SEC))
        try:
            proc.kill()
        except OSError:
            pass
        return False

    def _read_line(self, conn: socket.socket, deadline: float) -> Optional[str]:
        """One line from ``conn`` before ``deadline`` (the rest stays in helper_buf), or None."""
        while b"\n" not in self.helper_buf:
            conn.settimeout(max(0.1, deadline - time.time()))
            try:
                data = conn.recv(65536)
            except (socket.timeout, OSError):
                return None
            if not data:
                return None
            self.helper_buf += data
        line, self.helper_buf = self.helper_buf.split(b"\n", 1)
        return line.decode("utf-8", "replace").strip()

    def start_helper(self) -> bool:
        tried = []
        for interop in self.interop:
            if interop in tried:
                continue
            tried.append(interop)
            self.helper_buf = b""
            if self._spawn(interop):
                self.interop_used = interop
                self.record("event", "helper up (interop %s)" % (interop or "default"))
                self.sel.register(self.conn, selectors.EVENT_READ, "helper")
                return True
        return False

    def helper_readable(self) -> None:
        assert self.conn is not None
        try:
            data = self.conn.recv(65536)
        except OSError:
            data = b""
        if not data:
            self.record("event", "helper exited")
            self.reply_client(json.dumps({"ok": False, "error": "the Windows helper exited"}))
            self.running = False
            return
        self.helper_buf += data
        while b"\n" in self.helper_buf:
            raw, self.helper_buf = self.helper_buf.split(b"\n", 1)
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            self.record("from_helper", line)
            self.waiting_since = 0.0
            self.reply_client(line)
            if self.closing:
                self.running = False
                return
        self.check_client()

    # --- pt commands ---------------------------------------------------------

    def accept_client(self) -> None:
        conn, _ = self.control.accept()
        conn.setblocking(True)
        self.client = conn
        self.client_buf = b""
        self.sel.unregister(self.control)
        self.sel.register(conn, selectors.EVENT_READ, "client")

    def drop_client(self) -> None:
        if self.client is not None:
            try:
                self.sel.unregister(self.client)
            except (KeyError, ValueError):
                pass
            self.client.close()
        self.client = None
        self.client_buf = b""
        self.sel.register(self.control, selectors.EVENT_READ, "control")

    def client_readable(self) -> None:
        try:
            data = self.client.recv(65536)
        except OSError:
            data = b""
        if not data:
            self.drop_client()
            return
        self.client_buf += data
        self.check_client()

    def check_client(self) -> None:
        while self.client is not None and not self.waiting_since and b"\n" in self.client_buf:
            raw, self.client_buf = self.client_buf.split(b"\n", 1)
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                self.reply_client(json.dumps({"ok": False, "error": "bad JSON"}))
                continue
            if msg.get("op") == "relay":
                self.reply_client(json.dumps({"ok": True, "op": "relay", "pid": os.getpid(),
                                              "interop": self.interop_used}))
                continue
            self.record("to_helper", line)
            assert self.conn is not None
            try:
                self.conn.sendall(line.encode("utf-8") + b"\n")
            except OSError:
                self.reply_client(json.dumps({"ok": False, "error": "the Windows helper is gone"}))
                self.running = False
                return
            self.waiting_since = time.time()
            if msg.get("op") == "bye":
                self.closing = True  # exit once the helper's reply has been passed on

    def reply_client(self, line: str) -> None:
        if self.client is None:
            return
        try:
            self.client.sendall(line.encode("utf-8") + b"\n")
        except OSError:
            self.drop_client()

    # --- the loop ------------------------------------------------------------

    def run(self) -> int:
        if not self.start_helper():
            self.close()
            return 1
        # listen only once the helper answers, so a control socket means "ready"
        self.control = listen(self.control_path)
        self.sel.register(self.control, selectors.EVENT_READ, "control")
        while self.running:
            for key, _ in self.sel.select(timeout=1.0):
                what = key.data
                if what == "control":
                    self.accept_client()
                elif what == "client":
                    self.client_readable()
                elif what == "helper":
                    self.helper_readable()
            if self.waiting_since and time.time() - self.waiting_since > REPLY_TIMEOUT_SEC:
                self.record("event", "the helper did not answer within %gs" % REPLY_TIMEOUT_SEC)
                self.reply_client(json.dumps({"ok": False, "error": "the Windows helper did not answer"}))
                break
        self.close()
        return 0

    def close(self) -> None:
        if self.conn is not None:
            if self.helper is not None and self.helper.poll() is None:
                try:  # ask it to exit; a closed connection does not always reach Windows
                    self.conn.settimeout(3)
                    self.conn.sendall(b'{"op":"bye"}\n')
                except OSError:
                    pass
            self.conn.close()
        if self.helper is not None:
            try:
                self.helper.wait(3)
            except subprocess.TimeoutExpired:
                self.helper.kill()
        try:
            os.unlink(self.control_path)
        except OSError:
            pass
        self.log.close()


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(prog="playtester.harness.windows_relay", description=__doc__.split("\n")[0])
    ap.add_argument("--control", required=True, help="socket pt commands connect to")
    ap.add_argument("--log", required=True, help="desktop.jsonl: every line, both ways")
    ap.add_argument("--powershell", default="powershell.exe", help="the powershell.exe to run")
    ap.add_argument("--interop", action="append", default=[], help="WSL interop sockets to try, in order")
    args = ap.parse_args(argv)
    relay = Relay(args.control, args.log, args.powershell, args.interop)

    def stop(signum, frame):
        relay.running = False
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    return relay.run()


if __name__ == "__main__":
    sys.exit(main())
