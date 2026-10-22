"""Checks a game's probe output against the probe contract (docs/PROBE_CONTRACT.md).

    pt probe-check DIR
    python3 -m playtester.probecheck DIR [--require-world]
    python3 -m playtester.probecheck --events-only FILE.jsonl

DIR holds the game's ``state.json`` and ``events.jsonl``. Every event line
must be valid JSON matching ``event.schema.json``, ticks must never go
backwards within one world, and state.json must match ``state.schema.json``.
``--events-only`` checks one events file on its own (recorded evidence keeps
the events but not the last state).
Prints one line per problem; exits 0 when there are none.
"""

import json
import os
import sys
from typing import List

from .schema import load_schema, validate


def check_state(state: object) -> List[str]:
    return ["state.json %s" % e for e in validate(state, load_schema("state.schema.json"))]


def check_events_lines(lines: List[str]) -> List[str]:
    schema = load_schema("event.schema.json")
    problems = []
    last_tick = None
    for n, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError as e:
            problems.append("events.jsonl line %d: not valid JSON (%s)" % (n, e))
            continue
        problems.extend("events.jsonl line %d %s" % (n, e) for e in validate(event, schema))
        if not isinstance(event, dict):
            continue
        if event.get("type") == "world":
            last_tick = None
        tick = event.get("tick")
        if isinstance(tick, int) and event.get("type") != "screen":
            if last_tick is not None and tick < last_tick:
                problems.append("events.jsonl line %d: tick %d is before the previous event's %d in the same world"
                                % (n, tick, last_tick))
            last_tick = tick
    return problems


def check_dir(directory: str, require_world: bool = False) -> List[str]:
    problems = []
    state_path = os.path.join(directory, "state.json")
    events_path = os.path.join(directory, "events.jsonl")
    try:
        with open(state_path, encoding="utf-8") as f:
            state = json.load(f)
        problems.extend(check_state(state))
        if require_world and not (isinstance(state, dict) and state.get("world")):
            problems.append("state.json: no world in play (world is not true)")
    except OSError:
        problems.append("state.json: missing in %s" % directory)
    except ValueError as e:
        problems.append("state.json: not valid JSON (%s)" % e)
    try:
        with open(events_path, encoding="utf-8") as f:
            lines = f.readlines()
        problems.extend(check_events_lines(lines))
        if not any(l.strip() for l in lines):
            problems.append("events.jsonl: empty (a game writes at least its first screen event)")
    except OSError:
        problems.append("events.jsonl: missing in %s" % directory)
    return problems


def check_events_file(path: str) -> List[str]:
    try:
        with open(path, encoding="utf-8") as f:
            return check_events_lines(f.readlines())
    except OSError as e:
        return ["%s: cannot read: %s" % (path, e.strerror)]


def main(argv: List[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        print(__doc__.strip())
        return 2
    if "--events-only" in argv:
        problems = ["%s: %s" % (args[0], p) for p in check_events_file(args[0])]
    else:
        problems = check_dir(args[0], require_world="--require-world" in argv)
    for p in problems:
        print(p)
    if not problems:
        print("ok: %s conforms to the probe contract" % args[0])
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
