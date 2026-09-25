"""The subprocess boundary for the Parallels command-line tools.

This module deliberately accepts argv elements, never a shell command string.
Keeping process creation here makes the host-side security boundary small and
auditable before guest execution is added.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any


class PrlError(RuntimeError):
    """Base error for failures talking to Parallels Desktop."""


class PrlTimeoutError(PrlError):
    """Raised when a Parallels command does not finish in time."""


class PrlOutputError(PrlError):
    """Raised when a command claims JSON output but returns invalid JSON."""


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Captured result of one argv-based Parallels command."""

    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class PrlCommandError(PrlError):
    """Raised for a non-zero Parallels command result."""

    def __init__(self, result: CommandResult) -> None:
        detail = result.stderr.strip() or result.stdout.strip() or "no error output"
        command = " ".join(result.args)
        super().__init__(
            f"Parallels command failed with exit code {result.returncode}: "
            f"{command}: {detail}"
        )
        self.result = result


async def run_argv(
    executable: str,
    *args: str,
    timeout: float = 30.0,
) -> CommandResult:
    """Run one executable with explicit argv and capture both output streams."""

    if timeout <= 0:
        raise ValueError("timeout must be greater than zero")

    argv = (executable, *args)
    try:
        process = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise PrlError(f"Parallels executable not found: {executable!r}") from exc
    except OSError as exc:
        raise PrlError(f"Could not start Parallels executable {executable!r}: {exc}") from exc

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError as exc:
        process.kill()
        await process.communicate()
        raise PrlTimeoutError(
            f"Parallels command timed out after {timeout:.1f}s: {' '.join(argv)}"
        ) from exc

    return CommandResult(
        args=argv,
        returncode=process.returncode,
        stdout=stdout_bytes.decode(errors="replace"),
        stderr=stderr_bytes.decode(errors="replace"),
    )


async def run_prlctl(
    *args: str,
    timeout: float = 30.0,
    executable: str = "prlctl",
) -> CommandResult:
    """Run ``prlctl`` with an explicit argv."""

    return await run_argv(executable, *args, timeout=timeout)


async def run_prlctl_json(*args: str, timeout: float = 30.0) -> Any:
    """Run ``prlctl`` and decode its JSON stdout, preserving CLI failures."""

    result = await run_prlctl(*args, timeout=timeout)
    if not result.ok:
        raise PrlCommandError(result)

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise PrlOutputError(
            f"Parallels returned invalid JSON for {' '.join(result.args)}: {exc}"
        ) from exc
