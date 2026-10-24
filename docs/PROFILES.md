# Game profiles

A profile tells the harness how to build, start, see and steer one game. It
is a JSON file (standard library only); the bundled ones are in
[`src/playtester/data/profiles/`](../src/playtester/data/profiles/), and
`pt start --profile PATH` takes any other file. `pt validate-profile PATH`
checks one against [`profile.schema.json`](../src/playtester/data/schemas/profile.schema.json).

| Profile | Game | Probe |
| --- | --- | --- |
| `beyond-nations` | Beyond Nations, a 3D colony-and-nations game (.NET, Dear ImGui) | `--playtest-out` |
| `kindling` | Kindling, a cozy first-person homestead game on Strata (C++) | `--playtest-out` |
| `atman` | Atman, a first-person game about Advaita Vedanta on Strata (C++) | none (screenshots only); asks `questions` |
| `demo` | the tiny test game in `playtester.demo` | `--playtest-out` |
| `kindling-strata` | Kindling on the Strata driver (headless, no X server) | `--playtest-out` |
| `atman-strata` | Atman on the Strata driver (headless, no X server) | none; asks `questions` |
| `steading-strata` | steading, a colony simulation on Strata, on the Strata driver | none |
| `orrery-strata` | orrery, the solar system from JPL data on Strata, on the Strata driver | none |

The `-strata` profiles drive the game through Strata's drive channel instead
of Xvfb and xdotool ([below](#drivers)). `kindling` and `kindling-strata` are
the same game with the same smoke script, kept side by side so the two
drivers can be compared.

## Fields

| Field | Required | |
| --- | --- | --- |
| `name` | yes | lower-case-with-dashes; the bundled file name |
| `title` | yes | The game's name, as agents call it |
| `description` | yes | One phrase agents read first ("a 3D colony-and-nations game: ...") |
| `repository` | | `owner/name`, for issues and evidence |
| `driver` | | `x11` (default) or `strata`; see [Drivers](#drivers) |
| `build.command` | | Shell command run in the game's checkout that builds what `launch.command` runs |
| `build.requires` | | The toolchain the build needs, a list of commands (e.g. `["dotnet"]`); `pt validate-profile` prints it |
| `build.artifact` | | The built file whose modification time is the build's time, with the `launch` placeholders (default `launch.command[0]` when it is inside the game's checkout). `pt start` warns when it is older than the checkout's HEAD commit or an uncommitted edit |
| `launch.command` | yes | The executable and fixed arguments, a list |
| `launch.args` | | More arguments, always passed (window size, data directory) |
| `launch.cwd` | | Working directory (default the session directory) |
| `launch.env` | | Environment variables to set |
| `launch.env_defaults` | | Set only when unset and the value is an existing path (e.g. `DOTNET_ROOT`) |
| `launch.seed_args` | | Passed when `pt start --seed S` is given; `{seed}` is S |
| `launch.quick_world_args` | | Arguments that start straight in a world, for `pt measure` |
| `launch.start_timeout_sec` | | How long `start` waits for the window (default 90) |
| `launch.settle_sec` | | Wait this long after the window appears (games whose first frames are blank) |
| `launch.lp_threads` | | llvmpipe threads per game unless `PT_LP_THREADS` is set (default 2) |
| `window.title_regex` | x11 only | `xdotool search --name` pattern for the game's window (not used by the Strata driver) |
| `window.width`, `window.height` | | Window size (default 960x540); `PT_WIDTH`/`PT_HEIGHT` override |
| `probe` | | `null` (screenshots only) or `{flag, ticks_per_second, world_screens, screens, since}`; see [PROBE_CONTRACT.md](PROBE_CONTRACT.md) |
| `movement` | | For `face` and `walkto` (needs a probe); below |
| `crash_patterns` | | Regular expressions that mark a crash in `game.log`; the aggregator turns a match into a blocker finding |
| `process_name` | | What `pgrep -f` matches for a running game, for the coordinator's cleanup check |
| `agent_notes` | | A Markdown file beside the profile: controls, how to get into the game, practical notes. It is pasted into every agent's prompt |
| `cheats` | | What agents must not press or pass unless their goal says so |
| `smoke` | | The scripted check `pt smoke` runs; below |
| `goals` | | Default goals: `{goal, budget_min, seed, args}`; `pt prompt --goal-index N` uses them |
| `questions` | | Questions every agent answers at the end of its session, in its own words (for example, what the game seemed to be about). The prompt lists them, the report carries the answers (`answers`: `{question, answer}`), `pt report` refuses a report that leaves one out, and `pt aggregate` puts every agent's answer side by side under each question in the summary |
| `evidence_dir` | | Where in the game's repository evidence is committed (default `docs/playtests`) |

Placeholders in `launch` strings: `{game_dir}` (the checkout: `--game-dir`,
`PT_GAME_DIR` or the current directory), `{session_dir}`, `{data_dir}`
(`<session>/data`: point the game's saves and settings here so sessions never
share them), `{probe_dir}` (`<session>/out`), `{width}`, `{height}`,
`{python}` (the harness's interpreter), and `{seed}` in `seed_args`.

### `movement`

| Field | |
| --- | --- |
| `turn` | `{"method": "keys", "left": "a", "right": "d", "degrees_per_second": 100}` or `{"method": "mouse", "pixels_per_degree": 7}`. Keys are better when the game has them: a key held for a time turns by the same amount at any frame rate, while relative mouse motion through a virtual X server is clamped at the window's edge |
| `yaw_increases` | `left` or `right`: which way `player.yawDeg` grows |
| `forward_key` | Default `w` |
| `speed_field`, `default_speed` | The player field with the walking speed, and the speed if it is missing |
| `interact_key`, `interact_range` | Shown in `walkto`'s result |
| `stop_distance` | `walkto` stops closer than this |
| `face_tolerance` | Degrees `face` accepts as done (default 8) |
| `nearest_kinds` | The kinds of `nearest` agents may `walkto` |

### `smoke`

A script of `pt` commands, run by `pt smoke` after starting the game with
`smoke.seed` and `smoke.args`:

```json
"smoke": {
  "seed": 42,
  "steps": [["await", "TITLE", "30"], ["key", "space"], ["await", "WORLD", "30"], ["shot", "02-world"]],
  "until": {
    "event": {"type": "objective_completed", "title": "Gather wood"},
    "attempts": 10,
    "steps": [["walkto", "tree", "60"], ["key", "e"], ["wait", "1.5"]],
    "may_fail": ["walkto"]
  }
}
```

Every step must succeed; then the `until` steps repeat until an event with
all of `event`'s fields appears in `events.jsonl` (a failing `may_fail`
command just ends that attempt). It prints `PASS` or `FAIL` with the log
tail and a `fail.png`. It runs in its own session (`smoke-<pid>` unless
`--session NAME` is given; `$PT_SESSION` is ignored), never touches a session
of that name that is already running, and stops the session it started when
it finishes, unless `--keep` asks it to leave the game running.

## Drivers

`driver` says how a session runs the game and reaches it.

- **`x11`** (the default): the game gets its own Xvfb display; input goes in
  through `xdotool` and screenshots come out through ImageMagick's `import`.
  Works for any game with a window.
- **`strata`**: for games on the [Strata](https://github.com/Preponderous-Software/strata)
  engine, built against ABI 1.12 or later. No X server, `xdotool` or
  ImageMagick: the game renders on a headless EGL surface and takes its input
  through Strata's drive channel (Strata `docs/DRIVE.md`). `pt start` starts a
  small relay that listens on `drive.sock` in the session directory (mode
  0600) and sets `STRATA_DRIVE` for the game, which connects to it; the game
  never listens on anything. Every `pt` command keeps its name and meaning:
  keys and mouse buttons become injected events (key names map to USB HID
  scancodes, and an unknown name is an error), `look DX DY` is one exact
  relative motion with no window edge to stop it, and `shot` asks the engine
  for the frame. `drive.jsonl` records every line sent to the game.

With the Strata driver, `pt start --clock stepped [--step SECS]` (default
step 1/60 s) makes the game wait for the harness between frames: `wait`,
`hold` and the closed-loop `await`, `face` and `walkto` run whole frames of
game time, and `pt step N` runs exactly N. The same build, seed and commands
then give the same frames, run after run, whatever the machine's load.
`--clock free` (the default) keeps today's behaviour: the game runs in real
time while the agent thinks. Games read the clock through Strata's
`frameSeconds()`, and a driven game does not write the player's saves
(each game's own change; see its log line "driven by a test harness").

## Adding a game

1. Write `<name>.json` and `<name>.md` (copy the demo's).
2. `pt validate-profile <name>.json`, then `pt start --profile <name>.json --game-dir ...`,
   `pt shot first` and look.
3. Add a smoke script and make `pt smoke` pass.
4. Optionally add a probe to the game ([PROBE_CONTRACT.md](PROBE_CONTRACT.md)),
   then `movement`.
5. To bundle it with playtester, put both files in
   `src/playtester/data/profiles/` and add the name to `tests/test_profiles.py`.
