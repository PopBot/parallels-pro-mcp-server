"""System environment and Parallels Desktop pre-flight verification."""

from __future__ import annotations

import asyncio
import platform
import shutil
import sys
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .guest import GuestService
from .prl import run_argv, run_prlctl, run_prlctl_json


class DoctorCheck(BaseModel):
    """Result of a single pre-flight diagnostic check."""

    model_config = ConfigDict(extra="forbid")

    name: str
    status: str  # PASS, WARN, FAIL
    detail: str


class DoctorReport(BaseModel):
    """Aggregate health and readiness report for host and optional guest VM."""

    model_config = ConfigDict(extra="forbid")

    all_ok: bool
    host_checks: list[DoctorCheck]
    guest_checks: list[DoctorCheck] = Field(default_factory=list)


async def check_host() -> list[DoctorCheck]:
    """Execute host-level pre-flight diagnostics."""
    checks: list[DoctorCheck] = []

    # 1. Host OS Check
    system = platform.system()
    mac_ver = platform.mac_ver()[0] or "unknown"
    if system == "Darwin":
        checks.append(DoctorCheck(name="Host OS", status="PASS", detail=f"macOS {mac_ver} ({platform.machine()})"))
    else:
        checks.append(DoctorCheck(name="Host OS", status="FAIL", detail=f"{system}. Parallels Desktop runs on macOS."))

    # 2. Python Version Check
    py_ver = sys.version_info
    py_str = f"{py_ver.major}.{py_ver.minor}.{py_ver.micro}"
    if py_ver >= (3, 10):
        checks.append(DoctorCheck(name="Python Version", status="PASS", detail=f"{py_str} (>= 3.10 required)"))
    else:
        checks.append(DoctorCheck(name="Python Version", status="FAIL", detail=f"{py_str}. Please use Python >= 3.10."))

    # 3. prlctl CLI Check
    prlctl_path = shutil.which("prlctl") or "/usr/local/bin/prlctl"
    prlctl_found = shutil.which(prlctl_path) is not None
    if prlctl_found:
        try:
            ver_res = await run_argv(prlctl_path, "--version", timeout=10.0)
            ver_text = ver_res.stdout.strip() or "version unknown"
            checks.append(DoctorCheck(name="Parallels CLI", status="PASS", detail=f"Found '{prlctl_path}' ({ver_text})"))
        except Exception as exc:
            checks.append(DoctorCheck(name="Parallels CLI", status="WARN", detail=f"Execution error on '{prlctl_path}': {exc}"))
    else:
        checks.append(DoctorCheck(name="Parallels CLI", status="FAIL", detail="'prlctl' not found. Ensure Parallels Desktop is installed."))

    # 4. Parallels License / Edition Check
    try:
        lic_res = await run_argv("prlsrvctl", "info", "--license", timeout=10.0)
        lic_out = lic_res.stdout.lower()
        if "pro" in lic_out or "business" in lic_out:
            checks.append(DoctorCheck(name="Parallels License", status="PASS", detail="Pro/Business Edition active (supports prlctl exec)."))
        else:
            checks.append(DoctorCheck(name="Parallels License", status="WARN", detail="Could not confirm Pro/Business edition. Standard edition does not support 'exec'."))
    except Exception as exc:
        checks.append(DoctorCheck(name="Parallels License", status="WARN", detail=f"Could not query license: {exc}"))

    # 5. VM Discovery Check
    try:
        vms = await run_prlctl_json("list", "-a", "-j", timeout=15.0)
        if isinstance(vms, list):
            count = len(vms)
            vms_desc = ", ".join(f"{v.get('name', 'unnamed')} ({v.get('status', 'unknown')})" for v in vms[:5])
            checks.append(DoctorCheck(name="Virtual Machines", status="PASS", detail=f"{count} VMs found: {vms_desc}"))
        else:
            checks.append(DoctorCheck(name="Virtual Machines", status="WARN", detail="Unexpected VM list format from Parallels."))
    except Exception as exc:
        checks.append(DoctorCheck(name="Virtual Machines", status="FAIL", detail=f"Failed listing VMs: {exc}"))

    return checks


async def check_guest(guest: GuestService, vm_name: str) -> list[DoctorCheck]:
    """Execute guest-level diagnostics inside a specific Parallels VM."""
    checks: list[DoctorCheck] = []
    is_win = await guest.vms.is_windows(vm_name)

    # Helper for running guest command safely
    async def _exec(cmd: list[str]) -> tuple[bool, str]:
        if is_win:
            full_cmd = ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", " ".join(cmd)]
        else:
            full_cmd = list(cmd)
        try:
            res = await guest.execute(vm_name, full_cmd, timeout=15.0)
            out = (res.stdout or res.stderr or "").strip()
            return res.ok, out
        except Exception as exc:
            return False, str(exc)

    # 1. OS & Kernel Check
    if is_win:
        ok, out = await _exec(["Write-Output", "(Get-CimInstance Win32_OperatingSystem).Caption"])
        checks.append(DoctorCheck(name="Guest OS", status="PASS" if ok else "WARN", detail=f"Windows ({out or 'unknown'})"))
    else:
        ok, out = await _exec(["uname", "-srm"])
        checks.append(DoctorCheck(name="Guest OS", status="PASS" if ok else "WARN", detail=f"Linux ({out or 'unknown'})"))

    # 2. Python Version Check
    ok, out = await _exec(["python3", "--version"] if not is_win else ["python.exe", "--version"])
    if ok and out:
        checks.append(DoctorCheck(name="Python Runtime", status="PASS", detail=out))
    else:
        checks.append(DoctorCheck(name="Python Runtime", status="WARN", detail="python not found in guest PATH"))

    # 3. Node.js Version Check
    ok, out = await _exec(["node", "-v"])
    if ok and out.startswith("v"):
        checks.append(DoctorCheck(name="Node.js Runtime", status="PASS", detail=out))
    else:
        checks.append(DoctorCheck(name="Node.js Runtime", status="WARN", detail="node not found in guest PATH"))

    # 4. Git CLI Check
    ok, out = await _exec(["git", "--version"])
    if ok:
        checks.append(DoctorCheck(name="Git CLI", status="PASS", detail=out))
    else:
        checks.append(DoctorCheck(name="Git CLI", status="WARN", detail="git not found in guest"))

    # 5. OS-Specific checks
    if is_win:
        # Check ExecutionPolicy
        ok, out = await _exec(["Get-ExecutionPolicy"])
        if ok and ("bypass" in out.lower() or "unrestricted" in out.lower()):
            checks.append(DoctorCheck(name="PowerShell ExecutionPolicy", status="PASS", detail=f"ExecutionPolicy: {out}"))
        else:
            checks.append(DoctorCheck(name="PowerShell ExecutionPolicy", status="WARN", detail=f"ExecutionPolicy is '{out}'. Run 'vm_optimize_windows' to set Bypass."))

        # Check Defender Exclusions
        ok, out = await _exec(["(Get-MpPreference).ExclusionPath"])
        if ok and out:
            checks.append(DoctorCheck(name="Windows Defender Exclusions", status="PASS", detail="Defender path exclusions configured."))
        else:
            checks.append(DoctorCheck(name="Windows Defender Exclusions", status="WARN", detail="No Defender exclusions found. Consider 'vm_optimize_windows' to prevent file locking."))
    else:
        # Linux glibc check
        ok, out = await _exec(["ldd", "--version"])
        first_line = out.splitlines()[0] if out else "unknown"
        checks.append(DoctorCheck(name="Linux C Library", status="PASS" if ok else "WARN", detail=first_line))

        # Check build-essential / gcc
        ok, out = await _exec(["gcc", "--version"])
        if ok:
            gcc_ver = out.splitlines()[0] if out else "installed"
            checks.append(DoctorCheck(name="Build Tools (gcc)", status="PASS", detail=gcc_ver))
        else:
            checks.append(DoctorCheck(name="Build Tools (gcc)", status="WARN", detail="gcc not found; required for native builds"))

    return checks


async def run_doctor_report(guest: GuestService | None = None, vm: str | None = None) -> DoctorReport:
    """Run full diagnostic checks returning a structured DoctorReport."""
    host_checks = await check_host()
    guest_checks: list[DoctorCheck] = []

    if guest and vm:
        try:
            guest_checks = await check_guest(guest, vm)
        except Exception as exc:
            guest_checks.append(DoctorCheck(name="Guest Diagnostics", status="FAIL", detail=f"Error inspecting guest: {exc}"))

    has_fail = any(c.status == "FAIL" for c in host_checks + guest_checks)
    return DoctorReport(
        all_ok=not has_fail,
        host_checks=host_checks,
        guest_checks=guest_checks,
    )


async def run_doctor() -> int:
    """Run diagnostic checks on the host environment and Parallels setup for CLI."""
    report = await run_doctor_report()

    print("Parallels Pro MCP Server — Diagnostic Doctor")
    print("=" * 50)
    for c in report.host_checks:
        print(f" [{c.status}] {c.name}: {c.detail}")
    print("=" * 50)
    if report.all_ok:
        print("Status: READY - All essential checks passed.")
        return 0
    else:
        print("Status: ATTENTION - Some pre-flight checks failed. Review details above.")
        return 1
