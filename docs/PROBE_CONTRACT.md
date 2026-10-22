# The probe contract

A game can help AI playtesters by writing what the player sees to two files
while it runs. Playtester calls this the game's **probe**. It is optional:
every `pt` command except `state`, `events`, `await`, `face` and `walkto`
works from screenshots alone. With a probe, agents can steer precisely (turn
to a bearing, walk to the nearest tree), check numbers, and the aggregator
can time objectives across sessions from the game's own events rather than
from the agents' accounts.

The contract is small on purpose: a few required fields, a few standard event
types, and room for anything else a game wants to report.

| | |
| --- | --- |
| Schemas | [`state.schema.json`](../src/playtester/data/schemas/state.schema.json), [`event.schema.json`](../src/playtester/data/schemas/event.schema.json) |
| Checker | `pt probe-check DIR` or `python3 -m playtester.probecheck DIR [--require-world]` |
| Reference implementation | [`src/playtester/demo.py`](../src/playtester/demo.py) (about 60 lines of it) |
| Implementations | Beyond Nations (`--playtest-out`, since 0.5.0), Kindling (`--playtest-out`) |

## Turning it on

The game takes a command-line option naming a directory, conventionally
`--playtest-out DIR`, and writes `DIR/state.json` and `DIR/events.jsonl`.
The profile's `probe.flag` names the option; `pt start` passes
`<flag> <session>/out`. Without the option the game writes nothing and
behaves exactly as it always does.

Two rules make a probe safe to leave in a shipped game:

- **Read, never write.** The probe observes what the game already shows. It
  must not change the simulation: the same seed and inputs give the same
  world with or without it. (Beyond Nations finds events by comparing each
  frame with the previous one; Kindling's test checks the world's
  fingerprint is identical with and without recording.)
- **Never take the game down.** A file that cannot be written is reported
  once and otherwise ignored.

## `state.json`

A snapshot of the game, **rewritten about twice a second** and **atomically**:
write a temporary file beside it and rename it over the old one, so a reader
never sees half a file.

Required always:

| Field | Type | |
| --- | --- | --- |
| `wallTimeMs` | integer | Unix time in milliseconds when it was written (the harness uses it to wait for a fresh state) |
| `version` | string | The version the game shows |
| `screen` | string | The screen on show, upper case: `TITLE`, `MAIN_MENU`, `WORLD`, `PAUSE`, ... |
| `world` | boolean | Whether a game is in play; when `true` the fields below are required |

Required when `world` is `true`:

| Field | Type | |
| --- | --- | --- |
| `tick` | integer | Simulation ticks since the world began (saved with it, so it is game time) |
| `seed` | integer or string | The seed the world was made from |
| `player.x`, `player.z` | number | Position on the ground plane (`player.y` optional) |
| `player.yawDeg` | number | Heading in degrees. Which way it grows when the player turns is the profile's `movement.yaw_increases` |

Optional, with fixed meanings when present:

| Field | |
| --- | --- |
| `fps` | Frames a second |
| `tps` | Measured simulation ticks per wall-clock second. Below the game's full rate (the profile's `probe.ticks_per_second`) the world runs slower than real time, which happens when many sessions share a machine |
| `openPanels` | Names of panels and overlays on show |
| `tip`, `status` | The tip and status line on screen |
| `objective` | `{number, title, progress, completed}`: the current objective |
| `player.speed` | Walking speed in world units a second (`walkto` sizes its steps by it) |
| `player.alive` | |
| `nearest` | Kind -> list of `{name, id, distance, bearing}`, closest first. `bearing` is degrees from where the player faces, -180 to 180, **+ to the right**. `walkto KIND` steers by it |

Anything else is the game's own: Beyond Nations adds the era, season,
inventory and world-event options; Kindling adds the HUD checklist, what the
crosshair is on and the restoration's numbers. `pt state` shows every
top-level field, compactly.

Example (Beyond Nations, abridged):

```json
{"wallTimeMs":1792642042971,"version":"0.4.1","screen":"WORLD","fps":13,"world":true,"tps":49.8,
 "openPanels":["chronicle-recent","tip"],"seed":42,"tick":1420,"era":"Camp",
 "player":{"x":117.63,"z":14.23,"yawDeg":64,"speed":25,"alive":true},
 "objective":{"number":1,"title":"Gather wood","progress":"Wood 4/10","completed":0},
 "nearest":{"tree":[{"name":"Tree","id":"8efc84cd","distance":2.5,"bearing":-8.1}],"rock":[]}}
```

## `events.jsonl`

One JSON object a line, **appended** as things happen, each with:

| Field | |
| --- | --- |
| `type` | lower_snake_case |
| `tick` | the world's tick when it happened (0 off the world) |
| `wallTimeMs` | Unix milliseconds |

Ticks never go backwards within one world; a `world` event starts a new one.
A session restarted with the same name keeps appending, so a save and load
round trip is one file.

Standard types (the checker enforces their fields; a game emits the ones that
apply to it):

| Type | Fields | |
| --- | --- | --- |
| `screen` | `from` (string or null), `to` | The screen changed. The first event a game writes has `from: null` |
| `world` | `how`: `created` or `loaded`; `seed` optional | A world was made or loaded. Objective timings run from the latest `created` |
| `objective_completed` | `title`; `number`, `id`, `ticksTaken` optional | The aggregator's objective timings come from these: tick / ticks per second is game seconds |
| `player_death` | `total` optional | Counted per session |
| `status` | `text` | Every new status line or message shown |
| `save` | `count` optional | A save was written |

Games add their own types freely (`chronicle`, `era_changed`,
`world_event_offered`, `pawn_death`, ...). `era_changed` and `stage_changed`
with a `to` field are shown as the "Reached" column in the summary.

## Checking an implementation

```bash
pt probe-check path/to/out                       # or, in a running session: pt probe-check
python3 -m playtester.probecheck path/to/out --require-world
python3 -m playtester.probecheck --events-only docs/playtests/1.2.0/s01/events.jsonl   # recorded evidence
```

It validates `state.json` and every line of `events.jsonl` against the
schemas and checks that ticks do not go backwards. Beyond Nations' recorded
events from a ten-session run and Kindling's headless autopilot output pass
it unchanged.

## Adding a probe to a game

1. Add the option. Create the directory if it does not exist.
2. Once a frame (or a tick), compare what is on screen with the last frame and
   append events for what changed.
3. Every 500 ms, write `state.json` through a temporary file and a rename
   (on Windows, remove the old file first or use a replace call).
4. Keep it out of the simulation: read only. A test that runs the same seed
   and inputs with and without the probe and compares the result is cheap
   insurance.
5. Put `probe` (`flag`, `ticks_per_second`) and, if the player walks around,
   `movement` and `nearest_kinds` in the game's profile ([PROFILES.md](PROFILES.md)).
6. Run `pt smoke` and `pt probe-check`.
