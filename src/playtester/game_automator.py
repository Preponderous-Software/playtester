"""
Game Automator Module

This is the main orchestrator that integrates all components to automate game play.
"""

from typing import Optional, Dict, Any, Callable
import time
from PIL import Image

from .screenshot_capture import ScreenshotCapture
from .ai_decision_engine import AIDecisionEngine, GameAction
from .action_executor import ActionExecutor


class GameAutomator:
    """
    Main orchestrator for AI-powered game automation.
    
    This class coordinates the screenshot capture, AI decision making, and
    action execution to create an automated game playing system.
    """
    
    def __init__(self, 
                 capture: ScreenshotCapture,
                 decision_engine: AIDecisionEngine,
                 executor: ActionExecutor,
                 loop_delay: float = 1.0):
        """
        Initialize the game automator.
        
        Args:
            capture: Screenshot capture instance
            decision_engine: AI decision engine instance
            executor: Action executor instance
            loop_delay: Time to wait between automation cycles
        """
        self.capture = capture
        self.decision_engine = decision_engine
        self.executor = executor
        self.loop_delay = loop_delay
        self.is_running = False
        self.cycle_count = 0
        self.game_context = {}
    
    def set_game_context(self, context: Dict[str, Any]):
        """
        Set or update the game context.
        
        Args:
            context: Dictionary containing game-specific context information
        """
        self.game_context.update(context)
    
    def run_single_cycle(self, region: Optional[tuple] = None) -> Dict[str, Any]:
        """
        Run a single automation cycle.
        
        This consists of:
        1. Capture screenshot
        2. AI analyzes and decides action
        3. Execute the action
        
        Args:
            region: Optional (x, y, width, height) tuple to capture specific region
        
        Returns:
            Dictionary containing cycle information
        """
        # Capture screenshot
        if region:
            screenshot = self.capture.capture_region(*region)
        else:
            screenshot = self.capture.capture_full_screen()
        
        # AI decides action
        action = self.decision_engine.analyze_and_decide(screenshot, self.game_context)
        confidence = self.decision_engine.get_decision_confidence()
        
        # Execute action
        success = self.executor.execute_action(action)
        
        self.cycle_count += 1
        
        return {
            'cycle': self.cycle_count,
            'action': action,
            'confidence': confidence,
            'success': success,
            'timestamp': time.time()
        }
    
    def run_continuous(self, 
                      max_cycles: Optional[int] = None,
                      stop_condition: Optional[Callable[[], bool]] = None,
                      region: Optional[tuple] = None):
        """
        Run continuous automation loop.
        
        Args:
            max_cycles: Maximum number of cycles to run (None for infinite)
            stop_condition: Optional function that returns True to stop
            region: Optional region to capture
        
        Yields:
            Dictionary containing cycle information for each iteration
        """
        self.is_running = True
        cycle = 0
        
        while self.is_running:
            if max_cycles and cycle >= max_cycles:
                break
            
            if stop_condition and stop_condition():
                break
            
            cycle_info = self.run_single_cycle(region)
            yield cycle_info
            
            time.sleep(self.loop_delay)
            cycle += 1
    
    def stop(self):
        """Stop the continuous automation loop."""
        self.is_running = False
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the automation session.
        
        Returns:
            Dictionary containing statistics
        """
        return {
            'total_cycles': self.cycle_count,
            'actions_executed': self.executor.action_count,
            'screenshots_taken': self.capture.screenshot_count,
        }
