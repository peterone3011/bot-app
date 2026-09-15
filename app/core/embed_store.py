from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any


class EmbedStoreError(ValueError):
    """Raised when durable Embed builder state cannot be read safely."""


LegacyImporter = Callable[[], Awaitable[list[dict[str, Any]]]]


class EmbedMessageStore:
    """A durable, project-owned collection of Embed builder records."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = asyncio.Lock()

    @staticmethod
    def _validate_records(value: object) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            raise EmbedStoreError("Embed state must be a JSON list")
        records: list[dict[str, Any]] = []
        ids: set[str] = set()
        for index, item in enumerate(value):
            if not isinstance(item, dict):
                raise EmbedStoreError(f"Embed record {index} must be an object")
            message_id = item.get("id")
            if not isinstance(message_id, str) or not message_id:
                raise EmbedStoreError(f"Embed record {index} must have a string id")
            if message_id in ids:
                raise EmbedStoreError(f"Embed state contains duplicate id {message_id!r}")
            ids.add(message_id)
            records.append(dict(item))
        return records

    def _read_unlocked(self) -> list[dict[str, Any]]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise EmbedStoreError(f"Embed state contains invalid JSON: {exc.msg}") from exc
        except OSError as exc:
            raise EmbedStoreError(f"Unable to read Embed state: {exc}") from exc
        return self._validate_records(value)

    def _write_unlocked(self, records: list[dict[str, Any]]) -> None:
        validated = self._validate_records(records)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        try:
            temporary.write_text(
                json.dumps(validated, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary.replace(self.path)
        except OSError as exc:
            raise EmbedStoreError(f"Unable to write Embed state: {exc}") from exc

    async def ensure_initialized(self, importer: LegacyImporter | None = None) -> None:
        async with self._lock:
            if self.path.exists():
                self._read_unlocked()
                return
            imported = await importer() if importer else []
            self._write_unlocked(imported)

    async def list(self) -> list[dict[str, Any]]:
        async with self._lock:
            if not self.path.exists():
                raise EmbedStoreError("Embed state has not been initialized")
            return self._read_unlocked()

    async def get(self, message_id: str) -> dict[str, Any] | None:
        records = await self.list()
        return next((record for record in records if record["id"] == message_id), None)

    async def upsert(self, message: dict[str, Any]) -> None:
        async with self._lock:
            if not self.path.exists():
                raise EmbedStoreError("Embed state has not been initialized")
            records = self._read_unlocked()
            replacement = dict(message)
            message_id = replacement.get("id")
            if not isinstance(message_id, str) or not message_id:
                raise EmbedStoreError("Embed record must have a string id")
            for index, record in enumerate(records):
                if record["id"] == message_id:
                    records[index] = replacement
                    break
            else:
                records.append(replacement)
            self._write_unlocked(records)

    async def delete(self, message_id: str) -> None:
        async with self._lock:
            if not self.path.exists():
                raise EmbedStoreError("Embed state has not been initialized")
            records = self._read_unlocked()
            self._write_unlocked([record for record in records if record["id"] != message_id])
