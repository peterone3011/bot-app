# tests/test_updates.py
import datetime
import pytest
import cogs.updates as upd

_TODAY = datetime.date(2026, 5, 28)
_TS_TODAY  = 1779926400000  # 2026-05-28 00:00 UTC (BJT 08:00, date 2026-05-28)
_TS_PAST   = 1779062400000  # 2026-05-18 00:00 UTC
_TS_FUTURE = 1780531200000  # 2026-06-04 00:00 UTC


def _rec(ts=_TS_PAST, status="待发布", content="text", has_image=False):
    fields = {
        upd._FLD_DATE: str(ts),
        upd._FLD_STATUS: status,
        upd._FLD_CONTENT: content,
    }
    if has_image:
        fields[upd._FLD_IMAGE] = [{"url": "https://example.com/img.png", "file_token": "tok"}]
    return {"record_id": "recABC", "fields": fields}


# ── _extract_text ─────────────────────────────────────────────────────────────

def test_extract_text_none():
    assert upd._extract_text(None) == ""

def test_extract_text_string():
    assert upd._extract_text("hello") == "hello"

def test_extract_text_rich_list():
    nodes = [{"text": "Hello "}, {"text": "world"}]
    assert upd._extract_text(nodes) == "Hello world"

def test_extract_text_skips_non_dict():
    assert upd._extract_text(["a", {"text": "b"}]) == "b"


# ── _is_due ───────────────────────────────────────────────────────────────────

def test_is_due_past_date():
    assert upd._is_due(_rec(ts=_TS_PAST), today=_TODAY) is True

def test_is_due_today_not_yet():
    # record dated today → not due until tomorrow's poll
    assert upd._is_due(_rec(ts=_TS_TODAY), today=_TODAY) is False

def test_is_due_future_skipped():
    assert upd._is_due(_rec(ts=_TS_FUTURE), today=_TODAY) is False

def test_is_due_skips_published():
    assert upd._is_due(_rec(status="已发布"), today=_TODAY) is False

def test_is_due_skips_missing_date():
    rec = {"record_id": "recX", "fields": {upd._FLD_STATUS: "待发布"}}
    assert upd._is_due(rec, today=_TODAY) is False

def test_is_due_invalid_timestamp():
    rec = _rec()
    rec["fields"][upd._FLD_DATE] = "not-a-number"
    assert upd._is_due(rec, today=_TODAY) is False

def test_is_due_multiple_records_filtered():
    records = [
        _rec(ts=_TS_PAST, status="待发布"),
        _rec(ts=_TS_PAST, status="已发布"),
        _rec(ts=_TS_FUTURE, status="待发布"),
    ]
    due = [r for r in records if upd._is_due(r, today=_TODAY)]
    assert len(due) == 1
