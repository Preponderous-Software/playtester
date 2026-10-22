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

### Changed
- `import playtester` no longer needs a display: the automation classes are loaded lazily on first use (`from playtester import GameAutomator` works as before)
- Alignment with DPC (Dans Plugins Community) conventions
- CONTRIBUTING.md with contribution guidelines
- USER_GUIDE.md with comprehensive usage instructions
- CHANGELOG.md for tracking changes
- LICENSE file (GPL-3.0)
- GitHub Actions workflows for CI/CD
- Copilot instructions for better AI assistance
- `ci/smoke_test.py`, run by the `Build` workflow under Xvfb: captures screenshots of a virtual screen and runs four mocked automation cycles
- CLAUDE.md with project context for Claude Code

### Fixed
- `Build` workflow: the import check now runs under Xvfb (it failed with `KeyError: 'DISPLAY'` on every run before); the job is now named `test`
- Documentation: the "testing without a display" instructions in QUICKSTART.md and CONTRIBUTING.md now say that importing `playtester` needs an X display (use `xvfb-run`); the Error Handling section of docs/API_REFERENCE.md describes what the code actually does; `get_stats()` documents that `screenshots_taken` only counts saved screenshots; README.md and CONTRIBUTING.md describe the CI checks

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
