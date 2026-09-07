"""
Playtester - AI-powered game automation system

This package provides a framework for automating game play through AI decision-making
based on visual game state.
"""

__version__ = "0.1.0"

from .game_automator import GameAutomator
from .screenshot_capture import ScreenshotCapture
from .ai_decision_engine import AIDecisionEngine
from .action_executor import ActionExecutor

__all__ = [
    "GameAutomator",
    "ScreenshotCapture",
    "AIDecisionEngine",
    "ActionExecutor",
]
