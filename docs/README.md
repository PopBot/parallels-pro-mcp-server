# Parallels Pro MCP Server — Operator Guide

This document is the comprehensive runbook for installing, configuring, operating, and troubleshooting the **Parallels Pro MCP Server**.

The server bridges a macOS installation of Parallels Desktop with Model Context Protocol (MCP) clients (such as Claude Desktop, ChatGPT Codex, Cursor, and custom agent workflows) over standard input/output (`stdio`).

---

## Contents

- [Mental Model & Architecture](#mental-model--architecture)
- [Prerequisites & Verification](#prerequisites--verification)
- [Installation & Launching](#installation--launching)
- [Tool Reference](#tool-reference)
  - [vm_list](#vm_list)
  - [vm_status](#vm_status)
  - [vm_start](#vm_start)
  - [vm_stop](#vm_stop)
  - [vm_suspend](#vm_suspend)
  - [vm_wait_ready](#vm_wait_ready)
  - [vm_exec](#vm_exec)
  - [vm_screenshot](#vm_screenshot)
  - [snapshot_list](#snapshot_list)
  - [snapshot_create](#snapshot_create)
  - [snapshot_revert](#snapshot_revert)
- [Pre-flight Diagnostics (`doctor`)](#pre-flight-diagnostics-doctor)
- [Troubleshooting](#troubleshooting)
- [Security & Isolation](#security--isolation)

---

## Mental Model & Architecture

1. **Subprocess Boundary**: The MCP server never uses shell string execution on macOS. All commands issued to `prlctl` or `prlsrvctl` use explicit argument vectors (`argv`), preventing shell injection.
2. **Native JSON Reads**: Parallels Desktop CLI (`prlctl`) supports `-j` for structured JSON output across VM queries and snapshot lists. The server parses this structured data directly without brittle text scraping.
3. **OS-Agnostic Execution**: Works with Windows, Linux (Ubuntu, Debian, Fedora, CentOS, Kali, NixOS), and macOS guest VMs.
4. **Safety Confirmation**: Destructive or irreversible state changes (such as creating or reverting snapshots) require explicit `confirm: true` from the calling agent.

---

## Prerequisites & Verification

1. **macOS**: Host machine must be running macOS on Apple Silicon or Intel.
2. **Parallels Desktop Edition**: Pro or Business edition is required. Parallels Standard edition restricts the command-line interface and does not include `prlctl exec`.
3. **Parallels Tools**: Installed and active in the guest virtual machine.
4. **Python**: Python 3.10 or newer.

Run the pre-flight verification doctor:
```bash
./scripts/doctor.sh
# or
uv run parallels-pro-mcp doctor
```

---

## Installation & Launching

### Quick Launch via `uvx`
No installation needed:
```bash
uvx parallels-pro-mcp-server
```

### Local Development Installation
```bash
git clone https://github.com/your-username/parallels-pro-mcp-server.git
cd parallels-pro-mcp-server
uv sync
uv run parallels-pro-mcp
```

---

## Tool Reference

### `vm_list`
Lists every registered virtual machine on the host.
- **Parameters**: None
- **Returns**: Array of VM objects with `uuid`, `name`, `status` (`running`, `stopped`, `suspended`), and `ip_address`.

### `vm_status`
Queries full details for a target virtual machine.
- **Parameters**: `vm` (string: friendly name or UUID).
- **Returns**: Extended status including `os`, `uptime_seconds`, `home_path`, and `guest_tools_state`.

### `vm_start`
Powers on a stopped or suspended VM.
- **Parameters**: `vm` (string: name or UUID).

### `vm_stop`
Initiates a clean, graceful ACPI shutdown.
- **Parameters**: `vm` (string: name or UUID).
- **Safety**: Never issues a forced power cut (`--kill`).

### `vm_suspend`
Suspends a running VM, saving its memory state to disk.
- **Parameters**: `vm` (string: name or UUID).

### `vm_wait_ready`
Polls the guest operating system until execution probes answer successfully.
- **Parameters**:
  - `vm`: Name or UUID.
  - `timeout_s` (float, default 300.0): Maximum duration in seconds to wait.
- **Behavior**: Auto-detects Windows vs POSIX (Linux/macOS) and executes appropriate readiness probes (`cmd.exe` vs `/bin/sh`).

### `vm_exec`
Executes an explicit command vector in the guest operating system.
- **Parameters**:
  - `vm`: Name or UUID.
  - `command`: List of string arguments, e.g. `["whoami"]` or `["ls", "-la", "/tmp"]`.
  - `user` (optional): Guest user to run as. If omitted, Windows defaults to `--current-user` (interactive desktop console session 1).
  - `timeout_s` (float, default 300.0): Execution timeout.
- **Returns**: Bounded `stdout`, `stderr`, `returncode`, and truncation flags.

### `vm_screenshot`
Captures the current visual display buffer of the virtual machine to a host PNG image.
- **Parameters**:
  - `vm`: Name or UUID.
  - `output_path` (optional): Host file path to write PNG. If omitted, writes to `PARALLELS_ARTIFACT_DIR`.
- **Returns**: Object with `vm`, `uuid`, `path`, and file `bytes`.

### `snapshot_list`
Lists all existing snapshots for a virtual machine.
- **Parameters**: `vm` (string: name or UUID).
- **Returns**: List of snapshot objects with `id`, `name`, `date`, `state`, and `current` indicator.

### `snapshot_create`
Takes a new snapshot of the virtual machine.
- **Parameters**:
  - `vm`: Name or UUID.
  - `name`: Human-readable snapshot name.
  - `description` (optional): Additional notes.
  - `confirm`: Must be `true`.

### `snapshot_revert`
Reverts the virtual machine state to a designated snapshot.
- **Parameters**:
  - `vm`: Name or UUID.
  - `snapshot`: Snapshot name or UUID.
  - `confirm`: Must be `true`.

---

## Pre-flight Diagnostics (`doctor`)

To assist with debugging environment issues, the server includes a diagnostic doctor:

```bash
uv run parallels-pro-mcp doctor
```

It validates:
- Host operating system (macOS verification)
- Python runtime version
- `prlctl` availability in PATH
- Parallels license edition (`pro` or `business`)
- Parallels Desktop service responsiveness
- Enumerates registered VMs and power states

---

## Troubleshooting

### `prlctl: command not found`
Ensure Parallels Desktop Pro or Business is installed. If installed in a non-standard directory, add `/usr/local/bin` to your `PATH`.

### License error on `vm_exec`
If `vm_exec` reports a license error, check `prlsrvctl info --license`. Parallels Standard edition does not license guest command execution; Pro or Business edition is required.

### `vm_wait_ready` times out
1. Check if Parallels Tools is installed inside the guest OS.
2. In Windows guests, verify that the desktop session is unlocked.
3. Call `vm_screenshot` to inspect if a modal dialog or OS update is blocking boot.

---

## Security & Isolation

- **Host Shared Folders**: If Parallels Shared Folders are enabled, guest execution commands can read or mutate files in shared host directories. Only execute commands against trusted virtual machines.
- **No Remote Ports**: The MCP server operates exclusively over local `stdio` processes launched by the client. It does not open network ports or expose HTTP services.
