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
    monkeypatch.setattr(db_module, "_activity_read_client", None)
    monkeypatch.setattr(db_module, "_activity_rpc_client", None)
    mock = MagicMock()
    monkeypatch.setattr(db_module, "_client", mock)
    monkeypatch.setattr(db_module, "_activity_read_client", mock)
    monkeypatch.setattr(db_module, "_activity_rpc_client", mock)
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


# --- load_roles ---

def test_load_roles_returns_rows(client):
    rows = [
        {"id": "uuid-1", "label": "📢 Exclusive Updates", "description": "...", "display_order": 0},
        {"id": "uuid-2", "label": "🎰Gaming Alerts", "description": "...", "display_order": 1},
    ]
    client.table.return_value.select.return_value.order.return_value.execute.return_value = make_response(rows)
    result = db_module.load_roles()
    assert result == rows
    client.table.assert_called_with("roles")


def test_load_roles_empty(client):
    client.table.return_value.select.return_value.order.return_value.execute.return_value = make_response([])
    assert db_module.load_roles() == []


# --- get_config ---

def test_get_config_found(client):
    client.table.return_value.select.return_value.eq.return_value.execute.return_value = make_response(
        [{"value": "🔔roles"}]
    )
    assert db_module.get_config("roles_channel_name") == "🔔roles"


def test_get_config_missing_returns_default(client):
    client.table.return_value.select.return_value.eq.return_value.execute.return_value = make_response([])
    assert db_module.get_config("nonexistent", "fallback") == "fallback"


# --- Activities ---

def _query_with(data):
    query = MagicMock()
    query.select.return_value = query
    query.eq.return_value = query
    query.limit.return_value = query
    query.order.return_value = query
    query.execute.return_value = make_response(data)
    return query


def test_get_activity_by_message_loads_ordered_questions(client):
    campaign_query = _query_with([{"id": "campaign-1", "status": "active"}])
    question_query = _query_with(
        [
            {"field_key": "discord_username", "position": 1},
            {"field_key": "fp_id", "position": 2},
        ]
    )
    client.table.side_effect = lambda table: {
        "activity_campaigns": campaign_query,
        "activity_questions": question_query,
    }[table]

    result = db_module.get_activity_by_message("123456789012345678")

    assert result == {
        "id": "campaign-1",
        "status": "active",
        "questions": [
            {"field_key": "discord_username", "position": 1},
            {"field_key": "fp_id", "position": 2},
        ],
    }
    campaign_query.eq.assert_called_once_with(
        "discord_message_id", "123456789012345678"
    )
    question_query.eq.assert_called_once_with("campaign_id", "campaign-1")
    question_query.order.assert_called_once_with("position")


def test_get_activity_by_message_returns_none_when_missing(client):
    campaign_query = _query_with([])
    client.table.return_value = campaign_query

    assert db_module.get_activity_by_message("999") is None


def test_claim_activity_reward_calls_atomic_rpc(client):
    rpc_query = MagicMock()
    rpc_query.execute.return_value = make_response(
        [{"outcome": "winner", "reward_code": "CODE-1"}]
    )
    client.rpc.return_value = rpc_query

    result = db_module.claim_activity_reward(
        campaign_id="campaign-1",
        discord_user_id="123",
        discord_username="player",
        answers={"fp_id": "FP1"},
        participant_key="FP1",
    )

    assert result == {"outcome": "winner", "reward_code": "CODE-1"}
    client.rpc.assert_called_once_with(
        "claim_activity_reward",
        {
            "p_campaign_id": "campaign-1",
            "p_discord_user_id": "123",
            "p_discord_username": "player",
            "p_answers": {"fp_id": "FP1"},
            "p_participant_key": "FP1",
        },
    )


def test_activity_read_and_rpc_clients_use_separate_postgrest_timeouts(monkeypatch):
    monkeypatch.setattr(db_module, "_activity_read_client", None)
    monkeypatch.setattr(db_module, "_activity_rpc_client", None)
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "service-key")
    created = []

    def create(_url, _key, *, options):
        created.append(options)
        return MagicMock()

    monkeypatch.setattr(db_module, "create_client", create)

    assert db_module.get_activity_read_client() is not db_module.get_activity_rpc_client()
    assert created[0].postgrest_client_timeout == db_module.ACTIVITY_DB_READ_TIMEOUT
    assert created[1].postgrest_client_timeout == db_module.ACTIVITY_DB_FUNCTION_TIMEOUT
