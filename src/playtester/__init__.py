"""
Playtester - game playtesting by AI agents, and an AI game automation framework

Two ways to play a game:

- the agent playtest kit (``playtester.harness``, the ``pt`` command, and
  ``playtester.agents``): AI agents such as Claude Code subagents play the
  real game headless in isolated sessions, report what they find, and the
  reports are aggregated into one summary;
- the automation loop (``GameAutomator``): screenshot -> decision engine
  (mocked) -> keyboard executor.

The automation framework is experimental and its decision engine is mocked.
Its classes need the ``automation`` extra (``pip install "playtester[automation]"``:
pillow, pyautogui, pynput), and pyautogui needs a display at import time, so
they are loaded lazily: ``import playtester`` and the harness work on a
headless machine with no third-party packages, and
``from playtester import GameAutomator`` works where the extra is installed
and there is a display.
"""

__version__ = "0.2.0"

__all__ = [
    "GameAutomator",
    "ScreenshotCapture",
    "AIDecisionEngine",
    "ActionExecutor",
]

_AUTOMATION_PACKAGES = ("PIL", "pyautogui", "pynput")

_LAZY = {
    "GameAutomator": ".game_automator",
    "ScreenshotCapture": ".screenshot_capture",
    "AIDecisionEngine": ".ai_decision_engine",
    "ActionExecutor": ".action_executor",
}


def __getattr__(name):
    if name in _LAZY:
        import importlib
        try:
            module = importlib.import_module(_LAZY[name], __name__)
        except ImportError as e:
            missing = (getattr(e, "name", None) or "").split(".")[0]
            if missing in _AUTOMATION_PACKAGES:
                raise ImportError(
                    "playtester.%s needs the automation extra (missing %s): "
                    'pip install "playtester[automation] @ git+https://github.com/dmccoystephenson/playtester", '
                    'or pip install -e ".[automation]" in a checkout' % (name, missing),
                    name=missing) from e
            raise
        value = getattr(module, name)
        globals()[name] = value
        return value
    raise AttributeError("module %r has no attribute %r" % (__name__, name))


def __dir__():
    return sorted(list(globals()) + list(_LAZY))
