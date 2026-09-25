"""System environment and Parallels Desktop pre-flight verification."""

from __future__ import annotations

import asyncio
import platform
import shutil
import sys
from typing import Any

from .prl import run_argv, run_prlctl, run_prlctl_json


async def run_doctor() -> int:
    """Run diagnostic checks on the host environment and Parallels setup."""

    print("Parallels Pro MCP Server — Diagnostic Doctor")
    print("=" * 50)
    all_ok = True

    # 1. Host OS Check
    system = platform.system()
    mac_ver = platform.mac_ver()[0] or "unknown"
    if system == "Darwin":
        print(f" [PASS] Host OS: macOS {mac_ver} ({platform.machine()})")
    else:
        print(f" [FAIL] Host OS: {system}. Parallels Desktop runs exclusively on macOS.")
        all_ok = False

    # 2. Python Version Check
    py_ver = sys.version_info
    py_str = f"{py_ver.major}.{py_ver.minor}.{py_ver.micro}"
    if py_ver >= (3, 10):
        print(f" [PASS] Python Version: {py_str} (>= 3.10 required)")
    else:
        print(f" [FAIL] Python Version: {py_str}. Please use Python 3.10 or newer.")
        all_ok = False

    # 3. prlctl CLI Check
    prlctl_path = shutil.which("prlctl") or "/usr/local/bin/prlctl"
    prlctl_found = shutil.which(prlctl_path) is not None
    if prlctl_found:
        try:
            ver_res = await run_argv(prlctl_path, "--version", timeout=10.0)
            ver_text = ver_res.stdout.strip() or "version unknown"
            print(f" [PASS] Parallels CLI: Found '{prlctl_path}' ({ver_text})")
        except Exception as exc:
            print(f" [WARN] Parallels CLI: Found '{prlctl_path}' but execution returned error: {exc}")
    else:
        print(f" [FAIL] Parallels CLI: 'prlctl' not found in PATH or at /usr/local/bin/prlctl.")
        print("        Ensure Parallels Desktop is installed.")
        all_ok = False

    # 4. Parallels License / Edition Check
    try:
        lic_res = await run_argv("prlsrvctl", "info", "--license", timeout=10.0)
        lic_out = lic_res.stdout.lower()
        if "pro" in lic_out or "business" in lic_out:
            print(f" [PASS] Parallels License: Pro/Business Edition detected.")
        else:
            print(f" [WARN] Parallels License: Could not confirm Pro/Business edition.")
            print("        Standard edition does not support 'prlctl exec' command execution.")
    except Exception as exc:
        print(f" [WARN] Parallels License: Could not query prlsrvctl ({exc}).")

    # 5. VM Discovery Check
    try:
        vms = await run_prlctl_json("list", "-a", "-j", timeout=15.0)
        if isinstance(vms, list):
            count = len(vms)
            print(f" [PASS] Registered Virtual Machines: {count} found.")
            for vm in vms:
                name = vm.get("name") or vm.get("Name") or "unnamed"
                state = vm.get("status") or vm.get("State") or "unknown"
                os_name = vm.get("os") or vm.get("OS") or "unknown"
                print(f"        - {name} (State: {state}, OS: {os_name})")
        else:
            print(" [WARN] Parallels returned unexpected VM list format.")
    except Exception as exc:
        print(f" [FAIL] Could not query Parallels VMs: {exc}")
        print("        Ensure Parallels Desktop is running and permission is granted.")
        all_ok = False

    print("=" * 50)
    if all_ok:
        print("Status: READY - All essential checks passed.")
        return 0
    else:
        print("Status: ATTENTION - Some pre-flight checks failed. Review details above.")
        return 1
