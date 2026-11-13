"""The Windows driver: playing a game on the real Windows desktop, from WSL2.

A profile with ``"driver": "windows"`` runs a Windows game on the desktop of
the Windows machine that hosts this WSL2 distribution, and drives it the way
a person would: the real mouse pointer, real key presses, screenshots of the
real screen. It is for games that only run on Windows (Mount&Blade: Warband
and its mods), where no Xvfb or engine drive channel is possible.

**It takes over the owner's screen.** While a session runs, its input goes to
whatever window is in front, and ``pt`` brings the game to the front before
every command. So only one session at a time may drive the desktop: ``pt
start`` takes the desktop lock (``~/.pt-windows-desktop.lock``, or
``PT_WINDOWS_LOCK``) and ``pt stop`` gives it back. A lock whose holder has
gone (its relay's process no longer runs) is stale and is taken over.

How a session runs:

1. ``pt start`` takes the desktop lock, then starts the session's relay
   (``windows_relay``), which starts one ``powershell.exe`` helper
   (``data/windows/pt_helper.ps1``) for the whole session and listens on
   ``control.sock`` for ``pt`` commands.
2. It launches the game (``Start-Process``) or, with ``pt start --attach``,
   attaches to a copy that is already running; finds its window by process
   name and ``window.title_regex``; and brings it to the front.
3. Every input command brings the window to the front (restoring it when
   minimised: a minimised game draws nothing), then sends the input.
   Coordinates are screenshot pixels: shots are scaled to the profile's
   ``window`` size and clicks are scaled back to the real window.
4. ``pt stop`` closes a game it launched (the window's close message, then
   ``Stop-Process`` after ``windows.close_timeout_sec``), restores anything
   it changed in the registry, stops the relay and releases the lock. It
   never closes a game it attached to.
"""

import glob
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_LOCK = os.path.join(os.path.expanduser("~"), ".pt-windows-desktop.lock")
POWERSHELL = "powershell.exe"
# The helper's bootstrap: connect back to the relay, say the session's token,
# read the helper script up to the marker, and run it only if its SHA-256 is
# the one on the command line (so whatever answers on the port can only ever
# get this script run, not its own). {port}, {token} and {digest} are filled
# in per session. It retries the connection for up to 15 seconds: WSL2
# forwards a Windows connection to 127.0.0.1 into the distribution only once
# it has noticed the new listening port, which can take a moment.
BOOTSTRAP = ("$c=$null;for($i=0;($i -lt 60) -and (-not $c);$i++){{"
             "try{{$c=New-Object Net.Sockets.TcpClient('127.0.0.1',{port})}}catch{{Start-Sleep -Milliseconds 250}}}};"
             "$st=$c.GetStream();"
             "$utf8=New-Object Text.UTF8Encoding $false;"
             "$stdin=New-Object IO.StreamReader($st,$utf8);"
             "$stdout=New-Object IO.StreamWriter($st,$utf8);$stdout.AutoFlush=$true;"
             "$stdout.WriteLine('{token}');"
             "$b=New-Object Text.StringBuilder;"
             "while((($l=$stdin.ReadLine()) -ne $null) -and ($l -ne '#PT-END-OF-SCRIPT')){{[void]$b.AppendLine($l)}};"
             "$s=$b.ToString();"
             "$d=[BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash($utf8.GetBytes($s)))"
             ".Replace('-','');"
             "if($d -ne '{digest}'){{$stdout.WriteLine('PT-SCRIPT-MISMATCH '+$d);exit 1}};"
             ". ([ScriptBlock]::Create($s))")


class DesktopLockError(RuntimeError):
    """The desktop is being driven by another session."""


# --- the helper's command line ------------------------------------------------

def powershell() -> Optional[str]:
    """The ``powershell.exe`` to run (``PT_POWERSHELL``, the PATH, or the usual place under /mnt/c)."""
    explicit = os.environ.get("PT_POWERSHELL")
    if explicit:
        return explicit
    found = shutil.which(POWERSHELL)
    if found:
        return found
    usual = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
    return usual if os.path.exists(usual) else None


def script_digest(script: str) -> str:
    """The SHA-256 (upper-case hex) the bootstrap computes for ``script`` sent line by line: it reads each
    line (``ReadLine`` drops the line ends) and appends it with Windows' line end (``AppendLine``)."""
    import hashlib
    lines = (script + "\n").split("\n")[:-1]
    text = "".join(line.rstrip("\r") + "\r\n" for line in lines)
    return hashlib.sha256(text.encode("utf-8")).hexdigest().upper()


def helper_command(exe: str, port: int, token: str, digest: str = "") -> List[str]:
    """The helper's command line: a short bootstrap that connects back to the relay on ``port``.

    The helper talks to the relay over TCP on 127.0.0.1 (WSL2 forwards a
    Windows connection to localhost into the distribution). Measured on
    Windows 11 with WSL2 (2026-11): a pipe to powershell.exe's standard input
    did not deliver lines promptly, and powershell.exe started from WSL with
    ``-EncodedCommand`` exited by itself a second or two after starting, so the
    bootstrap goes in ``-Command`` and standard input is not used.

    ``digest`` is ``script_digest`` of the helper script the relay will send.

    ``PT_WINDOWS_HELPER`` replaces the whole command, a JSON list whose strings
    may use ``{port}``, ``{token}`` and ``{digest}`` (the tests run a stand-in in Python).
    """
    override = os.environ.get("PT_WINDOWS_HELPER")
    if override:
        return [part.replace("{port}", str(port)).replace("{token}", token).replace("{digest}", digest)
                for part in json.loads(override)]
    if not re.match(r"^[0-9A-F]{64}$", digest or ""):
        raise ValueError("the helper's command needs the script's SHA-256 (script_digest)")
    return [exe, "-NoProfile", "-NonInteractive", "-InputFormat", "None", "-ExecutionPolicy", "Bypass",
            "-Command", BOOTSTRAP.format(port=int(port), token=token, digest=digest)]


def interop_sockets(current: Optional[str] = None, run_dir: str = "/run/WSL") -> List[str]:
    """WSL interop sockets to try, the environment's first.

    A WSL interop socket can wedge (every Windows program started through it
    hangs) while the others in /run/WSL keep working; the relay tries them in
    this order.
    """
    out = []  # type: List[str]
    current = os.environ.get("WSL_INTEROP", "") if current is None else current
    if current:
        out.append(current)
    for path in sorted(glob.glob(os.path.join(run_dir, "*_interop")), key=lambda p: -_mtime(p)):
        if path not in out:
            out.append(path)
    return out


def _mtime(path: str) -> float:
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


def start_relay(session_dir: str, control: str, log_path: str) -> subprocess.Popen:
    """Starts the relay; returns once its control socket exists (the helper has answered)."""
    exe = powershell()
    if not exe and not os.environ.get("PT_WINDOWS_HELPER"):
        raise RuntimeError("the windows driver needs powershell.exe: run pt inside WSL2 with Windows interop "
                           "enabled (or set PT_POWERSHELL)")
    pkg_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    env = dict(os.environ)
    env["PYTHONPATH"] = pkg_root + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    cmd = [sys.executable, "-m", "playtester.harness.windows_relay", "--control", control, "--log", log_path,
           "--powershell", exe or POWERSHELL]
    for sock in interop_sockets():
        cmd += ["--interop", sock]
    with open(os.path.join(session_dir, "relay.log"), "w") as log:
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, env=env,
                                start_new_session=True)
    deadline = time.time() + 120
    while time.time() < deadline:
        if os.path.exists(control):
            return proc
        if proc.poll() is not None:
            break
        time.sleep(0.05)
    if proc.poll() is None:
        proc.kill()
    raise RuntimeError("the Windows helper did not start (no answer from powershell.exe through any WSL interop "
                       "socket; see %s and %s)" % (os.path.join(session_dir, "relay.log"), log_path))


# --- paths --------------------------------------------------------------------

_MNT = re.compile(r"^/mnt/([a-zA-Z])(/.*)?$")


def mnt_to_windows(path: str) -> Optional[str]:
    """``/mnt/c/Program Files/x`` -> ``C:\\Program Files\\x``; None for a path outside /mnt/<drive>."""
    m = _MNT.match(path)
    if not m:
        return None
    rest = (m.group(2) or "/").replace("/", "\\")
    return "%s:%s" % (m.group(1).upper(), rest)


def windows_path(path: str) -> str:
    """A WSL path as Windows sees it (``wslpath -w``; /mnt/<drive> paths are converted directly)."""
    direct = mnt_to_windows(os.path.abspath(path))
    if direct is not None:
        return direct
    try:
        r = subprocess.run(["wslpath", "-w", os.path.abspath(path)], stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, universal_newlines=True, timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return path


def registry_path(key: str) -> str:
    """``HKCU\\Software\\X`` (reg.exe style) -> ``HKCU:\\Software\\X`` (PowerShell drive style)."""
    m = re.match(r"^(HKCU|HKLM|HKEY_CURRENT_USER|HKEY_LOCAL_MACHINE):?\\(.*)$", key)
    if not m:
        raise ValueError("registry key %r must start with HKCU\\ or HKLM\\" % key)
    hive = {"HKEY_CURRENT_USER": "HKCU", "HKEY_LOCAL_MACHINE": "HKLM"}.get(m.group(1), m.group(1))
    return "%s:\\%s" % (hive, m.group(2))


# --- the desktop lock -----------------------------------------------------------

def lock_path() -> str:
    return os.environ.get("PT_WINDOWS_LOCK") or DEFAULT_LOCK


def read_lock(path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    try:
        with open(path or lock_path(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except OSError:
        return None
    except ValueError:
        return {}  # half-written or damaged: treated as stale


def lock_is_live(holder: Optional[Dict[str, Any]]) -> bool:
    """Whether the process holding the lock still runs (pid and start time both match)."""
    from .session import same_process
    if not holder:
        return False
    pid = holder.get("pid")
    if not isinstance(pid, int):
        return False
    return same_process(pid, holder.get("pidStart"), ["windows_relay", "playtester"])


def describe_holder(holder: Dict[str, Any]) -> str:
    return "session %s (in %s, pid %s, since %s)" % (
        holder.get("session"), holder.get("root"), holder.get("pid"),
        time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(holder.get("startedAtMs", 0) / 1000.0)))


def acquire_lock(session: str, root: str, pid: int, path: Optional[str] = None) -> Dict[str, Any]:
    """Takes the desktop lock for ``session``; raises DesktopLockError if a live session holds it.

    The lock is a JSON file created with O_EXCL. A lock held by the same
    session (same name and root) is taken over, so a session can be restarted;
    a stale one (its pid gone, or a different process now has that pid) is
    replaced. Returns what was written.
    """
    from .session import proc_start_time
    path = path or lock_path()
    me = {"session": session, "root": root, "pid": pid, "pidStart": proc_start_time(pid),
          "startedAtMs": int(time.time() * 1000), "host": socket.gethostname()}
    for _ in range(5):
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            holder = read_lock(path)
            if holder is None:
                continue  # removed meanwhile
            mine = holder.get("session") == session and holder.get("root") == root
            if lock_is_live(holder) and not mine:
                raise DesktopLockError(
                    "the Windows desktop is being driven by %s; only one session may drive it at a time "
                    "(pt stop that session first; the lock is %s)" % (describe_holder(holder), path))
            try:
                os.remove(path)
            except OSError:
                pass
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(me, f)
        return me
    raise DesktopLockError("could not take the desktop lock %s" % path)


def update_lock(session: str, root: str, pid: int, path: Optional[str] = None) -> None:
    """Points our lock at ``pid`` (the relay, which lives as long as the session)."""
    from .session import proc_start_time
    path = path or lock_path()
    holder = read_lock(path) or {}
    if holder.get("session") != session or holder.get("root") != root:
        return
    holder.update({"pid": pid, "pidStart": proc_start_time(pid)})
    tmp = path + ".%d.tmp" % os.getpid()
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(holder, f)
    os.replace(tmp, path)


def release_lock(session: str, root: str, path: Optional[str] = None) -> bool:
    """Removes the lock if this session holds it; returns whether it did."""
    path = path or lock_path()
    holder = read_lock(path)
    if holder is None:
        return False
    if holder and (holder.get("session") != session or holder.get("root") != root):
        return False
    try:
        os.remove(path)
        return True
    except OSError:
        return False


# --- coordinates ----------------------------------------------------------------

def scale_point(x: float, y: float, client: List[int], shot: Tuple[int, int]) -> Tuple[int, int]:
    """Screenshot pixel (x, y) -> screen pixel, for a window whose client area is ``[left, top, w, h]``."""
    left, top, w, h = (int(v) for v in client[:4])
    sw, sh = shot
    sx = w / float(sw) if sw else 1.0
    sy = h / float(sh) if sh else 1.0
    px = left + int(round(x * sx))
    py = top + int(round(y * sy))
    return (min(max(px, left), left + max(0, w - 1)), min(max(py, top), top + max(0, h - 1)))


def shot_size(profile: Dict[str, Any], width: Optional[int], height: Optional[int]) -> Tuple[int, int]:
    """The size screenshots are saved at (and coordinates are given in): --width/--height, else the profile's window."""
    return (int(width or profile["window"]["width"]), int(height or profile["window"]["height"]))


def pick_window(windows: List[Dict[str, Any]], title_regex: str, min_width: int = 0) -> Optional[Dict[str, Any]]:
    """The game's window among a process's top-level windows: title matches, largest client area first."""
    pattern = re.compile(title_regex) if title_regex else None
    good = [w for w in windows if (pattern is None or pattern.search(w.get("title") or ""))
            and int((w.get("client") or [0, 0, 0, 0])[2]) >= min_width]
    good.sort(key=lambda w: -(int(w["client"][2]) * int(w["client"][3])))
    return good[0] if good else None
