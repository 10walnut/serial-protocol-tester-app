from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPlainTextEdit

from serial_console import AboutDialog, LANGUAGE_OPTIONS, SerialConsole, VariableInputDialog, VirtualPortDialog
from themes import COLORS, direction_color, set_status


def contrast(first: str, second: str) -> float:
    def luminance(value: str) -> float:
        channels = QColor(value).getRgbF()[:3]
        linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return sum(c * weight for c, weight in zip(linear, (0.2126, 0.7152, 0.0722)))

    values = sorted((luminance(first), luminance(second)))
    return (values[1] + 0.05) / (values[0] + 0.05)


class ThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.settings_path = str(Path(self.directory.name) / "appearance.ini")
        self.settings = QSettings(self.settings_path, QSettings.Format.IniFormat)
        self.window = SerialConsole(settings=self.settings)
        self.addCleanup(self.window.close)

    def test_first_launch_is_dark_and_uses_new_brand(self) -> None:
        self.assertTrue(self.window.dark_theme)
        self.assertTrue(self.window.theme_switch.isChecked())
        self.assertTrue(self.app.property("darkTheme"))
        self.assertEqual(self.window.windowTitle(), "串口协议助手")
        self.assertEqual(self.window.palette().color(QPalette.ColorRole.Window).name(), COLORS["dark"]["window"])

    def test_mouse_keyboard_and_restart_preserve_theme_choice(self) -> None:
        self.window.show()
        QTest.mouseClick(self.window.theme_switch, Qt.MouseButton.LeftButton, pos=QPoint(20, 17))
        self.assertFalse(self.window.dark_theme)
        reloaded = QSettings(self.settings_path, QSettings.Format.IniFormat)
        self.assertEqual(reloaded.value("appearance/theme"), "light")
        second = SerialConsole(settings=reloaded)
        self.addCleanup(second.close)
        self.assertFalse(second.theme_switch.isChecked())
        second.show()
        second.theme_switch.setFocus()
        QTest.keyClick(second.theme_switch, Qt.Key.Key_Space)
        self.assertTrue(second.dark_theme)
        reloaded.sync()
        self.assertEqual(reloaded.value("appearance/theme"), "dark")

    def test_invalid_setting_falls_back_to_dark(self) -> None:
        self.settings.setValue("appearance/theme", "unknown")
        second = SerialConsole(settings=self.settings)
        self.addCleanup(second.close)
        self.assertTrue(second.dark_theme)

    def test_toggle_preserves_connection_history_and_defers_decoding(self) -> None:
        self.window._open_connection()
        frame = {"decode": [{"name": "value", "offset": 0, "length": 1, "type": "uint8"}]}
        self.window._append_log("TX", b"\x11", {"name": "Test"}, frame)
        self.window._append_log("RX", b"\x22", {"name": "Test"}, frame)
        self.window.follow_latest_checkbox.setChecked(False)
        self.window.log_table.selectRow(0)
        entries = list(self.window.log_entries)
        protocol = self.window.protocol
        self.window.variable_values["test"] = {"value": 12}
        with patch.object(self.window, "_render_frame_details") as decode:
            self.window.theme_switch.setChecked(False)
            self.window.theme_switch.setChecked(True)
        decode.assert_not_called()
        self.assertTrue(self.window.connected)
        self.assertIs(self.window.protocol, protocol)
        self.assertEqual(self.window.log_entries, entries)
        self.assertEqual(self.window.log_table.currentRow(), 0)
        self.assertEqual(self.window.variable_values["test"], {"value": 12})
        self.assertEqual(self.window.decoded_table.item(0, 0).foreground().color(), direction_color("TX"))

    def test_realtime_replies_continue_after_theme_switch(self) -> None:
        self.window._open_connection()
        start = next(c for c in self.window.protocol["commands"] if c["id"] == "start_temperature_stream")
        self.window._receive_internal_response(start)
        QTest.qWait(140)
        timers = self.window.reply_timers["temperature_stream"][:]
        before = len(self.window.log_entries)
        self.window.theme_switch.setChecked(False)
        QTest.qWait(140)
        self.assertEqual(self.window.reply_timers["temperature_stream"], timers)
        self.assertGreater(len(self.window.log_entries), before)

    def test_dialogs_and_status_colors_follow_both_themes(self) -> None:
        about = AboutDialog("zh", self.window)
        self.addCleanup(about.close)
        frame = {"variables": [{"name": "value", "default": 2, "min": 0, "max": 10}]}
        variables = VariableInputDialog(frame, "Test", "zh", parent=self.window)
        self.addCleanup(variables.close)
        with patch.object(VirtualPortDialog, "_refresh_driver_state"):
            ports = VirtualPortDialog("zh", lambda: None, self.window)
        self.addCleanup(ports.close)
        for dark in (False, True):
            self.window.theme_switch.setChecked(dark)
            colors = COLORS["dark" if dark else "light"]
            self.app.processEvents()
            for widget in (about, variables, ports, about.findChild(QPlainTextEdit), variables.widgets["value"]):
                self.assertEqual(widget.palette().color(QPalette.ColorRole.Text).name(), colors["text"])
            set_status(ports.driver_status, "error")
            self.assertEqual(ports.driver_status.palette().color(QPalette.ColorRole.WindowText).name(), colors["error"])

    def test_text_and_direction_colors_have_readable_contrast(self) -> None:
        for theme, colors in COLORS.items():
            for foreground in ("text", "tx", "rx", "warning", "error", "link"):
                for background in ("base", "alternate", "window"):
                    self.assertGreaterEqual(contrast(colors[foreground], colors[background]), 4.5, f"{theme}.{foreground}")
            self.assertGreaterEqual(contrast(colors["selection_text"], colors["selection"]), 4.5)

    def test_language_changes_keep_the_switch_visible_and_checked(self) -> None:
        self.window.resize(1050, 680)
        self.window.show()
        for code, _name in LANGUAGE_OPTIONS:
            self.window.language_combo.setCurrentIndex(self.window.language_combo.findData(code))
            self.app.processEvents()
            switch = self.window.theme_switch
            self.assertTrue(switch.isChecked())
            self.assertGreaterEqual(switch.width(), switch.sizeHint().width())
            self.assertLessEqual(switch.geometry().right(), self.window.about_button.geometry().left())


if __name__ == "__main__":
    unittest.main()
