import asyncio
import json
import unittest
from typing import Any

from parallels_mcp.input import InputService
from parallels_mcp.prl import CommandResult
from parallels_mcp.vm import VmService


class FakeJsonRunner:
    async def __call__(self, *args: str, timeout: float):
        if args == ("list", "-a", "-j"):
            return [{"uuid": "11111111-1111-1111-1111-111111111111", "name": "Windows 11", "status": "running"}]
        raise AssertionError(args)


class FakeRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], Any]] = []

    async def __call__(self, *args: str, timeout: float, stdin: str | None = None) -> CommandResult:
        self.calls.append((args, stdin))
        return CommandResult(args=("prlctl", *args), returncode=0, stdout="", stderr="")


class InputServiceTests(unittest.TestCase):
    def test_send_keys_single_key(self) -> None:
        fake_runner = FakeRunner()
        service = InputService(VmService(FakeJsonRunner()), fake_runner)

        result = asyncio.run(service.send_keys("Windows 11", "enter"))
        self.assertEqual(result.vm, "Windows 11")
        self.assertEqual(result.uuid, "11111111-1111-1111-1111-111111111111")
        self.assertEqual(result.events_sent, 2)  # press and release

        args, stdin = fake_runner.calls[0]
        self.assertEqual(args, ("send-key-event", "11111111-1111-1111-1111-111111111111", "-j"))
        payload = json.loads(stdin)
        self.assertEqual(payload, [
            {"key": 36, "event": "press", "delay": 50},
            {"key": 36, "event": "release", "delay": 50},
        ])

    def test_send_keys_chord_combination(self) -> None:
        fake_runner = FakeRunner()
        service = InputService(VmService(FakeJsonRunner()), fake_runner)

        result = asyncio.run(service.send_keys("Windows 11", ["ctrl+alt+del"]))
        self.assertEqual(result.events_sent, 6)  # 3 press + 3 release in reverse

        args, stdin = fake_runner.calls[0]
        payload = json.loads(stdin)
        # Ctrl (37), Alt (64), Del (106)
        expected_keys = [37, 64, 106, 106, 64, 37]
        self.assertEqual([e["key"] for e in payload], expected_keys)
        self.assertEqual([e["event"] for e in payload], [
            "press", "press", "press",
            "release", "release", "release"
        ])

    def test_send_keys_invalid_token_raises_error(self) -> None:
        fake_runner = FakeRunner()
        service = InputService(VmService(FakeJsonRunner()), fake_runner)

        with self.assertRaises(ValueError):
            asyncio.run(service.send_keys("Windows 11", "super_nonexistent_key_xyz"))
