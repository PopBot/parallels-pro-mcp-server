"""Command execution inside a Parallels guest."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from .prl import CommandResult, run_prlctl
from .vm import VmService


Runner = Callable[..., Awaitable[CommandResult]]
DEFAULT_TIMEOUT = 300.0
MAX_OUTPUT_CHARS = 8_000

TRANSIENT_PARALLELS_PATTERNS = (
    "failed to connect to parallels tools",
    "the virtual machine is not ready",
    "cannot connect to the virtual machine",
    "authentication failed",
    "prl_err_disp_connection_lost",
    "guest is not ready",
    "user credentials are not valid",
    "connection closed",
    "server is busy",
    "prl_err_operation_failed",
    "operation timed out",
)


def to_guest_path(
    host_path: Path | str,
    *,
    host_home: Path | None = None,
    guest_home: str | None = None,
    is_windows: bool = True,
) -> str:
    """Map a host path under the shared home folder to a guest path (UNC on Windows, /media/psf on Linux)."""

    home = (host_home or Path.home()).expanduser().resolve()
    path = Path(host_path).expanduser().resolve()
    try:
        relative = path.relative_to(home)
    except ValueError as exc:
        raise ValueError(f"{path} is outside the shared host home {home}") from exc

    if is_windows:
        base = (guest_home or r"\\Mac\Home").rstrip("\\")
        return base + "\\" + "\\".join(relative.parts)
    else:
        base = (guest_home or "/media/psf/Home").rstrip("/")
        return base + "/" + "/".join(relative.parts)


class GuestExecResult(BaseModel):
    """Bounded result of one guest command."""

    model_config = ConfigDict(extra="forbid")

    vm: str
    uuid: str
    command: list[str]
    returncode: int
    ok: bool
    stdout: str
    stderr: str
    stdout_truncated: bool = False
    stderr_truncated: bool = False


def _bounded(value: str) -> tuple[str, bool]:
    value = value.strip()
    if len(value) <= MAX_OUTPUT_CHARS:
        return value, False
    return value[-MAX_OUTPUT_CHARS:], True


class GuestService:
    """Run commands inside guest operating systems with transient error resilience."""

    def __init__(
        self,
        vms: VmService,
        runner: Runner = run_prlctl,
        *,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._vms = vms
        self._runner = runner
        self._timeout = timeout

    @property
    def vms(self) -> VmService:
        return self._vms

    async def execute(
        self,
        vm: str,
        command: list[str],
        *,
        user: str | None = None,
        timeout: float | None = None,
        retries: int = 1,
        retry_delay_s: float = 1.0,
    ) -> GuestExecResult:
        if not command or any(not isinstance(arg, str) or not arg for arg in command):
            raise ValueError("command must contain at least one non-empty string")

        uuid = await self._vms.resolve(vm)
        is_win = await self._vms.is_windows(uuid)
        if user:
            user_args = ["--user", user]
        elif is_win:
            user_args = []
        else:
            user_args = ["--current-user"]
        exec_timeout = self._timeout if timeout is None else timeout

        attempts = 0
        max_attempts = max(1, 1 + retries)
        current_user_args = list(user_args)

        while True:
            attempts += 1
            result = await self._runner(
                "exec",
                uuid,
                *current_user_args,
                *command,
                timeout=exec_timeout,
            )

            # If failed because --current-user is unsupported (Windows) or no interactive GUI session (Linux)
            if not result.ok and user is None and attempts < max_attempts:
                stderr_lower = result.stderr.lower()
                if "invalid argument" in stderr_lower or "prljob_getretcode" in stderr_lower:
                    current_user_args = []
                    await asyncio.sleep(0.5)
                    continue
                if any(phrase in stderr_lower for phrase in ("not logged in", "current user", "no user")):
                    current_user_args = ["--user", "root"]
                    await asyncio.sleep(0.5)
                    continue

            # If failed due to transient Parallels communication glitch
            if not result.ok and attempts < max_attempts:
                stderr_lower = result.stderr.lower()
                is_transient = any(pattern in stderr_lower for pattern in TRANSIENT_PARALLELS_PATTERNS)
                if is_transient or result.returncode in (45, 137):
                    await asyncio.sleep(retry_delay_s)
                    continue

            break

        stdout, stdout_truncated = _bounded(result.stdout)
        stderr, stderr_truncated = _bounded(result.stderr)
        return GuestExecResult(
            vm=vm,
            uuid=uuid,
            command=command,
            returncode=result.returncode,
            ok=result.ok,
            stdout=stdout,
            stderr=stderr,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
        )

