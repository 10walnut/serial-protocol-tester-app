from __future__ import annotations

import sys
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = PROJECT_ROOT / "app"
sys.path.insert(0, str(APP_ROOT))

from serial_ports import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    POSIX_PORT_GLOBS,
    URL_SCHEMES,
    PortInfo,
    default_endpoint_placeholder,
    explain_open_error,
    is_posix,
    list_serial_ports,
    normalize_endpoint,
    permission_hint,
    platform_name,
    validate_endpoint,
)


@contextmanager
def fake_platform(platform: str, os_name: str) -> Iterator[None]:
    with patch("serial_ports.sys.platform", platform), patch(
        "serial_ports.os.name", os_name
    ):
        yield


def fake_port(device: str, description: str = "", hwid: str = "") -> SimpleNamespace:
    return SimpleNamespace(device=device, description=description, hwid=hwid)


PLATFORMS = (
    ("win32", "nt", "windows", False),
    ("linux", "posix", "linux", True),
    ("darwin", "posix", "macos", True),
    ("freebsd", "posix", "other", True),
    ("java", "java", "other", False),
)


class SerialPortsTests(unittest.TestCase):
    def test_platform_name_and_is_posix(self) -> None:
        for platform, os_name, expected_name, expected_posix in PLATFORMS:
            with self.subTest(platform=platform), fake_platform(platform, os_name):
                self.assertEqual(platform_name(), expected_name)
                self.assertEqual(is_posix(), expected_posix)

    def test_default_endpoint_placeholder_per_platform(self) -> None:
        expected = {
            "win32": "COM3 or loop://",
            "linux": "/dev/ttyUSB0 or loop://",
            "darwin": "/dev/cu.usbserial or loop://",
            "freebsd": "serial port or loop://",
        }
        for platform, os_name, _, _ in PLATFORMS:
            if platform not in expected:
                continue
            with self.subTest(platform=platform), fake_platform(platform, os_name):
                self.assertEqual(default_endpoint_placeholder(), expected[platform])

    def test_module_level_constants(self) -> None:
        self.assertIsInstance(URL_SCHEMES, frozenset)
        self.assertEqual(
            URL_SCHEMES,
            frozenset({"loop", "socket", "rfc2217", "spy", "alt", "hwgrep"}),
        )
        self.assertEqual(POSIX_PORT_GLOBS["macos"], ("/dev/cu.*", "/dev/tty.*"))
        for pattern in (
            "/dev/ttyUSB*",
            "/dev/ttyACM*",
            "/dev/ttyS[0-9]*",
            "/dev/ttyAMA*",
            "/dev/ttyXRUSB*",
            "/dev/serial/by-id/*",
        ):
            self.assertIn(pattern, POSIX_PORT_GLOBS["linux"])

    def test_normalize_endpoint_strips_and_macos_tty_to_cu(self) -> None:
        self.assertEqual(normalize_endpoint("  COM3  "), "COM3")
        with fake_platform("darwin", "posix"), patch(
            "serial_ports._path_exists", return_value=True
        ):
            self.assertEqual(
                normalize_endpoint("  /dev/tty.usbserial-0001  "),
                "/dev/cu.usbserial-0001",
            )
            self.assertEqual(
                validate_endpoint("/dev/tty.usbserial"), "/dev/cu.usbserial"
            )
        with fake_platform("darwin", "posix"), patch(
            "serial_ports._path_exists", return_value=False
        ):
            self.assertEqual(
                normalize_endpoint("/dev/tty.usbserial"), "/dev/tty.usbserial"
            )
        with fake_platform("win32", "nt"):
            self.assertEqual(
                normalize_endpoint("/dev/tty.usbserial"), "/dev/tty.usbserial"
            )

    def test_validate_endpoint_accepts_common_endpoints(self) -> None:
        common = (
            "COM3",
            "/dev/ttyUSB0",
            "/dev/cu.usbserial-0001",
            "/tmp/serial-pair-xxx/ttyA",
            "loop://",
            "socket://localhost:7000",
            "rfc2217://localhost:2217",
        )
        for platform, os_name, _, _ in PLATFORMS[:3]:
            with self.subTest(platform=platform), fake_platform(
                platform, os_name
            ), patch("serial_ports.os.lstat", side_effect=OSError):
                for endpoint in common:
                    with self.subTest(endpoint=endpoint):
                        self.assertEqual(validate_endpoint(endpoint), endpoint)
                self.assertEqual(validate_endpoint("  /dev/ttyUSB0\n"), "/dev/ttyUSB0")
                self.assertEqual(validate_endpoint("com256"), "com256")

    def test_validate_endpoint_rejects_invalid_values(self) -> None:
        invalid = (
            "",
            "   ",
            "COM 3",
            "COM0",
            "COM257",
            "http://example.com",
            "socket://",
            "://",
            "://target",
            "/dev/../etc/passwd",
            "endpoint\x00name",
        )
        with fake_platform("win32", "nt"):
            for value in invalid:
                with self.subTest(value=value), self.assertRaises(ValueError) as ctx:
                    validate_endpoint(value)
                self.assertTrue(str(ctx.exception))

    def test_windows_accepts_posix_looking_paths(self) -> None:
        with fake_platform("win32", "nt"):
            self.assertEqual(
                validate_endpoint("/dev/cu.usbserial-0001"),
                "/dev/cu.usbserial-0001",
            )
            self.assertEqual(
                validate_endpoint("/tmp/serial-pair-xxx/ttyA"),
                "/tmp/serial-pair-xxx/ttyA",
            )
            self.assertEqual(validate_endpoint("ttyUSB0"), "ttyUSB0")

    def test_posix_rejects_bare_device_names(self) -> None:
        for platform, os_name, _, _ in PLATFORMS[:3]:
            if platform == "win32":
                continue
            with self.subTest(platform=platform), fake_platform(platform, os_name):
                for value in ("ttyUSB0", "cu.usbserial", "relative/path"):
                    with self.subTest(value=value), self.assertRaises(ValueError) as ctx:
                        validate_endpoint(value)
                    self.assertIn("/dev", str(ctx.exception))

    def test_port_info_label(self) -> None:
        self.assertEqual(PortInfo("COM3").label, "COM3")
        self.assertEqual(PortInfo("COM3").hardware_id, "")
        self.assertEqual(
            PortInfo("/dev/ttyUSB0", "USB Serial", "USB VID:PID").label,
            "/dev/ttyUSB0 — USB Serial",
        )

    def test_list_serial_ports_windows_dedup_and_com_order(self) -> None:
        discovered = [
            fake_port("COM10", "USB Serial", "USB VID:PID"),
            fake_port("COM3"),
            fake_port("COM10"),
            "loop://",
            "/dev/tty",
        ]
        with fake_platform("win32", "nt"):
            result = list_serial_ports(comports=lambda: discovered)
        self.assertEqual(
            [port.device for port in result], ["COM3", "COM10", "loop://"]
        )
        self.assertEqual(result[0].description, "")
        self.assertEqual(result[0].hardware_id, "")
        self.assertEqual(result[1].description, "USB Serial")
        self.assertEqual(result[1].hardware_id, "USB VID:PID")

    def test_list_serial_ports_uses_patched_comports_and_getattr(self) -> None:
        with fake_platform("win32", "nt"), patch(
            "serial_ports.list_ports.comports",
            return_value=[SimpleNamespace(device="COM7"), "COM8"],
        ) as mocked:
            result = list_serial_ports()
        self.assertTrue(mocked.called)
        self.assertEqual([port.device for port in result], ["COM7", "COM8"])
        self.assertEqual(result[0].description, "")
        self.assertEqual(result[0].hardware_id, "")

    def test_list_serial_ports_posix_glob_and_priority(self) -> None:
        discovered = [
            fake_port("/dev/ttyS0", "Built-in serial"),
            fake_port("/dev/ttyACM0"),
            fake_port("/dev/ttyUSB0"),
            fake_port("/dev/ttyUSB0"),
            fake_port("/dev/tty"),
            fake_port("/dev/cu.usbserial-0001"),
        ]
        extra = {
            "/dev/ttyUSB*": ["/dev/ttyUSB1"],
            "/dev/ttyACM*": [],
            "/dev/ttyS[0-9]*": [],
            "/dev/ttyAMA*": ["/dev/ttyAMA0"],
            "/dev/ttyXRUSB*": ["/dev/ttyXRUSB0"],
            "/dev/serial/by-id/*": ["/dev/serial/by-id/usb-FTDI"],
        }
        with fake_platform("linux", "posix"), patch(
            "serial_ports.glob.glob", side_effect=lambda pattern: extra.get(pattern, [])
        ):
            result = list_serial_ports(comports=lambda: discovered)
        self.assertEqual(
            [port.device for port in result],
            [
                "/dev/cu.usbserial-0001",
                "/dev/ttyUSB0",
                "/dev/ttyUSB1",
                "/dev/ttyACM0",
                "/dev/ttyAMA0",
                "/dev/serial/by-id/usb-FTDI",
                "/dev/ttyXRUSB0",
                "/dev/ttyS0",
            ],
        )
        self.assertEqual(result[-1].description, "Built-in serial")

    def test_list_serial_ports_survives_provider_error(self) -> None:
        def broken() -> list[SimpleNamespace]:
            raise RuntimeError("boom")

        with fake_platform("linux", "posix"), patch(
            "serial_ports.glob.glob", return_value=["/dev/ttyUSB9", "/dev/tty"]
        ):
            result = list_serial_ports(comports=broken)
        self.assertEqual([port.device for port in result], ["/dev/ttyUSB9"])

    def test_permission_hint_platform_specific(self) -> None:
        with fake_platform("linux", "posix"):
            zh = permission_hint("/dev/ttyUSB0", language="zh")
            en = permission_hint("/dev/ttyUSB0", language="en")
        self.assertIn("dialout", zh)
        self.assertIn("uucp", zh)
        self.assertIn("sudo usermod -aG dialout $USER", zh)
        self.assertIn("udev", zh)
        self.assertIn("dialout", en)
        self.assertIn("udev", en)
        self.assertIn("log out", en.lower())
        self.assertNotEqual(zh, en)

        with fake_platform("darwin", "posix"):
            mac = permission_hint("/dev/tty.usbserial", language="zh")
        self.assertIn("/dev/cu.", mac)
        self.assertIn("CH340", mac)
        self.assertIn("CP210x", mac)
        self.assertIn("FTDI", mac)

        with fake_platform("win32", "nt"):
            win = permission_hint("COM3", language="en")
        self.assertIn("Device Manager", win)
        self.assertIn("driver", win.lower())
        self.assertIn("in use", win.lower())

        with fake_platform("freebsd", "posix"):
            self.assertTrue(permission_hint("/dev/ttyU0", language="zh"))

    def test_permission_hint_error_classification(self) -> None:
        with fake_platform("linux", "posix"):
            perm = permission_hint(
                "/dev/ttyUSB0", PermissionError(13, "Permission denied"), "zh"
            )
            missing = permission_hint(
                "/dev/ttyUSB0",
                FileNotFoundError(2, "No such file or directory"),
                "zh",
            )
            text_perm = permission_hint(
                "/dev/ttyUSB0", RuntimeError("Access is denied"), "en"
            )
            text_missing = permission_hint(
                "/dev/ttyUSB0", RuntimeError("No such file"), "en"
            )
        self.assertIn("权限", perm)
        self.assertIn("dialout", perm)
        self.assertIn("拔出", missing)
        self.assertIn("permission", text_perm.lower())
        self.assertIn("unplug", text_missing.lower())

    def test_permission_hint_none_error_missing_device(self) -> None:
        with fake_platform("linux", "posix"), patch(
            "serial_ports._path_exists", return_value=False
        ):
            hint = permission_hint("/dev/ttyUSB99", None, "zh")
        self.assertTrue(hint)
        self.assertIn("拔出", hint)
        self.assertIn("dialout", hint)

    def test_explain_open_error_appends_hint(self) -> None:
        error = PermissionError(13, "Permission denied")
        with fake_platform("linux", "posix"):
            text = explain_open_error("/dev/ttyUSB0", error, "zh")
        self.assertTrue(text.startswith(str(error)))
        self.assertIn("\n\n", text)
        self.assertIn("dialout", text)
        self.assertIn("权限", text)

        with patch("serial_ports.permission_hint", return_value=""):
            self.assertEqual(
                explain_open_error("/dev/ttyUSB0", error, "zh"), str(error)
            )
        self.assertEqual(explain_open_error("loop://", error, "zh"), str(error))

    def test_validate_endpoint_normalizes_url_scheme_and_rejects_nul(self) -> None:
        with fake_platform("win32", "nt"):
            self.assertEqual(validate_endpoint("LOOP://"), "loop://")
            self.assertEqual(
                validate_endpoint("SOCKET://localhost:7000"),
                "socket://localhost:7000",
            )
        with self.assertRaises(ValueError):
            validate_endpoint("loop://\x00name")

    def test_explain_open_error_skips_parameter_errors(self) -> None:
        error = ValueError("Invalid baudrate")
        with fake_platform("linux", "posix"):
            self.assertEqual(explain_open_error("/dev/ttyUSB0", error, "zh"), str(error))
        self.assertEqual(explain_open_error("loop://", error, "zh"), str(error))

    def test_normalize_endpoint_only_rewrites_macos_tty_devices(self) -> None:
        with fake_platform("linux", "posix"), patch(
            "serial_ports._path_exists", return_value=True
        ):
            self.assertEqual(
                normalize_endpoint("/dev/tty.usbserial"), "/dev/tty.usbserial"
            )
        with fake_platform("darwin", "posix"), patch(
            "serial_ports._path_exists", return_value=True
        ):
            self.assertEqual(
                normalize_endpoint("/dev/tty.usbserial"), "/dev/cu.usbserial"
            )


if __name__ == "__main__":
    unittest.main()
