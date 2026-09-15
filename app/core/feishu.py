from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any, Awaitable, Callable, Literal
import uuid

import aiohttp


FEISHU_API_BASE = "https://open.feishu.cn/open-apis"


class FeishuApiError(RuntimeError):
    """Raised when Feishu rejects a request or returns an invalid response."""


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: dict[str, Any]


Transport = Callable[
    [str, str],
    Awaitable[HttpResponse],
]


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


def _client_token(app_token: str, table_id: str, key: str) -> str:
    digest = hashlib.sha256(f"{app_token}:{table_id}:{key}".encode("utf-8")).digest()
    raw = bytearray(digest[:16])
    raw[6] = (raw[6] & 0x0F) | 0x40
    raw[8] = (raw[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(raw)))


class FeishuClient:
    def __init__(
        self,
        app_id: str,
        app_secret: str,
        *,
        transport: Callable[..., Awaitable[HttpResponse]] | None = None,
    ) -> None:
        self._app_id = app_id
        self._app_secret = app_secret
        self._transport = transport or self._aiohttp_transport
        self._token: str | None = None
        self._token_expires_at = datetime.min.replace(tzinfo=timezone.utc)
        self._upsert_lock = asyncio.Lock()

    async def _aiohttp_transport(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> HttpResponse:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30)
        ) as session:
            async with session.request(
                method,
                f"{FEISHU_API_BASE}{path}",
                params=params,
                json=payload,
                headers=headers,
            ) as response:
                raw = await response.text()
                try:
                    body = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise FeishuApiError(
                        f"Feishu {method} returned non-JSON HTTP {response.status}: {raw[:200]}"
                    ) from exc
                if not isinstance(body, dict):
                    raise FeishuApiError(f"Feishu {method} returned an invalid JSON body")
                return HttpResponse(response.status, body)

    async def _call_transport(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> HttpResponse:
        return await self._transport(
            method,
            path,
            params=params,
            payload=payload,
            headers=headers,
        )

    @staticmethod
    def _validate_response(method: str, response: HttpResponse) -> dict[str, Any]:
        body = response.body
        if response.status >= 400 or body.get("code") != 0:
            raise FeishuApiError(
                f"Feishu {method} error: HTTP {response.status}: {body.get('msg', 'unknown error')}"
            )
        return body

    async def _tenant_token(self) -> str:
        now = datetime.now(timezone.utc)
        if self._token and now < self._token_expires_at:
            return self._token
        response = await self._call_transport(
            "POST",
            "/auth/v3/tenant_access_token/internal",
            payload={"app_id": self._app_id, "app_secret": self._app_secret},
        )
        body = self._validate_response("POST", response)
        token = str(body.get("tenant_access_token") or "")
        if not token:
            raise FeishuApiError("Feishu token response missing tenant_access_token")
        expire_seconds = max(60, int(body.get("expire", 3600)) - 300)
        self._token = token
        self._token_expires_at = now + timedelta(seconds=expire_seconds)
        return token

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        token = await self._tenant_token()
        try:
            response = await self._call_transport(
                method,
                path,
                params=params,
                payload=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
            )
            return self._validate_response(method, response)
        except Exception:
            self._token = None
            self._token_expires_at = datetime.min.replace(tzinfo=timezone.utc)
            raise

    async def list_records(self, app_token: str, table_id: str) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        page_token: str | None = None
        path = f"/bitable/v1/apps/{app_token}/tables/{table_id}/records"
        while True:
            params = {"page_size": "500"}
            if page_token:
                params["page_token"] = page_token
            body = await self._request("GET", path, params=params)
            data = body.get("data")
            if not isinstance(data, dict):
                raise FeishuApiError("Feishu list records response missing data")
            items = data.get("items")
            if not isinstance(items, list):
                raise FeishuApiError("Feishu list records response missing items")
            records.extend(item for item in items if isinstance(item, dict))
            if not data.get("has_more"):
                return records
            page_token = str(data.get("page_token") or "")
            if not page_token:
                raise FeishuApiError("Feishu list records pagination missing page_token")

    async def update_record(
        self,
        app_token: str,
        table_id: str,
        record_id: str,
        fields: dict[str, Any],
    ) -> None:
        await self._request(
            "PUT",
            f"/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}",
            payload={"fields": fields},
        )

    async def create_record(
        self,
        app_token: str,
        table_id: str,
        key: str,
        fields: dict[str, Any],
    ) -> None:
        await self._request(
            "POST",
            f"/bitable/v1/apps/{app_token}/tables/{table_id}/records",
            params={"client_token": _client_token(app_token, table_id, key)},
            payload={"fields": fields},
        )

    async def upsert_record_by_text_field(
        self,
        app_token: str,
        table_id: str,
        key_field: str,
        key: str,
        fields: dict[str, Any],
    ) -> Literal["created", "updated"]:
        async with self._upsert_lock:
            records = await self.list_records(app_token, table_id)
            matches = [
                record
                for record in records
                if _extract_text((record.get("fields") or {}).get(key_field)) == key
            ]
            if len(matches) > 1:
                raise FeishuApiError(
                    f"Feishu table contains duplicate records for {key_field}={key!r}"
                )
            if matches:
                await self.update_record(app_token, table_id, str(matches[0]["record_id"]), fields)
                return "updated"
            await self.create_record(app_token, table_id, key, fields)
            return "created"
