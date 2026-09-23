from __future__ import annotations

from typing import Any

import pytest

from app.core.feishu import FeishuApiError, FeishuClient, HttpResponse


@pytest.mark.asyncio
async def test_list_records_reuses_tenant_token_and_paginates() -> None:
    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    async def transport(
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> HttpResponse:
        calls.append((method, path, params))
        if path == "/auth/v3/tenant_access_token/internal":
            return HttpResponse(200, {"code": 0, "tenant_access_token": "tenant", "expire": 3600})
        if params and params.get("page_token") == "second":
            return HttpResponse(200, {"code": 0, "data": {"items": [{"record_id": "2"}], "has_more": False}})
        return HttpResponse(200, {"code": 0, "data": {"items": [{"record_id": "1"}], "has_more": True, "page_token": "second"}})

    client = FeishuClient("app-id", "app-secret", transport=transport)

    assert await client.list_records("base", "table") == [{"record_id": "1"}, {"record_id": "2"}]
    await client.list_records("base", "table")

    assert sum(path == "/auth/v3/tenant_access_token/internal" for _, path, _ in calls) == 1


@pytest.mark.asyncio
async def test_list_records_treats_an_empty_response_without_items_as_no_records() -> None:
    async def transport(
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> HttpResponse:
        if path == "/auth/v3/tenant_access_token/internal":
            return HttpResponse(
                200,
                {"code": 0, "tenant_access_token": "tenant", "expire": 3600},
            )
        return HttpResponse(200, {"code": 0, "data": {"has_more": False, "total": 0}})

    client = FeishuClient("app-id", "app-secret", transport=transport)

    assert await client.list_records("base", "table") == []


@pytest.mark.asyncio
async def test_upsert_rejects_duplicate_text_keys_before_writing() -> None:
    methods: list[str] = []

    async def transport(
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> HttpResponse:
        methods.append(method)
        if path == "/auth/v3/tenant_access_token/internal":
            return HttpResponse(200, {"code": 0, "tenant_access_token": "tenant", "expire": 3600})
        return HttpResponse(
            200,
            {"code": 0, "data": {"items": [
                {"record_id": "1", "fields": {"日期": "2026/09/15"}},
                {"record_id": "2", "fields": {"日期": "2026/09/15"}},
            ], "has_more": False}},
        )

    client = FeishuClient("app-id", "app-secret", transport=transport)

    with pytest.raises(FeishuApiError, match="duplicate records"):
        await client.upsert_record_by_text_field(
            "base", "table", "日期", "2026/09/15", {"日期": "2026/09/15"}
        )

    assert methods == ["POST", "GET"]


@pytest.mark.asyncio
async def test_api_error_invalidates_cached_token() -> None:
    token_calls = 0

    async def transport(
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> HttpResponse:
        nonlocal token_calls
        if path == "/auth/v3/tenant_access_token/internal":
            token_calls += 1
            return HttpResponse(200, {"code": 0, "tenant_access_token": f"tenant-{token_calls}", "expire": 3600})
        return HttpResponse(400, {"code": 999, "msg": "bad request"})

    client = FeishuClient("app-id", "app-secret", transport=transport)

    with pytest.raises(FeishuApiError, match="bad request"):
        await client.list_records("base", "table")
    with pytest.raises(FeishuApiError, match="bad request"):
        await client.list_records("base", "table")

    assert token_calls == 2
