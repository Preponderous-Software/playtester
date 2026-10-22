"""A scripted session that proves the harness end to end on this machine.

    pt smoke [--profile P] [--game-dir D] [--session NAME] [--keep]

Runs the profile's ``smoke`` script through the same commands an agent uses:
starts the game with the script's seed and arguments, runs its steps, then
(if the script has an ``until``) repeats the ``until`` steps until the game
writes the expected event. Prints PASS or FAIL; always stops its session
(``--keep`` leaves the session directory's files, which are kept anyway).
"""

import os
import sys
import time
from typing import List

from . import probe
from . import profile as profiles
from .cli import run_session_command, screenshot
from .session import HarnessError, Session, default_root


def main(args: List[str]) -> int:
    opts = {"--profile": os.environ.get("PT_PROFILE"), "--game-dir": os.environ.get("PT_GAME_DIR") or os.getcwd(),
            "--session": os.environ.get("PT_SESSION") or "smoke"}
    rest = list(args)
    while rest:
        key = rest.pop(0)
        if key == "--keep":
            continue
        if key not in opts or not rest:
            print(__doc__.strip())
            return 2
        opts[key] = rest.pop(0)
    profile = profiles.load(opts["--profile"] or "")
    script = profile.get("smoke")
    if not script:
        print("smoke: the %s profile has no smoke script" % profile["name"], file=sys.stderr)
        return 2
    root = os.environ.get("PT_ROOT") or os.path.join(default_root(), "smoke-%d" % int(time.time()))
    session = Session(opts["--session"], root)
    os.makedirs(session.dir, exist_ok=True)

    def run(step: List[str]) -> int:
        session.log_action(step[0], step[1:])
        return run_session_command(session, step[0], step[1:])

    started = time.time()
    try:
        start = ["start", "--profile", profile["_source"], "--game-dir", opts["--game-dir"]]
        if script.get("seed") is not None:
            start += ["--seed", str(script["seed"])]
        if run(start + list(script.get("args", []))) != 0:
            raise HarnessError("start failed")
        for step in script["steps"]:
            if run(step) != 0:
                raise HarnessError("step failed: " + " ".join(step))
        until = script.get("until")
        if until:
            may_fail = set(until.get("may_fail", []))
            for attempt in range(1, int(until.get("attempts", 10)) + 1):
                for step in until["steps"]:
                    if run(step) != 0:
                        if step[0] in may_fail:
                            break
                        raise HarnessError("step failed: " + " ".join(step))
                event = next((e for e in probe.read_events(session) if probe.event_matches(e, until["event"])), None)
                if event:
                    print("smoke %s: PASS: %s after %d attempt(s), %ds" % (
                        profile["name"], json_line(until["event"]), attempt, time.time() - started))
                    return 0
            raise HarnessError("no event %s after %d attempts" % (json_line(until["event"]), until.get("attempts", 10)))
        print("smoke %s: PASS: every step ran, %ds" % (profile["name"], time.time() - started))
        return 0
    except (HarnessError, profiles.ProfileError, RuntimeError) as e:
        try:
            screenshot(session, "fail")
        except HarnessError:
            pass
        print("smoke %s: FAIL: %s (session %s)" % (profile["name"], e, session.dir), file=sys.stderr)
        sys.stderr.write(session_tail(session))
        return 1
    finally:
        session.stop()


def json_line(obj) -> str:
    import json
    return json.dumps(obj, separators=(",", ":"))


def session_tail(session: Session) -> str:
    from .session import tail
    text = tail(session.path("game.log"), 15)
    return ("last lines of game.log:\n" + text) if text else ""
