"""Serial Protocol Assistant application package.

The GUI modules are intentionally not imported here so that metadata and
packaging tools can import the package without a Qt installation.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

__version__ = "1.4.1"

# This project's modules import each other by top-level name (for example
# ``from protocol_core import ...``). When installed as a package, make this
# directory importable so those imports keep working. Script/PyInstaller
# launches already have the directory on sys.path.
_MODULE_DIR = str(_Path(__file__).resolve().parent)
if _MODULE_DIR not in _sys.path:
    _sys.path.insert(0, _MODULE_DIR)

__all__ = ["__version__"]
