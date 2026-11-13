"""The OCR probe: probe lines read off the screen, for games that cannot write files while they run.

    python -m playtester.harness.windows_ocr --session DIR [--once]

Mount&Blade: Warband's scripts cannot write files, and its ``rgl_log.txt`` is
written only when the game exits (measured 2026-11-12, Steam Warband 1.174),
so nothing on disk changes while it runs. What it can do is show a line in
its message window. A mod's test build can show a short probe line
(docs/PROBE_LINES.md, ``ptline``) every in-game hour and on events, in a
colour nothing else on screen uses. With ``windows.ocr`` in the profile,
``pt start`` runs this reader beside the session's relay:

1. every ``interval_sec`` it asks the helper for the region ``rect`` of the
   game's window at full resolution, with only the pixels near ``color``
   kept (black on white: the helper does the filtering, so this side stays
   standard-library Python);
2. runs ``tesseract`` on it (page segmentation ``psm``, characters limited
   to ``whitelist``);
3. hands the text lines to ``windows_log.ingest``: lines with a bad check
   digit are dropped, lines already seen in an earlier screenshot are kept
   once (their ``seq``), and new ones become events in ``events.jsonl`` and
   the latest state in ``state.json``.

It writes ``out/ocr/last.png`` (the latest filtered capture), keeps the
captures that gave new lines in ``out/ocr/frames/`` (at most ``KEEP_FRAMES``),
logs what it read to ``out/ocr.log`` and its counts to ``out/ocr.json``. It
stops when the session's relay or the game is gone. Without ``tesseract``
it writes why to ``out/ocr.log`` and exits; the session is then
screenshot-only, as without a probe.

Alternatives weighed (2026-11-12), for the record:

- ``rgl_log.txt``: written at exit only, and without ``display_log_message``
  text; kept as a post-mortem source of script errors (``windows_log``).
- Saving the game to read the save file: changes what is being tested (and
  the player's saves), needs input, and is slow.
- A presentation drawing numbers at a fixed spot: needs per-glyph templates
  and takes over part of the screen for the whole session; the message
  window is already there, scrolls (several lines a frame survive a missed
  capture) and needs no new UI.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional

from . import windows_log

DEFAULTS = {"rect": [0.0, 0.5, 0.6, 0.94], "color": "#FF00FF", "tolerance": 90, "scale": 1.0,
            "interval_sec": 1.5, "psm": 6, "whitelist": "PTSMEB0123456789-"}
KEEP_FRAMES = 200


def settings(win: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The profile's ``windows.ocr`` with its defaults, or None when the profile has none."""
    ocr = win.get("ocr")
    if not isinstance(ocr, dict):
        return None
    out = dict(DEFAULTS)
    out.update(ocr)
    return out


def rgb(color: str) -> List[int]:
    """``#FF00FF`` -> ``[255, 0, 255]``."""
    c = color.lstrip("#")
    return [int(c[i:i + 2], 16) for i in (0, 2, 4)]


def region(client: List[int], rect: List[float]) -> List[int]:
    """Screen pixels ``[x, y, w, h]`` of fractions ``[left, top, right, bottom]`` of a client area."""
    left, top, w, h = (int(v) for v in client[:4])
    x0, y0 = left + int(round(rect[0] * w)), top + int(round(rect[1] * h))
    x1, y1 = left + int(round(rect[2] * w)), top + int(round(rect[3] * h))
    return [x0, y0, max(1, x1 - x0), max(1, y1 - y0)]


def shot_request(client: List[int], cfg: Dict[str, Any], path: str) -> Dict[str, Any]:
    """The helper request for one filtered capture."""
    x, y, w, h = region(client, cfg["rect"])
    scale = float(cfg.get("scale") or 1.0)
    return {"rect": [x, y, w, h], "width": int(round(w * scale)), "height": int(round(h * scale)),
            "path": path, "keep": rgb(cfg["color"]) + [int(cfg["tolerance"])]}


def tesseract_command(png: str, cfg: Dict[str, Any]) -> List[str]:
    cmd = ["tesseract", png, "stdout", "--psm", str(int(cfg["psm"]))]
    if cfg.get("whitelist"):
        cmd += ["-c", "tessedit_char_whitelist=" + cfg["whitelist"] + " "]
    return cmd


def read_text(png: str, cfg: Dict[str, Any], timeout: float = 30.0) -> List[str]:
    """The text lines tesseract reads in ``png`` (no empty ones)."""
    r = subprocess.run(tesseract_command(png, cfg), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                       universal_newlines=True, timeout=timeout)
    return [l.strip() for l in r.stdout.splitlines() if l.strip()]


class Reader:
    """One session's OCR reader (``run`` loops; ``poll`` is one capture)."""

    def __init__(self, session_dir: str, channel: Any = None, to_windows_path: Any = None,
                 ocr_text: Any = None):
        from .windows_driver import windows_path
        self.dir = session_dir
        self.out = os.path.join(session_dir, "out")
        self.ocr_dir = os.path.join(self.out, "ocr")
        os.makedirs(os.path.join(self.ocr_dir, "frames"), exist_ok=True)
        with open(os.path.join(session_dir, "profile.json"), encoding="utf-8") as f:
            self.profile = json.load(f)
        self.cfg = settings(self.profile.get("windows") or {}) or dict(DEFAULTS)
        self.channel = channel
        self.to_windows_path = to_windows_path or windows_path
        self.ocr_text = ocr_text or read_text
        self.stats = {"captures": 0, "lines": 0, "new": 0, "failed": 0, "started": windows_log.now_ms()}
        self.kept = 0

    def info(self) -> Dict[str, Any]:
        try:
            with open(os.path.join(self.dir, "session.json"), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def version(self) -> str:
        title = self.profile.get("title") or self.profile.get("name") or "game"
        module = self.info().get("module")
        return "%s (%s)" % (module, title) if module else str(title)

    def log(self, text: str) -> None:
        with open(os.path.join(self.out, "ocr.log"), "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (time.strftime("%H:%M:%S"), text))

    def poll(self) -> List[str]:
        """One capture: returns the new probe lines it gave."""
        info = self.info()
        hwnd = info.get("hwnd")
        if not hwnd:
            return []
        w = self.channel.request("window", hwnd=hwnd).get("window") or {}
        client = w.get("client") or info.get("client")
        if not client or w.get("minimized"):
            return []
        png = os.path.join(self.ocr_dir, "last.png")
        self.channel.request("shot", timeout=30.0, **shot_request(client, self.cfg, self.to_windows_path(png)))
        self.stats["captures"] += 1
        lines = self.ocr_text(png, self.cfg)
        self.stats["lines"] += len(lines)
        new = windows_log.ingest(self.out, lines, self.version())
        if lines:
            self.log("read %r -> new %r" % (lines, new))
        if new:
            self.stats["new"] += len(new)
            if self.kept < KEEP_FRAMES and os.path.exists(png):
                self.kept += 1
                shutil.copyfile(png, os.path.join(self.ocr_dir, "frames", "%04d.png" % self.kept))
        windows_log.write_json_atomic(os.path.join(self.out, "ocr.json"), dict(self.stats, updated=windows_log.now_ms()))
        return new

    def alive(self) -> bool:
        info = self.info()
        pid = info.get("gamePid")
        if not pid:
            return False
        return bool(self.channel.request("alive", pid=pid, startTicks=info.get("gameStartTicks"), timeout=15.0)
                    .get("alive"))

    def run(self, once: bool = False) -> int:
        if not shutil.which("tesseract") and self.ocr_text is read_text:
            self.log("tesseract is not installed (apt install tesseract-ocr): no OCR probe in this session")
            return 2
        self.log("reading %s every %ss" % (self.cfg["rect"], self.cfg["interval_sec"]))
        from .strata_driver import DriveError
        misses = 0
        while True:
            started = time.time()
            try:
                self.poll()
                if not self.alive():
                    self.log("the game is gone; stopping")
                    return 0
                misses = 0
            except (DriveError, OSError, subprocess.SubprocessError, ValueError) as e:
                self.stats["failed"] += 1
                misses += 1
                self.log("capture failed: %s" % e)
                self.channel.close()
                if misses >= 10 or not os.path.exists(os.path.join(self.dir, "control.sock")):
                    self.log("the session's relay is gone; stopping")
                    return 0
            if once:
                return 0
            time.sleep(max(0.0, float(self.cfg["interval_sec"]) - (time.time() - started)))


class ShortChannel:
    """A channel to the relay that connects for each request and lets go after it: the relay serves one
    client at a time, so ``pt`` commands only ever wait for one capture."""

    def __init__(self, path: str):
        self.path = path

    def request(self, op: str, timeout: float = 60.0, **fields: Any) -> Dict[str, Any]:
        from .strata_driver import Channel
        ch = Channel(self.path, timeout=timeout)
        try:
            return ch.request(op, timeout=timeout, **fields)
        finally:
            ch.close()

    def close(self) -> None:
        pass


def start(session: Any) -> Optional[int]:
    """Starts the reader for a session whose profile asks for it (``windows.ocr``); returns its pid."""
    win = session.profile().get("windows") or {}
    if not settings(win):
        return None
    pkg_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    env = dict(os.environ)
    env["PYTHONPATH"] = pkg_root + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    with open(session.path("ocr.stderr"), "w") as log:
        proc = subprocess.Popen([sys.executable, "-m", "playtester.harness.windows_ocr", "--session", session.dir],
                                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, env=env,
                                start_new_session=True)
    session._write_pid("ocr", proc.pid)
    return proc.pid


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="windows_ocr")
    ap.add_argument("--session", required=True, help="the session's directory")
    ap.add_argument("--once", action="store_true", help="one capture, then exit")
    a = ap.parse_args(argv)
    with open(os.path.join(a.session, "session.json"), encoding="utf-8") as f:
        control = json.load(f).get("controlSocket") or os.path.join(a.session, "control.sock")
    return Reader(a.session, ShortChannel(control)).run(once=a.once)


if __name__ == "__main__":
    sys.exit(main())
