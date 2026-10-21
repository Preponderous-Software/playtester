# CLAUDE.md

## Project overview

Playtester is a Python framework for automating game play: it captures
screenshots of a running game, passes them to an AI decision engine, and
executes the chosen action (keyboard/mouse) back into the game. The AI layer
is currently **mocked** (`MockedAIDecisionEngine`, `MockedActionExecutor`);
integrating a real vision-language model is roadmap work described in
`docs/IMPLEMENTATION_PLAN.md`.

## Technology stack

- Python >= 3.8 (`setup.py` `python_requires`; CI pins 3.8)
- `pillow>=10.0.0`, `pyautogui>=0.9.54`, `pynput>=1.7.6` (`requirements.txt`, mirrored in `setup.py` `install_requires`)
- setuptools, `src/` layout (`package_dir={"": "src"}`)
- GitHub Actions: `.github/workflows/build.yml` (push to main/develop/copilot/**, PRs to main/develop), `.github/workflows/release.yml` (on release created, `python -m build`)

## Build and run commands

```bash
pip install -r requirements.txt
pip install -e .

# Example scripts (need a real display: X11, Wayland, Windows or macOS)
cd examples
python basic_example.py      # also roam_example.py, ophidian_example.py
```

On this machine bare `python` is Python 2; use `python3` (3.8) explicitly.

## Test commands

There is no automated test suite (no `tests/`, no pytest config). The checks
CI runs are:

```bash
python3 -m py_compile src/playtester/*.py src/playtester/games/*.py examples/*.py
python3 -c "import playtester; print('Playtester imported successfully')"
```

**Headless caveat:** `import playtester` imports `pyautogui`, whose
`mouseinfo` dependency reads `os.environ['DISPLAY']` at import time. Without a
display the import fails with `KeyError: 'DISPLAY'`. This is why the Build
workflow's "Verify installation" step currently fails on `main` (GitHub's
`ubuntu-latest` runner has no display). `py_compile` works headless.

`CONTRIBUTING.md` documents a manual headless check that imports the
submodules directly (`playtester.ai_decision_engine`, `playtester.action_executor`)
with `sys.path.insert(0, 'src')`; note that `action_executor` also imports
`pyautogui`, so it needs a display too.

## Lint and format

No linter or formatter is configured. `CONTRIBUTING.md` asks for PEP 8.

## Repository layout

```
src/playtester/
  __init__.py              Public API: GameAutomator, ScreenshotCapture, AIDecisionEngine, ActionExecutor; __version__
  game_automator.py        Orchestrates capture -> decide -> execute cycles (run_single_cycle, run_continuous, stats)
  screenshot_capture.py    pyautogui/Pillow screenshot capture, optional saving to disk
  ai_decision_engine.py    GameAction enum, AIDecisionEngine ABC, MockedAIDecisionEngine
  action_executor.py       ActionExecutor ABC, KeyboardActionExecutor (pynput), MockedActionExecutor
  games/                   Per-game presets: roam.py (RoamAutomator), ophidian.py (OphidianAutomator)
examples/                  Runnable scripts: basic, roam, ophidian
docs/                      API_REFERENCE.md, ARCHITECTURE.md, IMPLEMENTATION_PLAN.md, README.md
README.md, USER_GUIDE.md, QUICKSTART.md, SUMMARY.md, CHANGELOG.md, CONTRIBUTING.md
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
- Keep `requirements.txt` and `setup.py` `install_requires` in sync.
- Run the `py_compile` check before pushing.

**Don't:**
- Don't claim a real AI model is integrated; the engines are mocked.
- Don't run the example scripts against a real desktop unattended: the
  keyboard executor sends real key presses to whatever window has focus.
- Don't commit `screenshots/` output or other generated artefacts.
