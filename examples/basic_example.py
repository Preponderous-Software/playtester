#!/usr/bin/env python3
"""
Example: Basic Game Automation

This example demonstrates the basic usage of the playtester framework
with the mocked AI decision engine.
"""

import sys
import os

# Add src to path for development
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from playtester import GameAutomator, ScreenshotCapture
from playtester.ai_decision_engine import MockedAIDecisionEngine, GameAction
from playtester.action_executor import MockedActionExecutor


def main():
    """Run a basic automation example."""
    
    print("Basic Game Automation Example")
    print("=" * 50)
    
    # Initialize components
    capture = ScreenshotCapture(save_screenshots=True, output_dir="screenshots/basic")
    
    # Define available actions for the game
    available_actions = [
        GameAction.MOVE_UP,
        GameAction.MOVE_DOWN,
        GameAction.MOVE_LEFT,
        GameAction.MOVE_RIGHT,
        GameAction.ACTION_PRIMARY,
    ]
    
    decision_engine = MockedAIDecisionEngine(available_actions)
    executor = MockedActionExecutor()
    
    # Create the automator
    automator = GameAutomator(
        capture=capture,
        decision_engine=decision_engine,
        executor=executor,
        loop_delay=0.5
    )
    
    # Set game context
    automator.set_game_context({
        'game': 'Example Game',
        'objective': 'Demonstrate automation',
    })
    
    # Run for 5 cycles
    print("\nRunning 5 automation cycles...\n")
    
    for cycle_info in automator.run_continuous(max_cycles=5):
        print(f"Cycle {cycle_info['cycle']}:")
        print(f"  Action: {cycle_info['action'].name}")
        print(f"  Confidence: {cycle_info['confidence']:.2f}")
        print(f"  Success: {cycle_info['success']}")
        print()
    
    # Get final statistics
    stats = automator.get_stats()
    print("Automation Statistics:")
    print(f"  Total cycles: {stats['total_cycles']}")
    print(f"  Actions executed: {stats['actions_executed']}")
    print(f"  Screenshots taken: {stats['screenshots_taken']}")
    
    # Show executed actions (mocked executor feature)
    print("\nExecuted Actions:")
    for action_record in executor.get_execution_history():
        print(f"  {action_record['action'].name} at {action_record['timestamp']:.2f}")


if __name__ == '__main__':
    main()
