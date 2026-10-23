# API Reference

Complete API documentation for the Playtester framework.

## Core Modules

### playtester.ScreenshotCapture

Captures screenshots of game applications.

#### Class: `ScreenshotCapture`

```python
ScreenshotCapture(save_screenshots=False, output_dir="screenshots")
```

**Parameters:**
- `save_screenshots` (bool): Whether to save screenshots to disk
- `output_dir` (str): Directory path for saved screenshots

**Methods:**

##### `capture_full_screen() -> Image.Image`
Captures the entire screen.

**Returns:** PIL Image object

##### `capture_region(x, y, width, height) -> Image.Image`
Captures a specific screen region.

**Parameters:**
- `x` (int): X-coordinate of top-left corner
- `y` (int): Y-coordinate of top-left corner
- `width` (int): Width of region in pixels
- `height` (int): Height of region in pixels

**Returns:** PIL Image object

##### `get_screen_size() -> Tuple[int, int]`
Gets the screen dimensions.

**Returns:** Tuple of (width, height)

---

### playtester.ai_decision_engine

AI-based decision making for game automation.

#### Enum: `GameAction`

Enumerated game actions:

- `MOVE_UP = 1`
- `MOVE_DOWN = 2`
- `MOVE_LEFT = 3`
- `MOVE_RIGHT = 4`
- `ACTION_PRIMARY = 5` - Primary action (attack, select, confirm)
- `ACTION_SECONDARY = 6` - Secondary action (defend, cancel)
- `WAIT = 7`
- `MENU = 8`
- `QUIT = 9`

#### Abstract Class: `AIDecisionEngine`

Base class for AI decision engines.

```python
AIDecisionEngine(game_actions: List[GameAction])
```

**Parameters:**
- `game_actions` (List[GameAction]): Valid actions for the game

**Abstract Methods:**

##### `analyze_and_decide(screenshot, game_context=None) -> GameAction`
Analyzes a screenshot and decides the next action.

**Parameters:**
- `screenshot` (Image.Image): Current game state screenshot
- `game_context` (Dict[str, Any], optional): Additional game context

**Returns:** GameAction enum

##### `get_decision_confidence() -> float`
Gets confidence level of the last decision.

**Returns:** Float between 0.0 and 1.0

#### Class: `MockedAIDecisionEngine`

Mocked implementation for testing.

```python
MockedAIDecisionEngine(game_actions: List[GameAction])
```

Cycles through available actions for demonstration purposes.

---

### playtester.action_executor

Executes game actions via input automation.

#### Abstract Class: `ActionExecutor`

Base class for action executors.

```python
ActionExecutor(delay_between_actions=0.5)
```

**Parameters:**
- `delay_between_actions` (float): Time to wait between actions in seconds

**Abstract Methods:**

##### `execute_action(action, action_params=None) -> bool`
Executes a game action.

**Parameters:**
- `action` (GameAction): Action to execute
- `action_params` (Dict[str, Any], optional): Action parameters

**Returns:** True if successful, False otherwise

**Methods:**

##### `wait(duration=None)`
Waits for specified duration.

**Parameters:**
- `duration` (float, optional): Wait time in seconds

#### Class: `KeyboardActionExecutor`

Executes actions using keyboard input.

```python
KeyboardActionExecutor(key_mapping=None, delay_between_actions=0.5)
```

**Parameters:**
- `key_mapping` (Dict[GameAction, str], optional): Custom key mappings
- `delay_between_actions` (float): Delay between actions

**Default Key Mapping:**
```python
{
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
```

#### Class: `MockedActionExecutor`

Mocked executor for testing without actual input.

```python
MockedActionExecutor(delay_between_actions=0.5)
```

**Additional Methods:**

##### `get_execution_history() -> list`
Returns history of executed actions.

**Returns:** List of action records with timestamps

---

### playtester.GameAutomator

Main orchestrator for game automation.

#### Class: `GameAutomator`

```python
GameAutomator(capture, decision_engine, executor, loop_delay=1.0)
```

**Parameters:**
- `capture` (ScreenshotCapture): Screenshot capture instance
- `decision_engine` (AIDecisionEngine): AI decision engine instance
- `executor` (ActionExecutor): Action executor instance
- `loop_delay` (float): Time between automation cycles

**Methods:**

##### `set_game_context(context: Dict[str, Any])`
Sets or updates game context.

**Parameters:**
- `context` (dict): Game-specific context information

##### `run_single_cycle(region=None) -> Dict[str, Any]`
Runs a single automation cycle.

**Parameters:**
- `region` (tuple, optional): Screen region (x, y, width, height)

**Returns:** Dictionary with cycle information:
```python
{
    'cycle': int,
    'action': GameAction,
    'confidence': float,
    'success': bool,
    'timestamp': float
}
```

##### `run_continuous(max_cycles=None, stop_condition=None, region=None)`
Runs continuous automation loop.

**Parameters:**
- `max_cycles` (int, optional): Maximum cycles (None for infinite)
- `stop_condition` (Callable, optional): Function returning True to stop
- `region` (tuple, optional): Screen region to capture

**Yields:** Cycle information dictionaries

##### `stop()`
Stops the continuous automation loop.

##### `get_stats() -> Dict[str, Any]`
Gets automation session statistics.

**Returns:** Dictionary with statistics:
```python
{
    'total_cycles': int,
    'actions_executed': int,
    'screenshots_taken': int
}
```

`actions_executed` is the executor's `action_count`; `KeyboardActionExecutor`
does not count `WAIT` or unmapped actions, which press no key.
`screenshots_taken` is the capture's `screenshot_count`: every
`capture_full_screen()` and `capture_region()` call increments it, whether or
not `save_screenshots` is set.

---

## Game-Specific Modules

### playtester.games.OphidianAutomator

Ophidian-specific game automator.

#### Class: `OphidianAutomator`

```python
OphidianAutomator(save_screenshots=False)
```

**Parameters:**
- `save_screenshots` (bool): Whether to save screenshots

**Methods:**

##### `start(max_cycles=None, region=None)`
Starts automated gameplay.

**Parameters:**
- `max_cycles` (int, optional): Maximum cycles
- `region` (tuple, optional): Screen region

##### `stop()`
Stops automation.

---

### playtester.games.RoamAutomator

Roam-specific game automator.

#### Class: `RoamAutomator`

```python
RoamAutomator(save_screenshots=False)
```

**Parameters:**
- `save_screenshots` (bool): Whether to save screenshots

**Methods:**

##### `start(max_cycles=None, region=None)`
Starts automated gameplay.

**Parameters:**
- `max_cycles` (int, optional): Maximum cycles
- `region` (tuple, optional): Screen region

##### `stop()`
Stops automation.

---

## Usage Examples

### Basic Automation

```python
from playtester import GameAutomator, ScreenshotCapture
from playtester.ai_decision_engine import MockedAIDecisionEngine, GameAction
from playtester.action_executor import MockedActionExecutor

# Setup
capture = ScreenshotCapture()
engine = MockedAIDecisionEngine([GameAction.MOVE_UP, GameAction.ACTION_PRIMARY])
executor = MockedActionExecutor()

# Create automator
automator = GameAutomator(capture, engine, executor)

# Run
for info in automator.run_continuous(max_cycles=10):
    print(f"Cycle {info['cycle']}: {info['action']}")
```

### Custom Game Automator

```python
from playtester import GameAutomator, ScreenshotCapture
from playtester.ai_decision_engine import AIDecisionEngine, GameAction
from playtester.action_executor import KeyboardActionExecutor

class MyGameEngine(AIDecisionEngine):
    def analyze_and_decide(self, screenshot, game_context):
        # Custom logic
        return GameAction.MOVE_UP
    
    def get_decision_confidence(self):
        return 0.9

# Setup
capture = ScreenshotCapture()
engine = MyGameEngine([GameAction.MOVE_UP, GameAction.MOVE_DOWN])
executor = KeyboardActionExecutor({
    GameAction.MOVE_UP: 'w',
    GameAction.MOVE_DOWN: 's'
})

automator = GameAutomator(capture, engine, executor)
```

### With Screen Region

```python
automator = OphidianAutomator()

# Only capture/analyze specific region where game window is
region = (100, 100, 800, 600)  # x, y, width, height
automator.start(max_cycles=50, region=region)
```

### With Stop Condition

```python
def should_stop():
    # Custom logic to determine when to stop
    return some_condition

for info in automator.run_continuous(stop_condition=should_stop):
    print(f"Action: {info['action']}")
```

---

## Type Hints

The codebase uses Python type hints throughout. The package does not define
type aliases; the names below are shorthand for the types used in signatures
and are not importable from `playtester`:

```python
from typing import List, Dict, Any, Optional, Tuple, Callable
from PIL import Image
from enum import Enum

# Shorthand for common types (not defined in the package)
GameContext = Dict[str, Any]
ActionParams = Optional[Dict[str, Any]]
ScreenRegion = Tuple[int, int, int, int]  # (x, y, width, height)
CycleInfo = Dict[str, Any]
```

---

## Error Handling

- `execute_action()` returns `bool`. `KeyboardActionExecutor` catches any
  exception raised while pressing a key, prints it and returns `False`;
  `MockedActionExecutor` always returns `True`.
- `capture_full_screen()` and `capture_region()` do not catch errors: an
  exception from `pyautogui.screenshot()` (or from saving the file when
  `save_screenshots=True`) propagates to the caller, and through
  `GameAutomator.run_single_cycle()` / `run_continuous()`.
- `MockedAIDecisionEngine.analyze_and_decide()` does not raise for normal
  input; custom decision engines should handle their own errors and return a
  safe default action, because `GameAutomator` does not catch exceptions from
  the engine.
- Importing `playtester` imports `pyautogui`, which on Linux raises
  `KeyError: 'DISPLAY'` when no X display is available (run under `xvfb-run`
  headless).

---

## Thread Safety

The current implementation is **not thread-safe**. Each `GameAutomator` instance should be used from a single thread. For multi-game automation, create separate instances.

---

## Performance Considerations

- Screenshot capture frequency: Limited by `loop_delay` parameter
- AI inference time: Depends on model implementation (mocked version is instant)
- Action execution delay: Controlled by `delay_between_actions`

For optimal performance:
- Use specific screen regions instead of full screen capture
- Adjust `loop_delay` based on game speed
- Consider caching game context between cycles

---

## Version Compatibility

- Python: 3.8+
- Pillow: 10.0.0+
- PyAutoGUI: 0.9.54+
- Pynput: 1.7.6+
