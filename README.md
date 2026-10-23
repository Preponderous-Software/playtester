# Playtester - AI Playtesting and Game Automation

An open-source Python toolkit for playing games with AI: parallel AI agents that playtest a real game headless, and a framework for automating game play from screenshots.

## Description

Playtester has two parts:

- **The agent playtest kit** (the main part). Any number of AI agents (for example Claude Code subagents) play the real game at once, each in its own headless session and toward its own goal, the way a person would: by looking at screenshots and pressing keys. Each writes a structured report, and the reports are merged into one summary with grouped findings and objective timings. The `pt` command runs and drives the sessions; a **profile** describes each game; games can optionally implement a small **probe** (state and event files) so agents can steer precisely. A tiny demo game ships with the kit, and Beyond Nations and Kindling are bundled as profiles. See [docs/AGENT_PLAYTESTING.md](docs/AGENT_PLAYTESTING.md).
- **The screenshot automation framework (experimental).** Screenshot capture, an AI decision engine and a keyboard executor, wired together by `GameAutomator`. The decision engine is **mocked**: no AI model is integrated yet, and [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) describes how one could be (LLaVA, CLIP, MiniGPT-4, OpenFlamingo). See [The automation framework](#the-automation-framework-experimental).

## Quick start: the agent playtest kit

You need Linux (or WSL2) with Python 3.8 or newer; no desktop is needed. The kit is standard-library Python, so installing it installs no Python packages.

```bash
# system tools: a virtual X server, input, screenshots, software OpenGL
sudo apt-get install -y xvfb xdotool imagemagick libgl1-mesa-dri

git clone https://github.com/Preponderous-Software/playtester.git
cd playtester
pip install -e .                   # gives the `pt` command (also `python -m playtester`)
# or, without a checkout: pip install git+https://github.com/Preponderous-Software/playtester

pt profiles                        # the bundled game profiles
PT_ROOT=/tmp/pt-try pt smoke --profile demo
```

`pt smoke --profile demo` plays the bundled demo game through a scripted session (start it, walk to the trees, chop until the *Gather wood* objective completes) and prints `PASS` when this machine can run the kit. Its screenshots and logs stay under `/tmp/pt-try`.

Then drive one session by hand, as an agent would:

```bash
export PT_ROOT=/tmp/pt-try PT_SESSION=me     # every pt command needs these
pt start --profile demo --seed 7
pt shot title                                # prints the PNG path; open it
pt key space && pt await WORLD
pt state                                     # what the game reports about itself
pt walkto tree && pt key e                   # walk to the nearest tree and chop
pt events 5
pt stop
```

To run a coordinated playtest with many agents, install the coordinator skill into the game's checkout and ask Claude Code to `/playtest`:

```bash
pt install-skill ~/beyond-nations --profile beyond-nations
```

To playtest your own game, write a profile for it: see [Adding a game](docs/PROFILES.md#adding-a-game).

| Document | |
| --- | --- |
| [docs/AGENT_PLAYTESTING.md](docs/AGENT_PLAYTESTING.md) | The kit: install, commands, running N agents, costs, goals, reading the summary, troubleshooting |
| [docs/PROFILES.md](docs/PROFILES.md) | Game profiles: every field, and [adding a game](docs/PROFILES.md#adding-a-game) |
| [docs/PROBE_CONTRACT.md](docs/PROBE_CONTRACT.md) | The optional probe a game can implement (`state.json`, `events.jsonl`) |

## Bundled games

| Profile | Game | Needs |
| --- | --- | --- |
| `demo` | A tiny top-down test game that ships with playtester (`playtester.demo`) | Nothing more: no clone, no build |
| `beyond-nations` | [Beyond Nations](https://github.com/Preponderous-Software/beyond-nations), a 3D colony-and-nations game | The .NET 8 SDK; release **0.5.0** or newer for the probe (0.5.0 is marked as a pre-release on GitHub, so the "latest release" link skips it) |
| `kindling` | [Kindling](https://github.com/Preponderous-Software/kindling), a first-person homestead game | CMake and a C++17 compiler, plus the X11 development packages its SDL3 build needs; commit **d47730f** or newer for the probe |

The profiles start a game you have cloned and built; pass its checkout with `--game-dir` (or `PT_GAME_DIR`). `pt validate-profile NAME` prints a profile's build command and the toolchain it needs.

**Beyond Nations** (`pt start --profile beyond-nations --game-dir ~/beyond-nations`):

```bash
git clone https://github.com/Preponderous-Software/beyond-nations.git ~/beyond-nations
cd ~/beyond-nations
git checkout 0.5.0          # or any later release; main works too
dotnet build src/BeyondNations.Desktop/BeyondNations.Desktop.csproj -c Release
```

**Kindling** (`pt start --profile kindling --game-dir ~/kindling`):

```bash
sudo apt-get install -y cmake g++ libx11-dev libxext-dev libxcursor-dev libxi-dev \
    libxfixes-dev libxrandr-dev libxss-dev
git clone https://github.com/Preponderous-Software/kindling.git ~/kindling
cd ~/kindling
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build --target kindling -j4
```

A game without a probe can still be playtested from screenshots alone; the probe adds precise state, events and the `await`, `face` and `walkto` commands.

## The automation framework (experimental)

The framework captures screenshots of a game running on your desktop, asks a decision engine for an action and sends key presses. **The decision engine is mocked** (it cycles through a fixed list of actions), and the Ophidian and Roam presets are templates with mocked implementations. It needs a graphical desktop (X11, Wayland, Windows or macOS) and the `automation` extra, which adds pillow, pyautogui and pynput:

```bash
pip install -e ".[automation]"
```

Without the extra, `from playtester import GameAutomator` raises an `ImportError` that names it.

### Documentation

- [User Guide](USER_GUIDE.md) – Getting started and common scenarios
- [API Reference](docs/API_REFERENCE.md) – Complete API documentation
- [Implementation Plan](docs/IMPLEMENTATION_PLAN.md) – Roadmap for AI integration
- [Architecture](docs/ARCHITECTURE.md) – System design diagrams

### Running the example

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

`KeyboardActionExecutor` sends real key presses to whatever window has focus; use `MockedActionExecutor` to try the loop safely.

## Support

### Experiencing a bug?

Please file a bug report [here](https://github.com/Preponderous-Software/playtester/issues/new).

- [Known Issues](https://github.com/Preponderous-Software/playtester/issues)

### Questions?

- [Documentation](docs/AGENT_PLAYTESTING.md) for the agent kit, [docs/README.md](docs/README.md) for the automation framework
- Ask in a [GitHub issue](https://github.com/Preponderous-Software/playtester/issues)

### Security

Report vulnerabilities privately, as described in [SECURITY.md](SECURITY.md).

## Contributing

- [CONTRIBUTING.md](CONTRIBUTING.md) – How to contribute to this project
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) – How we treat each other
- [GitHub Issues](https://github.com/Preponderous-Software/playtester/issues) – Find something to work on

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed information on how to contribute to this project.

## Testing

### Test suite

```bash
python -m unittest discover -s tests -t .
```

The end-to-end tests in `tests/test_harness_live.py` play the demo game in real virtual displays; they are skipped unless Xvfb, xdotool and ImageMagick are installed. The rest need nothing beyond Python.

### Syntax Verification

```bash
python -m py_compile src/playtester/*.py src/playtester/*/*.py examples/*.py ci/*.py tests/*.py
```

If all files compile without errors, the syntax is valid.

### Continuous Integration

Every pull request runs the `Build` workflow (job `test`, Python 3.8): the syntax check above, the unit and end-to-end test suite (`python -m unittest discover -s tests -t .`, which plays the bundled demo game in real virtual displays, three sessions at once), `pt smoke --profile demo`, an import check of the automation classes and `ci/smoke_test.py`, which captures screenshots of a virtual screen and runs four mocked automation cycles. The automation classes need the `automation` extra and a display at import time, so those checks run under Xvfb; the agent kit needs neither. See [CONTRIBUTING.md](CONTRIBUTING.md#continuous-integration) for running these locally.

### Manual Testing

Run the automation framework's example scripts (requires a display environment and the `automation` extra):

```bash
cd examples
python basic_example.py
python ophidian_example.py
python roam_example.py
```

## Development

### Technology Stack

- **Language**: Python 3.8+
- **Dependencies**: none for the agent kit (standard-library Python plus Xvfb, xdotool and ImageMagick); pillow, pyautogui and pynput for the automation framework (the `automation` extra)
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
| dmccoystephenson | Project creator and maintainer |

Much of the code and documentation was written with AI coding assistants (GitHub Copilot and Claude Code) and reviewed by the maintainer.

### Project Origin

Playtester began as an open-source framework for automating gameplay through AI-driven decision making, and grew into a kit for letting AI agents playtest real games headless and report what they find.

## License

This project is licensed under the [MIT License](LICENSE).

## Project Status

This project is in active development.

### Current Status

✅ **Implemented:**
- The agent playtest kit: headless sessions, the `pt` command, game profiles, the probe contract, the agent prompt, report validation and aggregation, the `/playtest` coordinator skill
- Unit and end-to-end tests for the kit, run in CI
- The automation framework's architecture and loop, screenshot capture and action execution
- Game-specific automation templates (Ophidian, Roam), with mocked implementations

🚧 **In Progress:**
- AI decision engine integration with open-source models (the engine is mocked)
- Game-specific UI detection for the automation framework

See [CHANGELOG.md](CHANGELOG.md) for version history and [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) for the roadmap.

### Supported Games

- **Agent playtest kit** – the demo game, Beyond Nations and Kindling (see [Bundled games](#bundled-games)), and any game you write a profile for
- **Automation framework** – Ophidian and Roam templates with mocked implementations, and a base for your own automators