from __future__ import annotations

import errno
import os
import select
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = PROJECT_ROOT / "app"
sys.path.insert(0, str(APP_ROOT))

from virtual_ports_posix import (  # noqa: E402
    PosixVirtualPortError,
    VirtualPortPair,
    _relay_loop,
    _write_all,
    backend_description,
    create_pair,
    is_supported,
)


_O_NOCTTY = getattr(os, "O_NOCTTY", 0)
_WAIT_SECONDS = 3.0


class PortableVirtualPortPosixTests(unittest.TestCase):
    """Tests that run on every platform, including Windows."""

    def test_is_supported_returns_a_bool(self) -> None:
        self.assertIsInstance(is_supported(), bool)

    def test_backend_description_is_not_empty(self) -> None:
        description = backend_description()
        self.assertIsInstance(description, str)
        self.assertTrue(description.strip())

    def test_create_pair_rejects_unsupported_platforms(self) -> None:
        if is_supported():
            self.skipTest("create_pair is available on this POSIX host")
        with self.assertRaises(PosixVirtualPortError) as ctx:
            create_pair()
        self.assertIn("Linux/macOS", str(ctx.exception))


class RelayLogicTests(unittest.TestCase):
    """Relay logic without a real PTY, so Windows can validate it too."""

    def test_write_all_handles_partial_writes(self) -> None:
        sizes = iter([2, 2])
        with patch("virtual_ports_posix.os.write", side_effect=lambda fd, data: next(sizes)):
            self.assertTrue(_write_all(9, b"data", threading.Event()))

    def test_write_all_gives_up_on_permanent_eagain(self) -> None:
        with patch("virtual_ports_posix.os.write", side_effect=BlockingIOError()), patch(
            "virtual_ports_posix.time.sleep"
        ):
            self.assertFalse(
                _write_all(9, b"data", threading.Event(), timeout=0.0)
            )

    def test_write_all_respects_stop_event(self) -> None:
        stop = threading.Event()
        stop.set()
        with patch("virtual_ports_posix.os.write") as write:
            self.assertFalse(_write_all(9, b"data", stop))
        write.assert_not_called()

    def test_relay_loop_exits_on_wake_fd(self) -> None:
        fake_select = SimpleNamespace(select=lambda *args: ([99], [], []))
        with patch("virtual_ports_posix.select", fake_select), patch(
            "virtual_ports_posix.os.read"
        ) as read:
            _relay_loop(10, 11, 99, threading.Event())
        read.assert_not_called()

    def test_relay_loop_exits_on_persistent_eof(self) -> None:
        fake_select = SimpleNamespace(select=lambda *args: ([10], [], []))
        with patch("virtual_ports_posix.select", fake_select), patch(
            "virtual_ports_posix.os.read", return_value=b""
        ), patch("virtual_ports_posix.time.sleep") as sleep:
            _relay_loop(10, 11, 99, threading.Event())
        # 20th consecutive EOF returns before sleeping.
        self.assertEqual(sleep.call_count, 19, "EOF must back off and then exit")

    def test_relay_loop_exits_on_bad_fd(self) -> None:
        fake_select = SimpleNamespace(
            select=Mock(side_effect=ValueError("file descriptor cannot be negative"))
        )
        with patch("virtual_ports_posix.select", fake_select):
            _relay_loop(10, 11, 99, threading.Event())

    def test_close_wakes_relay_and_is_idempotent(self) -> None:
        pair = VirtualPortPair("a", "b", _wake_w=7)
        with patch("virtual_ports_posix.os.write") as write, patch(
            "virtual_ports_posix.os.close"
        ):
            pair.close()
            pair.close()
        write.assert_called_once_with(7, b"\x00")
        self.assertFalse(pair.active)


@unittest.skipUnless(is_supported(), "POSIX only")
class PosixVirtualPortPairTests(unittest.TestCase):
    """Real PTY tests; entirely skipped on Windows."""

    @staticmethod
    def _open(path: str) -> int:
        return os.open(path, os.O_RDWR | _O_NOCTTY)

    @staticmethod
    def _read_until(fd: int, size: int) -> bytes:
        """Accumulate up to ``size`` bytes with a bounded wall-clock timeout."""
        deadline = time.monotonic() + _WAIT_SECONDS
        data = bytearray()
        while len(data) < size:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            readable, _, _ = select.select([fd], [], [], min(remaining, 0.2))
            if not readable:
                continue
            try:
                chunk = os.read(fd, 4096)
            except BlockingIOError:
                continue
            except OSError as exc:
                if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK, errno.EIO):
                    time.sleep(0.01)
                    continue
                raise
            if chunk:
                data.extend(chunk)
        return bytes(data)

    def test_create_pair_returns_two_distinct_existing_paths(self) -> None:
        pair = create_pair()
        try:
            self.assertIsInstance(pair, VirtualPortPair)
            self.assertTrue(pair.active)
            self.assertNotEqual(pair.port_a, pair.port_b)
            self.assertTrue(os.path.exists(pair.port_a))
            self.assertTrue(os.path.exists(pair.port_b))
        finally:
            pair.close()

    def test_endpoints(self) -> None:
        pair = create_pair()
        try:
            endpoints = pair.endpoints()
            self.assertIsInstance(endpoints, tuple)
            self.assertEqual(endpoints, (pair.port_a, pair.port_b))
            self.assertEqual(len(endpoints), 2)
        finally:
            pair.close()

    def test_relay_is_bidirectional(self) -> None:
        pair = create_pair()
        fd_a = fd_b = -1
        try:
            fd_a = self._open(pair.port_a)
            fd_b = self._open(pair.port_b)
            # \x00 / \xff / \r / \n verify raw mode (no ICRNL/ONLCR rewriting).
            os.write(fd_a, b"A2B\x00\xff")
            self.assertEqual(self._read_until(fd_b, 5), b"A2B\x00\xff")
            os.write(fd_b, b"B2A\x0d\x0a")
            self.assertEqual(self._read_until(fd_a, 5), b"B2A\x0d\x0a")
        finally:
            for fd in (fd_a, fd_b):
                if fd >= 0:
                    try:
                        os.close(fd)
                    except OSError:
                        pass
            pair.close()

    def test_relay_works_through_pyserial(self) -> None:
        try:
            import serial
        except ImportError:
            self.skipTest("pyserial is not installed")
        pair = create_pair()
        port_a = port_b = None
        try:
            # This is the exact path the GUI uses (serial_for_url on a path).
            port_a = serial.serial_for_url(pair.port_a, baudrate=9600, timeout=2)
            port_b = serial.serial_for_url(pair.port_b, baudrate=9600, timeout=2)
            port_a.write(b"ping\x00\xff")
            port_a.flush()
            self.assertEqual(port_b.read(6), b"ping\x00\xff")
            port_b.write(b"pong")
            port_b.flush()
            self.assertEqual(port_a.read(4), b"pong")
        finally:
            for port in (port_a, port_b):
                if port is not None:
                    try:
                        port.close()
                    except Exception:
                        pass
            pair.close()

    def test_relay_works_across_processes(self) -> None:
        try:
            import serial  # noqa: F401
        except ImportError:
            self.skipTest("pyserial is not installed")
        pair = create_pair()
        script = (
            "import sys, serial\n"
            "port = serial.serial_for_url(sys.argv[1], baudrate=9600, timeout=5)\n"
            "sys.stdout.write('READY\\n'); sys.stdout.flush()\n"
            "data = port.read(4)\n"
            "port.write(data); port.flush(); port.close()\n"
            "sys.stdout.write(data.decode('latin1') + '\\n'); sys.stdout.flush()\n"
        )
        proc = subprocess.Popen(
            [sys.executable, "-c", script, pair.port_b],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        fd_a = -1
        try:
            stream = proc.stdout
            if stream is None:
                self.fail("subprocess stdout is unavailable")
            self.assertEqual(stream.readline().strip(), "READY")
            fd_a = self._open(pair.port_a)
            os.write(fd_a, b"ping")
            self.assertEqual(self._read_until(fd_a, 4), b"ping")
            stdout, stderr = proc.communicate(timeout=10)
            self.assertEqual(proc.returncode, 0, stderr)
            self.assertIn("ping", stdout)
        finally:
            if fd_a >= 0:
                try:
                    os.close(fd_a)
                except OSError:
                    pass
            if proc.poll() is None:
                proc.kill()
                proc.communicate()
            pair.close()

    def test_close_is_idempotent_and_cleans_links_and_temp_dir(self) -> None:
        pair = create_pair()
        link_a = Path(pair.port_a)
        link_b = Path(pair.port_b)
        parent = link_a.parent
        symlinked = link_a.is_symlink()
        self.assertTrue(link_a.exists())
        self.assertTrue(link_b.exists())

        pair.close()
        pair.close()
        pair.close()
        self.assertFalse(pair.active)

        if symlinked:
            self.assertFalse(link_a.exists())
            self.assertFalse(link_b.exists())
            self.assertTrue(parent.name.startswith("serial-pair-"))
            self.assertFalse(parent.exists())

    def test_context_manager_deactivates_on_exit(self) -> None:
        with create_pair() as pair:
            self.assertTrue(pair.active)
            self.assertEqual(pair.endpoints(), (pair.port_a, pair.port_b))
        self.assertFalse(pair.active)

    def test_user_directory_is_preserved(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="vpt-user-dir-"))
        sentinel = root / "keep.txt"
        sentinel.write_text("keep", encoding="utf-8")
        try:
            pair = create_pair(directory=root)
            link_a = Path(pair.port_a)
            link_b = Path(pair.port_b)
            self.assertTrue(link_a.exists())
            pair.close()
            if link_a.is_symlink() or link_b.is_symlink():
                self.assertFalse(link_a.exists())
                self.assertFalse(link_b.exists())
            self.assertTrue(root.exists())
            self.assertTrue(sentinel.exists())
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
