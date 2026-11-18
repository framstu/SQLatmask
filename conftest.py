"""Make the project modules importable no matter how pytest is invoked.

``pytest`` only adds the directory of a test file to ``sys.path`` when that
directory has no ``__init__.py``, so the repository root needs to be added
explicitly - otherwise ``import cmds`` fails for ``pytest`` while
``python -m pytest`` happens to work.
"""

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
