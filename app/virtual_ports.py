from __future__ import annotations

import ctypes
import locale
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


COM0COM_DOWNLOAD_URL = "https://sourceforge.net/projects/com0com/"
COMMON_SETUPC_PATHS = (
    Path(r"C:\Program Files\com0com\setupc.exe"),
    Path(r"C:\Program Files (x86)\com0com\setupc.exe"),
)


class VirtualPortError(RuntimeError):
    pass


@dataclass(frozen=True)
class DriverProblem:
    instance_id: str
    code: int | None
    symbol: str
    description: str


def normalize_com_name(value: str | int) -> str:
    text = f"COM{value}" if isinstance(value, int) else str(value).strip().upper()
    match = re.fullmatch(r"COM([1-9]\d{0,2})", text)
    if not match:
        raise VirtualPortError("COM port must be COM1 through COM256")
    number = int(match.group(1))
    if number > 256:
        raise VirtualPortError("COM port must be COM1 through COM256")
    return f"COM{number}"


def build_install_arguments(port_a: str | int, port_b: str | int) -> list[str]:
    first = normalize_com_name(port_a)
    second = normalize_com_name(port_b)
    if first == second:
        raise VirtualPortError("The two virtual ports must use different COM numbers")
    return [
        "install",
        f"PortName={first}",
        f"PortName={second}",
    ]


def parse_com0com_pnp_problems(output: str) -> list[DriverProblem]:
    problems: list[DriverProblem] = []
    for block in re.split(r"(?:\r?\n\s*){2,}", output):
        if "com0com" not in block.lower() and "root\\com0com" not in block.lower():
            continue
        instance_match = re.search(r"ROOT\\COM0COM\\[^\s]+", block, re.IGNORECASE)
        symbol_match = re.search(r"\[(CM_PROB_[A-Z_]+)\]", block)
        code_match = re.search(r"(\d+)\s*\(0x[0-9A-Fa-f]+\)\s*\[CM_PROB_", block)
        description_match = re.search(
            r"(?:Device Description|设备描述)\s*:\s*([^\r\n]+)",
            block,
            re.IGNORECASE,
        )
        problems.append(
            DriverProblem(
                instance_id=instance_match.group(0).upper() if instance_match else "com0com",
                code=int(code_match.group(1)) if code_match else None,
                symbol=symbol_match.group(1) if symbol_match else "",
                description=description_match.group(1).strip() if description_match else "com0com device",
            )
        )
    return problems


def query_com0com_driver_problems() -> list[DriverProblem]:
    if os.name != "nt":
        return []
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(
            ["pnputil", "/enum-devices", "/problem", "/deviceids"],
            capture_output=True,
            text=True,
            encoding=locale.getpreferredencoding(False),
            errors="replace",
            timeout=20,
            creationflags=creation_flags,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    return parse_com0com_pnp_problems(output)


def count_unassigned_ports(output: str) -> int:
    return sum(
        1
        for line in output.splitlines()
        if "PortName=COM#" in line and not re.search(r"RealPortName=COM\d+", line, re.IGNORECASE)
    )


def virtual_ports_ready(
    port_a: str | int,
    port_b: str | int,
    enumerated_ports: list[str] | tuple[str, ...] | set[str],
    setup_output: str = "",
) -> bool:
    expected = {normalize_com_name(port_a), normalize_com_name(port_b)}
    available = {str(port).strip().upper() for port in enumerated_ports}
    if expected.issubset(available):
        return True
    return all(
        re.search(rf"(?:Real)?PortName={re.escape(port)}(?=,|\s|$)", setup_output, re.IGNORECASE)
        for port in expected
    )


def find_setupc(explicit_path: str | Path | None = None) -> Path | None:
    candidates: list[Path] = []
    if explicit_path:
        candidates.append(Path(explicit_path).expanduser())
    configured = os.environ.get("COM0COM_SETUPC")
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.extend(COMMON_SETUPC_PATHS)
    discovered = shutil.which("setupc.exe") or shutil.which("setupc")
    if discovered:
        candidates.append(Path(discovered))
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


def list_virtual_pairs(setupc_path: str | Path) -> str:
    setupc = find_setupc(setupc_path)
    if setupc is None:
        raise VirtualPortError("com0com setupc.exe was not found")
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(
            [str(setupc), "list"],
            capture_output=True,
            text=True,
            encoding=locale.getpreferredencoding(False),
            errors="replace",
            timeout=15,
            creationflags=creation_flags,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise VirtualPortError(f"Could not query com0com: {exc}") from exc
    output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
    if result.returncode != 0:
        raise VirtualPortError(output or f"setupc list failed with exit code {result.returncode}")
    return output or "No virtual port pairs were reported."


def launch_elevated_install(setupc_path: str | Path, port_a: str | int, port_b: str | int) -> None:
    if os.name != "nt":
        raise VirtualPortError("Virtual COM pair creation is supported on Windows only")
    setupc = find_setupc(setupc_path)
    if setupc is None:
        raise VirtualPortError("com0com setupc.exe was not found")
    arguments = subprocess.list2cmdline(build_install_arguments(port_a, port_b))
    result = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        str(setupc),
        arguments,
        str(setupc.parent),
        1,
    )
    if result <= 32:
        raise VirtualPortError(f"Windows could not start setupc.exe with administrator rights (code {result})")
