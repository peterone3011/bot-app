# Community Metrics Base Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Switch production Discord daily and weekly community metric rollups from the legacy Lark Sheet to the migrated `FP-DC数据` Lark Base table.

**Architecture:** Keep all Discord event collection, metric calculation, reaction counting, and 23:59 Beijing scheduling unchanged. Replace only the storage boundary with a small Lark Base client that upserts by the unique `记录` value (`日报 YYYY/MM/DD` or `周报 YYYY/MM/DD`) and rejects duplicate remote keys.

**Tech Stack:** Python 3, `aiohttp`, discord.py tasks, Lark Base API v1, pytest.

## Global Constraints

- Target Base app token defaults to `CeqtbxWt5azkkHs8OzpjZ9D1p2e`.
- Target table ID defaults to `tblMeRm8yocZPqUR`.
- Preserve daily execution at 23:59 Beijing time and weekly execution on Sunday at 23:59 Beijing time.
- Preserve all existing metric definitions, including human-only reactions and Lucky Drops metrics.
- Do not write any new rows to spreadsheet `PA8usyjmshX40HtXaeTjkr4Apne`, sheet `e348a1`.
- Upserts must update an existing same-type/date record and never create duplicates.
- Keep the old Sheet unchanged as a read-only rollback reference.

---

### Task 1: Idempotent Lark Base Storage Client

**Files:**
- Modify: `cogs/community_metrics.py`
- Modify: `tests/test_community_metrics.py`

**Interfaces:**
- Produces: `LarkBaseClient.upsert_record(key: str, fields: dict[str, object]) -> Literal["created", "updated"]`
- Produces: `_extract_lark_text(value: Any) -> str`

- [ ] **Step 1: Write failing tests**

Add tests proving that the client paginates all Base records, updates exactly one matching `记录`, creates when no match exists, and raises on duplicate matching keys.

- [ ] **Step 2: Run focused tests and verify failure**

Run: `python -m pytest tests/test_community_metrics.py -q`

Expected: fail because `LarkBaseClient` and Base upsert behavior do not exist.

- [ ] **Step 3: Implement the Base client**

Use tenant token authentication with the existing `LARK_APP_ID` and `LARK_APP_SECRET`. Read records with `page_size=500` and `page_token`, compare text values after rich-text normalization, then `PUT /records/{record_id}` for one match or `POST /records` for no match. Treat two or more matches as an error before writing.

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest tests/test_community_metrics.py -q`

Expected: all community metric tests pass.

### Task 2: Daily and Weekly Base Record Mapping

**Files:**
- Modify: `cogs/community_metrics.py`
- Modify: `tests/test_community_metrics.py`

**Interfaces:**
- Produces: `_base_date_ms(day: datetime.date) -> int`
- Consumes: `LarkBaseClient.upsert_record(...)`

- [ ] **Step 1: Write failing rollup tests**

Replace Sheet-range assertions with exact Base field assertions for daily and weekly records. Verify `记录`, `统计类型`, Beijing-midnight `日期`, all common metrics, daily subscription additions, weekly reaction/role totals, and explicit `None` values for fields not applicable to that record type.

- [ ] **Step 2: Run focused tests and verify failure**

Run: `python -m pytest tests/test_community_metrics.py -q`

Expected: existing rollups still call Sheet row lookup/write methods.

- [ ] **Step 3: Replace the storage boundary**

Instantiate `LarkBaseClient` as `self.base`. Build complete 14-field dictionaries in `_write_daily` and `_write_weekly`, call `upsert_record`, and remove `LarkSheetClient`, Sheet range constants, date normalization used only for row lookup, and `_find_or_next_row`.

- [ ] **Step 4: Verify no legacy Sheet writes remain**

Run: `rg -n "LarkSheetClient|METRICS_SPREADSHEET_TOKEN|METRICS_SHEET_ID|write_values|read_values|_find_or_next_row" cogs/community_metrics.py tests/test_community_metrics.py`

Expected: no matches.

- [ ] **Step 5: Run focused and full tests**

Run: `python -m pytest tests/test_community_metrics.py -q`

Run: `python -m pytest -q`

Expected: all tests pass.

### Task 3: Review, Deploy, and Production Verification

**Files:**
- Modify: Railway production variables only if explicit Base token/table overrides are absent.

**Interfaces:**
- Produces: deployed Bot writing future rollups only to Lark Base.

- [ ] **Step 1: Run code review**

Review for duplicate creation, pagination, field-name accuracy, error handling, accidental Sheet writes, and unchanged scheduling/statistics.

- [ ] **Step 2: Re-run verification after review fixes**

Run: `python -m pytest -q`

Expected: zero failures.

- [ ] **Step 3: Commit and push the reviewed branch**

Commit only the Base cutover code, tests, and plan. Push the feature branch after verification.

- [ ] **Step 4: Deploy the Bot service**

Set `COMMUNITY_METRICS_BASE_APP_TOKEN=CeqtbxWt5azkkHs8OzpjZ9D1p2e` and `COMMUNITY_METRICS_BASE_TABLE_ID=tblMeRm8yocZPqUR` if not already present, then deploy the reviewed commit without changing other Railway variables.

- [ ] **Step 5: Verify production startup**

Confirm the CommunityMetrics cog starts without Lark or Discord errors. Do not manually trigger a rollup unless explicitly requested; the next scheduled 23:59 run performs the first production Base upsert.

