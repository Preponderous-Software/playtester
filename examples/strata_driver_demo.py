"""Record a stepped Strata-driver session twice and show that the frames repeat.

    python examples/strata_driver_demo.py --profile kindling-strata --game-dir ~/kindling \\
        --out docs/playtests/0.2.0/strata-driver/kindling [--seed 1881] [--step 0.0333] [--every 3] \\
        [--runs 2] [-- game args...]

For each run, a session is started with ``--clock stepped`` and a short
scripted play (the game's entry in SCRIPTS) is driven through the same
harness an agent uses. Every ``--every`` frames a screenshot is taken through
the drive channel, so a run is a sequence of frames at fixed game times.

Then, in ``--out``:

- ``frames.json``: every frame's SHA-256 in every run, and whether the runs agree
- ``<name>.gif``: run 1 as an animation (real time: one frame per --every steps)
- ``<name>-sheet.jpg``: a contact sheet of run 1, labelled with frame numbers
- ``<name>-runs.png``: the last frame of run 1, of run 2, and their difference
  (black where the pixels are equal), side by side

The GIF and images need ImageMagick (``convert``, ``montage``, ``compare``).
Nothing here is needed by playtester itself; it makes the pictures for the
documentation and PRs.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Dict, List

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))

from playtester.harness import cli, inputs  # noqa: E402
from playtester.harness import profile as profiles  # noqa: E402
from playtester.harness.session import Session  # noqa: E402

# Scripted play per profile: (action, ...) in game seconds. "hold" holds a
# combo, "look" spreads a relative mouse motion over a time, "drag" holds a
# mouse button while moving, "wait" lets time pass, "key" taps.
SCRIPTS = {
    "kindling-strata": [
        ("key", "F1"),                   # hide the help
        ("wait", 0.5),
        ("hold", "w", 1.6),              # through the door
        ("look", 0, 160, 0.6),           # down at the floor
        ("look", 0, -160, 0.6),
        ("hold", "Right", 1.2),          # turn to the hearth side
        ("hold", "w", 0.8),
        ("hold", "Left", 2.0),
        ("wait", 0.5),
    ],
    "atman-strata": [
        ("key", "F1"),
        ("wait", 0.5),
        ("hold", "w", 1.5),
        ("look", 480, 0, 1.2),
        ("hold", "w", 1.2),
        ("look", -240, 60, 0.8),
        ("hold", "Shift_L+w", 1.0),
        ("wait", 0.5),
    ],
    "orrery-strata": [
        ("wait", 0.5),
        ("key", "period"),
        ("key", "period"),
        ("key", "period"),
        ("wait", 1.5),
        ("drag", 220, 40, 1.5),
        ("key", "Prior"),
        ("wait", 1.0),
        ("drag", -160, -30, 1.0),
        ("wait", 0.5),
    ],
    "steading-strata": [
        ("wait", 1.0),
        ("key", "equal"),
        ("key", "equal"),
        ("wait", 2.0),
        ("key", "Tab"),
        ("hold", "w", 1.0),
        ("hold", "Down", 0.5),
        ("wait", 1.0),
    ],
}


class Recorder:
    def __init__(self, session: Session, inp: "inputs.StrataInput", every: int):
        self.session = session
        self.inp = inp
        self.every = every
        self.frame = 0
        self.shots = []  # type: List[str]
        self.pending = 0  # frames stepped since the last shot

    def shot(self) -> None:
        path = self.session.path("shots", "frame-%05d.png" % self.frame)
        self.inp.screenshot(path)
        self.shots.append(path)

    def advance(self, frames: int, during=None) -> None:
        """Steps ``frames``, taking a shot every ``every`` frames; ``during(i, n)`` runs before each chunk."""
        done = 0
        while done < frames:
            n = min(self.every - self.pending, frames - done)
            if during:
                during(done, n, frames)
            self.inp.step(n)
            done += n
            self.frame += n
            self.pending += n
            if self.pending == self.every:
                self.pending = 0
                self.shot()

    def run(self, script: List[Any]) -> None:
        self.shot()
        for action in script:
            kind = action[0]
            if kind == "wait":
                self.advance(self.inp.frames(action[1]))
            elif kind == "key":
                keys = self.inp._keys_down(action[1])
                self.advance(self.inp.frames(0.12))
                self.inp._keys_up(keys)
                self.advance(1)
            elif kind == "hold":
                keys = self.inp._keys_down(action[1])
                self.advance(self.inp.frames(action[2]))
                self.inp._keys_up(keys)
                self.advance(1)
            elif kind in ("look", "drag"):
                if kind == "look":
                    dx, dy, seconds = action[1], action[2], action[3]
                else:
                    dx, dy, seconds = action[1], action[2], action[3]
                    w, h = self.size
                    cx, cy = w // 2, h // 2
                    self.inp.event("mouse_motion", x=cx, y=cy)
                    self.inp.event("mouse_button_down", button=1, x=cx, y=cy)
                total = self.inp.frames(seconds)
                sent = [0, 0]

                def move(done, n, frames_total, dx=dx, dy=dy, sent=sent, drag=kind == "drag"):
                    tx = dx * (done + n) // frames_total
                    ty = dy * (done + n) // frames_total
                    ex, ey = tx - sent[0], ty - sent[1]
                    sent[0], sent[1] = tx, ty
                    if drag:
                        w, h = self.size
                        self.inp.event("mouse_motion", x=w // 2 + tx, y=h // 2 + ty, dx=ex, dy=ey)
                    else:
                        self.inp.event("mouse_motion", dx=ex, dy=ey)
                self.advance(total, during=move)
                if kind == "drag":
                    w, h = self.size
                    self.inp.event("mouse_button_up", button=1, x=w // 2 + dx, y=h // 2 + dy)
                    self.advance(1)
            else:
                raise ValueError("unknown action %r" % (kind,))
        if self.pending:
            self.advance(self.every - self.pending)

    size = (640, 360)


def record(profile_name: str, game_dir: str, root: str, name: str, seed: str, step: float, every: int,
           extra: List[str]) -> List[str]:
    session = Session(name, root)
    os.makedirs(session.dir, exist_ok=True)
    profile = profiles.load(profile_name)
    try:
        info = session.start(profile, game_dir, seed, extra, clock="stepped", step=step)
        inp = session.input()
        rec = Recorder(session, inp, every)
        w, h = (int(v) for v in info["size"].split("x"))
        rec.size = (w, h)
        rec.run(SCRIPTS[profile["name"]])
        return rec.shots
    finally:
        session.stop()


def sha(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


FONTS = ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")


def font_args() -> List[str]:
    for path in FONTS:
        if os.path.isfile(path):
            return ["-font", path]
    return []


def magick(*args: str) -> None:
    r = subprocess.run(list(args), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, universal_newlines=True)
    if r.returncode != 0:
        raise RuntimeError("%s failed: %s" % (args[0], r.stderr.strip()))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--profile", required=True)
    ap.add_argument("--game-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", help="file name prefix (default: the profile name without -strata)")
    ap.add_argument("--seed", default=None)
    ap.add_argument("--step", type=float, default=1.0 / 30.0)
    ap.add_argument("--every", type=int, default=3, help="frames between screenshots")
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--gif-width", type=int, default=400)
    ap.add_argument("extra", nargs="*", help="game arguments (after --)")
    args = ap.parse_args(argv)
    name = args.name or args.profile.replace("-strata", "")
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    root = tempfile.mkdtemp(prefix="pt-demo-")
    runs = []
    for r in range(1, args.runs + 1):
        print("run %d: %s" % (r, args.profile), flush=True)
        runs.append(record(args.profile, os.path.abspath(os.path.expanduser(args.game_dir)), root, "run%d" % r,
                           args.seed, args.step, args.every, args.extra))
    frames = []
    for i, path in enumerate(runs[0]):
        hashes = [sha(run[i]) if i < len(run) else None for run in runs]
        frames.append({"frame": int(os.path.basename(path)[6:11]), "sha256": hashes,
                       "identical": len(set(hashes)) == 1})
    identical = sum(1 for f in frames if f["identical"])
    with open(os.path.join(root, "run1", "session.json")) as f:
        session_info = json.load(f)
    manifest = {
        "profile": args.profile, "seed": args.seed, "step": args.step, "every": args.every, "runs": args.runs,
        "frames": len(frames), "identicalFrames": identical, "allIdentical": identical == len(frames),
        "game": {"version": session_info.get("version"), "commit": session_info.get("commit"),
                 "strata": session_info.get("strata"), "abi": session_info.get("abi"),
                 "size": session_info.get("size"), "args": session_info.get("args")},
        "script": [list(a) for a in SCRIPTS[args.profile]],
        "perFrame": frames,
    }
    with open(os.path.join(out, "frames.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    print("%s: %d of %d frames identical across %d runs" % (name, identical, len(frames), args.runs))

    if shutil.which("convert") and shutil.which("montage"):
        delay = str(int(round(args.every * args.step * 100)))
        magick("convert", "-delay", delay, "-loop", "0", *runs[0], "-resize", "%dx" % args.gif_width,
               "+dither", "-colors", "128", "-fuzz", "1%", "-layers", "Optimize", os.path.join(out, name + ".gif"))
        pick = runs[0][::max(1, len(runs[0]) // 12)][:12]
        labelled = []
        for p in pick:
            labelled += ["-label", "frame %d" % int(os.path.basename(p)[6:11]), p]
        magick("montage", *font_args(), *labelled, "-tile", "4x", "-geometry", "240x135+3+3", "-background",
               "#202020", "-fill", "#e0e0e0", "-pointsize", "12", "-quality", "85",
               os.path.join(out, name + "-sheet.jpg"))
        if len(runs) > 1:
            last1, last2 = runs[0][-1], runs[1][-1]
            diff = os.path.join(root, "diff.png")
            subprocess.run(["compare", "-metric", "AE", "-compose", "src", "-highlight-color", "red",
                            "-lowlight-color", "black", last1, last2, diff],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            magick("montage", *font_args(), "-label", "run 1, frame %d" % frames[-1]["frame"], last1,
                   "-label", "run 2, frame %d" % frames[-1]["frame"], last2,
                   "-label", "difference (red where pixels differ)", diff,
                   "-tile", "3x", "-geometry", "320x180+4+4", "-background", "#202020", "-fill", "#e0e0e0",
                   "-pointsize", "14", os.path.join(out, name + "-runs.png"))
    shutil.rmtree(root, ignore_errors=True)
    return 0 if identical == len(frames) else 1


if __name__ == "__main__":
    sys.exit(main())
