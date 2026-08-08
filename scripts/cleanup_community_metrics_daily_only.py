from __future__ import annotations

import argparse
import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from scripts.migrate_community_metrics_to_base import (
        LarkMigrationClient,
        TARGET_APP_TOKEN,
        TARGET_TABLE_ID,
        _extract_text,
        _load_dotenv,
    )
except ModuleNotFoundError:
    from migrate_community_metrics_to_base import (  # type: ignore[no-redef]
        LarkMigrationClient,
        TARGET_APP_TOKEN,
        TARGET_TABLE_ID,
        _extract_text,
        _load_dotenv,
    )


RETAINED_FIELDS = (
    "记录",
    "日期",
    "当前总人数",
    "新增人数",
    "离开人数",
    "净增长",
    "Gaming Alerts 新增订阅人数",
    "Exclusive Updates 新增订阅人数",
    "Lucky Drops 新增订阅人数",
)
NUMERIC_FIELDS = RETAINED_FIELDS[2:]
OBSOLETE_FIELDS = (
    "统计类型",
    "本周贴文 Reaction 数",
    "Gaming Alerts 总订阅人数",
    "Exclusive Updates 总订阅人数",
    "Lucky Drops 总订阅人数",
)


@dataclass(frozen=True)
class CleanupPlan:
    daily_count: int
    weekly_record_ids: tuple[str, ...]
    obsolete_field_ids: tuple[str, ...]
    numeric_fields: tuple[tuple[str, str], ...]
    numeric_updates: tuple[tuple[str, str], ...]

    @property
    def numeric_field_ids(self) -> tuple[str, ...]:
        return tuple(field_id for field_id, _ in self.numeric_fields)

    @property
    def numeric_update_ids(self) -> tuple[str, ...]:
        return tuple(field_id for field_id, _ in self.numeric_updates)


@dataclass(frozen=True)
class CleanupReport:
    daily: int
    weekly: int
    field_count: int
    obsolete_fields: int
    numeric_updates: int
    applied: bool
    verified: bool


def build_cleanup_plan(
    fields: list[dict[str, Any]],
    records: list[dict[str, Any]],
) -> CleanupPlan:
    by_name: dict[str, dict[str, Any]] = {}
    for field in fields:
        name = str(field.get("field_name") or "")
        if name in by_name:
            raise RuntimeError(f"duplicate field name: {name}")
        by_name[name] = field

    missing = [name for name in RETAINED_FIELDS if name not in by_name]
    if missing:
        raise RuntimeError(f"missing retained fields: {', '.join(missing)}")
    allowed = set(RETAINED_FIELDS) | set(OBSOLETE_FIELDS)
    unexpected = sorted(name for name in by_name if name not in allowed)
    if unexpected:
        raise RuntimeError(f"unexpected fields: {', '.join(unexpected)}")
    if int(by_name["记录"].get("type", -1)) != 1:
        raise RuntimeError("field '记录' must have type 1")
    if int(by_name["日期"].get("type", -1)) != 5:
        raise RuntimeError("field '日期' must have type 5")

    numeric_fields: list[tuple[str, str]] = []
    numeric_updates: list[tuple[str, str]] = []
    for name in NUMERIC_FIELDS:
        field = by_name[name]
        if int(field.get("type", -1)) != 2:
            raise RuntimeError(f"numeric field {name!r} must have type 2")
        item = (str(field["field_id"]), name)
        numeric_fields.append(item)
        if (field.get("property") or {}).get("formatter") != "0":
            numeric_updates.append(item)

    daily_count = 0
    weekly_ids: list[str] = []
    for record in records:
        record_fields = record.get("fields") or {}
        if not isinstance(record_fields, dict):
            raise RuntimeError("record fields must be an object")
        key = _extract_text(record_fields.get("记录"))
        if key.startswith("日报 "):
            daily_count += 1
        elif key.startswith("周报 "):
            weekly_ids.append(str(record["record_id"]))
        else:
            raise RuntimeError(f"unexpected record key: {key!r}")

    return CleanupPlan(
        daily_count=daily_count,
        weekly_record_ids=tuple(weekly_ids),
        obsolete_field_ids=tuple(
            str(by_name[name]["field_id"])
            for name in OBSOLETE_FIELDS
            if name in by_name
        ),
        numeric_fields=tuple(numeric_fields),
        numeric_updates=tuple(numeric_updates),
    )


class DailyCleanupClient(LarkMigrationClient):
    async def update_number_field(self, field_id: str, field_name: str) -> None:
        await self._request(
            "PUT",
            f"/bitable/v1/apps/{TARGET_APP_TOKEN}/tables/{TARGET_TABLE_ID}/fields/{field_id}",
            json={"field_name": field_name, "type": 2, "property": {"formatter": "0"}},
        )

    async def delete_field(self, field_id: str) -> None:
        await self._request(
            "DELETE",
            f"/bitable/v1/apps/{TARGET_APP_TOKEN}/tables/{TARGET_TABLE_ID}/fields/{field_id}",
            retry_ambiguous=False,
        )


async def run_cleanup(
    client: Any,
    *,
    apply: bool,
    minimum_daily: int = 0,
) -> CleanupReport:
    fields = await client.list_fields()
    records = await client.list_records()
    plan = build_cleanup_plan(fields, records)
    if plan.daily_count < minimum_daily:
        raise RuntimeError(
            f"expected at least {minimum_daily} daily records, got {plan.daily_count}"
        )

    if not apply:
        verified = (
            not plan.weekly_record_ids
            and not plan.obsolete_field_ids
            and not plan.numeric_updates
            and len(fields) == len(RETAINED_FIELDS)
        )
        return CleanupReport(
            daily=plan.daily_count,
            weekly=len(plan.weekly_record_ids),
            field_count=len(fields),
            obsolete_fields=len(plan.obsolete_field_ids),
            numeric_updates=len(plan.numeric_updates),
            applied=False,
            verified=verified,
        )

    if plan.weekly_record_ids:
        await client.delete_records(list(plan.weekly_record_ids))
    for field_id, field_name in plan.numeric_updates:
        await client.update_number_field(field_id, field_name)
    for field_id in plan.obsolete_field_ids:
        await client.delete_field(field_id)

    final_fields = await client.list_fields()
    final_records = await client.list_records()
    final_plan = build_cleanup_plan(final_fields, final_records)
    verified = (
        not final_plan.weekly_record_ids
        and not final_plan.obsolete_field_ids
        and not final_plan.numeric_updates
        and len(final_fields) == len(RETAINED_FIELDS)
        and final_plan.daily_count == plan.daily_count
    )
    if not verified:
        raise RuntimeError("daily-only cleanup verification failed")
    return CleanupReport(
        daily=final_plan.daily_count,
        weekly=0,
        field_count=len(final_fields),
        obsolete_fields=0,
        numeric_updates=0,
        applied=True,
        verified=True,
    )


async def _main(apply: bool) -> None:
    _load_dotenv(Path.cwd() / ".env")
    app_id = os.getenv("LARK_APP_ID", "")
    app_secret = os.getenv("LARK_APP_SECRET", "")
    if not app_id or not app_secret:
        raise RuntimeError("LARK_APP_ID and LARK_APP_SECRET are required")
    async with DailyCleanupClient(app_id, app_secret) as client:
        report = await run_cleanup(client, apply=apply, minimum_daily=39)
    print(
        "daily_cleanup_report "
        f"daily={report.daily} weekly={report.weekly} fields={report.field_count} "
        f"obsolete_fields={report.obsolete_fields} numeric_updates={report.numeric_updates} "
        f"apply={report.applied} verified={report.verified}",
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Keep only daily metrics in the Lark Base")
    parser.add_argument("--apply", action="store_true", help="apply the validated cleanup")
    args = parser.parse_args()
    asyncio.run(_main(args.apply))
