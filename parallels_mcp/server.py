"""MCP stdio server for local Parallels Desktop virtual machines."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import sys

from mcp.server import MCPServer
from mcp_types import ToolAnnotations

from . import __version__
from .config import Settings
from .doctor import DoctorReport, run_doctor, run_doctor_report
from .guest import GuestExecResult, GuestService
from .input import InputService, KeyEventResult
from .lifecycle import VmLifecycle, VmOperationResult
from .manage import (
    CloneResult,
    DeleteResult,
    HeadlessResult,
    NetworkConditionResult,
    VmManagementService,
    WindowsOptimizationResult,
)
from .screen import ScreenCapture, ScreenshotResult
from .sharing import SharedFolderResult, SharingService
from .snapshots import Snapshot, SnapshotOperationResult, SnapshotService
from .transfer import FileTransferResult, FileTransferService
from .vm import VmService, VmStatus, VmSummary


mcp = MCPServer(
    name="parallels-pro",
    version=__version__,
    description="Operate and automate local Parallels Desktop virtual machines.",
    instructions=(
        "Read-only inspection tools are available alongside power lifecycle, guest "
        "command execution, file transfer, shared folders, screen capture, keyboard simulation, and snapshot management. "
        "Mutating operations require explicit confirmation where indicated."
    ),
)
_vms = VmService()
_guest = GuestService(_vms)
_lifecycle = VmLifecycle(_vms, _guest)
_settings = Settings.from_env()
_screen = ScreenCapture(_vms)
_input = InputService(_vms)
_snapshots = SnapshotService(_vms)
_sharing = SharingService(_vms)
_transfer = FileTransferService(_vms, _guest)
_manage = VmManagementService(_vms)

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


@mcp.tool(title="Send keystrokes to Parallels VM", annotations=_GUEST_COMMAND)
async def vm_send_keys(
    vm: str,
    keys: list[str] | str,
    delay_ms: int = 50,
) -> KeyEventResult:
    """Send synthetic keystrokes or hotkey combinations to a running VM.

    Supports:
    - Single keys: "enter", "esc", "tab", "space", "backspace", "delete", "f1"-"f12", arrows, etc.
    - Key chords: "ctrl+alt+del", "win+r", "alt+f4", "ctrl+c", "ctrl+shift+esc", etc.
    - Strings to type: "notepad.exe" or "echo Hello"
    - Multiple key entries in sequence: ["win+r", "notepad.exe", "enter"]

    Args:
        vm: The VM name or UUID.
        keys: Key name, chord string (e.g. "ctrl+alt+del"), or list of keys to send in order.
        delay_ms: Delay in milliseconds between key events (default: 50ms).
    """

    return await _input.send_keys(vm, keys, delay_ms=delay_ms)


@mcp.tool(title="Copy file or directory from host to Parallels guest", annotations=_GUEST_COMMAND)
async def vm_copy_to_guest(
    vm: str,
    host_path: str,
    guest_path: str,
    user: str | None = None,
    timeout_s: float = 300.0,
) -> FileTransferResult:
    """Stream a file or entire directory from the host into a guest path.

    Works across Windows, Linux, and macOS guests using direct stream execution.
    Creates parent directories in the guest if they do not exist.

    Args:
        vm: The VM name or UUID.
        host_path: Path on the host filesystem (file or directory).
        guest_path: Destination path inside the guest (e.g. "C:\\temp\\file.txt" or "/tmp/dir").
        user: Optional guest user to run file extraction as.
        timeout_s: Transfer timeout in seconds (default: 300s).
    """

    return await _transfer.copy_to_guest(vm, host_path, guest_path, user=user, timeout=timeout_s)


@mcp.tool(title="Copy file or directory from Parallels guest to host", annotations=_GUEST_COMMAND)
async def vm_copy_from_guest(
    vm: str,
    guest_path: str,
    host_path: str,
    user: str | None = None,
    timeout_s: float = 300.0,
) -> FileTransferResult:
    """Stream a file or directory from a guest path back to the host filesystem.

    Extracts test reports, build artifacts, logs, or files produced inside the VM.

    Args:
        vm: The VM name or UUID.
        guest_path: Path to the file or directory inside the guest.
        host_path: Destination path on the host where file/folder will be written.
        user: Optional guest user to read files as.
        timeout_s: Transfer timeout in seconds (default: 300s).
    """

    return await _transfer.copy_from_guest(vm, guest_path, host_path, user=user, timeout=timeout_s)


@mcp.tool(title="Share a host directory with Parallels VM", annotations=_MUTATING_STATE)
async def vm_share_folder(
    vm: str,
    name: str,
    host_path: str,
    mode: str = "rw",
    description: str | None = None,
) -> SharedFolderResult:
    """Mount a host directory into the guest as a Parallels Shared Folder.

    Args:
        vm: The VM name or UUID.
        name: Name of the share (e.g. "project_workspace").
        host_path: Host directory to mount.
        mode: Sharing mode: "ro" (read-only) or "rw" (read-write). Default is "rw".
        description: Optional notes describing the shared folder.
    """

    return await _sharing.share_folder(vm, name, host_path, mode=mode, description=description)


@mcp.tool(title="Unshare a host directory from Parallels VM", annotations=_MUTATING_STATE)
async def vm_unshare_folder(
    vm: str,
    name: str,
) -> SharedFolderResult:
    """Unmount and remove a previously shared folder from the VM.

    Args:
        vm: The VM name or UUID.
        name: Name of the share to delete.
    """

    return await _sharing.unshare_folder(vm, name)


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


@mcp.tool(title="Delete Parallels snapshot", annotations=_MUTATING_STATE)
async def snapshot_delete(
    vm: str,
    snapshot: str,
    delete_children: bool = False,
    confirm: bool = False,
) -> SnapshotOperationResult:
    """Permanently delete a snapshot to free host disk space.

    Args:
        vm: The VM name or UUID.
        snapshot: Snapshot name or UUID to delete.
        delete_children: If true, also delete child snapshots descended from this one.
        confirm: Must be explicitly set to true.
    """

    if not confirm:
        raise ValueError("snapshot_delete permanently deletes snapshot storage; call it with confirm=true")
    return await _snapshots.delete(vm, snapshot, delete_children=delete_children)


@mcp.tool(title="Clone Parallels VM", annotations=_MUTATING_STATE)
async def vm_clone(
    vm: str,
    name: str,
    linked: bool = True,
    dst: str | None = None,
) -> CloneResult:
    """Clone an existing VM to quickly spin up sandboxes or disposable test environments.

    Args:
        vm: The source VM name or UUID to clone.
        name: Name for the newly created clone.
        linked: If true (default), creates a fast linked clone sharing the base disk. If false, creates a full independent deep clone.
        dst: Optional custom destination path for the cloned VM.
    """
    return await _manage.clone(vm, name, linked=linked, dst=dst)


@mcp.tool(title="Delete Parallels VM", annotations=_MUTATING_STATE)
async def vm_delete(
    vm: str,
    confirm: bool = False,
) -> DeleteResult:
    """Permanently delete a VM and all its associated disk images from host storage.

    Args:
        vm: The VM name or UUID to delete.
        confirm: Must be explicitly set to true to prevent accidental VM deletion.
    """
    if not confirm:
        raise ValueError("vm_delete permanently destroys the VM and its disks; call it with confirm=true")
    return await _manage.delete(vm, confirm=confirm)


@mcp.tool(title="Set Parallels VM headless mode", annotations=_MUTATING_STATE)
async def vm_set_headless(
    vm: str,
    enabled: bool = True,
) -> HeadlessResult:
    """Configure whether the VM runs headlessly in the background or displays a GUI window.

    Args:
        vm: The VM name or UUID.
        enabled: If true (default), sets startup-view to headless. If false, sets startup-view to window.
    """
    return await _manage.set_headless(vm, enabled=enabled)


@mcp.tool(title="Set Parallels network condition", annotations=_MUTATING_STATE)
async def vm_set_network_condition(
    vm: str,
    profile: str = "off",
) -> NetworkConditionResult:
    """Simulate degraded network conditions or offline state for the VM.

    Args:
        vm: The VM name or UUID.
        profile: Network profile name ('off', 'edge', 'dsl', '3g', '100-percent-loss', 'very-bad-net', 'wifi').
                 Use 'off' to disable simulation and restore normal network conditions.
    """
    return await _manage.set_network_condition(vm, profile=profile)


@mcp.tool(title="Run Parallels pre-flight doctor diagnostics", annotations=_READ_ONLY)
async def vm_doctor(vm: str | None = None) -> DoctorReport:
    """Run diagnostic pre-flight checks on host macOS and Parallels setup, with optional guest inspection.

    Args:
        vm: Optional VM name or UUID. If specified, checks guest OS, runtimes, and environment.
    """
    return await run_doctor_report(guest=_guest, vm=vm)


@mcp.tool(title="Optimize Windows VM for automation", annotations=_MUTATING_STATE)
async def vm_optimize_windows(
    vm: str,
    exclusion_paths: list[str] | None = None,
    exclusion_processes: list[str] | None = None,
) -> WindowsOptimizationResult:
    """Optimize a Windows guest VM for automated tasks, testing, and script execution.

    Configures Windows Defender real-time scanning exclusions (preventing EPERM/EBUSY file locks)
    and sets PowerShell ExecutionPolicy to Bypass.

    Args:
        vm: The Windows VM name or UUID.
        exclusion_paths: Optional directory paths to exclude from Defender scanning.
        exclusion_processes: Optional process binary names to exclude (defaults to node.exe, npm.cmd, pnpm.cmd, git.exe, python.exe).
    """
    return await _manage.optimize_windows(
        vm,
        exclusion_paths=exclusion_paths,
        exclusion_processes=exclusion_processes,
    )


@mcp.tool(title="Get Parallels MCP server changelog and release notes", annotations=_READ_ONLY)
async def vm_changelog(latest_only: bool = False) -> str:
    """Read the release notes, new features, and bug fixes for parallels-pro-mcp-server.

    Args:
        latest_only: If true, returns only the latest release section. If false, returns the complete changelog.
    """
    changelog_path = Path(__file__).resolve().parent.parent / "CHANGELOG.md"
    if not changelog_path.is_file():
        return "# Changelog\n\nNo CHANGELOG.md found."
    content = changelog_path.read_text(encoding="utf-8")
    if not latest_only:
        return content
    parts = content.split("\n## ")
    if len(parts) >= 2:
        return "## " + parts[1].strip()
    return content


@mcp.resource(
    "parallels://changelog",
    name="changelog",
    title="Parallels MCP Server Changelog & Release Notes",
    description="The complete changelog, recent updates, bug fixes, and release history for parallels-pro-mcp-server.",
    mime_type="text/markdown",
)
def get_changelog() -> str:
    """Resource returning the complete changelog markdown."""
    changelog_path = Path(__file__).resolve().parent.parent / "CHANGELOG.md"
    if changelog_path.is_file():
        return changelog_path.read_text(encoding="utf-8")
    return "# Changelog\n\nNo CHANGELOG.md found."


def main() -> None:
    """Run the server over MCP stdio or execute CLI subcommands."""

    if len(sys.argv) > 1 and sys.argv[1].lower() in {"--version", "-v", "version"}:
        print(f"parallels-pro-mcp {__version__}")
        sys.exit(0)

    if len(sys.argv) > 1 and sys.argv[1].lower() in {"changelog", "notes", "--changelog"}:
        changelog_path = Path(__file__).resolve().parent.parent / "CHANGELOG.md"
        if changelog_path.is_file():
            print(changelog_path.read_text(encoding="utf-8"))
        else:
            print("No CHANGELOG.md found.")
        sys.exit(0)

    if len(sys.argv) > 1 and sys.argv[1].lower() in {"doctor", "check", "--doctor"}:
        code = asyncio.run(run_doctor())
        sys.exit(code)

    debug_mode = os.getenv("PARALLELS_MCP_DEBUG", "1").lower() in {"1", "true", "yes", "debug"}
    if debug_mode:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            stream=sys.stderr,
        )
        logger = logging.getLogger("parallels_mcp")
        logger.setLevel(logging.DEBUG)
        logger.debug("Starting parallels-pro-mcp with DEBUG logging enabled")

    mcp.run()


if __name__ == "__main__":
    main()
