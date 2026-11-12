"""Cross-platform serial endpoint helpers for the PySide6 serial tester.

This module depends only on the Python standard library and
``serial.tools.list_ports`` so it can be imported and unit tested without
PySide6, without opening a device and without network access.

All platform checks are performed lazily through ``sys.platform`` / ``os.name``
so ``unittest.mock.patch("serial_ports.sys.platform", ...)`` works as expected.
"""

from __future__ import annotations

import glob
import os
import re
import stat
import sys
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from serial.tools import list_ports


URL_SCHEMES: frozenset[str] = frozenset(
    {"loop", "socket", "rfc2217", "spy", "alt", "hwgrep"}
)

POSIX_PORT_GLOBS: dict[str, tuple[str, ...]] = {
    "linux": (
        "/dev/ttyUSB*",
        "/dev/ttyACM*",
        "/dev/ttyS[0-9]*",
        "/dev/ttyAMA*",
        "/dev/ttyXRUSB*",
        "/dev/serial/by-id/*",
    ),
    "macos": (
        "/dev/cu.*",
        "/dev/tty.*",
    ),
}

_PLACEHOLDERS: dict[str, str] = {
    "windows": "COM3 or loop://",
    "linux": "/dev/ttyUSB0 or loop://",
    "macos": "/dev/cu.usbserial or loop://",
    "other": "serial port or loop://",
}


def platform_name() -> str:
    """Return one of ``"windows"``, ``"linux"``, ``"macos"``, ``"other"``.

    ``sys.platform`` is the primary source (it is read on every call so it can
    be patched); ``os.name`` is a fallback for the coarse nt/posix distinction.
    """
    platform = (sys.platform or "").lower()
    if platform.startswith("win") or platform == "cygwin":
        return "windows"
    if platform.startswith("linux"):
        return "linux"
    if platform == "darwin":
        return "macos"
    if os.name == "nt":
        return "windows"
    return "other"


def is_posix() -> bool:
    """Whether the (possibly mocked) platform uses POSIX device paths."""
    name = platform_name()
    if name != "other":
        return name != "windows"
    return os.name == "posix"


def default_endpoint_placeholder() -> str:
    """Platform specific hint shown in the endpoint input widget."""
    return _PLACEHOLDERS[platform_name()]


def normalize_endpoint(endpoint: str) -> str:
    """Strip surrounding whitespace and prefer macOS ``/dev/cu.*`` devices.

    On POSIX, ``/dev/tty.XXX`` is rewritten to ``/dev/cu.XXX`` when the
    matching callout device exists. Everything else is returned unchanged.
    """
    text = str(endpoint or "").strip()
    if not text or platform_name() != "macos":
        return text
    if not text.startswith("/dev/tty."):
        return text
    candidate = "/dev/cu." + text[len("/dev/tty.") :]
    return candidate if _path_exists(candidate) else text


def _path_exists(path: str) -> bool:
    """Filesystem check independent of pathlib's runtime platform binding.

    ``pathlib.Path`` chooses PosixPath/WindowsPath from ``os.name`` at call
    time; using ``os.path`` keeps endpoint handling safe when embedders (and
    tests) patch ``os.name``/``sys.platform``. Kept as a module level helper so
    it can be injected in unit tests.
    """
    try:
        return os.path.exists(path)
    except OSError:
        return False


def _is_device_path(endpoint: str) -> bool:
    return endpoint.startswith("/") and "://" not in endpoint


def _non_dev_path_allowed(path: str) -> bool:
    """Allow absolute paths outside /dev when they look like virtual pairs.

    A non-existing path is accepted (a virtual pair may be created later); an
    existing path is accepted when it is a char device, symlink or directory.
    This keeps ``/tmp/serial-pair-xxx/ttyA`` usable without opening anything.
    """
    try:
        info = os.lstat(path)
    except OSError:
        return True
    mode = info.st_mode
    return bool(stat.S_ISCHR(mode) or stat.S_ISLNK(mode) or stat.S_ISDIR(mode))


def validate_endpoint(endpoint: str) -> str:
    """Return the normalized endpoint or raise ``ValueError`` (English text).

    Rules: non-empty, no whitespace; ``scheme://`` URLs must use a whitelisted
    scheme (``loop://`` is the only URL allowed to have an empty target);
    Windows accepts ``COM1``..``COM256`` (case insensitive), ordinary device
    names and POSIX-looking paths; POSIX requires an absolute path without
    ``..`` segments and rejects bare names such as ``ttyUSB0``.
    """
    text = normalize_endpoint(endpoint)
    if not text:
        raise ValueError("Endpoint must not be empty")
    if any(char.isspace() for char in text):
        raise ValueError("Endpoint must not contain whitespace")
    if "\x00" in text:
        raise ValueError("Endpoint must not contain NUL bytes")

    if "://" in text:
        scheme, _, target = text.partition("://")
        lowered = scheme.lower()
        if not scheme or lowered not in URL_SCHEMES:
            raise ValueError(
                f"Unsupported URL scheme {scheme!r}; expected one of "
                f"{sorted(URL_SCHEMES)}"
            )
        if not target and lowered != "loop":
            raise ValueError(
                f"URL endpoint must include a target after '{scheme}://'"
            )
        # pyserial matches URL schemes case sensitively.
        return f"{lowered}://{target}"

    com_match = re.fullmatch(r"COM(\d+)", text, re.IGNORECASE)
    if com_match:
        number = int(com_match.group(1))
        if not 1 <= number <= 256:
            raise ValueError("COM port number must be between 1 and 256")
        return text

    if text.startswith("/"):
        if ".." in text.split("/"):
            raise ValueError("Endpoint path must not contain '..' segments")
        if platform_name() == "windows":
            # pyserial device names / URLs can look like POSIX paths on Windows.
            return text
        if text.startswith("/dev/"):
            return text
        if not _non_dev_path_allowed(text):
            raise ValueError(f"Endpoint must be an absolute /dev/... path: {text!r}")
        return text

    if is_posix():
        raise ValueError(
            f"Endpoint {text!r} is not a URL or an absolute path; "
            "use a full /dev/... path"
        )
    return text


@dataclass(frozen=True)
class PortInfo:
    device: str
    description: str = ""
    hardware_id: str = ""

    @property
    def label(self) -> str:
        if self.description:
            return f"{self.device} — {self.description}"
        return self.device


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _is_console_terminal(device: str) -> bool:
    """Exclude unnumbered console terminals such as ``/dev/tty``."""
    return device.rstrip("/") in (
        "/dev/tty",
        "/dev/console",
        "/dev/pts",
        "/dev/serial",
        "/dev/serial/by-id",
    )


def _posix_rank(device: str) -> tuple[int, str]:
    lowered = device.lower()
    if "://" in device:
        return (90, lowered)
    if lowered.startswith("/dev/cu."):
        return (0, lowered)
    if "ttyusb" in lowered:
        return (1, lowered)
    if "ttyacm" in lowered:
        return (2, lowered)
    if "ttyama" in lowered:
        return (3, lowered)
    if any(
        marker in lowered
        for marker in (
            "usb", "serial", "xrusb", "by-id", "ftdi",
            "ch34", "cp210", "pl2303", "modem",
        )
    ):
        return (4, lowered)
    if "ttys" in lowered:
        return (5, lowered)
    return (6, lowered)


def _windows_rank(device: str) -> tuple[int, int, str]:
    lowered = device.lower()
    match = re.fullmatch(r"COM(\d+)", device, re.IGNORECASE)
    if match:
        return (0, int(match.group(1)), lowered)
    if "://" in device:
        return (2, 0, lowered)
    return (1, 0, lowered)


def _sorted_ports(items: list[PortInfo], name: str) -> list[PortInfo]:
    if name == "windows":
        return sorted(items, key=lambda port: _windows_rank(port.device))
    return sorted(items, key=lambda port: _posix_rank(port.device))


def list_serial_ports(
    comports: Callable[[], Iterable[Any]] | None = None,
) -> list[PortInfo]:
    """List serial ports without opening them.

    Uses ``serial.tools.list_ports.comports()`` by default (``comports`` may be
    injected by tests). On POSIX, extra devices are discovered via glob, results
    are de-duplicated by device string and priority-sorted. Any failure returns
    whatever has been collected so far (possibly an empty list).
    """
    provider: Callable[[], Iterable[Any]] = (
        comports if comports is not None else list_ports.comports
    )
    collected: dict[str, PortInfo] = {}

    def add(device: Any, description: str = "", hardware_id: str = "") -> None:
        if device is None:
            return
        dev = str(device).strip()
        if not dev or dev in collected or _is_console_terminal(dev):
            return
        collected[dev] = PortInfo(
            device=dev,
            description=_text(description),
            hardware_id=_text(hardware_id),
        )

    try:
        for port in provider():
            if isinstance(port, str):
                add(port)
                continue
            add(
                getattr(port, "device", None),
                _text(getattr(port, "description", "")),
                _text(getattr(port, "hwid", "")),
            )
    except Exception:
        pass

    name = platform_name()
    patterns = POSIX_PORT_GLOBS.get(name) if is_posix() else None
    if patterns:
        for pattern in patterns:
            try:
                matches = glob.glob(pattern)
                for path in sorted(matches):
                    if _is_console_terminal(path):
                        continue
                    add(path)
            except Exception:
                continue

    try:
        return _sorted_ports(list(collected.values()), name)
    except Exception:
        return list(collected.values())


def _platform_advice(name: str, chinese: bool) -> str:
    if chinese:
        if name == "linux":
            return (
                "Linux 串口排障建议：\n"
                "• 确认当前用户属于 dialout（部分发行版为 uucp）用户组："
                "sudo usermod -aG dialout $USER，然后注销并重新登录；\n"
                "• 检查 udev 规则与 /dev 设备权限（ls -l /dev/ttyUSB*）；\n"
                "• 确认设备没有被其它程序占用（lsof /dev/ttyUSB0）；\n"
                "• 重新拔插 USB 设备，并用 dmesg 检查驱动是否加载。"
            )
        if name == "macos":
            return (
                "macOS 串口排障建议：\n"
                "• 优先使用 /dev/cu.* 端点，而不是 /dev/tty.*（后者可能被系统占用）；\n"
                "• 安装对应的 USB 转串口驱动：CH340 / CP210x / FTDI；\n"
                "• 在“系统设置 → 隐私与安全性”中允许驱动与串口访问；\n"
                "• 重新拔插设备并确认端点路径仍然存在。"
            )
        if name == "windows":
            return (
                "Windows 串口排障建议：\n"
                "• 打开设备管理器，检查“端口 (COM 和 LPT)”下的驱动是否正常；\n"
                "• 确认 COM 端口没有被其它串口工具占用；\n"
                "• 重新拔插 USB 转串口线，必要时重装驱动或以管理员身份运行。"
            )
        return "通用串口排障建议：确认端点路径正确、驱动已安装、端口未被占用，并重新插拔设备。"

    if name == "linux":
        return (
            "Linux serial port checklist:\n"
            "• Add your user to the dialout group (uucp on some distributions): "
            "sudo usermod -aG dialout $USER, then log out and log back in;\n"
            "• Check udev rules and /dev permissions (ls -l /dev/ttyUSB*);\n"
            "• Make sure the device is not already in use by another program "
            "(lsof /dev/ttyUSB0);\n"
            "• Unplug and replug the USB device, then check dmesg for driver messages."
        )
    if name == "macos":
        return (
            "macOS serial port checklist:\n"
            "• Prefer /dev/cu.* endpoints over /dev/tty.* (callout devices are "
            "not claimed by the system);\n"
            "• Install the correct USB-to-serial driver (CH340 / CP210x / FTDI);\n"
            "• Allow the driver in System Settings -> Privacy & Security;\n"
            "• Unplug and replug the device and confirm the endpoint path still exists."
        )
    if name == "windows":
        return (
            "Windows serial port checklist:\n"
            "• Open Device Manager and verify the driver under 'Ports (COM & LPT)';\n"
            "• Make sure the COM port is not in use by another program;\n"
            "• Unplug and replug the USB adapter, reinstall the driver, or run "
            "the app as administrator."
        )
    return (
        "General serial port checklist: verify the endpoint path, install the "
        "driver, make sure the port is not in use, then replug the device."
    )


def permission_hint(
    endpoint: str,
    error: BaseException | None = None,
    language: str = "zh",
) -> str:
    """Return a user facing troubleshooting hint.

    ``language == "zh"`` produces Simplified Chinese; anything else produces
    English. The hint is always non-empty so it can be appended to any error.
    """
    chinese = language.lower() == "zh"
    name = platform_name()
    detail = str(error) if error is not None else ""
    type_name = type(error).__name__ if error is not None else ""
    combined = f"{type_name} {detail}".lower()

    permission_issue = isinstance(error, PermissionError) or any(
        marker in combined
        for marker in (
            "permission", "access is denied", "access denied",
            "eacces", "errno 13",
        )
    )
    missing_issue = isinstance(error, FileNotFoundError) or any(
        marker in combined
        for marker in (
            "no such file", "enoent", "errno 2",
            "filenotfound", "not found",
        )
    )

    if error is None and _is_device_path(endpoint):
        if not _path_exists(endpoint):
            missing_issue = True
        else:
            try:
                if not os.access(endpoint, os.R_OK | os.W_OK):
                    permission_issue = True
            except OSError:
                pass

    parts: list[str] = [_platform_advice(name, chinese)]
    if permission_issue:
        parts.append(
            "检测到权限不足：请修正设备权限或用户组后重试，不建议长期以 root 运行 GUI。"
            if chinese
            else "A permission-related error was detected: fix device permissions "
            "or group membership and retry."
        )
    if missing_issue:
        parts.append(
            "设备未连接或已被拔出：请重新插拔 USB，并确认端点路径仍然有效。"
            if chinese
            else "The device is not connected or was unplugged: replug it and "
            "confirm the endpoint path is still valid."
        )
    return "\n".join(part for part in parts if part)


def _is_hardware_failure(error: BaseException) -> bool:
    """Whether an open failure is device related (vs. a bad parameter)."""
    if isinstance(error, OSError):
        return True
    combined = f"{type(error).__name__} {error}".lower()
    return any(
        marker in combined
        for marker in (
            "permission", "access is denied", "access denied",
            "no such file", "device", "in use", "serial",
        )
    )


def explain_open_error(
    endpoint: str,
    error: BaseException,
    language: str = "zh",
) -> str:
    """Turn a pyserial open failure into readable text.

    URL endpoints and pure parameter errors (for example an invalid baudrate)
    get the original message only; the platform specific checklist is appended
    for device/permission failures to avoid misleading troubleshooting noise.
    """
    original = str(error)
    if "://" in endpoint or not _is_hardware_failure(error):
        return original
    hint = permission_hint(endpoint, error, language)
    if hint:
        return f"{original}\n\n{hint}"
    return original
