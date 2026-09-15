# Project-Scoped Embed Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` task-by-task. Steps use checkbox syntax.

**Goal:** Make the interactive Discord Embed builder durable and project-isolated on the Railway volume, while preserving FortunePurple's existing records.

**Architecture:** Add a JSON-backed `EmbedMessageStore` at `/data/<slug>/embed-messages.json`. `ProjectRuntime` owns one store. A shared Embed builder Cog uses that store; FortunePurple imports legacy Supabase records only if its project file does not already exist.

**Tech Stack:** Python 3.13, discord.py, asyncio, JSON, Railway persistent volume, pytest.

## Global Constraints

- Preserve `/embed`, `/edit-embed`, and message-context `Edit Embed` behavior and English player-facing text.
- Never allow one project to read or write another project's records.
- New projects must not need Supabase variables.
- Do not alter Feishu, community metrics, auto reactions, or role assignment.
- Do not delete the legacy Supabase table.

---

### Task 1: Durable Project Store

**Files:**
- Modify: `app/core/state.py`
- Create: `app/core/embed_store.py`
- Create: `tests/test_embed_store.py`

**Produces:** `ProjectState.embed_messages_file`; `EmbedMessageStore(path)` with async `list`, `get`, `upsert`, `delete`, and `ensure_initialized(importer)`.

- [ ] Write failing tests for isolation, atomic persistence, malformed-file rejection, and one-time import.

```python
@pytest.mark.asyncio
async def test_store_isolates_project_records(tmp_path: Path):
    alpha = EmbedMessageStore(tmp_path / "alpha" / "embed-messages.json")
    beta = EmbedMessageStore(tmp_path / "beta" / "embed-messages.json")
    await alpha.ensure_initialized(None)
    await beta.ensure_initialized(None)
    await alpha.upsert({"id": "a", "status": "draft"})
    assert [row["id"] for row in await alpha.list()] == ["a"]
    assert await beta.list() == []

@pytest.mark.asyncio
async def test_store_imports_once(tmp_path: Path):
    calls = 0
    async def importer():
        nonlocal calls
        calls += 1
        return [{"id": "legacy", "status": "draft"}]
    store = EmbedMessageStore(tmp_path / "fp" / "embed-messages.json")
    await store.ensure_initialized(importer)
    await store.ensure_initialized(importer)
    assert calls == 1
```

- [ ] Run `python -m pytest tests/test_embed_store.py -q --basetemp=.tmp-pytest-store-red`; expect import failure.
- [ ] Implement `EmbedMessageStore` with an `asyncio.Lock`; validate a JSON list whose entries have unique string IDs; write a temporary sibling file and atomically replace the real file.
- [ ] Add `embed_messages_file` returning `self.directory / "embed-messages.json"`.
- [ ] Run `python -m pytest tests/test_embed_store.py -q --basetemp=.tmp-pytest-store-green`; expect all pass.
- [ ] Commit: `git commit -m "feat: add project scoped embed storage"`.

### Task 2: Runtime Initialization and Legacy Import

**Files:**
- Modify: `app/core/runtime.py`
- Modify: `app/runner.py`
- Create: `app/core/legacy_embed_import.py`
- Modify: `tests/test_runner.py`

**Produces:** `ProjectRuntime.embed_store`; `build_embed_store(runtime)`; `import_fortunepurple_embed_messages()`.

- [ ] Write a failing test proving two runtimes receive different store paths, and a non-FortunePurple runtime never calls the legacy importer.

```python
@pytest.mark.asyncio
async def test_only_fortunepurple_requests_legacy_import(monkeypatch, tmp_path):
    importer = AsyncMock(return_value=[])
    monkeypatch.setattr(runner, "import_fortunepurple_embed_messages", importer)
    runtime = make_runtime(tmp_path, slug="alpha")
    await runner.build_embed_store(runtime)
    importer.assert_not_awaited()
```

- [ ] Run `python -m pytest tests/test_runner.py -q --basetemp=.tmp-pytest-runtime-red`; expect missing runtime initialization.
- [ ] Implement lazy `cogs.db.aload_messages` import inside `import_fortunepurple_embed_messages`; do not contact Supabase at module import time.
- [ ] In `run_project`, create and initialize the project store before installing Cogs. Pass the importer only for slug `fortunepurple`; other projects initialize empty stores.
- [ ] Run `python -m pytest tests/test_runner.py -q --basetemp=.tmp-pytest-runtime-green`; expect all pass.
- [ ] Commit: `git commit -m "feat: initialize embed storage per project"`.

### Task 3: Shared Interactive Embed Builder

**Files:**
- Create: `app/cogs/embed_builder.py`
- Modify: `app/cogs/manual_embed.py`
- Modify: `tests/test_embed_builder.py`
- Modify: `tests/test_manual_embed.py`

**Produces:** `EmbedBuilderCog(runtime)` and `EmbedBuilderService(runtime, store)`.

- [ ] Write failing tests proving a new draft, edit, deletion, and scheduled-send query operate via `runtime.embed_store`, and a second project's store remains empty.
- [ ] Run `python -m pytest tests/test_embed_builder.py tests/test_manual_embed.py -q --basetemp=.tmp-pytest-builder-red`; expect shared builder imports to be missing.
- [ ] Port the existing UI from `cogs/embed.py` into `app/cogs/embed_builder.py`. Preserve command names, modal fields, context menu, Beijing-time scheduling, embed rendering, and link buttons.
- [ ] Pass one `EmbedBuilderService` through all modals, buttons, selects, and views. Replace every legacy `aload_messages`, `aget_message`, `aupsert_message`, and `adelete_message` call with the service store methods.
- [ ] Change `manual_embed.install(runtime)` to install the shared builder; remove its live import of `cogs.embed`.
- [ ] Keep failed scheduled sends in `scheduled` state. Remove a scheduled record only when its channel no longer exists, matching legacy behavior.
- [ ] Run `python -m pytest tests/test_embed_builder.py tests/test_manual_embed.py -q --basetemp=.tmp-pytest-builder-green`; expect all pass.
- [ ] Commit: `git commit -m "feat: make embed builder project scoped"`.

### Task 4: Migration Safety and Full Verification

**Files:**
- Modify: `tests/test_embed_store.py`
- Modify: `docs/superpowers/specs/2026-09-15-project-scoped-embed-storage-design.md`

- [ ] Write a failing test where the importer raises and assert no JSON file is created.

```python
@pytest.mark.asyncio
async def test_failed_import_creates_no_state_file(tmp_path: Path):
    async def broken_importer():
        raise RuntimeError("Supabase unavailable")
    path = tmp_path / "fortunepurple" / "embed-messages.json"
    with pytest.raises(RuntimeError):
        await EmbedMessageStore(path).ensure_initialized(broken_importer)
    assert not path.exists()
```

- [ ] Run `python -m pytest tests/test_embed_store.py -q --basetemp=.tmp-pytest-migration-red`; expect failure before safety code exists.
- [ ] Ensure import happens before directory creation and atomic persistence. Add project-scoped success/failure logs without secrets.
- [ ] Run `python -m pytest -q --basetemp=.tmp-pytest-full` and `python -m compileall -q app`; expect passing tests and exit code 0.
- [ ] Commit: `git commit -m "test: cover embed migration safety"`.

### Task 5: Deploy and Validate

**Files:** No source changes.

- [ ] Push the feature branch with `git push`.
- [ ] Deploy verified source: `railway up E:\company-ai\fpbot-railway-deploy-20260915-embed-storage --path-as-root --service bot-app --environment production --detach`.
- [ ] Verify latest status with `railway deployment list --service bot-app --environment production --limit 1 --json`; expect `SUCCESS`.
- [ ] Verify `railway logs --service bot-app --environment production --lines 40`; expect shared `manual_embed` Cog loaded, FortunePurple login, and no migration or command-sync traceback.
- [ ] Inspect the Railway volume read-only with `railway ssh --service bot-app --environment production -- ls -l /data/fortunepurple/embed-messages.json`.
