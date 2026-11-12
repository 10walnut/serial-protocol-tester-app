"""POSIX (Linux/macOS) virtual serial port pair backed by two linked PTYs.

No external program (socat / com0com) and no third-party package is needed.
A daemon relay thread copies bytes between the two PTY masters, so the two
slave device paths behave like a null-modem cable and can be opened directly
with ``serial.serial_for_url(path)``.
"""

from __future__ import annotations

import errno
import os
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# termios / pty / tty do not exist on Windows: never import them there,
# otherwise importing this module would crash on Windows.
pty: Any = None
select: Any = None
termios: Any = None
tty: Any = None

if os.name == "posix":
    try:
        import pty as _pty
        import select as _select
        import termios as _termios
        import tty as _tty
    except (ImportError, OSError):  # pragma: no cover - unusual POSIX builds
        pass
    else:
        pty, select, termios, tty = _pty, _select, _termios, _tty

__all__ = [
    "PosixVirtualPortError",
    "VirtualPortPair",
    "backend_description",
    "create_pair",
    "is_supported",
]

_BACKEND_DESCRIPTION = "POSIX pseudo-terminal pair (pty)"
_RELAY_TIMEOUT = 0.15
_RELAY_JOIN_TIMEOUT = 2.0
_READ_SIZE = 4096


class PosixVirtualPortError(RuntimeError):
    """Raised when a POSIX PTY pair cannot be created or is unavailable."""


def is_supported() -> bool:
    """Return True only when POSIX PTY support is usable on this host."""
    if os.name != "posix":
        return False
    return all(module is not None for module in (pty, select, termios, tty))


def backend_description() -> str:
    """Return a short English description of the backend."""
    return _BACKEND_DESCRIPTION


def _make_raw(fd: int) -> None:
    """Disable the line discipline so binary protocol bytes are untouched.

    ``tty.setraw`` clears ECHO/ICANON/ISIG/IEXTEN, OPOST (hence ONLCR) and
    IXON/ICRNL.  Its ``when`` parameter only exists on Python 3.12+, so it is
    called with a single argument for Python 3.10 compatibility; a manual
    termios fallback is used if that call is unsupported.
    """
    if tty is not None:
        try:
            tty.setraw(fd)
            return
        except Exception:  # noqa: BLE001 - best-effort terminal configuration
            pass
    if termios is None:
        return

    def bits(*names: str) -> int:
        value = 0
        for name in names:
            value |= int(getattr(termios, name, 0) or 0)
        return value

    try:
        attrs = termios.tcgetattr(fd)
        iflag, oflag, cflag, lflag, ispeed, ospeed, cc = attrs
        iflag &= ~bits(
            "IGNBRK", "BRKINT", "PARMRK", "ISTRIP", "INLCR", "IGNCR",
            "ICRNL", "IXON", "IXOFF", "IXANY", "IMAXBEL",
        )
        oflag &= ~bits("OPOST", "ONLCR", "OCRNL", "ONLRET")
        lflag &= ~bits("ECHO", "ECHOE", "ECHOK", "ECHONL", "ICANON", "ISIG", "IEXTEN")
        cflag &= ~bits("CSIZE", "PARENB")
        cflag |= bits("CS8", "CREAD")
        try:
            cc[termios.VMIN] = 1
            cc[termios.VTIME] = 0
        except Exception:  # noqa: BLE001 - cc may be immutable on some platforms
            pass
        termios.tcsetattr(
            fd, termios.TCSANOW, [iflag, oflag, cflag, lflag, ispeed, ospeed, cc]
        )
    except Exception:  # noqa: BLE001 - raw mode is best effort
        pass


def _write_all(
    fd: int,
    payload: bytes,
    stop: threading.Event,
    timeout: float = 1.0,
) -> bool:
    """Write every byte, tolerating partial writes and transient errors.

    A peer that never reads must not block the relay forever (head-of-line
    blocking): give up after ``timeout`` seconds so the loop can service the
    other direction and react to ``close()``. Returns True on a complete write.
    """
    deadline = time.monotonic() + timeout
    view = memoryview(payload)
    while view and not stop.is_set():
        try:
            written = os.write(fd, view)
        except BlockingIOError:
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.005)
            continue
        except InterruptedError:
            continue
        except OSError as exc:
            if exc.errno == errno.EIO and time.monotonic() < deadline:
                time.sleep(0.01)
                continue
            return False  # EBADF / EPIPE: peer is gone
        if written <= 0:
            return False
        view = view[written:]
    return not view and not stop.is_set()


def _relay_loop(
    master_a: int,
    master_b: int,
    wake_fd: int,
    stop: threading.Event,
) -> None:
    """Copy bytes between two PTY masters until ``stop`` is set.

    ``wake_fd`` is the read end of a self-pipe: ``close()`` writes to it so
    ``select`` returns immediately instead of waiting for its poll timeout.
    """
    peers = {master_a: master_b, master_b: master_a}
    fds = [master_a, master_b, wake_fd]
    empty_reads = 0
    while not stop.is_set():
        try:
            readable, _, _ = select.select(fds, [], [], _RELAY_TIMEOUT)
        except (OSError, ValueError):
            # FDs were closed by close(), or select got a bad fd. Retrying here
            # would spin forever, so exit; close() is the only normal path.
            return
        for source in readable:
            if source == wake_fd:
                return
            if stop.is_set():
                return
            try:
                payload = os.read(source, _READ_SIZE)
            except (BlockingIOError, InterruptedError):
                continue
            except OSError as exc:
                if exc.errno == errno.EIO:
                    # Linux masters report EIO while the slave is not open yet.
                    time.sleep(0.01)
                    continue
                return
            if not payload:
                # EOF: back off instead of spinning on a permanently readable
                # fd, and exit if the hangup persists (~1 second).
                empty_reads += 1
                if empty_reads >= 20:
                    return
                time.sleep(0.05)
                continue
            empty_reads = 0
            _write_all(peers[source], payload, stop)


@dataclass
class VirtualPortPair:
    """A pair of interconnected PTY endpoints usable as serial ports."""

    port_a: str
    port_b: str
    _master_a: int = field(default=-1, repr=False)
    _master_b: int = field(default=-1, repr=False)
    _slave_a: int = field(default=-1, repr=False)
    _slave_b: int = field(default=-1, repr=False)
    _stop_event: threading.Event = field(default_factory=threading.Event, repr=False)
    _relay: threading.Thread | None = field(default=None, repr=False)
    _links: tuple[Path, ...] = field(default_factory=tuple, repr=False)
    _temp_dir: Path | None = field(default=None, repr=False)
    _created_dir: Path | None = field(default=None, repr=False)
    _wake_r: int = field(default=-1, repr=False)
    _wake_w: int = field(default=-1, repr=False)
    _closed: bool = field(default=False, repr=False)

    @property
    def active(self) -> bool:
        return not self._closed

    def endpoints(self) -> tuple[str, str]:
        return (self.port_a, self.port_b)

    def close(self) -> None:
        """Stop the relay, close all fds and remove only our own artifacts."""
        if self._closed:
            return
        self._closed = True  # idempotent even if a later step fails
        self._stop_event.set()
        if self._wake_w >= 0:
            try:
                os.write(self._wake_w, b"\x00")
            except OSError:
                pass

        relay = self._relay
        if relay is not None and relay.is_alive():
            try:
                relay.join(timeout=_RELAY_JOIN_TIMEOUT)
            except RuntimeError:
                pass
        self._relay = None

        for name in (
            "_master_a", "_master_b", "_slave_a", "_slave_b", "_wake_r", "_wake_w",
        ):
            fd = getattr(self, name)
            if fd >= 0:
                try:
                    os.close(fd)
                except OSError:
                    pass
                setattr(self, name, -1)

        for link in self._links:
            try:
                link.unlink()
            except OSError:
                pass
        self._links = ()

        if self._temp_dir is not None:
            shutil.rmtree(self._temp_dir, ignore_errors=True)
            self._temp_dir = None
        if self._created_dir is not None:
            try:
                self._created_dir.rmdir()  # only succeeds when empty; never rmtree
            except OSError:
                pass
            self._created_dir = None

    def __enter__(self) -> VirtualPortPair:
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()

    def __del__(self) -> None:
        # Last-resort cleanup; daemon=True already prevents interpreter hang.
        try:
            self.close()
        except BaseException:  # noqa: BLE001 - interpreter shutdown
            pass


def create_pair(directory: str | Path | None = None) -> VirtualPortPair:
    """Create two PTYs wired together through a daemon relay thread.

    ``directory=None`` uses ``tempfile.mkdtemp(prefix="serial-pair-")``.
    A user supplied directory is created if missing, but only the symlinks we
    created are removed on close; the directory itself is removed with
    ``rmdir()`` only when we created it and it is still empty.
    """
    if not is_supported():
        raise PosixVirtualPortError(
            "Virtual PTY port pairs are supported on Linux/macOS (POSIX) only"
        )

    temp_dir: Path | None = None
    created_dir: Path | None = None
    if directory is None:
        try:
            temp_dir = Path(tempfile.mkdtemp(prefix="serial-pair-"))
        except OSError as exc:
            raise PosixVirtualPortError(
                f"Could not create a temporary directory: {exc}"
            ) from exc
        base = temp_dir
    else:
        base = Path(directory).expanduser()
        if not base.is_dir():
            try:
                base.mkdir(parents=True, exist_ok=True)
                created_dir = base
            except OSError as exc:
                raise PosixVirtualPortError(
                    f"Could not create directory {base}: {exc}"
                ) from exc

    master_a = master_b = slave_a = slave_b = -1
    wake_r = wake_w = -1
    links: list[Path] = []
    pair: VirtualPortPair | None = None
    try:
        try:
            master_a, slave_a = pty.openpty()
            master_b, slave_b = pty.openpty()
        except OSError as exc:
            raise PosixVirtualPortError(
                f"Could not open a pseudo-terminal: {exc}"
            ) from exc

        try:
            os.set_blocking(master_a, False)
            os.set_blocking(master_b, False)
        except (OSError, AttributeError) as exc:
            raise PosixVirtualPortError(
                f"Could not configure non-blocking PTY masters: {exc}"
            ) from exc

        _make_raw(slave_a)
        _make_raw(slave_b)
        try:
            device_a = os.ttyname(slave_a)
            device_b = os.ttyname(slave_b)
        except OSError as exc:
            raise PosixVirtualPortError(
                f"Could not resolve the PTY device path: {exc}"
            ) from exc

        # Prefer stable, short symlinks; fall back to the raw /dev/pts/N paths
        # when symlinks are unavailable (close() then skips link cleanup).
        port_a, port_b = device_a, device_b
        try:
            link_a = base / "ttyA"
            link_b = base / "ttyB"
            for link, device in ((link_a, device_a), (link_b, device_b)):
                if link.exists() or link.is_symlink():
                    raise OSError(errno.EEXIST, "link already exists", str(link))
                os.symlink(device, link)
                links.append(link)
            port_a, port_b = str(link_a), str(link_b)
        except (OSError, NotImplementedError, AttributeError):
            for link in links:
                try:
                    link.unlink()
                except OSError:
                    pass
            links = []
            port_a, port_b = device_a, device_b

        try:
            wake_r, wake_w = os.pipe()
            os.set_blocking(wake_r, False)
            os.set_blocking(wake_w, False)
        except (OSError, AttributeError) as exc:
            raise PosixVirtualPortError(
                f"Could not create the relay wake pipe: {exc}"
            ) from exc

        stop = threading.Event()
        relay = threading.Thread(
            target=_relay_loop,
            args=(master_a, master_b, wake_r, stop),
            name="serial-pty-relay",
            daemon=True,
        )
        pair = VirtualPortPair(
            port_a=port_a,
            port_b=port_b,
            _master_a=master_a,
            _master_b=master_b,
            _slave_a=slave_a,
            _slave_b=slave_b,
            _stop_event=stop,
            _relay=relay,
            _links=tuple(links),
            _temp_dir=temp_dir,
            _created_dir=created_dir,
            _wake_r=wake_r,
            _wake_w=wake_w,
        )
        try:
            relay.start()
        except RuntimeError as exc:
            pair.close()
            raise PosixVirtualPortError(
                f"Could not start the PTY relay thread: {exc}"
            ) from exc
        return pair
    except Exception:
        if pair is None:  # pair.close() already cleaned up in the start failure
            for fd in (master_a, master_b, slave_a, slave_b, wake_r, wake_w):
                if fd >= 0:
                    try:
                        os.close(fd)
                    except OSError:
                        pass
            for link in links:
                try:
                    link.unlink()
                except OSError:
                    pass
            if temp_dir is not None:
                shutil.rmtree(temp_dir, ignore_errors=True)
            elif created_dir is not None:
                try:
                    created_dir.rmdir()
                except OSError:
                    pass
        raise
