"""``python3 -m playtester``: the ``pt`` harness command line."""

import sys

from .harness.cli import main

sys.exit(main())
