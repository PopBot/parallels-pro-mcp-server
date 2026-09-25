import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from parallels_mcp.prl import PrlCommandError, PrlOutputError, run_prlctl, run_prlctl_json


class FakeProcess:
    def __init__(self, returncode: int = 0, stdout: bytes = b"", stderr: bytes = b"") -> None:
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr
        self.received_input: bytes | None = None

    async def communicate(self, input: bytes | None = None) -> tuple[bytes, bytes]:
        self.received_input = input
        return self._stdout, self._stderr

    def kill(self) -> None:
        pass


class PrlRunnerTests(unittest.TestCase):
    def test_uses_explicit_argv_without_a_shell(self) -> None:
        process = FakeProcess(stdout=b"ok\n")
        create = AsyncMock(return_value=process)
        with patch("asyncio.create_subprocess_exec", create):
            result = asyncio.run(run_prlctl("list", "-a", "-j"))

        self.assertTrue(result.ok)
        self.assertEqual(result.args, ("prlctl", "list", "-a", "-j"))
        create.assert_awaited_once_with(
            "prlctl",
            "list",
            "-a",
            "-j",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    def test_json_preserves_cli_failure_details(self) -> None:
        process = FakeProcess(returncode=7, stderr=b"bad VM\n")
        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=process)):
            with self.assertRaises(PrlCommandError) as caught:
                asyncio.run(run_prlctl_json("status", "missing"))
        self.assertEqual(caught.exception.result.returncode, 7)
        self.assertIn("bad VM", str(caught.exception))

    def test_json_failure_is_distinguished_from_cli_failure(self) -> None:
        process = FakeProcess(stdout=b"not json\n")
        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=process)):
            with self.assertRaises(PrlOutputError):
                asyncio.run(run_prlctl_json("list", "-a", "-j"))
