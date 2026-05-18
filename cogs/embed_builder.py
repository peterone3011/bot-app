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


# ---------------------------------------------------------------------------
# Parsing utilities
# ---------------------------------------------------------------------------

def parse_color(value: str) -> int | None:
    """Returns color int, None for empty input, -1 for invalid."""
    value = value.strip().lstrip("#")
    if not value:
        return None
    if len(value) != 6:
        return -1
    try:
        return int(value, 16)
    except ValueError:
        return -1


def parse_send_at(value: str) -> str | None:
    """Returns ISO 8601 string (UTC+8) or None if invalid or in the past."""
    try:
        dt = datetime.strptime(value.strip(), "%Y-%m-%d %H:%M").replace(tzinfo=CST)
    except ValueError:
        return None
    if dt <= datetime.now(CST):
        return None
    return dt.isoformat()


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def build_embed(msg: dict[str, Any]) -> discord.Embed:
    embed = discord.Embed(
        title=msg["title"],
        description=msg["description"],
        color=msg["color"],
    )
    if msg["footer"]:
        embed.set_footer(text=msg["footer"])
    if msg["image_url"]:
        embed.set_image(url=msg["image_url"])
    return embed


def build_view(msg: dict[str, Any]) -> discord.ui.View | None:
    if not (msg["button_label"] and msg["button_url"]):
        return None
    view = discord.ui.View()
    view.add_item(discord.ui.Button(
        label=msg["button_label"],
        url=msg["button_url"],
        style=discord.ButtonStyle.link,
    ))
    return view


def display_label(msg: dict[str, Any], bot: commands.Bot | None) -> str:
    if msg.get("label"):
        return msg["label"]
    if bot:
        ch = bot.get_channel(msg["channel_id"])
        ch_name = f"#{ch.name}" if ch else f"#{msg['channel_id']}"
    else:
        ch_name = f"#{msg['channel_id']}"
    date = (msg.get("created_at") or "")[:10]
    title = msg.get("title") or ""
    preview = (title[:20] + "…") if len(title) > 20 else (title or "(untitled)")
    return f"{ch_name} · {date} · \"{preview}\""


# ---------------------------------------------------------------------------
# Content formatters
# ---------------------------------------------------------------------------

def _field_summary(msg: dict[str, Any]) -> str:
    color_val = msg["color"]
    color_str = f"#{color_val:06X}" if color_val is not None else "(none)"
    desc = msg["description"] or ""
    desc_preview = (desc[:50] + "…") if len(desc) > 50 else (desc or "(none)")
    btn = f"{msg['button_label']} | {msg['button_url']}" if (msg["button_label"] and msg["button_url"]) else "(none)"
    return "\n".join([
        f"Title:       {msg['title'] or '(none)'}",
        f"Description: {desc_preview}",
        f"Footer:      {msg['footer'] or '(none)'}",
        f"Image:       {'set' if msg['image_url'] else '(none)'}",
        f"Button:      {btn}",
        f"Color:       {color_str}",
    ])


def format_builder_content(msg: dict[str, Any]) -> str:
    status = "Scheduled" if msg["status"] == "scheduled" else "Draft"
    send_time = ""
    if msg["send_at"]:
        send_time = " · " + msg["send_at"][:16].replace("T", " ")
    header = f"**{msg.get('label') or '(untitled)'}**  |  <#{msg['channel_id']}>  |  {status}{send_time}"
    return f"{header}\n\n```\n{_field_summary(msg)}\n```"


def format_edit_fields_content(msg: dict[str, Any]) -> str:
    return f"**Edit Fields** — click a field to update it\n\n```\n{_field_summary(msg)}\n```"
