from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial
import os
from typing import Any

from supabase import Client, ClientOptions, create_client

_client: Client | None = None
_activity_read_client: Client | None = None
_activity_rpc_client: Client | None = None

ACTIVITY_DB_MAX_WORKERS = 4
ACTIVITY_DB_READ_TIMEOUT = 1.5
ACTIVITY_DB_FUNCTION_TIMEOUT = 8.0
_activity_executor = ThreadPoolExecutor(
    max_workers=ACTIVITY_DB_MAX_WORKERS,
    thread_name_prefix="activity-db",
)


def get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_SERVICE_KEY"],
        )
    return _client


def get_activity_read_client() -> Client:
    global _activity_read_client
    if _activity_read_client is None:
        _activity_read_client = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_SERVICE_KEY"],
            options=ClientOptions(
                postgrest_client_timeout=ACTIVITY_DB_READ_TIMEOUT,
            ),
        )
    return _activity_read_client


def get_activity_rpc_client() -> Client:
    global _activity_rpc_client
    if _activity_rpc_client is None:
        _activity_rpc_client = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_SERVICE_KEY"],
            options=ClientOptions(
                postgrest_client_timeout=ACTIVITY_DB_FUNCTION_TIMEOUT,
            ),
        )
    return _activity_rpc_client


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

def load_messages() -> list[dict[str, Any]]:
    return get_client().table("messages").select("*").execute().data


def get_message(msg_id: str) -> dict[str, Any] | None:
    rows = get_client().table("messages").select("*").eq("id", msg_id).limit(1).execute().data
    return rows[0] if rows else None


def upsert_message(msg: dict[str, Any]) -> None:
    get_client().table("messages").upsert(msg).execute()


def delete_message(msg_id: str) -> None:
    get_client().table("messages").delete().eq("id", msg_id).execute()


# ---------------------------------------------------------------------------
# Async wrappers (run sync Supabase calls in a thread pool)
# ---------------------------------------------------------------------------

async def aload_messages() -> list[dict[str, Any]]:
    return await asyncio.to_thread(load_messages)


async def aget_message(msg_id: str) -> dict[str, Any] | None:
    return await asyncio.to_thread(get_message, msg_id)


async def aupsert_message(msg: dict[str, Any]) -> None:
    await asyncio.to_thread(upsert_message, msg)


async def adelete_message(msg_id: str) -> None:
    await asyncio.to_thread(delete_message, msg_id)


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------

def load_roles() -> list[dict]:
    rows = (
        get_client()
        .table("roles")
        .select("id, label, description, display_order")
        .order("display_order")
        .execute()
        .data
    )
    return rows


async def aload_roles() -> list[dict]:
    return await asyncio.to_thread(load_roles)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def get_config(key: str, default: str = "") -> str:
    rows = get_client().table("config").select("value").eq("key", key).execute().data
    return rows[0]["value"] if rows else default


# ---------------------------------------------------------------------------
# Reusable activities
# ---------------------------------------------------------------------------

def get_activity_by_message(message_id: str) -> dict[str, Any] | None:
    rows = (
        get_activity_read_client()
        .table("activity_campaigns")
        .select("*")
        .eq("discord_message_id", message_id)
        .limit(1)
        .execute()
        .data
    )
    if not rows:
        return None

    activity = dict(rows[0])
    activity["questions"] = (
        get_activity_read_client()
        .table("activity_questions")
        .select("*")
        .eq("campaign_id", activity["id"])
        .order("position")
        .execute()
        .data
    )
    return activity


async def aget_activity_by_message(message_id: str) -> dict[str, Any] | None:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _activity_executor, get_activity_by_message, message_id
    )


def claim_activity_reward(
    *,
    campaign_id: str,
    discord_user_id: str,
    discord_username: str,
    answers: dict[str, str],
    participant_key: str | None,
) -> dict[str, Any]:
    rows = (
        get_activity_rpc_client()
        .rpc(
            "claim_activity_reward",
            {
                "p_campaign_id": campaign_id,
                "p_discord_user_id": discord_user_id,
                "p_discord_username": discord_username,
                "p_answers": answers,
                "p_participant_key": participant_key,
            },
        )
        .execute()
        .data
    )
    if not rows:
        raise RuntimeError("claim_activity_reward returned no result")
    return rows[0]


async def aclaim_activity_reward(
    *,
    campaign_id: str,
    discord_user_id: str,
    discord_username: str,
    answers: dict[str, str],
    participant_key: str | None,
) -> dict[str, Any]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _activity_executor,
        partial(
            claim_activity_reward,
            campaign_id=campaign_id,
            discord_user_id=discord_user_id,
            discord_username=discord_username,
            answers=answers,
            participant_key=participant_key,
        ),
    )
