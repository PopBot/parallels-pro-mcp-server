import asyncio
import unittest
from typing import Any

from parallels_mcp.snapshots import SnapshotService
from parallels_mcp.vm import VmService
from parallels_mcp.prl import CommandResult


class FakeJsonRunner:
    async def __call__(self, *args: str, timeout: float) -> Any:
        if args == ("list", "-a", "-j"):
            return [{"uuid": "11111111-1111-1111-1111-111111111111", "name": "Windows 11", "status": "running"}]
        if args == ("snapshot-list", "11111111-1111-1111-1111-111111111111", "-j"):
            return {
                "{aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa}": {
                    "name": "clean-baseline",
                    "date": "2026-08-15 14:25:04",
                    "state": "poweron",
                    "current": True,
                    "parent": "",
                }
            }
        raise AssertionError(args)


class FakeRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    async def __call__(self, *args: str, timeout: float) -> CommandResult:
        self.calls.append(args)
        return CommandResult(args=("prlctl", *args), returncode=0, stdout="ok\n", stderr="")


class SnapshotServiceTests(unittest.TestCase):
    def test_revert_resolves_snapshot_name_to_id(self) -> None:
        runner = FakeRunner()
        service = SnapshotService(VmService(FakeJsonRunner()), json_runner=FakeJsonRunner(), runner=runner)
        result = asyncio.run(service.revert("Windows 11", "clean-baseline"))
        self.assertEqual(result.snapshot_id, "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        self.assertEqual(
            runner.calls[-1],
            (
                "snapshot-switch",
                "11111111-1111-1111-1111-111111111111",
                "--id",
                "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            ),
        )

    def test_delete_resolves_snapshot_name_to_id(self) -> None:
        runner = FakeRunner()
        service = SnapshotService(VmService(FakeJsonRunner()), json_runner=FakeJsonRunner(), runner=runner)
        result = asyncio.run(service.delete("Windows 11", "clean-baseline"))
        self.assertEqual(result.snapshot_id, "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        self.assertEqual(
            runner.calls[-1],
            (
                "snapshot-delete",
                "11111111-1111-1111-1111-111111111111",
                "--id",
                "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            ),
        )
