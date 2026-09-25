"""Power lifecycle and guest readiness operations."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from pydantic import BaseModel, ConfigDict

from .guest import GuestService
from .prl import CommandResult, PrlCommandError, PrlError, PrlTimeoutError, run_prlctl
from .vm import VmService


Runner = Callable[..., Awaitable[CommandResult]]


class VmOperationResult(BaseModel):
    """Result of a successful power operation."""

    model_config = ConfigDict(extra="forbid")

    vm: str
    uuid: str
    action: str
    message: str


class VmLifecycle:
    def __init__(
        self,
        vms: VmService,
        guest: GuestService,
        runner: Runner = run_prlctl,
        *,
        timeout: float = 120.0,
    ) -> None:
        self._vms = vms
        self._guest = guest
        self._runner = runner
        self._timeout = timeout

    async def _power(self, vm: str, action: str, *options: str) -> VmOperationResult:
        uuid = await self._vms.resolve(vm)
        result = await self._runner(action, uuid, *options, timeout=self._timeout)
        if not result.ok:
            raise PrlCommandError(result)
        return VmOperationResult(
            vm=vm,
            uuid=uuid,
            action=action,
            message=result.stdout.strip() or f"{action} completed",
        )

    async def start(self, vm: str) -> VmOperationResult:
        return await self._power(vm, "start")

    async def stop(self, vm: str) -> VmOperationResult:
        return await self._power(vm, "stop", "--acpi")

    async def suspend(self, vm: str) -> VmOperationResult:
        return await self._power(vm, "suspend")

    async def wait_ready(
        self,
        vm: str,
        *,
        timeout: float = 300.0,
        poll_interval: float = 5.0,
    ) -> VmOperationResult:
        if timeout <= 0 or poll_interval <= 0:
            raise ValueError("timeout and poll_interval must be greater than zero")

        loop = asyncio.get_running_loop()
        started = loop.time()
        deadline = started + timeout

        probe_commands: list[list[str]] = []
        try:
            status = await self._vms.status(vm)
            os_name = (status.os or "").lower()
            if "win" in os_name:
                probe_commands = [["cmd", "/c", "echo", "ready"]]
            elif any(k in os_name for k in ("linux", "ubuntu", "debian", "fedora", "centos", "darwin", "macos")):
                probe_commands = [["/bin/sh", "-c", "echo ready"]]
        except Exception:
            pass

        if not probe_commands:
            probe_commands = [
                ["cmd", "/c", "echo", "ready"],
                ["/bin/sh", "-c", "echo ready"],
            ]

        while loop.time() < deadline:
            remaining = deadline - loop.time()
            probe_timeout = min(15.0, remaining)
            for probe_cmd in probe_commands:
                try:
                    result = await self._guest.execute(
                        vm,
                        probe_cmd,
                        timeout=probe_timeout,
                    )
                except PrlError:
                    result = None
                if result and result.ok and result.stdout.strip() == "ready":
                    return VmOperationResult(
                        vm=vm,
                        uuid=result.uuid,
                        action="wait_ready",
                        message=f"Guest answered in {loop.time() - started:.1f}s",
                    )
            await asyncio.sleep(min(poll_interval, max(0.0, deadline - loop.time())))

        raise PrlTimeoutError(f"Guest {vm!r} did not answer within {timeout:.1f}s")
