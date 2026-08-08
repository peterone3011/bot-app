import asyncio

import pytest

from scripts.cleanup_community_metrics_daily_only import NUMERIC_FIELDS
from scripts.migrate_community_metrics_single_date import build_migration_plan, run_migration


def _fields(state="current"):
    primary_name = "日期" if state == "final" else "记录"
    fields = [
        {
            "field_id": "primary",
            "field_name": primary_name,
            "type": 1,
            "is_primary": True,
        }
    ]
    if state == "current":
        fields.append(
            {
                "field_id": "secondary-date",
                "field_name": "日期",
                "type": 5,
                "is_primary": False,
            }
        )
    fields.extend(
        {
            "field_id": f"number-{index}",
            "field_name": name,
            "type": 2,
            "property": {"formatter": "0"},
        }
        for index, name in enumerate(NUMERIC_FIELDS)
    )
    return fields


def _records(state="current"):
    field_name = "日期" if state == "final" else "记录"
    prefix = "" if state in {"normalized", "final"} else "日报 "
    return [
        {
            "record_id": "one",
            "fields": {field_name: f"{prefix}2026/08/06", "当前总人数": 800},
        },
        {
            "record_id": "two",
            "fields": {field_name: f"{prefix}2026/08/07", "当前总人数": 801},
        },
    ]


def test_build_plan_normalizes_values_then_deletes_and_renames():
    plan = build_migration_plan(_fields(), _records())

    assert plan.daily_count == 2
    assert plan.record_updates == (
        {"record_id": "one", "fields": {"记录": "2026/08/06"}},
        {"record_id": "two", "fields": {"记录": "2026/08/07"}},
    )
    assert plan.secondary_date_field_id == "secondary-date"
    assert plan.rename_primary is True
    assert plan.verified is False


def test_build_plan_resumes_after_values_or_field_were_already_changed():
    normalized = build_migration_plan(_fields(), _records("normalized"))
    assert normalized.record_updates == ()
    assert normalized.secondary_date_field_id == "secondary-date"
    assert normalized.rename_primary is True

    field_deleted = build_migration_plan(_fields("interrupted"), _records("normalized"))
    assert field_deleted.record_updates == ()
    assert field_deleted.secondary_date_field_id is None
    assert field_deleted.rename_primary is True


def test_build_plan_accepts_only_complete_final_state_as_verified():
    plan = build_migration_plan(_fields("final"), _records("final"))

    assert plan.record_updates == ()
    assert plan.secondary_date_field_id is None
    assert plan.rename_primary is False
    assert plan.field_count == 8
    assert plan.verified is True


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda fields, records: records[0]["fields"].update(记录="not-a-date"),
            "unexpected primary value",
        ),
        (
            lambda fields, records: records[1]["fields"].update(记录="日报 2026/08/06"),
            "duplicate normalized date",
        ),
        (
            lambda fields, records: fields.append(
                {"field_id": "extra", "field_name": "其他", "type": 1}
            ),
            "unexpected fields",
        ),
    ],
)
def test_build_plan_rejects_unsafe_shapes_before_writes(mutate, message):
    fields = _fields()
    records = _records()
    mutate(fields, records)

    with pytest.raises(RuntimeError, match=message):
        build_migration_plan(fields, records)


class _FakeClient:
    def __init__(self):
        self.fields = _fields()
        self.records = _records()
        self.calls = []

    async def list_fields(self):
        return self.fields

    async def list_records(self):
        return self.records

    async def update_records(self, updates):
        self.calls.append(("update_records", tuple(updates)))
        by_id = {record["record_id"]: record for record in self.records}
        for update in updates:
            by_id[update["record_id"]]["fields"].update(update["fields"])

    async def delete_field(self, field_id):
        self.calls.append(("delete_field", field_id))
        self.fields = [field for field in self.fields if field["field_id"] != field_id]
        for record in self.records:
            record["fields"].pop("日期", None)

    async def rename_field(self, field_id, field_name, field_type):
        self.calls.append(("rename_field", field_id, field_name, field_type))
        for field in self.fields:
            if field["field_id"] == field_id:
                old_name = field["field_name"]
                field["field_name"] = field_name
                field["type"] = field_type
                for record in self.records:
                    record["fields"][field_name] = record["fields"].pop(old_name)


def test_run_migration_dry_run_never_writes():
    client = _FakeClient()

    report = asyncio.run(run_migration(client, apply=False))

    assert client.calls == []
    assert report.daily == 2
    assert report.record_updates == 2
    assert report.delete_secondary_date is True
    assert report.rename_primary is True
    assert report.verified is False


def test_run_migration_apply_preserves_metrics_and_is_idempotent():
    client = _FakeClient()
    metric_values = [record["fields"]["当前总人数"] for record in client.records]

    report = asyncio.run(run_migration(client, apply=True))

    assert [call[0] for call in client.calls] == [
        "update_records",
        "delete_field",
        "rename_field",
    ]
    assert report.daily == 2
    assert report.field_count == 8
    assert report.verified is True
    assert [record["fields"]["当前总人数"] for record in client.records] == metric_values

    client.calls.clear()
    rerun = asyncio.run(run_migration(client, apply=True))
    assert client.calls == []
    assert rerun.verified is True
