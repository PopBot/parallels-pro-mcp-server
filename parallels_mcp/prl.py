"""The subprocess boundary for the Parallels command-line tools.

This module deliberately accepts argv elements, never a shell command string.
Keeping process creation here makes the host-side security boundary small and
auditable before guest execution is added.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import logging
import time
from typing import Any

logger = logging.getLogger("parallels_mcp.prl")


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


@dataclass(frozen=True, slots=True)
class BinaryCommandResult:
    """Captured binary result of one argv-based Parallels command."""

    args: tuple[str, ...]
    returncode: int
    stdout_bytes: bytes
    stderr_bytes: bytes

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class PrlCommandError(PrlError):
    """Raised for a non-zero Parallels command result."""

    def __init__(self, result: CommandResult | BinaryCommandResult) -> None:
        if isinstance(result, BinaryCommandResult):
            detail = result.stderr_bytes.decode(errors="replace").strip() or "no error output"
        else:
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
    stdin: str | bytes | None = None,
) -> CommandResult:
    """Run one executable with explicit argv and capture both output streams."""

    if timeout <= 0:
        raise ValueError("timeout must be greater than zero")

    argv = (executable, *args)
    t0 = time.monotonic()
    logger.debug("Executing: %s", " ".join(argv))
    stdin_kwargs = {"stdin": asyncio.subprocess.PIPE} if stdin is not None else {}
    input_bytes = stdin.encode("utf-8") if isinstance(stdin, str) else stdin
    try:
        process = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **stdin_kwargs,
        )
    except FileNotFoundError as exc:
        raise PrlError(f"Parallels executable not found: {executable!r}") from exc
    except OSError as exc:
        raise PrlError(f"Could not start Parallels executable {executable!r}: {exc}") from exc

    try:
        communicate_kwargs = {"input": input_bytes} if input_bytes is not None else {}
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(**communicate_kwargs), timeout=timeout
        )
    except asyncio.TimeoutError as exc:
        process.kill()
        await process.communicate()
        raise PrlTimeoutError(
            f"Parallels command timed out after {timeout:.1f}s: {' '.join(argv)}"
        ) from exc

    elapsed = time.monotonic() - t0
    logger.debug("Finished %s in %.3fs (returncode: %d)", argv[0], elapsed, process.returncode)
    return CommandResult(
        args=argv,
        returncode=process.returncode,
        stdout=stdout_bytes.decode(errors="replace"),
        stderr=stderr_bytes.decode(errors="replace"),
    )


async def run_argv_binary(
    executable: str,
    *args: str,
    timeout: float = 30.0,
    stdin: str | bytes | None = None,
) -> BinaryCommandResult:
    """Run one executable with explicit argv and capture raw bytes."""

    if timeout <= 0:
        raise ValueError("timeout must be greater than zero")

    argv = (executable, *args)
    t0 = time.monotonic()
    logger.debug("Executing (binary): %s", " ".join(argv))
    stdin_kwargs = {"stdin": asyncio.subprocess.PIPE} if stdin is not None else {}
    input_bytes = stdin.encode("utf-8") if isinstance(stdin, str) else stdin
    try:
        process = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **stdin_kwargs,
        )
    except FileNotFoundError as exc:
        raise PrlError(f"Parallels executable not found: {executable!r}") from exc
    except OSError as exc:
        raise PrlError(f"Could not start Parallels executable {executable!r}: {exc}") from exc

    try:
        communicate_kwargs = {"input": input_bytes} if input_bytes is not None else {}
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(**communicate_kwargs), timeout=timeout
        )
    except asyncio.TimeoutError as exc:
        process.kill()
        await process.communicate()
        raise PrlTimeoutError(
            f"Parallels command timed out after {timeout:.1f}s: {' '.join(argv)}"
        ) from exc

    elapsed = time.monotonic() - t0
    logger.debug("Finished (binary) %s in %.3fs (returncode: %d)", argv[0], elapsed, process.returncode)
    return BinaryCommandResult(
        args=argv,
        returncode=process.returncode,
        stdout_bytes=stdout_bytes,
        stderr_bytes=stderr_bytes,
    )


async def run_prlctl(
    *args: str,
    timeout: float = 30.0,
    executable: str = "prlctl",
    stdin: str | bytes | None = None,
) -> CommandResult:
    """Run ``prlctl`` with an explicit argv."""

    return await run_argv(executable, *args, timeout=timeout, stdin=stdin)


async def run_prlctl_binary(
    *args: str,
    timeout: float = 30.0,
    executable: str = "prlctl",
    stdin: str | bytes | None = None,
) -> BinaryCommandResult:
    """Run ``prlctl`` and capture raw binary stdout/stderr."""

    return await run_argv_binary(executable, *args, timeout=timeout, stdin=stdin)


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
