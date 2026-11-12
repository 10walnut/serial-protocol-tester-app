from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = PROJECT_ROOT / "app"
sys.path.insert(0, str(APP_ROOT))

try:
    from PySide6.QtCore import QSettings, Qt
    from PySide6.QtWidgets import QApplication

    from serial_console import (  # noqa: E402
        PortInfo,
        PosixVirtualPortDialog,
        SerialConsole,
        default_endpoint_placeholder,
        posix_virtual_ports_supported,
        resource_root,
    )
    from serial_ports import is_posix  # noqa: E402

    PYSIDE_AVAILABLE = True
except ImportError:  # pragma: no cover - GUI dependency is optional for pure tests
    PYSIDE_AVAILABLE = False


@unittest.skipUnless(PYSIDE_AVAILABLE, "PySide6 is required for GUI integration tests")
class CrossPlatformConsoleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        settings = QSettings(str(Path(directory.name) / "ui.ini"), QSettings.Format.IniFormat)
        factory = patch("serial_console.QSettings", return_value=settings)
        factory.start()
        self.addCleanup(factory.stop)

    def test_resource_root_prefers_pyinstaller_bundle(self) -> None:
        with tempfile.TemporaryDirectory(prefix="meipass-") as bundle:
            with patch.object(sys, "_MEIPASS", bundle, create=True):
                self.assertEqual(resource_root(), Path(bundle))

    def test_resource_root_falls_back_to_module_directory(self) -> None:
        with patch.object(sys, "_MEIPASS", None, create=True):
            root = resource_root()
        self.assertTrue((root / "sample_protocol.json").is_file())

    def test_placeholder_uses_platform_helper(self) -> None:
        for expected in ("/dev/cu.example", "COM7 or loop://"):
            with self.subTest(expected=expected), patch(
                "serial_console.default_endpoint_placeholder", return_value=expected
            ):
                window = SerialConsole()
                self.addCleanup(window.close)
                self.assertEqual(window.port_combo.placeholderText(), expected)
        with patch("serial_ports.sys.platform", "linux"), patch(
            "serial_ports.os.name", "posix"
        ):
            self.assertEqual(default_endpoint_placeholder(), "/dev/ttyUSB0 or loop://")
        self.assertIsInstance(is_posix(), bool)

    def test_refresh_ports_uses_cross_platform_enumeration(self) -> None:
        with patch(
            "serial_console.list_serial_ports",
            return_value=[PortInfo("/dev/ttyUSB0", "USB Serial")],
        ):
            window = SerialConsole()
            self.addCleanup(window.close)
            window._refresh_ports()
        self.assertEqual(window.port_combo.count(), 1)
        self.assertEqual(window.port_combo.itemText(0), "/dev/ttyUSB0")
        self.assertIn(
            "USB Serial",
            str(window.port_combo.itemData(0, Qt.ItemDataRole.ToolTipRole)),
        )

    def test_open_connection_validates_endpoint_before_calling_pyserial(self) -> None:
        window = SerialConsole()
        self.addCleanup(window.close)
        index = window.transport_combo.findData("serial")
        window.transport_combo.setCurrentIndex(index)
        window.port_combo.setEditText("COM 3")
        with patch("serial_console.QMessageBox.critical") as message, patch(
            "serial_console.serial.serial_for_url"
        ) as factory:
            window._open_connection()
        self.assertFalse(window.connected)
        factory.assert_not_called()
        message.assert_called_once()

    def test_posix_backend_helpers_are_importable(self) -> None:
        self.assertIsInstance(posix_virtual_ports_supported(), bool)
        self.assertTrue(hasattr(PosixVirtualPortDialog, "_create_pair"))

    def test_virtual_ports_button_uses_posix_dialog(self) -> None:
        window = SerialConsole()
        self.addCleanup(window.close)
        with patch("serial_console.is_posix", return_value=True), patch.object(
            PosixVirtualPortDialog, "exec", return_value=0
        ) as dialog_exec:
            window._show_virtual_ports()
        dialog_exec.assert_called_once()

    def test_virtual_pair_is_released_on_demand(self) -> None:
        window = SerialConsole()
        self.addCleanup(window.close)
        pair = Mock()
        window._replace_virtual_pair(pair)
        self.assertIs(window.virtual_pair, pair)
        window._release_virtual_pair()
        pair.close.assert_called_once()
        self.assertIsNone(window.virtual_pair)

    def test_refresh_ports_includes_virtual_pair_endpoints(self) -> None:
        window = SerialConsole()
        self.addCleanup(window.close)
        pair = Mock()
        pair.active = True
        pair.endpoints.return_value = ("/tmp/serial-pair/ttyA", "/tmp/serial-pair/ttyB")
        window._replace_virtual_pair(pair)
        with patch("serial_console.list_serial_ports", return_value=[]):
            window._refresh_ports()
        self.assertEqual(
            [window.port_combo.itemText(i) for i in range(window.port_combo.count())],
            ["/tmp/serial-pair/ttyA", "/tmp/serial-pair/ttyB"],
        )

    def test_virtual_ports_dialog_is_locked_while_connected(self) -> None:
        window = SerialConsole()
        self.addCleanup(window.close)
        pair = Mock()
        pair.active = True
        pair.port_a = "/tmp/ttyA"
        pair.port_b = "/tmp/ttyB"
        pair.endpoints.return_value = ("/tmp/ttyA", "/tmp/ttyB")
        window._replace_virtual_pair(pair)
        window.connected = True
        seen = {}

        def fake_exec(dialog: Any) -> int:
            seen["dialog"] = dialog
            return 0

        with patch("serial_console.is_posix", return_value=True), patch.object(
            PosixVirtualPortDialog, "exec", new=fake_exec
        ):
            window._show_virtual_ports()
        dialog = seen["dialog"]
        self.assertTrue(dialog.locked)
        self.assertFalse(dialog.create_button.isEnabled())
        self.assertFalse(dialog.release_button.isEnabled())
        text = dialog.status_label.text()
        self.assertTrue("断开" in text or "disconnect" in text.lower(), text)
        self.assertIs(window.virtual_pair, pair)
        pair.close.assert_not_called()

    def test_replacing_connected_virtual_pair_disconnects_first(self) -> None:
        window = SerialConsole()
        self.addCleanup(window.close)
        pair = Mock()
        pair.active = True
        pair.endpoints.return_value = ("/tmp/ttyA", "/tmp/ttyB")
        window._replace_virtual_pair(pair)
        window.port_combo.setEditText("/tmp/ttyA")
        window.connected = True
        with patch.object(window, "_close_connection") as close_connection:
            window._replace_virtual_pair(None)
        close_connection.assert_called_once()
        pair.close.assert_called_once()
        self.assertIsNone(window.virtual_pair)


if __name__ == "__main__":
    unittest.main()
