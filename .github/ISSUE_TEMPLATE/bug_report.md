---
name: Bug report
about: Something in playtester does not work as documented
title: ''
labels: bug
assignees: ''
---

**What happened**
A clear description of the bug.

**What you expected**
What should have happened instead.

**How to reproduce**
The commands you ran, for example:

```bash
PT_ROOT=/tmp/pt-try pt smoke --profile demo
```

**Which part**
- [ ] The agent playtest kit (`pt`, profiles, probe, reports, aggregation)
- [ ] The screenshot automation framework (`GameAutomator`, presets)

**Environment**
- playtester version or commit (`pt --version`, `git rev-parse --short HEAD`):
- Python version (`python3 --version`):
- OS (and WSL2 or not):
- Game and profile, if any:

**Logs and screenshots**
Relevant output, the session's `game.log` / `xvfb.log`, or screenshots. Remove
anything private before posting.
