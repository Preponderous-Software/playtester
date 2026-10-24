"""One playtest session: a game in its own Xvfb (or driven headless), with its own files.

Everything a session owns lives in ``$PT_ROOT/$PT_SESSION``::

    session.json      display, window, profile, game args, version, commit,
                      dirty, builtAtMs, buildWarnings (see ``build_check``)
    profile.json      the resolved profile the session was started with
    actions.jsonl     every harness command, with its time (for repro)
    findings.jsonl    ``pt note``: raw notes as they were taken
    trace.jsonl       each step of ``face`` and ``walkto``
    report.json       the agent's report
    shots/*.png       screenshots
    out/              the game's probe output (state.json, events.jsonl)
    data/             the game's saves and settings for this session
    game.log, xvfb.log
    display, game.pid, xvfb.pid, window   while running (X11 driver)
    drive.jsonl       every drive-channel line, both ways (Strata driver)
    relay.log, relay.pid, drive.sock, control.sock   while running (Strata driver)

The Strata driver (``"driver": "strata"``, strata_driver.py) starts no Xvfb:
the game renders headless and takes its input through its drive channel.

A pid file holds the pid and the process's start time (``PID START``, the
start time being field 22 of ``/proc/PID/stat``). Before signalling a pid the
harness checks the start time still matches, so a stale pid file left behind
by a crash or a reboot never signals an unrelated process that has since been
given the same pid.

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
from typing import Any, Dict, List, Optional, Tuple

from . import inputs
from . import profile as profiles
from . import strata_driver
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


def proc_start_time(pid: int) -> Optional[str]:
    """The start time of ``pid`` (field 22 of /proc/PID/stat, in clock ticks since boot), or None."""
    try:
        with open("/proc/%d/stat" % pid) as f:
            # the command name (field 2) is in parentheses and may contain spaces
            fields = f.read().rsplit(")", 1)[1].split()
        return fields[19]
    except (OSError, IndexError, ValueError):
        return None


def proc_cmdline(pid: int) -> str:
    """The command line of ``pid`` with its arguments joined by spaces ("" if unknown)."""
    try:
        with open("/proc/%d/cmdline" % pid, "rb") as f:
            return f.read().replace(b"\0", b" ").decode("utf-8", "replace").strip()
    except OSError:
        return ""


def parse_pid_file(text: Optional[str]) -> Tuple[Optional[int], Optional[str]]:
    """``(pid, start_time)`` from a pid file's text; start_time is None in old files that hold only the pid."""
    parts = (text or "").split()
    try:
        pid = int(parts[0]) if parts else None
    except ValueError:
        return None, None
    return pid, (parts[1] if len(parts) > 1 else None)


def pid_file_text(pid: int) -> str:
    start = proc_start_time(pid)
    return "%d %s" % (pid, start) if start else str(pid)


def same_process(pid: Optional[int], start_time: Optional[str], expected: List[str]) -> bool:
    """Whether the live process ``pid`` is the one the pid file recorded.

    With a recorded start time, the process's start time must match. An old
    pid file without one is trusted only when the process's command line
    contains one of ``expected`` (for example the game's executable).
    """
    if not pid_alive(pid):
        return False
    if start_time is not None:
        return proc_start_time(pid) == start_time
    cmdline = proc_cmdline(pid)
    return bool(cmdline) and any(e and e in cmdline for e in expected)


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
        """The pid recorded in NAME.pid, if that process is still the one the session started."""
        pid, start_time = parse_pid_file(self._read(name + ".pid"))
        if pid is None:
            return None
        return pid if same_process(pid, start_time, self._expected_commands(name)) else None

    def _expected_commands(self, name: str) -> List[str]:
        """What the command line of an old-style pid file's process must contain."""
        if name == "xvfb":
            return ["Xvfb"]
        if name == "relay":
            return ["strata_relay"]
        expected = []
        command = self.info().get("command")
        if isinstance(command, list) and command:
            expected.append(str(command[0]))
        saved = read_json(self.path("profile.json")) or {}
        if saved.get("process_name"):
            expected.append(str(saved["process_name"]).strip())
        return expected

    def _write_pid(self, name: str, pid: int) -> None:
        with open(self.path(name + ".pid"), "w") as f:
            f.write(pid_file_text(pid))

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

    @property
    def driver(self) -> str:
        return self.info().get("driver") or self.profile().get("driver") or "x11"

    def channel(self) -> strata_driver.Channel:
        """The drive channel of a Strata-driver session (one connection to the relay per Session object)."""
        control = self.info().get("controlSocket") or self.path("control.sock")
        cached = getattr(self, "_channel", None)
        if cached is None or cached.path != control:
            if cached is not None:
                cached.close()
            cached = strata_driver.Channel(control)
            self._channel = cached
        return cached

    def input(self) -> Any:
        """The game's input, screenshots and clock, for whichever driver started it."""
        self.need_game()
        if self.driver == "strata":
            info = self.info()
            return inputs.StrataInput(self.channel(), info.get("clock", "free"),
                                      float(info.get("step") or strata_driver.DEFAULT_STEP), self.path("pointer"))
        return inputs.X11Input(self.input_env(), self.window or "")

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
                self._write_pid("xvfb", proc.pid)
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
              lp_threads: Optional[str] = None, clock: Optional[str] = None,
              step: Optional[float] = None) -> Dict[str, Any]:
        """Xvfb on a free display, then the game; waits for its window (and first state.json).

        With ``"driver": "strata"`` there is no Xvfb: see ``_start_strata``.
        On any failure prints why (the end of the game's log), stops whatever
        was started and raises HarnessError.
        """
        if (profile.get("driver") or "x11") == "strata":
            return self._start_strata(profile, game_dir, seed, extra_args, use_probe, width, height, lp_threads,
                                      clock or "free", step)
        if clock not in (None, "free"):
            raise HarnessError("--clock %s needs a profile with \"driver\": \"strata\" (the %s profile drives "
                               "the game through X11)" % (clock, profile["name"]))
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
        build = build_check(game_dir, plan["artifact"])
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
            self._write_pid("game", game.pid)
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
            "dirty": build["dirty"],
            "builtAtMs": build["builtAtMs"],
            "buildWarnings": build["warnings"],
            "driver": "x11",
        }
        with open(self.path("session.json"), "w", encoding="utf-8") as f:
            json.dump(info, f, indent=2)
        return info

    def _start_strata(self, profile: Dict[str, Any], game_dir: str, seed: Optional[str], extra_args: List[str],
                      use_probe: bool, width: Optional[int], height: Optional[int], lp_threads: Optional[str],
                      clock: str, step: Optional[float]) -> Dict[str, Any]:
        """The relay, then the game with STRATA_DRIVE set; waits for it to connect (and for its first state.json).

        No Xvfb, xdotool or ImageMagick. The game renders on a headless EGL
        surface and connects to the relay's socket; it never listens itself.
        """
        if clock not in ("free", "stepped"):
            raise HarnessError("--clock must be free or stepped (got %r)" % clock)
        step = float(step or strata_driver.DEFAULT_STEP)
        if not 0.0 < step <= 1.0:
            raise HarnessError("--step must be in (0, 1] seconds")
        if self.game_alive():
            raise HarnessError("session %s is already running (pt stop first)" % self.name)
        self.stop()
        width = int(width or profile["window"]["width"])
        height = int(height or profile["window"]["height"])
        use_probe = bool(use_probe and profile.get("probe"))
        for sub in ("data", "out", "shots"):
            os.makedirs(self.path(sub), exist_ok=True)
        for stale in ("drive.jsonl", "pointer"):
            try:
                os.remove(self.path(stale))
            except OSError:
                pass
        resolved = dict(profile, _game_dir=game_dir, _probe=use_probe)
        with open(self.path("profile.json"), "w", encoding="utf-8") as f:
            json.dump(resolved, f, indent=2)
        plan = profiles.launch_plan(profile, game_dir, self.dir, width, height, seed, extra_args, use_probe)
        if not shutil.which(plan["command"][0]) and not os.access(plan["command"][0], os.X_OK):
            hint = profile.get("build", {}).get("command") if isinstance(profile.get("build"), dict) else None
            raise HarnessError("no game executable at %s%s" % (plan["command"][0], " (build it: %s)" % hint if hint else ""))
        build = build_check(game_dir, plan["artifact"])
        timeout = float(profile["launch"].get("start_timeout_sec", 90))
        sock_dir = strata_driver.socket_dir(self.dir)
        drive_sock = os.path.join(sock_dir, "drive.sock")
        control_sock = os.path.join(sock_dir, "control.sock")
        # session.json first, so stop() and the commands below find the sockets
        info = {"session": self.name, "dir": self.dir, "driver": "strata", "clock": clock, "step": step,
                "driveSocket": drive_sock, "controlSocket": control_sock}  # type: Dict[str, Any]
        with open(self.path("session.json"), "w", encoding="utf-8") as f:
            json.dump(info, f, indent=2)
        try:
            relay = strata_driver.start_relay(self.dir, sock_dir, self.path("drive.jsonl"), timeout + 30)
            self._write_pid("relay", relay.pid)
            state_path = os.path.join(self.probe_dir, "state.json")
            if os.path.exists(state_path):
                os.remove(state_path)
            env = dict(os.environ, **plan["env"])
            env.update(SOFTWARE_GL)
            # no display: a game that ignored the drive channel must fail here,
            # not open a window on someone's desktop
            for key in ("DISPLAY", "WAYLAND_DISPLAY"):
                env.pop(key, None)
            env.update({"STRATA_DRIVE": drive_sock, "STRATA_DRIVE_SURFACE": "headless",
                        "STRATA_DRIVE_CLOCK": clock, "STRATA_DRIVE_STEP": repr(step)})
            env["LP_NUM_THREADS"] = str(lp_threads or os.environ.get("PT_LP_THREADS") or profile["launch"].get("lp_threads") or 2)
            env["PT_SESSION_DIR"] = self.dir
            with open(self.path("game.log"), "w") as log:
                game = subprocess.Popen(plan["command"], cwd=plan["cwd"], env=env, stdin=subprocess.DEVNULL,
                                        stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            self._write_pid("game", game.pid)
            channel = strata_driver.Channel(control_sock)
            try:
                hello = strata_driver.await_connection(channel, game, timeout)
                inp = inputs.StrataInput(channel, clock, step, self.path("pointer"))
                self._settle_strata(profile, inp, game, use_probe, state_path, timeout)
            finally:
                channel.close()
        except strata_driver.DriveError as e:
            self.stop()
            raise HarnessError("the game did not come up in session %s (%s). Last lines of %s:\n%s"
                               % (self.name, e, self.path("game.log"), tail(self.path("game.log"))))
        except BaseException:
            self.stop()
            raise
        state = read_json(state_path) or {}
        info.update({
            "profile": profile["name"],
            "size": "%dx%d" % (width, height),
            "seed": seed,
            "args": list(extra_args),
            "command": plan["command"],
            "probe": use_probe,
            "ticksPerSecond": (profile.get("probe") or {}).get("ticks_per_second"),
            "startedAtMs": now_ms(),
            "version": state.get("version"),
            "commit": git_commit(game_dir),
            "dirty": build["dirty"],
            "builtAtMs": build["builtAtMs"],
            "buildWarnings": build["warnings"],
            "strata": hello.get("strata"),
            "abi": hello.get("abi"),
            "surface": hello.get("surface"),
        })
        with open(self.path("session.json"), "w", encoding="utf-8") as f:
            json.dump(info, f, indent=2)
        return info

    def _settle_strata(self, profile: Dict[str, Any], inp: "inputs.StrataInput", game: "subprocess.Popen",
                       use_probe: bool, state_path: str, timeout: float) -> None:
        """Lets the first frames run: settle_sec of game time, then (with a probe) until state.json exists."""
        inp.wait(float(profile["launch"].get("settle_sec", 0)))
        if not use_probe:
            return
        deadline = time.time() + timeout
        while not os.path.exists(state_path):
            if game.poll() is not None:
                raise strata_driver.DriveError("the game exited with status %s" % game.returncode)
            if time.time() > deadline:
                raise strata_driver.DriveError("no state.json after %gs" % timeout)
            if inp.stepped:
                inp.step(15)
            time.sleep(0.2)

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
        """Stops the game, then its Xvfb. Safe to repeat.

        Only signals a process that is still the one this session started
        (see ``same_process``); a stale pid file is just removed.
        """
        if self.info().get("driver") == "strata" and self.game_alive():
            self._quit_strata()
        for name, grace in (("game", 5.0), ("xvfb", 3.0), ("relay", 3.0)):
            pid = self._pid(name)
            if pid:
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

    def _quit_strata(self) -> None:
        """Asks a driven game to quit the way a player would (a QUIT event), so it shuts down cleanly."""
        channel = self.channel()
        try:
            channel.request("event", type="quit", timeout=5.0)
            if self.info().get("clock") == "stepped":
                channel.request("step", frames=2, timeout=10.0)
            channel.request("bye", timeout=5.0)
        except (strata_driver.DriveError, OSError):
            pass
        finally:
            channel.close()
        deadline = time.time() + 5.0
        while time.time() < deadline and self.game_alive():
            time.sleep(0.1)

    def status(self) -> Dict[str, Any]:
        game, xvfb = self._pid("game"), self._pid("xvfb")
        info = {"session": self.name, "running": self.game_alive(), "gamePid": game if pid_alive(game) else None,
                "xvfbPid": xvfb if pid_alive(xvfb) else None}  # type: Dict[str, Any]
        if self.display:
            info["display"] = ":" + self.display
        if self.info().get("driver") == "strata":
            info["driver"] = "strata"
            info["clock"] = self.info().get("clock")
            if info["running"]:
                channel = self.channel()
                try:
                    stats = channel.request("stats", timeout=10.0)
                    info["frame"] = stats.get("frame")
                    info["step"] = stats.get("step")
                except (strata_driver.DriveError, OSError) as e:
                    info["driveError"] = str(e)
                finally:
                    channel.close()
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


def _git(game_dir: str, *args: str) -> Optional[str]:
    """The output of ``git -C game_dir ARGS``, or None when git fails (no git, not a checkout)."""
    try:
        r = subprocess.run(["git", "-C", game_dir] + list(args), stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, universal_newlines=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def git_commit(game_dir: str) -> Optional[str]:
    return (_git(game_dir, "rev-parse", "--short", "HEAD") or "").strip() or None


def build_check(game_dir: str, artifact: Optional[str]) -> Dict[str, Any]:
    """Whether the build the session runs is the checkout's commit.

    Returns ``builtAtMs`` (the artifact's modification time, or None),
    ``dirty`` (tracked files in the checkout have uncommitted changes, or
    None outside a git checkout) and ``warnings``: one line each when the
    artifact is older than the HEAD commit, or older than an uncommitted
    edit, either of which means ``commit`` does not describe what runs.
    """
    built = None  # type: Optional[float]
    if artifact:
        try:
            built = os.path.getmtime(artifact)
        except OSError:
            pass
    warnings = []  # type: List[str]
    committed = (_git(game_dir, "log", "-1", "--format=%ct") or "").strip()
    if built is not None and committed.isdigit() and built < int(committed):
        warnings.append("%s was built before the checkout's HEAD commit; rebuild it or the session runs old code"
                        % artifact)
    status = _git(game_dir, "status", "--porcelain", "--untracked-files=no")
    dirty = None if status is None else bool(status.strip())
    if dirty and built is not None:
        # porcelain paths are relative to the top of the checkout, which
        # game_dir need not be
        top = (_git(game_dir, "rev-parse", "--show-toplevel") or "").strip() or game_dir
        edited = []
        for line in status.splitlines():
            path = line[3:].split(" -> ")[-1].strip('"')
            try:
                if os.path.getmtime(os.path.join(top, path)) > built:
                    edited.append(path)
            except OSError:
                pass
        if edited:
            warnings.append("%s was built before uncommitted edits to %s; rebuild it or the session runs old code"
                            % (artifact, ", ".join(edited[:3]) + (" and %d more" % (len(edited) - 3) if len(edited) > 3 else "")))
    return {"builtAtMs": int(built * 1000) if built is not None else None, "dirty": dirty, "warnings": warnings}
