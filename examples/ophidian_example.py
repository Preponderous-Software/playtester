#!/usr/bin/env python3
"""
Example: Ophidian Game Automation

This example demonstrates how to use the Ophidian-specific automator.
"""

import sys
import os

# Add src to path for development
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from playtester.games import OphidianAutomator


def main():
    """Run Ophidian automation example."""
    
    print("Ophidian Game Automation Example")
    print("=" * 50)
    print()
    print("This example demonstrates the Ophidian game automator.")
    print("Note: This is a mocked implementation for demonstration.")
    print()
    
    # Create the Ophidian automator
    automator = OphidianAutomator(save_screenshots=True)
    
    # Run for 10 cycles
    print("Starting automation for 10 cycles...\n")
    
    try:
        automator.start(max_cycles=10)
    except KeyboardInterrupt:
        print("\nStopping automation...")
        automator.stop()
    
    print("\nAutomation completed!")


if __name__ == '__main__':
    main()
