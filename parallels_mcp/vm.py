"""Read-only VM discovery and status normalization."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, ConfigDict

from .prl import run_prlctl_json


Runner = Callable[..., Awaitable[Any]]


class VmError(RuntimeError):
    """Base error for VM lookup failures."""


class VmNotFoundError(VmError):
    """Raised when a requested VM name or UUID is not registered."""


class AmbiguousVmError(VmError):
    """Raised when a friendly VM name matches more than one VM."""


class VmSummary(BaseModel):
    """Compact VM data suitable for an MCP tool result."""

    model_config = ConfigDict(extra="forbid")

    uuid: str
    name: str
    status: str
    ip_address: str | None = None


class VmStatus(VmSummary):
    """Detailed, bounded VM status returned by ``vm_status``."""

    os: str | None = None
    uptime_seconds: int | None = None
    home_path: str | None = None
    guest_tools_state: str | None = None
    guest_tools_version: str | None = None


def _strip_uuid(value: Any) -> str:
    return str(value or "").strip().strip("{}").lower()


def _string(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _ip_address(value: Any) -> str | None:
    value = _string(value)
    return None if value in (None, "-") else value


def _int_or_none(value: Any) -> int | None:
    try:
        return None if value in (None, "") else int(value)
    except (TypeError, ValueError):
        return None


def _as_rows(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, list) or not all(isinstance(row, dict) for row in payload):
        raise VmError("Parallels returned an unexpected VM list shape")
    return payload


def _summary_from_row(row: dict[str, Any]) -> VmSummary:
    """Normalize compact and detailed Parallels VM row field names."""

    uuid = _string(row.get("uuid") or row.get("ID"))
    name = _string(row.get("name") or row.get("Name"))
    status = _string(row.get("status") or row.get("State"))
    if not uuid or not name or not status:
        raise VmError("Parallels returned a VM row missing uuid, name, or status")
    return VmSummary(
        uuid=_strip_uuid(uuid),
        name=name,
        status=status,
        ip_address=_ip_address(row.get("ip_configured") or row.get("IP_ADDR")),
    )


def _status_from_row(row: dict[str, Any]) -> VmStatus:
    summary = _summary_from_row(row)
    guest_tools = row.get("GuestTools")
    if not isinstance(guest_tools, dict):
        guest_tools = {}
    return VmStatus(
        **summary.model_dump(),
        os=_string(row.get("OS") or row.get("os")),
        uptime_seconds=_int_or_none(row.get("Uptime") or row.get("uptime_seconds")),
        home_path=_string(row.get("Home") or row.get("home_path")),
        guest_tools_state=_string(guest_tools.get("state")),
        guest_tools_version=_string(guest_tools.get("version")),
    )


class VmService:
    """Use the Parallels read APIs without exposing their raw output to tools."""

    def __init__(self, runner: Runner = run_prlctl_json, *, timeout: float = 30.0) -> None:
        self._runner = runner
        self._timeout = timeout

    async def list_vms(self) -> list[VmSummary]:
        payload = await self._runner("list", "-a", "-j", timeout=self._timeout)
        return [_summary_from_row(row) for row in _as_rows(payload)]

    async def resolve(self, name_or_uuid: str) -> str:
        key = name_or_uuid.strip()
        if not key:
            raise VmNotFoundError("VM name or UUID cannot be empty")

        vms = await self.list_vms()
        normalized_key = _strip_uuid(key)
        uuid_matches = [vm for vm in vms if vm.uuid == normalized_key]
        if uuid_matches:
            return uuid_matches[0].uuid

        name_matches = [vm for vm in vms if vm.name == key]
        if len(name_matches) == 1:
            return name_matches[0].uuid
        if len(name_matches) > 1:
            raise AmbiguousVmError(
                f"VM name {key!r} is ambiguous; use a UUID: "
                + ", ".join(vm.uuid for vm in name_matches)
            )

        known = ", ".join(sorted(vm.name for vm in vms)) or "none"
        raise VmNotFoundError(f"No VM named or identified by {key!r}. Registered VMs: {known}")

    async def status(self, name_or_uuid: str) -> VmStatus:
        uuid = await self.resolve(name_or_uuid)
        payload = await self._runner("list", "-i", "-j", uuid, timeout=self._timeout)
        rows = _as_rows(payload)
        if not rows:
            raise VmError(f"Parallels returned no status for VM {uuid}")
        return _status_from_row(rows[0])

    async def is_windows(self, name_or_uuid: str) -> bool:
        """Return True if the guest OS is Windows, False for Linux/other."""
        lower_name = name_or_uuid.lower()
        if any(term in lower_name for term in ("ubuntu", "linux", "debian", "centos", "rhel", "fedora", "nixos", "kali")):
            return False
        if any(term in lower_name for term in ("win", "windows")):
            return True
        try:
            vms = await self.list_vms()
            norm = _strip_uuid(name_or_uuid)
            for v in vms:
                if v.uuid == norm or v.name == name_or_uuid:
                    v_name = v.name.lower()
                    if any(term in v_name for term in ("ubuntu", "linux", "debian", "centos", "rhel", "fedora", "nixos", "kali")):
                        return False
                    if any(term in v_name for term in ("win", "windows")):
                        return True
        except Exception:
            pass
        try:
            st = await self.status(name_or_uuid)
            if st.os:
                os_lower = st.os.lower()
                if any(term in os_lower for term in ("ubuntu", "linux", "debian", "centos", "rhel", "fedora")):
                    return False
                if "win" in os_lower:
                    return True
        except Exception:
            pass
        return True
