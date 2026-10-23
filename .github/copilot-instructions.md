# Copilot Instructions

Read [CLAUDE.md](../CLAUDE.md) before making changes: it describes this
repository's two parts, its build and test commands, layout, architecture and
conventions. [CONTRIBUTING.md](../CONTRIBUTING.md) describes the contribution
workflow.

In short:

- **The agent playtest kit** (`src/playtester/harness/`, `src/playtester/agents/`,
  the `pt` command) is standard-library Python 3.8+ that drives games in Xvfb
  with xdotool and ImageMagick. Keep it free of third-party imports.
- **The screenshot automation framework** (`GameAutomator` and friends) is
  experimental; its decision engine is mocked. Its dependencies (pillow,
  pyautogui, pynput) are the `automation` extra.
- Test with `python -m unittest discover -s tests -t .` and
  `python -m py_compile src/playtester/*.py src/playtester/*/*.py examples/*.py ci/*.py tests/*.py`.
- Keep code Python 3.8 compatible, follow PEP 8, add docstrings to public
  classes and methods, and add a `CHANGELOG.md` entry for user-facing changes.
- Branch from `main` and open pull requests against `main`.
