#!/usr/bin/env bash
# Launch Serial Protocol Assistant from source on Linux / macOS.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$ROOT/.venv"
PYTHON="$VENV/bin/python"

# Pick the first interpreter >= 3.10 (macOS may ship an older python3).
find_python() {
    for candidate in python3.13 python3.12 python3.11 python3.10 \
        /opt/homebrew/bin/python3 /usr/local/bin/python3 python3; do
        if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' \
            >/dev/null 2>&1; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
}

BASE_PYTHON="$(find_python || true)"
if [ -z "$BASE_PYTHON" ]; then
    echo "Python 3.10+ is required but was not found (python3: $(python3 --version 2>&1 || true))" >&2
    exit 1
fi

if [ ! -x "$PYTHON" ]; then
    if ! "$BASE_PYTHON" -m venv "$VENV"; then
        echo "Could not create a virtual environment at $VENV." >&2
        echo "Install venv support (e.g. 'sudo apt install python3-venv')," >&2
        echo "or use: python -m pip install . && serial-protocol-assistant" >&2
        exit 1
    fi
fi

# Check the GUI dependencies too, not just package importability.
if ! "$PYTHON" -c "import PySide6, serial, serial_protocol_assistant" >/dev/null 2>&1; then
    "$PYTHON" -m pip install --upgrade pip
    "$PYTHON" -m pip install -e "$ROOT"
fi

exec "$PYTHON" -m serial_protocol_assistant "$@"
