# Copilot Instructions

This repository follows the DPC (Dans Plugins Community) conventions defined at
https://github.com/Dans-Plugins/dpc-conventions. Read those conventions before
making any changes.

## Technology Stack

- Language: Python 3.8+
- Build tool: Python setuptools
- Target platform: Cross-platform (Windows, Linux, macOS)
- Dependencies: pillow, pyautogui, pynput

## Project Structure

- `src/playtester/` – Main package source code
  - `screenshot_capture.py` – Screenshot capture functionality
  - `ai_decision_engine.py` – AI decision interface and implementations
  - `action_executor.py` – Action execution with keyboard/mouse
  - `game_automator.py` – Main orchestrator
  - `games/` – Game-specific automator implementations
- `examples/` – Example scripts demonstrating usage
- `docs/` – Documentation files
  - `README.md` – Full usage guide
  - `API_REFERENCE.md` – Complete API documentation
  - `IMPLEMENTATION_PLAN.md` – Future roadmap
  - `ARCHITECTURE.md` – System design diagrams
- `requirements.txt` – Python dependencies
- `setup.py` – Package configuration

## Coding Conventions

- Follow PEP 8 Python style guidelines
- Use type hints for function parameters and return values
- Add comprehensive docstrings to all public classes and methods
- Use descriptive variable and function names
- Keep functions focused and small
- Use abstract base classes for extensibility
- Separate concerns: capture, decide, execute
- All user-facing strings should be clear and descriptive
- Add inline comments for complex logic only

## Architecture Patterns

- **Modular Design**: Each component (capture, AI, executor) is independent
- **Abstract Base Classes**: Use ABC for extensibility (AIDecisionEngine, ActionExecutor)
- **Enumerated Actions**: All decisions must be GameAction enum values
- **Orchestrator Pattern**: GameAutomator coordinates all components
- **Mocked Implementations**: Provide mocked versions for testing (MockedAIDecisionEngine, MockedActionExecutor)

## Contribution Workflow

- Branch from `main` for all changes
- Open pull requests against `main`
- Reference the related GitHub issue in every pull request description
- Update documentation when adding features
- Verify Python syntax with `python -m py_compile`
- Test changes with example scripts (if display is available)

## Documentation Requirements

When adding or modifying features:
- Update `README.md` for major features
- Update `docs/README.md` for detailed usage changes
- Update `docs/API_REFERENCE.md` for API changes
- Update `docs/IMPLEMENTATION_PLAN.md` if adding to roadmap
- Update `CHANGELOG.md` with your changes
- Add docstrings to new classes and methods

## Testing

- Verify Python syntax: `python -m py_compile src/playtester/*.py`
- Test manually with examples (requires display environment)
- For headless testing, test core logic without GUI components

## Important Notes

- This framework is designed to integrate with open-source AI models
- Current AI decision engine is mocked - see IMPLEMENTATION_PLAN.md for integration guidance
- Screenshot capture requires a display environment (not headless compatible)
- Follow the existing patterns when adding new games or executors
