from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = PROJECT_ROOT / "app"
sys.path.insert(0, str(APP_ROOT))

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QToolButton

from serial_console import SerialConsole, VariableInputDialog


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


if __name__ == "__main__":
    unittest.main()
