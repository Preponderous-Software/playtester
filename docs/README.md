# Playtester - AI-Powered Game Automation System

## Overview

Besides the automation framework described here, playtester has an agent playtest kit: see [AGENT_PLAYTESTING.md](AGENT_PLAYTESTING.md), [PROFILES.md](PROFILES.md) and [PROBE_CONTRACT.md](PROBE_CONTRACT.md).

Playtester is a Python framework for automating game play using AI-powered decision making based on visual game state analysis. The system captures screenshots of game applications, feeds them to an AI decision engine, and executes corresponding game actions.

## Features

- **Screenshot Capture**: Capture full screen or specific regions for game state analysis
- **AI Decision Engine**: Analyze game state and make enumerated decisions (currently mocked with plans for open-source AI integration)
- **Action Execution**: Translate AI decisions into actual game inputs (keyboard, mouse)
- **Game-Specific Implementations**: Pre-configured automators for specific games (Ophidian, Roam)
- **Extensible Architecture**: Easy to add new games and customize behavior

## Architecture

The system consists of four main components:

### 1. Screenshot Capture (`ScreenshotCapture`)
Captures screenshots of the game application for analysis.

```python
from playtester import ScreenshotCapture

capture = ScreenshotCapture(save_screenshots=True, output_dir="screenshots")
screenshot = capture.capture_full_screen()
```

### 2. AI Decision Engine (`AIDecisionEngine`)
Analyzes screenshots and decides which action to take from a set of enumerated game actions.

**Current Status**: Mocked implementation  
**Planned Implementation**: Integration with open-source vision-language models (LLaVA, CLIP, etc.)

```python
from playtester.ai_decision_engine import MockedAIDecisionEngine, GameAction

decision_engine = MockedAIDecisionEngine([
    GameAction.MOVE_UP,
    GameAction.MOVE_DOWN,
    GameAction.ACTION_PRIMARY,
])

action = decision_engine.analyze_and_decide(screenshot, game_context)
```

### 3. Action Executor (`ActionExecutor`)
Executes the decided action by translating it into actual game inputs.

```python
from playtester.action_executor import MockedActionExecutor

executor = MockedActionExecutor()
executor.execute_action(action)
```

### 4. Game Automator (`GameAutomator`)
Orchestrates all components to create a complete automation loop.

```python
from playtester import GameAutomator

automator = GameAutomator(capture, decision_engine, executor)

# Run single cycle
cycle_info = automator.run_single_cycle()

# Run continuous automation
for cycle_info in automator.run_continuous(max_cycles=100):
    print(f"Cycle {cycle_info['cycle']}: {cycle_info['action']}")
```

## Installation

### Prerequisites
- Python 3.8 or higher
- pip package manager

### Install from source

```bash
# Clone the repository
git clone https://github.com/dmccoystephenson/playtester.git
cd playtester

# Install in development mode, with the automation framework's dependencies
pip install -e ".[automation]"
```

## Quick Start

### Basic Usage

```python
from playtester import GameAutomator, ScreenshotCapture
from playtester.ai_decision_engine import MockedAIDecisionEngine, GameAction
from playtester.action_executor import MockedActionExecutor

# Setup components
capture = ScreenshotCapture(save_screenshots=False)
decision_engine = MockedAIDecisionEngine([GameAction.MOVE_UP, GameAction.ACTION_PRIMARY])
executor = MockedActionExecutor()

# Create automator
automator = GameAutomator(capture, decision_engine, executor, loop_delay=1.0)

# Run automation
for cycle in automator.run_continuous(max_cycles=10):
    print(f"Executed: {cycle['action']}")
```

### Ophidian Game Automation

```python
from playtester.games import OphidianAutomator

automator = OphidianAutomator(save_screenshots=True)
automator.start(max_cycles=100)
```

### Roam Game Automation

```python
from playtester.games import RoamAutomator

automator = RoamAutomator(save_screenshots=True)
automator.start(max_cycles=100)
```

## Examples

See the `examples/` directory for complete working examples:

- `basic_example.py` - Basic automation with mocked components
- `ophidian_example.py` - Ophidian game automation
- `roam_example.py` - Roam game automation

Run examples:
```bash
cd examples
python basic_example.py
```

## Game Actions

The system uses enumerated `GameAction` values to represent possible actions:

- `MOVE_UP`, `MOVE_DOWN`, `MOVE_LEFT`, `MOVE_RIGHT` - Movement actions
- `ACTION_PRIMARY` - Primary action (attack, select, confirm)
- `ACTION_SECONDARY` - Secondary action (defend, cancel, back)
- `WAIT` - Wait/idle action
- `MENU` - Open menu
- `QUIT` - Quit game

Game-specific implementations can extend these with custom actions.

## Creating Custom Game Automators

To create an automator for a new game:

1. **Define game-specific actions** (optional)
```python
class MyGameAction(GameAction):
    CUSTOM_ACTION = 10
```

2. **Create custom AI engine** (optional)
```python
class MyGameAIEngine(MockedAIDecisionEngine):
    def analyze_and_decide(self, screenshot, game_context):
        # Custom decision logic
        return action
```

3. **Create custom action executor** (optional)
```python
class MyGameActionExecutor(MockedActionExecutor):
    def execute_action(self, action, action_params):
        # Custom execution logic
        return success
```

4. **Create game automator class**
```python
class MyGameAutomator:
    def __init__(self):
        self.capture = ScreenshotCapture()
        self.ai_engine = MyGameAIEngine()
        self.executor = MyGameActionExecutor()
        self.automator = GameAutomator(
            self.capture, self.ai_engine, self.executor
        )
```

## Configuration

### Screenshot Capture Configuration

```python
capture = ScreenshotCapture(
    save_screenshots=True,  # Save screenshots to disk
    output_dir="screenshots"  # Directory for saved screenshots
)
```

### Action Executor Configuration

```python
executor = KeyboardActionExecutor(
    key_mapping={
        GameAction.MOVE_UP: 'w',
        GameAction.MOVE_DOWN: 's',
        # ... custom mappings
    },
    delay_between_actions=0.5  # Seconds between actions
)
```

### Automator Configuration

```python
automator = GameAutomator(
    capture, decision_engine, executor,
    loop_delay=1.0  # Seconds between automation cycles
)

automator.set_game_context({
    'game': 'My Game',
    'objective': 'Win',
    'difficulty': 'Hard',
})
```

## Dependencies

- `pillow` - Image processing and screenshot handling
- `pyautogui` - Screen capture and basic input automation
- `pynput` - Advanced keyboard and mouse control

## Future Development

See [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for details on planned features and implementation roadmap.

## License

This project is licensed under the MIT License. See the [LICENSE](../LICENSE) file.

## Contributing

Contributions are welcome! Please see CONTRIBUTING.md for guidelines.

## Support

For issues, questions, or contributions, please visit:
https://github.com/dmccoystephenson/playtester
