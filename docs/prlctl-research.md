# Parallels CLI research

Captured from the live install on this machine, not from docs.

|          |                                                                      |
|----------|----------------------------------------------------------------------|
| Version  | `prlctl` 26.4.1 (57516)                                              |
| Edition  | **pro** (`prlsrvctl info --license` → `edition="pro"`)               |
| Binaries | `/usr/local/bin/prlctl`, `prlsrvctl`, `prl_disk_tool`, `prl_convert` |
| Test VMs | 6 registered (Windows 11, macOS 12, Ubuntu, Debian, Kali, NixOS)     |

## JSON support — the key finding

Structured output exists for every important **read** path, so the server needs
almost no text scraping.

| Command                                         | `-j`    | Shape                                      |
|-------------------------------------------------|---------|--------------------------------------------|
| `prlctl list`                                   | yes     | array of objects                           |
| `prlctl list -i` (full config)                  | **yes** | array of deeply nested objects             |
| `prlctl snapshot-list`                          | yes     | **object keyed by `{uuid}`**, not an array |
| `prlsrvctl info`                                | yes     | object                                     |
| `prlsrvctl net list` / `usb list` / `user list` | yes     | array                                      |
| `prlctl status`                                 | no      | one line of text                           |
| everything else (writes)                        | no      | human text, exit code is the real signal   |

Quirks to handle:

- `snapshot-list -j` returns a map, and its UUIDs carry `{}` braces. Normalize to a list.
- `list -i -j` UUIDs are bare; `list -i` (text) wraps them in `{}`. Normalize.
- `Uptime` is seconds in JSON, a human string in text.
- Paths are escaped (`\/`), which `json.loads` handles.
- Values are strings, including `"on"` / `"off"` / `"no"` — coerce to bool deliberately.

## Command inventory

### prlctl — VM management

| Action                                           | Notes                                                                     |
|--------------------------------------------------|---------------------------------------------------------------------------|
| `list`                                           | `-a` all, `-i` info, `-j` json, `-o` fields, `-t` templates, `-S` stopped |
| `status`                                         | single VM state                                                           |
| `create`                                         | `--ostype`, `--distribution`, `--ostemplate`, `--dst`, `--no-hdd`         |
| `clone`                                          | `--name`, `--linked`, `--template`, `--dst`, `--regenerate-src-uuid`      |
| `delete`                                         | **destructive, irreversible**                                             |
| `register` / `unregister`                        | add/remove an existing `.pvm` from the library                            |
| `move` / `convert`                               | `--dst`                                                                   |
| `archive` / `unarchive`                          | shrink a VM bundle on disk                                                |
| `protection-set` / `protection-remove`           | expiration-date protection                                                |
| `encrypt` / `decrypt` / `change-passwd`          | needs interactive password                                                |
| `installtools`                                   | Parallels Tools into guest                                                |
| `capture`                                        | `--file` screenshot → image tool candidate                                |
| `exec`                                           | run a command in the guest; `-u/--user`, `--password`                     |
| `enter`                                          | interactive shell — **not MCP-viable**, needs a TTY                       |
| `send-key-event`                                 | synthetic keystrokes                                                      |
| `problem-report`, `guest-debugger`, `debug-dump` | diagnostics                                                               |

### prlctl — power

`start` (`--rollback-mode`, `--recovery-mode`) · `stop` (`--kill`, `--acpi`, `--drop-state`) ·
`restart` · `reset` · `suspend` · `resume` · `pause` (`--acpi`) · `reset-uptime`

### prlctl — snapshots

| Action            | Options                                  |
|-------------------|------------------------------------------|
| `snapshot`        | `-n/--name`, `-d/--description`          |
| `snapshot-list`   | `-t` tree, `-i` id, `-j` json            |
| `snapshot-switch` | `-i` id, `--skip-resume`                 |
| `snapshot-delete` | `-i` id, `-c` children — **destructive** |

### prlctl set — configuration categories

`cpus` · `memory` · `boot` · `video` · `mouse` · `keyboard` · `printers` · `usb` ·
`bluetooth` · `startup` · `optimization` · `travel` · `security` · `smartguard` ·
`protection` · `modality` · `fullscreen` · `coherence` · `timesync` · `device_mgmt` ·
`shared_folders` · `shared_profiles` · `shared_apps` · `smart_mounts` · `misc_sharing` ·
`advanced` · `misc` · `network_cond`

Help for a category is `prlctl set <category> --help` — note the VM ID is **omitted**
in the help form, unlike the real invocation.

High-value flags:

- **cpus** — `--cpus <auto|N>`
- **memory** — `--memsize <auto|MB>`
- **misc** — `--name`, `--description`, `--template <on|off>`
- **startup** — `--autostart`, `--autostop`, `--startup-view` (incl. `headless`), `--on-window-close`
- **optimization** — `--nested-virt`, `--hypervisor-type <parallels|apple>`, `--resource-quota`, `--faster-vm`
- **boot** — `--device-bootorder`, `--bios-type`, `--efi-secure-boot`
- **security** — `--isolate-vm`, `--tpm`, `--lock-edit-settings`, `--userpasswd`
- **advanced** — `--sync-ssh-ids`, `--rosetta-linux`, `--sync-vm-hostname`
- **network_cond** — bandwidth/delay/packet-loss shaping; profiles: `edge, dsl, 3g, 100-percent-loss, very-bad-net, wifi`
- **shared_folders** — `--shf-host-add <name> --path <p> --mode <ro|rw>`, `--shf-host-del`, `--shf-host-defined`

### prlctl set — device management

`--device-add` / `--device-set` / `--device-del` / `--device-connect` / `--device-disconnect`

Types: `hdd`, `cdrom`, `fdd`, `net`, `serial`, `parallel`, `sound`, `usb`.
Per-type help: `prlctl set --device-add-hdd --help`.

- **hdd** — `--image`, `--size`, `--type <expand|plain>`, `--iface <ide|scsi|sata|nvme>`, `--alloc-policy`
- **net** — `--type <shared|bridged|host-only>`, `--iface`, `--mac`, `--ipadd`, `--dhcp`, `--gw`, `--nameserver`, `--adapter-type <virtio|e1000|rtl>`
- **cdrom** — `--image`, `--iface`, `--device`, `--passthr`

### prlsrvctl — host/server level

`info` (`-j`, `--license`, `-f`) · `install-license` / `update-license` / `deactivate-license` ·
`set` (host mem limit, security level, password requirements) ·
`user list` / `user set --def-vm-home` ·
`net list|info|set` (virtual networks, DHCP scopes, **NAT port-forward rules** via
`--nat-tcp-add <name,src_port,dest_ip|dest_vm,dest_port>`) ·
`usb list|set|del|rename|cleanup` · `problem-report` · `shutdown`

### prl_disk_tool — virtual disk ops

`create` (`--size`, `--expanding`, `--split`, `--alloc-policy`, from `--dmg`, or `-p` physical) ·
`resize` (`--size`, `--resize_partition`, `--force`; `-i` info-only) ·
`compact` (`--buildmap`, `--exclude-pagefile`; `-i` estimate-only) ·
plus merge/convert subcommands.

## Engineering implications

1. **Reads are cheap and safe.** `list`, `list -i`, `snapshot-list`, `prlsrvctl info` cover
   ~80% of useful MCP surface with JSON in, JSON out.
2. **Writes return human text.** Treat the exit code as the source of truth and return
   stderr on failure.
3. **Identify VMs by UUID internally.** Names contain spaces and change; always pass args
   as a list to `subprocess`, never a shell string.
4. **`prlctl enter` cannot work over MCP** — it needs an interactive TTY. Use `exec`.
5. **Secrets**: `exec --password` and `set --userpasswd` put credentials in the process
   table. Prefer `--current-user`, or pass via env/stdin where possible.
6. **Long operations** (clone, convert, compact, archive) can run for minutes. They need
   a timeout policy and probably an async/background story.
7. **Destructive set**: `delete`, `snapshot-delete`, `stop --kill`, `set --userpasswd`,
   `prlsrvctl shutdown`. These want an explicit opt-in, not a default-on tool.

## `prlctl exec` — verified against the Windows 11 guest

Tested live on 2026-08-15 against the Windows 11 ARM64 VM (Parallels Tools 26.4.0).

### Argument order is load-bearing

Options come **after** the VM name, not before:

```
prlctl exec "Windows 11" --current-user cmd /c "whoami"   # works
prlctl exec --current-user "Windows 11" cmd /c "whoami"   # "virtual machine could not be found"
```

The misleading error makes this easy to misdiagnose. The wrapper must always build
argv as `[prlctl, exec, <uuid>, *flags, *command]`.

### `--current-user` is mandatory for this use case

|                     | default (no flag)                          | `--current-user`            |
|---------------------|--------------------------------------------|-----------------------------|
| Identity            | `nt authority\system`                      | `DOMAIN\username`           |
| Windows session     | **0** (services, no desktop)               | **1** (interactive console) |
| `%USERPROFILE%`     | `C:\WINDOWS\system32\config\systemprofile` | `C:\Users\username`         |
| `Z:` → `\\Mac\Home` | **missing**                                | **present**                 |
| Headed browsers     | cannot render — no desktop                 | works                       |

Why it matters for Playwright:

- Browsers installed by `npx playwright install` land in
  `%USERPROFILE%\AppData\Local\ms-playwright`. Under SYSTEM that is a *different
  directory* than the one a human sees, so a manual install and an `exec` install
  silently disagree about whether browsers exist.
- Session 0 has no interactive desktop, so `headless: false` runs fail there.
- Drive-letter shares (`Z:`, `Y:`) are per-session mappings and do not exist under
  SYSTEM. UNC paths (`\\Mac\Home\...`) work in **both** sessions and are the safer
  form regardless.

**Decision: the server always passes `--current-user`.**

`-u <user>` without `--password` fails auth outright, so the alternative would mean
handling credentials — avoided entirely by using `--current-user`.

### Verified behaviour

| Property                      | Result                                                                   |
|-------------------------------|--------------------------------------------------------------------------|
| Exit codes                    | propagate exactly (tested 0, 1, 3, 7)                                    |
| stdout / stderr               | cleanly separated, not merged                                            |
| Guest readiness after `start` | `exec` answered within 5s                                                |
| PowerShell                    | available at `C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe` |
| Trailing whitespace           | `cmd /c echo` appends a space before the newline — strip it              |

Exit-code fidelity is what makes a Playwright wrapper viable at all: a failing suite
returns non-zero and the server can report failure honestly.

### Guest software inventory (as of this research)

Bare Windows 11 — **no `node`, no `npm`, no `git`**. Provisioning is in scope.

Shared folders already mounted: `Z:` → `\\Mac\Home`, `Y:` → `\\Mac\iCloud`.

### GUI rendering — verified for Electron

Launched Notepad via `exec --current-user` and confirmed Windows assigned it a real
window handle (`MainWindowHandle` non-zero). GUI processes get a genuine desktop under
`--current-user`, so an Electron app will launch and paint.

This is make-or-break rather than a nicety: **Electron has no headless mode on Windows**
(no `xvfb` equivalent), so every run is a real windowed run. Under the default SYSTEM /
session 0 identity the suite would not run slower — it would not run.

Operational consequence: the console session must stay unlocked. A screensaver or lock
timeout can break GUI rendering mid-run and produce failures unrelated to the code under
test. Disable both on the test VM.

### `prlctl capture` — verified

```
prlctl capture "Windows 11" --file /tmp/shot.png
→ PNG image data, 1420 x 943, 8-bit/color RGB   (~1s, 301 KB)
```

Captures the **entire VM screen**, not a browser viewport — so it sees native window
chrome, DPI scaling, menu bars, system dialogs, and tray icons that a Playwright
screenshot cannot. Unusually valuable for Electron compatibility testing.

### Architecture constraint

Parallels on Apple Silicon runs **ARM64 guests only**. Any Electron testing here is
`win32-arm64`, or x64 under Windows' emulation layer — not native x64 Windows.
