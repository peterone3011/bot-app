import asyncio
import datetime

import cogs.community_metrics as cm


def test_day_window_uses_bjt_calendar_day():
    day = datetime.date(2026, 7, 3)
    start, end = cm._day_window(day)
    assert start.isoformat() == "2026-07-03T00:00:00+08:00"
    assert end.isoformat() == "2026-07-04T00:00:00+08:00"


def test_week_window_starts_monday_and_covers_full_week():
    sunday = datetime.date(2026, 7, 5)
    start, end = cm._week_window(sunday)
    assert start.isoformat() == "2026-06-29T00:00:00+08:00"
    assert end.isoformat() == "2026-07-06T00:00:00+08:00"


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


def test_normalize_lark_serial_date():
    assert cm._normalize_sheet_date(46206) == "2026/07/03"
    assert cm._normalize_sheet_date("2026-07-03") == "2026/07/03"
    assert cm._normalize_sheet_date("2026/07/03") == "2026/07/03"


def test_format_sheet_date_uses_slashes():
    assert cm._format_sheet_date(datetime.date(2026, 7, 3)) == "2026/07/03"


def test_sheet_ranges_include_lucky_drops_columns():
    assert cm.DAILY_FIRST_COL == "A"
    assert cm.DAILY_LAST_COL == "H"
    assert cm.DAILY_RANGE_COLS == "A:H"
    assert cm.WEEKLY_FIRST_COL == "I"
    assert cm.WEEKLY_LAST_COL == "Q"
    assert cm.WEEKLY_RANGE_COLS == "I:Q"


class _FakeSheet:
    def __init__(self):
        self.writes = []

    async def read_values(self, range_name):
        return []

    async def write_values(self, range_name, values):
        self.writes.append((range_name, values))


def _rollup_cog(monkeypatch, guild, events):
    cog = cm.CommunityMetricsCog.__new__(cm.CommunityMetricsCog)
    cog.bot = type("Bot", (), {"guilds": [guild]})()
    cog.sheet = _FakeSheet()
    monkeypatch.setattr(cm, "_load_events", lambda: asyncio.sleep(0, result=events))
    cog._count_weekly_update_reactions = lambda start, end: asyncio.sleep(0, result=0)
    return cog


def test_write_daily_includes_unique_lucky_drops_subscribers(monkeypatch):
    guild = type("Guild", (), {"member_count": 540, "members": []})()
    events = [
        {"type": "join", "ts": "2026-07-28T01:00:00+08:00"},
        {"type": "role_subscribe", "role": "Lucky Drops", "member_id": "1", "ts": "2026-07-28T03:00:00+08:00"},
        {"type": "role_subscribe", "role": "Lucky Drops", "member_id": "1", "ts": "2026-07-28T04:00:00+08:00"},
    ]
    cog = _rollup_cog(monkeypatch, guild, events)

    asyncio.run(cog._write_daily(datetime.date(2026, 7, 28)))

    assert cog.sheet.writes[-1] == (
        f"{cm.METRICS_SHEET_ID}!A2:H2",
        [["2026/07/28", 540, 1, 0, 1, 0, 0, 1]],
    )


def test_write_weekly_includes_current_lucky_drops_member_count(monkeypatch):
    roles = [
        type("Role", (), {"name": "Gaming Alerts", "members": [1, 2]})(),
        type("Role", (), {"name": "Exclusive Updates", "members": [1, 2, 3]})(),
        type("Role", (), {"name": "Lucky Drops", "members": [1, 2, 3, 4]})(),
    ]
    guild = type("Guild", (), {"member_count": 540, "members": [], "roles": roles})()
    cog = _rollup_cog(
        monkeypatch,
        guild,
        [{"type": "join", "ts": "2026-07-28T01:00:00+08:00"}],
    )

    asyncio.run(cog._write_weekly(datetime.date(2026, 8, 2)))

    assert cog.sheet.writes[-1] == (
        f"{cm.METRICS_SHEET_ID}!I2:Q2",
        [["2026/08/02", 540, 1, 0, 1, 0, 2, 3, 4]],
    )


class _FakeReaction:
    def __init__(self, users):
        self._users = users

    async def _iter_users(self):
        for user in self._users:
            yield user

    def users(self, limit=None):
        return self._iter_users()


class _FakeUser:
    def __init__(self, bot):
        self.bot = bot


def test_count_human_reaction_users_excludes_bots():
    reaction = _FakeReaction([_FakeUser(bot=True), _FakeUser(bot=False), _FakeUser(bot=False)])
    assert asyncio.run(cm._count_human_reaction_users(reaction)) == 2
