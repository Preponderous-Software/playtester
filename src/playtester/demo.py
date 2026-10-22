"""A tiny game that implements the probe contract, for testing the harness.

    python3 -m playtester.demo [--width W] [--height H] [--seed S] [--playtest-out DIR]

A top-down clearing with a few trees. A title screen waits for Space (or a
click); in the world A and D turn, W walks, E chops a tree within reach and
Escape pauses. Chopping three trees completes the "Gather wood" objective.
It opens a real X11 window (through libX11 with ctypes, so it needs no
toolkit) titled "Playtester Demo", and with ``--playtest-out`` writes
state.json and events.jsonl exactly as docs/PROBE_CONTRACT.md describes.

It exists so the harness (start, input, screenshots, face, walkto, events,
parallel sessions) can be tested end to end in CI without a real game, and as
a short reference implementation of the probe for game authors. The bundled
``demo`` profile runs it.
"""

import ctypes
import ctypes.util
import json
import math
import os
import random
import sys
import time
from typing import Any, Dict, List, Optional

VERSION = "1.0.0"
TITLE = b"Playtester Demo"
TICKS_PER_SECOND = 30
TURN_DEGREES_PER_SECOND = 90.0
WALK_SPEED = 3.0
REACH = 1.5
WOOD_GOAL = 3
PIXELS_PER_UNIT = 16

KEY_PRESS, BUTTON_PRESS, EXPOSE, DESTROY_NOTIFY, CLIENT_MESSAGE = 2, 4, 12, 17, 33
KEY_PRESS_MASK, BUTTON_PRESS_MASK, EXPOSURE_MASK, STRUCTURE_NOTIFY_MASK = 1, 4, 1 << 15, 1 << 17


def _xlib():
    path = ctypes.util.find_library("X11")
    if not path:
        raise SystemExit("demo: libX11 not found")
    x = ctypes.cdll.LoadLibrary(path)
    x.XOpenDisplay.restype = ctypes.c_void_p
    x.XOpenDisplay.argtypes = [ctypes.c_char_p]
    for name in ("XDefaultScreen", "XPending", "XFlush"):
        getattr(x, name).argtypes = [ctypes.c_void_p]
    x.XRootWindow.restype = ctypes.c_ulong
    x.XRootWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
    x.XCreateSimpleWindow.restype = ctypes.c_ulong
    x.XCreateSimpleWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int, ctypes.c_uint,
                                      ctypes.c_uint, ctypes.c_uint, ctypes.c_ulong, ctypes.c_ulong]
    x.XStoreName.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_char_p]
    x.XSelectInput.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_long]
    x.XMapWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    x.XCreateGC.restype = ctypes.c_void_p
    x.XCreateGC.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p]
    x.XSetForeground.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
    x.XFillRectangle.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                 ctypes.c_uint, ctypes.c_uint]
    x.XDrawLine.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                            ctypes.c_int, ctypes.c_int]
    x.XDrawString.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                              ctypes.c_char_p, ctypes.c_int]
    x.XNextEvent.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    x.XLookupKeysym.restype = ctypes.c_ulong
    x.XLookupKeysym.argtypes = [ctypes.c_void_p, ctypes.c_int]
    x.XQueryKeymap.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    x.XStringToKeysym.restype = ctypes.c_ulong
    x.XStringToKeysym.argtypes = [ctypes.c_char_p]
    x.XKeysymToKeycode.restype = ctypes.c_ubyte
    x.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    return x


class Probe:
    """Writes state.json (twice a second, atomically) and events.jsonl."""

    def __init__(self, directory: Optional[str]):
        self.dir = directory
        self.next_state = 0.0
        self.last = None  # (wall seconds, tick) of the previous state, for tps
        self.tps = 0.0
        if directory:
            os.makedirs(directory, exist_ok=True)

    def event(self, kind: str, tick: int, **fields: Any) -> None:
        if not self.dir:
            return
        line = dict({"type": kind, "tick": tick, "wallTimeMs": int(time.time() * 1000)}, **fields)
        with open(os.path.join(self.dir, "events.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(line, separators=(",", ":")) + "\n")

    def state(self, game: "Game", force: bool = False) -> None:
        now = time.time()
        if not self.dir or (now < self.next_state and not force):
            return
        self.next_state = now + 0.5
        if self.last and now > self.last[0]:
            self.tps = (game.tick - self.last[1]) / (now - self.last[0])
        self.last = (now, game.tick)
        st = {"wallTimeMs": int(now * 1000), "version": VERSION, "screen": game.screen, "fps": game.fps,
              "world": game.screen != "TITLE", "tps": round(self.tps, 1), "openPanels": []}  # type: Dict[str, Any]
        if st["world"]:
            st.update({
                "seed": game.seed, "tick": game.tick,
                "player": {"x": round(game.x, 2), "z": round(game.z, 2), "yawDeg": round(game.yaw % 360.0, 1),
                           "speed": WALK_SPEED, "wood": game.wood},
                "objective": {"number": 1, "title": "Gather wood", "progress": "Wood %d/%d" % (game.wood, WOOD_GOAL),
                              "completed": 1 if game.wood >= WOOD_GOAL else 0},
                "status": game.status,
                "nearest": {"tree": game.nearest_trees()},
            })
        path = os.path.join(self.dir, "state.json")
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(st, f, separators=(",", ":"))
        os.replace(path + ".tmp", path)


class Game:
    """The rules: no X11 here, so tests can drive it directly."""

    def __init__(self, seed: int, probe: Probe):
        self.seed = seed
        self.probe = probe
        rng = random.Random(seed)
        self.trees = []  # type: List[Dict[str, Any]]
        for i in range(6):
            angle, dist = rng.uniform(0, 2 * math.pi), rng.uniform(4.0, 9.0)
            self.trees.append({"id": "t%d" % i, "x": round(math.sin(angle) * dist, 2), "z": round(-math.cos(angle) * dist, 2)})
        self.x = self.z = 0.0
        self.yaw = 180.0  # facing +z, away from most of what a player expects
        self.tick = 0
        self.wood = 0
        self.fps = 0
        self.status = None  # type: Optional[str]
        self.screen = ""
        self.set_screen("TITLE")

    def set_screen(self, screen: str) -> None:
        if screen != self.screen:
            self.probe.event("screen", self.tick, **{"from": self.screen or None, "to": screen})
            if screen == "WORLD" and self.screen == "TITLE":
                self.probe.event("world", self.tick, how="created", seed=self.seed)
            self.screen = screen

    def bearing(self, tx: float, tz: float) -> float:
        # heading grows to the right; forward is (sin yaw, -cos yaw)
        yaw = math.radians(self.yaw)
        dx, dz = tx - self.x, tz - self.z
        fwd = dx * math.sin(yaw) - dz * math.cos(yaw)
        right = dx * math.cos(yaw) + dz * math.sin(yaw)
        return math.degrees(math.atan2(right, fwd))

    def nearest_trees(self) -> List[Dict[str, Any]]:
        rows = [{"name": "Tree", "id": t["id"], "distance": round(math.hypot(t["x"] - self.x, t["z"] - self.z), 2),
                 "bearing": round(self.bearing(t["x"], t["z"]), 1)} for t in self.trees]
        return sorted(rows, key=lambda r: r["distance"])[:3]

    def press(self, key: str) -> None:
        if self.screen == "TITLE":
            if key in ("space", "Return", "click"):
                self.set_screen("WORLD")
        elif key == "Escape":
            self.set_screen("PAUSE" if self.screen == "WORLD" else "WORLD")
        elif self.screen == "WORLD" and key == "e":
            self.chop()

    def say(self, text: str) -> None:
        self.status = text
        self.probe.event("status", self.tick, text=text)

    def chop(self) -> None:
        near = self.nearest_trees()
        if not near or near[0]["distance"] > REACH:
            self.say("Nothing within reach.")
            return
        self.trees = [t for t in self.trees if t["id"] != near[0]["id"]]
        self.wood += 1
        self.say("Chopped a tree: %d wood." % self.wood)
        if self.wood == WOOD_GOAL:
            self.probe.event("objective_completed", self.tick, number=1, id="gather-wood", title="Gather wood",
                             ticksTaken=self.tick)

    def step(self, turn: float, forward: float) -> None:
        """One tick: turn is -1 (left) .. 1 (right), forward 0 .. 1."""
        if self.screen != "WORLD":
            return
        self.tick += 1
        self.yaw = (self.yaw + turn * TURN_DEGREES_PER_SECOND / TICKS_PER_SECOND) % 360.0
        if forward:
            yaw = math.radians(self.yaw)
            self.x += math.sin(yaw) * WALK_SPEED * forward / TICKS_PER_SECOND
            self.z -= math.cos(yaw) * WALK_SPEED * forward / TICKS_PER_SECOND


class XKeyEvent(ctypes.Structure):
    _fields_ = [("type", ctypes.c_int), ("serial", ctypes.c_ulong), ("send_event", ctypes.c_int),
                ("display", ctypes.c_void_p), ("window", ctypes.c_ulong), ("root", ctypes.c_ulong),
                ("subwindow", ctypes.c_ulong), ("time", ctypes.c_ulong), ("x", ctypes.c_int), ("y", ctypes.c_int)]


def run(width: int, height: int, seed: int, out: Optional[str]) -> int:
    x = _xlib()
    dpy = x.XOpenDisplay(None)
    if not dpy:
        print("demo: cannot open the display %r" % os.environ.get("DISPLAY"), file=sys.stderr)
        return 1
    screen = x.XDefaultScreen(dpy)
    win = x.XCreateSimpleWindow(dpy, x.XRootWindow(dpy, screen), 50, 50, width, height, 0, 0, 0x203020)
    x.XStoreName(dpy, win, TITLE)
    x.XSelectInput(dpy, win, KEY_PRESS_MASK | BUTTON_PRESS_MASK | EXPOSURE_MASK | STRUCTURE_NOTIFY_MASK)
    x.XMapWindow(dpy, win)
    gc = x.XCreateGC(dpy, win, 0, None)
    codes = {k: x.XKeysymToKeycode(dpy, x.XStringToKeysym(k.encode())) for k in ("a", "d", "w")}
    keymap = ctypes.create_string_buffer(32)
    event = ctypes.create_string_buffer(256)
    game = Game(seed, Probe(out))
    print("demo %s: %dx%d, seed %d" % (VERSION, width, height, seed), flush=True)

    def down(code: int) -> bool:
        return bool(keymap.raw[code // 8] & (1 << (code % 8)))

    def draw() -> None:
        def rect(color, px, py, w, h):
            x.XSetForeground(dpy, gc, color)
            x.XFillRectangle(dpy, win, gc, int(px), int(py), w, h)

        def text(color, px, py, s):
            x.XSetForeground(dpy, gc, color)
            b = s.encode()
            x.XDrawString(dpy, win, gc, int(px), int(py), b, len(b))

        rect(0x203020, 0, 0, width, height)
        if game.screen == "TITLE":
            text(0xffffff, width // 2 - 60, height // 2, "PLAYTESTER DEMO")
            text(0xc0c0c0, width // 2 - 80, height // 2 + 20, "press Space or click to start")
        else:
            cx, cy = width // 2, height // 2
            for t in game.trees:
                rect(0x30a030, cx + (t["x"] - game.x) * PIXELS_PER_UNIT - 6, cy + (t["z"] - game.z) * PIXELS_PER_UNIT - 6, 12, 12)
            rect(0xffffff, cx - 4, cy - 4, 8, 8)
            yaw = math.radians(game.yaw)
            x.XDrawLine(dpy, win, gc, cx, cy, int(cx + math.sin(yaw) * 20), int(cy - math.cos(yaw) * 20))
            text(0xffffff, 10, 20, "Gather wood: %d/%d" % (game.wood, WOOD_GOAL))
            if game.status:
                text(0xffe080, 10, height - 12, game.status)
            if game.screen == "PAUSE":
                text(0xffffff, cx - 25, cy - 30, "PAUSED")
        x.XFlush(dpy)

    frames, fps_since = 0, time.time()
    next_tick = time.time()
    while True:
        while x.XPending(dpy):
            x.XNextEvent(dpy, event)
            kind = ctypes.cast(event, ctypes.POINTER(ctypes.c_int))[0]
            if kind == KEY_PRESS:
                sym = x.XLookupKeysym(event, 0)
                names = {0x20: "space", 0xff0d: "Return", 0xff1b: "Escape", 0x65: "e"}
                if sym in names:
                    game.press(names[sym])
            elif kind == BUTTON_PRESS:
                game.press("click")
            elif kind == DESTROY_NOTIFY:
                return 0
        x.XQueryKeymap(dpy, keymap)
        now = time.time()
        while next_tick <= now:
            game.step((1 if down(codes["d"]) else 0) - (1 if down(codes["a"]) else 0), 1 if down(codes["w"]) else 0)
            next_tick += 1.0 / TICKS_PER_SECOND
        draw()
        frames += 1
        if now - fps_since >= 1.0:
            game.fps = int(frames / (now - fps_since) + 0.5)
            frames, fps_since = 0, now
        game.probe.state(game)
        time.sleep(max(0.0, min(next_tick - time.time(), 1.0 / TICKS_PER_SECOND)))


def main(argv: List[str]) -> int:
    opts = {"--width": "640", "--height": "360", "--seed": "7", "--playtest-out": None}
    args = list(argv)
    while args:
        key = args.pop(0)
        if key not in opts or not args:
            print("demo: unknown argument %s\n\n%s" % (key, __doc__.strip()), file=sys.stderr)
            return 2
        opts[key] = args.pop(0)
    try:
        seed = int(opts["--seed"])
    except ValueError:
        seed = sum(ord(c) for c in opts["--seed"])
    return run(int(opts["--width"]), int(opts["--height"]), seed, opts["--playtest-out"])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
