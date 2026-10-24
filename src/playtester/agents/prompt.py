"""Fills the playtest agent prompt for one session.

    pt prompt --profile NAME --goal TEXT --session s01 --run-dir DIR [--seed S]
              [--budget MIN] [--game-dir DIR] [--start-args "..."] [--goal-index N]
              [--pt-command "python3 -m playtester"]

Prints everything below the template's ``---`` line with the placeholders
filled from the arguments and the game's profile (its controls notes, probe
commands, window size and cheats rule). ``--goal-index N`` takes the goal,
seed, budget and arguments from the profile's Nth default goal.
``--pt-command`` is how agents run the harness (default: this interpreter
with ``-m playtester``).
"""

import json
import os
import shlex
import sys
from typing import Any, Dict, List, Optional

from ..harness import profile as profiles
from ..schema import DATA_DIR

TEMPLATE = os.path.join(DATA_DIR, "prompts", "AGENT_PROMPT.md")

PROBE_COMMANDS = """| `pt state` | compact state from the game's probe: screen, tick, player position and heading, nearest things with distance and bearing, and whatever else the game reports |
| `pt state --full` | the whole state.json |
| `pt events 20` | the last 20 game events (objectives completed, screens, deaths, saves...) |
| `pt await SCREEN 20` | wait until the game shows that screen ({SCREENS}) |
| `pt face DEG` | turn DEG degrees, + right / - left, closed loop |
{WALKTO}"""

WALKTO = "| `pt walkto KIND [60]` | walk to the nearest {KINDS} until it is within reach, then stop{INTERACT} |\n"

PROBE_NOTES = """The game writes what it shows to `state.json` and `events.jsonl` (its
*probe*), so you can steer precisely (where the nearest thing is, which way
you face) and check numbers. Game time can run slower than real time on a
busy machine (`pt state` shows `tps`; {TPS} is full speed): judge pacing in
game time, ticks / {TPS} = seconds."""

NO_PROBE_NOTES = """This game has no probe: everything you know comes from screenshots. Look
often, and say in a finding when the screen does not tell a player
something they need."""


QUESTIONS = """## Questions to answer at the end

Before you write the report, answer each of these in your own words, from
what you saw, heard and read in the game itself (not from the game's
documentation or source, and not from what you already knew about it). An
honest "I could not tell" is a useful answer.

{LIST}

Put the answers in `report.json` as `answers`, one per question, with the
question copied verbatim:

```json
"answers": [
  {{"question": "<question 1, verbatim>", "answer": "<your answer>"}}
]
```

`pt report` checks that every question has an answer.

"""


def questions_section(profile: Dict[str, Any]) -> str:
    """The prompt's section for the profile's ``questions``, or an empty string."""
    questions = [q for q in profile.get("questions") or [] if q]
    if not questions:
        return ""
    return QUESTIONS.format(LIST="\n".join("%d. %s" % (i, q) for i, q in enumerate(questions, 1)))


def fill(profile: Dict[str, Any], goal: str, session: str, run_dir: str, seed: Optional[str] = None,
         budget_min: float = 30, game_dir: Optional[str] = None, start_args: str = "",
         pt_command: Optional[str] = None) -> str:
    """The prompt text for one agent."""
    with open(TEMPLATE, encoding="utf-8") as f:
        template = f.read().split("\n---\n", 1)[1].lstrip("\n")
    run_dir = os.path.abspath(run_dir)
    game_dir = os.path.abspath(game_dir or os.getcwd())
    probe = profile.get("probe")
    movement = profile.get("movement") or {}
    pt_command = pt_command or "%s -m playtester" % shlex.quote(sys.executable)
    prefix = "PT_ROOT=%s PT_SESSION=%s %s" % (shlex.quote(run_dir), shlex.quote(session), pt_command)
    source = profile.get("_source") or ""
    bundled = not source or os.path.dirname(source) == profiles.PROFILE_DIR
    start = " --profile %s --game-dir %s" % (shlex.quote(profile["name"] if bundled else source), shlex.quote(game_dir))
    if seed not in (None, ""):
        start += " --seed %s" % shlex.quote(str(seed))
    if start_args:
        start += " " + start_args
    if probe:
        kinds = movement.get("nearest_kinds") or []
        walkto = ""
        if movement:
            interact = ""
            if movement.get("interact_key"):
                interact = ". Then press `%s`." % movement["interact_key"]
            walkto = WALKTO.format(KINDS=", ".join("`%s`" % k for k in kinds) or "thing of that kind", INTERACT=interact)
        screens = ", ".join(probe.get("screens") or ["WORLD"])
        commands = PROBE_COMMANDS.format(SCREENS=screens, WALKTO=walkto)
        tps = "%g" % probe["ticks_per_second"]
        notes = PROBE_NOTES.format(TPS=tps)
        probe_rule = ("`state.json` is there so you can steer precisely and check numbers; it is not a way to "
                      "skip reading the screen. If something matters to the player but is only in `state.json` "
                      "and not visible on screen, that is a finding.")
        metrics_note = ("`secondsToObjective` is game seconds (the event's tick / %s); `pt events` shows "
                        "`objective_completed` events with their ticks." % tps)
        tick_hint = ", the tick (`pt state` shows it)"
        version_source = "state.json version"
        status_extra = ", fps, ticks a second"
    else:
        commands, notes = "", NO_PROBE_NOTES
        probe_rule = "There is no state file for this game, so screenshots are all you have; that is the point."
        metrics_note = "`secondsToObjective` is wall-clock seconds for a game without a probe; say so in the verdict."
        tick_hint = ""
        version_source = "the version the game shows, or session.json version, or null"
        status_extra = ""
    cheats = profile.get("cheats") or "Use only what a player would: no debug keys or developer switches unless your goal says so."
    try:
        seed_json = json.dumps(int(seed)) if seed not in (None, "") else "null"
    except ValueError:
        seed_json = json.dumps(str(seed))
    values = {
        "GAME": profile["title"],
        "GAME_DESCRIPTION": profile["description"].rstrip(".") + ".",
        "GOAL": goal,
        "SESSION": session,
        "RUN_DIR": run_dir,
        "SEED": "-" if seed in (None, "") else str(seed),
        "SEED_JSON": seed_json,
        "TIME_BUDGET_MIN": "%g" % float(budget_min),
        "GAME_DIR": game_dir,
        "PT": prefix,
        "START_ARGS": start,
        "WIDTH": str(profile["window"]["width"]),
        "HEIGHT": str(profile["window"]["height"]),
        "PROBE_RULE": probe_rule,
        "PROBE_COMMANDS": commands,
        "PROBE_NOTES": notes,
        "CHEATS_RULE": cheats,
        "CONTROLS": profiles.agent_notes(profile) or "See the game's own help screen.",
        "TICK_HINT": tick_hint,
        "VERSION_SOURCE": version_source,
        "METRICS_NOTE": metrics_note,
        "STATUS_EXTRA": status_extra,
        "QUESTIONS": questions_section(profile),
    }
    text = template
    for key, value in values.items():
        text = text.replace("{{%s}}" % key, value)
    return text


def main(argv: List[str]) -> int:
    opts = {"--profile": None, "--goal": None, "--session": None, "--run-dir": None, "--seed": None,
            "--budget": "30", "--game-dir": None, "--start-args": "", "--goal-index": None, "--pt-command": None}
    args = list(argv[1:])
    while args:
        key = args.pop(0)
        if key not in opts or not args:
            print(__doc__.strip())
            return 2
        opts[key] = args.pop(0)
    profile = profiles.load(opts["--profile"] or os.environ.get("PT_PROFILE", ""))
    if opts["--goal-index"] is not None:
        g = profile["goals"][int(opts["--goal-index"]) - 1]
        opts["--goal"] = opts["--goal"] or g["goal"]
        if opts["--seed"] is None and "seed" in g:
            opts["--seed"] = str(g["seed"])
        if "budget_min" in g and opts["--budget"] == "30":
            opts["--budget"] = str(g["budget_min"])
        if g.get("args") and not opts["--start-args"]:
            opts["--start-args"] = " ".join(shlex.quote(a) for a in g["args"])
    if not (opts["--goal"] and opts["--session"] and opts["--run-dir"]):
        print(__doc__.strip())
        return 2
    sys.stdout.write(fill(profile, opts["--goal"], opts["--session"], opts["--run-dir"], opts["--seed"],
                          float(opts["--budget"]), opts["--game-dir"], opts["--start-args"], opts["--pt-command"]))
    return 0
