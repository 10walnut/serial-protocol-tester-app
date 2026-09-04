"""Capture actual Qt widgets without opening serial ports or changing user settings."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from PySide6.QtCore import QSettings
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QTabWidget

from protocol_core import encode_frame, localized_value
from serial_console import AboutDialog, SerialConsole, VariableInputDialog, VirtualPortDialog


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("build/theme-previews"))
    parser.add_argument("--protocol", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    if os.name == "nt":
        # The offscreen platform does not automatically discover Windows system fonts.
        font_root = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        for filename in ("msyh.ttc", "msyhbd.ttc", "segoeui.ttf", "consola.ttf"):
            QFontDatabase.addApplicationFont(str(font_root / filename))
        app.setFont(QFont("Microsoft YaHei", 10))
    with tempfile.TemporaryDirectory() as directory:
        settings = QSettings(str(Path(directory) / "appearance.ini"), QSettings.Format.IniFormat)
        window = SerialConsole(settings=settings)
        if args.protocol:
            window._load_protocol_file(args.protocol.resolve())
        # Use the application's internal simulator, never a real device.
        window._open_connection()
        command = next(c for c in window.protocol["commands"] if c["request"].get("variables"))
        window.command_table.selectRow(window.protocol["commands"].index(command))
        window._append_log("TX", encode_frame(command["request"]), command, command["request"])
        if command.get("response"):
            window._append_log("RX", encode_frame(command["response"]), command, command["response"])
        for dark in (True, False):
            name = "dark" if dark else "light"
            window.theme_switch.setChecked(dark)
            for width, height in ((1380, 840), (1050, 680)):
                window.resize(width, height)
                window.show()
                QTest.qWait(100)
                window.grab().save(str(args.output / f"main-{name}-{width}.png"))
            variables = VariableInputDialog(
                command["request"], localized_value(command, "name", "zh"), "zh", parent=window
            )
            variables.show()
            QTest.qWait(100)
            variables.grab().save(str(args.output / f"variables-{name}.png"))
            variables.close()
            variables.deleteLater()
            about = AboutDialog("zh", window)
            about.show()
            for index, page in enumerate(("about", "skill", "support")):
                about.findChild(QTabWidget).setCurrentIndex(index)
                QTest.qWait(100)
                about.grab().save(str(args.output / f"{page}-{name}.png"))
            about.close()
            about.deleteLater()
            with patch.object(VirtualPortDialog, "_refresh_driver_state"):
                ports = VirtualPortDialog("zh", lambda: None, window)
            ports.show()
            QTest.qWait(100)
            ports.grab().save(str(args.output / f"ports-{name}.png"))
            ports.close()
            ports.deleteLater()
        window.close()
        app.processEvents()
    print(f"Saved Qt theme previews to {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
