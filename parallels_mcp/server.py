"""MCP stdio server for local Parallels Desktop virtual machines."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
import sys

from mcp.server import MCPServer
from mcp_types import ToolAnnotations

from . import __version__
from .config import Settings
from .doctor import run_doctor
from .guest import GuestExecResult, GuestService
from .lifecycle import VmLifecycle, VmOperationResult
from .screen import ScreenCapture, ScreenshotResult
from .snapshots import Snapshot, SnapshotOperationResult, SnapshotService
from .vm import VmService, VmStatus, VmSummary


mcp = MCPServer(
    name="parallels-pro",
    version=__version__,
    description="Operate and automate local Parallels Desktop virtual machines.",
    instructions=(
        "Read-only inspection tools are available alongside power lifecycle, guest "
        "command execution, screen capture, and snapshot management. Mutating operations "
        "require explicit confirmation where indicated."
    ),
)
_vms = VmService()
_guest = GuestService(_vms)
_lifecycle = VmLifecycle(_vms, _guest)
_settings = Settings.from_env()
_screen = ScreenCapture(_vms)
_snapshots = SnapshotService(_vms)

_READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False)
_POWER_CHANGE = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)
_GUEST_COMMAND = ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=True)
_GUEST_READINESS = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False)
_MUTATING_STATE = ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=False)


@mcp.tool(
    title="List Parallels VMs",
    annotations=_READ_ONLY,
)
async def vm_list() -> list[VmSummary]:
    """List every registered Parallels VM with its current power state."""

    return await _vms.list_vms()


@mcp.tool(
    title="Get Parallels VM status",
    annotations=_READ_ONLY,
)
async def vm_status(vm: str) -> VmStatus:
    """Return bounded status details for a VM name or UUID."""

    return await _vms.status(vm)


@mcp.tool(title="Start Parallels VM", annotations=_POWER_CHANGE)
async def vm_start(vm: str) -> VmOperationResult:
    """Start a registered VM by name or UUID."""

    return await _lifecycle.start(vm)


@mcp.tool(
    title="Gracefully stop Parallels VM",
    annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=False),
)
async def vm_stop(vm: str) -> VmOperationResult:
    """Request an ACPI shutdown; this never uses Parallels force-kill."""

    return await _lifecycle.stop(vm)


@mcp.tool(
    title="Suspend Parallels VM",
    annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=False),
)
async def vm_suspend(vm: str) -> VmOperationResult:
    """Suspend a VM, preserving its current guest memory state."""

    return await _lifecycle.suspend(vm)


@mcp.tool(title="Wait for Parallels guest readiness", annotations=_GUEST_READINESS)
async def vm_wait_ready(vm: str, timeout_s: float = 300.0) -> VmOperationResult:
    """Poll the guest OS until Parallels Tools and execution answering."""

    return await _lifecycle.wait_ready(vm, timeout=timeout_s)


@mcp.tool(title="Execute a command in a Parallels guest", annotations=_GUEST_COMMAND)
async def vm_exec(
    vm: str,
    command: list[str],
    user: str | None = None,
    timeout_s: float = 300.0,
) -> GuestExecResult:
    """Execute an explicit argv vector inside the guest.

    Args:
        vm: The VM name or UUID.
        command: Argument vector, e.g. ["whoami"] or ["ls", "-la"].
        user: Optional guest username. If omitted, uses the current desktop user on Windows.
        timeout_s: Execution timeout in seconds (default: 300s).
    """

    return await _guest.execute(vm, command, user=user, timeout=timeout_s)


@mcp.tool(title="Capture Parallels VM screenshot", annotations=_READ_ONLY)
async def vm_screenshot(
    vm: str,
    output_path: str | None = None,
) -> ScreenshotResult:
    """Capture a screenshot of the VM's current screen buffer.

    Args:
        vm: The VM name or UUID.
        output_path: Optional host path where the PNG will be saved.
                     If omitted, saved to the default artifact directory.
    """

    if output_path:
        dest = Path(output_path).expanduser().resolve()
    else:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in vm)
        dest = _settings.artifact_dir / f"screenshot_{safe_name}_{timestamp}.png"

    return await _screen.capture(vm, dest)


@mcp.tool(title="List Parallels snapshots", annotations=_READ_ONLY)
async def snapshot_list(vm: str) -> list[Snapshot]:
    """List snapshots for a VM without changing state."""

    return await _snapshots.list(vm)


@mcp.tool(title="Create Parallels snapshot", annotations=_MUTATING_STATE)
async def snapshot_create(
    vm: str,
    name: str,
    description: str | None = None,
    confirm: bool = False,
) -> SnapshotOperationResult:
    """Create a snapshot of the current VM state after explicit confirmation."""

    if not confirm:
        raise ValueError("snapshot_create changes VM storage; call it with confirm=true")
    return await _snapshots.create(vm, name, description)


@mcp.tool(title="Revert Parallels snapshot", annotations=_MUTATING_STATE)
async def snapshot_revert(vm: str, snapshot: str, confirm: bool = False) -> SnapshotOperationResult:
    """Revert guest state to a snapshot after explicit confirmation."""

    if not confirm:
        raise ValueError("snapshot_revert discards guest changes; call it with confirm=true")
    return await _snapshots.revert(vm, snapshot)


def main() -> None:
    """Run the server over MCP stdio or execute CLI subcommands."""

    if len(sys.argv) > 1 and sys.argv[1].lower() in {"doctor", "check", "--doctor"}:
        code = asyncio.run(run_doctor())
        sys.exit(code)

    mcp.run()


if __name__ == "__main__":
    main()
