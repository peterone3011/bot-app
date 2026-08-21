# tests/test_updates.py
import datetime
import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
import cogs.updates as upd

_TODAY = datetime.date(2026, 5, 28)
_TS_TODAY  = 1779926400000  # 2026-05-28 00:00 UTC (BJT 08:00, date 2026-05-28)
_TS_YESTERDAY = 1779840000000
_TS_OLDER = 1779062400000
_TS_FUTURE = 1780531200000  # 2026-06-04 00:00 UTC


def test_updates_uses_feishu_api_configuration():
    assert upd.FEISHU_API_BASE == "https://open.feishu.cn/open-apis"
    assert hasattr(upd, "FEISHU_APP_ID")
    assert hasattr(upd, "FEISHU_APP_SECRET")
    assert hasattr(upd, "FEISHU_UPDATES_BASE_APP_TOKEN")
    assert hasattr(upd, "FEISHU_UPDATES_TABLE_ID")
    assert not hasattr(upd, "LARK_BASE")
    assert not hasattr(upd, "BITABLE_APP_TOKEN")


def _rec(ts=_TS_OLDER, status="待发布", content="text", has_image=False):
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

def test_is_due_yesterday():
    assert upd._is_due(_rec(ts=_TS_YESTERDAY), today=_TODAY) is True

def test_is_due_older_record():
    assert upd._is_due(_rec(ts=_TS_OLDER), today=_TODAY) is True

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
        _rec(ts=_TS_YESTERDAY, status="待发布"),
        _rec(ts=_TS_YESTERDAY, status="已发布"),
        _rec(ts=_TS_FUTURE, status="待发布"),
    ]
    due = [r for r in records if upd._is_due(r, today=_TODAY)]
    assert len(due) == 1


# -- Midnight scheduling ------------------------------------------------------

def _bjt(hour, minute, second=0):
    return datetime.datetime(2026, 7, 24, hour, minute, second, tzinfo=upd._BJT)


def test_slot_for_time_uses_latest_reached_slot():
    assert upd._slot_for_time(_bjt(0, 0)) is None
    assert upd._slot_for_time(_bjt(0, 1)) == datetime.time(0, 1)
    assert upd._slot_for_time(_bjt(0, 10)) == datetime.time(0, 6)
    assert upd._slot_for_time(_bjt(0, 20)) == datetime.time(0, 16)


def test_check_times_are_the_required_utc_midnight_slots():
    assert upd._CHECK_TIMES_UTC == [
        datetime.time(16, 1, tzinfo=upd._UTC),
        datetime.time(16, 6, tzinfo=upd._UTC),
        datetime.time(16, 16, tzinfo=upd._UTC),
    ]


def test_startup_window_is_midnight_only():
    assert upd._startup_window_contains(_bjt(0, 0))
    assert upd._startup_window_contains(_bjt(0, 30))
    assert not upd._startup_window_contains(_bjt(0, 30, 1))
    assert not upd._startup_window_contains(_bjt(12, 0))


def _make_cog(bot=None):
    cog = upd.UpdatesCog.__new__(upd.UpdatesCog)
    cog.bot = bot or Mock()
    cog._run_lock = asyncio.Lock()
    cog._completed_day = None
    cog._attempted_slots = set()
    cog._now_bjt = lambda: _bjt(0, 20)
    return cog


def _set_bjt_now(monkeypatch, now):
    real_datetime = datetime.datetime

    class FixedDateTime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return now if tz is None else now.astimezone(tz)

    monkeypatch.setattr(upd.datetime, "datetime", FixedDateTime)


class _Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


def test_success_stops_later_slots(monkeypatch):
    cog = _make_cog()
    do_post = AsyncMock(return_value=True)
    monkeypatch.setattr(cog, "_do_post", do_post)

    async def run():
        await cog._run_attempt(_bjt(0, 1), datetime.time(0, 1))
        await cog._run_attempt(_bjt(0, 6), datetime.time(0, 6))

    asyncio.run(run())
    do_post.assert_awaited_once_with(
        today=datetime.date(2026, 7, 24), deadline=_bjt(0, 30)
    )


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


def test_same_slot_concurrent_attempts_only_post_once(monkeypatch):
    cog = _make_cog()
    post_started = asyncio.Event()
    allow_post_to_finish = asyncio.Event()

    async def do_post(**kwargs):
        post_started.set()
        await allow_post_to_finish.wait()
        return False

    do_post_mock = AsyncMock(side_effect=do_post)
    monkeypatch.setattr(cog, "_do_post", do_post_mock)

    async def run():
        first = asyncio.create_task(
            cog._run_attempt(_bjt(0, 1), datetime.time(0, 1))
        )
        await post_started.wait()
        second = asyncio.create_task(
            cog._run_attempt(_bjt(0, 1), datetime.time(0, 1))
        )
        await asyncio.sleep(0)
        allow_post_to_finish.set()
        await asyncio.gather(first, second)

    asyncio.run(run())

    do_post_mock.assert_awaited_once_with(
        today=datetime.date(2026, 7, 24), deadline=_bjt(0, 30)
    )


def test_auto_post_ignores_delayed_daytime_callback(monkeypatch):
    cog = _make_cog()
    run_attempt = AsyncMock()
    monkeypatch.setattr(cog, "_run_attempt", run_attempt)
    _set_bjt_now(monkeypatch, _bjt(12, 0))

    asyncio.run(upd.UpdatesCog.auto_post.coro(cog))

    run_attempt.assert_not_awaited()


def test_startup_catchup_ignores_daytime(monkeypatch):
    cog = _make_cog()
    run_attempt = AsyncMock()
    monkeypatch.setattr(cog, "_run_attempt", run_attempt)
    _set_bjt_now(monkeypatch, _bjt(12, 0))

    asyncio.run(cog._run_startup_catchup())

    run_attempt.assert_not_awaited()


def test_startup_catchup_uses_latest_reached_slot(monkeypatch):
    cog = _make_cog()
    run_attempt = AsyncMock()
    monkeypatch.setattr(cog, "_run_attempt", run_attempt)
    now = _bjt(0, 7)
    _set_bjt_now(monkeypatch, now)

    asyncio.run(cog._run_startup_catchup())

    run_attempt.assert_awaited_once_with(now, datetime.time(0, 6))


def test_final_slot_failure_completes_without_external_alert(monkeypatch, capsys):
    cog = _make_cog()
    monkeypatch.setattr(cog, "_do_post", AsyncMock(return_value=False))
    send_alert = AsyncMock()
    monkeypatch.setattr(upd, "_send_feishu_dm", send_alert)

    asyncio.run(cog._run_attempt(_bjt(0, 16), datetime.time(0, 16)))

    send_alert.assert_not_awaited()
    assert cog._completed_day == datetime.date(2026, 7, 24)
    assert "Daily update 2026/07/24 failed after all midnight slots." in capsys.readouterr().out


def test_earlier_slot_failure_after_deadline_completes_without_external_alert(
    monkeypatch, capsys
):
    cog = _make_cog()
    clock = _Clock(_bjt(0, 1))
    monkeypatch.setattr(cog, "_now_bjt", clock)

    async def do_post(**kwargs):
        clock.now = _bjt(0, 30, 1)
        return False

    send_alert = AsyncMock()
    monkeypatch.setattr(cog, "_do_post", AsyncMock(side_effect=do_post))
    monkeypatch.setattr(upd, "_send_feishu_dm", send_alert)

    asyncio.run(cog._run_attempt(_bjt(0, 1), datetime.time(0, 1)))

    assert cog._completed_day == datetime.date(2026, 7, 24)
    send_alert.assert_not_awaited()
    assert "Daily update 2026/07/24 failed after all midnight slots." in capsys.readouterr().out


def test_final_slot_expired_while_waiting_for_lock_skips_bitable_read(monkeypatch, capsys):
    cog = _make_cog()
    clock = _Clock(_bjt(0, 16))
    monkeypatch.setattr(cog, "_now_bjt", clock)
    read_records = AsyncMock(return_value=[])
    send_alert = AsyncMock()
    monkeypatch.setattr(upd, "_read_bitable_records", read_records)
    monkeypatch.setattr(upd, "_send_feishu_dm", send_alert)

    async def run():
        await cog._run_lock.acquire()
        attempt = asyncio.create_task(
            cog._run_attempt(_bjt(0, 16), datetime.time(0, 16))
        )
        await asyncio.sleep(0)
        clock.now = _bjt(0, 30, 1)
        cog._run_lock.release()
        await attempt

    asyncio.run(run())

    read_records.assert_not_awaited()
    send_alert.assert_not_awaited()
    assert cog._completed_day == datetime.date(2026, 7, 24)
    assert "Daily update 2026/07/24 failed after all midnight slots." in capsys.readouterr().out


class _FakeMessage:
    id = 123


class _FakeChannel:
    async def send(self, **kwargs):
        return _FakeMessage()


class _FailingChannel(_FakeChannel):
    async def send(self, **kwargs):
        raise RuntimeError("Discord unavailable")


class _FakeBot:
    def __init__(self, channel):
        self.channel = channel

    def get_channel(self, channel_id):
        return self.channel


def _allow_fake_channel(monkeypatch):
    monkeypatch.setattr(upd.discord.abc, "Messageable", _FakeChannel)


def test_do_post_returns_true_after_successful_empty_read(monkeypatch):
    cog = _make_cog()
    monkeypatch.setattr(upd, "_read_bitable_records", AsyncMock(return_value=[]))

    assert asyncio.run(cog._do_post(today=_TODAY)) is True


def test_do_post_returns_true_after_successful_due_record(monkeypatch):
    _allow_fake_channel(monkeypatch)
    cog = _make_cog(_FakeBot(_FakeChannel()))
    monkeypatch.setattr(upd, "_read_bitable_records", AsyncMock(return_value=[_rec(_TS_YESTERDAY)]))
    monkeypatch.setattr(upd, "_update_record_status_with_retry", AsyncMock())

    assert asyncio.run(cog._do_post(today=_TODAY)) is True


def test_do_post_returns_false_after_read_failure(monkeypatch):
    cog = _make_cog()
    monkeypatch.setattr(
        upd, "_read_bitable_records", AsyncMock(side_effect=RuntimeError("read failed"))
    )

    assert asyncio.run(cog._do_post(today=_TODAY)) is False


def test_do_post_returns_false_after_malformed_record(monkeypatch):
    cog = _make_cog()
    monkeypatch.setattr(upd, "_read_bitable_records", AsyncMock(return_value=["not a record"]))

    assert asyncio.run(cog._do_post(today=_TODAY)) is False


def test_do_post_continues_after_malformed_filter_record(monkeypatch):
    _allow_fake_channel(monkeypatch)
    channel = _FakeChannel()
    cog = _make_cog(_FakeBot(channel))
    valid = _rec(_TS_YESTERDAY)
    valid["record_id"] = "recValid"
    update_status = AsyncMock()
    monkeypatch.setattr(
        upd, "_read_bitable_records", AsyncMock(return_value=["malformed", valid])
    )
    monkeypatch.setattr(upd, "_update_record_status_with_retry", update_status)

    assert asyncio.run(cog._do_post(today=_TODAY)) is False
    assert update_status.await_args_list == [
        (("recValid", upd._STATUS_POSTING),),
        (("recValid", upd._STATUS_DONE),),
    ]


def test_do_post_continues_after_pending_record_without_date(monkeypatch):
    _allow_fake_channel(monkeypatch)
    channel = _FakeChannel()
    cog = _make_cog(_FakeBot(channel))
    missing_date = _rec(_TS_YESTERDAY)
    missing_date["fields"].pop(upd._FLD_DATE)
    valid = _rec(_TS_YESTERDAY)
    valid["record_id"] = "recValid"
    update_status = AsyncMock()
    monkeypatch.setattr(
        upd, "_read_bitable_records", AsyncMock(return_value=[missing_date, valid])
    )
    monkeypatch.setattr(upd, "_update_record_status_with_retry", update_status)

    assert asyncio.run(cog._do_post(today=_TODAY)) is False
    assert update_status.await_args_list == [
        (("recValid", upd._STATUS_POSTING),),
        (("recValid", upd._STATUS_DONE),),
    ]


def test_do_post_restores_pending_without_sending_after_deadline(monkeypatch):
    _allow_fake_channel(monkeypatch)
    channel = _FakeChannel()
    channel.send = AsyncMock(return_value=_FakeMessage())
    cog = _make_cog(_FakeBot(channel))
    clock = _Clock(_bjt(0, 29, 59))
    monkeypatch.setattr(cog, "_now_bjt", clock)
    statuses = []

    async def update_status(record_id, status):
        statuses.append((record_id, status))
        if status == upd._STATUS_POSTING:
            clock.now = _bjt(0, 30, 1)

    monkeypatch.setattr(
        upd, "_read_bitable_records", AsyncMock(return_value=[_rec(_TS_YESTERDAY)])
    )
    monkeypatch.setattr(
        upd, "_update_record_status_with_retry", AsyncMock(side_effect=update_status)
    )

    assert asyncio.run(
        cog._do_post(today=_TODAY, deadline=_bjt(0, 30))
    ) is False
    channel.send.assert_not_awaited()
    assert statuses == [
        ("recABC", upd._STATUS_POSTING),
        ("recABC", upd._STATUS_PENDING),
    ]


def test_deadline_restore_failure_logs_without_external_alert(monkeypatch, capsys):
    _allow_fake_channel(monkeypatch)
    cog = _make_cog(_FakeBot(_FakeChannel()))
    clock = _Clock(_bjt(0, 29, 59))
    monkeypatch.setattr(cog, "_now_bjt", clock)

    async def update_status(record_id, status):
        if status == upd._STATUS_POSTING:
            clock.now = _bjt(0, 30, 1)
        elif status == upd._STATUS_PENDING:
            raise RuntimeError("restore failed")

    send_alert = AsyncMock()
    monkeypatch.setattr(
        upd, "_read_bitable_records", AsyncMock(return_value=[_rec(_TS_YESTERDAY)])
    )
    monkeypatch.setattr(upd, "_update_record_status_with_retry", AsyncMock(side_effect=update_status))
    monkeypatch.setattr(upd, "_send_feishu_dm", send_alert)

    assert asyncio.run(cog._do_post(today=_TODAY, deadline=_bjt(0, 30))) is False
    send_alert.assert_not_awaited()
    output = capsys.readouterr().out
    assert "Manual action required for record recABC" in output
    assert output.isascii()


def test_discord_failure_restore_failure_logs_without_external_alert(monkeypatch, capsys):
    _allow_fake_channel(monkeypatch)
    cog = _make_cog(_FakeBot(_FailingChannel()))

    async def update_status(record_id, status):
        if status == upd._STATUS_PENDING:
            raise RuntimeError("restore failed")

    send_alert = AsyncMock()
    monkeypatch.setattr(
        upd, "_read_bitable_records", AsyncMock(return_value=[_rec(_TS_YESTERDAY)])
    )
    monkeypatch.setattr(upd, "_update_record_status_with_retry", AsyncMock(side_effect=update_status))
    monkeypatch.setattr(upd, "_send_feishu_dm", send_alert)

    assert asyncio.run(cog._do_post(today=_TODAY)) is False
    send_alert.assert_not_awaited()
    output = capsys.readouterr().out
    assert "Manual action required for record recABC" in output
    assert output.isascii()


def test_do_post_preserves_posting_discord_done_inside_deadline(monkeypatch):
    _allow_fake_channel(monkeypatch)
    channel = _FakeChannel()
    channel.send = AsyncMock(return_value=_FakeMessage())
    cog = _make_cog(_FakeBot(channel))
    monkeypatch.setattr(cog, "_now_bjt", _Clock(_bjt(0, 29, 59)))
    update_status = AsyncMock()
    monkeypatch.setattr(
        upd, "_read_bitable_records", AsyncMock(return_value=[_rec(_TS_YESTERDAY)])
    )
    monkeypatch.setattr(upd, "_update_record_status_with_retry", update_status)

    assert asyncio.run(
        cog._do_post(today=_TODAY, deadline=_bjt(0, 30))
    ) is True
    channel.send.assert_awaited_once()
    assert update_status.await_args_list == [
        (("recABC", upd._STATUS_POSTING),),
        (("recABC", upd._STATUS_DONE),),
    ]


@pytest.mark.parametrize("exception", [OverflowError, OSError])
def test_is_due_skips_out_of_range_timestamp(exception, monkeypatch):
    real_datetime = datetime.datetime

    class RaisingDateTime(real_datetime):
        @classmethod
        def fromtimestamp(cls, timestamp, tz=None):
            raise exception("out of range")

    monkeypatch.setattr(upd.datetime, "datetime", RaisingDateTime)

    assert upd._is_due(_rec(ts=_TS_YESTERDAY), today=_TODAY) is False


@pytest.mark.parametrize("exception", [OverflowError, OSError])
def test_do_post_returns_false_for_out_of_range_record_date(exception, monkeypatch):
    real_datetime = datetime.datetime

    class RaisingDateTime(real_datetime):
        @classmethod
        def fromtimestamp(cls, timestamp, tz=None):
            raise exception("out of range")

    monkeypatch.setattr(upd.datetime, "datetime", RaisingDateTime)
    cog = _make_cog()
    monkeypatch.setattr(
        upd, "_read_bitable_records", AsyncMock(return_value=[_rec(_TS_YESTERDAY)])
    )

    assert asyncio.run(cog._do_post(today=_TODAY)) is False


def test_do_post_returns_false_when_channel_is_unavailable(monkeypatch):
    cog = _make_cog(_FakeBot(None))
    monkeypatch.setattr(upd, "_read_bitable_records", AsyncMock(return_value=[_rec(_TS_YESTERDAY)]))

    assert asyncio.run(cog._do_post(today=_TODAY)) is False


def test_do_post_returns_false_after_image_failure(monkeypatch):
    _allow_fake_channel(monkeypatch)
    cog = _make_cog(_FakeBot(_FakeChannel()))
    monkeypatch.setattr(
        upd, "_read_bitable_records", AsyncMock(return_value=[_rec(_TS_YESTERDAY, has_image=True)])
    )
    monkeypatch.setattr(
        upd, "_download_bitable_image", AsyncMock(side_effect=RuntimeError("image failed"))
    )

    assert asyncio.run(cog._do_post(today=_TODAY)) is False


def test_do_post_returns_false_after_posting_status_failure(monkeypatch):
    _allow_fake_channel(monkeypatch)
    cog = _make_cog(_FakeBot(_FakeChannel()))
    monkeypatch.setattr(upd, "_read_bitable_records", AsyncMock(return_value=[_rec(_TS_YESTERDAY)]))
    monkeypatch.setattr(
        upd,
        "_update_record_status_with_retry",
        AsyncMock(side_effect=RuntimeError("status failed")),
    )

    assert asyncio.run(cog._do_post(today=_TODAY)) is False


def test_do_post_returns_false_after_discord_send_failure(monkeypatch):
    _allow_fake_channel(monkeypatch)
    cog = _make_cog(_FakeBot(_FailingChannel()))
    monkeypatch.setattr(upd, "_read_bitable_records", AsyncMock(return_value=[_rec(_TS_YESTERDAY)]))
    monkeypatch.setattr(upd, "_update_record_status_with_retry", AsyncMock())

    assert asyncio.run(cog._do_post(today=_TODAY)) is False


def test_do_post_stops_after_done_status_failure(monkeypatch):
    _allow_fake_channel(monkeypatch)
    cog = _make_cog(_FakeBot(_FakeChannel()))
    monkeypatch.setattr(upd, "_read_bitable_records", AsyncMock(return_value=[_rec(_TS_YESTERDAY)]))
    monkeypatch.setattr(
        upd,
        "_update_record_status_with_retry",
        AsyncMock(side_effect=[None, RuntimeError("done status failed")]),
    )
    send_alert = AsyncMock()
    monkeypatch.setattr(upd, "_send_feishu_dm", send_alert)

    assert asyncio.run(cog._do_post(today=_TODAY)) is True
    send_alert.assert_awaited_once()


def test_do_post_continues_after_one_record_failure(monkeypatch):
    _allow_fake_channel(monkeypatch)
    channel = _FakeChannel()
    cog = _make_cog(_FakeBot(channel))
    failed = _rec(_TS_YESTERDAY)
    failed["record_id"] = "recFailure"
    succeeded = _rec(_TS_YESTERDAY)
    succeeded["record_id"] = "recSuccess"
    monkeypatch.setattr(
        upd, "_read_bitable_records", AsyncMock(return_value=[failed, succeeded])
    )

    async def update_status(record_id, status):
        if record_id == "recFailure" and status == upd._STATUS_POSTING:
            raise RuntimeError("write failed")

    update_status_mock = AsyncMock(side_effect=update_status)
    monkeypatch.setattr(upd, "_update_record_status_with_retry", update_status_mock)

    assert asyncio.run(cog._do_post(today=_TODAY)) is False
    assert update_status_mock.await_args_list[-2:] == [
        (("recSuccess", upd._STATUS_POSTING),),
        (("recSuccess", upd._STATUS_DONE),),
    ]
