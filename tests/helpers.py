"""Shared test helpers: the package on sys.path, fixture paths."""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "src")
FIXTURE_RUN = os.path.join(HERE, "fixtures", "run")
if SRC not in sys.path:
    sys.path.insert(0, SRC)
sys.dont_write_bytecode = True
