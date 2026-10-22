"""Measures what N concurrent playtest sessions cost on this machine.

    pt measure N [SETTLE_SEC] [SAMPLE_SEC] [--brief] [--profile P] [--game-dir D]

Starts N sessions (straight into a world, with the profile's
``launch.quick_world_args``), lets them settle, then samples CPU (from /proc,
so it is the rate over the sample window, not ps's lifetime average),
resident memory of each game and its Xvfb, and the frame and tick rates each
game reports in state.json. Stops every session it started, even on Ctrl-C.
PT_WIDTH, PT_HEIGHT and PT_LP_THREADS are passed through, so configurations
can be compared. Prints one JSON object.
"""

import json
import os
import statistics
import subprocess
import sys
import time
from typing import List, Optional

from . import profile as profiles
from .session import Session, default_root

TICK = os.sysconf("SC_CLK_TCK")


def cpu_ticks(pid: Optional[int]) -> Optional[int]:
    try:
        with open("/proc/%d/stat" % pid) as f:
            fields = f.read().rsplit(")", 1)[1].split()
        return int(fields[11]) + int(fields[12])  # utime + stime
    except (OSError, IndexError, ValueError, TypeError):
        return None


def rss_mb(pid: Optional[int]) -> Optional[float]:
    try:
        with open("/proc/%d/status" % pid) as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024.0
    except (OSError, TypeError):
        pass
    return None


def mem_available_mb() -> Optional[float]:
    with open("/proc/meminfo") as f:
        for line in f:
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) / 1024.0
    return None


def main(argv: List[str]) -> int:
    opts = {"--profile": os.environ.get("PT_PROFILE"), "--game-dir": os.environ.get("PT_GAME_DIR") or os.getcwd()}
    args, flags = [], set()
    rest = list(argv)
    while rest:
        a = rest.pop(0)
        if a in opts and rest:
            opts[a] = rest.pop(0)
        elif a.startswith("--"):
            flags.add(a)
        else:
            args.append(a)
    if not args:
        print(__doc__.strip())
        return 2
    profile = profiles.load(opts["--profile"] or "")
    n = int(args[0])
    settle = float(args[1]) if len(args) > 1 else 30.0
    window = float(args[2]) if len(args) > 2 else 20.0
    root = os.path.join(default_root(), "measure-%d-%d" % (n, int(time.time())))
    names = ["m%02d" % i for i in range(1, n + 1)]
    pt = [sys.executable, "-m", "playtester"]
    mem_before = mem_available_mb()
    load_before = os.getloadavg()[0]
    started = []
    try:
        procs = []
        for i, name in enumerate(names):
            env = dict(os.environ, PT_ROOT=root, PT_SESSION=name)
            cmd = pt + ["start", "--profile", profile["_source"], "--game-dir", opts["--game-dir"], "--seed", str(100 + i)]
            cmd += profile["launch"].get("quick_world_args", [])
            procs.append((name, subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                                 universal_newlines=True)))
        t0 = time.time()
        for name, p in procs:
            output = p.communicate()[0]
            if p.returncode == 0:
                started.append(name)
            else:
                print("start failed for %s:\n%s" % (name, output), file=sys.stderr)
        startup = time.time() - t0
        time.sleep(settle)
        sessions = {name: Session(name, root) for name in started}
        pids = {name: (s._pid("game"), s._pid("xvfb")) for name, s in sessions.items()}
        before = {name: (cpu_ticks(g), cpu_ticks(x)) for name, (g, x) in pids.items()}
        time.sleep(window)
        rows = []
        for name, (g, x) in pids.items():
            g1, x1 = cpu_ticks(g), cpu_ticks(x)
            g0, x0 = before[name]
            try:
                with open(os.path.join(root, name, "out", "state.json")) as f:
                    st = json.load(f)
            except (OSError, ValueError):
                st = {}
            rows.append({
                "session": name,
                "gameCpuCores": round((g1 - g0) / TICK / window, 2) if None not in (g0, g1) else None,
                "xvfbCpuCores": round((x1 - x0) / TICK / window, 2) if None not in (x0, x1) else None,
                "gameRssMb": round(rss_mb(g) or 0, 1),
                "xvfbRssMb": round(rss_mb(x) or 0, 1),
                "fps": st.get("fps"), "tps": st.get("tps"), "screen": st.get("screen"),
            })
        mem_after = mem_available_mb()
        fps = [r["fps"] for r in rows if isinstance(r["fps"], (int, float))]
        cores = [r["gameCpuCores"] + (r["xvfbCpuCores"] or 0) for r in rows if r["gameCpuCores"] is not None]
        tps = [r["tps"] for r in rows if isinstance(r["tps"], (int, float))]
        result = {
            "profile": profile["name"], "sessions": n, "started": len(started),
            "size": "%sx%s" % (os.environ.get("PT_WIDTH", profile["window"]["width"]),
                               os.environ.get("PT_HEIGHT", profile["window"]["height"])),
            "lpThreads": os.environ.get("PT_LP_THREADS") or profile["launch"].get("lp_threads") or 2, "cpuCount": os.cpu_count(),
            "loadBefore": round(load_before, 1), "startupSec": round(startup, 1),
            "totalCpuCores": round(sum(cores), 1),
            "perSessionCpuCores": round(statistics.mean(cores), 2) if cores else None,
            "perSessionRssMb": round(statistics.mean([r["gameRssMb"] + r["xvfbRssMb"] for r in rows]), 0) if rows else None,
            "memUsedMb": round(mem_before - mem_after, 0) if mem_before and mem_after else None,
            "fpsMin": min(fps) if fps else None, "fpsMedian": statistics.median(fps) if fps else None,
            "fpsMax": max(fps) if fps else None, "tpsMin": min(tps) if tps else None,
            "rows": rows,
        }
        if "--brief" in flags:
            result.pop("rows")
            print(json.dumps(result))
        else:
            print(json.dumps(result, indent=2))
    finally:
        for name in names:
            Session(name, root).stop()
    return 0
