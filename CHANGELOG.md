# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Alignment with DPC (Dans Plugins Community) conventions
- CONTRIBUTING.md with contribution guidelines
- USER_GUIDE.md with comprehensive usage instructions
- CHANGELOG.md for tracking changes
- LICENSE file (GPL-3.0)
- GitHub Actions workflows for CI/CD
- Copilot instructions for better AI assistance

## [0.1.0] - 2025-12-28

### Added
- Initial release of Playtester framework
- Screenshot capture system with full screen and region support
- AI decision engine interface with GameAction enumeration
- MockedAIDecisionEngine for testing and demonstration
- Action executor system with keyboard support
- KeyboardActionExecutor with configurable key mappings
- MockedActionExecutor for testing without actual input
- Game automator orchestrating the automation loop
- Ophidian game-specific automator (mocked implementation)
- Roam game-specific automator (mocked implementation)
- Comprehensive documentation suite
  - README.md with project overview
  - docs/README.md with full usage guide
  - docs/API_REFERENCE.md with complete API documentation
  - docs/IMPLEMENTATION_PLAN.md with future roadmap
  - docs/ARCHITECTURE.md with system design diagrams
- Example scripts demonstrating framework usage
  - basic_example.py - Basic automation demo
  - ophidian_example.py - Ophidian game automation
  - roam_example.py - Roam game automation
- Python package setup with setup.py
- Dependencies: pillow, pyautogui, pynput

### Documented
- Desired behavior for AI integration with open-source models (LLaVA, CLIP, MiniGPT-4, OpenFlamingo)
- Game-specific implementation patterns
- Extensibility points for custom games and AI engines
