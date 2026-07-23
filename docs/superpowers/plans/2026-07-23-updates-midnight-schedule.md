# Updates Midnight Schedule Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the five-minute Lark Bitable polling loop with one Beijing-midnight check plus two failure-only retries, while ensuring only yesterday's records can publish.

**Architecture:** Keep scheduling and publishing inside `cogs/updates.py`, following the existing Discord cog pattern. Add pure time/date helpers, then use process-local completed-day and attempted-slot state behind an `asyncio.Lock`; `_do_post()` returns a boolean so the scheduler can stop after success or advance to the next fixed retry slot.

**Tech Stack:** Python 3, discord.py `tasks.loop`, asyncio, pytest, `unittest.mock.AsyncMock`

## Global Constraints

- Scheduled checks are Beijing time `00:01`, `00:06`, and `00:16`.
- The later two checks read Lark only when an earlier attempt failed.
- Only records whose date equals yesterday in Beijing time and whose status is `待发布` are eligible.
- Startup catch-up is allowed only from Beijing time `00:00` through `00:30`.
- Daytime startup must not read Lark or publish updates.
- Records that miss their one eligible midnight window must never be automatically backfilled.
- Daily attempt state is process-local; no Supabase table or external scheduler is added.
- Existing unrelated untracked files must not be staged or committed.

---

## File Structure

- Modify `cogs/updates.py`: date eligibility, schedule constants and helpers, process-local scheduling state, startup catch-up, and publish-attempt result.
- Modify `tests/test_updates.py`: date, time-window, retry, deduplication, and alert regression tests.
- Modify `README.md`: replace the obsolete five-minute polling and historical backfill descriptions.

### Task 1: Lock Eligibility to Yesterday

**Files:**
- Modify: `tests/test_updates.py`
- Modify: `cogs/updates.py`

**Interfaces:**
- Consumes: existing `_is_due(rec: dict, today: Optional[datetime.date] = None) -> bool`
- Produces: `_is_due()` that accepts the same arguments but returns true only for `record_date == today - datetime.timedelta(days=1)`

- [ ] **Step 1: Replace the past-date tests with exact-yesterday coverage**

Add timestamps for yesterday and older records, then assert that only yesterday is eligible:

```python
_TS_YESTERDAY = 1779840000000
_TS_OLDER = 1779062400000


def test_is_due_yesterday():
    assert upd._is_due(_rec(ts=_TS_YESTERDAY), today=_TODAY) is True


def test_is_due_older_record_is_not_backfilled():
    assert upd._is_due(_rec(ts=_TS_OLDER), today=_TODAY) is False
```

Keep the existing today, future, status, missing-date, and invalid-date tests. Update the multiple-record test so its one eligible record is dated yesterday.

- [ ] **Step 2: Run the focused tests and confirm the older-record test fails**

Run:

```powershell
python -m pytest tests/test_updates.py -q
```

Expected: `test_is_due_older_record_is_not_backfilled` fails because the current implementation accepts every date before today.

- [ ] **Step 3: Narrow `_is_due()` to yesterday**

Change the final comparison in `cogs/updates.py`:

```python
target_date = today - datetime.timedelta(days=1)
return record_date == target_date
```

Update the docstring to describe exact-yesterday eligibility.

- [ ] **Step 4: Run the focused tests**

Run:

```powershell
python -m pytest tests/test_updates.py -q
```

Expected: all update tests pass.

- [ ] **Step 5: Commit the eligibility change**

```powershell
git add -- cogs/updates.py tests/test_updates.py
git commit -m "fix: prevent historical update backfills"
```

### Task 2: Add Midnight Slots and Failure-Only Retries

**Files:**
- Modify: `tests/test_updates.py`
- Modify: `cogs/updates.py`

**Interfaces:**
- Produces: `_CHECK_TIMES_UTC: list[datetime.time]`
- Produces: `_startup_window_contains(now: datetime.datetime) -> bool`
- Produces: `_slot_for_time(now: datetime.datetime) -> Optional[datetime.time]`
- Produces: `UpdatesCog._run_attempt(now: datetime.datetime, slot: datetime.time) -> None`
- Produces: `UpdatesCog._run_startup_catchup() -> None`
- Changes: `UpdatesCog._do_post(today: Optional[datetime.date] = None) -> bool`

- [ ] **Step 1: Add failing pure scheduling tests**

Add tests proving slot selection and the startup boundary:

```python
def _bjt(hour, minute, second=0):
    return datetime.datetime(2026, 7, 24, hour, minute, second, tzinfo=upd._BJT)


def test_slot_for_time_uses_latest_reached_slot():
    assert upd._slot_for_time(_bjt(0, 0)) is None
    assert upd._slot_for_time(_bjt(0, 1)) == datetime.time(0, 1)
    assert upd._slot_for_time(_bjt(0, 10)) == datetime.time(0, 6)
    assert upd._slot_for_time(_bjt(0, 20)) == datetime.time(0, 16)


def test_startup_window_is_midnight_only():
    assert upd._startup_window_contains(_bjt(0, 0))
    assert upd._startup_window_contains(_bjt(0, 30))
    assert not upd._startup_window_contains(_bjt(0, 30, 1))
    assert not upd._startup_window_contains(_bjt(12, 0))
```

- [ ] **Step 2: Run the pure scheduling tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_updates.py -q
```

Expected: failures report that `_slot_for_time` and `_startup_window_contains` do not exist.

- [ ] **Step 3: Add schedule constants and pure helpers**

Replace `_POLL_MINUTES` with:

```python
_CHECK_SLOTS_BJT = (
    datetime.time(0, 1),
    datetime.time(0, 6),
    datetime.time(0, 16),
)
_CHECK_TIMES_UTC = [
    datetime.time(16, 1, tzinfo=_UTC),
    datetime.time(16, 6, tzinfo=_UTC),
    datetime.time(16, 16, tzinfo=_UTC),
]


def _startup_window_contains(now: datetime.datetime) -> bool:
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + datetime.timedelta(minutes=30)
    return start <= now <= end


def _slot_for_time(now: datetime.datetime) -> Optional[datetime.time]:
    current = now.time().replace(tzinfo=None)
    reached = [slot for slot in _CHECK_SLOTS_BJT if slot <= current]
    return reached[-1] if reached else None
```

- [ ] **Step 4: Add failing coordinator tests**

Use `UpdatesCog.__new__()` so the real background loop does not start. Initialize `_run_lock`, `_completed_day`, and `_attempted_slots` directly. Add async tests through `asyncio.run()` proving:

```python
def test_success_stops_later_slots(monkeypatch):
    cog = _make_cog()
    do_post = AsyncMock(return_value=True)
    monkeypatch.setattr(cog, "_do_post", do_post)

    async def run():
        await cog._run_attempt(_bjt(0, 1), datetime.time(0, 1))
        await cog._run_attempt(_bjt(0, 6), datetime.time(0, 6))

    asyncio.run(run())
    do_post.assert_awaited_once_with(today=datetime.date(2026, 7, 24))


def test_failure_allows_next_slot_but_not_duplicate_slot(monkeypatch):
    cog = _make_cog()
    do_post = AsyncMock(side_effect=[False, True])
    monkeypatch.setattr(cog, "_do_post", do_post)

    async def run():
        await cog._run_attempt(_bjt(0, 1), datetime.time(0, 1))
        await cog._run_attempt(_bjt(0, 1), datetime.time(0, 1))
        await cog._run_attempt(_bjt(0, 6), datetime.time(0, 6))

    asyncio.run(run())
    assert do_post.await_count == 2
```

Also add tests that:

- daytime `_run_startup_catchup()` never calls `_run_attempt()`;
- a `00:07` startup uses the `00:06` slot;
- final-slot failure calls `_send_lark_dm()`;
- `_do_post()` returns true for a successful empty read and false for read/channel/record failures.

- [ ] **Step 5: Run the coordinator tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_updates.py -q
```

Expected: failures show missing coordinator methods and `_do_post()` returning `None`.

- [ ] **Step 6: Implement process-local coordination**

In `UpdatesCog.__init__`, initialize:

```python
self._run_lock = asyncio.Lock()
self._completed_day: Optional[datetime.date] = None
self._attempted_slots: set[tuple[datetime.date, datetime.time]] = set()
```

Change the loop and coordinator:

```python
@tasks.loop(time=_CHECK_TIMES_UTC)
async def auto_post(self) -> None:
    now = datetime.datetime.now(_BJT)
    slot = _slot_for_time(now)
    if slot is not None:
        await self._run_attempt(now, slot)


async def _run_attempt(
    self, now: datetime.datetime, slot: datetime.time
) -> None:
    day = now.date()
    key = (day, slot)
    async with self._run_lock:
        if self._completed_day == day or key in self._attempted_slots:
            return
        self._attempted_slots = {
            attempted for attempted in self._attempted_slots
            if attempted[0] == day
        }
        self._attempted_slots.add(key)
        success = await self._do_post(today=day)
        if success:
            self._completed_day = day
            return
        if slot == _CHECK_SLOTS_BJT[-1]:
            self._completed_day = day
            note = (
                f"⚠️ 日常贴 {day:%Y/%m/%d} 凌晨发布未成功，"
                "已停止自动处理，请人工检查。"
            )
            print(f"[updates] {note}", flush=True)
            try:
                await _send_lark_dm(note)
            except Exception as exc:
                print(f"[updates] Failed to send final Lark alert: {exc}", flush=True)
```

Implement startup behavior:

```python
async def _run_startup_catchup(self) -> None:
    now = datetime.datetime.now(_BJT)
    if not _startup_window_contains(now):
        return
    first_check = now.replace(hour=0, minute=1, second=0, microsecond=0)
    if now < first_check:
        await asyncio.sleep((first_check - now).total_seconds())
        now = datetime.datetime.now(_BJT)
    slot = _slot_for_time(now)
    if slot is not None and _startup_window_contains(now):
        await self._run_attempt(now, slot)
```

Call `_run_startup_catchup()` after `wait_until_ready()` in `before_auto_post()`.

- [ ] **Step 7: Make `_do_post()` report success or retry**

Change `_do_post(today=None) -> bool`, pass `today` to `_is_due()`, return false for every caught read/channel/record failure, and return true only when the read succeeded and no eligible record remained incomplete. Preserve the existing `发布中 -> Discord -> 已发布` ordering and existing status-write retries.

- [ ] **Step 8: Run update tests and the complete Python suite**

Run:

```powershell
python -m pytest tests/test_updates.py -q
python -m pytest -q
```

Expected: all tests pass with no failures.

- [ ] **Step 9: Commit the scheduler**

```powershell
git add -- cogs/updates.py tests/test_updates.py
git commit -m "feat: schedule updates at Beijing midnight"
```

### Task 3: Update Operations Documentation and Verify

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: final behavior from Tasks 1 and 2
- Produces: operator documentation matching deployed behavior

- [ ] **Step 1: Update README runtime descriptions**

Change the architecture entry to:

```text
cogs/updates.py           Lark Bitable -> Discord midnight updates publisher
```

Change the runtime source note to:

```markdown
| Updates source | Lark Bitable | Bot checks at 00:01 BJT and retries failures at 00:06 / 00:16. |
```

Change the workflow note to:

```markdown
- **Updates**: `cogs/updates.py` checks Lark Bitable at Beijing midnight, publishes only yesterday's `待发布` records, retries failures twice, and marks successful records `已发布`.
```

- [ ] **Step 2: Run documentation and regression checks**

Run:

```powershell
git diff --check
python -m pytest -q
```

Expected: `git diff --check` exits 0 and the complete test suite passes.

- [ ] **Step 3: Review the final diff for scope and secrets**

Run:

```powershell
git diff -- cogs/updates.py tests/test_updates.py README.md
git status --short
```

Expected: only the three planned files are modified; unrelated untracked files remain unstaged; no token, secret, or environment value is added.

- [ ] **Step 4: Commit the README update**

```powershell
git add -- README.md
git commit -m "docs: document midnight update checks"
```

- [ ] **Step 5: Run final pre-push verification**

Run:

```powershell
python -m pytest -q
git status --short --branch
git log -4 --oneline
```

Expected: the test suite passes, only pre-existing unrelated untracked files remain, and the three new commits are visible.
