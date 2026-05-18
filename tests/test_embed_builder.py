import json
import pytest
import cogs.embed_builder as eb


def test_new_draft_structure():
    draft = eb.new_draft(123456789)
    assert draft["status"] == "draft"
    assert draft["channel_id"] == 123456789
    assert draft["label"] is None
    assert draft["title"] is None
    assert draft["send_at"] is None
    assert draft["message_id"] is None
    assert "id" in draft
    assert "created_at" in draft


def test_new_draft_with_label():
    draft = eb.new_draft(111, label="May Announcement")
    assert draft["label"] == "May Announcement"


def test_load_messages_returns_empty_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(eb, "MESSAGES_FILE", tmp_path / "messages.json")
    result = eb.load_messages()
    assert result == []


def test_upsert_inserts_new(tmp_path, monkeypatch):
    monkeypatch.setattr(eb, "MESSAGES_FILE", tmp_path / "messages.json")
    draft = eb.new_draft(111)
    eb.upsert_message(draft)
    assert eb.load_messages() == [draft]


def test_upsert_updates_existing(tmp_path, monkeypatch):
    monkeypatch.setattr(eb, "MESSAGES_FILE", tmp_path / "messages.json")
    draft = eb.new_draft(111)
    eb.upsert_message(draft)
    draft["title"] = "Updated"
    eb.upsert_message(draft)
    messages = eb.load_messages()
    assert len(messages) == 1
    assert messages[0]["title"] == "Updated"


def test_get_message(tmp_path, monkeypatch):
    monkeypatch.setattr(eb, "MESSAGES_FILE", tmp_path / "messages.json")
    draft = eb.new_draft(222)
    eb.upsert_message(draft)
    found = eb.get_message(draft["id"])
    assert found["channel_id"] == 222


def test_get_message_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(eb, "MESSAGES_FILE", tmp_path / "messages.json")
    assert eb.get_message("nonexistent-id") is None


def test_delete_message(tmp_path, monkeypatch):
    monkeypatch.setattr(eb, "MESSAGES_FILE", tmp_path / "messages.json")
    draft = eb.new_draft(333)
    eb.upsert_message(draft)
    eb.delete_message(draft["id"])
    assert eb.get_message(draft["id"]) is None


def test_delete_nonexistent_is_safe(tmp_path, monkeypatch):
    monkeypatch.setattr(eb, "MESSAGES_FILE", tmp_path / "messages.json")
    eb.delete_message("does-not-exist")  # must not raise
