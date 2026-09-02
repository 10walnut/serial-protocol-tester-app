from __future__ import annotations

import struct
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ICON_PATH = ROOT / "app" / "assets" / "serial-protocol-tester-logo.ico"


class AssetTests(unittest.TestCase):
    def test_windows_icon_contains_standard_shell_sizes(self) -> None:
        data = ICON_PATH.read_bytes()
        reserved, kind, count = struct.unpack_from("<HHH", data, 0)
        self.assertEqual((reserved, kind), (0, 1))
        sizes = set()
        for index in range(count):
            width, height = struct.unpack_from("<BB", data, 6 + index * 16)
            sizes.add((width or 256, height or 256))
        self.assertTrue({(16, 16), (24, 24), (32, 32), (48, 48), (256, 256)}.issubset(sizes))


if __name__ == "__main__":
    unittest.main()
