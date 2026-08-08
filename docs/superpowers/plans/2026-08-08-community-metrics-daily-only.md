# Community Metrics Daily-Only Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep only daily Discord community metrics in the production Lark Base table and remove all weekly data, fields, and Bot scheduling.

**Architecture:** The Bot retains its existing durable daily upsert pipeline but removes the weekly task and weekly-only payload fields. A separate idempotent cleanup CLI validates the exact Base target, classifies every record, deletes only `周报 ` records, deletes five named obsolete fields, and applies integer formatting to the seven retained numeric fields.

**Tech Stack:** Python 3.13, discord.py tasks, aiohttp, Lark Base API v1, pytest, Railway.

## Global Constraints

- Target Base app token is `CeqtbxWt5azkkHs8OzpjZ9D1p2e`.
- Target table ID is `tblMeRm8yocZPqUR`.
- Keep the daily rollup at 23:59 Beijing time.
- Keep all existing daily records and delete all existing weekly records.
- Keep exactly nine fields: `记录`, `日期`, `当前总人数`, `新增人数`, `离开人数`, `净增长`, `Gaming Alerts 新增订阅人数`, `Exclusive Updates 新增订阅人数`, and `Lucky Drops 新增订阅人数`.
- Configure the seven retained metric number fields with integer formatter `0`.
- Do not read from, write to, or modify the legacy Lark Sheet.
- Preserve durable pending writes, retries, cross-process locking, and deterministic `client_token` behavior.

---

### Task 1: Remove Weekly Bot Behavior

**Files:**
- Modify: `cogs/community_metrics.py`
- Modify: `tests/test_community_metrics.py`
- Modify: `README.md`

**Interfaces:**
- Preserves: `CommunityMetricsCog.daily_rollup()` and `_write_daily(day: datetime.date) -> None`
- Removes: `CommunityMetricsCog.weekly_rollup()`, `_write_weekly()`, and weekly reaction helpers
- Produces daily Base fields containing only the nine retained fields

- [ ] **Step 1: Write failing tests**

Replace weekly rollup tests with assertions that `CommunityMetricsCog` has no `weekly_rollup` attribute and that the exact daily payload is:

```python
{
    "记录": "日报 2026/07/28",
    "日期": cm._base_date_ms(datetime.date(2026, 7, 28)),
    "当前总人数": 540,
    "新增人数": 1,
    "离开人数": 0,
    "净增长": 1,
    "Gaming Alerts 新增订阅人数": 0,
    "Exclusive Updates 新增订阅人数": 0,
    "Lucky Drops 新增订阅人数": 1,
}
```

- [ ] **Step 2: Run tests and verify the intended failures**

Run: `python -m pytest tests/test_community_metrics.py -q`

Expected: failures because `weekly_rollup` still exists and daily payload still includes `统计类型` plus weekly-only fields.

- [ ] **Step 3: Implement the daily-only Cog**

Remove weekly task startup/cancellation, `_write_weekly`, weekly reaction counting, and imports/constants used only by weekly metrics. Build the daily payload with exactly the nine retained fields. Do not alter `_persisted_upsert` or scheduling time `_ROLLUP_TIME_UTC`.

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest tests/test_community_metrics.py -q`

Expected: all community metric tests pass.

- [ ] **Step 5: Update documentation**

Change README community metric text from “daily/weekly” to “daily at 23:59 Beijing time” and remove references to weekly reaction/role totals.

- [ ] **Step 6: Commit**

```bash
git add cogs/community_metrics.py tests/test_community_metrics.py README.md
git commit -m "feat: keep community metrics daily only"
```

---

### Task 2: Add Idempotent Base Cleanup CLI

**Files:**
- Create: `scripts/cleanup_community_metrics_daily_only.py`
- Create: `tests/test_community_metrics_daily_cleanup.py`

**Interfaces:**
- Consumes: `LarkMigrationClient` from `scripts/migrate_community_metrics_to_base.py`
- Produces: `build_cleanup_plan(fields, records) -> CleanupPlan`
- Produces: `run_cleanup(client, apply: bool) -> CleanupReport`

- [ ] **Step 1: Write failing cleanup-plan tests**

Tests must prove that the planner:

```python
assert plan.weekly_record_ids == ("weekly-1", "weekly-2")
assert plan.obsolete_field_ids == (
    "type-field", "reaction-field", "gaming-total-field",
    "updates-total-field", "lucky-total-field",
)
assert plan.numeric_field_ids == (
    "total", "joins", "leaves", "net", "gaming-new", "updates-new", "lucky-new",
)
```

It must raise before writes for a record key that starts with neither `日报 ` nor `周报 `, a missing retained field, duplicate field names, or a retained numeric field whose type is not `2`.

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/test_community_metrics_daily_cleanup.py -q`

Expected: import failure because the cleanup module does not exist.

- [ ] **Step 3: Implement planning and API operations**

Create immutable `CleanupPlan` and `CleanupReport` dataclasses. Add client calls using these endpoints:

```text
POST   /bitable/v1/apps/{app}/tables/{table}/records/batch_delete
DELETE /bitable/v1/apps/{app}/tables/{table}/fields/{field_id}
PUT    /bitable/v1/apps/{app}/tables/{table}/fields/{field_id}
```

Use `{"field_name": name, "type": 2, "property": {"formatter": "0"}}` for retained numeric fields. Dry-run is the default; `--apply` performs record deletion, field updates, and obsolete-field deletion. Missing already-deleted weekly records/obsolete fields are accepted so reruns remain safe.

- [ ] **Step 4: Add verification tests**

Use a fake client to assert dry-run performs no writes, apply deletes only planned weekly IDs, and final verification requires zero weekly records, only daily keys, exactly nine retained fields, and formatter `0` on every numeric field.

- [ ] **Step 5: Run cleanup tests**

Run: `python -m pytest tests/test_community_metrics_daily_cleanup.py -q`

Expected: all cleanup tests pass.

- [ ] **Step 6: Commit**

```bash
git add scripts/cleanup_community_metrics_daily_only.py tests/test_community_metrics_daily_cleanup.py
git commit -m "feat: clean community metrics base to daily only"
```

---

### Task 3: Verify, Clean Production Base, And Deploy

**Files:**
- Verify only: all changed files

**Interfaces:**
- Consumes: `scripts/cleanup_community_metrics_daily_only.py`
- Produces: production Base with daily-only records and schema

- [ ] **Step 1: Run complete local verification**

```bash
python -m pytest -q
python -m compileall -q cogs scripts
git diff --check origin/main..HEAD
```

Expected: all tests pass, compilation succeeds, and diff check has no errors.

- [ ] **Step 2: Run final code review**

Review for accidental legacy Sheet writes, any remaining weekly scheduler, destructive cleanup selectors broader than the five named fields and `周报 ` keys, and loss of pending-write reliability.

- [ ] **Step 3: Run production dry-run**

```bash
python scripts/cleanup_community_metrics_daily_only.py
```

Expected report before cleanup: 39 daily records, 5 weekly records, 5 obsolete fields, 7 numeric fields requiring or confirming integer format, `apply=False`.

- [ ] **Step 4: Deploy the daily-only Bot once**

Push the reviewed commits to `main`, wait for Railway status `SUCCESS`, and verify the new instance is `RUNNING` with no error-level startup logs. Deploying code first prevents the old weekly task from writing removed fields on Sunday.

- [ ] **Step 5: Apply production Base cleanup**

```bash
python scripts/cleanup_community_metrics_daily_only.py --apply
```

Expected report: 39 daily records, 0 weekly records, 9 retained fields, all 7 number fields using formatter `0`, `verified=True`.

- [ ] **Step 6: Run final read-only verification**

Run the CLI again without `--apply`. Expected: no pending deletes or schema changes and `verified=True`.
