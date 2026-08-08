import asyncio

import pytest

from scripts.cleanup_community_metrics_daily_only import (
    NUMERIC_FIELDS,
    OBSOLETE_FIELDS,
    RETAINED_FIELDS,
    build_cleanup_plan,
    run_cleanup,
)


def _fields(*, integer_formatter: bool = False):
    fields = []
    for index, name in enumerate(RETAINED_FIELDS):
        field_type = 1 if name == "记录" else 5 if name == "日期" else 2
        field = {"field_id": f"retained-{index}", "field_name": name, "type": field_type}
        if name in NUMERIC_FIELDS:
            field["property"] = {"formatter": "0" if integer_formatter else "0.00"}
        fields.append(field)
    fields.extend(
        {
            "field_id": f"obsolete-{index}",
            "field_name": name,
            "type": 3 if name == "统计类型" else 2,
        }
        for index, name in enumerate(OBSOLETE_FIELDS)
    )
    return fields


def _records():
    return [
        {"record_id": "daily-1", "fields": {"记录": "日报 2026/08/07"}},
        {"record_id": "daily-2", "fields": {"记录": "日报 2026/08/08"}},
        {"record_id": "weekly-1", "fields": {"记录": "周报 2026/08/02"}},
        {"record_id": "weekly-2", "fields": {"记录": "周报 2026/08/09"}},
    ]


def test_build_cleanup_plan_selects_only_weekly_records_and_named_fields():
    plan = build_cleanup_plan(_fields(), _records())

    assert plan.daily_count == 2
    assert plan.weekly_record_ids == ("weekly-1", "weekly-2")
    assert plan.obsolete_field_ids == tuple(
        f"obsolete-{index}" for index in range(len(OBSOLETE_FIELDS))
    )
    assert plan.numeric_field_ids == tuple(
        f"retained-{RETAINED_FIELDS.index(name)}" for name in NUMERIC_FIELDS
    )
    assert plan.numeric_update_ids == plan.numeric_field_ids


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda fields, records: records.append(
                {"record_id": "other", "fields": {"记录": "备注"}}
            ),
            "unexpected record key",
        ),
        (
            lambda fields, records: fields.pop(1),
            "missing retained fields",
        ),
        (
            lambda fields, records: fields.append(
                {"field_id": "unknown", "field_name": "其他字段", "type": 1}
            ),
            "unexpected fields",
        ),
        (
            lambda fields, records: fields.append(dict(fields[0], field_id="duplicate")),
            "duplicate field name",
        ),
        (
            lambda fields, records: fields[2].update(type=1),
            "must have type 2",
        ),
    ],
)
def test_build_cleanup_plan_rejects_unsafe_remote_shapes(mutate, message):
    fields = _fields()
    records = _records()
    mutate(fields, records)

    with pytest.raises(RuntimeError, match=message):
        build_cleanup_plan(fields, records)


class _FakeClient:
    def __init__(self, *, cleaned=False):
        self.fields = _fields(integer_formatter=cleaned)
        self.records = _records()[:2] if cleaned else _records()
        if cleaned:
            self.fields = [
                field for field in self.fields if field["field_name"] not in OBSOLETE_FIELDS
            ]
        self.calls = []

    async def list_fields(self):
        return self.fields

    async def list_records(self):
        return self.records

    async def delete_records(self, record_ids):
        self.calls.append(("delete_records", tuple(record_ids)))
        selected = set(record_ids)
        self.records = [record for record in self.records if record["record_id"] not in selected]

    async def update_number_field(self, field_id, field_name):
        self.calls.append(("update_number_field", field_id, field_name))
        for field in self.fields:
            if field["field_id"] == field_id:
                field["property"] = {"formatter": "0"}

    async def delete_field(self, field_id):
        self.calls.append(("delete_field", field_id))
        self.fields = [field for field in self.fields if field["field_id"] != field_id]


def test_run_cleanup_dry_run_never_writes():
    client = _FakeClient()

    report = asyncio.run(run_cleanup(client, apply=False))

    assert client.calls == []
    assert report.daily == 2
    assert report.weekly == 2
    assert report.obsolete_fields == 5
    assert report.numeric_updates == 7
    assert report.applied is False
    assert report.verified is False


def test_run_cleanup_apply_is_verified_and_idempotent():
    client = _FakeClient()

    report = asyncio.run(run_cleanup(client, apply=True))

    assert client.calls[0] == ("delete_records", ("weekly-1", "weekly-2"))
    assert [call[0] for call in client.calls].count("update_number_field") == 7
    assert [call[0] for call in client.calls].count("delete_field") == 5
    assert report.daily == 2
    assert report.weekly == 0
    assert report.field_count == 9
    assert report.verified is True

    client.calls.clear()
    rerun = asyncio.run(run_cleanup(client, apply=True))

    assert client.calls == []
    assert rerun.verified is True
