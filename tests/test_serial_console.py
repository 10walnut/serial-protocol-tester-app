from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = PROJECT_ROOT / "app"
sys.path.insert(0, str(APP_ROOT))

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractSpinBox, QApplication, QLabel, QTabWidget, QToolButton

from protocol_core import encode_frame
from serial_console import (
    AboutDialog,
    COMMON_BAUDRATES,
    LOGO_PATH,
    SerialConsole,
    VariableInputDialog,
    VirtualPortDialog,
    version_key,
)


class SerialConsoleUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_explicit_increment_and_decrement_buttons(self) -> None:
        frame = {
            "variables": [
                {
                    "name": "count",
                    "label": "次数",
                    "type": "integer",
                    "default": 2,
                    "min": 1,
                    "max": 4,
                    "step": 1,
                }
            ],
            "encode": [],
        }
        dialog = VariableInputDialog(frame, "测试", "zh")
        value_widget = dialog.widgets["count"]
        increase = dialog.findChild(QToolButton, "increase_count")
        decrease = dialog.findChild(QToolButton, "decrease_count")
        self.assertIsNotNone(increase)
        self.assertIsNotNone(decrease)

        QTest.mouseClick(increase, Qt.MouseButton.LeftButton)
        self.app.processEvents()
        self.assertEqual(value_widget.value(), 3)
        QTest.mouseClick(decrease, Qt.MouseButton.LeftButton)
        self.app.processEvents()
        self.assertEqual(value_widget.value(), 2)
        dialog.close()

    def test_selecting_history_row_redecodes_that_frame(self) -> None:
        window = SerialConsole()
        frame_spec = {
            "decode": [
                {
                    "name": "value",
                    "label": "值",
                    "purpose": "测试历史数据选择",
                    "offset": 0,
                    "length": 1,
                    "type": "uint8",
                }
            ]
        }
        command = {"name": "历史命令"}
        window._append_log("TX", b"\x11", command, frame_spec)
        window._append_log("RX", b"\x22", command, frame_spec)
        self.assertEqual(window.log_table.currentRow(), 1)
        self.assertEqual(window.decoded_table.item(0, 4).text(), "22")

        window.log_table.selectRow(0)
        self.app.processEvents()
        self.assertEqual(window.decoded_table.item(0, 0).text(), "TX")
        self.assertEqual(window.decoded_table.item(0, 4).text(), "11")
        self.assertIn("TX", window.decoded_fields_label.text())
        window.close()

    def test_internal_device_sends_ack_then_periodic_frames_until_stop(self) -> None:
        window = SerialConsole()
        window._open_connection()
        start = next(item for item in window.protocol["commands"] if item["id"] == "start_temperature_stream")
        stop = next(item for item in window.protocol["commands"] if item["id"] == "stop_temperature_stream")

        window._receive_internal_response(start)
        self.assertEqual(window.log_entries[-1]["data"], b"OK,STREAM\r\n")
        QTest.qWait(240)
        streamed = [entry for entry in window.log_entries if entry["data"] == b"TEMP,25.0\r\n"]
        self.assertGreaterEqual(len(streamed), 2)

        window._receive_internal_response(stop)
        count_after_stop = len([entry for entry in window.log_entries if entry["data"] == b"TEMP,25.0\r\n"])
        QTest.qWait(220)
        self.assertEqual(
            len([entry for entry in window.log_entries if entry["data"] == b"TEMP,25.0\r\n"]),
            count_after_stop,
        )
        window.close()

    def test_about_dialog_loads_brand_and_donation_assets(self) -> None:
        self.assertTrue(LOGO_PATH.is_file())
        self.assertGreater(version_key("v1.2.0"), version_key("1.1.9"))
        dialog = AboutDialog("zh")
        self.assertIn("关于", dialog.windowTitle())
        self.assertTrue(dialog.update_button.isEnabled())
        tabs = dialog.findChild(QTabWidget)
        self.assertEqual(tabs.count(), 3)
        for name in ("qr_donate-alipay", "qr_donate-wechat"):
            qr_label = dialog.findChild(QLabel, name)
            self.assertIsNotNone(qr_label)
            self.assertIsNotNone(qr_label.pixmap())
            self.assertEqual(qr_label.pixmap().size().width(), 290)
            self.assertEqual(qr_label.pixmap().size().height(), 290)
        dialog.close()

    def test_baudrate_is_preloaded_editable_and_manual_value_is_preserved(self) -> None:
        window = SerialConsole()
        self.assertTrue(window.baudrate_combo.isEditable())
        self.assertIn(115200, COMMON_BAUDRATES)
        self.assertEqual(window.baudrate_combo.currentText(), "9600")

        window.baudrate_combo.setEditText("57600")
        window._commit_baudrate_edit()
        command = next(item for item in window.protocol["commands"] if item["id"] == "ascii_status")
        window._set_command_baudrate(command)
        self.assertEqual(window._current_baudrate(), 57600)

        window.baudrate_user_edited = False
        window._set_command_baudrate(command)
        self.assertEqual(window._current_baudrate(), 115200)
        window.close()

    def test_virtual_port_numbers_use_explicit_working_step_buttons(self) -> None:
        with patch.object(VirtualPortDialog, "_refresh_driver_state"):
            dialog = VirtualPortDialog("zh", lambda: None)
        increase = dialog.findChild(QToolButton, "increase_port_a")
        decrease = dialog.findChild(QToolButton, "decrease_port_a")
        self.assertEqual(dialog.port_a_spin.buttonSymbols(), QAbstractSpinBox.ButtonSymbols.NoButtons)
        QTest.mouseClick(increase, Qt.MouseButton.LeftButton)
        self.assertEqual(dialog.port_a_spin.value(), 11)
        QTest.mouseClick(decrease, Qt.MouseButton.LeftButton)
        self.assertEqual(dialog.port_a_spin.value(), 10)
        dialog.close()

    def test_serial_url_device_receives_request_and_sends_automatic_reply(self) -> None:
        window = SerialConsole()
        window.role_combo.setCurrentIndex(window.role_combo.findData("device"))
        window.transport_combo.setCurrentIndex(window.transport_combo.findData("serial"))
        window.port_combo.setEditText("loop://")
        window._open_connection()
        self.assertTrue(window.connected)

        command = window.protocol["commands"][0]
        request = encode_frame(command["request"])
        expected_response = encode_frame(command["response"])
        window.serial_port.write(request)
        window.serial_port.flush()
        QTest.qWait(260)

        self.assertTrue(any(entry["direction"] == "RX" and entry["data"] == request for entry in window.log_entries))
        self.assertTrue(
            any(entry["direction"] == "TX" and entry["data"] == expected_response for entry in window.log_entries)
        )
        window.close()

    def test_host_mode_explains_why_received_request_is_not_replied_to(self) -> None:
        window = SerialConsole()
        command = window.protocol["commands"][0]
        window._handle_received_frame(encode_frame(command["request"]))
        self.assertIn("下位机", window.statusBar().currentMessage())
        window.close()


if __name__ == "__main__":
    unittest.main()
