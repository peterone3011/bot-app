# Community Metrics Single-Date Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the duplicated primary record/date columns with one primary `日期` text field containing `YYYY/MM/DD`.

**Architecture:** The Bot uses the displayed date text as its idempotent key and sends seven integer metrics beside it. An idempotent migration normalizes existing primary values, deletes only the non-primary date field, renames the primary field, and verifies all records and fields afterward.

**Tech Stack:** Python 3.13, discord.py, aiohttp, Lark Base API v1, pytest, Railway.

## Global Constraints

- Target app is `CeqtbxWt5azkkHs8OzpjZ9D1p2e`; target table is `tblMeRm8yocZPqUR`.
- Preserve all 39 existing daily records and all seven metric values per record.
- Final table has exactly eight fields: primary text `日期` plus seven integer metrics.
- Primary values use exact `YYYY/MM/DD` text and remain unique.
- Daily schedule remains 23:59 Beijing time.
- Do not alter durable pending writes, retries, locking, or the legacy Sheet.

---

### Task 1: Use Date Text As The Bot Key

**Files:**
- Modify: `cogs/community_metrics.py`
- Modify: `tests/test_community_metrics.py`

**Interfaces:**
- Removes: `_base_date_ms(day)`
- Changes: `LarkBaseClient.upsert_record(key, fields)` matches `fields["日期"]`
- Changes: `_write_daily()` sends `{"日期": "YYYY/MM/DD", ...seven metrics}`

- [ ] Write tests asserting the exact eight-field daily payload and lookup by primary `日期` text.
- [ ] Run `python -m pytest tests/test_community_metrics.py -q`; expect failures against current `记录` lookup and timestamp date payload.
- [ ] Change lookup and payload without touching schedule or persistence code.
- [ ] Run the focused tests; expect all to pass.
- [ ] Commit with `git commit -m "feat: use date as community metric key"`.

---

### Task 2: Add Idempotent Single-Date Migration

**Files:**
- Create: `scripts/migrate_community_metrics_single_date.py`
- Create: `tests/test_community_metrics_single_date_migration.py`

**Interfaces:**
- Produces: `build_migration_plan(fields, records) -> MigrationPlan`
- Produces: `run_migration(client, apply: bool, minimum_daily: int = 0) -> MigrationReport`
- Consumes existing Lark migration client batch update, field delete, and field rename operations

- [ ] Write failing tests for current, interrupted, and completed schema states.
- [ ] Require every primary value to match either `日报 YYYY/MM/DD` or `YYYY/MM/DD`, reject duplicates and all unexpected fields/records before writes.
- [ ] Implement update order: normalize primary values, delete the non-primary `日期` field, rename primary `记录` to `日期`.
- [ ] Verify dry-run writes nothing, apply preserves record count, and rerun is a no-op.
- [ ] Run `python -m pytest tests/test_community_metrics_single_date_migration.py -q`; expect all tests to pass.
- [ ] Commit with `git commit -m "feat: migrate community metrics to one date field"`.

---

### Task 3: Verify And Roll Out

**Files:**
- Verify only: all changed files

- [ ] Run `python -m pytest -q`, `python -m compileall -q cogs scripts`, and `git diff --check origin/main..HEAD`.
- [ ] Review that selectors can delete only the one non-primary date field and that no metric field/value is included in migration updates.
- [ ] Run the migration without `--apply`; expect 39 records, 39 primary-value updates, one secondary date-field delete, and one primary rename.
- [ ] Apply migration and rerun dry-run; expect 39 records, 8 fields, zero pending operations, and `verified=True`.
- [ ] Push reviewed commits to `main`, wait for Railway `SUCCESS/RUNNING`, and check startup/error logs.
- [ ] Do not manually trigger the 23:59 rollup; the next scheduled run performs the first live single-date upsert.
