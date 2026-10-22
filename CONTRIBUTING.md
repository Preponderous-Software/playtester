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
4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
5. Install the package in development mode:
   ```bash
   pip install -e .
   ```
6. Verify the installation:
   ```bash
   python -c "import playtester; print('Success!')"
   ```
   If you encounter errors, please open an issue.

## Identifying What to Work On

### Issues

Work items are tracked as [GitHub issues](https://github.com/dmccoystephenson/playtester/issues).

### Milestones

Issues are grouped into [milestones](https://github.com/dmccoystephenson/playtester/milestones) representing upcoming releases.

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

### Manual Testing

Test your changes by running the example scripts:

```bash
cd examples
python basic_example.py
```

Note: Examples require a display environment (X11, Wayland, or similar).

### Code Verification

Verify Python syntax:

```bash
python -m py_compile src/playtester/*.py src/playtester/games/*.py examples/*.py
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

Importing any `playtester` module runs the package `__init__.py`, which imports
`pyautogui`; on Linux that needs an X display at import time and fails with
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

If you have questions:
- Open a [GitHub Discussion](https://github.com/dmccoystephenson/playtester/discussions)
- File an [issue](https://github.com/dmccoystephenson/playtester/issues)
