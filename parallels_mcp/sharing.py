"""Parallels host-to-guest shared folder management."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from .prl import CommandResult, PrlCommandError, run_prlctl
from .vm import VmService


Runner = Callable[..., Awaitable[CommandResult]]


class SharedFolderResult(BaseModel):
    """Result of configuring a host shared folder."""

    model_config = ConfigDict(extra="forbid")

    vm: str
    uuid: str
    name: str
    host_path: str | None
    mode: str | None
    action: str
    message: str


class SharingService:
    def __init__(self, vms: VmService, runner: Runner = run_prlctl) -> None:
        self._vms = vms
        self._runner = runner

    async def share_folder(
        self,
        vm: str,
        name: str,
        host_path: str | Path,
        *,
        mode: str = "rw",
        description: str | None = None,
        timeout: float = 30.0,
    ) -> SharedFolderResult:
        if not name or not name.strip():
            raise ValueError("Share name must not be empty")

        clean_mode = mode.strip().lower()
        if clean_mode not in {"ro", "rw"}:
            raise ValueError("mode must be 'ro' (read-only) or 'rw' (read-write)")

        path = Path(host_path).expanduser().resolve()
        if not path.is_dir():
            raise FileNotFoundError(f"Host path does not exist or is not a directory: {path}")

        uuid = await self._vms.resolve(vm)
        args = ["set", uuid, "--shf-host-add", name.strip(), "--path", str(path), "--mode", clean_mode]
        if description:
            args.extend(["--shf-description", description.strip()])

        result = await self._runner(*args, timeout=timeout)
        if not result.ok:
            raise PrlCommandError(result)

        return SharedFolderResult(
            vm=vm,
            uuid=uuid,
            name=name.strip(),
            host_path=str(path),
            mode=clean_mode,
            action="share_folder",
            message=result.stdout.strip() or f"Shared {path} as '{name}' ({clean_mode})",
        )

    async def unshare_folder(
        self,
        vm: str,
        name: str,
        *,
        timeout: float = 30.0,
    ) -> SharedFolderResult:
        if not name or not name.strip():
            raise ValueError("Share name must not be empty")

        clean_name = name.strip()
        uuid = await self._vms.resolve(vm)
        result = await self._runner("set", uuid, "--shf-host-del", clean_name, timeout=timeout)
        if not result.ok:
            raise PrlCommandError(result)

        return SharedFolderResult(
            vm=vm,
            uuid=uuid,
            name=clean_name,
            host_path=None,
            mode=None,
            action="unshare_folder",
            message=result.stdout.strip() or f"Removed shared folder '{clean_name}'",
        )
