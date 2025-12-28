# Playtester - AI-Powered Game Automation System

An open-source Python framework for automating game play through AI-powered decision making based on visual game state analysis.

## Overview

Playtester enables automated gameplay by:
1. Capturing screenshots of game applications
2. Feeding screenshots to an AI decision engine
3. Having the AI make enumerated decisions corresponding to game actions
4. Executing those actions in the game

The system is designed with a modular architecture that supports multiple games and can be extended with custom implementations.

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/dmccoystephenson/playtester.git
cd playtester

# Install dependencies
pip install -r requirements.txt

# Install the package
pip install -e .
```

### Basic Usage

```python
from playtester.games import OphidianAutomator

# Create and start the automator
automator = OphidianAutomator(save_screenshots=True)
automator.start(max_cycles=10)
```

### Run Examples

```bash
cd examples
python basic_example.py      # Basic automation demo
python ophidian_example.py   # Ophidian game automation
python roam_example.py       # Roam game automation
```

## Architecture

The system consists of four main components:

1. **Screenshot Capture** - Captures game screen for analysis
2. **AI Decision Engine** - Analyzes screenshots and decides actions (currently mocked)
3. **Action Executor** - Executes decided actions via keyboard/mouse
4. **Game Automator** - Orchestrates the automation loop

## Current Status

✅ **Implemented:**
- Core architecture and automation loop
- Screenshot capture system
- Action execution framework
- Game-specific templates (Ophidian, Roam)

🚧 **Mocked (needs implementation):**
- AI decision engine (documented for open-source AI integration)
- Game-specific UI detection
- Action verification

See [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) for detailed implementation roadmap.

## Documentation

- [Full Documentation](docs/README.md) - Complete usage guide
- [Implementation Plan](docs/IMPLEMENTATION_PLAN.md) - Roadmap and desired behavior
- [API Reference](docs/API_REFERENCE.md) - Detailed API documentation

## Supported Games

- **Ophidian** - Game-specific automator with mocked implementation
- **Roam** - Game-specific automator with mocked implementation
- **Custom Games** - Framework for creating your own automators

## Features

- 🎮 Modular architecture for easy game addition
- 🤖 AI-driven decision making (framework ready for model integration)
- 📸 Screenshot capture with debug logging
- ⌨️ Keyboard and mouse input automation
- 🔧 Extensible design for custom implementations
- 📚 Comprehensive documentation

## Dependencies

- Python 3.8+
- pillow - Image processing
- pyautogui - Screen capture and input
- pynput - Advanced input control

## Contributing

Contributions are welcome! Areas needing implementation:
- Integration with open-source vision-language models (LLaVA, CLIP, etc.)
- Game-specific implementations for Ophidian and Roam
- Window management and action verification
- Additional game automators

## License

Open source - see LICENSE file for details.

## Support

For issues, questions, or contributions:
- GitHub Issues: https://github.com/dmccoystephenson/playtester/issues
- Documentation: [docs/README.md](docs/README.md)