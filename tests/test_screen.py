import asyncio
import tempfile
import unittest
from pathlib import Path

from parallels_mcp.prl import CommandResult
from parallels_mcp.screen import ScreenCapture
from parallels_mcp.vm import VmService


class FakeJsonRunner:
    async def __call__(self, *args: str, timeout: float):
        if args == ("list", "-a", "-j"):
            return [{"uuid": "11111111-1111-1111-1111-111111111111", "name": "Windows 11", "status": "running"}]
        raise AssertionError(args)


class FakeRunner:
    def __init__(self, target_file: Path) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.target_file = target_file

    async def __call__(self, *args: str, timeout: float) -> CommandResult:
        self.calls.append(args)
        # Simulate creating the capture file
        self.target_file.write_bytes(b"\x89PNG\r\n\x1a\n")
        return CommandResult(args=("prlctl", *args), returncode=0, stdout="", stderr="")


class ScreenCaptureTests(unittest.TestCase):
    def test_capture_resolves_vm_and_captures_screen(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "screen.png"
            fake_runner = FakeRunner(dest)
            vms = VmService(FakeJsonRunner())
            screen = ScreenCapture(vms, fake_runner)

            result = asyncio.run(screen.capture("Windows 11", dest))
            self.assertEqual(result.vm, "Windows 11")
            self.assertEqual(result.uuid, "11111111-1111-1111-1111-111111111111")
            self.assertEqual(result.path, str(dest.resolve()))
            self.assertGreater(result.bytes, 0)
            self.assertEqual(
                fake_runner.calls[0],
                ("capture", "11111111-1111-1111-1111-111111111111", "--file", str(dest.resolve())),
            )
