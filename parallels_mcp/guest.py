"""Command execution inside a Parallels guest."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from .prl import CommandResult, run_prlctl
from .vm import VmService


Runner = Callable[..., Awaitable[CommandResult]]
DEFAULT_TIMEOUT = 300.0
MAX_OUTPUT_CHARS = 8_000


def to_guest_path(
    host_path: Path | str,
    *,
    host_home: Path | None = None,
    guest_home: str = r"\\Mac\Home",
) -> str:
    """Map a host path under the shared home folder to a guest UNC path."""

    home = (host_home or Path.home()).expanduser().resolve()
    path = Path(host_path).expanduser().resolve()
    try:
        relative = path.relative_to(home)
    except ValueError as exc:
        raise ValueError(f"{path} is outside the shared host home {home}") from exc
    return guest_home.rstrip("\\") + "\\" + "\\".join(relative.parts)


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
    """Run commands as the current interactive Windows user.

    ``--current-user`` and its position after the VM UUID are deliberate:
    Parallels otherwise runs in SYSTEM/session 0, which has no desktop and a
    different profile. That would make Electron validation fail for the wrong
    reason.
    """

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
    ) -> GuestExecResult:
        if not command or any(not isinstance(arg, str) or not arg for arg in command):
            raise ValueError("command must contain at least one non-empty string")

        uuid = await self._vms.resolve(vm)
        user_args = ["--user", user] if user else ["--current-user"]
        result = await self._runner(
            "exec",
            uuid,
            *user_args,
            *command,
            timeout=self._timeout if timeout is None else timeout,
        )
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
