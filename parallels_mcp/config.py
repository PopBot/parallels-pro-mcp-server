"""Environment-backed settings for Parallels Desktop MCP server."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    default_vm: str | None
    artifact_dir: Path

    @classmethod
    def from_env(cls) -> "Settings":
        default_vm = os.environ.get("PARALLELS_DEFAULT_VM") or os.environ.get("PARALLELS_VM")
        artifact_dir = os.environ.get(
            "PARALLELS_ARTIFACT_DIR",
            str(Path.home() / ".cache" / "parallels-pro-mcp-server"),
        )
        return cls(
            default_vm=default_vm,
            artifact_dir=Path(artifact_dir).expanduser(),
        )
