import asyncio
import datetime
import json
import uuid
from pathlib import Path

import cogs.community_metrics as cm
import pytest


def test_day_window_uses_bjt_calendar_day():
    day = datetime.date(2026, 7, 3)
    start, end = cm._day_window(day)
    assert start.isoformat() == "2026-07-03T00:00:00+08:00"
    assert end.isoformat() == "2026-07-04T00:00:00+08:00"


def test_rollup_time_is_2359_bjt():
    assert cm._ROLLUP_TIME_UTC.isoformat() == "15:59:00+00:00"


def test_count_events_filters_type_time_and_role():
    start = datetime.datetime(2026, 7, 3, 0, 0, tzinfo=cm._BJT)
    end = datetime.datetime(2026, 7, 4, 0, 0, tzinfo=cm._BJT)
    events = [
        {"type": "join", "ts": "2026-07-03T01:00:00+08:00"},
        {"type": "join", "ts": "2026-07-04T01:00:00+08:00"},
        {"type": "leave", "ts": "2026-07-03T02:00:00+08:00"},
        {"type": "role_subscribe", "role": "🎰Gaming Alerts", "ts": "2026-07-03T03:00:00+08:00"},
        {"type": "role_subscribe", "role": "Exclusive Updates", "ts": "2026-07-03T04:00:00+08:00"},
    ]
    assert cm._count_events(events, "join", start, end) == 1
    assert cm._count_events(events, "leave", start, end) == 1
    assert cm._count_events(events, "role_subscribe", start, end, "Gaming Alerts") == 1
    assert cm._count_events(events, "role_subscribe", start, end, "Exclusive Updates") == 1


def test_count_unique_role_subscribers_deduplicates_same_member():
    start = datetime.datetime(2026, 7, 3, 0, 0, tzinfo=cm._BJT)
    end = datetime.datetime(2026, 7, 4, 0, 0, tzinfo=cm._BJT)
    events = [
        {
            "type": "role_subscribe",
            "role": "🎰Gaming Alerts",
            "member_id": "1",
            "ts": "2026-07-03T03:00:00+08:00",
        },
        {
            "type": "role_subscribe",
            "role": "🎰Gaming Alerts",
            "member_id": "1",
            "ts": "2026-07-03T04:00:00+08:00",
        },
        {
            "type": "role_subscribe",
            "role": "🎰Gaming Alerts",
            "member_id": "2",
            "ts": "2026-07-03T05:00:00+08:00",
        },
    ]
    assert cm._count_unique_role_subscribers(events, start, end, "Gaming Alerts") == 2


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


def test_community_metrics_uses_feishu_api_configuration():
    assert cm.FEISHU_API_BASE == "https://open.feishu.cn/open-apis"
    assert hasattr(cm, "FEISHU_APP_ID")
    assert hasattr(cm, "FEISHU_APP_SECRET")
    assert hasattr(cm, "FEISHU_METRICS_BASE_APP_TOKEN")
    assert hasattr(cm, "FEISHU_METRICS_TABLE_ID")
    assert not hasattr(cm, "LARK_BASE")
    assert not hasattr(cm, "METRICS_BASE_APP_TOKEN")


class _FakeBase:
    def __init__(self):
        self.upserts = []

    async def upsert_record(self, key, fields):
        self.upserts.append((key, fields))
        return "created"


def _rollup_cog(monkeypatch, guild, events):
    cog = cm.CommunityMetricsCog.__new__(cm.CommunityMetricsCog)
    cog.bot = type("Bot", (), {"guilds": [guild]})()
    cog.base = _FakeBase()
    monkeypatch.setattr(cm, "_load_events", lambda: asyncio.sleep(0, result=events))
    monkeypatch.setattr(cm, "_queue_pending_rollup", lambda *_: asyncio.sleep(0))
    monkeypatch.setattr(cm, "_remove_pending_rollup", lambda *_: asyncio.sleep(0))
    return cog


def test_cog_has_no_weekly_rollup_task():
    assert not hasattr(cm.CommunityMetricsCog, "weekly_rollup")


def test_write_daily_excludes_role_subscription_fields(monkeypatch):
    guild = type("Guild", (), {"member_count": 540, "members": []})()
    events = [
        {"type": "join", "ts": "2026-07-28T01:00:00+08:00"},
        {"type": "role_subscribe", "role": "Lucky Drops", "member_id": "1", "ts": "2026-07-28T03:00:00+08:00"},
        {"type": "role_subscribe", "role": "Lucky Drops", "member_id": "1", "ts": "2026-07-28T04:00:00+08:00"},
    ]
    cog = _rollup_cog(monkeypatch, guild, events)

    asyncio.run(cog._write_daily(datetime.date(2026, 7, 28)))

    assert cog.base.upserts[-1] == (
        "2026/07/28",
        {
            "日期": "2026/07/28",
            "当前总人数": 540,
            "新增人数": 1,
            "离开人数": 0,
            "净增长": 1,
        },
    )


def test_base_client_paginates_and_updates_one_matching_record():
    client = cm.FeishuBaseClient()
    calls = []

    async def fake_request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        if method == "GET" and "page_token" not in kwargs.get("params", {}):
            return {
                "data": {
                    "items": [{"record_id": "other", "fields": {"日期": "2026/08/06"}}],
                    "has_more": True,
                    "page_token": "next-page",
                }
            }
        if method == "GET":
            return {
                "data": {
                    "items": [{"record_id": "target", "fields": {"日期": "2026/08/07"}}],
                    "has_more": False,
                }
            }
        return {"data": {}}

    client._request = fake_request
    result = asyncio.run(
        client.upsert_record("2026/08/07", {"日期": "2026/08/07", "当前总人数": 801})
    )

    assert result == "updated"
    assert calls[1][2]["params"]["page_token"] == "next-page"
    assert calls[-1] == (
        "PUT",
        f"/bitable/v1/apps/{cm.FEISHU_METRICS_BASE_APP_TOKEN}/tables/"
        f"{cm.FEISHU_METRICS_TABLE_ID}/records/target",
        {"json": {"fields": {"日期": "2026/08/07", "当前总人数": 801}}},
    )


def test_write_daily_queues_payload_after_final_base_failure(monkeypatch):
    guild = type("Guild", (), {"member_count": 540, "members": []})()
    cog = _rollup_cog(monkeypatch, guild, [])
    queued = []

    async def no_pending(_base):
        return 0

    async def fail_upsert(_base, _key, _fields):
        raise RuntimeError("Lark unavailable")

    async def queue(key, fields):
        queued.append((key, fields))

    monkeypatch.setattr(cm, "_flush_pending_rollups", no_pending)
    monkeypatch.setattr(cm, "_upsert_with_retry", fail_upsert)
    monkeypatch.setattr(cm, "_queue_pending_rollup", queue)

    asyncio.run(cog._write_daily(datetime.date(2026, 8, 7)))

    assert queued[0][0] == "2026/08/07"
    assert queued[0][1]["当前总人数"] == 540


def test_decode_feishu_response_rejects_non_json_and_api_errors():
    with pytest.raises(RuntimeError, match="non-JSON HTTP 502"):
        cm._decode_feishu_response("GET", 502, "upstream unavailable")

    with pytest.raises(RuntimeError, match="HTTP 401: invalid token"):
        cm._decode_feishu_response("GET", 401, '{"code": 99991663, "msg": "invalid token"}')

    assert cm._decode_feishu_response("GET", 200, '{"code": 0, "data": {"ok": true}}')[
        "data"
    ] == {"ok": True}


def test_base_client_creates_when_key_is_missing():
    client = cm.FeishuBaseClient()
    calls = []

    async def fake_request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        if method == "GET":
            return {"data": {"items": [], "has_more": False}}
        return {"data": {}}

    client._request = fake_request
    fields = {"日期": "2026/08/09", "新增人数": 3}

    result = asyncio.run(client.upsert_record("2026/08/09", fields))

    assert result == "created"
    assert calls[-1] == (
        "POST",
        f"/bitable/v1/apps/{cm.FEISHU_METRICS_BASE_APP_TOKEN}/tables/"
        f"{cm.FEISHU_METRICS_TABLE_ID}/records",
        {
            "params": {"client_token": cm._create_client_token("2026/08/09")},
            "json": {"fields": fields},
        },
    )


def test_base_client_rejects_duplicate_remote_keys_before_writing():
    client = cm.FeishuBaseClient()
    calls = []

    async def fake_request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return {
            "data": {
                "items": [
                    {"record_id": "one", "fields": {"日期": "2026/08/07"}},
                    {"record_id": "two", "fields": {"日期": "2026/08/07"}},
                ],
                "has_more": False,
            }
        }

    client._request = fake_request

    with pytest.raises(RuntimeError, match="duplicate Base records"):
        asyncio.run(client.upsert_record("2026/08/07", {"日期": "2026/08/07"}))

    assert [method for method, _, _ in calls] == ["GET"]


def test_create_client_token_is_stable_uuid4_per_record_key():
    first = cm._create_client_token("2026/08/07")
    second = cm._create_client_token("2026/08/07")
    other = cm._create_client_token("2026/08/08")

    assert first == second
    assert first != other
    assert uuid.UUID(first).version == 4


def test_upsert_retry_recovers_from_transient_failures():
    class FlakyBase:
        def __init__(self):
            self.attempts = 0

        async def upsert_record(self, key, fields):
            self.attempts += 1
            if self.attempts < 3:
                raise RuntimeError("temporary")
            return "created"

    base = FlakyBase()
    result = asyncio.run(
        cm._upsert_with_retry(base, "2026/08/07", {"日期": "2026/08/07"}, delays=(0, 0))
    )

    assert result == "created"
    assert base.attempts == 3


def test_pending_rollup_is_persisted_and_replayed(monkeypatch):
    pending_file = Path("work/test-community-metrics-pending.json")
    pending_file.parent.mkdir(exist_ok=True)
    pending_file.unlink(missing_ok=True)
    monkeypatch.setattr(cm, "_PENDING_ROLLUPS_FILE", pending_file)
    fields = {"日期": "2026/08/07", "当前总人数": 801}

    try:
        asyncio.run(cm._queue_pending_rollup("2026/08/07", fields))

        assert json.loads(pending_file.read_text(encoding="utf-8")) == {
            "2026/08/07": fields
        }

        class HealthyBase:
            async def upsert_record(self, key, payload):
                assert key == "2026/08/07"
                assert payload == fields
                return "created"

        asyncio.run(cm._flush_pending_rollups(HealthyBase(), delays=()))

        assert json.loads(pending_file.read_text(encoding="utf-8")) == {}
    finally:
        pending_file.unlink(missing_ok=True)
        pending_file.with_suffix(".lock").unlink(missing_ok=True)


def test_legacy_daily_pending_payload_is_normalized_for_single_date_schema(monkeypatch):
    pending_file = Path("work/test-community-metrics-legacy-pending.json")
    pending_file.parent.mkdir(exist_ok=True)
    pending_file.write_text(
        json.dumps(
            {
                "日报 2026/08/07": {
                    "记录": "日报 2026/08/07",
                    "日期": 1786032000000,
                    "当前总人数": 801,
                    "新增人数": 3,
                    "Gaming Alerts 新增订阅人数": 4,
                    "Exclusive Updates 新增订阅人数": 5,
                    "Lucky Drops 新增订阅人数": 6,
                },
                "周报 2026/08/02": {"记录": "周报 2026/08/02"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cm, "_PENDING_ROLLUPS_FILE", pending_file)

    try:
        assert cm._load_pending_rollups_sync() == {
            "2026/08/07": {
                "日期": "2026/08/07",
                "当前总人数": 801,
                "新增人数": 3,
            }
        }
    finally:
        pending_file.unlink(missing_ok=True)
        pending_file.with_suffix(".lock").unlink(missing_ok=True)


def test_removing_completed_rollup_preserves_newer_pending_payload(monkeypatch):
    pending_file = Path("work/test-community-metrics-newer-pending.json")
    pending_file.parent.mkdir(exist_ok=True)
    pending_file.unlink(missing_ok=True)
    monkeypatch.setattr(cm, "_PENDING_ROLLUPS_FILE", pending_file)
    key = "2026/08/07"
    old_fields = {"日期": key, "当前总人数": 800}
    new_fields = {"日期": key, "当前总人数": 801}

    try:
        asyncio.run(cm._queue_pending_rollup(key, old_fields))
        asyncio.run(cm._queue_pending_rollup(key, new_fields))
        asyncio.run(cm._remove_pending_rollup(key, old_fields))

        assert json.loads(pending_file.read_text(encoding="utf-8")) == {key: new_fields}
    finally:
        pending_file.unlink(missing_ok=True)
        pending_file.with_suffix(".lock").unlink(missing_ok=True)


def test_persisted_upsert_queues_before_remote_write_and_clears_after_success(monkeypatch):
    calls = []
    fields = {"日期": "2026/08/07", "当前总人数": 801}

    async def queue(key, payload):
        calls.append(("queue", key, payload))

    async def remove(key, payload):
        calls.append(("remove", key, payload))

    class Base:
        async def upsert_record(self, key, payload):
            calls.append(("upsert", key, payload))
            return "updated"

    monkeypatch.setattr(cm, "_queue_pending_rollup", queue)
    monkeypatch.setattr(cm, "_remove_pending_rollup", remove)

    result = asyncio.run(
        cm._persisted_upsert(Base(), "2026/08/07", fields, delays=())
    )

    assert result == "updated"
    assert [call[0] for call in calls] == ["queue", "upsert", "remove"]
