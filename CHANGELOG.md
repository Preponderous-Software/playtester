# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Windows driver: a profile with `"driver": "windows"` plays a Windows game on the real desktop of the machine hosting WSL2. One PowerShell helper per session (`data/windows/pt_helper.ps1`, held by `harness/windows_relay.py`, reached over a TCP connection back to 127.0.0.1) brings the game's window to the front before every command, sends keys as scancodes with `SendInput` (`harness/windows_keys.py`; unknown names are errors), moves and clicks the real pointer, and captures the window from the screen, scaled to the profile's `window` size with clicks scaled back. `pt start --attach` drives a copy that is already running and `pt stop` leaves it running; otherwise `pt start` launches the game (pressing through its launcher), sets the profile's `windows.registry` values (`--module M` fills `{module}`) and `pt stop` closes the game and puts them back. A desktop lock (`~/.pt-windows-desktop.lock`, `PT_WINDOWS_LOCK`) lets one session at a time drive the desktop, refuses a second with the holder's name, and is taken over when stale
- Log probe (`harness/windows_log.py`): for a Windows-driver profile with `windows.log`, every `pt` command copies the lines the game's log gained into `game.log`, turns lines with `PTPROBE` (JSON or `TYPE key=value ...`) into `events.jsonl` and `PTPROBE state ...` lines into `state.json`, and lines matching `windows.log_error_patterns` into `log_error` events
- Probe lines (`harness/ptline.py`, `docs/PROBE_LINES.md`): a short, checked line format (`PT <kind> <seq> <numbers> <check digit>`) for games that can only show text, decoded into `state.json` and `events.jsonl` with duplicates (the same line in several screenshots) dropped by sequence number; shared test vectors in `tests/data/ptline_vectors.json`. `windows.probe_format: "ptline"` decodes them from the log too
- OCR probe (`harness/windows_ocr.py`): with `windows.ocr`, `pt start` runs a reader that captures a region of the game's window every 1.5 s, keeps one colour (the helper filters it), runs `tesseract` and feeds the lines to the probe; it writes `out/probe-lines.txt`, `out/ocr.log`, `out/ocr.json` and keeps the captures that gave new lines
- Windows driver: `pt look DX DY [--steps N]` turns a mouse-look game's view (on foot in Warband, where `pt move` sets an absolute pointer position the game ignores and `a`/`d` strafe): one helper request (`look`) of relative `SendInput` motions without `MOUSEEVENTF_ABSOLUTE`, none over 20 pixels by default and 10 ms apart, replacing one relay round trip per 120-pixel step. `--steps N` (1 to 1000) works with every driver: xdotool's `mousemove_relative` in N steps, or N motion events in one frame with the Strata driver
- `pt type --keys TEXT`: with the Windows driver, types letters, digits, space and US-keyboard punctuation as scancode key presses (helper op `strokes`; Shift for capitals and shifted symbols, 30 ms held, 50 ms apart), for text fields that ignore unicode events (Warband's name fields); other characters still go as unicode events, in order. The X11 and Strata drivers type as `pt type` does
- Launcher focus: the helper's `focus` taps Alt and attaches to the window's thread when `SetForegroundWindow` alone is refused, and `windows.launcher.click` clicks the launcher's start button when it still will not come to the front
- Profile `warband`: Mount&Blade: Warband and its modules on the Windows driver, with agent notes (map travel by clicking, click-to-pick/click-to-drop inventory, Escape menus), probe lines read off the screen (`probe_format: "ptline"`, `ocr`) and `rgl_log.txt` errors after exit, the launcher's module set through the registry, and a smoke script (`pt smoke --attach`)
- `pt ghosts RUN...`: recorded sessions drawn as fading coloured trails over a ground sized to the runs, one colour a session, with markers where players died, stalled (`--stall-secs`, `--stall-radius`) and where each session ended; a still PNG, or a GIF or MP4 that replays the runs side by side. Rendered headless with the Strata engine through its Python binding, which stays optional (`playtester.ghosts`; docs/AGENT_PLAYTESTING.md#ghost-trails)
- `track.jsonl` in each session: the player's `x` and `z` from `state.json`, appended whenever `pt` reads it, so a game with a probe has a track with no change to the game
- Probe contract: any event may carry `x` and `z` (optional) to say where it happened
- Strata driver (Preponderous RFC 0027): a profile with `"driver": "strata"` runs a game on the Strata engine (ABI 1.12 or later) headless, with no Xvfb, xdotool or ImageMagick. `pt start` starts a per-session relay that listens on `drive.sock` (mode 0600) and the game connects to it through Strata's drive channel (`STRATA_DRIVE`); every `pt` command keeps its name and meaning, with keys mapped to USB HID scancodes (`harness/strata_keys.py`, unknown names are errors), exact relative `look`, engine screenshots, and `drive.jsonl` recording every line sent to the game. `pt stop` asks the game to quit before signalling it
- `pt start --clock free|stepped [--step SECS]` and `pt step N`: with the stepped clock the game waits for the harness between frames, so `wait`, `hold`, `await`, `face` and `walkto` run in game time and two runs of the same build, seed and commands give the same frames; `pt smoke --clock stepped` runs a profile's smoke script that way. The default clock is `free` (real time, as before)
- Profiles `kindling-strata`, `atman-strata`, `steading-strata`, `orrery-strata` and `sisyphus-strata`, beside the X11 `kindling` profile; `driver` in the profile schema (`window.title_regex` is required only for `x11`)
- `examples/strata_driver_demo.py`: records a stepped session twice and writes a GIF, a contact sheet and a run-against-run difference image; evidence for Kindling, Atman and orrery in `docs/playtests/0.2.0/strata-driver/`
- Agent playtest kit (0.2.0): parallel AI agents play a real game headless and report; `pt` / `playtester` command (`python -m playtester`) with isolated sessions (own Xvfb display claimed under a lock, own data directory, every command logged), input (keys, holds, clicks with hover, drags, relative mouse, typing), window screenshots, notes, and probe commands (`state`, `events`, `await`, closed-loop `face` and `walkto`)
- Game profiles (JSON): `beyond-nations`, `kindling` and `demo`, with launch templates, probe and movement settings, agent notes, smoke scripts and default goals (docs/PROFILES.md)
- Probe contract for games: `state.json` and `events.jsonl` schemas and `pt probe-check` (docs/PROBE_CONTRACT.md)
- Agent prompt template (`pt prompt`), report schema and validator (`pt report`), run aggregator (`pt aggregate`) with improved near-duplicate grouping, resource measurement (`pt measure`), profile-driven smoke runner (`pt smoke`)
- Coordinator skill for Claude Code (`pt install-skill`)
- `playtester.demo`: a tiny X11 game implementing the probe, used by the end-to-end tests
- Unit and end-to-end test suite (`tests/`), run in CI
- CONTRIBUTING.md with contribution guidelines
- USER_GUIDE.md with comprehensive usage instructions
- CHANGELOG.md for tracking changes
- GitHub Actions workflows for CI/CD
- Copilot instructions for AI assistants
- `ci/smoke_test.py`, run by the `Build` workflow under Xvfb: captures screenshots of a virtual screen and runs four mocked automation cycles
- CLAUDE.md with project context for Claude Code
- CODE_OF_CONDUCT.md (Contributor Covenant 2.1), SECURITY.md, issue templates and a pull request template
- `pyproject.toml` declaring the setuptools build backend, and `MANIFEST.in` so the source distribution includes the whole test suite
- `atman` profile: Atman, a first-person game about Advaita Vedanta on Strata, played from screenshots (no probe) at the game's own 1280x720, with agent notes, a smoke script, three default goals and two questions about what the game taught
- Profile `questions`: questions every agent answers at the end of a session; the prompt lists them, `report.json` carries `answers`, `pt report` and `pt aggregate` flag a missing answer, and `summary.md` / `summary.json` gather the answers by question
- `pt smoke --keep` leaves the smoke session running for inspection (it was accepted and ignored before)
- `pt start` warns when the game's build is older than the checkout's HEAD commit or an uncommitted edit to a tracked file, and records `dirty`, `builtAtMs` and `buildWarnings` in `session.json`; profile `build.artifact` names the built file to check (the `beyond-nations` profile names its `.dll`)

### Changed
- Relicensed from GPL-3.0 to MIT
- `import playtester` no longer needs a display: the automation classes are loaded lazily on first use (`from playtester import GameAutomator` works as before)
- Installing playtester no longer installs any Python packages: the agent playtest kit is standard-library Python. pillow, pyautogui and pynput, needed only by the experimental screenshot automation framework, moved to the `automation` extra (`pip install -e ".[automation]"`); using an automation class without it raises an `ImportError` that names the extra. The empty `headless` extra was removed
- `pt smoke` runs in its own session (`smoke-<pid>` unless `--session` names one) instead of `$PT_SESSION`, refuses to touch a session of that name that is already running, and stops only a session it started
- Pid files record each process's start time; `pt stop` (and every check of whether a session is running) signals a pid only while it still belongs to the process the session started, so a stale pid file never signals an unrelated process
- `sisyphus-strata` agent notes follow Sisyphus 0.2.0 and 0.3.0: the game starts in first person, V is a view from straight behind, F (held) refactors and Tab shows the climb history, with notes on module dependencies, stamina, cairns, contributors, the rewrite at the summit and the weather

### Fixed
- `GameAutomator.run_continuous(max_cycles=0)`, and so `RoamAutomator.start(max_cycles=0)` and `OphidianAutomator.start(max_cycles=0)`, run no cycles; `0` used to be treated like `None` and the loop ran without limit. Only `None` means no limit
- `pt key` and `pt hold`: a `+` at the end of a combo is the plus key (`Control_L++` used to press Control alone and report success), on both drivers; any other combo with a key missing (`Shift_L+`, `+w`, an empty combo) is refused before a key goes down
- `pt walkto` no longer reports `stuck: not getting closer` for a `nearest` entry with no `id` while the distance is falling; without an `id`, a jump in distance of more than `stop_distance` counts as a new target
- `GameAutomator.get_stats()` `screenshots_taken` counts every capture; it stayed `0` unless the `ScreenshotCapture` was created with `save_screenshots=True`
- `pt` reports a missing field in a profile or the game's probe output, and a flag without its value, as an error message instead of a traceback; so does `pt aggregate`
- Documentation: the shipped `/playtest` skill installs playtester from GitHub (it is not on PyPI); the README leads with the agent kit, a first run against the bundled demo game, and how to get and build the bundled games; dead GitHub Discussions links and the outdated SUMMARY.md were removed
- `Build` workflow: the import check now runs under Xvfb (it failed with `KeyError: 'DISPLAY'` on every run before); the job is now named `test`
- Documentation: the "testing without a display" instructions in QUICKSTART.md and CONTRIBUTING.md now say which modules need an X display (those that import pyautogui: `action_executor` and `screenshot_capture`, and so `game_automator` and `games`); the Error Handling section of docs/API_REFERENCE.md describes what the code actually does; `get_stats()` documents that `screenshots_taken` only counts saved screenshots; README.md and CONTRIBUTING.md describe the CI checks
- Documentation: the Strata driver is described where it was missing; the README's Bundled games names the `-strata` profiles, docs/AGENT_PLAYTESTING.md's command table has `pt start --width/--height/--clock/--step`, `pt step N` and the Strata-driver session files, and `pt help` shows `pt smoke --clock`
- Documentation: docs/API_REFERENCE.md no longer says `import playtester` imports pyautogui (the automation classes load lazily) and lists Pillow, PyAutoGUI and pynput as the `automation` extra; docs/README.md and docs/ARCHITECTURE.md no longer suggest subclassing `GameAction` to add actions (Python raises `TypeError` for an enum that has members), and docs/README.md's custom-automator steps now run as written (the engine passes its actions to `super().__init__`, `execute_action` takes `action_params=None`); QUICKSTART.md's missing-PIL fix installs the `automation` extra

## [0.1.0] - 2025-12-28

### Added
- Initial release of Playtester framework
- Screenshot capture system with full screen and region support
- AI decision engine interface with GameAction enumeration
- MockedAIDecisionEngine for testing and demonstration
- Action executor system with keyboard support
- KeyboardActionExecutor with configurable key mappings
- MockedActionExecutor for testing without actual input
- Game automator orchestrating the automation loop
- Ophidian game-specific automator (mocked implementation)
- Roam game-specific automator (mocked implementation)
- Comprehensive documentation suite
  - README.md with project overview
  - docs/README.md with full usage guide
  - docs/API_REFERENCE.md with complete API documentation
  - docs/IMPLEMENTATION_PLAN.md with future roadmap
  - docs/ARCHITECTURE.md with system design diagrams
- Example scripts demonstrating framework usage
  - basic_example.py - Basic automation demo
  - ophidian_example.py - Ophidian game automation
  - roam_example.py - Roam game automation
- Python package setup with setup.py
- Dependencies: pillow, pyautogui, pynput

### Documented
- Desired behavior for AI integration with open-source models (LLaVA, CLIP, MiniGPT-4, OpenFlamingo)
- Game-specific implementation patterns
- Extensibility points for custom games and AI engines
