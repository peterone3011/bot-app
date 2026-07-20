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


def test_normalize_lark_serial_date():
    assert cm._normalize_sheet_date(46206) == "2026/07/03"
    assert cm._normalize_sheet_date("2026-07-03") == "2026/07/03"
    assert cm._normalize_sheet_date("2026/07/03") == "2026/07/03"


def test_format_sheet_date_uses_slashes():
    assert cm._format_sheet_date(datetime.date(2026, 7, 3)) == "2026/07/03"


def test_weekly_sheet_range_matches_current_layout():
    assert cm.WEEKLY_FIRST_COL == "I"
    assert cm.WEEKLY_LAST_COL == "P"
    assert cm.WEEKLY_RANGE_COLS == "I:P"


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
