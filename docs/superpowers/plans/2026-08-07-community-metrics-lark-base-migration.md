# Community Metrics Lark Base Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and run an idempotent migration that creates the approved `FP-DC数据` Base schema and copies every historical daily and weekly community metric record present at execution time without changing the production Bot writer.

**Architecture:** A one-time Python migration script owns Lark authentication, source Sheet reads, Base schema setup, record normalization, idempotent upsert, and verification. Pure transformation helpers are covered by focused tests; the live run starts in dry-run mode and only writes after the source count and normalized records pass validation.

**Tech Stack:** Python 3, standard library, `aiohttp`, Lark Sheets API v2, Lark Base API v1, pytest.

## Global Constraints

- Keep spreadsheet `PA8usyjmshX40HtXaeTjkr4Apne`, sheet `e348a1` unchanged.
- Target only Base `CeqtbxWt5azkkHs8OzpjZ9D1p2e`, table `tblMeRm8yocZPqUR` (`FP-DC数据`).
- Require the validated baseline of 38 daily and 5 weekly records, while including newer source rows.
- Do not create, rename, or modify Base views in this stage.
- Convert `/` and empty source cells to absent Base fields, not zero.
- Do not modify `cogs/community_metrics.py` or deploy/restart the Bot in this stage.
- Delete only target records whose fields are all empty.

---

### Task 1: Pure Migration Mapping

**Files:**
- Create: `scripts/migrate_community_metrics_to_base.py`
- Create: `tests/test_community_metrics_base_migration.py`

**Interfaces:**
- Produces: `normalize_date(value) -> datetime.date | None`
- Produces: `build_migration_records(rows) -> list[dict[str, object]]`
- Produces: `validate_migration_records(records) -> None`

- [ ] **Step 1: Write failing transformation tests**

Cover serial dates `46187 -> 2026-06-14`, slash-to-empty conversion, daily and weekly mappings, separate daily/weekly records on the same date, negative growth preservation, a minimum baseline of 38 daily plus 5 weekly records, and acceptance of newer rows.

- [ ] **Step 2: Run the focused tests and verify failure**

Run: `python -m pytest tests/test_community_metrics_base_migration.py -q`

Expected: collection fails because `scripts.migrate_community_metrics_to_base` does not exist.

- [ ] **Step 3: Implement the pure mapping helpers**

Use these exact Base field names:

```python
COMMON_FIELDS = ("记录", "统计类型", "日期", "当前总人数", "新增人数", "离开人数", "净增长")
DAILY_FIELDS = (
    "Gaming Alerts 新增订阅人数",
    "Exclusive Updates 新增订阅人数",
    "Lucky Drops 新增订阅人数",
)
WEEKLY_FIELDS = (
    "本周贴文 Reaction 数",
    "Gaming Alerts 总订阅人数",
    "Exclusive Updates 总订阅人数",
    "Lucky Drops 总订阅人数",
)
```

Daily source columns map from `A:H`; weekly source columns map from `I:Q`. Date values written to Base use Beijing-midnight Unix milliseconds. The primary field is formatted as `日报 YYYY/MM/DD` or `周报 YYYY/MM/DD`.

- [ ] **Step 4: Run focused tests and verify success**

Run: `python -m pytest tests/test_community_metrics_base_migration.py -q`

Expected: all migration mapping tests pass.

### Task 2: Idempotent Lark Migration Client

**Files:**
- Modify: `scripts/migrate_community_metrics_to_base.py`
- Modify: `tests/test_community_metrics_base_migration.py`

**Interfaces:**
- Produces: `LarkMigrationClient`
- Produces: `run_migration(client, apply: bool) -> MigrationReport`

- [ ] **Step 1: Write failing client orchestration tests**

Use a fake client to prove dry-run performs no writes, missing fields are created only in apply mode, views are never modified, blank placeholders are the only deleted records, existing records are updated by primary key, missing records are created, and the final remote records exactly match the normalized source.

- [ ] **Step 2: Run focused tests and verify failure**

Run: `python -m pytest tests/test_community_metrics_base_migration.py -q`

Expected: tests fail because the client and orchestration functions are missing.

- [ ] **Step 3: Implement Lark API operations**

The script must:

1. Load `LARK_APP_ID` and `LARK_APP_SECRET` from process environment, with optional `.env` loading for local execution.
2. Read `e348a1!A1:Q200` from the source Sheet.
3. Rename the existing primary field `文本` to `记录`.
4. Create missing Base fields with text (`1`), number (`2`), single-select (`3`), and date (`5`) field types.
5. Leave all Base views unchanged.
6. Delete only records with an empty `fields` object or only empty values.
7. Upsert records by the `记录` primary field.
8. Re-read all records, reject duplicate primary keys, normalize Lark numeric strings, and compare every expected populated field.
9. Print dynamically calculated source daily/weekly counts, created/updated/deleted counts, and verification result without printing credentials.

- [ ] **Step 4: Run focused tests and the full Python suite**

Run: `python -m pytest tests/test_community_metrics_base_migration.py -q`

Expected: all focused tests pass.

Run: `python -m pytest -q`

Expected: the existing suite remains green.

### Task 3: Dry Run, Apply, and Remote Verification

**Files:**
- No tracked file changes beyond Tasks 1 and 2.

**Interfaces:**
- Consumes: `scripts/migrate_community_metrics_to_base.py`
- Produces: verified `FP-DC数据` Base schema and all source records present at execution time.

- [ ] **Step 1: Run a live dry-run**

Run: `python scripts/migrate_community_metrics_to_base.py`

Expected report: dynamic daily/weekly counts and `apply=False`; no Base writes occur.

- [ ] **Step 2: Apply the migration once**

Run: `python scripts/migrate_community_metrics_to_base.py --apply`

Expected: fields are created, views remain unchanged, five blank records are removed, and all normalized source records are present.

- [ ] **Step 3: Re-run dry-run to prove idempotency**

Run: `python scripts/migrate_community_metrics_to_base.py`

Expected: remote verification passes with the same record count as the source and no pending creates, updates, or deletes.

- [ ] **Step 4: Spot-check critical records**

Verify remotely:

- `日报 2026/07/03`: total `540`, added `1`, left `0`, net `1`.
- `周报 2026/08/02`: total `759`, added `39`, left `18`, net `21`, reactions `27`, role totals `94`, `140`, `55`.
- `日报 2026/08/06`: total `794`, added `15`, left `3`, net `12`, role additions `4`, `4`, `6`.

- [ ] **Step 5: Commit the migration tool and tests**

```bash
git add scripts/migrate_community_metrics_to_base.py tests/test_community_metrics_base_migration.py docs/superpowers/plans/2026-08-07-community-metrics-lark-base-migration.md
git commit -m "feat: migrate community metrics to lark base"
```

Do not push or deploy in this stage.
