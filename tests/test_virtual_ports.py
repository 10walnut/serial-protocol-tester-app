from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = PROJECT_ROOT / "app"
sys.path.insert(0, str(APP_ROOT))

from virtual_ports import (  # noqa: E402
    VirtualPortError,
    build_install_arguments,
    count_unassigned_ports,
    find_setupc,
    normalize_com_name,
    parse_com0com_pnp_problems,
    virtual_ports_ready,
)


class VirtualPortTests(unittest.TestCase):
    def test_normalize_com_name(self) -> None:
        self.assertEqual(normalize_com_name(" com10 "), "COM10")
        self.assertEqual(normalize_com_name(256), "COM256")

    def test_invalid_com_name(self) -> None:
        for value in ("COM0", "COM257", "CNCA0", "10"):
            with self.subTest(value=value), self.assertRaises(VirtualPortError):
                normalize_com_name(value)

    def test_install_arguments(self) -> None:
        self.assertEqual(
            build_install_arguments("COM10", "COM11"),
            [
                "install",
                "PortName=COM10",
                "PortName=COM11",
            ],
        )
        with self.assertRaises(VirtualPortError):
            build_install_arguments("COM10", "COM10")

    def test_find_explicit_setupc(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            setupc = Path(directory) / "setupc.exe"
            setupc.touch()
            self.assertEqual(find_setupc(setupc), setupc.resolve())

    def test_parse_unsigned_driver_problems(self) -> None:
        output = """
Instance ID:                ROOT\\COM0COM\\0000
Device Description:         com0com - bus for serial port pair emulator
Status:                     Problem
Problem Code:               52 (0x34) [CM_PROB_UNSIGNED_DRIVER]

Instance ID:                ROOT\\OTHER\\0000
Device Description:         Other device
Problem Code:               10 (0x0A) [CM_PROB_FAILED_START]
"""
        problems = parse_com0com_pnp_problems(output)
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0].instance_id, r"ROOT\COM0COM\0000")
        self.assertEqual(problems[0].code, 52)
        self.assertEqual(problems[0].symbol, "CM_PROB_UNSIGNED_DRIVER")

    def test_unassigned_and_ready_ports(self) -> None:
        incomplete = "CNCA0 PortName=COM#\nCNCB0 PortName=COM#,RealPortName=COM11"
        self.assertEqual(count_unassigned_ports(incomplete), 1)
        self.assertTrue(virtual_ports_ready("COM10", "COM11", ["COM10", "COM11"]))
        self.assertTrue(
            virtual_ports_ready(
                "COM10",
                "COM11",
                [],
                "CNCA0 PortName=COM10\nCNCB0 PortName=COM11",
            )
        )
        self.assertFalse(virtual_ports_ready("COM10", "COM11", ["COM10"]))


if __name__ == "__main__":
    unittest.main()
