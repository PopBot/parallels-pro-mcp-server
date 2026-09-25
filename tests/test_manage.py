import asyncio
from pathlib import Path
import unittest

from parallels_mcp.manage import VmManagementService
from parallels_mcp.prl import CommandResult, PrlCommandError
from parallels_mcp.vm import VmService


class FakeJsonRunner:
    def __init__(self, running: bool = False) -> None:
        self.running = running

    async def __call__(self, *args: str, timeout: float):
        if args == ("list", "-a", "-j"):
            return [
                {"uuid": "11111111-1111-1111-1111-111111111111", "name": "Windows 11", "status": "running" if self.running else "stopped"},
                {"uuid": "22222222-2222-2222-2222-222222222222", "name": "Existing Clone", "status": "stopped"},
            ]
        if args == ("list", "-i", "-j", "11111111-1111-1111-1111-111111111111"):
            return [{
                "uuid": "11111111-1111-1111-1111-111111111111",
                "name": "Windows 11",
                "status": "running" if self.running else "stopped",
                "os": "win-11",
            }]
        raise AssertionError(args)


class FakeRunner:
    def __init__(self, returncode: int = 0, stdout: str = "success\n", stderr: str = "") -> None:
        self.calls: list[tuple[str, ...]] = []
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    async def __call__(self, *args: str, timeout: float, stdin: str | None = None) -> CommandResult:
        self.calls.append(args)
        return CommandResult(
            args=("prlctl", *args),
            returncode=self.returncode,
            stdout=self.stdout,
            stderr=self.stderr,
        )


class VmManagementServiceTests(unittest.TestCase):
    def test_clone_linked_success(self) -> None:
        fake_runner = FakeRunner()
        service = VmManagementService(VmService(FakeJsonRunner()), fake_runner)

        result = asyncio.run(service.clone("Windows 11", "Win11-Worker-1", linked=True))
        self.assertEqual(result.source_vm, "Windows 11")
        self.assertEqual(result.name, "Win11-Worker-1")
        self.assertTrue(result.linked)
        self.assertEqual(
            fake_runner.calls[0],
            ("clone", "11111111-1111-1111-1111-111111111111", "--name", "Win11-Worker-1", "--linked"),
        )

    def test_clone_full_with_dst_success(self) -> None:
        fake_runner = FakeRunner()
        service = VmManagementService(VmService(FakeJsonRunner()), fake_runner)

        result = asyncio.run(
            service.clone("Windows 11", "Win11-Worker-2", linked=False, dst="/tmp/clones/win2.pvm")
        )
        self.assertEqual(result.name, "Win11-Worker-2")
        self.assertFalse(result.linked)
        self.assertEqual(
            fake_runner.calls[0],
            (
                "clone",
                "11111111-1111-1111-1111-111111111111",
                "--name",
                "Win11-Worker-2",
                "--dst",
                str(Path("/tmp/clones/win2.pvm").resolve()),
            ),
        )

    def test_clone_empty_name_raises(self) -> None:
        service = VmManagementService(VmService(FakeJsonRunner()), FakeRunner())
        with self.assertRaises(ValueError):
            asyncio.run(service.clone("Windows 11", "   "))

    def test_clone_duplicate_name_raises(self) -> None:
        service = VmManagementService(VmService(FakeJsonRunner()), FakeRunner())
        with self.assertRaises(ValueError):
            asyncio.run(service.clone("Windows 11", "Existing Clone"))

    def test_delete_requires_confirm(self) -> None:
        service = VmManagementService(VmService(FakeJsonRunner(running=False)), FakeRunner())
        with self.assertRaises(ValueError):
            asyncio.run(service.delete("Windows 11", confirm=False))

    def test_delete_running_vm_raises(self) -> None:
        service = VmManagementService(VmService(FakeJsonRunner(running=True)), FakeRunner())
        with self.assertRaises(RuntimeError):
            asyncio.run(service.delete("Windows 11", confirm=True))

    def test_delete_stopped_vm_success(self) -> None:
        fake_runner = FakeRunner()
        service = VmManagementService(VmService(FakeJsonRunner(running=False)), fake_runner)

        result = asyncio.run(service.delete("Windows 11", confirm=True))
        self.assertEqual(result.vm, "Windows 11")
        self.assertTrue(result.deleted)
        self.assertEqual(
            fake_runner.calls[0],
            ("delete", "11111111-1111-1111-1111-111111111111"),
        )

    def test_set_headless_true(self) -> None:
        fake_runner = FakeRunner()
        service = VmManagementService(VmService(FakeJsonRunner()), fake_runner)

        result = asyncio.run(service.set_headless("Windows 11", enabled=True))
        self.assertTrue(result.headless)
        self.assertEqual(
            fake_runner.calls[0],
            ("set", "11111111-1111-1111-1111-111111111111", "--startup-view", "headless"),
        )

    def test_set_headless_false(self) -> None:
        fake_runner = FakeRunner()
        service = VmManagementService(VmService(FakeJsonRunner()), fake_runner)

        result = asyncio.run(service.set_headless("Windows 11", enabled=False))
        self.assertFalse(result.headless)
        self.assertEqual(
            fake_runner.calls[0],
            ("set", "11111111-1111-1111-1111-111111111111", "--startup-view", "window"),
        )

    def test_set_network_condition_profile(self) -> None:
        fake_runner = FakeRunner()
        service = VmManagementService(VmService(FakeJsonRunner()), fake_runner)

        result = asyncio.run(service.set_network_condition("Windows 11", profile="3g"))
        self.assertTrue(result.enabled)
        self.assertEqual(result.profile, "3g")
        self.assertEqual(
            fake_runner.calls[0],
            (
                "set",
                "11111111-1111-1111-1111-111111111111",
                "--network-conditioner",
                "on",
                "--network-conditioner-profile",
                "3g",
            ),
        )

    def test_set_network_condition_off(self) -> None:
        fake_runner = FakeRunner()
        service = VmManagementService(VmService(FakeJsonRunner()), fake_runner)

        result = asyncio.run(service.set_network_condition("Windows 11", profile="off"))
        self.assertFalse(result.enabled)
        self.assertEqual(result.profile, "off")
        self.assertEqual(
            fake_runner.calls[0],
            (
                "set",
                "11111111-1111-1111-1111-111111111111",
                "--network-conditioner",
                "off",
            ),
        )

    def test_command_failure_raises(self) -> None:
        fake_runner = FakeRunner(returncode=1, stderr="Error occurred")
        service = VmManagementService(VmService(FakeJsonRunner()), fake_runner)

        with self.assertRaises(PrlCommandError):
            asyncio.run(service.set_headless("Windows 11", enabled=True))
