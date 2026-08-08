import asyncio
import datetime
import copy

import pytest

from scripts.migrate_community_metrics_to_base import (
    FIELD_DEFINITIONS,
    LarkMigrationClient,
    MigrationReport,
    _record_differs,
    build_migration_records,
    normalize_date,
    run_migration,
    validate_migration_records,
)


def _header() -> list[str]:
    return [f"col-{index}" for index in range(17)]


def test_normalize_date_supports_sheet_serial_and_text() -> None:
    assert normalize_date(46187) == datetime.date(2026, 6, 14)
    assert normalize_date("2026/08/06") == datetime.date(2026, 8, 6)
    assert normalize_date("2026-08-06") == datetime.date(2026, 8, 6)
    assert normalize_date("") is None


def test_record_comparison_accepts_numeric_strings_returned_by_lark() -> None:
    remote = {"当前总人数": "57", "净增长": "-2", "记录": "日报 2026/06/14"}
    expected = {"当前总人数": 57, "净增长": -2, "记录": "日报 2026/06/14"}

    assert _record_differs(remote, expected) is False


def test_record_comparison_detects_value_that_should_be_cleared() -> None:
    assert _record_differs({"新增人数": "99"}, {"新增人数": None}) is True


def test_build_records_maps_daily_and_weekly_sections() -> None:
    rows = [
        _header(),
        [
            "2026/08/02",
            759,
            2,
            4,
            -2,
            1,
            1,
            0,
            "2026/08/02",
            759,
            39,
            18,
            21,
            27,
            94,
            140,
            55,
        ],
    ]

    records = build_migration_records(rows)

    assert [record["记录"] for record in records] == [
        "日报 2026/08/02",
        "周报 2026/08/02",
    ]
    daily, weekly = records
    assert daily["统计类型"] == "日报"
    assert daily["当前总人数"] == 759
    assert daily["净增长"] == -2
    assert daily["Lucky Drops 新增订阅人数"] == 0
    assert daily["本周贴文 Reaction 数"] is None
    assert weekly["统计类型"] == "周报"
    assert weekly["本周贴文 Reaction 数"] == 27
    assert weekly["Lucky Drops 总订阅人数"] == 55
    assert weekly["Gaming Alerts 新增订阅人数"] is None


def test_build_records_omits_slashes_and_empty_values() -> None:
    rows = [
        _header(),
        [46187, 57, "/", "/", "/", "/", "/", ""],
    ]

    [record] = build_migration_records(rows)

    assert record["记录"] == "日报 2026/06/14"
    assert record["当前总人数"] == 57
    assert record["新增人数"] is None
    assert record["离开人数"] is None
    assert record["净增长"] is None
    assert record["Gaming Alerts 新增订阅人数"] is None


@pytest.mark.asyncio
async def test_source_read_uses_an_open_ended_sheet_range() -> None:
    client = LarkMigrationClient("app-id", "secret")
    requested_paths: list[str] = []

    async def fake_request(method: str, path: str, **kwargs: object) -> dict[str, object]:
        requested_paths.append(path)
        return {"data": {"valueRange": {"values": []}}}

    client._request = fake_request  # type: ignore[method-assign]

    await client.read_source_rows()

    assert requested_paths == [
        "/sheets/v2/spreadsheets/PA8usyjmshX40HtXaeTjkr4Apne/values/e348a1!A:Q"
    ]


class _FakeRequestContext:
    def __init__(self, response: object = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error

    async def __aenter__(self) -> object:
        if self.error is not None:
            raise self.error
        return self.response

    async def __aexit__(self, *_args: object) -> None:
        return None


class _FakeSession:
    def __init__(self, context_factory: object) -> None:
        self.context_factory = context_factory
        self.attempts = 0

    def request(self, *_args: object, **_kwargs: object) -> _FakeRequestContext:
        self.attempts += 1
        return self.context_factory()


class _TextResponse:
    status = 502

    async def text(self) -> str:
        return "upstream unavailable"


@pytest.mark.asyncio
async def test_non_idempotent_request_does_not_retry_ambiguous_timeout() -> None:
    session = _FakeSession(lambda: _FakeRequestContext(error=asyncio.TimeoutError()))
    client = LarkMigrationClient("app-id", "secret")
    client.session = session  # type: ignore[assignment]
    client.token = "token"

    with pytest.raises(RuntimeError, match="timed out"):
        await client._request("POST", "/create", retry_ambiguous=False)

    assert session.attempts == 1


@pytest.mark.asyncio
async def test_non_json_server_error_is_retried_and_reported() -> None:
    session = _FakeSession(lambda: _FakeRequestContext(response=_TextResponse()))
    client = LarkMigrationClient("app-id", "secret")
    client.session = session  # type: ignore[assignment]
    client.token = "token"

    with pytest.raises(RuntimeError, match="HTTP 502.*upstream unavailable"):
        await client._request("GET", "/read")

    assert session.attempts == 3


@pytest.mark.asyncio
async def test_record_batch_writes_are_split_into_500_record_chunks() -> None:
    client = LarkMigrationClient("app-id", "secret")
    requests: list[tuple[str, dict[str, object]]] = []

    async def fake_request(method: str, path: str, **kwargs: object) -> dict[str, object]:
        requests.append((path, kwargs["json"]))  # type: ignore[index]
        return {"code": 0}

    client._request = fake_request  # type: ignore[method-assign]
    await client.create_records([{"记录": f"日报 {index}"} for index in range(501)])

    assert [len(payload["records"]) for _, payload in requests] == [500, 1]


def test_validate_requires_baseline_counts_and_unique_keys() -> None:
    records = [
        {"记录": f"日报 2026/07/{day:02d}", "统计类型": "日报", "日期": day}
        for day in range(1, 39)
    ]
    records.extend(
        {"记录": f"周报 2026/07/{day:02d}", "统计类型": "周报", "日期": day}
        for day in range(1, 6)
    )

    validate_migration_records(records)

    expanded = records + [
        {"记录": "日报 2026/08/07", "统计类型": "日报", "日期": 44},
        {"记录": "周报 2026/08/09", "统计类型": "周报", "日期": 45},
    ]
    validate_migration_records(expanded)

    with pytest.raises(ValueError, match="at least 38 daily and 5 weekly"):
        validate_migration_records(records[:-1])

    duplicated = records + [dict(records[0])]
    with pytest.raises(ValueError, match="duplicate record key"):
        validate_migration_records(duplicated)


def _full_source_rows() -> list[list[object]]:
    rows: list[list[object]] = [_header()]
    for index in range(38):
        day = datetime.date(2026, 6, 14) + datetime.timedelta(days=index)
        row: list[object] = [
            day.strftime("%Y/%m/%d"),
            500 + index,
            index,
            index % 3,
            index - index % 3,
            index % 4,
            index % 5,
            index % 6,
        ]
        row.extend([None] * 9)
        if index < 5:
            row[8:17] = [
                day.strftime("%Y/%m/%d"),
                500 + index,
                10 + index,
                index,
                10,
                20 + index,
                30 + index,
                40 + index,
                50 + index,
            ]
        rows.append(row)
    return rows


class FakeMigrationClient:
    def __init__(self) -> None:
        self.source_rows = _full_source_rows()
        self.fields = [{"field_id": "primary", "field_name": "文本", "type": 1}]
        self.views = [{"view_id": "default", "view_name": "表格", "view_type": "grid"}]
        self.records = [
            {"record_id": f"blank-{index}", "fields": {"文本": ""}}
            for index in range(5)
        ]
        self.write_calls: list[str] = []

    async def read_source_rows(self) -> list[list[object]]:
        return copy.deepcopy(self.source_rows)

    async def list_fields(self) -> list[dict[str, object]]:
        return copy.deepcopy(self.fields)

    async def rename_field(self, field_id: str, field_name: str, field_type: int) -> None:
        self.write_calls.append("rename_field")
        field = next(item for item in self.fields if item["field_id"] == field_id)
        field.update(field_name=field_name, type=field_type)
        for record in self.records:
            if "文本" in record["fields"]:
                record["fields"][field_name] = record["fields"].pop("文本")

    async def create_field(self, definition: dict[str, object]) -> None:
        self.write_calls.append("create_field")
        self.fields.append(
            {
                "field_id": f"field-{len(self.fields)}",
                "field_name": definition["field_name"],
                "type": definition["type"],
            }
        )

    async def list_views(self) -> list[dict[str, object]]:
        return copy.deepcopy(self.views)

    async def rename_view(self, view_id: str, view_name: str) -> None:
        self.write_calls.append("rename_view")
        view = next(item for item in self.views if item["view_id"] == view_id)
        view["view_name"] = view_name

    async def create_view(self, view_name: str) -> None:
        self.write_calls.append("create_view")
        self.views.append(
            {"view_id": f"view-{len(self.views)}", "view_name": view_name, "view_type": "grid"}
        )

    async def list_records(self) -> list[dict[str, object]]:
        return copy.deepcopy(self.records)

    async def delete_records(self, record_ids: list[str]) -> None:
        self.write_calls.append("delete_records")
        ids = set(record_ids)
        self.records = [record for record in self.records if record["record_id"] not in ids]

    async def create_records(self, fields_list: list[dict[str, object]]) -> None:
        self.write_calls.append("create_records")
        for fields in fields_list:
            self.records.append(
                {"record_id": f"record-{len(self.records)}", "fields": copy.deepcopy(fields)}
            )

    async def update_records(self, updates: list[dict[str, object]]) -> None:
        self.write_calls.append("update_records")
        by_id = {record["record_id"]: record for record in self.records}
        for update in updates:
            by_id[update["record_id"]]["fields"] = copy.deepcopy(update["fields"])


@pytest.mark.asyncio
async def test_dry_run_reports_changes_without_writing() -> None:
    client = FakeMigrationClient()

    report = await run_migration(client, apply=False)

    assert isinstance(report, MigrationReport)
    assert report.daily == 38
    assert report.weekly == 5
    assert report.creates == 43
    assert report.updates == 0
    assert report.deletes == 5
    assert report.applied is False
    assert client.write_calls == []


@pytest.mark.asyncio
async def test_report_counts_newer_source_rows_dynamically() -> None:
    client = FakeMigrationClient()
    client.source_rows.append(
        ["2026/08/07", 800, 6, 2, 4, 1, 2, 3] + [None] * 9
    )

    report = await run_migration(client, apply=False)

    assert report.daily == 39
    assert report.weekly == 5


@pytest.mark.asyncio
async def test_apply_creates_schema_and_exact_records_without_touching_views() -> None:
    client = FakeMigrationClient()

    report = await run_migration(client, apply=True)

    assert report.verified is True
    assert len(client.records) == 43
    assert {field["field_name"] for field in client.fields} == {
        definition["field_name"] for definition in FIELD_DEFINITIONS
    }
    assert client.views == [{"view_id": "default", "view_name": "表格", "view_type": "grid"}]
    assert "rename_view" not in client.write_calls
    assert "create_view" not in client.write_calls

    second = await run_migration(client, apply=False)
    assert (second.creates, second.updates, second.deletes) == (0, 0, 0)
    assert second.verified is True


@pytest.mark.asyncio
async def test_apply_repairs_existing_record_in_place() -> None:
    client = FakeMigrationClient()
    await run_migration(client, apply=True)
    original_ids = {record["fields"]["记录"]: record["record_id"] for record in client.records}
    client.records[0]["fields"]["当前总人数"] = -1

    report = await run_migration(client, apply=True)

    assert report.updates == 1
    assert report.creates == 0
    assert original_ids == {
        record["fields"]["记录"]: record["record_id"] for record in client.records
    }
