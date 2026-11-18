"""SQLatmask - query JSON tables with a small SQL dialect on top of pandas.

The submodules are imported here so that ``from sqlatmask import cmds`` works
and so that a fresh install can be checked with a single import.
"""

__version__ = "0.2.0"

from . import cmds, iodata, queryparser, shelp, where  # noqa: F401  (public API)

__all__ = ["cmds", "iodata", "queryparser", "shelp", "where", "__version__"]
