"""Snapshot inspection and explicitly confirmed guest-state operations."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, ConfigDict

from .prl import CommandResult, PrlCommandError, run_prlctl, run_prlctl_json
from .vm import VmService


Runner = Callable[..., Awaitable[CommandResult]]
JsonRunner = Callable[..., Awaitable[Any]]


class Snapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    date: str | None = None
    state: str | None = None
    current: bool = False
    parent_id: str | None = None


class SnapshotOperationResult(BaseModel):
    vm: str
    uuid: str
    action: str
    snapshot_id: str | None = None
    message: str


def _clean_id(value: Any) -> str:
    return str(value or "").strip().strip("{}").lower()


def _snapshot_rows(payload: Any) -> list[Snapshot]:
    if not isinstance(payload, dict):
        raise RuntimeError("Parallels returned an unexpected snapshot-list shape")
    rows: list[Snapshot] = []
    for raw_id, raw in payload.items():
        if not isinstance(raw, dict):
            continue
        rows.append(
            Snapshot(
                id=_clean_id(raw_id),
                name=str(raw.get("name", "")),
                date=raw.get("date"),
                state=raw.get("state"),
                current=bool(raw.get("current", False)),
                parent_id=_clean_id(raw.get("parent")) or None,
            )
        )
    return rows


class SnapshotService:
    def __init__(
        self,
        vms: VmService,
        json_runner: JsonRunner = run_prlctl_json,
        runner: Runner = run_prlctl,
    ) -> None:
        self._vms = vms
        self._json_runner = json_runner
        self._runner = runner

    async def list(self, vm: str) -> list[Snapshot]:
        uuid = await self._vms.resolve(vm)
        payload = await self._json_runner("snapshot-list", uuid, "-j", timeout=30.0)
        return _snapshot_rows(payload)

    async def create(self, vm: str, name: str, description: str | None = None) -> SnapshotOperationResult:
        uuid = await self._vms.resolve(vm)
        args = ["snapshot", uuid, "--name", name]
        if description:
            args.extend(["--description", description])
        result = await self._runner(*args, timeout=300.0)
        if not result.ok:
            raise PrlCommandError(result)
        return SnapshotOperationResult(
            vm=vm,
            uuid=uuid,
            action="snapshot_create",
            message=result.stdout.strip() or "snapshot created",
        )

    async def revert(self, vm: str, snapshot: str) -> SnapshotOperationResult:
        uuid = await self._vms.resolve(vm)
        snapshots = await self.list(vm)
        requested_id = _clean_id(snapshot)
        matches = [item for item in snapshots if item.id == requested_id or item.name == snapshot]
        if len(matches) != 1:
            raise RuntimeError(f"Snapshot {snapshot!r} was not uniquely found for VM {vm!r}")
        snapshot_id = matches[0].id
        result = await self._runner("snapshot-switch", uuid, "--id", snapshot_id, timeout=600.0)
        if not result.ok:
            raise PrlCommandError(result)
        return SnapshotOperationResult(
            vm=vm,
            uuid=uuid,
            action="snapshot_revert",
            snapshot_id=snapshot_id,
            message=result.stdout.strip() or "snapshot reverted",
        )
