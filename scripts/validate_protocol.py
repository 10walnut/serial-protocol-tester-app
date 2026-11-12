#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = PROJECT_ROOT / "app"
sys.path.insert(0, str(APP_ROOT))

from protocol_core import (  # noqa: E402
    ProtocolError,
    read_json_file,
    validate_protocol_data,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a serial_protocol.v1 JSON file.")
    parser.add_argument("protocol", type=Path, help="Path to the protocol JSON file")
    args = parser.parse_args()

    try:
        data = read_json_file(args.protocol, label=str(args.protocol))
    except ProtocolError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    errors = validate_protocol_data(data)
    if errors:
        print(f"INVALID: {args.protocol}", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    command_count = len(data["commands"])
    print(f"OK: {args.protocol} ({command_count} commands, schema serial_protocol.v1)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
