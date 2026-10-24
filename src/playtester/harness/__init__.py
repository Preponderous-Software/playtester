"""The agent playtest harness: isolated headless sessions of a real game, driven like a player.

Standard library only (it shells out to Xvfb, xdotool and ImageMagick, or,
with the Strata driver, talks to a Strata game's drive channel), so it works
without a display and without the optional GUI dependencies the
screenshot -> decision engine -> executor loop needs. The command line is
``pt`` (``playtester.harness.cli``); see docs/AGENT_PLAYTESTING.md.
"""

from .profile import ProfileError, available, load as load_profile
from .session import HarnessError, Session

__all__ = ["HarnessError", "ProfileError", "Session", "available", "load_profile"]
