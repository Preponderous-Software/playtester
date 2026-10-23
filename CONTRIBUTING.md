# Contributing

## Thank You

Thank you for your interest in contributing to Playtester! This guide will help you get started.

## Links

- [GitHub Repository](https://github.com/dmccoystephenson/playtester)
- [Issues](https://github.com/dmccoystephenson/playtester/issues)
- [Documentation](docs/README.md)

## Requirements

- A GitHub account
- Git installed on your local machine
- Python 3.8 or higher
- A text editor or Python IDE
- Basic understanding of Python

## Getting Started

1. [Sign up for GitHub](https://github.com/signup) if you don't have an account.
2. Fork the repository by clicking **Fork** at the top right of the repo page.
3. Clone your fork:
   ```bash
   git clone https://github.com/<your-username>/playtester.git
   cd playtester
   ```
4. Install the system tools the agent playtest kit and the tests use (Debian/Ubuntu):
   ```bash
   sudo apt-get install xvfb xauth xdotool imagemagick libgl1-mesa-dri scrot
   ```
5. Install the package in development mode. The agent playtest kit needs no
   Python packages; the `automation` extra adds pillow, pyautogui and pynput for
   the experimental screenshot automation framework:
   ```bash
   pip install -e ".[automation]"
   ```
6. Verify the installation:
   ```bash
   python -m unittest discover -s tests -t .
   ```
   If you encounter errors, please open an issue.

## Identifying What to Work On

### Issues

Work items are tracked as [GitHub issues](https://github.com/dmccoystephenson/playtester/issues).

## Making Changes

1. Make sure an issue exists for the work. If not, create one.
2. Switch to `main` branch (this project uses `main` as the primary branch):
   ```bash
   git checkout main
   git pull origin main
   ```
3. Create a feature branch:
   ```bash
   git checkout -b feature/descriptive-branch-name
   ```
4. Make your changes.
5. Test your changes (see [Testing](#testing)).
6. Commit your changes:
   ```bash
   git add .
   git commit -m "Brief description of changes"
   ```
7. Push to your fork:
   ```bash
   git push origin feature/descriptive-branch-name
   ```
8. Open a pull request against the `main` branch of the upstream repository. Include a description and link the related issue using `#<number>`.
9. Address any review feedback.
10. Once approved, the maintainer will merge the PR into `main`.

### Documentation

If your change adds or modifies user-facing features, update the relevant documentation files:
- `README.md` - For major feature additions
- `docs/README.md` - For detailed usage changes
- `docs/API_REFERENCE.md` - For API changes
- `docs/IMPLEMENTATION_PLAN.md` - For planned features

## Testing

### The test suite

Run the unit and end-to-end tests (the end-to-end tests play the bundled demo
game in real virtual displays, so they need the system tools from
[Getting Started](#getting-started)):

```bash
python -m unittest discover -s tests -t .
```

### Code Verification

Verify Python syntax (the same command CI runs):

```bash
python -m py_compile src/playtester/*.py src/playtester/*/*.py examples/*.py ci/*.py tests/*.py
```

### Manual Testing

The automation framework's example scripts need a display environment (X11,
Wayland, or similar) and the `automation` extra:

```bash
cd examples
python basic_example.py
```

### Continuous Integration

The `Build` workflow (`.github/workflows/build.yml`, job `test`) runs on every
pull request and on pushes to `main`, on Python 3.8. Besides the syntax check
above, it runs the test suite and the demo smoke session of the agent
playtest kit (which start their own virtual X servers), then the import check
and `ci/smoke_test.py` under a virtual X server. To run the same checks
locally on Linux (requires the `xvfb`, `xauth`, `scrot`, `xdotool` and
`imagemagick` packages):

```bash
python -m unittest discover -s tests -t .
PT_ROOT=/tmp/pt-smoke python -m playtester smoke --profile demo
xvfb-run -a -s "-screen 0 1280x720x24" python -c "import playtester; print('Playtester imported successfully')"
XDG_SESSION_TYPE=x11 xvfb-run -a -s "-screen 0 1280x720x24" python ci/smoke_test.py
```

### Testing Without Display

`import playtester`, the agent playtest kit and `playtester.ai_decision_engine`
need no display. The modules that import `pyautogui` do: `action_executor` and
`screenshot_capture` (and so `game_automator` and `games`, which import them).
On Linux pyautogui needs an X display at import time and fails with
`KeyError: 'DISPLAY'` when none is available. In a headless environment, run the
script below under `xvfb-run` (as above) to test the core logic:

```python
import sys
sys.path.insert(0, 'src')

from playtester.ai_decision_engine import GameAction, MockedAIDecisionEngine
from playtester.action_executor import MockedActionExecutor

# Test components
actions = [GameAction.MOVE_UP, GameAction.ACTION_PRIMARY]
ai = MockedAIDecisionEngine(actions)
executor = MockedActionExecutor()

print("Tests passed!")
```

## Code Style

- Follow PEP 8 Python style guidelines
- Use meaningful variable and function names
- Add docstrings to all public classes and methods
- Keep functions focused and small
- Add type hints where appropriate

## Questions

If you have questions, file an [issue](https://github.com/dmccoystephenson/playtester/issues).

## Code of Conduct and Security

This project follows the [Code of Conduct](CODE_OF_CONDUCT.md). Please report
security problems privately as described in [SECURITY.md](SECURITY.md), not in
a public issue.
