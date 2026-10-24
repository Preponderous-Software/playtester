# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
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

### Fixed
- `GameAutomator.get_stats()` `screenshots_taken` counts every capture; it stayed `0` unless the `ScreenshotCapture` was created with `save_screenshots=True`
- `pt` reports a missing field in a profile or the game's probe output, and a flag without its value, as an error message instead of a traceback; so does `pt aggregate`
- Documentation: the shipped `/playtest` skill installs playtester from GitHub (it is not on PyPI); the README leads with the agent kit, a first run against the bundled demo game, and how to get and build the bundled games; dead GitHub Discussions links and the outdated SUMMARY.md were removed
- `Build` workflow: the import check now runs under Xvfb (it failed with `KeyError: 'DISPLAY'` on every run before); the job is now named `test`
- Documentation: the "testing without a display" instructions in QUICKSTART.md and CONTRIBUTING.md now say which modules need an X display (those that import pyautogui: `action_executor` and `screenshot_capture`, and so `game_automator` and `games`); the Error Handling section of docs/API_REFERENCE.md describes what the code actually does; `get_stats()` documents that `screenshots_taken` only counts saved screenshots; README.md and CONTRIBUTING.md describe the CI checks

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
