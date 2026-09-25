"""Host-side Parallels VM screen capture."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from pydantic import BaseModel, ConfigDict

from .prl import CommandResult, PrlCommandError, run_prlctl
from .vm import VmService


Runner = Callable[..., Awaitable[CommandResult]]


class ScreenshotResult(BaseModel):
    """Result of capturing a VM screen."""

    model_config = ConfigDict(extra="forbid")

    vm: str
    uuid: str
    path: str
    bytes: int


class ScreenCapture:
    def __init__(self, vms: VmService, runner: Runner = run_prlctl) -> None:
        self._vms = vms
        self._runner = runner

    async def capture(self, vm: str, path: Path, *, timeout: float = 30.0) -> ScreenshotResult:
        path = path.expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        uuid = await self._vms.resolve(vm)
        result = await self._runner("capture", uuid, "--file", str(path), timeout=timeout)
        if not result.ok:
            raise PrlCommandError(result)
        if not path.is_file():
            raise RuntimeError(f"Parallels reported capture success but did not create {path}")
        return ScreenshotResult(
            vm=vm,
            uuid=uuid,
            path=str(path),
            bytes=path.stat().st_size,
        )
