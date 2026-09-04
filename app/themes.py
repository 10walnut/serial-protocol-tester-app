from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPalette, QPen
from PySide6.QtWidgets import QApplication, QCheckBox, QWidget


COLORS = {
    "dark": {
        "window": "#191c20", "surface": "#22262b", "base": "#202428",
        "alternate": "#292e34", "header": "#30363d", "border": "#47505a",
        "text": "#e9edf1", "muted": "#aab3bd", "hover": "#343d44",
        "accent": "#30c9b8", "primary": "#227a73", "primary_hover": "#299188",
        "selection": "#364b55", "selection_text": "#ffffff",
        "tx": "#a8d5ff", "rx": "#8fe4b2", "warning": "#ffd085", "error": "#ffaaaa",
        "link": "#7bd7eb",
    },
    "light": {
        "window": "#f5f7f8", "surface": "#ffffff", "base": "#ffffff",
        "alternate": "#f2f6f6", "header": "#e7ecee", "border": "#b8c3ca",
        "text": "#1d262d", "muted": "#64717b", "hover": "#eaf1f2",
        "accent": "#176b70", "primary": "#176b70", "primary_hover": "#10585d",
        "selection": "#cfe4e4", "selection_text": "#101719",
        "tx": "#164b83", "rx": "#14633d", "warning": "#825100", "error": "#a12b1f",
        "link": "#125d83",
    },
}


def theme_colors() -> dict[str, str]:
    app = QApplication.instance()
    dark = app.property("darkTheme") if app is not None else None
    return COLORS["light" if dark is False else "dark"]


def direction_color(direction: str) -> QColor:
    return QColor(theme_colors()["rx" if direction == "RX" else "tx"])


def set_status(widget: QWidget, severity: str = "") -> None:
    widget.setProperty("severity", severity)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def apply_theme(app: QApplication, dark: bool) -> None:
    colors = COLORS["dark" if dark else "light"]
    app.setProperty("darkTheme", dark)
    if not app.property("assistantFusionStyle"):
        app.setStyle("Fusion")
        app.setProperty("assistantFusionStyle", True)
    hints = app.styleHints()
    if hasattr(hints, "setColorScheme"):
        hints.setColorScheme(Qt.ColorScheme.Dark if dark else Qt.ColorScheme.Light)

    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: "window",
        QPalette.ColorRole.WindowText: "text",
        QPalette.ColorRole.Base: "base",
        QPalette.ColorRole.AlternateBase: "alternate",
        QPalette.ColorRole.Text: "text",
        QPalette.ColorRole.Button: "surface",
        QPalette.ColorRole.ButtonText: "text",
        QPalette.ColorRole.ToolTipBase: "surface",
        QPalette.ColorRole.ToolTipText: "text",
        QPalette.ColorRole.Highlight: "selection",
        QPalette.ColorRole.HighlightedText: "selection_text",
        QPalette.ColorRole.Link: "link",
        QPalette.ColorRole.LinkVisited: "link",
        QPalette.ColorRole.PlaceholderText: "muted",
        QPalette.ColorRole.Accent: "accent",
    }
    for role, key in roles.items():
        palette.setColor(role, QColor(colors[key]))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(colors["muted"]))
    app.setPalette(palette)
    app.setStyleSheet("""
        QWidget { color: %(text)s; font-size: 13px; }
        QMainWindow, QDialog { background: %(window)s; }
        QLabel { background: transparent; }
        QGroupBox { background: %(surface)s; border: 1px solid %(border)s;
                    border-radius: 6px; margin-top: 12px; padding-top: 10px; font-weight: 600; }
        QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
        QLabel#protocolTitle { font-size: 17px; font-weight: 700; }
        QLabel#aboutName { font-size: 20px; font-weight: 700; }
        QLabel#sectionTitle { font-weight: 700; }
        QLabel[severity="success"] { color: %(rx)s; font-weight: 600; }
        QLabel[severity="warning"] { color: %(warning)s; font-weight: 600; }
        QLabel[severity="error"] { color: %(error)s; font-weight: 600; }
        QPushButton, QToolButton { min-height: 30px; padding: 0 10px; background: %(surface)s;
                                  border: 1px solid %(border)s; border-radius: 5px; }
        QToolButton { padding: 0 3px; }
        QPushButton:hover, QToolButton:hover { background: %(hover)s; border-color: %(accent)s; }
        QPushButton:pressed, QToolButton:pressed { background: %(selection)s; }
        QPushButton:focus, QToolButton:focus { border-color: %(accent)s; }
        QPushButton:disabled, QToolButton:disabled { color: %(muted)s; background: %(window)s; }
        QPushButton#primaryButton { background: %(primary)s; color: #ffffff;
                                   border-color: %(primary)s; font-weight: 600; }
        QPushButton#primaryButton:hover { background: %(primary_hover)s; }
        QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {
            min-height: 28px; background: %(base)s; border: 1px solid %(border)s;
            border-radius: 4px; padding: 0 6px; selection-background-color: %(selection)s;
            selection-color: %(selection_text)s;
        }
        QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus { border-color: %(accent)s; }
        QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QLineEdit:disabled {
            color: %(muted)s; background: %(window)s;
        }
        QComboBox QAbstractItemView { background: %(base)s; color: %(text)s; }
        QAbstractItemView, QPlainTextEdit {
            background: %(base)s; alternate-background-color: %(alternate)s;
            border: 1px solid %(border)s; gridline-color: %(border)s;
            selection-background-color: %(selection)s; selection-color: %(selection_text)s;
        }
        QTableView::item:selected { background: %(selection)s; color: %(selection_text)s; }
        QHeaderView::section { background: %(header)s; color: %(text)s; padding: 7px;
                              border: 0; border-right: 1px solid %(border)s; font-weight: 600; }
        QTableCornerButton::section { background: %(header)s; border: 0; }
        QStatusBar { background: %(header)s; }
        QTabWidget::pane { border: 1px solid %(border)s; background: %(surface)s; }
        QTabBar::tab { padding: 9px 14px; background: %(window)s; border-bottom: 2px solid transparent; }
        QTabBar::tab:selected { background: %(surface)s; border-bottom-color: %(accent)s; }
        QTabBar::tab:hover { background: %(hover)s; }
        QToolTip { background: %(surface)s; color: %(text)s; border: 1px solid %(border)s; padding: 5px; }
        QSplitter::handle { background: %(window)s; }
    """ % colors)


class ThemeSwitch(QCheckBox):
    """A painted switch with the native checkbox keyboard and accessibility behavior."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedHeight(34)

    def sizeHint(self) -> QSize:
        return QSize(60 + self.fontMetrics().horizontalAdvance(self.text()), 34)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def hitButton(self, position: QPoint) -> bool:
        return self.rect().contains(position)

    def paintEvent(self, event: object) -> None:
        colors = theme_colors()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(colors["primary"] if self.isChecked() else colors["border"]))
        painter.drawRoundedRect(QRectF(2, 6, 42, 22), 11, 11)
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(QRectF(24 if self.isChecked() else 5, 9, 16, 16))
        if self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(colors["accent"]), 1))
            painter.drawRoundedRect(QRectF(0.5, 4.5, 45, 25), 12, 12)
        painter.setPen(self.palette().color(QPalette.ColorRole.WindowText))
        painter.drawText(QRect(52, 0, self.width() - 52, self.height()), Qt.AlignmentFlag.AlignVCenter, self.text())
