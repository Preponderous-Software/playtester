# CLAUDE.md

## Project overview

Playtester has two independent parts:

- **The agent playtest kit** (`playtester.harness`, `playtester.agents`, the
  `pt` command): AI agents (Claude Code subagents) play a real game headless in
  isolated Xvfb sessions, driven through `pt`, and write reports that `pt
  aggregate` merges. Games are described by JSON profiles
  (`src/playtester/data/profiles/`) and may implement the optional probe
  (`docs/PROBE_CONTRACT.md`). Docs: `docs/AGENT_PLAYTESTING.md`,
  `docs/PROFILES.md`.
- **The automation framework**: it captures screenshots of a running game,
  passes them to an AI decision engine, and executes the chosen action
  (keyboard/mouse) back into the game. The AI layer is currently **mocked**
  (`MockedAIDecisionEngine`, `MockedActionExecutor`); integrating a real
  vision-language model is roadmap work described in
  `docs/IMPLEMENTATION_PLAN.md`.

## Technology stack

- Python >= 3.8 (`setup.py` `python_requires`; CI pins 3.8)
- No runtime dependencies (`install_requires=[]`): the agent kit is standard-library Python
- The `automation` extra: `pillow>=10.0.0`, `pyautogui>=0.9.54`, `pynput>=1.7.6`
  (`setup.py` `extras_require["automation"]`, mirrored in `requirements.txt`)
- setuptools (`pyproject.toml` `[build-system]`, metadata in `setup.py`), `src/` layout (`package_dir={"": "src"}`)
- GitHub Actions: `.github/workflows/build.yml` (job `test`; push to main, every PR), `.github/workflows/release.yml` (on release created, `python -m build`)

## Build and run commands

```bash
pip install -e .                 # the agent kit: no Python dependencies
pip install -e ".[automation]"   # plus the automation framework's dependencies

# Example scripts (need a real display: X11, Wayland, Windows or macOS)
cd examples
python basic_example.py      # also roam_example.py, ophidian_example.py
```

Where bare `python` is not Python 3 (some systems still ship Python 2 under
that name), use `python3` explicitly.

## Test commands

```bash
python3 -m py_compile src/playtester/*.py src/playtester/*/*.py examples/*.py ci/*.py tests/*.py
python3 -m unittest discover -s tests -t .      # unit + end-to-end (stdlib unittest, no pytest)
PT_ROOT=/tmp/pt-smoke python3 -m playtester smoke --profile demo
xvfb-run -a python3 ci/smoke_test.py            # the automation framework, needs a display
```

`tests/test_ghosts.py` renders with Strata only when its Python binding and a
libstrata (`STRATA_LIBRARY`) are available, and skips those tests otherwise; CI
installs both in its own step.

`tests/test_harness_live.py` plays the bundled demo game (`playtester.demo`, a
ctypes/libX11 window) in real Xvfb sessions; it is skipped unless `Xvfb`,
`xdotool` and `import` are installed. The rest of `tests/` needs nothing. Run
the suite with Python 3.8 as well as a newer one.

**Headless:** `import playtester` no longer imports `pyautogui`: the
automation classes are loaded lazily by a module `__getattr__`. Importing
`GameAutomator`, `ScreenshotCapture`, `action_executor` or `games` still
pulls in `pyautogui`, whose `mouseinfo` dependency reads
`os.environ['DISPLAY']` at import time, so they need a display.
CI (job `test` in `build.yml`) installs `xvfb`, `xauth` and `scrot` and runs the
import check and `ci/smoke_test.py` under `xvfb-run` with
`XDG_SESSION_TYPE=x11`. Run them locally the same way; `py_compile` works headless.

`CONTRIBUTING.md` documents a manual headless check that imports the
submodules directly (`playtester.ai_decision_engine`, `playtester.action_executor`)
with `sys.path.insert(0, 'src')`; note that `action_executor` also imports
`pyautogui`, so it needs a display too.

## Lint and format

No linter or formatter is configured. `CONTRIBUTING.md` asks for PEP 8.

## Repository layout

```
src/playtester/
  __init__.py              __version__; lazy GameAutomator, ScreenshotCapture, AIDecisionEngine, ActionExecutor
  __main__.py              python -m playtester == pt
  harness/                 Agent kit: cli.py (pt), session.py (Xvfb/game lifecycle, display lock), xdo.py (input),
                           probe.py (state/events, face, walkto), profile.py, smoke.py, measure.py
  agents/                  prompt.py (pt prompt), report.py (pt report), aggregate.py (pt aggregate)
  schema.py, probecheck.py Mini JSON Schema validator; probe contract checker
  ghosts.py                pt ghosts: runs' track.jsonl as fading trails, rendered with Strata (optional binding)
  demo.py                  Tiny libX11 game implementing the probe (end-to-end tests)
  data/                    profiles/*.json + *.md, schemas/*.json, prompts/AGENT_PROMPT.md, skills/playtest/SKILL.md
  game_automator.py        Orchestrates capture -> decide -> execute cycles (run_single_cycle, run_continuous, stats)
  screenshot_capture.py    pyautogui/Pillow screenshot capture, optional saving to disk
  ai_decision_engine.py    GameAction enum, AIDecisionEngine ABC, MockedAIDecisionEngine
  action_executor.py       ActionExecutor ABC, KeyboardActionExecutor (pynput), MockedActionExecutor
  games/                   Per-game presets: roam.py (RoamAutomator), ophidian.py (OphidianAutomator)
examples/                  Runnable scripts: basic, roam, ophidian
tests/                     unittest suite; fixtures/run is a recorded three-session run
docs/                      AGENT_PLAYTESTING.md, PROFILES.md, PROBE_CONTRACT.md, API_REFERENCE.md, ARCHITECTURE.md, IMPLEMENTATION_PLAN.md, README.md
README.md, USER_GUIDE.md, QUICKSTART.md, CHANGELOG.md, CONTRIBUTING.md, CODE_OF_CONDUCT.md, SECURITY.md
```

## Architecture notes

- Three pluggable seams, each an ABC with a mocked implementation:
  capture (`ScreenshotCapture`), decide (`AIDecisionEngine.analyze_and_decide`),
  act (`ActionExecutor.execute_action`). `GameAutomator` wires them together.
- Game actions are the `GameAction` enum; a game preset picks its subset of
  actions and a key mapping.
- Adding a game = a new module under `src/playtester/games/` with an AI
  engine subclass, an executor subclass and an `<Game>Automator` convenience
  class, following `roam.py` / `ophidian.py`, plus an export in
  `games/__init__.py` and an example script.
- The agent kit is standard-library only (it shells out to Xvfb, xdotool and
  ImageMagick). Keep it that way: it must run where the automation
  dependencies cannot be imported.
- Adding a game to the agent kit = a profile JSON plus an agent-notes
  Markdown file in `data/profiles/`, a smoke script that passes, and the name
  in `tests/test_profiles.py` (docs/PROFILES.md).

## Coding conventions

- PEP 8; snake_case functions/modules, PascalCase classes.
- Docstrings on all public classes and methods; type hints from `typing`
  (`Optional`, `Dict`, `List`, ...).
- Keep code Python 3.8 compatible (CI uses 3.8): no `match`, no `X | Y`
  type unions, no built-in generic annotations like `list[str]`.

## Do / Don't

**Do:**
- Branch from `main` (`feature/<name>`); PRs target `main`.
- Update `README.md` / `docs/API_REFERENCE.md` / `docs/IMPLEMENTATION_PLAN.md`
  when public behaviour or the API changes (per `CONTRIBUTING.md`), and add a
  `CHANGELOG.md` entry.
- Keep `requirements.txt` and `setup.py` `extras_require["automation"]` in sync;
  keep `install_requires` empty.
- Run the `py_compile` check before pushing.

**Don't:**
- Don't claim a real AI model is integrated; the engines are mocked.
- Don't run the example scripts against a real desktop unattended: the
  keyboard executor sends real key presses to whatever window has focus.
- Don't commit `screenshots/` output or other generated artefacts (test fixture PNGs under `tests/fixtures/` are the exception).
- Don't `pkill -f` a pattern that matches your own shell when cleaning up sessions; use `pt stop` per session.
