import asyncio
import unittest
from pathlib import Path
from typing import Any

from parallels_mcp.guest import GuestService, to_guest_path
from parallels_mcp.prl import CommandResult
from parallels_mcp.vm import VmService


class FakeRunner:
    def __init__(self, responses: dict[tuple[str, ...], Any]) -> None:
        self.responses = responses
        self.calls: list[tuple[tuple[str, ...], float]] = []

    async def __call__(self, *args: str, timeout: float) -> Any:
        self.calls.append((args, timeout))
        response = self.responses[args]
        return response() if callable(response) else response


class GuestServiceTests(unittest.TestCase):
    def test_exec_places_uuid_and_current_user_before_guest_argv_on_linux(self) -> None:
        discovery = FakeRunner(
            {
                ("list", "-a", "-j"): [
                    {
                        "uuid": "{11111111-1111-1111-1111-111111111111}",
                        "status": "running",
                        "name": "Ubuntu Linux",
                    }
                ]
            }
        )
        execution = FakeRunner(
            {
                ("exec", "11111111-1111-1111-1111-111111111111", "--current-user", "whoami"): CommandResult(
                    args=("prlctl", "exec"),
                    returncode=0,
                    stdout="jarodwong\n",
                    stderr="",
                )
            }
        )
        service = GuestService(VmService(discovery), execution)
        result = asyncio.run(service.execute("Ubuntu Linux", ["whoami"]))
        self.assertEqual(result.stdout, "jarodwong")
        self.assertEqual(execution.calls[0][0], ("exec", "11111111-1111-1111-1111-111111111111", "--current-user", "whoami"))

    def test_exec_windows_omits_current_user(self) -> None:
        discovery = FakeRunner(
            {
                ("list", "-a", "-j"): [
                    {
                        "uuid": "{11111111-1111-1111-1111-111111111111}",
                        "status": "running",
                        "name": "Windows 11",
                    }
                ]
            }
        )
        execution = FakeRunner(
            {
                ("exec", "11111111-1111-1111-1111-111111111111", "whoami"): CommandResult(
                    args=("prlctl", "exec"),
                    returncode=0,
                    stdout="nt authority\\system\r\n",
                    stderr="",
                )
            }
        )
        service = GuestService(VmService(discovery), execution)
        result = asyncio.run(service.execute("Windows 11", ["whoami"]))
        self.assertEqual(result.stdout, "nt authority\\system")
        self.assertEqual(execution.calls[0][0], ("exec", "11111111-1111-1111-1111-111111111111", "whoami"))

    def test_exec_with_explicit_user(self) -> None:
        discovery = FakeRunner(
            {
                ("list", "-a", "-j"): [
                    {
                        "uuid": "{11111111-1111-1111-1111-111111111111}",
                        "status": "running",
                        "name": "Ubuntu",
                    }
                ]
            }
        )
        execution = FakeRunner(
            {
                ("exec", "11111111-1111-1111-1111-111111111111", "--user", "root", "whoami"): CommandResult(
                    args=("prlctl", "exec"),
                    returncode=0,
                    stdout="root\n",
                    stderr="",
                )
            }
        )
        service = GuestService(VmService(discovery), execution)
        result = asyncio.run(service.execute("Ubuntu", ["whoami"], user="root"))
        self.assertEqual(result.stdout, "root")
        self.assertEqual(execution.calls[0][0], ("exec", "11111111-1111-1111-1111-111111111111", "--user", "root", "whoami"))

    def test_to_guest_path_windows_and_linux(self) -> None:
        fake_home = Path("/Users/developer")
        fake_file = fake_home / "projects" / "test.txt"

        win_path = to_guest_path(fake_file, host_home=fake_home, is_windows=True)
        self.assertEqual(win_path, r"\\Mac\Home\projects\test.txt")

        linux_path = to_guest_path(fake_file, host_home=fake_home, is_windows=False)
        self.assertEqual(linux_path, "/media/psf/Home/projects/test.txt")

    def test_exec_retries_transient_failure(self) -> None:
        discovery = FakeRunner(
            {
                ("list", "-a", "-j"): [
                    {
                        "uuid": "{11111111-1111-1111-1111-111111111111}",
                        "status": "running",
                        "name": "Windows 11",
                    }
                ]
            }
        )
        attempts = 0

        async def flaky_runner(*args: str, timeout: float) -> CommandResult:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return CommandResult(
                    args=("prlctl", *args),
                    returncode=1,
                    stdout="",
                    stderr="Failed to connect to Parallels Tools\n",
                )
            return CommandResult(
                args=("prlctl", *args),
                returncode=0,
                stdout="recovered\n",
                stderr="",
            )

        service = GuestService(VmService(discovery), flaky_runner)
        result = asyncio.run(service.execute("Windows 11", ["echo", "test"], retries=1, retry_delay_s=0.01))
        self.assertTrue(result.ok)
        self.assertEqual(result.stdout, "recovered")
        self.assertEqual(attempts, 2)

    def test_exec_current_user_linux_session_fallback(self) -> None:
        discovery = FakeRunner(
            {
                ("list", "-a", "-j"): [
                    {
                        "uuid": "{11111111-1111-1111-1111-111111111111}",
                        "status": "running",
                        "name": "Ubuntu",
                    }
                ]
            }
        )
        call_args: list[tuple[str, ...]] = []

        async def session_fallback_runner(*args: str, timeout: float) -> CommandResult:
            call_args.append(args)
            if "--current-user" in args:
                return CommandResult(
                    args=("prlctl", *args),
                    returncode=1,
                    stdout="",
                    stderr="Failed to execute the command: The current user is not logged in\n",
                )
            return CommandResult(
                args=("prlctl", *args),
                returncode=0,
                stdout="root-success\n",
                stderr="",
            )

        service = GuestService(VmService(discovery), session_fallback_runner)
        result = asyncio.run(service.execute("Ubuntu", ["whoami"], retries=1))
        self.assertTrue(result.ok)
        self.assertEqual(result.stdout, "root-success")
        self.assertIn("--current-user", call_args[0])
        self.assertIn("--user", call_args[1])
        self.assertIn("root", call_args[1])
