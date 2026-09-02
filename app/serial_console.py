from __future__ import annotations

import ctypes
import json
import os
import re
import subprocess
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any

import serial
from serial.tools import list_ports
from PySide6.QtCore import QSignalBlocker, QTimer, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QFont, QIcon, QIntValidator, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QApplication,
    QAbstractSpinBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QStyle,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from protocol_core import (
    ProtocolError,
    default_variable_values,
    decode_frame_details,
    encode_frame,
    find_matching_command,
    find_matching_frame,
    format_hex,
    load_protocol,
    localized_value,
    resolve_follow_up_frame,
    split_framed_bytes,
)
from virtual_ports import (
    COM0COM_DOWNLOAD_URL,
    VirtualPortError,
    count_unassigned_ports,
    find_setupc,
    launch_elevated_install,
    list_virtual_pairs,
    non_ports_class_names,
    query_com0com_driver_problems,
    virtual_ports_ready,
)
from i18n_extra import EXTRA_UI_TEXT, LANGUAGE_OPTIONS


def resource_root() -> Path:
    bundled_root = getattr(sys, "_MEIPASS", None)
    if bundled_root:
        return Path(bundled_root)
    return Path(__file__).resolve().parent


ROOT = resource_root()
SAMPLE_PROTOCOL = ROOT / "sample_protocol.json"
ASSETS_DIR = ROOT / "assets"
LOGO_PATH = ASSETS_DIR / "serial-protocol-tester-logo.png"
APP_VERSION = "1.3.1"
AUTHOR = "十个核桃 / 10walnut"
PROJECT_URL = "https://github.com/10walnut/serial-protocol-tester-app"
SKILL_PROJECT_URL = "https://github.com/10walnut/serial-protocol-tester-skill"
SKILL_DOWNLOAD_URL = "https://github.com/10walnut/serial-protocol-tester-skill/archive/refs/heads/main.zip"
LATEST_RELEASE_API = "https://api.github.com/repos/10walnut/serial-protocol-tester-app/releases/latest"
COMMON_BAUDRATES = (
    300,
    600,
    1200,
    2400,
    4800,
    9600,
    14400,
    19200,
    38400,
    57600,
    115200,
    128000,
    230400,
    256000,
    460800,
    921600,
    1000000,
)
MAX_RX_FRAMES_PER_POLL = 32
MAX_TRAFFIC_ROWS = 2000
TRAFFIC_TRIM_ROWS = 500
LIVE_DETAIL_REFRESH_MS = 200


def version_key(value: str) -> tuple[int, int, int]:
    numbers = [int(part) for part in re.findall(r"\d+", value)[:3]]
    return tuple((numbers + [0, 0, 0])[:3])


def is_windows_admin() -> bool:
    if os.name != "nt":
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


def relaunch_as_admin() -> bool:
    if os.name != "nt" or is_windows_admin():
        return False
    if getattr(sys, "frozen", False):
        executable = sys.executable
        arguments = subprocess.list2cmdline(sys.argv[1:])
        working_directory = str(Path(sys.executable).resolve().parent)
    else:
        executable = sys.executable
        arguments = subprocess.list2cmdline([str(Path(__file__).resolve()), *sys.argv[1:]])
        working_directory = str(Path(__file__).resolve().parent)
    result = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        executable,
        arguments,
        working_directory,
        1,
    )
    if result <= 32:
        ctypes.windll.user32.MessageBoxW(
            None,
            f"无法以管理员权限启动串口协议测试器（错误代码 {result}）。",
            "串口协议测试器",
            0x10,
        )
    return True


def open_external_url(url: str) -> bool:
    if os.name == "nt":
        try:
            return int(ctypes.windll.shell32.ShellExecuteW(None, "open", url, None, None, 1)) > 32
        except (OSError, TypeError, ValueError):
            return False
    return QDesktopServices.openUrl(QUrl(url))


UI_TEXT = {
    "zh": {
        "title": "串口协议测试器",
        "language_button": "EN",
        "no_protocol": "未加载协议",
        "load_protocol": "加载协议",
        "connection": "连接设置",
        "role": "角色",
        "host": "上位机",
        "device": "下位机",
        "transport": "通信通道",
        "internal_transport": "内部虚拟链路",
        "serial_transport": "串口或 URL",
        "endpoint": "端口",
        "refresh": "刷新",
        "virtual_ports": "虚拟串口",
        "baudrate": "波特率",
        "baudrate_invalid": "波特率必须是 50 到 4000000 之间的整数。",
        "data_bits": "数据位",
        "parity": "校验位",
        "parity_none": "无",
        "parity_even": "偶校验",
        "parity_odd": "奇校验",
        "parity_mark": "标记",
        "parity_space": "空格",
        "stop_bits": "停止位",
        "open": "打开",
        "close": "关闭",
        "opened": "已打开",
        "closed": "已关闭",
        "commands": "命令",
        "command_headers": ["名称", "命令原文", "注释", "波特率", "返回原文", "ID"],
        "select_command": "请选择命令",
        "send_request": "发送请求",
        "simulate_request": "模拟收到请求",
        "send_response": "手动发送应答",
        "traffic": "通讯记录与返回解析",
        "log_headers": ["时间", "方向", "命令", "原始 HEX", "文本"],
        "decoded_fields": "发送/接收数据解释",
        "decoded_fields_selected": "发送/接收数据解释 · {time} {direction} · {command}",
        "clear": "清空",
        "decoded_headers": ["方向", "字节位置", "字段", "功能/作用", "原始字节", "类型/规则", "计算过程", "结果"],
        "ready": "就绪",
        "load_dialog_title": "加载协议",
        "file_filter": "串口协议 (*.json);;所有文件 (*)",
        "protocol_error": "协议错误",
        "loaded_commands": "已加载 {count} 条命令",
        "no_protocol_title": "未加载协议",
        "no_protocol_message": "请先加载协议 JSON。",
        "endpoint_required": "请选择 COM 端口，或输入 loop:// 等串口 URL",
        "internal_name": "内部虚拟链路",
        "connected": "已连接：{endpoint}",
        "connection_failed": "连接失败",
        "connection_failed_status": "连接失败：{error}",
        "closed_status": "连接已关闭",
        "no_command_title": "未选择命令",
        "no_command_message": "请先选择一条命令。",
        "not_connected_title": "未连接",
        "not_connected_message": "请先打开连接。",
        "no_response_title": "无应答",
        "no_response_message": "该命令没有配置应答帧。",
        "unmatched": "未匹配",
        "traffic_status": "{direction} {count} 字节 · {command}",
        "rx_device_unmatched": "已接收 {count} 字节，但未匹配协议请求，因此没有自动应答。请确认角色为下位机、串口助手使用 HEX 发送，并检查帧长度与校验和。",
        "rx_host_request": "收到请求“{command}”，当前为上位机角色，不会自动应答；要模拟设备请切换为下位机。",
        "rx_auto_reply_disabled": "已匹配请求“{command}”，但该命令未启用 auto_reply 或未配置应答行为。",
        "output_cleared": "已清空输出",
        "serial_error": "串口错误",
        "error_status": "错误：{error}",
        "vp_title": "创建虚拟串口对",
        "vp_intro": "本功能调用已安装的 com0com 驱动创建两个互联 COM 端口。创建时 Windows 会请求管理员权限。",
        "vp_driver": "setupc.exe 路径",
        "vp_browse": "选择",
        "vp_port_a": "本软件端口",
        "vp_port_b": "外部软件端口",
        "vp_port_decrease": "减小端口号",
        "vp_port_increase": "增大端口号",
        "vp_create": "创建端口对",
        "vp_refresh": "刷新状态",
        "vp_close": "关闭",
        "vp_not_found": "未检测到 com0com。请先从官方项目安装驱动，或手动选择 setupc.exe。",
        "vp_found": "已检测到 com0com：{path}",
        "vp_download": "打开 com0com 官方下载页面",
        "vp_existing": "com0com 当前端口",
        "vp_no_output": "尚未读取端口状态。",
        "vp_select_title": "选择 com0com setupc.exe",
        "vp_executable_filter": "程序 (setupc.exe);;所有文件 (*)",
        "vp_driver_missing_title": "缺少虚拟串口驱动",
        "vp_driver_missing_message": "未找到 setupc.exe。请先安装 com0com 或选择正确路径。",
        "vp_invalid_title": "端口设置无效",
        "vp_same_port": "两个端口号不能相同。",
        "vp_conflict_title": "端口号已占用",
        "vp_conflict_message": "以下端口已存在：{ports}\n请选择其他端口号。",
        "vp_uac_title": "确认创建虚拟串口",
        "vp_uac_message": "将创建 {port_a} ↔ {port_b}。Windows 随后会显示管理员权限确认窗口。是否继续？",
        "vp_error_title": "虚拟串口错误",
        "vp_driver_unsigned": "检测到 {count} 个失效的 com0com 设备：错误代码 52，Windows 无法验证驱动数字签名。请卸载当前 com0com，安装与当前 Windows 匹配的已签名版本并重启；软件已停止创建，以免继续产生无效设备。",
        "vp_driver_problem": "检测到 {count} 个 com0com 驱动异常（{codes}）。请先在设备管理器中修复或重新安装驱动。",
        "vp_unassigned": "检测到 {count} 个未完成的 COM# 端口。请先修复或卸载这些失效设备，再创建新端口对。",
        "vp_wrong_class": "检测到未注册到“端口（COM 和 LPT）”的旧端口：{ports}。请先在 com0com Setup 中删除对应端口对，再由本软件重新创建。",
        "vp_wrong_class_title": "旧虚拟端口不可用",
        "vp_creating": "正在创建并验证 {port_a} ↔ {port_b}，请完成 Windows 管理员确认…",
        "vp_created_title": "虚拟串口已创建",
        "vp_created_message": "已验证 {port_a} ↔ {port_b}，两个端口现在可供软件使用。",
        "vp_verify_failed": "创建命令已运行，但 Windows 串口枚举中没有检测到 {port_a} 和 {port_b}。只有两个端口都出现在“端口（COM 和 LPT）”后才可使用；请删除旧的自定义类端口对后重试。",
        "variable_title": "输入发送参数：{command}",
        "variable_ok": "生成并发送",
        "variable_cancel": "取消",
        "variable_decrease": "减少 {label}",
        "variable_increase": "增加 {label}",
        "formula": "公式",
        "about_tooltip": "关于与检查更新",
        "about_title": "关于串口协议测试器",
        "about_app": "串口协议测试器",
        "about_version": "版本 {version}",
        "about_author": "作者：{author}",
        "about_project": "软件项目地址",
        "about_skill": "协议转换 Skill 项目地址",
        "about_donation": "赞赏",
        "about_alipay": "支付宝",
        "about_wechat": "微信赞赏",
        "about_check_update": "检查更新",
        "about_checking": "正在检查 GitHub 最新版本…",
        "about_latest": "当前已是最新版本。",
        "about_update_available": "发现新版本 {version}，打开发布页面",
        "about_open_release": "打开新版本",
        "about_update_error": "检查更新失败：{error}",
        "about_close": "关闭",
        "about_tab_about": "关于",
        "about_tab_skill": "Skill 下载与使用",
        "about_tab_support": "支持作者",
        "about_support_message": "如果这个工具为你的串口调试节省了时间，欢迎请作者喝杯咖啡。每一份支持都会用于继续修复兼容性、补充协议示例并维护开源版本。感谢你的认可与支持。",
        "about_skill_intro": "Serial Protocol Tester Skill 可以读取协议文档并生成本软件可加载的 serial_protocol.v1 JSON。",
        "about_skill_download": "下载 Skill ZIP",
        "about_skill_open": "打开 Skill 项目与详细教程",
        "about_skill_steps": "1. 下载 Skill ZIP。\n\n2. Codex：运行 .\\install.ps1 -Target codex\n   Claude Code：运行 .\\install.ps1 -Target claude\n   WorkBuddy / Harness：按项目 README 选择对应目标。\n\n3. 豆包：打开“技能新建”→“上传技能”，直接上传包含 SKILL.md 的 Skill ZIP 压缩包。\n\n4. 提示词示例：\n使用 serial-protocol-tester Skill 读取协议，只输出中文 JSON；生成后运行校验器，并为每个发送和接收字段写明作用与计算公式。",
        "about_link_error_title": "无法打开链接",
        "about_link_error_message": "无法调用默认浏览器打开：\n{url}",
    },
    "en": {
        "title": "Serial Protocol Tester",
        "language_button": "中文",
        "no_protocol": "No protocol loaded",
        "load_protocol": "Load protocol",
        "connection": "Connection",
        "role": "Role",
        "host": "Host",
        "device": "Device",
        "transport": "Transport",
        "internal_transport": "Internal virtual link",
        "serial_transport": "COM port or serial URL",
        "endpoint": "Endpoint",
        "refresh": "Refresh",
        "virtual_ports": "Virtual ports",
        "baudrate": "Baud rate",
        "baudrate_invalid": "Baud rate must be an integer from 50 to 4000000.",
        "data_bits": "Data bits",
        "parity": "Parity",
        "parity_none": "None",
        "parity_even": "Even",
        "parity_odd": "Odd",
        "parity_mark": "Mark",
        "parity_space": "Space",
        "stop_bits": "Stop bits",
        "open": "Open",
        "close": "Close",
        "opened": "Open",
        "closed": "Closed",
        "commands": "Commands",
        "command_headers": ["Name", "Request", "Annotation", "Baud", "Response", "ID"],
        "select_command": "Select a command",
        "send_request": "Send request",
        "simulate_request": "Simulate request",
        "send_response": "Send response",
        "traffic": "Traffic and decoded response",
        "log_headers": ["Time", "Direction", "Command", "Raw HEX", "Text"],
        "decoded_fields": "Transmitted/received data details",
        "decoded_fields_selected": "Transmitted/received data details · {time} {direction} · {command}",
        "clear": "Clear",
        "decoded_headers": ["Direction", "Bytes", "Field", "Purpose", "Raw bytes", "Type/rule", "Calculation", "Result"],
        "ready": "Ready",
        "load_dialog_title": "Load protocol",
        "file_filter": "Serial protocol (*.json);;All files (*)",
        "protocol_error": "Protocol error",
        "loaded_commands": "Loaded {count} commands",
        "no_protocol_title": "No protocol",
        "no_protocol_message": "Load a protocol JSON first.",
        "endpoint_required": "Select a COM port or enter a serial URL such as loop://",
        "internal_name": "internal virtual link",
        "connected": "Connected: {endpoint}",
        "connection_failed": "Connection failed",
        "connection_failed_status": "Connection failed: {error}",
        "closed_status": "Connection closed",
        "no_command_title": "No command",
        "no_command_message": "Select a command first.",
        "not_connected_title": "Not connected",
        "not_connected_message": "Open the connection first.",
        "no_response_title": "No response",
        "no_response_message": "This command has no configured response frame.",
        "unmatched": "Unmatched",
        "traffic_status": "{direction} {count} bytes · {command}",
        "rx_device_unmatched": "Received {count} bytes but no protocol request matched, so no automatic reply was sent. Select Device, send HEX bytes, and verify frame length and checksum.",
        "rx_host_request": "Received request '{command}'. Host mode does not auto-reply; switch to Device to emulate the device.",
        "rx_auto_reply_disabled": "Request '{command}' matched, but auto_reply is disabled or no reply behavior is configured.",
        "output_cleared": "Output cleared",
        "serial_error": "Serial error",
        "error_status": "Error: {error}",
        "vp_title": "Create virtual COM pair",
        "vp_intro": "This feature calls an installed com0com driver to create two linked COM ports. Windows administrator approval is required.",
        "vp_driver": "setupc.exe path",
        "vp_browse": "Browse",
        "vp_port_a": "This application",
        "vp_port_b": "External application",
        "vp_port_decrease": "Decrease COM number",
        "vp_port_increase": "Increase COM number",
        "vp_create": "Create port pair",
        "vp_refresh": "Refresh status",
        "vp_close": "Close",
        "vp_not_found": "com0com was not detected. Install it from the official project first, or select setupc.exe manually.",
        "vp_found": "com0com detected: {path}",
        "vp_download": "Open the official com0com download page",
        "vp_existing": "Current com0com ports",
        "vp_no_output": "Port status has not been read yet.",
        "vp_select_title": "Select com0com setupc.exe",
        "vp_executable_filter": "Program (setupc.exe);;All files (*)",
        "vp_driver_missing_title": "Virtual port driver missing",
        "vp_driver_missing_message": "setupc.exe was not found. Install com0com or select the correct path.",
        "vp_invalid_title": "Invalid port settings",
        "vp_same_port": "The two port numbers must be different.",
        "vp_conflict_title": "COM number already in use",
        "vp_conflict_message": "These ports already exist: {ports}\nChoose different port numbers.",
        "vp_uac_title": "Confirm virtual port creation",
        "vp_uac_message": "Create {port_a} ↔ {port_b}? Windows will request administrator approval.",
        "vp_error_title": "Virtual port error",
        "vp_driver_unsigned": "Detected {count} failed com0com devices: error 52 means Windows cannot verify the driver signature. Uninstall this com0com build, install a signed version compatible with this Windows release, and reboot. Creation is blocked to avoid more invalid devices.",
        "vp_driver_problem": "Detected {count} com0com driver problems ({codes}). Repair or reinstall the driver in Device Manager first.",
        "vp_unassigned": "Detected {count} unfinished COM# ports. Repair or remove these failed devices before creating another pair.",
        "vp_wrong_class": "Legacy ports not registered under Ports (COM & LPT) were found: {ports}. Remove their pair in com0com Setup, then recreate it with this application.",
        "vp_wrong_class_title": "Legacy virtual ports are unusable",
        "vp_creating": "Creating and verifying {port_a} ↔ {port_b}; complete the Windows administrator prompt…",
        "vp_created_title": "Virtual ports created",
        "vp_created_message": "Verified {port_a} ↔ {port_b}. Both ports are now available to applications.",
        "vp_verify_failed": "The command ran, but Windows serial enumeration did not find {port_a} and {port_b}. Both ports must appear under Ports (COM & LPT); remove legacy custom-class pairs and retry.",
        "variable_title": "Enter transmit values: {command}",
        "variable_ok": "Build and send",
        "variable_cancel": "Cancel",
        "variable_decrease": "Decrease {label}",
        "variable_increase": "Increase {label}",
        "formula": "Formula",
        "about_tooltip": "About and check for updates",
        "about_title": "About Serial Protocol Tester",
        "about_app": "Serial Protocol Tester",
        "about_version": "Version {version}",
        "about_author": "Author: {author}",
        "about_project": "Application repository",
        "about_skill": "Protocol Skill repository",
        "about_donation": "Support the author",
        "about_alipay": "Alipay",
        "about_wechat": "WeChat",
        "about_check_update": "Check for updates",
        "about_checking": "Checking the latest GitHub release…",
        "about_latest": "This is the latest version.",
        "about_update_available": "Version {version} is available; open the release page",
        "about_open_release": "Open release",
        "about_update_error": "Update check failed: {error}",
        "about_close": "Close",
        "about_tab_about": "About",
        "about_tab_skill": "Download and use Skill",
        "about_tab_support": "Support",
        "about_support_message": "If this tool saves time during serial debugging, you can support its continued development. Contributions help maintain compatibility, add protocol examples, and keep the open-source releases current. Thank you for your support.",
        "about_skill_intro": "Serial Protocol Tester Skill reads protocol documents and generates serial_protocol.v1 JSON files that this application can load.",
        "about_skill_download": "Download Skill ZIP",
        "about_skill_open": "Open Skill project and guide",
        "about_skill_steps": "1. Download the Skill ZIP.\n\n2. Codex: run .\\install.ps1 -Target codex\n   Claude Code: run .\\install.ps1 -Target claude\n   WorkBuddy / Harness: choose the matching target from the repository guide.\n\n3. Doubao: open Create Skill > Upload Skill, then directly upload the Skill ZIP containing SKILL.md.\n\n4. Example prompt:\nUse the serial-protocol-tester Skill, emit one-language JSON, run validation, and explain the purpose and calculation of every transmitted and received field.",
        "about_link_error_title": "Could not open link",
        "about_link_error_message": "The default browser could not open:\n{url}",
    },
}

UI_TEXT.update(EXTRA_UI_TEXT)


def ui_text(language: str, key: str, **values: Any) -> Any:
    text = UI_TEXT.get(language, UI_TEXT["en"]).get(key, UI_TEXT["en"][key])
    return text.format(**values) if isinstance(text, str) and values else text


class AboutDialog(QDialog):
    def __init__(self, language: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.language = language
        self.release_url = ""
        self.network = QNetworkAccessManager(self)
        self.setWindowTitle(self._t("about_title"))
        self.setMinimumSize(680, 620)
        self.resize(760, 700)
        self._build_ui()

    def _t(self, key: str, **values: Any) -> Any:
        return ui_text(self.language, key, **values)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)

        tabs = QTabWidget()
        tabs.addTab(self._build_about_page(), self._t("about_tab_about"))
        tabs.addTab(self._build_skill_page(), self._t("about_tab_skill"))
        tabs.addTab(self._build_support_page(), self._t("about_tab_support"))
        layout.addWidget(tabs, 1)

        close_row = QHBoxLayout()
        close_button = QPushButton(self._t("about_close"))
        close_button.clicked.connect(self.accept)
        close_row.addStretch(1)
        close_row.addWidget(close_button)
        layout.addLayout(close_row)

    def _build_about_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(26, 24, 26, 20)
        layout.setSpacing(10)

        logo = QLabel()
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = QPixmap(str(LOGO_PATH))
        if not pixmap.isNull():
            logo.setPixmap(
                pixmap.scaled(
                    96,
                    96,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        layout.addWidget(logo)

        name = QLabel(self._t("about_app"))
        name.setObjectName("aboutName")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(name)
        version = QLabel(self._t("about_version", version=APP_VERSION))
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)
        author = QLabel(self._t("about_author", author=AUTHOR))
        author.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(author)

        links = QLabel(
            f'<a href="{PROJECT_URL}">{self._t("about_project")}</a>'
            f' &nbsp;·&nbsp; <a href="{SKILL_PROJECT_URL}">{self._t("about_skill")}</a>'
        )
        links.setAlignment(Qt.AlignmentFlag.AlignCenter)
        links.setOpenExternalLinks(True)
        links.setWordWrap(True)
        layout.addWidget(links)
        layout.addStretch(1)

        self.update_status = QLabel()
        self.update_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.update_status.setWordWrap(True)
        layout.addWidget(self.update_status)
        update_row = QHBoxLayout()
        self.update_button = QPushButton(self._t("about_check_update"))
        self.update_button.clicked.connect(self._update_button_clicked)
        update_row.addStretch(1)
        update_row.addWidget(self.update_button)
        update_row.addStretch(1)
        layout.addLayout(update_row)
        return page

    def _build_skill_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)

        intro = QLabel(self._t("about_skill_intro"))
        intro.setWordWrap(True)
        layout.addWidget(intro)
        actions = QHBoxLayout()
        download_button = QPushButton(self._t("about_skill_download"))
        download_button.setObjectName("skillDownloadButton")
        download_button.clicked.connect(lambda _checked=False: self._open_url(SKILL_DOWNLOAD_URL))
        open_button = QPushButton(self._t("about_skill_open"))
        open_button.setObjectName("skillGuideButton")
        open_button.clicked.connect(lambda _checked=False: self._open_url(SKILL_PROJECT_URL))
        actions.addWidget(download_button)
        actions.addWidget(open_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        guide = QPlainTextEdit()
        guide.setReadOnly(True)
        guide.setPlainText(self._t("about_skill_steps"))
        guide.setFont(QFont("Consolas", 10))
        layout.addWidget(guide, 1)
        return page

    def _open_url(self, url: str) -> None:
        if not open_external_url(url):
            QMessageBox.warning(
                self,
                self._t("about_link_error_title"),
                self._t("about_link_error_message", url=url),
            )

    def _build_support_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        message = QLabel(self._t("about_support_message"))
        message.setWordWrap(True)
        message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(message)

        codes = QHBoxLayout()
        codes.setSpacing(20)
        codes.addWidget(self._donation_column(ASSETS_DIR / "donate-alipay.jpg", self._t("about_alipay")), 1)
        codes.addWidget(self._donation_column(ASSETS_DIR / "donate-wechat.png", self._t("about_wechat")), 1)
        layout.addLayout(codes, 1)
        return page

    def _donation_column(self, path: Path, title: str) -> QWidget:
        column = QWidget()
        layout = QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        heading = QLabel(title)
        heading.setObjectName("sectionTitle")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(heading)
        layout.addWidget(self._qr_label(path), 1)
        return column

    def _qr_label(self, path: Path) -> QLabel:
        label = QLabel()
        label.setObjectName(f"qr_{path.stem}")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = QPixmap(str(path))
        if not pixmap.isNull():
            label.setPixmap(
                pixmap.scaled(
                    290,
                    290,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        return label

    def _update_button_clicked(self) -> None:
        if self.release_url:
            self._open_url(self.release_url)
            return
        self.release_url = ""
        self.update_button.setEnabled(False)
        self.update_status.setText(self._t("about_checking"))
        request = QNetworkRequest(QUrl(LATEST_RELEASE_API))
        request.setRawHeader(b"Accept", b"application/vnd.github+json")
        request.setRawHeader(b"User-Agent", b"SerialProtocolTester-update-check")
        reply = self.network.get(request)
        reply.finished.connect(lambda reply=reply: self._handle_update_reply(reply))

    def _handle_update_reply(self, reply: QNetworkReply) -> None:
        self.update_button.setEnabled(True)
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                raise ValueError(reply.errorString())
            payload = json.loads(bytes(reply.readAll()).decode("utf-8"))
            tag = str(payload.get("tag_name", "")).strip()
            release_url = str(payload.get("html_url", "")).strip()
            if not tag:
                raise ValueError("GitHub response did not contain a release tag")
            if version_key(tag) > version_key(APP_VERSION):
                if not release_url.startswith(PROJECT_URL + "/releases/"):
                    raise ValueError("GitHub response contained an unexpected release URL")
                self.release_url = release_url
                self.update_status.setText(self._t("about_update_available", version=tag))
                self.update_button.setText(self._t("about_open_release"))
            else:
                self.update_status.setText(self._t("about_latest"))
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            self.update_status.setText(self._t("about_update_error", error=exc))
        finally:
            reply.deleteLater()


class VariableInputDialog(QDialog):
    def __init__(
        self,
        frame: dict[str, Any],
        command_name: str,
        language: str,
        previous: dict[str, Any] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.frame = frame
        self.language = language
        self.widgets: dict[str, QWidget] = {}
        defaults = default_variable_values(frame)
        defaults.update(previous or {})
        self.setWindowTitle(ui_text(language, "variable_title", command=command_name))
        self.setMinimumWidth(470)

        root = QVBoxLayout(self)
        form = QFormLayout()
        for variable in frame.get("variables", []):
            name = variable["name"]
            label = localized_value(variable, "label", language, name)
            unit = variable.get("unit", "")
            if unit:
                label = f"{label} ({unit})"
            choices = variable.get("choices")
            if isinstance(choices, dict) and choices:
                widget: QWidget = QComboBox()
                for raw_value, text_value in choices.items():
                    try:
                        value: Any = int(raw_value, 0)
                    except (TypeError, ValueError):
                        try:
                            value = float(raw_value)
                        except (TypeError, ValueError):
                            value = raw_value
                    widget.addItem(str(text_value), value)
                index = widget.findData(defaults.get(name))
                widget.setCurrentIndex(max(0, index))
            elif variable.get("type", "integer") == "number":
                widget = QDoubleSpinBox()
                decimals = int(variable.get("decimals", 3))
                widget.setDecimals(decimals)
                widget.setRange(float(variable.get("min", -1_000_000_000)), float(variable.get("max", 1_000_000_000)))
                widget.setSingleStep(float(variable.get("step", 10 ** -decimals)))
                widget.setValue(float(defaults.get(name, 0)))
            else:
                widget = QSpinBox()
                minimum = max(-2_147_483_648, int(variable.get("min", -2_147_483_648)))
                maximum = min(2_147_483_647, int(variable.get("max", 2_147_483_647)))
                widget.setRange(minimum, maximum)
                widget.setSingleStep(max(1, int(variable.get("step", 1))))
                widget.setValue(int(defaults.get(name, 0)))
            purpose = localized_value(variable, "purpose", language, localized_value(variable, "description", language))
            formulae = [
                field.get("formula", "")
                for field in frame.get("encode", [])
                if isinstance(field, dict) and name in str(field.get("formula", ""))
            ]
            tooltip = purpose
            if formulae:
                formula_label = ui_text(language, "formula")
                tooltip = f"{tooltip}\n{formula_label}: {', '.join(formulae)}".strip()
            widget.setToolTip(tooltip)
            if isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                widget.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
                widget.setMinimumWidth(180)
                editor = QWidget()
                editor_layout = QHBoxLayout(editor)
                editor_layout.setContentsMargins(0, 0, 0, 0)
                editor_layout.setSpacing(6)
                decrease = QToolButton()
                decrease.setText("−")
                decrease.setFixedSize(30, 30)
                decrease.setObjectName(f"decrease_{name}")
                decrease.setToolTip(ui_text(language, "variable_decrease", label=label))
                decrease.clicked.connect(widget.stepDown)
                increase = QToolButton()
                increase.setText("+")
                increase.setFixedSize(30, 30)
                increase.setObjectName(f"increase_{name}")
                increase.setToolTip(ui_text(language, "variable_increase", label=label))
                increase.clicked.connect(widget.stepUp)
                editor_layout.addWidget(decrease)
                editor_layout.addWidget(widget, 1)
                editor_layout.addWidget(increase)
                form.addRow(label, editor)
            else:
                form.addRow(label, widget)
            self.widgets[name] = widget
        root.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(ui_text(language, "variable_ok"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(ui_text(language, "variable_cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def values(self) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for name, widget in self.widgets.items():
            if isinstance(widget, QComboBox):
                values[name] = widget.currentData()
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                values[name] = widget.value()
        return values


class VirtualPortDialog(QDialog):
    def __init__(self, language: str, refresh_callback: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.language = language
        self.refresh_callback = refresh_callback
        self.setWindowTitle(ui_text(language, "vp_title"))
        self.resize(700, 500)
        self.setMinimumSize(620, 430)
        self.pending_ports: tuple[str, str] | None = None
        self.pending_checks = 0
        self._build_ui()
        self._refresh_driver_state()

    def _t(self, key: str, **values: Any) -> Any:
        return ui_text(self.language, key, **values)

    def _port_stepper(self, widget: QSpinBox, name: str) -> QWidget:
        widget.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        editor = QWidget()
        layout = QHBoxLayout(editor)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        decrease = QToolButton()
        decrease.setObjectName(f"decrease_{name}")
        decrease.setText("−")
        decrease.setFixedSize(30, 30)
        decrease.setToolTip(self._t("vp_port_decrease"))
        decrease.clicked.connect(widget.stepDown)
        increase = QToolButton()
        increase.setObjectName(f"increase_{name}")
        increase.setText("+")
        increase.setFixedSize(30, 30)
        increase.setToolTip(self._t("vp_port_increase"))
        increase.clicked.connect(widget.stepUp)
        layout.addWidget(decrease)
        layout.addWidget(widget, 1)
        layout.addWidget(increase)
        return editor

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        intro = QLabel(self._t("vp_intro"))
        intro.setWordWrap(True)
        layout.addWidget(intro)

        download_link = QLabel(f'<a href="{COM0COM_DOWNLOAD_URL}">{self._t("vp_download")}</a>')
        download_link.setOpenExternalLinks(False)
        download_link.linkActivated.connect(open_external_url)
        layout.addWidget(download_link)

        grid = QGridLayout()
        self.setupc_edit = QLineEdit()
        self.setupc_edit.setPlaceholderText(r"C:\Program Files\com0com\setupc.exe")
        browse_button = QPushButton(self._t("vp_browse"))
        browse_button.clicked.connect(self._browse_setupc)
        grid.addWidget(QLabel(self._t("vp_driver")), 0, 0)
        grid.addWidget(self.setupc_edit, 0, 1, 1, 3)
        grid.addWidget(browse_button, 0, 4)

        self.port_a_spin = QSpinBox()
        self.port_a_spin.setRange(1, 256)
        self.port_a_spin.setValue(10)
        self.port_a_spin.setPrefix("COM")
        self.port_b_spin = QSpinBox()
        self.port_b_spin.setRange(1, 256)
        self.port_b_spin.setValue(11)
        self.port_b_spin.setPrefix("COM")
        grid.addWidget(QLabel(self._t("vp_port_a")), 1, 0)
        grid.addWidget(self._port_stepper(self.port_a_spin, "port_a"), 1, 1)
        grid.addWidget(QLabel("↔"), 1, 2, alignment=Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(QLabel(self._t("vp_port_b")), 1, 3)
        grid.addWidget(self._port_stepper(self.port_b_spin, "port_b"), 1, 4)
        layout.addLayout(grid)

        self.driver_status = QLabel()
        self.driver_status.setWordWrap(True)
        layout.addWidget(self.driver_status)
        layout.addWidget(QLabel(self._t("vp_existing")))
        self.pair_output = QPlainTextEdit()
        self.pair_output.setReadOnly(True)
        self.pair_output.setPlaceholderText(self._t("vp_no_output"))
        layout.addWidget(self.pair_output, 1)

        buttons = QHBoxLayout()
        self.create_button = QPushButton(self._t("vp_create"))
        self.create_button.setObjectName("primaryButton")
        self.create_button.clicked.connect(self._create_pair)
        refresh_button = QPushButton(self._t("vp_refresh"))
        refresh_button.clicked.connect(self._refresh_driver_state)
        close_button = QPushButton(self._t("vp_close"))
        close_button.clicked.connect(self.accept)
        buttons.addWidget(self.create_button)
        buttons.addWidget(refresh_button)
        buttons.addStretch(1)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

    def _selected_setupc(self) -> Path | None:
        value = self.setupc_edit.text().strip()
        return find_setupc(value or None)

    def _browse_setupc(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            self._t("vp_select_title"),
            self.setupc_edit.text().strip(),
            self._t("vp_executable_filter"),
        )
        if path:
            self.setupc_edit.setText(path)
            self._refresh_driver_state()

    def _refresh_driver_state(self) -> None:
        setupc = self._selected_setupc()
        problems = query_com0com_driver_problems()
        self.create_button.setEnabled(setupc is not None and not problems and self.pending_ports is None)
        if setupc is None:
            self.driver_status.setText(self._t("vp_not_found"))
            self.driver_status.setStyleSheet("color: #9a4f00;")
            return
        self.setupc_edit.setText(str(setupc))
        output = ""
        try:
            output = list_virtual_pairs(setupc)
        except VirtualPortError as exc:
            output = str(exc)
        if problems:
            unsigned = any(problem.code == 52 or problem.symbol == "CM_PROB_UNSIGNED_DRIVER" for problem in problems)
            codes = ", ".join(sorted({str(problem.code or problem.symbol or "?") for problem in problems}))
            message = self._t("vp_driver_unsigned", count=len(problems)) if unsigned else self._t(
                "vp_driver_problem", count=len(problems), codes=codes
            )
            details = "\n".join(
                f"{problem.instance_id}: {problem.code or '?'} {problem.symbol}".rstrip() for problem in problems
            )
            self.driver_status.setText(message)
            self.driver_status.setStyleSheet("color: #a12b1f; font-weight: 600;")
            self.pair_output.setPlainText(f"{details}\n\n{output}".strip())
            self.refresh_callback()
            return
        unassigned = count_unassigned_ports(output)
        if unassigned:
            self.create_button.setEnabled(False)
            self.driver_status.setText(self._t("vp_unassigned", count=unassigned))
            self.driver_status.setStyleSheet("color: #9a4f00; font-weight: 600;")
            self.pair_output.setPlainText(output)
            self.refresh_callback()
            return
        wrong_class = sorted(non_ports_class_names(output))
        if wrong_class:
            self.driver_status.setText(self._t("vp_wrong_class", ports=", ".join(wrong_class)))
            self.driver_status.setStyleSheet("color: #9a4f00; font-weight: 600;")
            self.pair_output.setPlainText(output)
            self.refresh_callback()
            return
        self.driver_status.setText(self._t("vp_found", path=setupc))
        self.driver_status.setStyleSheet("color: #176b70; font-weight: 600;")
        self.pair_output.setPlainText(output)
        self.refresh_callback()

    def _create_pair(self) -> None:
        setupc = self._selected_setupc()
        if setupc is None:
            QMessageBox.warning(self, self._t("vp_driver_missing_title"), self._t("vp_driver_missing_message"))
            return
        problems = query_com0com_driver_problems()
        if problems:
            self._refresh_driver_state()
            QMessageBox.critical(self, self._t("vp_error_title"), self.driver_status.text())
            return
        port_a = f"COM{self.port_a_spin.value()}"
        port_b = f"COM{self.port_b_spin.value()}"
        if port_a == port_b:
            QMessageBox.warning(self, self._t("vp_invalid_title"), self._t("vp_same_port"))
            return
        try:
            configured_output = list_virtual_pairs(setupc)
        except VirtualPortError as exc:
            QMessageBox.critical(self, self._t("vp_error_title"), str(exc))
            return
        wrong_class_conflicts = sorted({port_a, port_b} & non_ports_class_names(configured_output))
        if wrong_class_conflicts:
            QMessageBox.warning(
                self,
                self._t("vp_wrong_class_title"),
                self._t("vp_wrong_class", ports=", ".join(wrong_class_conflicts)),
            )
            return
        existing = {port.device.upper() for port in list_ports.comports()}
        conflicts = [port for port in (port_a, port_b) if port in existing]
        if conflicts:
            QMessageBox.warning(
                self,
                self._t("vp_conflict_title"),
                self._t("vp_conflict_message", ports=", ".join(conflicts)),
            )
            return
        answer = QMessageBox.question(
            self,
            self._t("vp_uac_title"),
            self._t("vp_uac_message", port_a=port_a, port_b=port_b),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            launch_elevated_install(setupc, port_a, port_b)
        except VirtualPortError as exc:
            QMessageBox.critical(self, self._t("vp_error_title"), str(exc))
            return
        self.pending_ports = (port_a, port_b)
        self.pending_checks = 0
        self.create_button.setEnabled(False)
        self.driver_status.setText(self._t("vp_creating", port_a=port_a, port_b=port_b))
        self.driver_status.setStyleSheet("color: #176b70; font-weight: 600;")
        QTimer.singleShot(1500, self._verify_created_pair)

    def _verify_created_pair(self) -> None:
        if self.pending_ports is None:
            return
        port_a, port_b = self.pending_ports
        self.pending_checks += 1
        problems = query_com0com_driver_problems()
        setupc = self._selected_setupc()
        output = ""
        if setupc is not None:
            try:
                output = list_virtual_pairs(setupc)
            except VirtualPortError as exc:
                output = str(exc)
        available = [port.device for port in list_ports.comports()]
        if not problems and virtual_ports_ready(port_a, port_b, available, output):
            self.pending_ports = None
            self._refresh_driver_state()
            QMessageBox.information(
                self,
                self._t("vp_created_title"),
                self._t("vp_created_message", port_a=port_a, port_b=port_b),
            )
            return
        if problems or self.pending_checks >= 20:
            self.pending_ports = None
            self._refresh_driver_state()
            message = self.driver_status.text() if problems else self._t(
                "vp_verify_failed", port_a=port_a, port_b=port_b
            )
            QMessageBox.critical(self, self._t("vp_error_title"), message)
            return
        QTimer.singleShot(1500, self._verify_created_pair)


class SerialConsole(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.protocol: dict[str, Any] | None = None
        self.protocol_path: Path | None = None
        self.serial_port: serial.SerialBase | None = None
        self.connected = False
        self.last_command: dict[str, Any] | None = None
        self.log_entries: list[dict[str, Any]] = []
        self.variable_values: dict[str, dict[str, Any]] = {}
        self.reply_timers: dict[str, list[QTimer]] = {}
        self.rx_buffer = bytearray()
        self.pending_rx_frames: deque[bytes] = deque()
        self.last_rx_at = 0.0
        self.last_detail_render_at = 0.0
        self.auto_follow_log = True
        self.language = "zh"
        self.baudrate_user_edited = False
        self.last_valid_baudrate = 9600

        self.resize(1380, 840)
        self.setMinimumSize(1050, 680)
        self.setWindowIcon(QIcon(str(LOGO_PATH)))
        self._build_ui()
        self._apply_style()

        self.detail_refresh_timer = QTimer(self)
        self.detail_refresh_timer.setSingleShot(True)
        self.detail_refresh_timer.timeout.connect(self._select_latest_log_and_render)

        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(20)
        self.poll_timer.timeout.connect(self._poll_serial)
        self.poll_timer.start()

        self._refresh_ports()
        if SAMPLE_PROTOCOL.exists():
            self._load_protocol_file(SAMPLE_PROTOCOL)

    def _build_ui(self) -> None:
        central = QWidget(self)
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 14, 14, 10)
        root.setSpacing(10)

        file_row = QHBoxLayout()
        self.protocol_label = QLabel()
        self.protocol_label.setObjectName("protocolTitle")
        self.load_button = QPushButton()
        self.load_button.clicked.connect(self._choose_protocol)
        self.language_combo = QComboBox()
        self.language_combo.setObjectName("languageCombo")
        self.language_combo.setMinimumWidth(145)
        for code, name in LANGUAGE_OPTIONS:
            self.language_combo.addItem(name, code)
        self.language_combo.setCurrentIndex(self.language_combo.findData(self.language))
        self.language_combo.currentIndexChanged.connect(self._change_language)
        self.about_button = QToolButton()
        self.about_button.setFixedSize(34, 34)
        self.about_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation))
        self.about_button.clicked.connect(self._show_about)
        file_row.addWidget(self.protocol_label, 1)
        file_row.addWidget(self.about_button)
        file_row.addWidget(self.language_combo)
        file_row.addWidget(self.load_button)
        root.addLayout(file_row)

        self.settings_group = QGroupBox()
        settings_layout = QHBoxLayout(self.settings_group)

        left_form = QFormLayout()
        self.role_label = QLabel()
        self.role_combo = QComboBox()
        self.role_combo.addItem("", "host")
        self.role_combo.addItem("", "device")
        self.role_combo.currentIndexChanged.connect(self._sync_role_ui)
        left_form.addRow(self.role_label, self.role_combo)

        self.transport_label = QLabel()
        self.transport_combo = QComboBox()
        self.transport_combo.addItem("", "internal")
        self.transport_combo.addItem("", "serial")
        self.transport_combo.currentIndexChanged.connect(self._sync_transport_ui)
        left_form.addRow(self.transport_label, self.transport_combo)
        settings_layout.addLayout(left_form, 2)

        middle_form = QFormLayout()
        self.endpoint_label = QLabel()
        port_row = QHBoxLayout()
        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        self.port_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.port_combo.setPlaceholderText("COM3 or loop://")
        self.refresh_button = QPushButton()
        self.refresh_button.clicked.connect(self._refresh_ports)
        self.virtual_ports_button = QPushButton()
        self.virtual_ports_button.clicked.connect(self._show_virtual_ports)
        port_row.addWidget(self.port_combo, 1)
        port_row.addWidget(self.refresh_button)
        port_row.addWidget(self.virtual_ports_button)
        middle_form.addRow(self.endpoint_label, port_row)

        self.baudrate_label = QLabel()
        self.baudrate_combo = QComboBox()
        self.baudrate_combo.setEditable(True)
        self.baudrate_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.baudrate_combo.addItems([str(value) for value in COMMON_BAUDRATES])
        self.baudrate_combo.setCurrentText("9600")
        baudrate_editor = self.baudrate_combo.lineEdit()
        if baudrate_editor is not None:
            baudrate_editor.setValidator(QIntValidator(50, 4_000_000, self.baudrate_combo))
            baudrate_editor.editingFinished.connect(self._commit_baudrate_edit)
        self.baudrate_combo.activated.connect(self._mark_baudrate_user_edited)
        middle_form.addRow(self.baudrate_label, self.baudrate_combo)
        settings_layout.addLayout(middle_form, 3)

        serial_form = QFormLayout()
        self.bytesize_label = QLabel()
        self.bytesize_combo = QComboBox()
        self.bytesize_combo.addItems(["5", "6", "7", "8"])
        self.bytesize_combo.setCurrentText("8")
        serial_form.addRow(self.bytesize_label, self.bytesize_combo)
        self.parity_label = QLabel()
        self.parity_combo = QComboBox()
        for value in ("N", "E", "O", "M", "S"):
            self.parity_combo.addItem("", value)
        serial_form.addRow(self.parity_label, self.parity_combo)
        self.stopbits_label = QLabel()
        self.stopbits_combo = QComboBox()
        self.stopbits_combo.addItems(["1", "1.5", "2"])
        serial_form.addRow(self.stopbits_label, self.stopbits_combo)
        settings_layout.addLayout(serial_form, 2)

        action_column = QVBoxLayout()
        self.connect_button = QPushButton()
        self.connect_button.setObjectName("primaryButton")
        self.connect_button.clicked.connect(self._toggle_connection)
        self.connection_label = QLabel()
        self.connection_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        action_column.addWidget(self.connect_button)
        action_column.addWidget(self.connection_label)
        action_column.addStretch(1)
        settings_layout.addLayout(action_column, 1)
        root.addWidget(self.settings_group)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        self.command_group = QGroupBox()
        command_layout = QVBoxLayout(self.command_group)
        self.command_table = QTableWidget(0, 6)
        self.command_table.setHorizontalHeaderLabels(["", "", "", "", "", ""])
        self.command_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.command_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.command_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.command_table.setAlternatingRowColors(True)
        self.command_table.verticalHeader().setVisible(False)
        header = self.command_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.command_table.itemSelectionChanged.connect(self._show_selected_command)
        self.command_table.cellDoubleClicked.connect(lambda _row, _column: self._run_selected_command())
        command_layout.addWidget(self.command_table, 1)

        detail_row = QHBoxLayout()
        self.command_detail = QLineEdit()
        self.command_detail.setReadOnly(True)
        self.command_action_button = QPushButton()
        self.command_action_button.setObjectName("primaryButton")
        self.command_action_button.clicked.connect(self._run_selected_command)
        detail_row.addWidget(self.command_detail, 1)
        detail_row.addWidget(self.command_action_button)
        command_layout.addLayout(detail_row)
        splitter.addWidget(self.command_group)

        self.output_group = QGroupBox()
        output_layout = QVBoxLayout(self.output_group)
        self.log_table = QTableWidget(0, 5)
        self.log_table.setHorizontalHeaderLabels(["", "", "", "", ""])
        self.log_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.log_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.log_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.log_table.setAlternatingRowColors(True)
        self.log_table.setWordWrap(False)
        self.log_table.verticalHeader().setVisible(False)
        self.log_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.log_table.verticalHeader().setDefaultSectionSize(24)
        self.log_table.itemSelectionChanged.connect(self._show_selected_log_details)
        log_header = self.log_table.horizontalHeader()
        log_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        log_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        log_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        log_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        log_header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        output_layout.addWidget(self.log_table, 3)

        decoded_header = QHBoxLayout()
        self.decoded_fields_label = QLabel()
        decoded_header.addWidget(self.decoded_fields_label)
        decoded_header.addStretch(1)
        self.clear_button = QPushButton()
        self.clear_button.clicked.connect(self._clear_output)
        decoded_header.addWidget(self.clear_button)
        output_layout.addLayout(decoded_header)

        self.decoded_table = QTableWidget(0, 8)
        self.decoded_table.setHorizontalHeaderLabels(["", "", "", "", "", "", "", ""])
        self.decoded_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.decoded_table.verticalHeader().setVisible(False)
        decoded_table_header = self.decoded_table.horizontalHeader()
        decoded_table_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        decoded_table_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        decoded_table_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        decoded_table_header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        decoded_table_header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        decoded_table_header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        decoded_table_header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        decoded_table_header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        output_layout.addWidget(self.decoded_table, 2)
        splitter.addWidget(self.output_group)
        splitter.setSizes([760, 620])
        root.addWidget(splitter, 1)

        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar(self))
        self._retranslate_ui()
        self._sync_transport_ui()
        self._sync_role_ui()

    def _t(self, key: str, **values: Any) -> Any:
        return ui_text(self.language, key, **values)

    def _change_language(self, index: int) -> None:
        language = self.language_combo.itemData(index)
        if language and language != self.language:
            self.language = language
            self._retranslate_ui()

    def _retranslate_ui(self) -> None:
        self.setWindowTitle(self._t("title"))
        self.about_button.setToolTip(self._t("about_tooltip"))
        self.load_button.setText(self._t("load_protocol"))
        self.settings_group.setTitle(self._t("connection"))
        self.role_label.setText(self._t("role"))
        self.role_combo.setItemText(0, self._t("host"))
        self.role_combo.setItemText(1, self._t("device"))
        self.transport_label.setText(self._t("transport"))
        self.transport_combo.setItemText(0, self._t("internal_transport"))
        self.transport_combo.setItemText(1, self._t("serial_transport"))
        self.endpoint_label.setText(self._t("endpoint"))
        self.refresh_button.setText(self._t("refresh"))
        self.virtual_ports_button.setText(self._t("virtual_ports"))
        self.baudrate_label.setText(self._t("baudrate"))
        self.bytesize_label.setText(self._t("data_bits"))
        self.parity_label.setText(self._t("parity"))
        for index, key in enumerate(("parity_none", "parity_even", "parity_odd", "parity_mark", "parity_space")):
            self.parity_combo.setItemText(index, self._t(key))
        self.stopbits_label.setText(self._t("stop_bits"))
        self.command_group.setTitle(self._t("commands"))
        self.command_table.setHorizontalHeaderLabels(self._t("command_headers"))
        self.command_detail.setPlaceholderText(self._t("select_command"))
        self.output_group.setTitle(self._t("traffic"))
        self.log_table.setHorizontalHeaderLabels(self._t("log_headers"))
        self.decoded_fields_label.setText(self._t("decoded_fields"))
        self.clear_button.setText(self._t("clear"))
        self.decoded_table.setHorizontalHeaderLabels(self._t("decoded_headers"))
        if self.connected:
            self.connect_button.setText(self._t("close"))
            self.connection_label.setText(self._t("opened"))
            endpoint = self._t("internal_name") if self.transport_combo.currentData() == "internal" else self.port_combo.currentText()
            self.statusBar().showMessage(self._t("connected", endpoint=endpoint))
        else:
            self.connect_button.setText(self._t("open"))
            self.connection_label.setText(self._t("closed"))
            if self.protocol:
                self.statusBar().showMessage(self._t("loaded_commands", count=len(self.protocol["commands"])))
            else:
                self.protocol_label.setText(self._t("no_protocol"))
                self.statusBar().showMessage(self._t("ready"))
        if self.protocol:
            selected_row = max(0, self.command_table.currentRow())
            self.protocol_label.setText(
                f"{localized_value(self.protocol, 'name', self.language)}  ·  {self.protocol_path.name if self.protocol_path else ''}"
            )
            self._populate_commands(selected_row)
        self._render_frame_details()
        self._sync_role_ui()

    def _show_virtual_ports(self) -> None:
        dialog = VirtualPortDialog(self.language, self._refresh_ports, self)
        dialog.exec()
        self._refresh_ports()

    def _show_about(self) -> None:
        AboutDialog(self.language, self).exec()

    def _set_baudrate_value(self, value: int) -> None:
        baudrate = int(value)
        if not 50 <= baudrate <= 4_000_000:
            raise ValueError(self._t("baudrate_invalid"))
        text = str(baudrate)
        if self.baudrate_combo.findText(text) < 0:
            self.baudrate_combo.addItem(text)
        self.baudrate_combo.setCurrentText(text)
        self.last_valid_baudrate = baudrate

    def _current_baudrate(self) -> int:
        text = self.baudrate_combo.currentText().strip()
        if not text.isdigit():
            raise ValueError(self._t("baudrate_invalid"))
        baudrate = int(text)
        if not 50 <= baudrate <= 4_000_000:
            raise ValueError(self._t("baudrate_invalid"))
        return baudrate

    def _apply_baudrate_edit(self) -> None:
        try:
            baudrate = self._current_baudrate()
            self._set_baudrate_value(baudrate)
            if self.serial_port is not None:
                self.serial_port.baudrate = baudrate
        except (ValueError, serial.SerialException) as exc:
            self.baudrate_combo.setCurrentText(str(self.last_valid_baudrate))
            QMessageBox.warning(self, self._t("connection_failed"), str(exc))

    def _mark_baudrate_user_edited(self, *_args: Any) -> None:
        self.baudrate_user_edited = True
        self._apply_baudrate_edit()

    def _commit_baudrate_edit(self) -> None:
        self.baudrate_user_edited = True
        self._apply_baudrate_edit()

    def _apply_style(self) -> None:
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self.command_table.setFont(mono)
        self.log_table.setFont(mono)
        self.decoded_table.setFont(mono)
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #f5f7f8; color: #1d262d; font-size: 13px; }
            QGroupBox { background: #ffffff; border: 1px solid #cfd7dc; border-radius: 6px;
                        margin-top: 12px; padding-top: 10px; font-weight: 600; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
            QLabel#protocolTitle { font-size: 18px; font-weight: 700; color: #172126; }
            QLabel#aboutName { font-size: 20px; font-weight: 700; color: #172126; }
            QLabel#sectionTitle { font-weight: 700; color: #26343a; }
            QPushButton { min-height: 30px; padding: 0 12px; background: #ffffff;
                          border: 1px solid #aebbc2; border-radius: 5px; }
            QPushButton:hover { background: #eef4f4; border-color: #608087; }
            QPushButton:disabled { color: #8b969c; background: #edf0f1; }
            QPushButton#primaryButton { color: #ffffff; background: #176b70; border-color: #176b70; font-weight: 600; }
            QPushButton#primaryButton:hover { background: #10585d; }
            QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit { min-height: 28px; background: #ffffff;
                                            border: 1px solid #b9c4ca; border-radius: 4px; padding: 0 6px; }
            QTableWidget { background: #ffffff; alternate-background-color: #f2f6f6;
                           border: 1px solid #cfd7dc; gridline-color: #dce3e6; }
            QHeaderView::section { background: #e7ecee; color: #26343a; padding: 7px;
                                   border: 0; border-right: 1px solid #ccd5d9; font-weight: 600; }
            QTableWidget::item:selected { background: #cfe4e4; color: #101719; }
            QStatusBar { background: #e7ecee; }
            """
        )

    def _choose_protocol(self) -> None:
        start_dir = str(self.protocol_path.parent if self.protocol_path else ROOT)
        path, _ = QFileDialog.getOpenFileName(
            self,
            self._t("load_dialog_title"),
            start_dir,
            self._t("file_filter"),
        )
        if path:
            self._load_protocol_file(Path(path))

    def _load_protocol_file(self, path: Path) -> None:
        try:
            protocol = load_protocol(path)
        except ProtocolError as exc:
            QMessageBox.critical(self, self._t("protocol_error"), str(exc))
            return
        self._stop_all_reply_streams()
        self.protocol = protocol
        self.protocol_path = path
        self.protocol_label.setText(f"{localized_value(protocol, 'name', self.language)}  ·  {path.name}")
        defaults = protocol["serial"]["defaults"]
        self.baudrate_user_edited = False
        self._set_baudrate_value(defaults["baudrate"])
        self.bytesize_combo.setCurrentText(str(defaults.get("bytesize", 8)))
        parity_index = self.parity_combo.findData(defaults.get("parity", "N"))
        self.parity_combo.setCurrentIndex(max(0, parity_index))
        self.stopbits_combo.setCurrentText(str(defaults.get("stopbits", 1)))
        self._populate_commands()
        self.statusBar().showMessage(self._t("loaded_commands", count=len(protocol["commands"])))

    def _populate_commands(self, selected_row: int = 0) -> None:
        commands = self.protocol["commands"] if self.protocol else []
        default_baud = self._serial_defaults().get("baudrate", 9600)
        self.command_table.setRowCount(len(commands))
        for row, command in enumerate(commands):
            request = format_hex(encode_frame(command["request"]))
            response = format_hex(encode_frame(command["response"])) if command.get("response") else "—"
            values = [
                localized_value(command, "name", self.language),
                request,
                localized_value(command, "description", self.language),
                str(command.get("baudrate", default_baud)),
                response,
                command["id"],
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                self.command_table.setItem(row, column, item)
        if commands:
            self.command_table.selectRow(min(selected_row, len(commands) - 1))

    def _selected_command(self) -> dict[str, Any] | None:
        if not self.protocol:
            return None
        row = self.command_table.currentRow()
        if row < 0 or row >= len(self.protocol["commands"]):
            return None
        return self.protocol["commands"][row]

    def _show_selected_command(self) -> None:
        command = self._selected_command()
        if not command:
            self.command_detail.clear()
            return
        request = format_hex(encode_frame(command["request"]))
        description = localized_value(command, "description", self.language)
        self.command_detail.setText(f"{command['id']}  |  {request}  |  {description}")

    def _sync_role_ui(self) -> None:
        role = self.role_combo.currentData()
        if role == "host":
            self.command_action_button.setText(self._t("send_request"))
        elif self.transport_combo.currentData() == "internal":
            self.command_action_button.setText(self._t("simulate_request"))
        else:
            self.command_action_button.setText(self._t("send_response"))

    def _sync_transport_ui(self) -> None:
        serial_enabled = self.transport_combo.currentData() == "serial"
        self.port_combo.setEnabled(serial_enabled and not self.connected)
        self.bytesize_combo.setEnabled(serial_enabled and not self.connected)
        self.parity_combo.setEnabled(serial_enabled and not self.connected)
        self.stopbits_combo.setEnabled(serial_enabled and not self.connected)
        self._sync_role_ui()

    def _refresh_ports(self) -> None:
        current = self.port_combo.currentText() if hasattr(self, "port_combo") else ""
        if not hasattr(self, "port_combo"):
            return
        ports = [port.device for port in list_ports.comports()]
        self.port_combo.clear()
        self.port_combo.addItems(ports)
        if current:
            index = self.port_combo.findText(current)
            if index >= 0:
                self.port_combo.setCurrentIndex(index)
            else:
                self.port_combo.setEditText(current)

    def _serial_defaults(self) -> dict[str, Any]:
        if not self.protocol:
            return {"baudrate": 9600, "bytesize": 8, "parity": "N", "stopbits": 1, "timeout_ms": 200}
        return self.protocol["serial"]["defaults"]

    def _toggle_connection(self) -> None:
        if self.connected:
            self._close_connection()
        else:
            self._open_connection()

    def _open_connection(self) -> None:
        if not self.protocol:
            QMessageBox.warning(self, self._t("no_protocol_title"), self._t("no_protocol_message"))
            return
        transport = self.transport_combo.currentData()
        try:
            if transport == "serial":
                endpoint = self.port_combo.currentText().strip()
                if not endpoint:
                    raise ValueError(self._t("endpoint_required"))
                self.serial_port = serial.serial_for_url(
                    endpoint,
                    baudrate=self._current_baudrate(),
                    bytesize=int(self.bytesize_combo.currentText()),
                    parity=self.parity_combo.currentData(),
                    stopbits=float(self.stopbits_combo.currentText()),
                    timeout=0,
                    write_timeout=1,
                )
            self.connected = True
            self.rx_buffer.clear()
            self.pending_rx_frames.clear()
            self.connect_button.setText(self._t("close"))
            self.connection_label.setText(self._t("opened"))
            self.connection_label.setStyleSheet("color: #176b70; font-weight: 700;")
            self.transport_combo.setEnabled(False)
            self.role_combo.setEnabled(False)
            self._sync_transport_ui()
            endpoint_name = self._t("internal_name") if transport == "internal" else self.port_combo.currentText()
            self.statusBar().showMessage(self._t("connected", endpoint=endpoint_name))
        except (serial.SerialException, ValueError, OSError) as exc:
            QMessageBox.critical(self, self._t("connection_failed"), str(exc))
            self.statusBar().showMessage(self._t("connection_failed_status", error=exc))

    def _close_connection(self) -> None:
        self._stop_all_reply_streams()
        if self.serial_port is not None:
            try:
                self.serial_port.close()
            except serial.SerialException:
                pass
        self.serial_port = None
        self.connected = False
        self.rx_buffer.clear()
        self.pending_rx_frames.clear()
        self.detail_refresh_timer.stop()
        self.connect_button.setText(self._t("open"))
        self.connection_label.setText(self._t("closed"))
        self.connection_label.setStyleSheet("")
        self.transport_combo.setEnabled(True)
        self.role_combo.setEnabled(True)
        self._sync_transport_ui()
        self.statusBar().showMessage(self._t("closed_status"))

    def _set_command_baudrate(self, command: dict[str, Any]) -> None:
        if not self.baudrate_user_edited:
            self._set_baudrate_value(command.get("baudrate", self._serial_defaults()["baudrate"]))
        baudrate = self._current_baudrate()
        if self.serial_port is not None:
            self.serial_port.baudrate = baudrate

    def _run_selected_command(self) -> None:
        command = self._selected_command()
        if not command:
            QMessageBox.information(self, self._t("no_command_title"), self._t("no_command_message"))
            return
        if not self.connected:
            QMessageBox.information(self, self._t("not_connected_title"), self._t("not_connected_message"))
            return
        try:
            self._set_command_baudrate(command)
            role = self.role_combo.currentData()
            internal = self.transport_combo.currentData() == "internal"
            if role == "host":
                prepared = self._prepare_request(command)
                if prepared is None:
                    return
                request, request_spec = prepared
                self.last_command = command
                self._transmit(request, command, "TX", request_spec)
                if internal and (command.get("response") or command.get("follow_up_replies") or command.get("stop_streams")):
                    QTimer.singleShot(80, lambda: self._receive_internal_response(command))
            elif internal:
                prepared = self._prepare_request(command)
                if prepared is None:
                    return
                request, _request_spec = prepared
                self._handle_received_frame(request)
            elif command.get("response"):
                self._transmit(encode_frame(command["response"]), command, "TX", command["response"])
            else:
                QMessageBox.information(self, self._t("no_response_title"), self._t("no_response_message"))
        except (ProtocolError, serial.SerialException, OSError, ValueError) as exc:
            self._report_runtime_error(exc)

    def _prepare_request(self, command: dict[str, Any]) -> tuple[bytes, dict[str, Any]] | None:
        frame = command["request"]
        variables = frame.get("variables", [])
        if not variables:
            return encode_frame(frame), frame
        command_name = localized_value(command, "name", self.language, command["id"])
        dialog = VariableInputDialog(
            frame,
            command_name,
            self.language,
            self.variable_values.get(command["id"]),
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        values = dialog.values()
        self.variable_values[command["id"]] = values
        runtime_spec = dict(frame)
        runtime_spec["_runtime_values"] = values
        return encode_frame(frame, values), runtime_spec

    def _transmit(
        self,
        data: bytes,
        command: dict[str, Any] | None,
        direction: str,
        frame_spec: dict[str, Any] | None = None,
    ) -> None:
        if self.transport_combo.currentData() == "serial":
            if self.serial_port is None:
                raise serial.SerialException("serial port is not open")
            self.serial_port.write(data)
            self.serial_port.flush()
        self._append_log(direction, data, command, frame_spec)

    def _receive_internal_response(self, command: dict[str, Any]) -> None:
        if not self.connected or self.transport_combo.currentData() != "internal":
            return
        self._stop_reply_streams(command.get("stop_streams", []))
        response = command.get("response")
        if response:
            self._handle_received_frame(encode_frame(response), command)
        self._schedule_follow_up_replies(command, "RX")

    def _poll_serial(self) -> None:
        if not self.connected or self.serial_port is None:
            return
        try:
            waiting = self.serial_port.in_waiting
            if waiting:
                self.rx_buffer.extend(self.serial_port.read(waiting))
                self.last_rx_at = time.monotonic()
                framing = self.protocol.get("framing") if self.protocol else None
                if isinstance(framing, dict):
                    frames, remainder = split_framed_bytes(bytes(self.rx_buffer), framing)
                    self.rx_buffer = bytearray(remainder)
                    self.pending_rx_frames.extend(frames)
            elif (
                self.rx_buffer
                and not (self.protocol and isinstance(self.protocol.get("framing"), dict))
                and time.monotonic() - self.last_rx_at >= 0.04
            ):
                frame = bytes(self.rx_buffer)
                self.rx_buffer.clear()
                self.pending_rx_frames.append(frame)
            self._drain_received_frames()
        except (serial.SerialException, OSError) as exc:
            self._report_runtime_error(exc)
            self._close_connection()

    def _drain_received_frames(self) -> None:
        for _index in range(min(len(self.pending_rx_frames), MAX_RX_FRAMES_PER_POLL)):
            self._handle_received_frame(self.pending_rx_frames.popleft())

    def _handle_received_frame(self, data: bytes, known_command: dict[str, Any] | None = None) -> None:
        command = known_command
        passive_frame: dict[str, Any] | None = None
        matched_request = False
        if command is None and self.protocol:
            try:
                if self.role_combo.currentData() == "device":
                    command = find_matching_command(data, self.protocol["commands"])
                    matched_request = command is not None
                    if command is None:
                        passive_frame = find_matching_frame(data, self.protocol.get("frames", []))
                else:
                    passive_frame = find_matching_frame(data, self.protocol.get("frames", []))
                    if passive_frame is None:
                        command = find_matching_command(data, self.protocol["commands"])
                        matched_request = command is not None
                    if passive_frame is None and command is None:
                        command = self.last_command
            except ProtocolError as exc:
                self._report_runtime_error(exc)
        elif self.protocol:
            try:
                passive_frame = find_matching_frame(data, self.protocol.get("frames", []))
            except ProtocolError as exc:
                self._report_runtime_error(exc)
        definition = passive_frame or command
        if passive_frame:
            frame_spec = passive_frame
        elif command and matched_request:
            frame_spec = command.get("request")
        elif command and self.role_combo.currentData() == "host":
            frame_spec = command.get("response")
        elif command:
            frame_spec = command.get("request")
        else:
            frame_spec = None
        self._append_log("RX", data, definition, frame_spec)
        if command and self.role_combo.currentData() == "host":
            self.last_command = command
        has_reply_behavior = command and (
            command.get("response") or command.get("follow_up_replies") or command.get("stop_streams")
        )
        if command and self.role_combo.currentData() == "device" and command.get("auto_reply") and has_reply_behavior:
            QTimer.singleShot(50, lambda: self._send_automatic_response(command))
        elif self.role_combo.currentData() == "device" and command and matched_request:
            command_name = localized_value(command, "name", self.language, command.get("id", self._t("unmatched")))
            self.statusBar().showMessage(self._t("rx_auto_reply_disabled", command=command_name))
        elif self.role_combo.currentData() == "device" and command is None and passive_frame is None:
            self.statusBar().showMessage(self._t("rx_device_unmatched", count=len(data)))
        elif self.role_combo.currentData() == "host" and command and matched_request:
            command_name = localized_value(command, "name", self.language, command.get("id", self._t("unmatched")))
            self.statusBar().showMessage(self._t("rx_host_request", command=command_name))

    def _send_automatic_response(self, command: dict[str, Any]) -> None:
        if not self.connected:
            return
        try:
            self._stop_reply_streams(command.get("stop_streams", []))
            response_spec = command.get("response")
            if response_spec:
                self._transmit(encode_frame(response_spec), command, "TX", response_spec)
            self._schedule_follow_up_replies(command, "TX")
        except (ProtocolError, serial.SerialException, OSError) as exc:
            self._report_runtime_error(exc)

    def _schedule_follow_up_replies(self, command: dict[str, Any], direction: str) -> None:
        if not self.protocol:
            return
        for index, reply in enumerate(command.get("follow_up_replies", [])):
            frame_spec = resolve_follow_up_frame(self.protocol, reply)
            interval_ms = reply.get("interval_ms")
            repeat_count = reply.get("repeat_count", 0 if interval_ms is not None else 1)
            stream_id = reply.get("stream_id") or f"{command['id']}:{index}"
            if stream_id in self.reply_timers:
                self._stop_reply_streams([stream_id])

            prepared_values: dict[str, Any] | None = None
            if frame_spec.get("variables") and reply.get("prompt_variables", False):
                frame_name = localized_value(frame_spec, "name", self.language, stream_id)
                value_key = f"stream:{stream_id}"
                dialog = VariableInputDialog(
                    frame_spec,
                    frame_name,
                    self.language,
                    self.variable_values.get(value_key),
                    self,
                )
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    continue
                prepared_values = dialog.values()
                self.variable_values[value_key] = prepared_values

            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.setInterval(reply.get("delay_ms", 0))
            self.reply_timers.setdefault(stream_id, []).append(timer)
            state = {"sent": 0}

            def emit_reply(
                timer: QTimer = timer,
                stream_id: str = stream_id,
                frame_spec: dict[str, Any] = frame_spec,
                interval_ms: int | None = interval_ms,
                repeat_count: int = repeat_count,
                direction: str = direction,
                state: dict[str, int] = state,
                prepared_values: dict[str, Any] | None = prepared_values,
            ) -> None:
                if not self.connected:
                    self._remove_reply_timer(stream_id, timer)
                    return
                try:
                    values = dict(prepared_values) if prepared_values is not None else default_variable_values(frame_spec)
                    runtime_spec = dict(frame_spec)
                    if values:
                        runtime_spec["_runtime_values"] = values
                    data = encode_frame(frame_spec, values)
                    if direction == "TX":
                        self._transmit(data, frame_spec, "TX", runtime_spec)
                    else:
                        self._handle_received_frame(data)
                    state["sent"] += 1
                    if interval_ms is not None and (repeat_count == 0 or state["sent"] < repeat_count):
                        timer.setSingleShot(False)
                        timer.setInterval(interval_ms)
                        timer.start()
                    else:
                        self._remove_reply_timer(stream_id, timer)
                except (ProtocolError, serial.SerialException, OSError, ValueError) as exc:
                    self._remove_reply_timer(stream_id, timer)
                    self._report_runtime_error(exc)

            timer.timeout.connect(emit_reply)
            timer.start()

    def _remove_reply_timer(self, stream_id: str, timer: QTimer) -> None:
        timer.stop()
        timers = self.reply_timers.get(stream_id, [])
        if timer in timers:
            timers.remove(timer)
        if not timers:
            self.reply_timers.pop(stream_id, None)
        timer.deleteLater()

    def _stop_reply_streams(self, stream_ids: list[str]) -> None:
        for stream_id in stream_ids:
            for timer in list(self.reply_timers.pop(stream_id, [])):
                timer.stop()
                timer.deleteLater()

    def _stop_all_reply_streams(self) -> None:
        self._stop_reply_streams(list(self.reply_timers))

    def _append_log(
        self,
        direction: str,
        data: bytes,
        command: dict[str, Any] | None,
        frame_spec: dict[str, Any] | None,
    ) -> None:
        self._trim_log_history()
        row = self.log_table.rowCount()
        now = time.strftime("%H:%M:%S") + f".{int(time.time() * 1000) % 1000:03d}"
        try:
            text_preview = data.decode("utf-8").replace("\r", "\\r").replace("\n", "\\n")
            if not text_preview.isprintable():
                text_preview = ""
        except UnicodeDecodeError:
            text_preview = ""
        command_name = localized_value(command, "name", self.language, self._t("unmatched")) if command else self._t("unmatched")
        self.log_entries.append(
            {
                "time": now,
                "direction": direction,
                "data": bytes(data),
                "command": command,
                "frame_spec": frame_spec,
            }
        )
        self.log_table.setUpdatesEnabled(False)
        try:
            self.log_table.insertRow(row)
            values = [now, direction, command_name, format_hex(data), text_preview]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                if column == 1:
                    item.setForeground(Qt.GlobalColor.darkGreen if direction == "RX" else Qt.GlobalColor.darkBlue)
                self.log_table.setItem(row, column, item)
        finally:
            self.log_table.setUpdatesEnabled(True)

        if self.auto_follow_log:
            if frame_spec and frame_spec.get("repeat_group"):
                self._schedule_live_detail_refresh()
            else:
                self.detail_refresh_timer.stop()
                self._select_latest_log_and_render()
        self.statusBar().showMessage(
            self._t("traffic_status", direction=direction, count=len(data), command=command_name)
        )

    def _trim_log_history(self) -> None:
        row_count = self.log_table.rowCount()
        if row_count < MAX_TRAFFIC_ROWS:
            return
        remove_count = min(TRAFFIC_TRIM_ROWS, row_count)
        selected_row = self.log_table.currentRow()
        blocker = QSignalBlocker(self.log_table)
        self.log_table.setUpdatesEnabled(False)
        try:
            for _index in range(remove_count):
                self.log_table.removeRow(0)
            del self.log_entries[:remove_count]
            if not self.auto_follow_log and self.log_table.rowCount():
                self.log_table.selectRow(max(0, selected_row - remove_count))
        finally:
            self.log_table.setUpdatesEnabled(True)
            del blocker
        if not self.auto_follow_log:
            self._render_frame_details()

    def _schedule_live_detail_refresh(self) -> None:
        elapsed_ms = (time.monotonic() - self.last_detail_render_at) * 1000
        if elapsed_ms >= LIVE_DETAIL_REFRESH_MS and not self.detail_refresh_timer.isActive():
            self._select_latest_log_and_render()
            return
        if not self.detail_refresh_timer.isActive():
            self.detail_refresh_timer.start(max(1, int(LIVE_DETAIL_REFRESH_MS - elapsed_ms)))

    def _select_latest_log_and_render(self) -> None:
        if not self.auto_follow_log or not self.log_table.rowCount():
            return
        blocker = QSignalBlocker(self.log_table)
        self.log_table.selectRow(self.log_table.rowCount() - 1)
        del blocker
        self.log_table.scrollToBottom()
        self._render_frame_details()

    def _show_selected_log_details(self) -> None:
        self.detail_refresh_timer.stop()
        self.auto_follow_log = self.log_table.currentRow() == self.log_table.rowCount() - 1
        self._render_frame_details()

    def _render_frame_details(self) -> None:
        if not hasattr(self, "decoded_table"):
            return
        self.last_detail_render_at = time.monotonic()
        framing = self.protocol.get("framing") if self.protocol else None
        details: list[dict[str, str]] = []
        row = self.log_table.currentRow() if hasattr(self, "log_table") else -1
        entry = self.log_entries[row] if 0 <= row < len(self.log_entries) else None
        if entry is not None:
            direction = entry["direction"]
            data = entry["data"]
            frame_spec = entry["frame_spec"]
            for field in decode_frame_details(data, frame_spec, framing, self.language):
                details.append({"direction": direction, **field})
            command = entry["command"]
            command_name = localized_value(command, "name", self.language, self._t("unmatched")) if command else self._t("unmatched")
            self.decoded_fields_label.setText(
                self._t(
                    "decoded_fields_selected",
                    time=entry["time"],
                    direction=direction,
                    command=command_name,
                )
            )
        else:
            self.decoded_fields_label.setText(self._t("decoded_fields"))
        self.decoded_table.setRowCount(len(details))
        for row, field in enumerate(details):
            values = [
                field["direction"],
                field["byte_range"],
                field["field"],
                field["purpose"],
                field["raw"],
                field["rule"],
                field["calculation"],
                field["result"],
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                if column == 0:
                    item.setForeground(Qt.GlobalColor.darkGreen if value == "RX" else Qt.GlobalColor.darkBlue)
                self.decoded_table.setItem(row, column, item)

    def _clear_output(self) -> None:
        self.detail_refresh_timer.stop()
        self.log_table.setRowCount(0)
        self.log_entries.clear()
        self.decoded_table.setRowCount(0)
        self.auto_follow_log = True
        self.last_detail_render_at = 0.0
        self.statusBar().showMessage(self._t("output_cleared"))

    def _report_runtime_error(self, error: Exception) -> None:
        QMessageBox.critical(self, self._t("serial_error"), str(error))
        self.statusBar().showMessage(self._t("error_status", error=error))

    def closeEvent(self, event: Any) -> None:
        self._close_connection()
        event.accept()


def main() -> int:
    if "--self-test" not in sys.argv and relaunch_as_admin():
        return 0
    app = QApplication(sys.argv)
    app.setApplicationName("Serial Protocol Tester")
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("10walnut")
    app.setWindowIcon(QIcon(str(LOGO_PATH)))
    window = SerialConsole()
    if "--self-test" in sys.argv:
        if window.command_table.rowCount() == 0 or window.decoded_table.columnCount() != 8:
            return 2
        window.close()
        return 0
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
