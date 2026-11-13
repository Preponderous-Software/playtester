"""Starting, stopping and checking a Windows-driver session (``"driver": "windows"``).

``Session`` (session.py) hands its windows-driver sessions to these functions;
``windows_driver`` holds the lock, the helper's command line and the
coordinates, ``windows_log`` the log probe. See windows_driver's docstring for
how a session runs, and docs/PROFILES.md#drivers for the profile fields.
"""

import json
import os
import re
import shutil
import time
from typing import Any, Dict, List, Optional

from . import inputs, windows_driver, windows_log, windows_ocr
from . import profile as profiles
from .strata_driver import Channel, DriveError


def _errors():
    from .session import HarnessError
    return HarnessError


def settings(profile: Dict[str, Any], game_dir: str, session_dir: str, module: Optional[str]) -> Dict[str, Any]:
    """The profile's ``windows`` section with its placeholders filled in (``{module}`` too)."""
    win = dict(profile.get("windows") or {})
    chosen = module or os.environ.get("PT_MODULE") or win.get("module")
    variables = {"game_dir": game_dir, "session_dir": session_dir, "data_dir": os.path.join(session_dir, "data"),
                 "probe_dir": os.path.join(session_dir, "out")}
    if chosen:
        variables["module"] = chosen
    win = profiles.expand(win, variables)
    win["module"] = chosen
    return win


def game_alive(session: Any) -> bool:
    """Whether the game this session drives still runs (asked through the helper; False without one)."""
    info = session.info()
    if not info.get("gamePid") or not session._pid("relay"):
        return False
    # the session's one connection: the relay serves one client at a time, so a
    # second connection from the same process would wait behind the first
    ch = session.channel()
    try:
        return bool(ch.request("alive", pid=info["gamePid"], startTicks=info.get("gameStartTicks"),
                               timeout=15.0).get("alive"))
    except (DriveError, OSError):
        ch.close()
        return False


def make_input(session: Any) -> inputs.WindowsInput:
    info = session.info()
    if not info.get("hwnd"):
        raise _errors()("session %s has no game window (pt start first)" % session.name)
    return inputs.WindowsInput(session.channel(), info["hwnd"], info.get("shotSize") or [1280, 720],
                               windows_driver.windows_path)


def _write_info(session: Any, info: Dict[str, Any]) -> None:
    with open(session.path("session.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2)


def await_window(ch: Channel, pid: int, start_ticks: Optional[str], win: Dict[str, Any], title_regex: str,
                 timeout: float, launched: bool, log: Any = None) -> Dict[str, Any]:
    """Waits for the game's window, pressing through the launcher dialog of a game pt launched.

    The game's window is the largest visible window of the process whose
    title matches ``title_regex`` and whose client area is at least
    ``windows.min_width`` wide. With ``windows.launcher``, a smaller window of
    the process is taken for a launcher: it is brought to the front and sent
    ``launcher.keys`` (at most ``launcher.attempts`` times, a few seconds apart).
    When Windows will not bring it to the front (the helper's ``focus``
    already taps Alt and attaches to the window's thread), ``launcher.click``
    (fractions of its client area) is clicked instead: a real click activates
    the dialog and presses its start button.
    """
    HarnessError = _errors()
    min_width = int(win.get("min_width", 0))
    launcher = win.get("launcher") or {}
    presses = 0
    last_press = 0.0
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not ch.request("alive", pid=pid, startTicks=start_ticks).get("alive"):
            raise HarnessError("the game exited before its window appeared")
        windows = ch.request("windows", pid=pid).get("windows") or []
        game = windows_driver.pick_window(windows, title_regex, min_width)
        if game:
            return game
        if launched and launcher and presses < int(launcher.get("attempts", 3)) and time.time() - last_press > 4:
            small = [w for w in windows if int(w["client"][2]) < min_width and int(w["client"][2]) > 0
                     and re.search(launcher.get("title_regex", ""), w.get("title") or "")]
            if small:
                focus = ch.request("focus", hwnd=small[0]["hwnd"])
                click = launcher.get("click")
                if not focus.get("foreground") and click:
                    client = (focus.get("window") or small[0])["client"]
                    x = int(client[0]) + int(round(float(click[0]) * int(client[2])))
                    y = int(client[1]) + int(round(float(click[1]) * int(client[3])))
                    ch.request("move", x=x, y=y)
                    time.sleep(0.1)
                    ch.request("button", button=1, up=False)
                    time.sleep(0.05)
                    ch.request("button", button=1, up=True)
                    presses += 1
                    last_press = time.time()
                    if log:
                        log("clicked the launcher at %d,%d (%r would not come to the front for keys)"
                            % (x, y, small[0]["title"]))
                elif focus.get("foreground"):
                    from . import windows_keys, xdo
                    for key in launcher.get("keys") or ["Return"]:
                        keys = windows_keys.combo_scancodes(xdo.combo_parts(key))
                        ch.request("key", keys=keys, up=False)
                        time.sleep(xdo.TAP_HOLD)
                        ch.request("key", keys=keys, up=True)
                        time.sleep(0.3)
                    presses += 1
                    last_press = time.time()
                    if log:
                        log("pressed %s in the launcher (%r)" % (launcher.get("keys") or ["Return"], small[0]["title"]))
        time.sleep(1.0)
    raise HarnessError("no window matching %r at least %d pixels wide after %gs" % (title_regex, min_width, timeout))


def start(session: Any, profile: Dict[str, Any], game_dir: str, extra_args: List[str], use_probe: bool,
          width: Optional[int], height: Optional[int], attach: bool, module: Optional[str]) -> Dict[str, Any]:
    """Takes the desktop lock, starts the helper, launches (or attaches to) the game and finds its window."""
    HarnessError = _errors()
    from .session import now_ms, git_commit
    if session.game_alive():
        raise HarnessError("session %s is already running (pt stop first)" % session.name)
    session.stop()
    win = settings(profile, game_dir, session.dir, module)
    if not win.get("process"):
        raise HarnessError("the %s profile has no windows.process (the game's process name)" % profile["name"])
    shot = windows_driver.shot_size(profile, int(width) if width else None, int(height) if height else None)
    for sub in ("data", "out", "shots"):
        os.makedirs(session.path(sub), exist_ok=True)
    for stale in ("desktop.jsonl", "game.log", os.path.join("out", windows_log.OFFSET_FILE),
                  os.path.join("out", windows_log.DECODER_FILE)):
        try:
            os.remove(session.path(stale))
        except OSError:
            pass
    resolved = dict(profile, _game_dir=game_dir, _probe=bool(win.get("log")), windows=win)
    with open(session.path("profile.json"), "w", encoding="utf-8") as f:
        json.dump(resolved, f, indent=2)
    plan = profiles.launch_plan(profile, game_dir, session.dir, shot[0], shot[1], None, extra_args, use_probe)
    exe = plan["command"][0]
    if not attach and not os.path.isfile(exe):
        raise HarnessError("no game executable at %s (pt start --game-dir: the game's install folder)" % exe)
    try:
        windows_driver.acquire_lock(session.name, session.root, os.getpid())
    except windows_driver.DesktopLockError as e:
        raise HarnessError(str(e))
    control = session.path("control.sock")
    # values an earlier session could not put back (its helper was gone at pt stop): put back first
    leftover = list(session.info().get("registryRestore") or [])
    info = {"session": session.name, "dir": session.dir, "driver": "windows", "profile": profile["name"],
            "controlSocket": control, "attached": bool(attach), "shotSize": list(shot),
            "lock": windows_driver.lock_path()}  # type: Dict[str, Any]
    log_path = win.get("log")
    if log_path:
        info["logPath"] = log_path
    if leftover:
        info["registryRestore"] = leftover
    _write_info(session, info)
    timeout = float(profile["launch"].get("start_timeout_sec", 90))
    events = []  # type: List[str]
    try:
        try:
            relay = windows_driver.start_relay(session.dir, control, session.path("desktop.jsonl"))
        except RuntimeError as e:
            raise HarnessError(str(e))
        session._write_pid("relay", relay.pid)
        windows_driver.update_lock(session.name, session.root, relay.pid)
        ch = Channel(control, timeout=60.0)
        try:
            # what this helper may touch: the profile's registry values, this session's folder for
            # screenshots, the game's executable (and only processes it launches may be closed)
            keys = [windows_driver.registry_path(e["key"]) for e in win.get("registry") or []]
            ch.request("policy", registry=sorted(set(keys + [e["key"] for e in leftover])),
                       shotDir=windows_driver.windows_path(session.dir), exe=windows_driver.windows_path(exe))
            if leftover:
                info["registryRestore"] = _restore_registry(ch, leftover)
                _write_info(session, info)
            running = ch.request("processes", name=win["process"]).get("processes") or []
            if attach:
                if not running:
                    raise HarnessError("no running %s to attach to (start the game, or pt start without --attach "
                                       "to launch it)" % win["process"])
                proc = running[0]
                if log_path and os.path.exists(log_path):
                    # only what the game logs from now on
                    with open(session.path("out", windows_log.OFFSET_FILE), "w") as f:
                        f.write(str(os.path.getsize(log_path)))
            else:
                if running:
                    raise HarnessError("%s is already running (pid %s): pt start --attach drives that copy; pt will "
                                       "not start a second one or close it" % (win["process"], running[0]["pid"]))
                info["registryRestore"] = (info.get("registryRestore") or []) + _set_registry(ch, win.get("registry") or [])
                _write_info(session, info)
                if log_path and os.path.exists(log_path):
                    # the game starts its log again; keep the old one with the session
                    shutil.copyfile(log_path, session.path("log-before-start.txt"))
                    os.remove(log_path)
                launched = ch.request("launch", path=windows_driver.windows_path(exe), args=plan["command"][1:],
                                      cwd=windows_driver.windows_path(plan["cwd"]) if plan.get("cwd") else None)
                proc = {"pid": launched["pid"], "startTicks": launched.get("startTicks")}
            info.update({"gamePid": proc["pid"], "gameStartTicks": proc.get("startTicks")})
            _write_info(session, info)
            window = await_window(ch, proc["pid"], proc.get("startTicks"), win, profile["window"].get("title_regex", ""),
                                  timeout, not attach, events.append)
            focus = ch.request("focus", hwnd=window["hwnd"])
            if not attach:
                time.sleep(float(profile["launch"].get("settle_sec", 0)))
        finally:
            ch.close()
    except BaseException:
        stop(session)
        raise
    module_seen = windows_log.module_from_log(log_path) if log_path else None
    info.update({
        "hwnd": window["hwnd"], "title": window["title"], "client": window["client"],
        "foreground": bool(focus.get("foreground")), "module": module_seen or win.get("module"),
        "size": "%dx%d" % shot, "args": list(extra_args), "command": plan["command"], "probe": bool(log_path),
        "startedAtMs": now_ms(), "version": None, "commit": git_commit(game_dir), "dirty": None, "builtAtMs": None,
        "buildWarnings": [], "launcherPresses": events,
    })
    asked = module or os.environ.get("PT_MODULE")
    if asked and module_seen and module_seen != asked:
        info["buildWarnings"].append("the game runs module %s, not %s%s" % (
            module_seen, asked, " (--attach drives the copy that is running, as it is)" if attach else ""))
    _write_info(session, info)
    windows_log.sync(session)
    if (win.get("probe_format") == "ptline" and windows_ocr.settings(win)
            and not os.environ.get("PT_NO_OCR")):
        info["ocrPid"] = windows_ocr.start(session)
        _write_info(session, info)
    return info


def _restore_registry(ch: Channel, entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Puts back what ``_set_registry`` changed (newest first): the old value, or no value where pt
    created it. Returns the entries that could not be put back, so they are not forgotten."""
    left = []  # type: List[Dict[str, Any]]
    for entry in reversed(entries):
        try:
            if entry.get("existed"):
                ch.request("regset", key=entry["key"], name=entry["name"], value=entry.get("value") or "")
            else:
                ch.request("regdel", key=entry["key"], name=entry["name"])
        except (DriveError, OSError):
            left.insert(0, entry)
    return left


def _set_registry(ch: Channel, entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sets each ``{key, name, value}`` that differs; returns what to put back at stop."""
    restore = []
    for entry in entries:
        if entry.get("value") is None or "{" in str(entry.get("value")):
            continue  # a placeholder with nothing to fill it (no module chosen)
        key = windows_driver.registry_path(entry["key"])
        now = ch.request("regget", key=key, name=entry["name"])
        if now.get("exists") and now.get("value") == str(entry["value"]):
            continue
        ch.request("regset", key=key, name=entry["name"], value=str(entry["value"]))
        restore.append({"key": key, "name": entry["name"], "existed": bool(now.get("exists")),
                        "value": now.get("value"), "set": str(entry["value"])})
    return restore


def stop(session: Any) -> None:
    """Closes a game pt launched (never one it attached to), restores the registry, stops the helper, frees the lock.

    A registry value that could not be put back (the helper was gone) stays in ``session.json`` and is
    put back by the session's next ``pt start``."""
    info = session.info()
    win = (session.profile().get("windows") if os.path.exists(session.path("profile.json")) else None) or {}
    from .session import _terminate
    ocr = session._pid("ocr")
    if ocr:
        _terminate(ocr, 3.0)
    try:
        os.remove(session.path("ocr.pid"))
    except OSError:
        pass
    if session._pid("relay"):
        ch = session.channel()
        try:
            pid = info.get("gamePid")
            if pid and not info.get("attached"):
                ticks = info.get("gameStartTicks")
                if ch.request("alive", pid=pid, startTicks=ticks).get("alive"):
                    ch.request("close", pid=pid)
                    deadline = time.time() + float(win.get("close_timeout_sec", 15))
                    while time.time() < deadline and ch.request("alive", pid=pid, startTicks=ticks).get("alive"):
                        time.sleep(0.5)
                    if ch.request("alive", pid=pid, startTicks=ticks).get("alive"):
                        ch.request("kill", pid=pid)
            if info.get("registryRestore"):
                info["registryRestore"] = _restore_registry(ch, info["registryRestore"])
                _write_info(session, info)
            try:
                windows_log.sync(session)
            except OSError:
                pass
            ch.request("bye", timeout=5.0)
        except (DriveError, OSError):
            pass
        finally:
            ch.close()
        deadline = time.time() + 5.0
        while time.time() < deadline and session._pid("relay"):
            time.sleep(0.1)
    if "registryRestore" in info and not info["registryRestore"]:
        info.pop("registryRestore")  # everything was put back; what was not stays for the next pt start
        _write_info(session, info)
    windows_driver.release_lock(session.name, session.root)


def status(session: Any) -> Dict[str, Any]:
    info = session.info()
    out = {"session": session.name, "driver": "windows", "running": session.game_alive(),
           "gamePid": info.get("gamePid"), "attached": info.get("attached"), "module": info.get("module"),
           "lock": windows_driver.read_lock()}  # type: Dict[str, Any]
    if out["running"] and info.get("hwnd"):
        try:
            w = session.channel().request("window", hwnd=info["hwnd"]).get("window") or {}
            out.update({"title": w.get("title"), "client": w.get("client"), "minimized": w.get("minimized"),
                        "foreground": w.get("foreground")})
        except (DriveError, OSError) as e:
            out["helperError"] = str(e)
    return out
