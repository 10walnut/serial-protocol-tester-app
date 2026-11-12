"""Allow ``python -m serial_protocol_assistant`` to launch the GUI."""

from __future__ import annotations

# Import through the package so console-script and -m launches share the same
# module identity (see app/__init__.py for the sibling-module path setup).
from .serial_console import main

raise SystemExit(main())
