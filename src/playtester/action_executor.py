"""
Action Executor Module

This module handles the execution of enumerated game actions by translating them
into actual inputs to the game application.

NOTE: Parts of this module are mocked. The actual input execution should be
customized based on the target game's input requirements.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import pyautogui
import time
from pynput.keyboard import Key, Controller as KeyboardController
from pynput.mouse import Button, Controller as MouseController

from .ai_decision_engine import GameAction


class ActionExecutor(ABC):
    """
    Abstract base class for executing game actions.
    
    Implementations should translate high-level GameAction enums into
    concrete inputs (keyboard, mouse, etc.) for the specific game.
    """
    
    def __init__(self, delay_between_actions: float = 0.5):
        """
        Initialize the action executor.
        
        Args:
            delay_between_actions: Time to wait between actions in seconds
        """
        self.delay_between_actions = delay_between_actions
        self.keyboard = KeyboardController()
        self.mouse = MouseController()
        self.action_count = 0
    
    @abstractmethod
    def execute_action(self, action: GameAction, 
                      action_params: Optional[Dict[str, Any]] = None) -> bool:
        """
        Execute a game action.
        
        Args:
            action: The GameAction enum to execute
            action_params: Optional parameters for the action
        
        Returns:
            True if action was executed successfully, False otherwise
        """
        pass
    
    def wait(self, duration: Optional[float] = None):
        """
        Wait for a specified duration or the default delay.
        
        Args:
            duration: Time to wait in seconds, uses default if None
        """
        time.sleep(duration if duration is not None else self.delay_between_actions)


class KeyboardActionExecutor(ActionExecutor):
    """
    Action executor using keyboard inputs.
    
    This is a generic implementation that maps GameActions to keyboard keys.
    Game-specific implementations should inherit and customize the key mappings.
    """
    
    def __init__(self, key_mapping: Optional[Dict[GameAction, str]] = None, 
                 delay_between_actions: float = 0.5):
        """
        Initialize keyboard action executor.
        
        Args:
            key_mapping: Dictionary mapping GameActions to keyboard keys
            delay_between_actions: Time to wait between actions
        """
        super().__init__(delay_between_actions)
        
        # Default key mapping (can be overridden)
        self.key_mapping = key_mapping or {
            GameAction.MOVE_UP: 'w',
            GameAction.MOVE_DOWN: 's',
            GameAction.MOVE_LEFT: 'a',
            GameAction.MOVE_RIGHT: 'd',
            GameAction.ACTION_PRIMARY: 'space',
            GameAction.ACTION_SECONDARY: 'e',
            GameAction.WAIT: None,
            GameAction.MENU: 'esc',
            GameAction.QUIT: 'q',
        }
    
    def execute_action(self, action: GameAction, 
                      action_params: Optional[Dict[str, Any]] = None) -> bool:
        """
        Execute action by pressing the corresponding key.
        
        Args:
            action: The GameAction to execute
            action_params: Optional parameters (e.g., hold_duration)
        
        Returns:
            True if action was executed
        """
        key = self.key_mapping.get(action)
        
        if key is None:
            # WAIT action or unmapped action
            self.wait()
            return True
        
        try:
            # Press and release the key
            pyautogui.press(key)
            self.action_count += 1
            self.wait()
            return True
        except Exception as e:
            print(f"Error executing action {action}: {e}")
            return False


class MockedActionExecutor(ActionExecutor):
    """
    Mocked action executor for testing without actual input.
    
    DESIRED BEHAVIOR (to be implemented for actual games):
    The actual implementation should:
    1. Identify the game window and bring it to focus
    2. Determine the input method (keyboard, mouse, gamepad, etc.)
    3. Translate GameActions to specific inputs based on game controls
    4. Handle edge cases (e.g., game not responding, window not found)
    5. Verify action execution if possible (e.g., check if game state changed)
    
    For games like Ophidian or Roam:
    - May need to detect game-specific UI elements
    - May need to perform mouse clicks on specific coordinates
    - May need to handle game menus and dialogs
    - Should respect game timing (e.g., turn-based vs real-time)
    """
    
    def __init__(self, delay_between_actions: float = 0.5):
        super().__init__(delay_between_actions)
        self.executed_actions = []
    
    def execute_action(self, action: GameAction, 
                      action_params: Optional[Dict[str, Any]] = None) -> bool:
        """
        Mock action execution - logs the action without performing it.
        
        ACTUAL IMPLEMENTATION SHOULD:
        - Focus the game window
        - Perform the actual input (keyboard/mouse/gamepad)
        - Verify the action was received by the game
        - Handle any errors or edge cases
        """
        self.executed_actions.append({
            'action': action,
            'params': action_params,
            'timestamp': time.time()
        })
        self.action_count += 1
        self.wait()
        return True
    
    def get_execution_history(self) -> list:
        """Get the history of executed actions (for testing/debugging)."""
        return self.executed_actions
