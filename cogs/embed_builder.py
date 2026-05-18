from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands, tasks

MESSAGES_FILE = Path("messages.json")
CST = timezone(timedelta(hours=8))


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def load_messages() -> list[dict[str, Any]]:
    try:
        return json.loads(MESSAGES_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []


def save_messages(messages: list[dict[str, Any]]) -> None:
    MESSAGES_FILE.write_text(
        json.dumps(messages, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_message(msg_id: str) -> dict[str, Any] | None:
    return next((m for m in load_messages() if m["id"] == msg_id), None)


def upsert_message(msg: dict[str, Any]) -> None:
    messages = load_messages()
    for i, m in enumerate(messages):
        if m["id"] == msg["id"]:
            messages[i] = msg
            save_messages(messages)
            return
    messages.append(msg)
    save_messages(messages)


def delete_message(msg_id: str) -> None:
    save_messages([m for m in load_messages() if m["id"] != msg_id])


def new_draft(channel_id: int, label: str | None = None) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "status": "draft",
        "label": label,
        "created_at": datetime.now(CST).isoformat(),
        "channel_id": channel_id,
        "send_at": None,
        "message_id": None,
        "title": None,
        "description": None,
        "footer": None,
        "image_url": None,
        "button_label": None,
        "button_url": None,
        "color": None,
    }
