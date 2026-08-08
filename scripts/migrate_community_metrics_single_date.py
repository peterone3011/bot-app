from __future__ import annotations

import argparse
import asyncio
import datetime
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__:
    from scripts.cleanup_community_metrics_daily_only import DailyCleanupClient, NUMERIC_FIELDS
    from scripts.migrate_community_metrics_to_base import _extract_text, _load_dotenv
else:
    from cleanup_community_metrics_daily_only import DailyCleanupClient, NUMERIC_FIELDS
    from migrate_community_metrics_to_base import _extract_text, _load_dotenv


@dataclass(frozen=True)
class MigrationPlan:
    daily_count: int
    field_count: int
    primary_field_id: str
    record_updates: tuple[dict[str, object], ...]
    secondary_date_field_id: str | None
    rename_primary: bool
    verified: bool


@dataclass(frozen=True)
class MigrationReport:
    daily: int
    field_count: int
    record_updates: int
    delete_secondary_date: bool
    rename_primary: bool
    applied: bool
    verified: bool


def _normalize_date_text(value: Any) -> str:
    text = _extract_text(value)
    date_text = text.removeprefix("日报 ")
    try:
        day = datetime.datetime.strptime(date_text, "%Y/%m/%d").date()
    except ValueError as exc:
        raise RuntimeError(f"unexpected primary value: {text!r}") from exc
    if day.strftime("%Y/%m/%d") != date_text:
        raise RuntimeError(f"unexpected primary value: {text!r}")
    return date_text


def build_migration_plan(
    fields: list[dict[str, Any]],
    records: list[dict[str, Any]],
) -> MigrationPlan:
    primary_fields = [field for field in fields if field.get("is_primary")]
    if len(primary_fields) != 1:
        raise RuntimeError(f"expected exactly one primary field, got {len(primary_fields)}")
    primary = primary_fields[0]
    primary_name = str(primary.get("field_name") or "")
    if primary_name not in {"记录", "日期"} or int(primary.get("type", -1)) != 1:
        raise RuntimeError("primary field must be text named '记录' or '日期'")

    by_name: dict[str, dict[str, Any]] = {}
    for field in fields:
        name = str(field.get("field_name") or "")
        if name in by_name:
            raise RuntimeError(f"duplicate field name: {name}")
        by_name[name] = field
    allowed = {primary_name, *NUMERIC_FIELDS}
    if primary_name == "记录" and "日期" in by_name:
        allowed.add("日期")
    unexpected = sorted(name for name in by_name if name not in allowed)
    if unexpected:
        raise RuntimeError(f"unexpected fields: {', '.join(unexpected)}")
    missing_numbers = [name for name in NUMERIC_FIELDS if name not in by_name]
    if missing_numbers:
        raise RuntimeError(f"missing metric fields: {', '.join(missing_numbers)}")
    for name in NUMERIC_FIELDS:
        if int(by_name[name].get("type", -1)) != 2:
            raise RuntimeError(f"metric field {name!r} must have type 2")

    secondary_date_field_id: str | None = None
    if primary_name == "记录" and "日期" in by_name:
        secondary = by_name["日期"]
        if secondary.get("is_primary") or int(secondary.get("type", -1)) != 5:
            raise RuntimeError("secondary date field must be non-primary type 5")
        secondary_date_field_id = str(secondary["field_id"])

    normalized_dates: set[str] = set()
    updates: list[dict[str, object]] = []
    for record in records:
        record_fields = record.get("fields") or {}
        if not isinstance(record_fields, dict):
            raise RuntimeError("record fields must be an object")
        current_value = _extract_text(record_fields.get(primary_name))
        date_text = _normalize_date_text(current_value)
        if date_text in normalized_dates:
            raise RuntimeError(f"duplicate normalized date: {date_text}")
        normalized_dates.add(date_text)
        if current_value != date_text:
            updates.append(
                {
                    "record_id": str(record["record_id"]),
                    "fields": {primary_name: date_text},
                }
            )

    rename_primary = primary_name == "记录"
    verified = (
        not updates
        and secondary_date_field_id is None
        and not rename_primary
        and len(fields) == 1 + len(NUMERIC_FIELDS)
    )
    return MigrationPlan(
        daily_count=len(records),
        field_count=len(fields),
        primary_field_id=str(primary["field_id"]),
        record_updates=tuple(updates),
        secondary_date_field_id=secondary_date_field_id,
        rename_primary=rename_primary,
        verified=verified,
    )


async def run_migration(
    client: Any,
    *,
    apply: bool,
    minimum_daily: int = 0,
) -> MigrationReport:
    fields = await client.list_fields()
    records = await client.list_records()
    plan = build_migration_plan(fields, records)
    if plan.daily_count < minimum_daily:
        raise RuntimeError(
            f"expected at least {minimum_daily} daily records, got {plan.daily_count}"
        )
    if not apply:
        return MigrationReport(
            daily=plan.daily_count,
            field_count=plan.field_count,
            record_updates=len(plan.record_updates),
            delete_secondary_date=plan.secondary_date_field_id is not None,
            rename_primary=plan.rename_primary,
            applied=False,
            verified=plan.verified,
        )

    if plan.record_updates:
        await client.update_records(list(plan.record_updates))
    if plan.secondary_date_field_id is not None:
        await client.delete_field(plan.secondary_date_field_id)
    if plan.rename_primary:
        await client.rename_field(plan.primary_field_id, "日期", 1)

    final_fields = await client.list_fields()
    final_records = await client.list_records()
    final_plan = build_migration_plan(final_fields, final_records)
    if not final_plan.verified or final_plan.daily_count != plan.daily_count:
        raise RuntimeError("single-date migration verification failed")
    return MigrationReport(
        daily=final_plan.daily_count,
        field_count=final_plan.field_count,
        record_updates=0,
        delete_secondary_date=False,
        rename_primary=False,
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
        report = await run_migration(client, apply=apply, minimum_daily=39)
    print(
        "single_date_migration_report "
        f"daily={report.daily} fields={report.field_count} "
        f"record_updates={report.record_updates} "
        f"delete_secondary_date={report.delete_secondary_date} "
        f"rename_primary={report.rename_primary} apply={report.applied} "
        f"verified={report.verified}",
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Use one primary date field for metrics")
    parser.add_argument("--apply", action="store_true", help="apply the validated migration")
    args = parser.parse_args()
    asyncio.run(_main(args.apply))
