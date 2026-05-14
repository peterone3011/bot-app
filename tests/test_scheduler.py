import pytest
from datetime import datetime, timezone, timedelta
from cogs.scheduler import parse_time, load_messages, save_messages, is_due, TZ_CST

def test_parse_time_valid():
    result = parse_time("2026-05-15 20:00")
    assert result == datetime(2026, 5, 15, 20, 0, tzinfo=TZ_CST)

def test_parse_time_strips_whitespace():
    result = parse_time("  2026-05-15 20:00  ")
    assert result == datetime(2026, 5, 15, 20, 0, tzinfo=TZ_CST)

def test_parse_time_invalid_format():
    assert parse_time("not a date") is None

def test_parse_time_wrong_separator():
    assert parse_time("2026/05/15 20:00") is None


def test_load_messages_missing_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert load_messages() == []

def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    messages = [{
        "id": "abc123",
        "channel_id": 111,
        "send_at": "2026-05-15T20:00:00+08:00",
        "content": "hello",
        "image_url": None,
    }]
    save_messages(messages)
    assert load_messages() == messages

def test_is_due_past_message():
    assert is_due({"send_at": "2020-01-01T00:00:00+08:00"}) is True

def test_is_due_future_message():
    assert is_due({"send_at": "2099-01-01T00:00:00+08:00"}) is False
