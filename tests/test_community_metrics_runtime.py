from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.cogs.community_metrics import CommunityMetricsCog, count_events, day_window
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


def runtime(tmp_path: Path) -> ProjectRuntime:
    config = ProjectConfig(
        slug="alpha",
        brand_name="Alpha",
        discord=DiscordConfig("token", 101, (), ()),
        features=FeatureFlags(False, False, False, False, False, True),
        channels=ChannelConfig(None, None, None, None),
        role_selector=None,
        auto_reactions=(),
        feishu=FeishuConfig("id", "secret", "updates-base", "updates-table", "metrics-base", "metrics-table"),
    )
    bot = SimpleNamespace(guilds=[SimpleNamespace(id=101, member_count=540, members=[])])
    client = SimpleNamespace(upsert_record_by_text_field=AsyncMock(return_value="created"))
    return ProjectRuntime(config, bot, ProjectState(tmp_path, "alpha"), client)


def test_count_events_uses_bjt_calendar_day() -> None:
    start, end = day_window(date(2026, 9, 15))
    events = [
        {"type": "join", "ts": datetime(2026, 9, 15, 0, 1, tzinfo=BJT).isoformat()},
        {"type": "join", "ts": datetime(2026, 9, 16, 0, 0, tzinfo=BJT).isoformat()},
    ]

    assert count_events(events, "join", start, end) == 1


@pytest.mark.asyncio
async def test_daily_rollup_writes_only_the_five_approved_fields(tmp_path: Path) -> None:
    active_runtime = runtime(tmp_path)
    cog = CommunityMetricsCog(active_runtime)
    await cog.record_event("join", member_id=1, at=datetime(2026, 9, 15, 10, tzinfo=BJT))
    await cog.record_event("join", member_id=2, at=datetime(2026, 9, 15, 11, tzinfo=BJT))
    await cog.record_event("leave", member_id=3, at=datetime(2026, 9, 15, 12, tzinfo=BJT))

    await cog.write_daily(date(2026, 9, 15))

    active_runtime.feishu.upsert_record_by_text_field.assert_awaited_once_with(
        "metrics-base",
        "metrics-table",
        "日期",
        "2026/09/15",
        {
            "日期": "2026/09/15",
            "当前总人数": 540,
            "新增人数": 2,
            "离开人数": 1,
            "净增长": 1,
        },
    )


@pytest.mark.asyncio
async def test_failed_rollup_is_retained_in_its_project_pending_file(tmp_path: Path) -> None:
    active_runtime = runtime(tmp_path)
    active_runtime.feishu.upsert_record_by_text_field.side_effect = RuntimeError("Feishu unavailable")
    cog = CommunityMetricsCog(active_runtime)

    await cog.write_daily(date(2026, 9, 15))

    assert active_runtime.state.pending_rollups_file.exists()
    assert "2026/09/15" in active_runtime.state.pending_rollups_file.read_text(encoding="utf-8")
    assert not (tmp_path / "beta" / "pending-rollups.json").exists()


@pytest.mark.asyncio
async def test_member_events_from_another_guild_are_ignored() -> None:
    cog = CommunityMetricsCog(runtime(Path("/tmp")))
    cog.record_event = AsyncMock()
    member = SimpleNamespace(bot=False, id=123, guild=SimpleNamespace(id=999))

    await cog.on_member_join(member)
    await cog.on_member_remove(member)

    cog.record_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_rollup_uses_its_configured_guild_not_the_first_guild() -> None:
    active_runtime = runtime(Path("/tmp"))
    active_runtime.bot.guilds = [
        SimpleNamespace(id=999, member_count=999, members=[]),
        SimpleNamespace(id=101, member_count=540, members=[]),
    ]

    cog = CommunityMetricsCog(active_runtime)
    cog._queue_pending = AsyncMock()
    cog._remove_pending = AsyncMock()

    await cog.write_daily(date(2026, 9, 15))

    fields = active_runtime.feishu.upsert_record_by_text_field.await_args.args[-1]
    assert fields["当前总人数"] == 540
