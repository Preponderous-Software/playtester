"""The Strata driver's relay: holds a session's drive channel between pt commands.

    python -m playtester.harness.strata_relay --drive SOCK --control SOCK --log FILE

A Strata game driven by playtester connects, as a client, to the socket named
by ``STRATA_DRIVE`` (Strata's ``docs/DRIVE.md``). Each ``pt`` command is a
short-lived process, so something has to hold that connection for the whole
session. That is this relay, started by ``pt start``:

- it listens on ``--drive`` (mode 0600, inside the session directory) and
  accepts the game's one connection, then sends ``hello`` and keeps the reply;
- it listens on ``--control`` for ``pt`` commands, one at a time, and passes
  each JSON line to the game, returning the game's reply line;
- ``{"op":"relay"}`` is answered by the relay itself: whether the game is
  connected, and its ``hello``;
- every line in both directions is appended to ``--log`` (``drive.jsonl``),
  which is the exact input the game received, for replays.

The game never listens on anything. The relay exits on SIGTERM, when the game
has gone and no command has come for 30 seconds, or when no game has
connected within ``--connect-timeout`` seconds.

Standard library only, single-threaded (``selectors``).
"""

import argparse
import json
import os
import selectors
import signal
import socket
import sys
import time
from typing import Any, Dict, Optional

IDLE_AFTER_GAME_SEC = 30.0


def now_ms() -> int:
    return int(time.time() * 1000)


def listen(path: str) -> socket.socket:
    try:
        os.unlink(path)
    except OSError:
        pass
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    old = os.umask(0o177)
    try:
        sock.bind(path)
    finally:
        os.umask(old)
    os.chmod(path, 0o600)
    sock.listen(4)
    sock.setblocking(False)
    return sock


class Relay:
    def __init__(self, drive_path: str, control_path: str, log_path: str, connect_timeout: float):
        self.drive_path = drive_path
        self.control_path = control_path
        self.log = open(log_path, "a", encoding="utf-8")
        self.connect_timeout = connect_timeout
        self.sel = selectors.DefaultSelector()
        self.drive = listen(drive_path)
        self.control = listen(control_path)
        self.sel.register(self.drive, selectors.EVENT_READ, "drive")
        self.sel.register(self.control, selectors.EVENT_READ, "control")
        self.game = None  # type: Optional[socket.socket]
        self.game_buf = b""
        self.client = None  # type: Optional[socket.socket]
        self.client_buf = b""
        self.waiting = None  # type: Optional[str]  # "hello", "client", "orphan" or None
        self.hello = None  # type: Optional[Dict[str, Any]]
        self.game_closed = False
        self.closed_at = 0.0
        self.started = time.time()
        self.running = True

    def record(self, direction: str, line: str) -> None:
        self.log.write(json.dumps({"t": now_ms(), "dir": direction, "line": line}, ensure_ascii=False) + "\n")
        self.log.flush()

    # --- the game ------------------------------------------------------------

    def accept_game(self) -> None:
        conn, _ = self.drive.accept()
        if self.game is not None or self.game_closed:
            conn.close()  # one game per session
            return
        conn.setblocking(True)
        self.game = conn
        self.sel.unregister(self.drive)
        self.sel.register(conn, selectors.EVENT_READ, "game")
        self.record("event", "game connected")
        self.send_game('{"op":"hello","protocol":1}')
        self.waiting = "hello"

    def send_game(self, line: str) -> None:
        self.record("to_game", line)
        assert self.game is not None
        self.game.sendall(line.encode("utf-8") + b"\n")

    def game_readable(self) -> None:
        assert self.game is not None
        data = b""
        try:
            data = self.game.recv(65536)
        except OSError:
            pass
        if not data:
            self.game_gone()
            return
        self.game_buf += data
        while b"\n" in self.game_buf:
            raw, self.game_buf = self.game_buf.split(b"\n", 1)
            line = raw.decode("utf-8", "replace")
            self.record("from_game", line)
            self.game_line(line)

    def game_line(self, line: str) -> None:
        if self.waiting == "hello":
            try:
                self.hello = json.loads(line)
            except ValueError:
                self.hello = {"ok": False, "error": "bad hello reply: " + line}
            self.waiting = None
            self.check_client()
        elif self.waiting == "client":
            self.waiting = None
            self.reply_client(line)
        elif self.waiting == "orphan":
            self.waiting = None
            self.check_client()

    def game_gone(self) -> None:
        if self.game is not None:
            self.sel.unregister(self.game)
            self.game.close()
        self.game = None
        self.game_closed = True
        self.closed_at = time.time()
        self.record("event", "game disconnected")
        if self.waiting == "client":
            self.reply_client(json.dumps({"ok": False, "error": "the game closed the drive channel (it exited?)"}))
        self.waiting = None
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
        if self.waiting == "client":
            self.waiting = "orphan"  # the game's reply still comes; swallow it
        self.sel.register(self.control, selectors.EVENT_READ, "control")

    def client_readable(self) -> None:
        assert self.client is not None
        data = b""
        try:
            data = self.client.recv(65536)
        except OSError:
            pass
        if not data:
            self.drop_client()
            return
        self.client_buf += data
        self.check_client()

    def check_client(self) -> None:
        """Handles the client's next complete line, unless a reply is still owed."""
        while self.client is not None and self.waiting is None and b"\n" in self.client_buf:
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
                self.reply_client(json.dumps({"ok": True, "op": "relay", "connected": self.game is not None,
                                              "closed": self.game_closed, "hello": self.hello,
                                              "pid": os.getpid()}))
                continue
            if self.game is None:
                why = "the game has closed the drive channel" if self.game_closed else "the game has not connected yet"
                self.reply_client(json.dumps({"ok": False, "op": msg.get("op"), "error": why}))
                continue
            self.waiting = "client"
            self.send_game(line)

    def reply_client(self, line: str) -> None:
        if self.client is None:
            return
        try:
            self.client.sendall(line.encode("utf-8") + b"\n")
        except OSError:
            self.drop_client()

    # --- the loop ------------------------------------------------------------

    def run(self) -> int:
        while self.running:
            for key, _ in self.sel.select(timeout=1.0):
                what = key.data
                if what == "drive":
                    self.accept_game()
                elif what == "control":
                    self.accept_client()
                elif what == "game":
                    self.game_readable()
                elif what == "client":
                    self.client_readable()
            now = time.time()
            if self.game is None and not self.game_closed and now - self.started > self.connect_timeout:
                self.record("event", "no game connected within %gs" % self.connect_timeout)
                break
            if self.game_closed and self.client is None and now - self.closed_at > IDLE_AFTER_GAME_SEC:
                break
        self.close()
        return 0

    def close(self) -> None:
        for path in (self.drive_path, self.control_path):
            try:
                os.unlink(path)
            except OSError:
                pass
        self.log.close()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="playtester.harness.strata_relay", description=__doc__.split("\n")[0])
    ap.add_argument("--drive", required=True, help="socket the game connects to (STRATA_DRIVE)")
    ap.add_argument("--control", required=True, help="socket pt commands connect to")
    ap.add_argument("--log", required=True, help="drive.jsonl: every line, both ways")
    ap.add_argument("--connect-timeout", type=float, default=300.0)
    args = ap.parse_args(argv)
    relay = Relay(args.drive, args.control, args.log, args.connect_timeout)

    def stop(signum, frame):
        relay.running = False
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    return relay.run()


if __name__ == "__main__":
    sys.exit(main())
