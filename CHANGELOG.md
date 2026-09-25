# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

---

## [0.3.0] - 2026-09-25

### Added
- **`vm_doctor` MCP Tool**: Registered diagnostic health check returning structured `DoctorReport` and `DoctorCheck` objects inspecting the macOS host, Parallels Pro license, VM registrations, and guest operating system environment.
- **`vm_optimize_windows` MCP Tool**: Automated optimization for Windows VMs, configuring Windows Defender real-time scanning exclusions (preventing `EPERM` / `EBUSY` / `STATUS_SHARING_VIOLATION` file locks) and setting PowerShell `ExecutionPolicy Bypass`.
- **`parallels://changelog` MCP Resource**: Exposes the changelog directly to connected LLM agents (Claude Desktop, Cursor, Antigravity) over MCP stdio.
- **CLI `changelog` Subcommand**: Added `parallels-pro-mcp changelog` to view release notes directly from the terminal.
- **Dynamic Guest OS Detection**: Added `VmService.is_windows(vm)` using name heuristics, cached inventory, and `prlctl status --json` OS strings.
- **`PARALLELS_MCP_DEBUG` Stderr Logging**: Detailed command execution and millisecond timing logs (`Executing: ...`, `Finished in 0.320s`) streamed safely to `stderr` without interfering with JSON-RPC stdio.

### Changed
- **Multi-OS Shared Paths**: Enhanced `to_guest_path` to support both Windows UNC paths (`\\Mac\Home\...`) and Linux mount paths (`/media/psf/Home/...`) based on target guest OS.
- **Pre-flight Architecture**: Refactored `doctor.py` from CLI-only stdout prints into modular `check_host()` and `check_guest()` functions returning structured Pydantic models.

### Fixed
- **Windows `prlctl exec` Invalid Argument**: Fixed command failures on Windows VMs caused by Parallels rejecting `--current-user` with `PrlJob_GetRetCode: Invalid argument` (return code 1). Windows commands now run reliably under `NT AUTHORITY\SYSTEM`.
- **Transient Dispatch Retries**: Added automatic retry resilience in `GuestService.execute` for intermittent Parallels communication glitches (`failed to connect to parallels tools`, `the virtual machine is not ready`, `prl_err_disp_connection_lost`, `server is busy`, return code 45/137).
- **Linux Headless Session Fallback**: Added automatic fallback to `--user root` on Linux guests when `--current-user` fails because no interactive graphical desktop session is logged in.

---

## [0.2.0] - 2026-09-24

### Added
- **File Transfer Tools**: Added `vm_copy_to_guest` and `vm_copy_from_guest` using tar-over-prlctl-exec streams.
- **Shared Folder Tools**: Added `vm_share_folder` and `vm_unshare_folder` managing Parallels host-guest folder mounts.
- **Advanced VM Management**: Added `vm_clone`, `vm_delete`, `vm_set_headless`, and `vm_set_network_condition`.
- **Snapshot Deletion**: Added `snapshot_delete` for pruning saved states.
- **Input Simulation**: Added `vm_send_keys` simulating keystrokes via `prlctl send-key-event`.
- **CLI `--version` Flag**: Added `--version` / `-V` CLI flag printing package version.
- **Smithery Registry Support**: Added `smithery.yaml` configuration for automated MCP registry discovery.
- **Automated PyPI Publishing**: Added GitHub Actions workflow using OpenID Connect (OIDC) Trusted Publishing.

---

## [0.1.0] - 2026-08-15

### Added
- Initial release of Parallels Pro MCP Server.
- Read-only VM inspection (`vm_list`, `vm_status`).
- Power lifecycle management (`vm_start`, `vm_stop`, `vm_suspend`, `vm_wait_ready`).
- Command execution (`vm_exec`).
- Screen capture (`vm_screenshot`).
- Snapshot management (`snapshot_list`, `snapshot_create`, `snapshot_revert`).
- Pre-flight diagnostic CLI command (`parallels-pro-mcp doctor`).
