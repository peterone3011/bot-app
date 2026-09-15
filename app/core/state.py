from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectState:
    """Filesystem locations owned by one project runtime."""

    root: Path
    slug: str

    @property
    def directory(self) -> Path:
        return self.root / self.slug

    @property
    def events_file(self) -> Path:
        return self.directory / "community-events.jsonl"

    @property
    def pending_rollups_file(self) -> Path:
        return self.directory / "pending-rollups.json"

    @property
    def embed_messages_file(self) -> Path:
        return self.directory / "embed-messages.json"

    def ensure_directory(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
