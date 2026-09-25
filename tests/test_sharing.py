import asyncio
import tempfile
import unittest
from pathlib import Path

from parallels_mcp.prl import CommandResult
from parallels_mcp.sharing import SharingService
from parallels_mcp.vm import VmService


class FakeJsonRunner:
    async def __call__(self, *args: str, timeout: float):
        if args == ("list", "-a", "-j"):
            return [{"uuid": "11111111-1111-1111-1111-111111111111", "name": "Windows 11", "status": "running"}]
        raise AssertionError(args)


class FakeRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    async def __call__(self, *args: str, timeout: float, stdin: str | None = None) -> CommandResult:
        self.calls.append(args)
        return CommandResult(args=("prlctl", *args), returncode=0, stdout="success\n", stderr="")


class SharingServiceTests(unittest.TestCase):
    def test_share_folder_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_runner = FakeRunner()
            service = SharingService(VmService(FakeJsonRunner()), fake_runner)

            result = asyncio.run(service.share_folder("Windows 11", "dev_share", tmpdir, mode="ro"))
            self.assertEqual(result.name, "dev_share")
            self.assertEqual(result.mode, "ro")
            self.assertEqual(result.action, "share_folder")
            self.assertEqual(
                fake_runner.calls[0],
                ("set", "11111111-1111-1111-1111-111111111111", "--shf-host-add", "dev_share", "--path", str(Path(tmpdir).resolve()), "--mode", "ro"),
            )

    def test_share_folder_invalid_mode_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = SharingService(VmService(FakeJsonRunner()), FakeRunner())
            with self.assertRaises(ValueError):
                asyncio.run(service.share_folder("Windows 11", "dev_share", tmpdir, mode="invalid_mode"))

    def test_share_folder_nonexistent_path_raises(self) -> None:
        service = SharingService(VmService(FakeJsonRunner()), FakeRunner())
        with self.assertRaises(FileNotFoundError):
            asyncio.run(service.share_folder("Windows 11", "dev_share", "/nonexistent/path/123xyz"))

    def test_unshare_folder_success(self) -> None:
        fake_runner = FakeRunner()
        service = SharingService(VmService(FakeJsonRunner()), fake_runner)

        result = asyncio.run(service.unshare_folder("Windows 11", "dev_share"))
        self.assertEqual(result.name, "dev_share")
        self.assertEqual(result.action, "unshare_folder")
        self.assertEqual(
            fake_runner.calls[0],
            ("set", "11111111-1111-1111-1111-111111111111", "--shf-host-del", "dev_share"),
        )
