# System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Game Application                           │
│                   (Ophidian / Roam / Other)                     │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 │ (visual output)
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Screenshot Capture                            │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  - capture_full_screen()                                  │  │
│  │  - capture_region(x, y, width, height)                    │  │
│  │  - Optional: save to disk for debugging                   │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 │ (PIL Image)
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                 AI Decision Engine                              │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  CURRENT: MockedAIDecisionEngine (cycles through actions) │  │
│  │  PLANNED: Open-source vision-language model integration   │  │
│  │    - LLaVA (Large Language and Vision Assistant)          │  │
│  │    - CLIP (Contrastive Language-Image Pre-training)       │  │
│  │    - MiniGPT-4                                             │  │
│  │    - OpenFlamingo                                          │  │
│  │                                                            │  │
│  │  analyze_and_decide(screenshot, game_context)             │  │
│  │    → Returns enumerated GameAction                        │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 │ (GameAction enum)
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Action Executor                              │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Translates GameAction to actual inputs:                  │  │
│  │  - KeyboardActionExecutor (keyboard keys)                 │  │
│  │  - MouseActionExecutor (planned)                          │  │
│  │  - GamepadActionExecutor (planned)                        │  │
│  │  - MockedActionExecutor (for testing)                     │  │
│  │                                                            │  │
│  │  execute_action(action, params)                           │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 │ (keyboard/mouse input)
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Game Application                           │
│                   (receives automated input)                    │
└─────────────────────────────────────────────────────────────────┘
```

## Automation Loop

```
┌─────────────────────────────────────────────────────────────────┐
│                     Game Automator                              │
│                   (orchestrates the loop)                       │
│                                                                 │
│  1. Capture screenshot                                          │
│           ↓                                                     │
│  2. AI analyzes → decides action                                │
│           ↓                                                     │
│  3. Execute action                                              │
│           ↓                                                     │
│  4. Wait (configurable delay)                                   │
│           ↓                                                     │
│  5. Repeat (or stop on condition/max cycles)                    │
│                                                                 │
│  Provides:                                                      │
│  - run_single_cycle()                                           │
│  - run_continuous(max_cycles, stop_condition)                   │
│  - Statistics tracking                                          │
└─────────────────────────────────────────────────────────────────┘
```

## GameAction Enumeration

```
┌────────────────────────────────────────────────────────┐
│               GameAction (Enum)                        │
├────────────────────────────────────────────────────────┤
│  MOVE_UP = 1         │  Movement actions               │
│  MOVE_DOWN = 2       │  (directional control)          │
│  MOVE_LEFT = 3       │                                 │
│  MOVE_RIGHT = 4      │                                 │
├──────────────────────┼─────────────────────────────────┤
│  ACTION_PRIMARY = 5  │  Primary action                 │
│                      │  (attack, select, confirm)      │
├──────────────────────┼─────────────────────────────────┤
│  ACTION_SECONDARY = 6│  Secondary action               │
│                      │  (defend, cancel, back)         │
├──────────────────────┼─────────────────────────────────┤
│  WAIT = 7            │  Wait/idle                      │
│  MENU = 8            │  Open menu                      │
│  QUIT = 9            │  Quit game                      │
└──────────────────────┴─────────────────────────────────┘

Game-specific implementations pick the subset they
use; the enum cannot be subclassed to add members.
```

## Component Relationships

```
┌──────────────────────────────────────────────────────────────┐
│                   AbstractGame                               │
│                  ┌────────────┐                              │
│                  │ScreenShot  │                              │
│                  │  Capture   │                              │
│                  └─────┬──────┘                              │
│                        │                                     │
│                        ▼                                     │
│         ┌──────────────────────────────┐                    │
│         │   AIDecisionEngine (ABC)     │                    │
│         │  ┌─────────────────────────┐ │                    │
│         │  │ MockedAIDecisionEngine  │ │◄── Current         │
│         │  └─────────────────────────┘ │                    │
│         │  ┌─────────────────────────┐ │                    │
│         │  │ LLaVA/CLIP Integration  │ │◄── Planned         │
│         │  └─────────────────────────┘ │                    │
│         └──────────────┬───────────────┘                    │
│                        │                                     │
│                        ▼                                     │
│         ┌──────────────────────────────┐                    │
│         │   ActionExecutor (ABC)       │                    │
│         │  ┌─────────────────────────┐ │                    │
│         │  │ KeyboardActionExecutor  │ │◄── Implemented     │
│         │  └─────────────────────────┘ │                    │
│         │  ┌─────────────────────────┐ │                    │
│         │  │ MockedActionExecutor    │ │◄── For testing     │
│         │  └─────────────────────────┘ │                    │
│         └──────────────────────────────┘                    │
│                                                              │
│  All coordinated by: GameAutomator                          │
└──────────────────────────────────────────────────────────────┘
```

## Game-Specific Implementations

```
┌──────────────────────────────────────────────────────────────┐
│                  Generic Framework                           │
│   (ScreenshotCapture, AIDecisionEngine, ActionExecutor)      │
└────────────────────────┬─────────────────────────────────────┘
                         │
         ┌───────────────┴───────────────┐
         │                               │
         ▼                               ▼
┌─────────────────────┐         ┌─────────────────────┐
│  OphidianAutomator  │         │   RoamAutomator     │
├─────────────────────┤         ├─────────────────────┤
│ - OphidianAIEngine  │         │ - RoamAIEngine      │
│ - OphidianExecutor  │         │ - RoamExecutor      │
│ - Game context      │         │ - Game context      │
│ - Custom actions    │         │ - Custom actions    │
└─────────────────────┘         └─────────────────────┘

Each game-specific automator:
  1. Extends/customizes the AI engine
  2. Defines game-specific actions
  3. Implements game-specific execution logic
  4. Provides convenient start/stop methods
```

## Data Flow

```
Screenshot (PIL Image)
    │
    └─► game_context (Dict)
            │
            └─► AI Decision Engine
                    │
                    └─► GameAction (Enum)
                            │
                            └─► Action Executor
                                    │
                                    └─► Input to Game

Each cycle produces:
{
    'cycle': int,
    'action': GameAction,
    'confidence': float,
    'success': bool,
    'timestamp': float
}
```

## Extension Points

The system is designed to be extensible at multiple points:

1. **Custom AI Engines**: Inherit from `AIDecisionEngine`
2. **Custom Executors**: Inherit from `ActionExecutor`
3. **Custom Game Actions**: Extend `GameAction` enum
4. **Custom Game Automators**: Create game-specific convenience classes
5. **Custom Game Context**: Add any relevant game state information

See docs/README.md for detailed examples of creating custom implementations.
