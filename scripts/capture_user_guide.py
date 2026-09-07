"""Capture guide illustrations from Qt widgets and internal simulation only."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from PySide6.QtCore import QSettings
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QTabWidget
from protocol_core import encode_frame, format_hex
from serial_console import AboutDialog, SerialConsole, VariableInputDialog, VirtualPortDialog


def main() -> None:
    assets = ROOT / "docs/user-guide/assets"
    assets.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    for filename in ("msyh.ttc", "msyhbd.ttc", "segoeui.ttf", "consola.ttf"):
        QFontDatabase.addApplicationFont(str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / filename))
    app.setFont(QFont("Microsoft YaHei", 10))
    captured = []

    def save(widget, name, note):
        app.processEvents()
        QTest.qWait(100)
        if not widget.grab().save(str(assets / f"{name}.png")):
            raise RuntimeError(name)
        captured.append({"file": f"{name}.png", "source": note})

    with tempfile.TemporaryDirectory() as directory:
        settings = QSettings(str(Path(directory) / "guide.ini"), QSettings.Format.IniFormat)
        window = SerialConsole(settings=settings, default_language="zh")
        window.resize(1380, 840)
        window.show()
        save(window, "interface-zh", "Chinese edition; bundled sample; disconnected")
        about = AboutDialog("zh", window)
        about.show()
        about.findChild(QTabWidget).setCurrentIndex(1)
        save(about, "skill-install", "Actual Skill download and installation page")
        about.close()
        window._open_connection()
        window.command_table.selectRow(0)
        window._run_selected_command()
        QTest.qWait(240)
        save(window, "internal-read", "Internal simulation of Read temperature, no physical device")
        save(window.settings_group, "internal-settings", "Host plus internal link")
        save(window.decoded_table, "read-details", "Actual decoded internal response")
        save(window.log_table, "read-traffic", "Actual TX/RX from internal request/response")
        command = window.protocol["commands"][1]
        variables = VariableInputDialog(command["request"], command["name"], "zh", parent=window)
        variables.show()
        save(variables, "variable-input", "Actual bundled example run-state choices")
        variables.close()
        start = next(c for c in window.protocol["commands"] if c["id"] == "start_temperature_stream")
        stop = next(c for c in window.protocol["commands"] if c["id"] == "stop_temperature_stream")
        window.command_table.selectRow(window.protocol["commands"].index(start))
        window._run_selected_command()
        QTest.qWait(650)
        window.command_table.selectRow(window.protocol["commands"].index(stop))
        window._run_selected_command()
        QTest.qWait(250)
        save(window.log_table, "stream-traffic", "Internal ACK, periodic frames and stop acknowledgement")
        window.follow_latest_checkbox.setChecked(False)
        window.log_table.selectRow(1)
        save(window, "history-details", "Selected historical read-temperature response")
        window._close_connection()
        window.transport_combo.setCurrentIndex(window.transport_combo.findData("serial"))
        window.port_combo.setCurrentText("COM3")
        save(window.settings_group, "host-settings", "Configuration example COM3; not opened or hardware tested")
        window.role_combo.setCurrentIndex(window.role_combo.findData("device"))
        window.port_combo.setCurrentText("COM10")
        save(window.settings_group, "device-settings", "Configuration example COM10; not opened or pair-created")
        ports = VirtualPortDialog("zh", window._refresh_ports, window)
        ports.show()
        save(ports, "virtual-ports", "Actual read-only driver status; no create/delete action performed")
        ports.close()
        window.close()
        english = SerialConsole(settings=settings, default_language="en")
        english.resize(1380, 840)
        english.show()
        save(english, "interface-en", "English edition and English sample; disconnected")
        english.close()
        frames = {c["id"]: {key: format_hex(encode_frame(c[key])) for key in ("request", "response")} for c in window.protocol["commands"]}
        (assets / "capture-manifest.json").write_text(json.dumps({"captures": captured, "frames": frames}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Captured {len(captured)} guide illustrations in {assets}")


if __name__ == "__main__":
    main()
