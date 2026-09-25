"""VM instance lifecycle and hardware profile management."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from .prl import CommandResult, PrlCommandError, run_prlctl
from .vm import VmService

Runner = Callable[..., Awaitable[CommandResult]]

KNOWN_NETWORK_PROFILES = {
    "off",
    "edge",
    "dsl",
    "3g",
    "100-percent-loss",
    "very-bad-net",
    "wifi",
}


class CloneResult(BaseModel):
    """Result of cloning a VM."""

    model_config = ConfigDict(extra="forbid")

    source_vm: str
    source_uuid: str
    name: str
    linked: bool
    message: str


class DeleteResult(BaseModel):
    """Result of deleting a VM."""

    model_config = ConfigDict(extra="forbid")

    vm: str
    uuid: str
    deleted: bool
    message: str


class HeadlessResult(BaseModel):
    """Result of setting headless startup view."""

    model_config = ConfigDict(extra="forbid")

    vm: str
    uuid: str
    headless: bool
    message: str


class NetworkConditionResult(BaseModel):
    """Result of configuring network conditioning."""

    model_config = ConfigDict(extra="forbid")

    vm: str
    uuid: str
    enabled: bool
    profile: str
    message: str


class WindowsOptimizationResult(BaseModel):
    """Result of optimizing Windows guest VM for testing and automation."""

    model_config = ConfigDict(extra="forbid")

    vm: str
    uuid: str
    defender_exclusions_added: list[str]
    process_exclusions_added: list[str]
    execution_policy: str
    message: str


class VmManagementService:
    """Handles VM cloning, deletion, and advanced hardware/profile configurations."""

    def __init__(self, vms: VmService, runner: Runner = run_prlctl) -> None:
        self._vms = vms
        self._runner = runner

    async def clone(
        self,
        vm: str,
        name: str,
        *,
        linked: bool = True,
        dst: str | Path | None = None,
        timeout: float = 300.0,
    ) -> CloneResult:
        """Clone an existing VM (linked or full clone)."""
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Clone VM name must not be empty.")

        all_vms = await self._vms.list_vms()
        if any(v.name.lower() == clean_name.lower() for v in all_vms):
            raise ValueError(f"A virtual machine named '{clean_name}' already exists.")

        uuid = await self._vms.resolve(vm)
        args: list[str] = ["clone", uuid, "--name", clean_name]
        if linked:
            args.append("--linked")
        if dst:
            args.extend(["--dst", str(Path(dst).resolve())])

        result = await self._runner(*args, timeout=timeout)
        if not result.ok:
            raise PrlCommandError(result)

        return CloneResult(
            source_vm=vm,
            source_uuid=uuid,
            name=clean_name,
            linked=linked,
            message=result.stdout.strip() or f"Successfully cloned '{vm}' to '{clean_name}'.",
        )

    async def delete(
        self,
        vm: str,
        *,
        confirm: bool = False,
        timeout: float = 120.0,
    ) -> DeleteResult:
        """Permanently delete a VM from disk."""
        if not confirm:
            raise ValueError(
                f"Deleting virtual machine '{vm}' is permanent and cannot be undone. "
                "You must pass confirm=True to confirm deletion."
            )

        uuid = await self._vms.resolve(vm)
        status = await self._vms.status(uuid)
        if status.status.lower() == "running":
            raise RuntimeError(
                f"Cannot delete VM '{vm}' while it is running. Stop or suspend it first."
            )

        result = await self._runner("delete", uuid, timeout=timeout)
        if not result.ok:
            raise PrlCommandError(result)

        return DeleteResult(
            vm=vm,
            uuid=uuid,
            deleted=True,
            message=result.stdout.strip() or f"Successfully deleted VM '{vm}'.",
        )

    async def set_headless(
        self,
        vm: str,
        enabled: bool = True,
        *,
        timeout: float = 60.0,
    ) -> HeadlessResult:
        """Configure whether a VM starts in headless mode or as a window."""
        uuid = await self._vms.resolve(vm)
        view_mode = "headless" if enabled else "window"
        result = await self._runner("set", uuid, "--startup-view", view_mode, timeout=timeout)
        if not result.ok:
            raise PrlCommandError(result)

        return HeadlessResult(
            vm=vm,
            uuid=uuid,
            headless=enabled,
            message=result.stdout.strip() or f"Set startup-view to '{view_mode}' for '{vm}'.",
        )

    async def set_network_condition(
        self,
        vm: str,
        profile: str = "off",
        *,
        timeout: float = 60.0,
    ) -> NetworkConditionResult:
        """Simulate degraded or throttled network profiles (edge, 3g, wifi, 100-percent-loss, off)."""
        uuid = await self._vms.resolve(vm)
        norm = profile.strip().lower()

        if norm in ("off", "none", "disable", "disabled"):
            result = await self._runner("set", uuid, "--network-conditioner", "off", timeout=timeout)
            enabled = False
            applied_profile = "off"
        else:
            result = await self._runner(
                "set",
                uuid,
                "--network-conditioner",
                "on",
                "--network-conditioner-profile",
                norm,
                timeout=timeout,
            )
            enabled = True
            applied_profile = norm

        if not result.ok:
            raise PrlCommandError(result)

        return NetworkConditionResult(
            vm=vm,
            uuid=uuid,
            enabled=enabled,
            profile=applied_profile,
            message=result.stdout.strip() or f"Set network conditioner to '{applied_profile}' for '{vm}'.",
        )

    async def optimize_windows(
        self,
        vm: str,
        exclusion_paths: list[str] | None = None,
        exclusion_processes: list[str] | None = None,
        *,
        timeout: float = 60.0,
    ) -> WindowsOptimizationResult:
        """Optimize Windows guest VM by setting Defender exclusions and execution policy."""
        uuid = await self._vms.resolve(vm)
        paths = exclusion_paths or [r"C:\Windows\Temp", r"$env:TEMP"]
        processes = exclusion_processes or ["node.exe", "npm.cmd", "pnpm.cmd", "git.exe", "python.exe"]

        path_args = ", ".join(f"'{p}'" for p in paths)
        proc_args = ", ".join(f"'{p}'" for p in processes)

        script = (
            f"Add-MpPreference -ExclusionPath {path_args} -ErrorAction SilentlyContinue; "
            f"Add-MpPreference -ExclusionProcess {proc_args} -ErrorAction SilentlyContinue; "
            "Set-ExecutionPolicy -Scope LocalMachine -ExecutionPolicy Bypass -Force -ErrorAction SilentlyContinue; "
            "(Get-ExecutionPolicy)"
        )

        result = await self._runner(
            "exec",
            uuid,
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
            timeout=timeout,
        )
        if not result.ok:
            raise PrlCommandError(result)

        exec_policy = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "Bypass"

        return WindowsOptimizationResult(
            vm=vm,
            uuid=uuid,
            defender_exclusions_added=paths,
            process_exclusions_added=processes,
            execution_policy=exec_policy,
            message=f"Windows VM '{vm}' optimized: Defender exclusions and ExecutionPolicy '{exec_policy}' applied.",
        )
