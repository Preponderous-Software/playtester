"""The Strata driver: playing a Strata game through its drive channel, with no X.

A profile with ``"driver": "strata"`` is started like this:

1. ``pt start`` starts the session's relay (``strata_relay``), which listens on
   ``drive.sock`` (mode 0600) for the game and on ``control.sock`` for ``pt``.
2. The game is started with ``STRATA_DRIVE`` naming ``drive.sock``,
   ``STRATA_DRIVE_SURFACE=headless`` (so its window becomes a headless EGL
   surface), and ``STRATA_DRIVE_CLOCK`` / ``STRATA_DRIVE_STEP`` for the clock.
   It connects as a client; it never listens.
3. Every later ``pt`` command connects to ``control.sock`` and sends the
   drive protocol's JSON lines (Strata ``docs/DRIVE.md``) through the relay.

Needs no Xvfb, xdotool or ImageMagick: only the game and Mesa's EGL. Strata
ABI 1.12 or later, and a game that reads ``engine.frameSeconds()`` for a
stepped clock to be repeatable.
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, Optional

# A Unix socket path must fit in sockaddr_un.sun_path (108 bytes on Linux).
MAX_SOCKET_PATH = 100
DEFAULT_STEP = 1.0 / 60.0


class DriveError(RuntimeError):
    """The drive channel refused a request or could not be reached."""


def socket_dir(session_dir: str) -> str:
    """Where a session's sockets go: the session directory, or a private /tmp one if that path is too long."""
    if len(os.path.join(session_dir, "control.sock")) <= MAX_SOCKET_PATH:
        return session_dir
    return tempfile.mkdtemp(prefix="pt-drive-")


class Channel:
    """``pt``'s end of the relay: one JSON line out, one back."""

    def __init__(self, control_path: str, timeout: float = 60.0):
        self.path = control_path
        self.timeout = timeout
        self.sock = None  # type: Optional[socket.socket]
        self.buf = b""

    def _connect(self) -> socket.socket:
        if self.sock is None:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                s.connect(self.path)
            except OSError as e:
                s.close()
                raise DriveError("cannot reach the session's drive relay at %s (%s); is the session running?"
                                 % (self.path, e))
            self.sock = s
        return self.sock

    def raw(self, msg: Dict[str, Any], timeout: Optional[float] = None) -> Dict[str, Any]:
        s = self._connect()
        s.settimeout(timeout or self.timeout)
        s.sendall(json.dumps(msg, separators=(",", ":")).encode("utf-8") + b"\n")
        try:
            while b"\n" not in self.buf:
                data = s.recv(65536)
                if not data:
                    raise DriveError("the drive relay closed the connection")
                self.buf += data
        except socket.timeout:
            self.close()
            raise DriveError("no answer to %s within %gs" % (msg.get("op"), timeout or self.timeout))
        line, self.buf = self.buf.split(b"\n", 1)
        try:
            return json.loads(line.decode("utf-8"))
        except ValueError:
            raise DriveError("bad reply from the drive channel: %r" % line[:200])

    def request(self, op: str, timeout: Optional[float] = None, **fields: Any) -> Dict[str, Any]:
        """Sends ``op`` with ``fields``; returns the reply or raises DriveError if it is not ok."""
        msg = dict(fields)
        msg["op"] = op
        reply = self.raw(msg, timeout)
        if not reply.get("ok"):
            raise DriveError("%s: %s" % (op, reply.get("error", reply)))
        return reply

    def close(self) -> None:
        if self.sock is not None:
            self.sock.close()
        self.sock = None
        self.buf = b""


def start_relay(session_dir: str, sock_dir: str, log_path: str, connect_timeout: float) -> subprocess.Popen:
    """Starts the relay and waits until both of its sockets exist."""
    drive = os.path.join(sock_dir, "drive.sock")
    control = os.path.join(sock_dir, "control.sock")
    pkg_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    env = dict(os.environ)
    env["PYTHONPATH"] = pkg_root + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    with open(os.path.join(session_dir, "relay.log"), "w") as log:
        proc = subprocess.Popen([sys.executable, "-m", "playtester.harness.strata_relay", "--drive", drive,
                                 "--control", control, "--log", log_path,
                                 "--connect-timeout", str(connect_timeout)],
                                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, env=env,
                                start_new_session=True)
    for _ in range(100):
        if os.path.exists(drive) and os.path.exists(control):
            return proc
        if proc.poll() is not None:
            break
        time.sleep(0.05)
    raise DriveError("the drive relay did not start (see %s)" % os.path.join(session_dir, "relay.log"))


def await_connection(channel: Channel, game: subprocess.Popen, timeout: float) -> Dict[str, Any]:
    """Waits until the game has connected and answered hello; returns the hello reply."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if game.poll() is not None:
            raise DriveError("the game exited with status %s before connecting" % game.returncode)
        status = channel.request("relay")
        hello = status.get("hello")
        if hello:
            if not hello.get("ok"):
                raise DriveError("the game refused hello: %s" % hello.get("error"))
            return hello
        if status.get("closed"):
            raise DriveError("the game connected and then closed the drive channel")
        time.sleep(0.1)
    raise DriveError("the game did not connect to its drive channel within %gs (is it built against Strata "
                     "ABI 1.12 or later? the game's log says 'driven through' when it connects)" % timeout)
