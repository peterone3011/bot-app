# Lucky Drops Metrics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add daily new-subscriber and weekly current-member metrics for the Lucky Drops Discord role.

**Architecture:** Reuse the existing generic `role_subscribe` event stream for the daily unique count and the existing Discord role lookup for the weekly snapshot. Extend only the existing Lark row payloads and ranges, so schedules and request counts remain unchanged.

**Tech Stack:** Python 3, discord.py, aiohttp, pytest, Lark Sheets API

## Global Constraints

- Keep the daily rollup at 23:59 Beijing time.
- Keep the weekly rollup at 23:59 Beijing time on Sunday.
- Preserve columns A:G and I:P without changing their meaning or position.
- Add the daily Lucky Drops metric in H and the weekly Lucky Drops metric in Q.
- Do not add scheduled jobs, Lark API requests, dependencies, or migrations.

---

### Task 1: Extend Community Metrics Rollups

**Files:**
- Modify: `cogs/community_metrics.py`
- Modify: `tests/test_community_metrics.py`

**Interfaces:**
- Consumes: `record_metric_event("role_subscribe", member_id=..., role=...)`, `_count_unique_role_subscribers(...)`, `_find_role(...)`, and `LarkSheetClient`.
- Produces: `LUCKY_DROPS_ROLE_NAME`, daily range `A:H`, weekly range `I:Q`, and row payloads containing the Lucky Drops values in their final position.

- [ ] **Step 1: Add failing sheet-range and rollup tests**

Add a Lucky Drops event to the unique-subscriber test and assert it can be
counted independently:

```python
def test_count_unique_lucky_drops_subscribers():
    start = datetime.datetime(2026, 7, 28, 0, 0, tzinfo=cm._BJT)
    end = datetime.datetime(2026, 7, 29, 0, 0, tzinfo=cm._BJT)
    events = [
        {
            "type": "role_subscribe",
            "role": "Lucky Drops",
            "member_id": "1",
            "ts": "2026-07-28T03:00:00+08:00",
        },
        {
            "type": "role_subscribe",
            "role": "Lucky Drops",
            "member_id": "1",
            "ts": "2026-07-28T04:00:00+08:00",
        },
    ]
    assert cm._count_unique_role_subscribers(events, start, end, "Lucky Drops") == 1
```

Update the range contract:

```python
def test_sheet_ranges_include_lucky_drops_columns():
    assert cm.DAILY_FIRST_COL == "A"
    assert cm.DAILY_LAST_COL == "H"
    assert cm.DAILY_RANGE_COLS == "A:H"
    assert cm.WEEKLY_FIRST_COL == "I"
    assert cm.WEEKLY_LAST_COL == "Q"
    assert cm.WEEKLY_RANGE_COLS == "I:Q"
```

Add async rollup tests using a fake sheet and guild. The daily assertion must
verify that the final value is the unique Lucky Drops subscriber count and the
weekly assertion must verify that the final value is the current Lucky Drops
role member count:

```python
assert sheet.writes[-1] == (
    f"{cm.METRICS_SHEET_ID}!A2:H2",
    [["2026/07/28", 540, 1, 0, 1, 0, 0, 1]],
)

assert sheet.writes[-1] == (
    f"{cm.METRICS_SHEET_ID}!I2:Q2",
    [["2026/08/02", 540, 1, 0, 1, 0, 2, 3, 4]],
)
```

- [ ] **Step 2: Run the focused tests and confirm failure**

Run:

```powershell
python -m pytest tests/test_community_metrics.py -q
```

Expected: failures for missing daily constants, the old `P` weekly end column,
and row payloads that do not yet include Lucky Drops.

- [ ] **Step 3: Implement the minimum rollup changes**

Add the role configuration and sheet range constants:

```python
LUCKY_DROPS_ROLE_NAME = os.getenv(
    "METRICS_LUCKY_DROPS_ROLE_NAME",
    "Lucky Drops",
)
DAILY_FIRST_COL = "A"
DAILY_LAST_COL = "H"
DAILY_RANGE_COLS = "A:H"
WEEKLY_FIRST_COL = "I"
WEEKLY_LAST_COL = "Q"
WEEKLY_RANGE_COLS = "I:Q"
```

In `_write_daily`, count unique Lucky Drops subscribers with
`_count_unique_role_subscribers`, append the result after Exclusive Updates,
and use the daily constants for lookup and writing:

```python
lucky_drops_subs = _count_unique_role_subscribers(
    events,
    start,
    end,
    LUCKY_DROPS_ROLE_NAME,
)

row = [
    sheet_date,
    total_members,
    joins,
    leaves,
    joins - leaves,
    gaming_subs,
    updates_subs,
    lucky_drops_subs,
]
```

In `_write_weekly`, find the Lucky Drops role and append its current member
count:

```python
lucky_drops_role = _find_role(guild, LUCKY_DROPS_ROLE_NAME)

row = [
    sheet_date,
    total_members,
    joins,
    leaves,
    joins - leaves,
    reaction_count,
    len(gaming_role.members) if gaming_role else 0,
    len(updates_role.members) if updates_role else 0,
    len(lucky_drops_role.members) if lucky_drops_role else 0,
]
```

- [ ] **Step 4: Run focused and full verification**

Run:

```powershell
python -m pytest tests/test_community_metrics.py tests/test_roles.py -q
python -m pytest tests -q
git diff --check
```

Expected: all tests pass and `git diff --check` produces no errors.

- [ ] **Step 5: Review and commit**

Review the diff specifically for accidental schedule, API-client, or existing
column changes. Then commit only the intended files:

```powershell
git add cogs/community_metrics.py tests/test_community_metrics.py docs/superpowers/plans/2026-07-28-lucky-drops-metrics.md
git commit -m "feat: track Lucky Drops community metrics"
```

- [ ] **Step 6: Push and verify deployment**

Run:

```powershell
git push
```

Verify that the Railway deployment for the bot reaches a successful state and
that startup logs show the community metrics cog loaded without errors.

After deployment, set the Lark headers:

- H1: `Lucky Drops 今日新增订阅人数`
- Q1: `Lucky Drops 当前总订阅人数`
