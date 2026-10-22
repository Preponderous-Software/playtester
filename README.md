# Playtester - AI Playtesting and Game Automation

An open-source Python toolkit for playing games with AI: parallel AI agents that playtest a real game headless, and a framework for automating game play from screenshots.

## Description

Playtester has two parts:

- **The agent playtest kit.** Any number of AI agents (for example Claude Code subagents) play the real game at once, each in its own headless session and toward its own goal, the way a person would: by looking at screenshots and pressing keys. Each writes a structured report, and the reports are merged into one summary with grouped findings and objective timings. The `pt` command runs and drives the sessions; a **profile** describes each game; games can optionally implement a small **probe** (state and event files) so agents can steer precisely. Beyond Nations and Kindling are bundled as profiles. See [docs/AGENT_PLAYTESTING.md](docs/AGENT_PLAYTESTING.md).
- **The automation framework.** Screenshot capture, an AI decision engine (currently mocked) and a keyboard executor, wired together by `GameAutomator`, with documentation for integrating open-source vision-language models such as LLaVA, CLIP, MiniGPT-4, or OpenFlamingo.

## Agent playtesting, quickly

```bash
sudo apt-get install -y xvfb xdotool imagemagick libgl1-mesa-dri
pip install -e .
PT_ROOT=/tmp/pt-try pt smoke --profile demo        # proves the machine can run the kit

# one session of a real game, by hand
export PT_ROOT=/tmp/pt-try PT_SESSION=me
pt start --profile beyond-nations --game-dir ~/beyond-nations --seed 42
pt shot title && pt key space && pt state
pt stop

# a coordinated run: install the coordinator skill into the game's checkout,
# then ask Claude Code to /playtest
pt install-skill ~/beyond-nations --profile beyond-nations
```

| Document | |
| --- | --- |
| [docs/AGENT_PLAYTESTING.md](docs/AGENT_PLAYTESTING.md) | The kit: install, commands, running N agents, costs, goals, reading the summary, troubleshooting |
| [docs/PROFILES.md](docs/PROFILES.md) | Game profiles: every field, and adding a game |
| [docs/PROBE_CONTRACT.md](docs/PROBE_CONTRACT.md) | The optional probe a game can implement (`state.json`, `events.jsonl`) |

## Installation

### First Time Installation

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

### Requirements

- Python 3.8 or higher
- For the agent playtest kit: Linux or WSL2 with Xvfb, xdotool and ImageMagick (no desktop needed)
- For the automation framework: a graphical desktop environment (X11, Wayland, Windows, or macOS)
- The game you want to playtest or automate

## Usage

### Documentation

- [User Guide](USER_GUIDE.md) – Getting started and common scenarios
- [API Reference](docs/API_REFERENCE.md) – Complete API documentation
- [Implementation Plan](docs/IMPLEMENTATION_PLAN.md) – Roadmap for AI integration
- [Architecture](docs/ARCHITECTURE.md) – System design diagrams

### Quick Start

Run the basic example:

```bash
cd examples
python basic_example.py
```

### Game-Specific Automation

```python
from playtester.games import OphidianAutomator

# Create and start the automator
automator = OphidianAutomator(save_screenshots=True)
automator.start(max_cycles=10)
```

### Custom Automation

```python
from playtester import GameAutomator, ScreenshotCapture
from playtester.ai_decision_engine import MockedAIDecisionEngine, GameAction
from playtester.action_executor import KeyboardActionExecutor

capture = ScreenshotCapture()
engine = MockedAIDecisionEngine([GameAction.MOVE_UP, GameAction.ACTION_PRIMARY])
executor = KeyboardActionExecutor()

automator = GameAutomator(capture, engine, executor)
for cycle in automator.run_continuous(max_cycles=20):
    print(f"{cycle['action'].name} (confidence: {cycle['confidence']:.2f})")
```

## Support

### Experiencing a bug?

Please file a bug report [here](https://github.com/dmccoystephenson/playtester/issues/new).

- [Known Issues](https://github.com/dmccoystephenson/playtester/issues)

### Questions?

- [GitHub Discussions](https://github.com/dmccoystephenson/playtester/discussions)
- [Documentation](docs/README.md)

## Contributing

- [CONTRIBUTING.md](CONTRIBUTING.md) – How to contribute to this project
- [GitHub Issues](https://github.com/dmccoystephenson/playtester/issues) – Find something to work on

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed information on how to contribute to this project.

## Testing

### Syntax Verification

Linux / macOS:

```bash
python -m py_compile src/playtester/*.py src/playtester/games/*.py examples/*.py
```

Windows:

```cmd
python -m py_compile src/playtester/*.py src/playtester/games/*.py examples/*.py
```

If all files compile without errors, the syntax is valid.

### Continuous Integration

Every pull request runs the `Build` workflow (job `test`, Python 3.8): the syntax check above, the unit and end-to-end test suite (`python -m unittest discover -s tests -t .`, which plays the bundled demo game in real virtual displays, three sessions at once), `pt smoke --profile demo`, an import check of the automation classes and `ci/smoke_test.py`, which captures screenshots of a virtual screen and runs four mocked automation cycles. The automation classes need a display at import time, so those checks run under Xvfb; the agent kit does not. See [CONTRIBUTING.md](CONTRIBUTING.md#continuous-integration) for running these locally.

### Manual Testing

Run the example scripts (requires a display environment):

```bash
cd examples
python basic_example.py
python ophidian_example.py
python roam_example.py
```

## Development

### Technology Stack

- **Language**: Python 3.8+
- **Dependencies**: pillow, pyautogui, pynput (the automation framework); the agent kit is standard-library Python plus Xvfb, xdotool and ImageMagick
- **Package Manager**: pip
- **Build Tool**: setuptools

### Project Structure

```
playtester/
├── src/playtester/          # Main package
│   ├── harness/             # Agent playtest kit: the pt command, sessions, profiles, smoke, measure
│   ├── agents/              # Agent prompt, report validation, aggregation
│   ├── data/                # Bundled profiles, schemas, the agent prompt, the coordinator skill
│   ├── demo.py              # A tiny game implementing the probe, for tests
│   ├── probecheck.py, schema.py
│   ├── screenshot_capture.py, ai_decision_engine.py, action_executor.py, game_automator.py
│   └── games/               # Automation presets (Ophidian, Roam)
├── examples/                # Example scripts
├── docs/                    # Documentation
└── tests/                   # Unit and end-to-end tests
```

### Development Workflow

1. Fork and clone the repository
2. Create a feature branch
3. Make your changes
4. Test your changes
5. Submit a pull request

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed instructions.

## Authors and Acknowledgement

### Developers

| Name | Main Contributions |
|------|-------------------|
| dmccoystephenson | Project creator, initial implementation |
| GitHub Copilot | Code assistance and framework development |

### Project Origin

Playtester was created to provide an open-source framework for automating gameplay through AI-driven decision making. The project aims to make game automation accessible and extensible for researchers, developers, and enthusiasts.

## License

This project is licensed under the [GNU General Public License v3.0](LICENSE) (GPL-3.0).

You are free to use, modify, and distribute this software, provided that:

- Source code is made available under the same license when distributed.
- Changes are documented and attributed.
- No additional restrictions are applied.

See the [LICENSE](LICENSE) file for the full text of the GPL-3.0 license.

## Project Status

This project is in active development.

### Current Status

✅ **Implemented:**
- Core architecture and automation loop
- Screenshot capture system
- Action execution framework
- Game-specific templates (Ophidian, Roam)

🚧 **In Progress:**
- AI decision engine integration with open-source models
- Game-specific UI detection
- Comprehensive test suite

See [CHANGELOG.md](CHANGELOG.md) for version history and [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) for the roadmap.

### Supported Games

- **Ophidian** – Game-specific automator with mocked implementation
- **Roam** – Game-specific automator with mocked implementation
- **Custom Games** – Framework for creating your own automators