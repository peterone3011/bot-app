from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.cogs.daily_updates import DailyUpdatesCog, is_due, slot_for_time, startup_window_contains
from app.core.config import (
    ChannelConfig,
    DiscordConfig,
    FeatureFlags,
    FeishuConfig,
    ProjectConfig,
)
from app.core.runtime import ProjectRuntime
from app.core.state import ProjectState


BJT = timezone(timedelta(hours=8))


def runtime() -> ProjectRuntime:
    config = ProjectConfig(
        slug="alpha",
        brand_name="Alpha",
        discord=DiscordConfig("token", 101, (), ()),
        features=FeatureFlags(False, False, False, False, True, False),
        channels=ChannelConfig(None, None, 600, None),
        role_selector=None,
        auto_reactions=(),
        feishu=FeishuConfig("id", "secret", "updates-base", "updates-table", "metrics-base", "metrics-table"),
    )
    bot = SimpleNamespace(get_channel=lambda channel_id: None)
    return ProjectRuntime(config, bot, ProjectState(Path("/tmp"), "alpha"), SimpleNamespace())


def record(*, day: date, status: str = "待发布") -> dict:
    return {
        "record_id": "rec-1",
        "fields": {
            "日期": int(datetime.combine(day, datetime.min.time(), tzinfo=BJT).timestamp() * 1000),
            "状态": status,
            "发布文案": "Hello",
        },
    }


def test_due_record_must_be_pending_and_before_today() -> None:
    assert is_due(record(day=date(2026, 9, 14)), date(2026, 9, 15))
    assert not is_due(record(day=date(2026, 9, 15)), date(2026, 9, 15))
    assert not is_due(record(day=date(2026, 9, 14), status="已发布"), date(2026, 9, 15))


def test_startup_window_and_slot_use_bjt() -> None:
    assert startup_window_contains(datetime(2026, 9, 15, 0, 30, tzinfo=BJT))
    assert not startup_window_contains(datetime(2026, 9, 15, 0, 31, tzinfo=BJT))
    assert slot_for_time(datetime(2026, 9, 15, 0, 10, tzinfo=BJT)).minute == 6


@pytest.mark.asyncio
async def test_successful_first_slot_skips_later_reads(monkeypatch) -> None:
    cog = DailyUpdatesCog(runtime())
    calls: list[str] = []

    async def success(now):
        calls.append(now.strftime("%H:%M"))
        return True

    monkeypatch.setattr(cog, "publish_due_records", success)

    assert await cog.run_slot(datetime(2026, 9, 15, 0, 1, tzinfo=BJT))
    assert await cog.run_slot(datetime(2026, 9, 15, 0, 6, tzinfo=BJT))
    assert calls == ["00:01"]


@pytest.mark.asyncio
async def test_failed_slot_allows_next_slot_once(monkeypatch) -> None:
    cog = DailyUpdatesCog(runtime())
    calls: list[str] = []

    async def failure(now):
        calls.append(now.strftime("%H:%M"))
        return False

    monkeypatch.setattr(cog, "publish_due_records", failure)

    assert not await cog.run_slot(datetime(2026, 9, 15, 0, 1, tzinfo=BJT))
    assert not await cog.run_slot(datetime(2026, 9, 15, 0, 1, tzinfo=BJT))
    assert not await cog.run_slot(datetime(2026, 9, 15, 0, 6, tzinfo=BJT))
    assert calls == ["00:01", "00:06"]


@pytest.mark.asyncio
async def test_daytime_startup_does_not_read_feishu(monkeypatch) -> None:
    cog = DailyUpdatesCog(runtime())
    publish = AsyncMock(return_value=True)
    monkeypatch.setattr(cog, "publish_due_records", publish)

    assert not await cog.startup_catchup(datetime(2026, 9, 15, 12, 0, tzinfo=BJT))
    publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_status_writeback_failure_after_send_does_not_repeat_that_night(monkeypatch) -> None:
    active_runtime = runtime()
    sent_message = SimpleNamespace(id=123)
    channel = SimpleNamespace(send=AsyncMock(return_value=sent_message))
    active_runtime.bot.get_channel = lambda _: channel
    update_error = RuntimeError("temporary write failure")
    active_runtime.feishu = SimpleNamespace(
        list_records=AsyncMock(return_value=[record(day=date(2026, 9, 14))]),
        update_record=AsyncMock(side_effect=[None, update_error, update_error, update_error]),
    )
    cog = DailyUpdatesCog(active_runtime)
    monkeypatch.setattr("app.cogs.daily_updates.discord.abc.Messageable", SimpleNamespace)

    assert await cog.run_slot(datetime(2026, 9, 15, 0, 1, tzinfo=BJT))
    assert await cog.run_slot(datetime(2026, 9, 15, 0, 6, tzinfo=BJT))

    channel.send.assert_awaited_once_with(content="Hello")
