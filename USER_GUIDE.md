# User Guide

> **Scope:** this document covers the screenshot-driven **automation framework** (`GameAutomator`).
> For the **agent playtest kit** (the `pt` command, game profiles, the probe contract and report aggregation),
> see [docs/AGENT_PLAYTESTING.md](docs/AGENT_PLAYTESTING.md), [docs/PROFILES.md](docs/PROFILES.md) and
> [docs/PROBE_CONTRACT.md](docs/PROBE_CONTRACT.md).

This guide will help you get started with Playtester and understand how to use it for automating gameplay.

## Prerequisites

- Python 3.8 or higher
- A graphical desktop environment (X11, Wayland, Windows, or macOS)
- The game you want to automate

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/dmccoystephenson/playtester.git
   cd playtester
   ```

2. Install the package with the `automation` extra (pillow, pyautogui and
   pynput, which the automation framework needs):
   ```bash
   pip install -e ".[automation]"
   ```

## First Steps

### Running Your First Automation

The easiest way to get started is with the provided examples:

```bash
cd examples
python basic_example.py
```

This will run a basic automation loop for 5 cycles, demonstrating how the system captures screenshots, makes decisions, and executes actions.

### Understanding the Output

You'll see output like this:

```
Basic Game Automation Example
==================================================

Running 5 automation cycles...

Cycle 1:
  Action: MOVE_UP
  Confidence: 0.70
  Success: True

Cycle 2:
  Action: MOVE_DOWN
  Confidence: 0.70
  Success: True
...
```

Each cycle shows:
- The action the AI decided to take
- The confidence level (0.0 to 1.0)
- Whether the action was executed successfully

## Common Scenarios

### Scenario 1: Automating a Specific Game (Ophidian)

To automate the Ophidian game:

```python
from playtester.games import OphidianAutomator

# Create the automator with screenshot saving enabled
automator = OphidianAutomator(save_screenshots=True)

# Run for 100 decision cycles
automator.start(max_cycles=100)
```

Screenshots will be saved to `screenshots/ophidian/` for debugging.

### Scenario 2: Automating a Specific Game (Roam)

To automate the Roam game:

```python
from playtester.games import RoamAutomator

# Create the automator
automator = RoamAutomator(save_screenshots=True)

# Run for 50 cycles
automator.start(max_cycles=50)
```

### Scenario 3: Creating Custom Automation

For a custom game, you'll compose your own automation:

```python
from playtester import GameAutomator, ScreenshotCapture
from playtester.ai_decision_engine import MockedAIDecisionEngine, GameAction
from playtester.action_executor import KeyboardActionExecutor

# Setup screenshot capture
capture = ScreenshotCapture(save_screenshots=True, output_dir="screenshots/mygame")

# Define which actions the AI can choose from
available_actions = [
    GameAction.MOVE_UP,
    GameAction.MOVE_DOWN,
    GameAction.MOVE_LEFT,
    GameAction.MOVE_RIGHT,
    GameAction.ACTION_PRIMARY,
]

# Create AI decision engine
ai_engine = MockedAIDecisionEngine(available_actions)

# Create action executor with custom key mappings
executor = KeyboardActionExecutor({
    GameAction.MOVE_UP: 'w',
    GameAction.MOVE_DOWN: 's',
    GameAction.MOVE_LEFT: 'a',
    GameAction.MOVE_RIGHT: 'd',
    GameAction.ACTION_PRIMARY: 'space',
})

# Create the automator
automator = GameAutomator(
    capture=capture,
    decision_engine=ai_engine,
    executor=executor,
    loop_delay=1.0  # 1 second between cycles
)

# Set game context (optional information for the AI)
automator.set_game_context({
    'game': 'My Game',
    'objective': 'Complete level 1',
})

# Run the automation
for cycle_info in automator.run_continuous(max_cycles=20):
    print(f"Cycle {cycle_info['cycle']}: {cycle_info['action'].name}")
```

### Scenario 4: Capturing Specific Screen Region

If your game window doesn't fill the whole screen, capture only the game region:

```python
automator = OphidianAutomator()

# Define game window region (x, y, width, height)
game_region = (100, 100, 800, 600)

# Run with region specified
automator.start(max_cycles=50, region=game_region)
```

### Scenario 5: Stopping Automation Based on Condition

Create a custom stop condition:

```python
def should_stop():
    # Your custom logic here
    # For example, check if a file exists indicating game is over
    import os
    return os.path.exists('/tmp/game_finished.txt')

# Run with stop condition
for cycle in automator.run_continuous(stop_condition=should_stop):
    print(f"Running cycle {cycle['cycle']}...")
```

## Available Game Actions

The system uses enumerated `GameAction` values:

- `MOVE_UP` - Move character/cursor up
- `MOVE_DOWN` - Move character/cursor down
- `MOVE_LEFT` - Move character/cursor left
- `MOVE_RIGHT` - Move character/cursor right
- `ACTION_PRIMARY` - Primary action (attack, select, confirm)
- `ACTION_SECONDARY` - Secondary action (defend, cancel, back)
- `WAIT` - Wait/idle (do nothing)
- `MENU` - Open menu
- `QUIT` - Quit game

## Configuration Options

### Screenshot Capture

```python
capture = ScreenshotCapture(
    save_screenshots=True,  # Save screenshots to disk?
    output_dir="screenshots"  # Where to save them
)
```

### Action Executor

```python
# Keyboard executor with custom key mappings
executor = KeyboardActionExecutor(
    key_mapping={
        GameAction.MOVE_UP: 'w',
        GameAction.MOVE_DOWN: 's',
        # ... more mappings
    },
    delay_between_actions=0.5  # Seconds to wait between actions
)
```

### Game Automator

```python
automator = GameAutomator(
    capture,
    decision_engine,
    executor,
    loop_delay=1.0  # Seconds between automation cycles
)
```

## Troubleshooting

### "KeyError: 'DISPLAY'"

The system requires a graphical environment. Solutions:
- Run on a machine with a desktop environment
- Use a virtual display (Xvfb on Linux)
- Use remote desktop
- Run on your local machine instead of a headless server

### Actions Not Working in Game

1. Make sure the game window is in focus
2. Verify key mappings match your game's controls
3. Check that `delay_between_actions` is long enough for the game to process inputs
4. Try running with `save_screenshots=True` to see what the system is capturing

### Screenshots Are Black/Empty

1. Ensure the game is visible on screen
2. Try specifying a screen region instead of full screen
3. Check display permissions on your operating system

## Advanced Usage

For advanced features like integrating actual AI models, see:
- [Implementation Plan](docs/IMPLEMENTATION_PLAN.md) - Roadmap for AI integration
- [Architecture](docs/ARCHITECTURE.md) - System design
- [API Reference](docs/API_REFERENCE.md) - Complete API documentation

## Getting Help

- [GitHub Issues](https://github.com/dmccoystephenson/playtester/issues) - Bug reports and feature requests
- [Documentation](docs/README.md) - Complete documentation
- [Examples](examples/) - Working code examples
