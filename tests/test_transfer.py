import asyncio
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
from typing import Any

from parallels_mcp.guest import GuestExecResult, GuestService
from parallels_mcp.prl import BinaryCommandResult, CommandResult
from parallels_mcp.transfer import FileTransferService
from parallels_mcp.vm import VmService


class FakeJsonRunner:
    async def __call__(self, *args: str, timeout: float):
        if args == ("list", "-a", "-j"):
            return [
                {"uuid": "11111111-1111-1111-1111-111111111111", "name": "Windows 11", "status": "running"},
                {"uuid": "22222222-2222-2222-2222-222222222222", "name": "Ubuntu", "status": "running"},
            ]
        if args == ("list", "-i", "-j", "11111111-1111-1111-1111-111111111111"):
            return [{
                "uuid": "11111111-1111-1111-1111-111111111111",
                "name": "Windows 11",
                "status": "running",
                "os": "win-11",
            }]
        if args == ("list", "-i", "-j", "22222222-2222-2222-2222-222222222222"):
            return [{
                "uuid": "22222222-2222-2222-2222-222222222222",
                "name": "Ubuntu",
                "status": "running",
                "os": "ubuntu-22.04",
            }]
        raise AssertionError(args)


class FakeBinaryRunner:
    def __init__(self, stdout_bytes: bytes = b"") -> None:
        self.calls: list[tuple[tuple[str, ...], Any]] = []
        self.stdout_bytes = stdout_bytes

    async def __call__(self, *args: str, timeout: float, stdin: Any = None) -> BinaryCommandResult:
        self.calls.append((args, stdin))
        return BinaryCommandResult(
            args=("prlctl", *args),
            returncode=0,
            stdout_bytes=self.stdout_bytes,
            stderr_bytes=b"",
        )


class FakeGuestRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    async def __call__(self, *args: str, timeout: float, stdin: Any = None) -> CommandResult:
        self.calls.append(args)
        return CommandResult(args=("prlctl", *args), returncode=0, stdout="", stderr="")


class FileTransferServiceTests(unittest.TestCase):
    def test_copy_to_guest_single_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "sample.txt"
            file_path.write_text("hello transfer")

            vms = VmService(FakeJsonRunner())
            guest = GuestService(vms, FakeGuestRunner())
            bin_runner = FakeBinaryRunner()
            service = FileTransferService(vms, guest, bin_runner)

            result = asyncio.run(service.copy_to_guest("Windows 11", file_path, r"C:\Temp\sample.txt"))
            self.assertEqual(result.bytes, len("hello transfer"))
            self.assertEqual(result.source, str(file_path.resolve()))
            self.assertEqual(result.destination, r"C:\Temp\sample.txt")

            # Check that tar extraction was invoked with tar.exe on Windows
            args, stdin = bin_runner.calls[0]
            self.assertIn("tar.exe", args)
            self.assertIn("-xf", args)
            # Check tar payload
            with tarfile.open(fileobj=io.BytesIO(stdin), mode="r") as t:
                self.assertIn("sample.txt", t.getnames())
                self.assertEqual(t.extractfile("sample.txt").read(), b"hello transfer")

    def test_copy_from_guest_single_file(self) -> None:
        # Build simulated tar output from guest
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as t:
            data = b"remote content"
            ti = tarfile.TarInfo(name="remote.txt")
            ti.size = len(data)
            t.addfile(ti, io.BytesIO(data))

        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "retrieved.txt"
            vms = VmService(FakeJsonRunner())
            guest = GuestService(vms, FakeGuestRunner())
            bin_runner = FakeBinaryRunner(stdout_bytes=buf.getvalue())
            service = FileTransferService(vms, guest, bin_runner)

            result = asyncio.run(service.copy_from_guest("Windows 11", r"C:\Temp\remote.txt", out_file))
            self.assertEqual(result.bytes, len("remote content"))
            self.assertTrue(out_file.is_file())
            self.assertEqual(out_file.read_text(), "remote content")

    def test_copy_to_guest_nonexistent_source_raises(self) -> None:
        vms = VmService(FakeJsonRunner())
        guest = GuestService(vms, FakeGuestRunner())
        service = FileTransferService(vms, guest, FakeBinaryRunner())

        with self.assertRaises(FileNotFoundError):
            asyncio.run(service.copy_to_guest("Windows 11", "/nonexistent/host/file.txt", r"C:\Temp\file.txt"))

    def test_copy_to_guest_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            dir_path = Path(tmpdir) / "mydir"
            dir_path.mkdir()
            (dir_path / "subfile.txt").write_text("nested data")

            vms = VmService(FakeJsonRunner())
            guest = GuestService(vms, FakeGuestRunner())
            bin_runner = FakeBinaryRunner()
            service = FileTransferService(vms, guest, bin_runner)

            result = asyncio.run(service.copy_to_guest("Windows 11", dir_path, r"C:\Temp\dest"))
            self.assertEqual(result.bytes, len("nested data"))
            args, stdin = bin_runner.calls[0]
            self.assertIn("-C", args)
            self.assertIn(r"C:\Temp\dest", args)

    def test_copy_to_and_from_guest_linux(self) -> None:
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as t:
            data = b"linux data"
            ti = tarfile.TarInfo(name="data.txt")
            ti.size = len(data)
            t.addfile(ti, io.BytesIO(data))

        with tempfile.TemporaryDirectory() as tmpdir:
            host_file = Path(tmpdir) / "local.txt"
            host_file.write_text("linux host data")

            vms = VmService(FakeJsonRunner())
            guest = GuestService(vms, FakeGuestRunner())
            bin_runner = FakeBinaryRunner(stdout_bytes=buf.getvalue())
            service = FileTransferService(vms, guest, bin_runner)

            # Copy to linux
            res_to = asyncio.run(service.copy_to_guest("Ubuntu", host_file, "/tmp/local.txt"))
            self.assertEqual(res_to.bytes, len("linux host data"))
            args_to, _ = bin_runner.calls[0]
            self.assertIn("tar", args_to)
            self.assertNotIn("tar.exe", args_to)

            # Copy from linux
            dest_file = Path(tmpdir) / "from_linux.txt"
            res_from = asyncio.run(service.copy_from_guest("Ubuntu", "/tmp/data.txt", dest_file))
            self.assertEqual(res_from.bytes, len("linux data"))
            self.assertEqual(dest_file.read_text(), "linux data")

