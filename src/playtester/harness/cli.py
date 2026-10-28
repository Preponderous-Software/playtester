"""pt: drive one playtest session of a real game, headless.

    PT_SESSION=s01 pt start --profile beyond-nations --game-dir ~/beyond-nations --seed 42
    PT_SESSION=s01 pt shot title
    PT_SESSION=s01 pt stop

Session commands (need PT_SESSION; PT_ROOT is where sessions live)
  start [--profile P] [--game-dir D] [--seed S] [--no-probe] [--width W --height H]
        [--clock free|stepped [--step SECS]] [game args...]
                            Xvfb on a free display + the game; waits for its window
                            (and first state.json); on failure prints the log tail and cleans up.
                            A "driver": "strata" profile needs no Xvfb: the game runs headless
                            and is driven through its drive channel; --clock stepped makes it
                            wait for pt between frames, so a run repeats frame for frame
  stop                      stop the game and its Xvfb (safe to repeat)
  status                    running?, display, CPU/RSS, fps (Strata driver: frame and clock)
  key KEY...                tap keys; a KEY may be a combo such as Shift_L+w
  hold KEY SECS             hold a key or combo
  click X Y [BUTTON]        click at window coordinates (hovers first)
  mousehold SECS [BUTTON]   hold a mouse button where the pointer is
  move X Y                  move the pointer without clicking
  look DX DY                relative pointer motion (mouse look)
  drag X1 Y1 X2 Y2 SECS [BUTTON]   drag with a button held (default 3, the right one)
  scroll N                  mouse wheel: + down, - up
  type TEXT                 type text into a focused text field
  shot NAME                 screenshot of the game's window to shots/NAME.png; prints the path
  note [--shot NAME] TEXT   append a finding to findings.jsonl (optionally with a screenshot)
  wait SECS                 let SECS of game time pass (sleep; stepped: step SECS/step frames)
  step N                    run exactly N frames (Strata driver, stepped clock only)
  log [N]                   tail of the game's log
  dir                       print the session directory
  report                    validate the session's report.json
Probe commands (games with a probe; docs/PROBE_CONTRACT.md)
  state [--full]            the game's state.json, compact (or whole)
  events [N]                the last N lines of events.jsonl (default 20)
  await SCREEN [SECS]       wait until state.json shows SCREEN; fails after SECS (default 15)
  face DEG                  turn DEG degrees (+ right, - left), closed loop
  walkto KIND [MAXSEC]      walk to the nearest KIND until it is within reach
  probe-check [DIR]         validate state.json and events.jsonl against the probe contract
Run commands
  smoke [--profile P] [--game-dir D] [--session NAME] [--clock free|stepped [--step SECS]] [--keep]
                            scripted session proving the harness on this machine
                            (its own session, smoke-<pid> by default; --keep leaves it running)
  measure N [SETTLE] [SAMPLE] [--brief]  cost of N concurrent sessions
  prompt ...                fill the agent prompt for one session (pt prompt for its options)
  aggregate RUN_DIR         merge a run's reports into summary.md and summary.json
  install-skill REPO [--profile P]   copy the coordinator skill into REPO/.claude/skills/playtest
  profiles                  list the bundled game profiles
  validate-profile PATH     check a profile file

Environment: PT_SESSION, PT_ROOT (default $TMPDIR/playtester), PT_PROFILE,
PT_GAME_DIR, PT_WIDTH/PT_HEIGHT, PT_LP_THREADS (llvmpipe threads, default 2),
PT_GAME_ARGS (extra game arguments for every start), PT_CLOCK/PT_STEP (pt start
--clock/--step defaults, Strata driver).
"""

import json
import os
import re
import shlex
import sys
import time
from typing import Any, Dict, List, Optional

from . import inputs, probe, strata_keys
from . import profile as profiles
from .session import HarnessError, Session, now_ms, append_json, tail
from .strata_driver import DriveError

SESSION_COMMANDS = {"start", "stop", "status", "key", "hold", "click", "mousehold", "move", "look", "drag", "scroll",
                    "type", "shot", "note", "wait", "step", "log", "dir", "report", "state", "events", "await", "face",
                    "walkto", "probe-check"}


def out(obj: Any) -> None:
    print(json.dumps(obj, separators=(",", ":"), ensure_ascii=False))


def _need(args: List[str], n: int, usage: str) -> None:
    if len(args) < n:
        raise HarnessError("usage: pt " + usage)


def safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)


def screenshot(session: Session, name: str) -> str:
    """shots/NAME.png, always inside the session directory (the name is sanitised)."""
    inp = session.input()
    path = session.path("shots", safe_name(name) + ".png")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        return inp.screenshot(path)
    except inputs.InputError as e:
        raise HarnessError(str(e))


def parse_start(args: List[str]) -> Dict[str, Any]:
    opts = {"profile": os.environ.get("PT_PROFILE"), "game_dir": os.environ.get("PT_GAME_DIR") or os.getcwd(),
            "seed": None, "probe": True, "width": os.environ.get("PT_WIDTH"), "height": os.environ.get("PT_HEIGHT"),
            "clock": os.environ.get("PT_CLOCK"), "step": os.environ.get("PT_STEP"),
            "extra": []}  # type: Dict[str, Any]
    takes = {"--profile": "profile", "--game-dir": "game_dir", "--seed": "seed", "--width": "width", "--height": "height",
             "--clock": "clock", "--step": "step"}
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            opts["extra"].extend(args[i + 1:])
            break
        if a in takes:
            if i + 1 >= len(args):
                raise HarnessError("pt start: %s needs a value" % a)
            opts[takes[a]] = args[i + 1]
            i += 2
            continue
        if a == "--no-probe":
            opts["probe"] = False
        else:
            opts["extra"].append(a)
        i += 1
    opts["extra"] = shlex.split(os.environ.get("PT_GAME_ARGS", "")) + opts["extra"]
    opts["game_dir"] = os.path.abspath(os.path.expanduser(opts["game_dir"]))
    return opts


def run_session_command(session: Session, cmd: str, args: List[str]) -> int:
    """One harness command against ``session``; returns the exit status."""
    if cmd == "start":
        opts = parse_start(args)
        profile = profiles.load(opts["profile"] or "")
        info = session.start(profile, opts["game_dir"], opts["seed"], opts["extra"], use_probe=opts["probe"],
                             width=opts["width"], height=opts["height"], clock=opts["clock"],
                             step=float(opts["step"]) if opts["step"] else None)
        for warning in info.get("buildWarnings", []):
            print("pt: warning: " + warning, file=sys.stderr)
        out(info)
    elif cmd == "stop":
        session.stop()
        print("stopped " + session.name)
    elif cmd == "status":
        out(session.status())
    elif cmd == "key":
        _need(args, 1, "key KEY...")
        inp = session.input()
        for k in args:
            inp.tap(k)
    elif cmd == "hold":
        _need(args, 2, "hold KEY SECS")
        session.input().hold(args[0], float(args[1]))
    elif cmd == "click":
        _need(args, 2, "click X Y [BUTTON]")
        session.input().click(int(args[0]), int(args[1]), int(args[2]) if len(args) > 2 else 1)
    elif cmd == "mousehold":
        _need(args, 1, "mousehold SECS [BUTTON]")
        session.input().button_hold(float(args[0]), int(args[1]) if len(args) > 1 else 1)
    elif cmd == "move":
        _need(args, 2, "move X Y")
        session.input().move(int(args[0]), int(args[1]))
    elif cmd == "look":
        _need(args, 2, "look DX DY")
        session.input().look(int(float(args[0])), int(float(args[1])))
    elif cmd == "drag":
        _need(args, 5, "drag X1 Y1 X2 Y2 SECS [BUTTON]")
        x1, y1, x2, y2 = (int(a) for a in args[:4])
        session.input().drag(x1, y1, x2, y2, float(args[4]), int(args[5]) if len(args) > 5 else 3)
    elif cmd == "scroll":
        _need(args, 1, "scroll N")
        session.input().scroll(int(args[0]))
    elif cmd == "type":
        session.input().type_text(" ".join(args))
    elif cmd == "shot":
        _need(args, 1, "shot NAME")
        print(screenshot(session, args[0]))
    elif cmd == "note":
        shot = None
        if args and args[0] == "--shot":
            _need(args, 2, "note [--shot NAME] TEXT")
            shot = screenshot(session, args[1])
            args = args[2:]
        entry = {"t": now_ms(), "text": " ".join(args)}  # type: Dict[str, Any]
        if shot:
            entry["screenshot"] = os.path.relpath(shot, session.dir)
        st = probe.read_state(session)
        if st and st.get("tick") is not None:
            entry["tick"] = st.get("tick")
        append_json(session.path("findings.jsonl"), entry)
        out(entry)
    elif cmd == "wait":
        _need(args, 1, "wait SECS")
        if session.game_alive():
            session.input().wait(float(args[0]))
        else:
            time.sleep(float(args[0]))
    elif cmd == "step":
        _need(args, 1, "step N")
        inp = session.input()
        if not isinstance(inp, inputs.StrataInput):
            raise HarnessError("pt step needs a Strata-driver session started with --clock stepped")
        out(inp.step(int(args[0])))
    elif cmd == "log":
        sys.stdout.write(tail(session.path("game.log"), int(args[0]) if args else 25))
    elif cmd == "dir":
        print(session.dir)
    elif cmd == "report":
        from ..agents.report import main as report_main
        try:
            questions = session.profile().get("questions") or []
        except profiles.ProfileError:
            questions = []  # a report checked outside a session the harness started
        return report_main(["report", session.path("report.json")], questions)
    elif cmd == "state":
        st = probe.read_state(session)
        if "--full" in args:
            print(json.dumps(st, indent=2, ensure_ascii=False))
        else:
            kinds = (session.profile().get("movement") or {}).get("nearest_kinds") or []
            out(probe.compact(st, kinds))
        return 0 if st is not None else 1
    elif cmd == "events":
        n = int(args[0]) if args else 20
        for e in probe.read_events(session)[-n:] if n > 0 else []:
            out(e)
    elif cmd == "await":
        _need(args, 1, "await SCREEN [SECS]")
        result = probe.await_screen(session, args[0], float(args[1]) if len(args) > 1 else 15.0)
        out(result)
        return 0 if result["ok"] else 1
    elif cmd == "face":
        _need(args, 1, "face DEG")
        result = probe.face(session, float(args[0]))
        out(result)
        return 0 if result.get("ok") else 1
    elif cmd == "walkto":
        _need(args, 1, "walkto KIND [MAXSEC]")
        result = probe.walkto(session, args[0], float(args[1]) if len(args) > 1 else 60.0)
        out(result)
        return 0 if result.get("ok") else 1
    elif cmd == "probe-check":
        from ..probecheck import check_dir
        problems = check_dir(args[0] if args else session.probe_dir)
        for p in problems:
            print(p)
        if not problems:
            print("ok: probe output conforms to the contract")
        return 1 if problems else 0
    return 0


def install_skill(args: List[str]) -> int:
    from ..schema import DATA_DIR
    if not args:
        raise HarnessError("usage: pt install-skill REPO [--profile NAME]")
    repo = os.path.abspath(args[0])
    name = "<profile>"
    if "--profile" in args:
        name = args[args.index("--profile") + 1]
        profiles.load(name)
    with open(os.path.join(DATA_DIR, "skills", "playtest", "SKILL.md"), encoding="utf-8") as f:
        text = f.read().replace("{{PROFILE}}", name)
    dest = os.path.join(repo, ".claude", "skills", "playtest", "SKILL.md")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        f.write(text)
    print(dest)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "help"
    args = argv[1:]
    try:
        if cmd in ("help", "-h", "--help"):
            print(__doc__.strip())
            return 0
        if cmd in ("--version", "version"):
            from .. import __version__
            print(__version__)
            return 0
        if cmd in SESSION_COMMANDS:
            session = Session(os.environ.get("PT_SESSION", ""), os.environ.get("PT_ROOT"))
            os.makedirs(session.dir, exist_ok=True)
            session.log_action(cmd, args)
            return run_session_command(session, cmd, args)
        if cmd == "smoke":
            from .smoke import main as smoke_main
            return smoke_main(args)
        if cmd == "measure":
            from .measure import main as measure_main
            return measure_main(args)
        if cmd == "prompt":
            from ..agents.prompt import main as prompt_main
            return prompt_main(["prompt"] + args)
        if cmd == "aggregate":
            from ..agents.aggregate import main as aggregate_main
            return aggregate_main(["aggregate"] + args)
        if cmd == "install-skill":
            return install_skill(args)
        if cmd == "profiles":
            for name in profiles.available():
                p = profiles.load(name)
                print("%-16s %s%s" % (name, p["title"], " (probe: %s)" % p["probe"]["flag"] if p.get("probe") else " (screenshots only)"))
            return 0
        if cmd == "validate-profile":
            _need(args, 1, "validate-profile PATH")
            p = profiles.load(args[0])
            print("ok: %s (%s), from %s" % (args[0], p["title"], p["_source"]))
            if p.get("build"):
                print("build: " + p["build"]["command"])
                if p["build"].get("requires"):
                    print("build needs: " + ", ".join(p["build"]["requires"]))
            print("window: %dx%d; probe: %s; process: %s" % (
                p["window"]["width"], p["window"]["height"], p["probe"]["flag"] if p.get("probe") else "none",
                p.get("process_name", "-")))
            return 0
        raise HarnessError("unknown command: %s (pt help)" % cmd)
    except (HarnessError, profiles.ProfileError, RuntimeError, DriveError, strata_keys.UnknownKey) as e:
        print("pt: %s" % e, file=sys.stderr)
        return 1
    except (ValueError, IndexError) as e:
        print("pt %s: bad or missing argument: %s" % (cmd, e), file=sys.stderr)
        return 2
    except KeyError as e:
        print("pt %s: missing field %s (in the game's probe output or the profile; see docs/PROBE_CONTRACT.md"
              " and docs/PROFILES.md)" % (cmd, e), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
