# Quick Start Guide

## Installation

1. Clone the repository:
```bash
git clone https://github.com/dmccoystephenson/playtester.git
cd playtester
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Install the package:
```bash
pip install -e .
```

## Running Examples

### Basic Example (No Display Required for Testing)
Test the framework logic without actual game automation:
```bash
cd examples
# Note: Requires a display environment to run fully
python basic_example.py
```

### Ophidian Automation
```bash
cd examples
python ophidian_example.py
```

### Roam Automation
```bash
cd examples
python roam_example.py
```

**Note**: Examples require a display environment (X11, Wayland, or similar) to capture screenshots. They will not work in headless environments.

## Usage in Your Code

### Quick Start
```python
from playtester.games import OphidianAutomator

# Create automator for Ophidian
automator = OphidianAutomator(save_screenshots=True)

# Run for 10 cycles
automator.start(max_cycles=10)
```

### Custom Implementation
```python
from playtester import GameAutomator, ScreenshotCapture
from playtester.ai_decision_engine import MockedAIDecisionEngine, GameAction
from playtester.action_executor import KeyboardActionExecutor

# Setup components
capture = ScreenshotCapture(save_screenshots=True)
engine = MockedAIDecisionEngine([
    GameAction.MOVE_UP,
    GameAction.MOVE_DOWN,
    GameAction.MOVE_LEFT,
    GameAction.MOVE_RIGHT,
    GameAction.ACTION_PRIMARY
])
executor = KeyboardActionExecutor({
    GameAction.MOVE_UP: 'w',
    GameAction.MOVE_DOWN: 's',
    GameAction.MOVE_LEFT: 'a',
    GameAction.MOVE_RIGHT: 'd',
    GameAction.ACTION_PRIMARY: 'space'
})

# Create automator
automator = GameAutomator(capture, engine, executor, loop_delay=1.0)

# Set game context
automator.set_game_context({
    'game': 'My Game',
    'objective': 'Complete level 1'
})

# Run automation
for cycle_info in automator.run_continuous(max_cycles=20):
    print(f"Cycle {cycle_info['cycle']}: {cycle_info['action'].name}")
    print(f"  Confidence: {cycle_info['confidence']:.2f}")
    print(f"  Success: {cycle_info['success']}")
```

## Testing Without a Display

To test the code structure without a display:
```python
# Test imports
import sys
sys.path.insert(0, 'src')

from playtester.ai_decision_engine import GameAction, MockedAIDecisionEngine
from playtester.action_executor import MockedActionExecutor

# Create components
actions = [GameAction.MOVE_UP, GameAction.MOVE_DOWN, GameAction.ACTION_PRIMARY]
ai = MockedAIDecisionEngine(actions)
executor = MockedActionExecutor()

# Test decision making (doesn't require screenshot)
from PIL import Image
dummy_image = Image.new('RGB', (100, 100), color='red')
action = ai.analyze_and_decide(dummy_image, {'test': True})
print(f"AI decided: {action.name}")

# Test execution (mocked, no actual input)
success = executor.execute_action(action)
print(f"Execution success: {success}")

# Check execution history
print(f"Executed actions: {executor.get_execution_history()}")
```

## Project Structure

```
playtester/
├── README.md              # Main documentation
├── SUMMARY.md            # Project summary
├── requirements.txt      # Dependencies
├── setup.py             # Package configuration
├── docs/                # Detailed documentation
│   ├── README.md        # Full usage guide
│   ├── API_REFERENCE.md # API documentation
│   ├── ARCHITECTURE.md  # System architecture
│   └── IMPLEMENTATION_PLAN.md  # Future roadmap
├── examples/            # Usage examples
│   ├── basic_example.py
│   ├── ophidian_example.py
│   └── roam_example.py
└── src/playtester/      # Main package
    ├── __init__.py
    ├── screenshot_capture.py
    ├── ai_decision_engine.py
    ├── action_executor.py
    ├── game_automator.py
    └── games/           # Game-specific implementations
        ├── __init__.py
        ├── ophidian.py
        └── roam.py
```

## Next Steps

1. **Read the documentation**:
   - Start with `README.md`
   - Review `docs/ARCHITECTURE.md` for system design
   - Check `docs/API_REFERENCE.md` for detailed API

2. **Try the examples**:
   - Run `examples/basic_example.py` first
   - Experiment with different game automators

3. **Create your own game automator**:
   - Follow the patterns in `games/ophidian.py`
   - Customize for your specific game

4. **Integrate AI** (advanced):
   - See `docs/IMPLEMENTATION_PLAN.md` Phase 1
   - Replace `MockedAIDecisionEngine` with actual AI model

## Troubleshooting

### "No module named 'PIL'"
Install dependencies:
```bash
pip install pillow pyautogui pynput
```

### "KeyError: 'DISPLAY'"
The system requires a display environment. Run on a machine with X11/Wayland or use:
- Virtual display (Xvfb)
- Remote desktop
- Local machine with GUI

### "ModuleNotFoundError: No module named 'playtester'"
Install the package:
```bash
pip install -e .
```

## Support

- Documentation: See `docs/` directory
- Issues: https://github.com/dmccoystephenson/playtester/issues
- Examples: See `examples/` directory
