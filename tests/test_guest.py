import asyncio
import unittest
from typing import Any

from parallels_mcp.guest import GuestService
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
    def test_exec_places_uuid_and_current_user_before_guest_argv(self) -> None:
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
                ("exec", "11111111-1111-1111-1111-111111111111", "--current-user", "whoami"): CommandResult(
                    args=("prlctl", "exec"),
                    returncode=0,
                    stdout="DOMAIN\\testuser\r\n",
                    stderr="",
                )
            }
        )
        service = GuestService(VmService(discovery), execution)
        result = asyncio.run(service.execute("Windows 11", ["whoami"]))
        self.assertEqual(result.stdout, "DOMAIN\\testuser")
        self.assertEqual(execution.calls[0][0], ("exec", "11111111-1111-1111-1111-111111111111", "--current-user", "whoami"))

    def test_exec_supports_explicit_user(self) -> None:
        discovery = FakeRunner(
            {
                ("list", "-a", "-j"): [
                    {
                        "uuid": "{11111111-1111-1111-1111-111111111111}",
                        "status": "running",
                        "name": "Ubuntu 20.04",
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
        result = asyncio.run(service.execute("Ubuntu 20.04", ["whoami"], user="root"))
        self.assertEqual(result.stdout, "root")
        self.assertEqual(execution.calls[0][0], ("exec", "11111111-1111-1111-1111-111111111111", "--user", "root", "whoami"))
