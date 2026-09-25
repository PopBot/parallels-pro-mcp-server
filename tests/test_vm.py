import asyncio
import unittest
from typing import Any

from parallels_mcp.vm import AmbiguousVmError, VmNotFoundError, VmService


class FakeRunner:
    def __init__(self, responses: dict[tuple[str, ...], Any]) -> None:
        self.responses = responses
        self.calls: list[tuple[tuple[str, ...], float]] = []

    async def __call__(self, *args: str, timeout: float) -> Any:
        self.calls.append((args, timeout))
        return self.responses[args]


LIST = [
    {
        "uuid": "{11111111-1111-1111-1111-111111111111}",
        "status": "running",
        "ip_configured": "192.0.2.10",
        "name": "Windows 11",
    },
    {
        "uuid": "22222222-2222-2222-2222-222222222222",
        "status": "stopped",
        "ip_configured": "-",
        "name": "Ubuntu",
    },
]


class VmServiceTests(unittest.TestCase):
    def test_list_normalizes_compact_json(self) -> None:
        runner = FakeRunner({("list", "-a", "-j"): LIST})
        result = asyncio.run(VmService(runner).list_vms())
        self.assertEqual(result[0].uuid, "11111111-1111-1111-1111-111111111111")
        self.assertEqual(result[0].ip_address, "192.0.2.10")
        self.assertIsNone(result[1].ip_address)

    def test_status_handles_detailed_cli_field_names(self) -> None:
        detail = [
            {
                "ID": "{11111111-1111-1111-1111-111111111111}",
                "Name": "Windows 11",
                "State": "running",
                "OS": "win-11",
                "Uptime": "42",
                "Home": "/Users/example/Parallels/Windows 11.pvm/",
                "GuestTools": {"state": "outdated", "version": "26.4.0"},
            }
        ]
        runner = FakeRunner(
            {
                ("list", "-a", "-j"): LIST,
                ("list", "-i", "-j", "11111111-1111-1111-1111-111111111111"): detail,
            }
        )
        result = asyncio.run(VmService(runner).status("Windows 11"))
        self.assertEqual(result.status, "running")
        self.assertEqual(result.os, "win-11")
        self.assertEqual(result.uptime_seconds, 42)
        self.assertEqual(result.guest_tools_state, "outdated")
        self.assertEqual(
            runner.calls[-1][0],
            ("list", "-i", "-j", "11111111-1111-1111-1111-111111111111"),
        )

    def test_unknown_vm_reports_known_names(self) -> None:
        runner = FakeRunner({("list", "-a", "-j"): LIST})
        with self.assertRaises(VmNotFoundError) as caught:
            asyncio.run(VmService(runner).resolve("missing"))
        self.assertIn("Ubuntu", str(caught.exception))
        self.assertIn("Windows 11", str(caught.exception))

    def test_duplicate_names_require_a_uuid(self) -> None:
        duplicate_list = [
            {**LIST[0], "uuid": "11111111-1111-1111-1111-111111111111"},
            {**LIST[1], "uuid": "22222222-2222-2222-2222-222222222222", "name": "Windows 11"},
        ]
        runner = FakeRunner({("list", "-a", "-j"): duplicate_list})
        with self.assertRaises(AmbiguousVmError):
            asyncio.run(VmService(runner).resolve("Windows 11"))
