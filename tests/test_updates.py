# tests/test_updates.py
import datetime
import pytest
import cogs.updates as upd


# ── parse_rich_text ───────────────────────────────────────────────────────────

def test_parse_rich_text_none():
    assert upd.parse_rich_text(None) == ""

def test_parse_rich_text_plain_string():
    assert upd.parse_rich_text("Hello world") == "Hello world"

def test_parse_rich_text_array_text_nodes():
    nodes = [{"type": "text", "text": "Hello "}, {"type": "text", "text": "world"}]
    assert upd.parse_rich_text(nodes) == "Hello world"

def test_parse_rich_text_array_url_node_with_https():
    nodes = [{"type": "url", "link": "https://fortunepurple.com", "text": "click"}]
    assert upd.parse_rich_text(nodes) == "https://fortunepurple.com"

def test_parse_rich_text_array_url_node_without_https():
    nodes = [{"type": "url", "link": "fortunepurple.com", "text": "click"}]
    assert upd.parse_rich_text(nodes) == "https://fortunepurple.com"

def test_parse_rich_text_mixed_nodes():
    nodes = [
        {"type": "text", "text": "Play now: "},
        {"type": "url", "link": "fortunepurple.com", "text": "here"},
    ]
    assert upd.parse_rich_text(nodes) == "Play now: https://fortunepurple.com"


# ── get_image_token ───────────────────────────────────────────────────────────

def test_get_image_token_none():
    assert upd.get_image_token(None) is None

def test_get_image_token_wu():
    assert upd.get_image_token("无") is None

def test_get_image_token_empty_string():
    assert upd.get_image_token("") is None

def test_get_image_token_embed_image():
    cell = {"type": "embed-image", "fileToken": "abc123", "width": 1280, "height": 720}
    assert upd.get_image_token(cell) == "abc123"

def test_get_image_token_unknown_dict():
    assert upd.get_image_token({"type": "other"}) is None


# ── find_pending_row ──────────────────────────────────────────────────────────

_TODAY = datetime.date(2026, 5, 28)

def _make_rows(*data_rows):
    """Prepend title + header rows to match real Lark structure."""
    title = ["Fortune Purple · Discord", None, None, None, None, None, None]
    header = ["日期", "发布频道", "内容类型", "发布文案", "配图", "状态", "备注"]
    return [title, header] + list(data_rows)

def _row(date_str, channel="exclusive-updates", status="待发布", content="text", image=None):
    return [date_str, channel, "游戏上新", content, image or "无", status, None]


def test_find_pending_row_finds_due_row():
    rows = _make_rows(_row("2026-5-28 00:00"))
    result = upd.find_pending_row(rows, today=_TODAY)
    assert result is not None
    sheet_row, row = result
    assert sheet_row == 3  # index 2 → sheet row 3

def test_find_pending_row_finds_past_row():
    rows = _make_rows(_row("2026-5-20 00:00"))
    assert upd.find_pending_row(rows, today=_TODAY) is not None

def test_find_pending_row_skips_future():
    rows = _make_rows(_row("2026-6-1 00:00"))
    assert upd.find_pending_row(rows, today=_TODAY) is None

def test_find_pending_row_skips_published():
    rows = _make_rows(_row("2026-5-28 00:00", status="已发布"))
    assert upd.find_pending_row(rows, today=_TODAY) is None

def test_find_pending_row_skips_fabu_zhong():
    rows = _make_rows(_row("2026-5-28 00:00", status="发布中"))
    assert upd.find_pending_row(rows, today=_TODAY) is None

def test_find_pending_row_skips_wrong_channel():
    rows = _make_rows(_row("2026-5-28 00:00", channel="big-wins"))
    assert upd.find_pending_row(rows, today=_TODAY) is None

def test_find_pending_row_returns_first_due():
    rows = _make_rows(
        _row("2026-5-26 00:00"),
        _row("2026-5-28 00:00"),
    )
    sheet_row, _ = upd.find_pending_row(rows, today=_TODAY)
    assert sheet_row == 3  # first one

def test_find_pending_row_empty():
    assert upd.find_pending_row([], today=_TODAY) is None
