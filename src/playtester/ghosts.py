"""Ghost trails: recorded playtest runs drawn as fading paths in a Strata scene.

    pt ghosts RUN_OR_SESSION... [-o ghosts.png] [--gif ghosts.gif] [--mp4 ghosts.mp4]
              [--size 960x540] [--frames 60] [--fps 12] [--stall-secs 20] [--stall-radius R]
              [--title TEXT] [--strata-lib PATH | --strata-release VERSION]

Each argument is a session directory (``$PT_ROOT/s01``, or committed evidence
such as ``docs/playtests/0.1.2/s01``), a run directory holding sessions, or
one ``track.jsonl`` / ``events.jsonl`` file. Every session is one run, drawn
in its own colour over a ground sized to the runs' bounds:

- the path, brighter where it is recent and fading towards where it began;
- a cube where the player died (``player_death`` events);
- a ring where the player stalled: stayed within ``--stall-radius`` world
  units for ``--stall-secs`` or more (on a free clock that includes an
  agent's thinking time, which is when a real player would be standing still
  too);
- a pin (a ball on a post) where the session ended (the run's last position: a quit, a crash
  or the end of the budget).

Positions come from the session's ``track.jsonl``, which the harness writes
from the probe's ``state.json`` (``player.x``, ``player.z``) every time it
reads it, so any game with a probe has one. Events that carry ``x`` and ``z``
(optional in the probe contract) add positions and place their markers
exactly; older sessions without a track fall back to ``trace.jsonl``
(``walkto`` steps). Game seconds come from ticks and the session's
``ticksPerSecond`` where they are known, wall-clock seconds otherwise.

The still image shows each run whole. The GIF and MP4 replay the runs side
by side from their starts: each trail grows, its tail fading out behind the
moving head, and leaves a faint ghost of where it went.

Rendering needs the Strata engine's Python binding (``import strata``, from
Strata's ``bindings/python``) and a libstrata (``STRATA_LIBRARY``,
``--strata-lib`` or ``--strata-release``); it runs headless on any OpenGL 3.3
driver, including Mesa's llvmpipe. The GIF needs ImageMagick or Pillow, the
MP4 ffmpeg. Reading runs (``load_runs``) and laying out the scene
(``build_frame``) are standard-library Python and need none of them.
"""

import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# Run colours, linear RGB (the engine takes linear colour): bright, distinct
# hues that read on a dark ground.
PALETTE = [
    (1.00, 0.42, 0.05),  # orange
    (0.10, 0.55, 1.00),  # blue
    (0.20, 0.85, 0.15),  # green
    (0.95, 0.10, 0.55),  # magenta
    (1.00, 0.85, 0.05),  # yellow
    (0.05, 0.85, 0.80),  # cyan
    (0.60, 0.25, 1.00),  # violet
    (0.90, 0.90, 0.90),  # white
]

SOFTWARE_GL = {"LIBGL_ALWAYS_SOFTWARE": "1", "GALLIUM_DRIVER": "llvmpipe"}  # as harness.session

DEFAULT_STALL_SECS = 20.0
DEFAULT_SIZE = (960, 540)
# Faintest a trail gets: the oldest part of a whole run is still visible.
MIN_ALPHA = 0.18


class GhostsError(RuntimeError):
    """A run could not be read or drawn; the message says why."""


class Sample:
    """One recorded position: seconds since the run began, wall ms, world x and z."""

    __slots__ = ("t", "wall", "tick", "x", "z", "brk")

    def __init__(self, t: float, wall: Optional[int], tick: Optional[int], x: float, z: float, brk: bool = False):
        self.t = t
        self.wall = wall
        self.tick = tick
        self.x = x
        self.z = z
        self.brk = brk  # a new world starts here: no line from the previous sample

    def __repr__(self) -> str:
        return "Sample(t=%.1f, x=%.2f, z=%.2f%s)" % (self.t, self.x, self.z, ", break" if self.brk else "")


class Marker:
    """Something that happened at a place: ``death``, ``stall`` or ``end``."""

    __slots__ = ("kind", "t", "x", "z", "seconds")

    def __init__(self, kind: str, t: float, x: float, z: float, seconds: float = 0.0):
        self.kind = kind
        self.t = t
        self.x = x
        self.z = z
        self.seconds = seconds  # how long, for a stall

    def __repr__(self) -> str:
        return "Marker(%s, t=%.1f, x=%.2f, z=%.2f)" % (self.kind, self.t, self.x, self.z)


class Run:
    """One session's path and markers."""

    def __init__(self, name: str, samples: List[Sample], markers: List[Marker], clock: str, source: str):
        self.name = name
        self.samples = samples
        self.markers = markers
        self.clock = clock  # "game" (ticks) or "wall"
        self.source = source

    @property
    def duration(self) -> float:
        return self.samples[-1].t if self.samples else 0.0

    def __repr__(self) -> str:
        return "Run(%s, %d samples, %d markers, %.0fs %s)" % (
            self.name, len(self.samples), len(self.markers), self.duration, self.clock)


# --------------------------------------------------------------- reading runs

def _read_jsonl(path: str) -> List[Dict[str, Any]]:
    rows = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue  # a line cut short by a crash
                if isinstance(row, dict):
                    rows.append(row)
    except OSError:
        pass
    return rows


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _ticks_per_second(session_dir: str) -> Optional[float]:
    for name, keys in (("session.json", ("ticksPerSecond",)), ("profile.json", ("probe", "ticks_per_second"))):
        try:
            with open(os.path.join(session_dir, name), encoding="utf-8") as f:
                v = json.load(f)  # type: Any
        except (OSError, ValueError):
            continue
        for k in keys:
            v = v.get(k) if isinstance(v, dict) else None
        if _num(v) and v > 0:
            return float(v)
    return None


def _events_path(session_dir: str) -> Optional[str]:
    for rel in (("out", "events.jsonl"), ("events.jsonl",)):
        p = os.path.join(session_dir, *rel)
        if os.path.isfile(p):
            return p
    return None


def is_session(path: str) -> bool:
    """Whether a directory holds one session's records."""
    return os.path.isdir(path) and any(
        os.path.isfile(os.path.join(path, *rel))
        for rel in (("track.jsonl",), ("trace.jsonl",), ("out", "events.jsonl"), ("events.jsonl",)))


def session_dirs(path: str) -> List[str]:
    """The session directories ``path`` names: itself, or the sessions inside it."""
    if is_session(path):
        return [path]
    if not os.path.isdir(path):
        raise GhostsError("not a session, a run directory or a .jsonl file: %s" % path)
    found = sorted(os.path.join(path, d) for d in os.listdir(path) if is_session(os.path.join(path, d)))
    if not found:
        raise GhostsError("no sessions in %s (a session has track.jsonl, trace.jsonl or events.jsonl)" % path)
    return found


def _raw_positions(session_dir: Optional[str], track: Optional[str], events: List[Dict[str, Any]]):
    """(wall ms, tick, x, z) from the track (or the walkto trace) and positioned events."""
    rows = []  # type: List[Tuple[Optional[int], Optional[int], float, float]]
    source = []
    if track is None and session_dir is not None:
        p = os.path.join(session_dir, "track.jsonl")
        track = p if os.path.isfile(p) else None
    if track is not None:
        for r in _read_jsonl(track):
            if _num(r.get("x")) and _num(r.get("z")):
                rows.append((r.get("t") if _num(r.get("t")) else None, r.get("tick") if _num(r.get("tick")) else None,
                             float(r["x"]), float(r["z"])))
        source.append("track.jsonl")
    elif session_dir is not None:
        for r in _read_jsonl(os.path.join(session_dir, "trace.jsonl")):
            if _num(r.get("x")) and _num(r.get("z")):
                rows.append((r.get("t") if _num(r.get("t")) else None, None, float(r["x"]), float(r["z"])))
        if rows:
            source.append("trace.jsonl")
    n = len(rows)
    for e in events:
        if _num(e.get("x")) and _num(e.get("z")):
            rows.append((e.get("wallTimeMs") if _num(e.get("wallTimeMs")) else None,
                         e.get("tick") if _num(e.get("tick")) else None, float(e["x"]), float(e["z"])))
    if len(rows) > n:
        source.append("events.jsonl")
    return rows, "+".join(source) or "nothing"


def load_run(path: str, stall_secs: float = DEFAULT_STALL_SECS, stall_radius: Optional[float] = None,
             name: Optional[str] = None) -> Run:
    """Reads one session directory, or one ``track.jsonl`` or ``events.jsonl`` file."""
    session_dir = None  # type: Optional[str]
    track = None  # type: Optional[str]
    events_file = None  # type: Optional[str]
    if os.path.isfile(path):
        base = os.path.basename(path)
        parent = os.path.dirname(os.path.abspath(path))
        if base.startswith("events"):
            events_file = path
            if os.path.basename(parent) == "out":
                parent = os.path.dirname(parent)
        else:
            track = path
        session_dir = parent if os.path.isfile(os.path.join(parent, "session.json")) else None
        label = name or os.path.basename(parent)
    elif is_session(path):
        session_dir = path
        events_file = _events_path(path)
        label = name or os.path.basename(os.path.abspath(path))
    else:
        raise GhostsError("not a session directory or a .jsonl file: %s" % path)
    events = _read_jsonl(events_file) if events_file else []
    rows, source = _raw_positions(session_dir, track, events)
    tps = _ticks_per_second(session_dir) if session_dir else None
    samples, clock = _timeline(rows, tps)
    if not samples:
        raise GhostsError("%s records no positions (a probe game's sessions keep them in track.jsonl; "
                          "see docs/PROBE_CONTRACT.md)" % path)
    markers = _death_markers(events, samples, tps)
    markers.extend(find_stalls(samples, stall_secs, stall_radius))
    last = samples[-1]
    markers.append(Marker("end", last.t, last.x, last.z))
    markers.sort(key=lambda m: m.t)
    return Run(label, samples, markers, clock, source)


def _timeline(rows, tps: Optional[float]) -> Tuple[List[Sample], str]:
    """Orders positions and gives each seconds since the run began.

    Game seconds (tick / ticks a second) when every position has a tick and the
    rate is known; wall seconds otherwise. A tick going backwards is a new
    world (a restart, a load): the line breaks there and the clock carries on.
    """
    rows = sorted(rows, key=lambda r: (r[0] is None, r[0] or 0, r[1] or 0))
    if not rows:
        return [], "wall"
    game = tps is not None and all(r[1] is not None for r in rows)
    if not game and any(r[0] is None for r in rows):
        rows = [r for r in rows if r[0] is not None]
        if not rows:
            return [], "wall"
    samples = []  # type: List[Sample]
    offset = 0.0
    prev = None
    for wall, tick, x, z in rows:
        brk = False
        if game:
            t = tick / tps + offset
            if prev is not None and tick < prev.tick:
                brk = True
                offset = prev.t
                t = offset  # the new world's clock picks up where the old one stopped
                offset -= tick / tps
            elif prev is not None and t < prev.t:
                t = prev.t
        else:
            t = (wall - rows[0][0]) / 1000.0
            if prev is not None and tick is not None and prev.tick is not None and tick < prev.tick:
                brk = True
        s = Sample(t, wall, tick, x, z, brk)
        if prev is not None and not brk and (s.t, s.x, s.z) == (prev.t, prev.x, prev.z):
            continue  # the same state read twice
        samples.append(s)
        prev = s
    t0 = samples[0].t
    for s in samples:
        s.t -= t0
    return samples, "game" if game else "wall"


def _nearest(samples: List[Sample], wall: Optional[int], tick: Optional[int]) -> Sample:
    if tick is not None and samples[0].tick is not None:
        return min(samples, key=lambda s: abs((s.tick if s.tick is not None else 0) - tick))
    if wall is not None:
        return min(samples, key=lambda s: abs((s.wall or 0) - wall))
    return samples[-1]


def _death_markers(events: List[Dict[str, Any]], samples: List[Sample], tps: Optional[float]) -> List[Marker]:
    out = []
    for e in events:
        if e.get("type") != "player_death":
            continue
        wall = e.get("wallTimeMs") if _num(e.get("wallTimeMs")) else None
        tick = e.get("tick") if _num(e.get("tick")) else None
        near = _nearest(samples, wall, tick)
        x, z = (float(e["x"]), float(e["z"])) if _num(e.get("x")) and _num(e.get("z")) else (near.x, near.z)
        out.append(Marker("death", near.t, x, z))
    return out


def run_extent(samples: Sequence[Sample]) -> float:
    xs = [s.x for s in samples]
    zs = [s.z for s in samples]
    return max(max(xs) - min(xs), max(zs) - min(zs)) if samples else 0.0


def find_stalls(samples: List[Sample], stall_secs: float = DEFAULT_STALL_SECS,
                radius: Optional[float] = None) -> List[Marker]:
    """Places where the player stayed within ``radius`` for ``stall_secs`` or more.

    ``radius`` defaults to 3% of the run's extent (at least 0.5 units). Each
    stall is marked at the middle of the positions in it, with its length.
    """
    if radius is None:
        radius = max(0.5, 0.03 * run_extent(samples))
    out = []
    i = 0
    n = len(samples)
    while i < n:
        a = samples[i]
        j = i
        while j + 1 < n and not samples[j + 1].brk and math.hypot(samples[j + 1].x - a.x, samples[j + 1].z - a.z) <= radius:
            j += 1
        seconds = samples[j].t - a.t
        if seconds >= stall_secs:
            pts = samples[i:j + 1]
            out.append(Marker("stall", a.t, sum(p.x for p in pts) / len(pts), sum(p.z for p in pts) / len(pts),
                              seconds))
            i = j + 1
        else:
            i += 1
    return out


def load_runs(paths: Iterable[str], stall_secs: float = DEFAULT_STALL_SECS,
              stall_radius: Optional[float] = None) -> List[Run]:
    """Every run the paths name, in order; sessions named alike get their parent's name too."""
    found = []  # type: List[str]
    runs = []  # type: List[Run]
    for p in paths:
        if os.path.isfile(p) or is_session(p):
            runs.append(load_run(p, stall_secs, stall_radius))
            found.append(p)
            continue
        for d in session_dirs(p):  # a run directory: skip sessions with nothing to draw
            try:
                runs.append(load_run(d, stall_secs, stall_radius))
                found.append(d)
            except GhostsError as e:
                print("pt ghosts: skipped: %s" % e, file=sys.stderr)
    if not runs:
        raise GhostsError("none of the sessions records positions (track.jsonl is written by pt from 0.2.0 "
                          "on, for games with a probe)")
    names = [r.name for r in runs]
    for r, p in zip(runs, found):
        if names.count(r.name) > 1:
            parent = os.path.basename(os.path.dirname(os.path.abspath(p if os.path.isdir(p) else os.path.dirname(p))))
            r.name = "%s/%s" % (parent, r.name)
    return runs


# ------------------------------------------------------------ laying out the scene

class Bounds:
    """The ground: the runs' extent on x and z, padded, at least ``minimum`` across."""

    def __init__(self, runs: Sequence[Run], pad: float = 0.12, minimum: float = 4.0):
        xs = [s.x for r in runs for s in r.samples]
        zs = [s.z for r in runs for s in r.samples]
        if not xs:
            raise GhostsError("no positions to draw")
        self.cx = (min(xs) + max(xs)) / 2.0
        self.cz = (min(zs) + max(zs)) / 2.0
        w = max(max(xs) - min(xs), minimum)
        d = max(max(zs) - min(zs), minimum)
        self.width = w * (1 + 2 * pad)
        self.depth = d * (1 + 2 * pad)

    @property
    def extent(self) -> float:
        return max(self.width, self.depth)

    def __repr__(self) -> str:
        return "Bounds(centre=(%.2f, %.2f), %.2f x %.2f)" % (self.cx, self.cz, self.width, self.depth)


def nice_step(span: float, lines: int = 10) -> float:
    """A 1, 2 or 5 times a power of ten that cuts ``span`` into about ``lines`` cells."""
    raw = span / max(1, lines)
    p = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1.0
    for m in (1, 2, 5, 10):
        if raw <= m * p:
            return m * p
    return 10 * p


def colour(i: int) -> Tuple[float, float, float]:
    return PALETTE[i % len(PALETTE)]


def fade(age: float, window: float) -> float:
    """Alpha for a point ``age`` seconds old when trails fade over ``window`` seconds."""
    if window <= 0:
        return 1.0
    return max(MIN_ALPHA, 1.0 - (1.0 - MIN_ALPHA) * min(1.0, max(0.0, age / window)))


def _interp(a: Sample, b: Sample, t: float) -> Tuple[float, float]:
    if b.t <= a.t:
        return b.x, b.z
    k = (t - a.t) / (b.t - a.t)
    return a.x + (b.x - a.x) * k, a.z + (b.z - a.z) * k


class Frame:
    """Everything one image draws, as plain tuples (the renderer turns them into Strata structs).

    primitives: (kind, position, scale, rgba) with kind one of cube, cylinder, capsule, sphere
    lines: ((x, y, z), rgba, (x, y, z), rgba) segments
    points: (position, size_pixels, world_diameter, rgba, soft)
    texts: (x, y, pixel_size, rgba, text) in pixels from the top left
    rects: (x, y, width, height, rgba)
    """

    def __init__(self):
        self.primitives = []  # type: List[Tuple[str, Tuple[float, float, float], Tuple[float, float, float], Tuple[float, ...]]]
        self.lines = []  # type: List[Tuple[Tuple[float, float, float], Tuple[float, ...], Tuple[float, float, float], Tuple[float, ...]]]
        self.points = []  # type: List[Tuple[Tuple[float, float, float], float, float, Tuple[float, ...], bool]]
        self.texts = []  # type: List[Tuple[float, float, float, Tuple[float, ...], str]]
        self.rects = []  # type: List[Tuple[float, float, float, float, Tuple[float, ...]]]


TRAIL_Y = 0.02


def ground(frame: Frame, bounds: Bounds) -> None:
    """A flat slab under the runs, with a grid every ``nice_step`` units."""
    frame.primitives.append(("cube", (bounds.cx, -0.05, bounds.cz), (bounds.width, 0.1, bounds.depth),
                             (0.13, 0.15, 0.14, 1.0)))
    step = nice_step(bounds.extent)
    x0, x1 = bounds.cx - bounds.width / 2, bounds.cx + bounds.width / 2
    z0, z1 = bounds.cz - bounds.depth / 2, bounds.cz + bounds.depth / 2
    grid = (0.30, 0.34, 0.32, 0.55)
    x = math.ceil(x0 / step) * step
    while x <= x1:
        frame.lines.append(((x, 0.005, z0), grid, (x, 0.005, z1), grid))
        x += step
    z = math.ceil(z0 / step) * step
    while z <= z1:
        frame.lines.append(((x0, 0.005, z), grid, (x1, 0.005, z), grid))
        z += step


def _trail(frame: Frame, run: Run, rgb, now: float, window: float, bounds: Bounds) -> Optional[Tuple[float, float]]:
    """The run's path up to ``now``; returns where its head is (None before it starts)."""
    samples = run.samples
    if not samples or now < samples[0].t:
        return None
    width = bounds.extent / 80.0  # a ribbon of soft points, so a trail is wider than a 1-pixel line
    spacing = width * 0.45
    offset = bounds.extent / 900.0  # about a pixel at the default size
    head = (samples[0].x, samples[0].z)
    for a, b in zip(samples, samples[1:]):
        if a.t > now:
            break
        end_t = min(b.t, now)
        bx, bz = _interp(a, b, end_t)
        head = (bx, bz)
        if b.brk:
            head = (a.x, a.z)
            continue
        aa = fade(now - a.t, window)
        ab = fade(now - end_t, window)
        length = math.hypot(bx - a.x, bz - a.z)
        # Strata's lines are one pixel wide: three side by side make a trail that reads.
        nx, nz = ((a.z - bz) / length * offset, (bx - a.x) / length * offset) if length > 0 else (0.0, 0.0)
        for side in (0.0, -1.0, 1.0):
            frame.lines.append(((a.x + nx * side, TRAIL_Y, a.z + nz * side), rgb + (aa,),
                                (bx + nx * side, TRAIL_Y, bz + nz * side), rgb + (ab,)))
        steps = max(1, int(length / spacing))
        for k in range(steps):
            f = k / float(steps)
            alpha = aa + (ab - aa) * f
            frame.points.append(((a.x + (bx - a.x) * f, TRAIL_Y, a.z + (bz - a.z) * f), 2.0, width,
                                 rgb + (alpha * 0.9,), True))
    if now >= samples[-1].t:
        head = (samples[-1].x, samples[-1].z)
    return head


def _ring(frame: Frame, x: float, z: float, r: float, rgba, segments: int = 28) -> None:
    for k in range(segments):
        a0 = 2 * math.pi * k / segments
        a1 = 2 * math.pi * (k + 1) / segments
        frame.lines.append(((x + r * math.cos(a0), TRAIL_Y, z + r * math.sin(a0)), rgba,
                            (x + r * math.cos(a1), TRAIL_Y, z + r * math.sin(a1)), rgba))


def _markers(frame: Frame, run: Run, rgb, now: float, bounds: Bounds) -> None:
    u = bounds.extent / 36.0  # marker size
    dark = tuple(c * 0.55 for c in rgb)
    for m in run.markers:
        if m.t > now:
            continue
        if m.kind == "death":
            frame.primitives.append(("cube", (m.x, u * 0.6, m.z), (u * 1.2, u * 1.2, u * 1.2), (0.85, 0.05, 0.05, 1.0)))
            frame.primitives.append(("cube", (m.x, u * 0.6, m.z), (u * 1.5, u * 0.3, u * 0.3), dark + (1.0,)))
        elif m.kind == "stall":
            # The ring grows with the stall: a minute is about twice the size of a short one.
            r = u * (1.2 + min(2.5, m.seconds / 60.0))
            _ring(frame, m.x, m.z, r, rgb + (0.95,))
            _ring(frame, m.x, m.z, r * 0.92, rgb + (0.6,))
            frame.primitives.append(("cylinder", (m.x, u * 0.08, m.z), (u * 0.7, u * 0.16, u * 0.7), dark + (1.0,)))
        elif m.kind == "end" and now >= run.duration:
            frame.primitives.append(("cylinder", (m.x, u * 0.6, m.z), (u * 0.25, u * 1.2, u * 0.25), dark + (1.0,)))
            frame.primitives.append(("sphere", (m.x, u * 1.4, m.z), (u * 0.9, u * 0.9, u * 0.9), rgb + (1.0,)))


def build_frame(runs: Sequence[Run], bounds: Bounds, now: Optional[float] = None, window: Optional[float] = None,
                size: Tuple[int, int] = DEFAULT_SIZE, title: str = "", credit: str = "rendered with Strata") -> Frame:
    """One image: the ground, every run's trail up to ``now`` seconds after its start, markers and a legend.

    ``now`` None draws every run whole. Trails fade over ``window`` seconds
    (default: the longest run, so a whole run fades from start to end).
    """
    longest = max((r.duration for r in runs), default=0.0)
    if now is None:
        now = longest
    if window is None:
        window = longest
    frame = Frame()
    ground(frame, bounds)
    for i, run in enumerate(runs):
        rgb = colour(i)
        head = _trail(frame, run, rgb, now, window, bounds)
        _markers(frame, run, rgb, now, bounds)
        if head is not None and now < run.duration:
            frame.points.append(((head[0], TRAIL_Y, head[1]), 9.0, bounds.extent / 45.0, rgb + (1.0,), False))
        elif run.samples and now >= run.samples[0].t:
            frame.points.append(((run.samples[0].x, TRAIL_Y, run.samples[0].z), 5.0, 0.0, (1.0, 1.0, 1.0, 0.8), False))
    _legend(frame, runs, now, size, title, credit)
    return frame


def _clock(seconds: float) -> str:
    m, s = divmod(int(round(seconds)), 60)
    return "%d:%02d" % (m, s)


def _legend(frame: Frame, runs: Sequence[Run], now: float, size: Tuple[int, int], title: str, credit: str) -> None:
    w, h = size
    px = 16.0 if h >= 480 else 8.0
    pad = px * 0.75
    lines = []  # type: List[Tuple[str, Tuple[float, ...]]]
    if title:
        lines.append((title, (1.0, 1.0, 1.0, 1.0)))
    for i, run in enumerate(runs):
        kinds = [m.kind for m in run.markers if m.t <= now]
        bits = ["%s %s" % (_clock(min(now, run.duration)), "game" if run.clock == "game" else "wall")]
        if kinds.count("death"):
            bits.append("%d death%s" % (kinds.count("death"), "" if kinds.count("death") == 1 else "s"))
        if kinds.count("stall"):
            bits.append("%d stall%s" % (kinds.count("stall"), "" if kinds.count("stall") == 1 else "s"))
        lines.append(("%s  %s" % (run.name, ", ".join(bits)), colour(i) + (1.0,)))
    width = max(len(t) for t, _ in lines) * px + 2 * pad
    frame.rects.append((pad, pad, width, len(lines) * px * 1.4 + pad, (0.0, 0.0, 0.0, 0.55)))
    for k, (text, rgba) in enumerate(lines):
        frame.texts.append((pad * 2, pad * 1.5 + k * px * 1.4, px, rgba, text))
    key = "cube: death  ring: stall  pin: end"
    small = max(8.0, px / 2) if h < 720 else 16.0
    frame.texts.append((pad, h - pad - small * 2.6, small, (0.85, 0.85, 0.85, 1.0), key))
    if credit:
        frame.texts.append((w - pad - len(credit) * small, h - pad - small * 1.2, small, (0.85, 0.85, 0.85, 1.0), credit))


def camera_pose(bounds: Bounds, aspect: float, fov_y: float = 40.0, pitch: float = 58.0):
    """(eye, target, far): looking down from the south at ``pitch`` degrees, framing the ground."""
    half = max(bounds.depth / 2.0, bounds.width / 2.0 / aspect) * 1.12
    dist = half / math.tan(math.radians(fov_y) / 2.0) + bounds.depth * 0.15
    p = math.radians(pitch)
    eye = (bounds.cx, dist * math.sin(p), bounds.cz + dist * math.cos(p))
    target = (bounds.cx, 0.0, bounds.cz + bounds.depth * 0.04)
    return eye, target, dist * 3.0 + bounds.extent


# -------------------------------------------------------------------- rendering

def load_strata(lib_path: Optional[str] = None, release: Optional[str] = None):
    """(strata module, Library): the binding and a libstrata, or GhostsError saying how to get them."""
    try:
        import strata  # type: ignore
    except ImportError:
        raise GhostsError(
            "pt ghosts renders with the Strata engine and needs its Python binding: "
            "pip install 'git+https://github.com/Preponderous-Software/strata#subdirectory=bindings/python' "
            "(or put a Strata checkout's bindings/python on PYTHONPATH)")
    try:
        if release:
            return strata, strata.load_release(release)
        return strata, strata.load(lib_path)
    except Exception as e:  # StrataLoadError, StrataAbiError, OSError
        raise GhostsError("could not load libstrata (%s). Point STRATA_LIBRARY or --strata-lib at a built "
                          "libstrata.so, or pass --strata-release VERSION" % e)


_KINDS = {"cube": 0, "capsule": 1, "cylinder": 2, "sphere": 3}


class Renderer:
    """A headless Strata engine that draws Frames to PNG files."""

    def __init__(self, strata_mod, lib, size: Tuple[int, int] = DEFAULT_SIZE):
        self.s = strata_mod
        self.lib = lib
        self.size = size
        # Mesa's software rasteriser, as the harness gives its games: the same
        # image on every machine, and no GPU driver needed (set
        # LIBGL_ALWAYS_SOFTWARE=0 to use one). Mesa reads it when the engine starts.
        for k, v in SOFTWARE_GL.items():
            os.environ.setdefault(k, v)
        self.engine = strata_mod.Engine(lib, size[0], size[1])
        self.lines_on_top = lib.has("strata_submit_lines_ex")
        self.on_top = self.lines_on_top  # STRATA_POINT_ON_TOP arrived with lines_ex in ABI 1.11

    def close(self) -> None:
        self.engine.close()

    def __enter__(self) -> "Renderer":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def setup(self, bounds: Bounds) -> None:
        s, w, h = self.s, self.size[0], self.size[1]
        eye, target, far = camera_pose(bounds, w / float(h))
        self.engine.set_camera(self.lib.look_at(eye, target, fov_y_degrees=40.0, aspect=w / float(h),
                                                near_plane=max(0.05, bounds.extent / 500.0), far_plane=far))
        lighting = self.lib.lighting_defaults(s.LIGHTING_SUN)
        lighting.time_of_day = 0.36
        lighting.fog = 0
        lighting.cascade_count = 0  # nothing tall enough to shadow anything
        self.engine.set_lighting(lighting)

    def draw(self, frame: Frame, png: str) -> None:
        s = self.s
        e = self.engine
        e.begin_frame(clear_color=(0.035, 0.04, 0.05, 1.0))
        if frame.primitives:
            e.submit_primitives([s.RenderItem(_KINDS[k], p, sc, c) for k, p, sc, c in frame.primitives])
        grid = [ln for ln in frame.lines if ln[0][1] < TRAIL_Y]
        trails = [ln for ln in frame.lines if ln[0][1] >= TRAIL_Y]
        if grid:
            e.submit_lines([v for a, ca, b, cb in grid for v in (s.LineVertex(a, ca), s.LineVertex(b, cb))])
        if trails:
            verts = [v for a, ca, b, cb in trails for v in (s.LineVertex(a, ca), s.LineVertex(b, cb))]
            if self.lines_on_top:
                e.submit_lines(verts, s.LINES_ON_TOP)
            else:
                e.submit_lines(verts)
        if frame.points:
            top = s.POINT_ON_TOP if self.on_top else 0
            e.submit_points([s.Point(p, px, wd, c, (s.POINT_SOFT if soft else 0) | top)
                             for p, px, wd, c, soft in frame.points])
        if frame.rects and self.lib.has("strata_submit_rects"):
            e.submit_rects([s.Rect(x, y, w, h, c) for x, y, w, h, c in frame.rects])
        if frame.texts:
            e.submit_text([s.Text(x, y, px, s.TEXT_SHADOW, c, t.encode("ascii", "replace"))
                           for x, y, px, c, t in frame.texts])
        e.end_frame()
        e.save_screenshot_png(png)


def render(runs: Sequence[Run], png: Optional[str] = None, gif: Optional[str] = None, mp4: Optional[str] = None,
           size: Tuple[int, int] = DEFAULT_SIZE, frames: int = 60, fps: int = 12, title: str = "",
           lib_path: Optional[str] = None, release: Optional[str] = None) -> Dict[str, Any]:
    """Draws the runs to a still PNG and/or an animated GIF or MP4; returns what was written."""
    if not runs:
        raise GhostsError("no runs to draw")
    if not (png or gif or mp4):
        raise GhostsError("nothing to write: give -o/--png, --gif or --mp4")
    strata_mod, lib = load_strata(lib_path, release)
    bounds = Bounds(runs)
    credit = "rendered with Strata %s" % lib.version
    written = {"runs": [repr(r) for r in runs], "strata": lib.version}  # type: Dict[str, Any]
    with Renderer(strata_mod, lib, size) as r:
        r.setup(bounds)
        if png:
            r.draw(build_frame(runs, bounds, size=size, title=title, credit=credit), png)
            written["png"] = png
        if gif or mp4:
            longest = max(run.duration for run in runs)
            window = max(longest * 0.25, 1.0)
            tmp = tempfile.mkdtemp(prefix="pt-ghosts-")
            try:
                paths = []
                n = max(2, frames)
                for k in range(n):
                    now = longest * k / float(n - 1)
                    p = os.path.join(tmp, "frame%04d.png" % k)
                    r.draw(build_frame(runs, bounds, now=now, window=window, size=size, title=title, credit=credit), p)
                    paths.append(p)
                hold = os.path.join(tmp, "frame%04d.png" % n)  # linger on the last frame
                r.draw(build_frame(runs, bounds, size=size, title=title, credit=credit), hold)
                paths.extend([hold] * max(1, fps))
                if gif:
                    _write_gif(paths, gif, fps)
                    written["gif"] = gif
                if mp4:
                    _write_mp4(tmp, paths, mp4, fps)
                    written["mp4"] = mp4
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
    return written


def _write_gif(paths: List[str], gif: str, fps: int) -> None:
    try:
        from PIL import Image  # type: ignore
    except ImportError:
        Image = None
    if Image is not None:
        imgs = [Image.open(p).convert("RGB") for p in paths]
        pal = [im.quantize(colors=128, method=Image.MEDIANCUT, dither=Image.NONE) for im in imgs]
        pal[0].save(gif, save_all=True, append_images=pal[1:], duration=int(1000 / fps), loop=0, optimize=True)
        return
    convert = shutil.which("convert") or shutil.which("magick")
    if not convert:
        raise GhostsError("writing a GIF needs Pillow or ImageMagick (convert)")
    subprocess.run([convert, "-delay", str(max(1, int(100 / fps))), "-loop", "0"] + paths
                   + ["-layers", "Optimize", gif], check=True)


def _write_mp4(tmp: str, paths: List[str], mp4: str, fps: int) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise GhostsError("writing an MP4 needs ffmpeg")
    listing = os.path.join(tmp, "frames.txt")
    with open(listing, "w") as f:
        for p in paths:
            f.write("file '%s'\nduration %f\n" % (p, 1.0 / fps))
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", listing,
                    "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-pix_fmt", "yuv420p", "-r", str(fps), mp4], check=True)


# -------------------------------------------------------------------------- CLI

USAGE = __doc__.strip().split("\n\n")[0].strip()


def parse_args(argv: List[str]) -> Dict[str, Any]:
    opts = {"paths": [], "png": None, "gif": None, "mp4": None, "size": DEFAULT_SIZE, "frames": 60, "fps": 12,
            "stall_secs": DEFAULT_STALL_SECS, "stall_radius": None, "title": "", "lib": None,
            "release": None, "dry_run": False}  # type: Dict[str, Any]
    rest = list(argv)
    valued = {"-o": "png", "--png": "png", "--gif": "gif", "--mp4": "mp4", "--size": "size", "--frames": "frames",
              "--fps": "fps", "--stall-secs": "stall_secs", "--stall-radius": "stall_radius", "--title": "title",
              "--strata-lib": "lib", "--strata-release": "release"}
    while rest:
        a = rest.pop(0)
        if a in valued:
            if not rest:
                raise GhostsError("%s needs a value" % a)
            v = rest.pop(0)
            key = valued[a]
            if key == "size":
                try:
                    w, h = (int(n) for n in v.lower().split("x"))
                except ValueError:
                    raise GhostsError("--size is WIDTHxHEIGHT, such as 960x540")
                if w < 64 or h < 64:
                    raise GhostsError("--size must be at least 64x64")
                opts["size"] = (w, h)
            elif key in ("frames", "fps"):
                opts[key] = int(v)
                if opts[key] < 1:
                    raise GhostsError("%s must be at least 1" % a)
            elif key in ("stall_secs", "stall_radius"):
                opts[key] = float(v)
            else:
                opts[key] = v
        elif a == "--dry-run":
            opts["dry_run"] = True
        elif a.startswith("-") and a != "-":
            raise GhostsError("unknown option %s (pt ghosts --help)" % a)
        else:
            opts["paths"].append(a)
    if not opts["paths"]:
        raise GhostsError("which runs? " + USAGE.splitlines()[0].strip())
    if not (opts["png"] or opts["gif"] or opts["mp4"]) and not opts["dry_run"]:
        opts["png"] = "ghosts.png"
    return opts


def main(argv: List[str]) -> int:
    """``pt ghosts``. --dry-run prints the runs it read without rendering."""
    if argv and argv[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return 0
    try:
        opts = parse_args(argv)
        runs = load_runs(opts["paths"], opts["stall_secs"], opts["stall_radius"])
        if opts["dry_run"]:
            for r in runs:
                print(json.dumps({"run": r.name, "source": r.source, "clock": r.clock, "samples": len(r.samples),
                                  "seconds": round(r.duration, 1),
                                  "markers": [{"kind": m.kind, "t": round(m.t, 1), "x": round(m.x, 2),
                                               "z": round(m.z, 2), **({"seconds": round(m.seconds, 1)}
                                                                      if m.kind == "stall" else {})}
                                              for m in r.markers]}))
            return 0
        written = render(runs, opts["png"], opts["gif"], opts["mp4"], opts["size"], opts["frames"], opts["fps"],
                         opts["title"], opts["lib"], opts["release"])
        print(json.dumps(written))
        return 0
    except GhostsError as e:
        print("pt ghosts: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
