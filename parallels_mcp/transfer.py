"""Bi-directional file and directory streaming between host and Parallels guests."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import io
import os
from pathlib import Path
import tarfile
from typing import Any

from pydantic import BaseModel, ConfigDict

from .guest import GuestService
from .prl import BinaryCommandResult, CommandResult, PrlCommandError, run_prlctl_binary
from .vm import VmService


BinaryRunner = Callable[..., Awaitable[BinaryCommandResult]]


class FileTransferResult(BaseModel):
    """Result of copying files or directories between host and guest."""

    model_config = ConfigDict(extra="forbid")

    vm: str
    uuid: str
    source: str
    destination: str
    bytes: int
    message: str


def _split_guest_path(guest_path: str, is_windows: bool) -> tuple[str, str]:
    norm = guest_path.strip().replace("/", "\\") if is_windows else guest_path.strip()
    sep = "\\" if is_windows else "/"
    parts = norm.rstrip(sep).rsplit(sep, 1)
    if len(parts) == 2:
        parent, name = parts[0], parts[1]
        if is_windows and parent.endswith(":"):
            parent = parent + "\\"
        return parent or ("C:\\" if is_windows else "/"), name
    return ("C:\\" if is_windows else "/"), parts[0]


class FileTransferService:
    def __init__(
        self,
        vms: VmService,
        guest: GuestService,
        binary_runner: BinaryRunner = run_prlctl_binary,
    ) -> None:
        self._vms = vms
        self._guest = guest
        self._binary_runner = binary_runner

    async def copy_to_guest(
        self,
        vm: str,
        host_path: str | Path,
        guest_path: str,
        *,
        user: str | None = None,
        timeout: float = 300.0,
    ) -> FileTransferResult:
        src = Path(host_path).expanduser().resolve()
        if not src.exists():
            raise FileNotFoundError(f"Source path does not exist on host: {src}")

        uuid = await self._vms.resolve(vm)
        status = await self._vms.status(vm)
        is_windows = "win" in (status.os or "").lower()

        # Build in-memory tar stream
        tar_buf = io.BytesIO()
        total_uncompressed_bytes = 0

        with tarfile.open(fileobj=tar_buf, mode="w") as archive:
            if src.is_file():
                total_uncompressed_bytes = src.stat().st_size
                _, dest_name = _split_guest_path(guest_path, is_windows)
                archive.add(src, arcname=dest_name, recursive=False)
            else:
                for entry in src.rglob("*"):
                    rel = entry.relative_to(src)
                    if entry.is_file():
                        total_uncompressed_bytes += entry.stat().st_size
                    archive.add(entry, arcname=str(rel), recursive=False)

        tar_data = tar_buf.getvalue()

        # Determine target directory in guest
        if src.is_file():
            target_dir, _ = _split_guest_path(guest_path, is_windows)
        else:
            target_dir = guest_path.strip()

        # Ensure destination directory exists in guest
        if is_windows:
            mkdir_cmd = [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                f"if (!(Test-Path -LiteralPath '{target_dir}')) {{ New-Item -ItemType Directory -Force -Path '{target_dir}' | Out-Null }}",
            ]
        else:
            mkdir_cmd = ["mkdir", "-p", target_dir]

        await self._guest.execute(vm, mkdir_cmd, user=user, timeout=30.0)

        # Stream tar into guest tar
        tar_bin = "tar.exe" if is_windows else "tar"
        user_args = ["--user", user] if user else ["--current-user"]
        result = await self._binary_runner(
            "exec",
            uuid,
            *user_args,
            tar_bin,
            "-xf",
            "-",
            "-C",
            target_dir,
            timeout=timeout,
            stdin=tar_data,
        )
        if not result.ok:
            raise PrlCommandError(result)

        return FileTransferResult(
            vm=vm,
            uuid=uuid,
            source=str(src),
            destination=guest_path,
            bytes=total_uncompressed_bytes,
            message=f"Transferred {total_uncompressed_bytes} bytes from host '{src.name}' to guest '{guest_path}'",
        )

    async def copy_from_guest(
        self,
        vm: str,
        guest_path: str,
        host_path: str | Path,
        *,
        user: str | None = None,
        timeout: float = 300.0,
    ) -> FileTransferResult:
        uuid = await self._vms.resolve(vm)
        status = await self._vms.status(vm)
        is_windows = "win" in (status.os or "").lower()

        parent_dir, target_name = _split_guest_path(guest_path, is_windows)
        tar_bin = "tar.exe" if is_windows else "tar"
        user_args = ["--user", user] if user else ["--current-user"]

        # Stream tar archive out of guest
        result = await self._binary_runner(
            "exec",
            uuid,
            *user_args,
            tar_bin,
            "-cf",
            "-",
            "-C",
            parent_dir,
            target_name,
            timeout=timeout,
        )
        if not result.ok:
            raise PrlCommandError(result)

        dest = Path(host_path).expanduser().resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)

        total_bytes = 0
        with tarfile.open(fileobj=io.BytesIO(result.stdout_bytes), mode="r") as archive:
            members = archive.getmembers()
            for m in members:
                total_bytes += m.size

            # If extracting a single file and host_path has that file name
            if len(members) == 1 and members[0].name == target_name and not members[0].isdir():
                f = archive.extractfile(members[0])
                if f:
                    dest.write_bytes(f.read())
            else:
                dest.mkdir(parents=True, exist_ok=True)
                if hasattr(tarfile, "data_filter"):
                    archive.extractall(path=dest, filter="data")
                else:
                    archive.extractall(path=dest)

        return FileTransferResult(
            vm=vm,
            uuid=uuid,
            source=guest_path,
            destination=str(dest),
            bytes=total_bytes,
            message=f"Transferred {total_bytes} bytes from guest '{guest_path}' to host '{dest}'",
        )
