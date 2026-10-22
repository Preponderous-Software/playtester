"""One playtest session: a game in its own Xvfb, with its own files.

Everything a session owns lives in ``$PT_ROOT/$PT_SESSION``::

    session.json      display, window, profile, game args, version, commit
    profile.json      the resolved profile the session was started with
    actions.jsonl     every harness command, with its time (for repro)
    findings.jsonl    ``pt note``: raw notes as they were taken
    trace.jsonl       each step of ``face`` and ``walkto``
    report.json       the agent's report
    shots/*.png       screenshots
    out/              the game's probe output (state.json, events.jsonl)
    data/             the game's saves and settings for this session
    game.log, xvfb.log
    display, game.pid, xvfb.pid, window   while running

Only the X display number is shared between sessions, and it is claimed under
an exclusive ``flock`` so simultaneous starts never pick the same one.
"""

import fcntl
import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
from typing import Any, Dict, List, Optional

from . import profile as profiles
from . import xdo

SESSION_NAME = re.compile(r"^[A-Za-z0-9._-]+$")
DISPLAY_RANGE = range(100, 200)
LOCK_FILE = os.path.join(tempfile.gettempdir(), "playtester-displays.lock")
# Xvfb aborts on some hosts (WSL2 among them) without these, and a game
# rendering with OpenGL needs them for Mesa's llvmpipe software renderer.
SOFTWARE_GL = {"LIBGL_ALWAYS_SOFTWARE": "1", "GALLIUM_DRIVER": "llvmpipe"}
TOOLS = ("Xvfb", "xdotool", "import")


class HarnessError(Exception):
    """A command that cannot be carried out; the message says why."""


def default_root() -> str:
    return os.environ.get("PT_ROOT") or os.path.join(tempfile.gettempdir(), "playtester")


def now_ms() -> int:
    return int(time.time() * 1000)


def append_json(path: str, obj: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def read_json(path: str) -> Optional[Any]:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def pid_alive(pid: Optional[int]) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    # a zombie (exited, not yet reaped) is not running
    try:
        with open("/proc/%d/stat" % pid) as f:
            return f.read().rsplit(")", 1)[1].split()[0] != "Z"
    except (OSError, IndexError):
        return True


def tail(path: str, lines: int = 25) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return "".join(f.readlines()[-lines:])
    except OSError:
        return ""


class Session:
    """The files and processes of one session (``PT_ROOT/PT_SESSION``)."""

    def __init__(self, name: str, root: Optional[str] = None):
        if not name:
            raise HarnessError("PT_SESSION is not set (each session needs its own name, e.g. PT_SESSION=s01)")
        if not SESSION_NAME.match(name):
            raise HarnessError("PT_SESSION may only contain letters, digits, '.', '_' and '-'")
        self.name = name
        self.root = os.path.abspath(root or default_root())
        self.dir = os.path.join(self.root, name)

    # --- paths and small files ---------------------------------------------

    def path(self, *parts: str) -> str:
        return os.path.join(self.dir, *parts)

    @property
    def probe_dir(self) -> str:
        return self.path("out")

    def _read(self, name: str) -> Optional[str]:
        try:
            with open(self.path(name)) as f:
                return f.read().strip() or None
        except OSError:
            return None

    def _pid(self, name: str) -> Optional[int]:
        value = self._read(name + ".pid")
        try:
            return int(value) if value else None
        except ValueError:
            return None

    @property
    def window(self) -> Optional[str]:
        return self._read("window")

    @property
    def display(self) -> Optional[str]:
        return self._read("display")

    def game_alive(self) -> bool:
        return pid_alive(self._pid("game"))

    def env(self) -> Dict[str, str]:
        """The environment for anything that talks to this session's display."""
        env = dict(os.environ)
        if self.display:
            env["DISPLAY"] = ":" + self.display
        env.update(SOFTWARE_GL)
        return env

    def profile(self) -> Dict[str, Any]:
        """The profile this session was started with (falls back to PT_PROFILE)."""
        saved = read_json(self.path("profile.json"))
        if saved:
            return saved
        return profiles.load(os.environ.get("PT_PROFILE", ""))

    def info(self) -> Dict[str, Any]:
        return read_json(self.path("session.json")) or {}

    def log_action(self, cmd: str, args: List[str]) -> None:
        append_json(self.path("actions.jsonl"), {"t": now_ms(), "cmd": cmd, "args": list(args)})

    def need_game(self) -> None:
        if not self.game_alive():
            raise HarnessError("the game is not running in session %s (pt start first; pt log shows why it stopped)" % self.name)

    def input_env(self) -> Dict[str, str]:
        """The environment for input, after focusing the game's window."""
        self.need_game()
        env = self.env()
        xdo.focus(env, self.window or "")
        return env

    # --- start and stop ----------------------------------------------------

    def _claim_display(self, width: int, height: int) -> int:
        """Starts Xvfb on a free display under the shared lock; returns the display number."""
        with open(LOCK_FILE, "a") as lock:
            deadline = time.time() + 60
            while True:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    if time.time() > deadline:
                        raise HarnessError("could not take the display lock " + LOCK_FILE)
                    time.sleep(0.1)
            try:
                number = next((n for n in DISPLAY_RANGE if not os.path.exists("/tmp/.X%d-lock" % n)
                               and not os.path.exists("/tmp/.X11-unix/X%d" % n)), None)
                if number is None:
                    raise HarnessError("no free X display in :%d-:%d" % (DISPLAY_RANGE[0], DISPLAY_RANGE[-1]))
                env = dict(os.environ, **SOFTWARE_GL)
                with open(self.path("xvfb.log"), "w") as log:
                    proc = subprocess.Popen(
                        ["Xvfb", ":%d" % number, "-screen", "0", "%dx%dx24" % (width + 64, height + 64), "-nolisten", "tcp"],
                        stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, env=env, start_new_session=True)
                with open(self.path("xvfb.pid"), "w") as f:
                    f.write(str(proc.pid))
                with open(self.path("display"), "w") as f:
                    f.write(str(number))
                for _ in range(80):
                    if os.path.exists("/tmp/.X11-unix/X%d" % number) or proc.poll() is not None:
                        break
                    time.sleep(0.25)
                if proc.poll() is not None or not os.path.exists("/tmp/.X11-unix/X%d" % number):
                    raise HarnessError("Xvfb :%d did not start; its log:\n%s" % (number, tail(self.path("xvfb.log"), 20)))
                return number
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def start(self, profile: Dict[str, Any], game_dir: str, seed: Optional[str], extra_args: List[str],
              use_probe: bool = True, width: Optional[int] = None, height: Optional[int] = None,
              lp_threads: Optional[str] = None) -> Dict[str, Any]:
        """Xvfb on a free display, then the game; waits for its window (and first state.json).

        On any failure prints why (the end of the game's log), stops whatever
        was started and raises HarnessError.
        """
        missing = [t for t in TOOLS if shutil.which(t) is None]
        if missing:
            raise HarnessError("missing tools: %s (install xvfb, xdotool and imagemagick; docs/AGENT_PLAYTESTING.md)"
                               % ", ".join(missing))
        if self.game_alive():
            raise HarnessError("session %s is already running (pt stop first)" % self.name)
        self.stop()
        width = int(width or profile["window"]["width"])
        height = int(height or profile["window"]["height"])
        use_probe = bool(use_probe and profile.get("probe"))
        for sub in ("data", "out", "shots"):
            os.makedirs(self.path(sub), exist_ok=True)
        resolved = dict(profile, _game_dir=game_dir, _probe=use_probe)
        with open(self.path("profile.json"), "w", encoding="utf-8") as f:
            json.dump(resolved, f, indent=2)
        plan = profiles.launch_plan(profile, game_dir, self.dir, width, height, seed, extra_args, use_probe)
        if not shutil.which(plan["command"][0]) and not os.access(plan["command"][0], os.X_OK):
            hint = profile.get("build", {}).get("command") if isinstance(profile.get("build"), dict) else None
            raise HarnessError("no game executable at %s%s" % (plan["command"][0], " (build it: %s)" % hint if hint else ""))
        try:
            number = self._claim_display(width, height)
            state_path = os.path.join(self.probe_dir, "state.json")
            if os.path.exists(state_path):
                os.remove(state_path)
            env = dict(os.environ, **plan["env"])
            env.update(SOFTWARE_GL)
            env["DISPLAY"] = ":%d" % number
            env["LP_NUM_THREADS"] = str(lp_threads or os.environ.get("PT_LP_THREADS") or profile["launch"].get("lp_threads") or 2)
            env["PT_SESSION_DIR"] = self.dir
            with open(self.path("game.log"), "w") as log:
                game = subprocess.Popen(plan["command"], cwd=plan["cwd"], env=env, stdin=subprocess.DEVNULL,
                                        stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            with open(self.path("game.pid"), "w") as f:
                f.write(str(game.pid))
            window = self._await_window(profile, game, use_probe, env)
            with open(self.path("window"), "w") as f:
                f.write(window)
            # With no window manager nothing places the window; a window opened
            # at +50+50 would be cut off in screenshots past the screen's edge.
            xdo.run(env, "windowmove", window, 0, 0)
            xdo.run(env, "mousemove", "--window", window, width // 2, height // 2)
            time.sleep(float(profile["launch"].get("settle_sec", 0)))
        except BaseException:
            self.stop()
            raise
        state = read_json(state_path) or {}
        info = {
            "session": self.name,
            "dir": self.dir,
            "profile": profile["name"],
            "display": ":%d" % number,
            "window": window,
            "size": "%dx%d" % (width, height),
            "seed": seed,
            "args": list(extra_args),
            "command": plan["command"],
            "probe": use_probe,
            "ticksPerSecond": (profile.get("probe") or {}).get("ticks_per_second"),
            "startedAtMs": now_ms(),
            "version": state.get("version"),
            "commit": git_commit(game_dir),
        }
        with open(self.path("session.json"), "w", encoding="utf-8") as f:
            json.dump(info, f, indent=2)
        return info

    def _await_window(self, profile: Dict[str, Any], game: "subprocess.Popen", use_probe: bool, env: Dict[str, str]) -> str:
        timeout = float(profile["launch"].get("start_timeout_sec", 90))
        deadline = time.time() + timeout
        state_path = os.path.join(self.probe_dir, "state.json")
        window = ""
        while time.time() < deadline:
            if game.poll() is not None:
                break
            found = xdo.run(env, "search", "--name", profile["window"]["title_regex"]).split()
            window = found[0] if found else ""
            if window and (not use_probe or os.path.exists(state_path)):
                return window
            time.sleep(0.5)
        why = ("the game exited with status %s" % game.returncode if game.poll() is not None
               else "no window matching %r%s after %gs" % (profile["window"]["title_regex"],
                                                            " with a state.json" if use_probe else "", timeout))
        raise HarnessError("the game did not come up in session %s (%s). Last lines of %s:\n%s"
                           % (self.name, why, self.path("game.log"), tail(self.path("game.log"))))

    def stop(self) -> None:
        """Stops the game, then its Xvfb. Safe to repeat."""
        for name, grace in (("game", 5.0), ("xvfb", 3.0)):
            pid = self._pid(name)
            if pid and pid_alive(pid):
                _terminate(pid, grace)
            try:
                os.remove(self.path(name + ".pid"))
            except OSError:
                pass
        for name in ("window",):
            try:
                os.remove(self.path(name))
            except OSError:
                pass

    def status(self) -> Dict[str, Any]:
        game, xvfb = self._pid("game"), self._pid("xvfb")
        info = {"session": self.name, "running": self.game_alive(), "gamePid": game if pid_alive(game) else None,
                "xvfbPid": xvfb if pid_alive(xvfb) else None}  # type: Dict[str, Any]
        if self.display:
            info["display"] = ":" + self.display
        if info["running"]:
            r = subprocess.run(["ps", "-o", "%cpu=,rss=", "-p", str(game)], stdout=subprocess.PIPE, universal_newlines=True)
            parts = r.stdout.split()
            if len(parts) == 2:
                info["cpuPercent"] = float(parts[0])
                info["rssMb"] = round(int(parts[1]) / 1024.0, 1)
        state = read_json(os.path.join(self.probe_dir, "state.json"))
        if state:
            info["fps"] = state.get("fps")
            info["tps"] = state.get("tps")
            info["screen"] = state.get("screen")
            info["stateAgeSec"] = round((now_ms() - state.get("wallTimeMs", 0)) / 1000.0, 1)
        return info


def _terminate(pid: int, grace: float) -> None:
    """TERM the process group (the session leader and anything it spawned), then KILL after ``grace``."""
    def send(sig):
        try:
            os.killpg(pid, sig)
        except OSError:
            try:
                os.kill(pid, sig)
            except OSError:
                pass
    send(signal.SIGTERM)
    deadline = time.time() + grace
    while time.time() < deadline and pid_alive(pid):
        time.sleep(0.1)
    if pid_alive(pid):
        send(signal.SIGKILL)
        time.sleep(0.2)


def git_commit(game_dir: str) -> Optional[str]:
    try:
        r = subprocess.run(["git", "-C", game_dir, "rev-parse", "--short", "HEAD"], stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, universal_newlines=True, timeout=10)
        return r.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None
