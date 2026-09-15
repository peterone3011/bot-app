from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.embed_store import EmbedMessageStore, EmbedStoreError


@pytest.mark.asyncio
async def test_store_isolates_records_by_project_file(tmp_path: Path) -> None:
    alpha = EmbedMessageStore(tmp_path / "alpha" / "embed-messages.json")
    beta = EmbedMessageStore(tmp_path / "beta" / "embed-messages.json")

    await alpha.ensure_initialized()
    await beta.ensure_initialized()
    await alpha.upsert({"id": "draft-a", "status": "draft"})

    assert [row["id"] for row in await alpha.list()] == ["draft-a"]
    assert await beta.list() == []


@pytest.mark.asyncio
async def test_store_imports_legacy_records_only_once(tmp_path: Path) -> None:
    calls = 0

    async def importer() -> list[dict[str, str]]:
        nonlocal calls
        calls += 1
        return [{"id": "legacy", "status": "draft"}]

    store = EmbedMessageStore(tmp_path / "fortunepurple" / "embed-messages.json")
    await store.ensure_initialized(importer)
    await store.ensure_initialized(importer)

    assert calls == 1
    assert await store.get("legacy") == {"id": "legacy", "status": "draft"}


@pytest.mark.asyncio
async def test_failed_import_creates_no_state_file(tmp_path: Path) -> None:
    async def broken_importer() -> list[dict[str, str]]:
        raise RuntimeError("Supabase unavailable")

    path = tmp_path / "fortunepurple" / "embed-messages.json"

    with pytest.raises(RuntimeError, match="Supabase unavailable"):
        await EmbedMessageStore(path).ensure_initialized(broken_importer)

    assert not path.exists()


@pytest.mark.asyncio
async def test_store_rejects_malformed_state_without_overwriting_it(tmp_path: Path) -> None:
    path = tmp_path / "alpha" / "embed-messages.json"
    path.parent.mkdir()
    path.write_text("{not json", encoding="utf-8")
    store = EmbedMessageStore(path)

    with pytest.raises(EmbedStoreError, match="invalid JSON"):
        await store.list()

    assert path.read_text(encoding="utf-8") == "{not json"


@pytest.mark.asyncio
async def test_store_writes_a_json_list_atomically(tmp_path: Path) -> None:
    path = tmp_path / "alpha" / "embed-messages.json"
    store = EmbedMessageStore(path)
    await store.ensure_initialized()
    await store.upsert({"id": "draft-a", "status": "draft"})

    assert json.loads(path.read_text(encoding="utf-8")) == [
        {"id": "draft-a", "status": "draft"}
    ]
