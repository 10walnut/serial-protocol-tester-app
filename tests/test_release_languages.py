from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from protocol_core import encode_frame
from serial_console import SerialConsole, release_language


class ReleaseLanguageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.settings = QSettings(str(Path(directory.name) / "settings.ini"), QSettings.Format.IniFormat)

    def window(self, language: str) -> SerialConsole:
        window = SerialConsole(settings=self.settings, default_language=language)
        self.addCleanup(window.close)
        return window

    def test_editions_default_to_corresponding_ui_and_sample(self) -> None:
        chinese = self.window("zh")
        english = self.window("en")
        self.assertEqual(chinese.windowTitle(), "串口协议助手")
        self.assertEqual(english.windowTitle(), "Serial Protocol Assistant")
        self.assertEqual(english.protocol["commands"][0]["name"], "Read temperature")
        self.assertEqual(chinese.protocol["commands"][0]["name"], "读取温度")
        for first, second in zip(chinese.protocol["commands"], english.protocol["commands"], strict=True):
            self.assertEqual(first["id"], second["id"])
            for key in ("request", "response"):
                self.assertEqual(encode_frame(first[key]), encode_frame(second[key]))

    def test_manual_selection_is_saved_per_edition(self) -> None:
        chinese = self.window("zh")
        chinese.language_combo.setCurrentIndex(chinese.language_combo.findData("es"))
        self.assertEqual(self.window("zh").language, "es")
        self.assertEqual(self.window("en").language, "en")
        self.settings.setValue("ui/language/en", "invalid")
        self.assertEqual(self.window("en").language, "en")

    def test_packaged_metadata_and_missing_fallback(self) -> None:
        with patch("serial_console.Path.read_text", return_value='{"language":"en"}'):
            self.assertEqual(release_language(), "en")
        for content in ('{"language":"invalid"}', '[]', 'bad json'):
            with patch("serial_console.Path.read_text", return_value=content):
                self.assertEqual(release_language(), "zh")
        with patch("serial_console.Path.read_text", side_effect=FileNotFoundError):
            self.assertEqual(release_language(), "zh")
