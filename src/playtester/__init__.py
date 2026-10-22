"""
Playtester - game playtesting by AI agents, and an AI game automation framework

Two ways to play a game:

- the agent playtest kit (``playtester.harness``, the ``pt`` command, and
  ``playtester.agents``): AI agents such as Claude Code subagents play the
  real game headless in isolated sessions, report what they find, and the
  reports are aggregated into one summary;
- the automation loop (``GameAutomator``): screenshot -> decision engine
  (mocked) -> keyboard executor.

The automation classes import pyautogui, which needs a display at import
time, so they are loaded lazily: ``import playtester`` and the harness work
on a headless machine, and ``from playtester import GameAutomator`` still
works where there is a display.
"""

__version__ = "0.2.0"

__all__ = [
    "GameAutomator",
    "ScreenshotCapture",
    "AIDecisionEngine",
    "ActionExecutor",
]

_LAZY = {
    "GameAutomator": ".game_automator",
    "ScreenshotCapture": ".screenshot_capture",
    "AIDecisionEngine": ".ai_decision_engine",
    "ActionExecutor": ".action_executor",
}


def __getattr__(name):
    if name in _LAZY:
        import importlib
        value = getattr(importlib.import_module(_LAZY[name], __name__), name)
        globals()[name] = value
        return value
    raise AttributeError("module %r has no attribute %r" % (__name__, name))


def __dir__():
    return sorted(list(globals()) + list(_LAZY))
