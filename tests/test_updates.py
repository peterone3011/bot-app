# tests/test_updates.py
import datetime
import pytest
import cogs.updates as upd

_TODAY = datetime.date(2026, 5, 28)
_TS_TODAY  = 1779926400000  # 2026-05-28 00:00 UTC (BJT 08:00, date 2026-05-28)
_TS_PAST   = 1779062400000  # 2026-05-18 00:00 UTC
_TS_FUTURE = 1780531200000  # 2026-06-04 00:00 UTC


def _rec(ts=_TS_TODAY, status="待发布", content="text", has_image=False):
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


# ── find_pending_record ───────────────────────────────────────────────────────

def test_find_pending_record_due_today_not_sent_yet():
    # record dated today → sent tomorrow midnight, not today
    result = upd.find_pending_record([_rec(ts=_TS_TODAY)], today=_TODAY)
    assert result is None

def test_find_pending_record_past_date():
    # record dated yesterday or earlier → sent at today's midnight run
    result = upd.find_pending_record([_rec(ts=_TS_PAST)], today=_TODAY)
    assert result is not None

def test_find_pending_record_future_skipped():
    result = upd.find_pending_record([_rec(ts=_TS_FUTURE)], today=_TODAY)
    assert result is None

def test_find_pending_record_skips_published():
    result = upd.find_pending_record([_rec(status="已发布")], today=_TODAY)
    assert result is None

def test_find_pending_record_skips_posting():
    result = upd.find_pending_record([_rec(status="发布中")], today=_TODAY)
    assert result is None

def test_find_pending_record_returns_first():
    records = [_rec(ts=_TS_PAST), _rec(ts=_TS_TODAY)]
    record_id, _ = upd.find_pending_record(records, today=_TODAY)
    assert record_id == "recABC"

def test_find_pending_record_empty():
    assert upd.find_pending_record([], today=_TODAY) is None

def test_find_pending_record_missing_date():
    rec = {"record_id": "recX", "fields": {upd._FLD_STATUS: "待发布"}}
    assert upd.find_pending_record([rec], today=_TODAY) is None
