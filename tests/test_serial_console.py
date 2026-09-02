from __future__ import annotations

import os
import string
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
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QToolButton,
)

from protocol_core import encode_frame
from serial_console import (
    AboutDialog,
    COMMON_BAUDRATES,
    LANGUAGE_OPTIONS,
    MAX_RX_FRAMES_PER_POLL,
    MAX_TRAFFIC_ROWS,
    LOGO_PATH,
    SKILL_DOWNLOAD_URL,
    SKILL_PROJECT_URL,
    SerialConsole,
    UI_TEXT,
    VariableInputDialog,
    VirtualPortDialog,
    version_key,
)

AT32_REALTIME_FRAME = bytes.fromhex(
    "AA 55 10 25 EA 07 09 02 0C 02 1A 93 02 7C FF FF FF 9B FF FF FF "
    "5B 00 00 00 D2 FF FF FF 45 FF 9C 00 1B 10 43 00 12 00 06 00 8F"
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

    def test_skill_buttons_open_download_and_guide_urls(self) -> None:
        dialog = AboutDialog("zh")
        guide = dialog.findChild(QPlainTextEdit)
        self.assertIn("技能新建", guide.toPlainText())
        self.assertIn("Skill ZIP", guide.toPlainText())

        with patch("serial_console.open_external_url", return_value=True) as opener:
            QTest.mouseClick(dialog.findChild(QPushButton, "skillDownloadButton"), Qt.MouseButton.LeftButton)
            QTest.mouseClick(dialog.findChild(QPushButton, "skillGuideButton"), Qt.MouseButton.LeftButton)
        self.assertEqual(opener.call_args_list[0].args, (SKILL_DOWNLOAD_URL,))
        self.assertEqual(opener.call_args_list[1].args, (SKILL_PROJECT_URL,))
        dialog.close()

    def test_language_selector_exposes_ten_languages_and_retranslates(self) -> None:
        window = SerialConsole()
        self.assertEqual(window.language_combo.count(), 10)
        self.assertEqual(
            tuple(window.language_combo.itemData(i) for i in range(10)),
            tuple(code for code, _ in LANGUAGE_OPTIONS),
        )

        spanish_index = window.language_combo.findData("es")
        window.language_combo.setCurrentIndex(spanish_index)
        self.app.processEvents()
        self.assertEqual(window.language, "es")
        self.assertEqual(window.windowTitle(), "Probador de protocolos serie")
        self.assertEqual(window.load_button.text(), "Cargar protocolo")
        window.close()

    def test_all_languages_cover_every_key_and_preserve_placeholders(self) -> None:
        formatter = string.Formatter()
        english_keys = set(UI_TEXT["en"])
        for language, _name in LANGUAGE_OPTIONS:
            self.assertEqual(set(UI_TEXT[language]), english_keys)
            for key, english_value in UI_TEXT["en"].items():
                translated_value = UI_TEXT[language][key]
                if not isinstance(english_value, str):
                    continue
                english_fields = {field for _text, field, _spec, _conversion in formatter.parse(english_value) if field}
                translated_fields = {
                    field for _text, field, _spec, _conversion in formatter.parse(translated_value) if field
                }
                self.assertEqual(translated_fields, english_fields, f"{language}.{key}")

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

    def test_realtime_history_is_bounded_and_details_refresh_on_demand(self) -> None:
        window = SerialConsole()
        frame_spec = {
            "repeat_group": "measurement",
            "decode": [
                {
                    "name": "value",
                    "label": "值",
                    "purpose": "实时值",
                    "offset": 0,
                    "length": 1,
                    "type": "uint8",
                }
            ],
        }
        command = {"name": "实时数据"}
        with patch.object(window, "_render_frame_details", wraps=window._render_frame_details) as render:
            for value in range(MAX_TRAFFIC_ROWS + 525):
                window._append_log("RX", bytes([value & 0xFF]), command, frame_spec)

        self.assertLessEqual(window.log_table.rowCount(), MAX_TRAFFIC_ROWS)
        self.assertEqual(len(window.log_entries), window.log_table.rowCount())
        self.assertEqual(render.call_count, 0)
        self.assertEqual(window.decoded_table.rowCount(), 0)
        self.assertIn("刷新解析", window.decoded_fields_label.text())

        QTest.mouseClick(window.refresh_details_button, Qt.MouseButton.LeftButton)
        self.app.processEvents()
        self.assertEqual(window.decoded_table.item(0, 4).text(), f"{(MAX_TRAFFIC_ROWS + 524) & 0xFF:02X}")
        window.close()

    def test_follow_latest_is_explicit_and_returns_to_the_newest_row(self) -> None:
        window = SerialConsole()
        window.show()
        frame_spec = {"repeat_group": "measurement", "decode": []}
        command = {"name": "实时数据"}
        for value in range(1, 80):
            window._append_log("RX", bytes([value]), command, frame_spec)
        self.app.processEvents()
        self.assertEqual(window.log_table.currentRow(), window.log_table.rowCount() - 1)
        self.assertEqual(window.log_table.verticalScrollBar().value(), window.log_table.verticalScrollBar().maximum())

        window.follow_latest_checkbox.setChecked(False)
        window.log_table.selectRow(0)
        self.app.processEvents()
        self.assertFalse(window.auto_follow_log)

        for value in range(80, 90):
            window._append_log("RX", bytes([value]), command, frame_spec)
        self.assertEqual(window.log_table.currentRow(), 0)

        window.follow_latest_checkbox.setChecked(True)
        self.app.processEvents()
        self.assertTrue(window.auto_follow_log)
        self.assertEqual(window.log_table.currentRow(), window.log_table.rowCount() - 1)
        self.assertEqual(window.log_table.verticalScrollBar().value(), window.log_table.verticalScrollBar().maximum())
        window.close()

    def test_received_frame_queue_has_a_per_poll_budget(self) -> None:
        window = SerialConsole()
        window.pending_rx_frames.extend([b"\x01"] * (MAX_RX_FRAMES_PER_POLL + 5))
        with patch.object(window, "_handle_received_frame") as handler:
            window._drain_received_frames()
        self.assertEqual(handler.call_count, MAX_RX_FRAMES_PER_POLL)
        self.assertEqual(len(window.pending_rx_frames), 5)
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

    def test_serial_url_drains_burst_of_realtime_frames_without_loss(self) -> None:
        window = SerialConsole()
        window.protocol = {
            "name": "AT32 实时测试",
            "serial": {
                "defaults": {"baudrate": 115200, "bytesize": 8, "parity": "N", "stopbits": 1, "timeout_ms": 200}
            },
            "framing": {
                "header": "AA 55",
                "length_offset": 3,
                "length_size": 1,
                "payload_offset": 4,
                "checksum_length": 1,
                "max_frame_length": 260,
            },
            "frames": [
                {
                    "id": "realtime",
                    "name": "实时数据",
                    "repeat_group": "measurement",
                    "match": {"offset": 2, "data": "10"},
                    "decode": [],
                }
            ],
            "commands": [],
        }
        window.role_combo.setCurrentIndex(window.role_combo.findData("host"))
        window.transport_combo.setCurrentIndex(window.transport_combo.findData("serial"))
        window.port_combo.setEditText("loop://")
        window._set_baudrate_value(115200)
        window._open_connection()
        self.assertTrue(window.connected)

        frame_count = MAX_RX_FRAMES_PER_POLL * 2
        window.serial_port.write(AT32_REALTIME_FRAME * frame_count)
        window.serial_port.flush()
        QTest.qWait(500)

        received = [entry for entry in window.log_entries if entry["direction"] == "RX"]
        self.assertEqual(len(received), frame_count)
        self.assertTrue(all(entry["data"] == AT32_REALTIME_FRAME for entry in received))
        self.assertFalse(window.pending_rx_frames)
        window.close()

    def test_host_mode_explains_why_received_request_is_not_replied_to(self) -> None:
        window = SerialConsole()
        command = window.protocol["commands"][0]
        window._handle_received_frame(encode_frame(command["request"]))
        self.assertIn("下位机", window.statusBar().currentMessage())
        window.close()


if __name__ == "__main__":
    unittest.main()
