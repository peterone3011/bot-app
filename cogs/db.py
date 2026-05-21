from __future__ import annotations

import os
from typing import Any

from supabase import Client, create_client

_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_SERVICE_KEY"],
        )
    return _client


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

def load_messages() -> list[dict[str, Any]]:
    return get_client().table("messages").select("*").execute().data


def get_message(msg_id: str) -> dict[str, Any] | None:
    rows = get_client().table("messages").select("*").eq("id", msg_id).execute().data
    return rows[0] if rows else None


def upsert_message(msg: dict[str, Any]) -> None:
    get_client().table("messages").upsert(msg).execute()


def delete_message(msg_id: str) -> None:
    get_client().table("messages").delete().eq("id", msg_id).execute()


# ---------------------------------------------------------------------------
# Sites
# ---------------------------------------------------------------------------

def load_sites() -> list[str]:
    rows = get_client().table("sites").select("name").order("display_order").execute().data
    return [row["name"] for row in rows]


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def get_config(key: str, default: str = "") -> str:
    rows = get_client().table("config").select("value").eq("key", key).execute().data
    return rows[0]["value"] if rows else default
