from __future__ import annotations

import argparse
import asyncio
import datetime
import json as jsonlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiohttp


_BJT = datetime.timezone(datetime.timedelta(hours=8))
_SHEET_DATE_BASE = datetime.date(1899, 12, 30)

COMMON_FIELDS = (
    "记录",
    "统计类型",
    "日期",
    "当前总人数",
    "新增人数",
    "离开人数",
    "净增长",
)
DAILY_FIELDS = (
    "Gaming Alerts 新增订阅人数",
    "Exclusive Updates 新增订阅人数",
    "Lucky Drops 新增订阅人数",
)
WEEKLY_FIELDS = (
    "本周贴文 Reaction 数",
    "Gaming Alerts 总订阅人数",
    "Exclusive Updates 总订阅人数",
    "Lucky Drops 总订阅人数",
)

SOURCE_SPREADSHEET_TOKEN = "PA8usyjmshX40HtXaeTjkr4Apne"
SOURCE_SHEET_ID = "e348a1"
TARGET_APP_TOKEN = "CeqtbxWt5azkkHs8OzpjZ9D1p2e"
TARGET_TABLE_ID = "tblMeRm8yocZPqUR"
LARK_BASE = "https://open.larksuite.com/open-apis"
_BATCH_SIZE = 500

FIELD_DEFINITIONS: tuple[dict[str, object], ...] = (
    {"field_name": "记录", "type": 1},
    {
        "field_name": "统计类型",
        "type": 3,
        "property": {"options": [{"name": "日报"}, {"name": "周报"}]},
    },
    {"field_name": "日期", "type": 5, "property": {"date_formatter": "yyyy/MM/dd"}},
    *(
        {"field_name": field_name, "type": 2}
        for field_name in (
            "当前总人数",
            "新增人数",
            "离开人数",
            "净增长",
            *DAILY_FIELDS,
            *WEEKLY_FIELDS,
        )
    ),
)


@dataclass(frozen=True)
class MigrationReport:
    daily: int
    weekly: int
    creates: int
    updates: int
    deletes: int
    applied: bool
    verified: bool


def normalize_date(value: Any) -> datetime.date | None:
    if value in (None, "", "/"):
        return None
    if isinstance(value, (int, float)):
        return _SHEET_DATE_BASE + datetime.timedelta(days=int(value))
    text = str(value).strip()
    for fmt in ("%Y/%m/%d", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"unsupported date value: {value!r}")


def _date_ms(day: datetime.date) -> int:
    value = datetime.datetime.combine(day, datetime.time.min, tzinfo=_BJT)
    return int(value.timestamp() * 1000)


def _number(value: Any) -> int | float | None:
    if value in (None, "", "/"):
        return None
    if isinstance(value, bool):
        raise ValueError(f"invalid numeric value: {value!r}")
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip()
    try:
        number = float(text)
    except ValueError as exc:
        raise ValueError(f"invalid numeric value: {value!r}") from exc
    return int(number) if number.is_integer() else number


def _set_number(record: dict[str, object], field: str, value: Any) -> None:
    record[field] = _number(value)


def _build_record(
    kind: str,
    day: datetime.date,
    values: list[Any],
    field_names: tuple[str, ...],
) -> dict[str, object]:
    record: dict[str, object] = {
        "记录": f"{kind} {day:%Y/%m/%d}",
        "统计类型": kind,
        "日期": _date_ms(day),
    }
    for field_name, value in zip(field_names, values):
        _set_number(record, field_name, value)
    for field_name in (*DAILY_FIELDS, *WEEKLY_FIELDS):
        record.setdefault(field_name, None)
    return record


def build_migration_records(rows: list[list[Any]]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for source_row in rows[1:]:
        row = list(source_row) + [None] * max(0, 17 - len(source_row))
        daily_day = normalize_date(row[0])
        if daily_day is not None:
            records.append(
                _build_record(
                    "日报",
                    daily_day,
                    row[1:8],
                    (
                        "当前总人数",
                        "新增人数",
                        "离开人数",
                        "净增长",
                        *DAILY_FIELDS,
                    ),
                )
            )
        weekly_day = normalize_date(row[8])
        if weekly_day is not None:
            records.append(
                _build_record(
                    "周报",
                    weekly_day,
                    row[9:17],
                    (
                        "当前总人数",
                        "新增人数",
                        "离开人数",
                        "净增长",
                        *WEEKLY_FIELDS,
                    ),
                )
            )
    return records


def validate_migration_records(records: list[dict[str, object]]) -> None:
    keys = [str(record.get("记录", "")) for record in records]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate record key")
    daily = sum(record.get("统计类型") == "日报" for record in records)
    weekly = sum(record.get("统计类型") == "周报" for record in records)
    if daily < 38 or weekly < 5:
        raise ValueError(
            f"expected at least 38 daily and 5 weekly records, got {daily} daily and {weekly} weekly"
        )


def _extract_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(
            str(item.get("text", "")) for item in value if isinstance(item, dict)
        )
    return str(value)


def _is_blank_fields(fields: dict[str, Any]) -> bool:
    return not fields or all(value in (None, "", [], {}) for value in fields.values())


def _normalize_remote_value(value: Any, expected: Any = None) -> Any:
    if isinstance(value, list):
        value = _extract_text(value)
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        return _number(value)
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _record_differs(remote: dict[str, Any], expected: dict[str, object]) -> bool:
    return any(
        _normalize_remote_value(remote.get(field_name), expected_value) != expected_value
        for field_name, expected_value in expected.items()
    )


class LarkMigrationClient:
    def __init__(self, app_id: str, app_secret: str) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.session: aiohttp.ClientSession | None = None
        self.token = ""

    async def __aenter__(self) -> "LarkMigrationClient":
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        auth = await self._request(
            "POST",
            "/auth/v3/app_access_token/internal",
            authenticated=False,
            json={"app_id": self.app_id, "app_secret": self.app_secret},
        )
        self.token = str(auth.get("tenant_access_token") or auth.get("app_access_token") or "")
        if not self.token:
            raise RuntimeError("Lark auth response did not include an access token")
        return self

    async def __aexit__(self, *_args: object) -> None:
        if self.session is not None:
            await self.session.close()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        authenticated: bool = True,
        params: dict[str, str] | None = None,
        json: dict[str, object] | None = None,
        retry_ambiguous: bool = True,
    ) -> dict[str, Any]:
        if self.session is None:
            raise RuntimeError("LarkMigrationClient must be used as an async context manager")
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if authenticated:
            headers["Authorization"] = f"Bearer {self.token}"
        retryable_codes = {1254290, 1254291, 1255040}
        last_error = "unknown Lark error"
        for attempt in range(1, 4):
            try:
                async with self.session.request(
                    method,
                    f"{LARK_BASE}{path}",
                    headers=headers,
                    params=params,
                    json=json,
                ) as response:
                    raw_body = await response.text()
                    try:
                        parsed = jsonlib.loads(raw_body)
                    except jsonlib.JSONDecodeError:
                        parsed = {"code": -1, "msg": raw_body[:200] or "non-JSON response"}
                    data = parsed if isinstance(parsed, dict) else {"code": -1, "msg": raw_body[:200]}
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last_error = "request timed out" if isinstance(exc, asyncio.TimeoutError) else str(exc)
                if attempt == 3 or not retry_ambiguous:
                    break
            else:
                code = int(data.get("code", -1))
                if response.status < 500 and code == 0:
                    return data
                last_error = f"HTTP {response.status}, code {code}: {data.get('msg')}"
                retryable_http = response.status == 429 or response.status >= 500
                retryable = retryable_http or code in retryable_codes
                ambiguous = response.status >= 500 or code == 1255040
                if not retryable or (ambiguous and not retry_ambiguous):
                    break
            if attempt < 3:
                await asyncio.sleep(attempt)
        raise RuntimeError(f"Lark request {method} {path} failed: {last_error}")

    async def read_source_rows(self) -> list[list[object]]:
        data = await self._request(
            "GET",
            f"/sheets/v2/spreadsheets/{SOURCE_SPREADSHEET_TOKEN}/values/"
            f"{SOURCE_SHEET_ID}!A:Q",
        )
        return data["data"]["valueRange"].get("values", [])

    async def list_fields(self) -> list[dict[str, object]]:
        data = await self._request(
            "GET",
            f"/bitable/v1/apps/{TARGET_APP_TOKEN}/tables/{TARGET_TABLE_ID}/fields",
            params={"page_size": "100"},
        )
        return data["data"].get("items", [])

    async def rename_field(self, field_id: str, field_name: str, field_type: int) -> None:
        await self._request(
            "PUT",
            f"/bitable/v1/apps/{TARGET_APP_TOKEN}/tables/{TARGET_TABLE_ID}/fields/{field_id}",
            json={"field_name": field_name, "type": field_type},
        )

    async def create_field(self, definition: dict[str, object]) -> None:
        await self._request(
            "POST",
            f"/bitable/v1/apps/{TARGET_APP_TOKEN}/tables/{TARGET_TABLE_ID}/fields",
            json=definition,
            retry_ambiguous=False,
        )

    async def list_views(self) -> list[dict[str, object]]:
        data = await self._request(
            "GET",
            f"/bitable/v1/apps/{TARGET_APP_TOKEN}/tables/{TARGET_TABLE_ID}/views",
            params={"page_size": "100"},
        )
        return data["data"].get("items", [])

    async def rename_view(self, view_id: str, view_name: str) -> None:
        await self._request(
            "PATCH",
            f"/bitable/v1/apps/{TARGET_APP_TOKEN}/tables/{TARGET_TABLE_ID}/views/{view_id}",
            json={"view_name": view_name},
        )

    async def create_view(self, view_name: str) -> None:
        await self._request(
            "POST",
            f"/bitable/v1/apps/{TARGET_APP_TOKEN}/tables/{TARGET_TABLE_ID}/views",
            json={"view_name": view_name, "view_type": "grid"},
            retry_ambiguous=False,
        )

    async def list_records(self) -> list[dict[str, object]]:
        items: list[dict[str, object]] = []
        page_token: str | None = None
        while True:
            params = {"page_size": "500"}
            if page_token:
                params["page_token"] = page_token
            data = await self._request(
                "GET",
                f"/bitable/v1/apps/{TARGET_APP_TOKEN}/tables/{TARGET_TABLE_ID}/records",
                params=params,
            )
            items.extend(data["data"].get("items", []))
            if not data["data"].get("has_more"):
                return items
            page_token = str(data["data"]["page_token"])

    async def delete_records(self, record_ids: list[str]) -> None:
        for start in range(0, len(record_ids), _BATCH_SIZE):
            await self._request(
                "POST",
                f"/bitable/v1/apps/{TARGET_APP_TOKEN}/tables/{TARGET_TABLE_ID}/records/batch_delete",
                json={"records": record_ids[start : start + _BATCH_SIZE]},
            )

    async def create_records(self, fields_list: list[dict[str, object]]) -> None:
        for start in range(0, len(fields_list), _BATCH_SIZE):
            chunk = fields_list[start : start + _BATCH_SIZE]
            await self._request(
                "POST",
                f"/bitable/v1/apps/{TARGET_APP_TOKEN}/tables/{TARGET_TABLE_ID}/records/batch_create",
                json={"records": [{"fields": fields} for fields in chunk]},
                retry_ambiguous=False,
            )

    async def update_records(self, updates: list[dict[str, object]]) -> None:
        for start in range(0, len(updates), _BATCH_SIZE):
            await self._request(
                "POST",
                f"/bitable/v1/apps/{TARGET_APP_TOKEN}/tables/{TARGET_TABLE_ID}/records/batch_update",
                json={"records": updates[start : start + _BATCH_SIZE]},
            )


async def _ensure_schema(client: Any) -> None:
    fields = await client.list_fields()
    by_name = {str(field["field_name"]): field for field in fields}
    if "记录" not in by_name:
        primary = next((field for field in fields if field.get("is_primary")), None)
        if primary is None:
            primary = next((field for field in fields if field.get("field_name") == "文本"), None)
        if primary is None:
            raise RuntimeError("target table primary field was not found")
        await client.rename_field(str(primary["field_id"]), "记录", 1)
        fields = await client.list_fields()
        by_name = {str(field["field_name"]): field for field in fields}
    for definition in FIELD_DEFINITIONS:
        name = str(definition["field_name"])
        existing = by_name.get(name)
        if existing is None:
            await client.create_field(dict(definition))
            continue
        if int(existing["type"]) != int(definition["type"]):
            raise RuntimeError(
                f"field {name!r} has type {existing['type']}, expected {definition['type']}"
            )

def _plan_record_changes(
    remote_records: list[dict[str, object]],
    expected_records: list[dict[str, object]],
) -> tuple[list[str], list[dict[str, object]], list[dict[str, object]]]:
    expected_by_key = {str(record["记录"]): record for record in expected_records}
    blank_ids: list[str] = []
    remote_by_key: dict[str, dict[str, object]] = {}
    for record in remote_records:
        fields = record.get("fields") or {}
        if not isinstance(fields, dict):
            raise RuntimeError("remote record fields must be an object")
        if _is_blank_fields(fields):
            blank_ids.append(str(record["record_id"]))
            continue
        key = _extract_text(fields.get("记录") or fields.get("文本"))
        if not key:
            raise RuntimeError(f"non-empty remote record {record['record_id']} has no primary key")
        if key in remote_by_key:
            raise RuntimeError(f"duplicate remote record key: {key}")
        if key not in expected_by_key:
            raise RuntimeError(f"unexpected non-empty remote record: {key}")
        remote_by_key[key] = record

    creates = [record for key, record in expected_by_key.items() if key not in remote_by_key]
    updates: list[dict[str, object]] = []
    for key, expected in expected_by_key.items():
        remote = remote_by_key.get(key)
        if remote is None:
            continue
        fields = remote["fields"]
        if isinstance(fields, dict) and _record_differs(fields, expected):
            updates.append({"record_id": remote["record_id"], "fields": expected})
    return blank_ids, creates, updates


def _verify_remote_records(
    remote_records: list[dict[str, object]],
    expected_records: list[dict[str, object]],
) -> None:
    blank_ids, creates, updates = _plan_record_changes(remote_records, expected_records)
    if blank_ids or creates or updates:
        raise RuntimeError(
            "remote verification failed: "
            f"blank={len(blank_ids)}, missing={len(creates)}, mismatched={len(updates)}"
        )
    if len(remote_records) != len(expected_records):
        raise RuntimeError(
            f"remote verification expected {len(expected_records)} records, got {len(remote_records)}"
        )


async def run_migration(client: Any, *, apply: bool) -> MigrationReport:
    rows = await client.read_source_rows()
    expected = build_migration_records(rows)
    validate_migration_records(expected)

    if apply:
        await _ensure_schema(client)
    remote = await client.list_records()
    deletes, creates, updates = _plan_record_changes(remote, expected)
    verified = not deletes and not creates and not updates and len(remote) == len(expected)
    daily = sum(record.get("统计类型") == "日报" for record in expected)
    weekly = sum(record.get("统计类型") == "周报" for record in expected)
    report = MigrationReport(
        daily=daily,
        weekly=weekly,
        creates=len(creates),
        updates=len(updates),
        deletes=len(deletes),
        applied=apply,
        verified=verified,
    )
    if not apply:
        return report

    await client.delete_records(deletes)
    await client.update_records(updates)
    await client.create_records(creates)
    final_records = await client.list_records()
    _verify_remote_records(final_records, expected)
    return MigrationReport(**{**report.__dict__, "verified": True})


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"'))


async def _main(apply: bool) -> None:
    _load_dotenv(Path.cwd() / ".env")
    app_id = os.getenv("LARK_APP_ID", "")
    app_secret = os.getenv("LARK_APP_SECRET", "")
    if not app_id or not app_secret:
        raise RuntimeError("LARK_APP_ID and LARK_APP_SECRET are required")
    async with LarkMigrationClient(app_id, app_secret) as client:
        report = await run_migration(client, apply=apply)
    print(
        "migration_report "
        f"daily={report.daily} weekly={report.weekly} total={report.daily + report.weekly} "
        f"creates={report.creates} updates={report.updates} deletes={report.deletes} "
        f"apply={report.applied} verified={report.verified}",
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate Discord community metrics to Lark Base")
    parser.add_argument("--apply", action="store_true", help="write the planned migration")
    args = parser.parse_args()
    asyncio.run(_main(args.apply))
