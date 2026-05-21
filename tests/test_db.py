from unittest.mock import MagicMock
import pytest
import cogs.db as db_module


def make_response(data):
    m = MagicMock()
    m.data = data
    return m


@pytest.fixture
def client(monkeypatch):
    # Reset singleton, then inject mock
    monkeypatch.setattr(db_module, "_client", None)
    mock = MagicMock()
    monkeypatch.setattr(db_module, "_client", mock)
    return mock


# --- get_client env-var fail-fast ---

def test_get_client_missing_url_raises(monkeypatch):
    monkeypatch.setattr(db_module, "_client", None)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    with pytest.raises(KeyError):
        db_module.get_client()


def test_get_client_missing_key_raises(monkeypatch):
    monkeypatch.setattr(db_module, "_client", None)
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    with pytest.raises(KeyError):
        db_module.get_client()


# --- load_messages ---

def test_load_messages_empty(client):
    client.table.return_value.select.return_value.execute.return_value = make_response([])
    assert db_module.load_messages() == []


def test_load_messages_returns_rows(client):
    rows = [{"id": "a", "title": "Hello", "status": "draft"}]
    client.table.return_value.select.return_value.execute.return_value = make_response(rows)
    assert db_module.load_messages() == rows


# --- get_message ---

def test_get_message_found(client):
    row = {"id": "abc", "title": "Test"}
    client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = make_response([row])
    assert db_module.get_message("abc") == row


def test_get_message_not_found(client):
    client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = make_response([])
    assert db_module.get_message("missing") is None


# --- upsert_message ---

def test_upsert_message_calls_upsert(client):
    msg = {"id": "abc", "title": "T", "status": "draft"}
    db_module.upsert_message(msg)
    client.table.assert_called_with("messages")
    client.table.return_value.upsert.assert_called_with(msg)


# --- delete_message ---

def test_delete_message_calls_delete(client):
    db_module.delete_message("abc")
    client.table.return_value.delete.return_value.eq.assert_called_with("id", "abc")


# --- load_sites ---

def test_load_sites_returns_names(client):
    rows = [{"name": "Fortune Purple"}, {"name": "Site 2"}]
    client.table.return_value.select.return_value.order.return_value.execute.return_value = make_response(rows)
    assert db_module.load_sites() == ["Fortune Purple", "Site 2"]


def test_load_sites_empty(client):
    client.table.return_value.select.return_value.order.return_value.execute.return_value = make_response([])
    assert db_module.load_sites() == []


# --- get_config ---

def test_get_config_found(client):
    client.table.return_value.select.return_value.eq.return_value.execute.return_value = make_response(
        [{"value": "🔔roles"}]
    )
    assert db_module.get_config("roles_channel_name") == "🔔roles"


def test_get_config_missing_returns_default(client):
    client.table.return_value.select.return_value.eq.return_value.execute.return_value = make_response([])
    assert db_module.get_config("nonexistent", "fallback") == "fallback"
