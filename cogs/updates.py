import io
import os
import asyncio
import random
import datetime
from typing import Optional

import aiohttp
import discord
from discord.ext import commands, tasks

# ── Constants ────────────────────────────────────────────────────────────────

_BJT = datetime.timezone(datetime.timedelta(hours=8))
_UTC = datetime.timezone.utc
_POST_WEEKDAYS = {1, 3, 5}  # Tuesday=1, Thursday=3, Saturday=5 (UTC weekday, same day as BJT at 15:50 UTC)
_BROADCAST_TIME = datetime.time(hour=15, minute=50, tzinfo=_UTC)

UPDATE_CHANNEL_ID: int = int(os.getenv("UPDATE_CHANNEL_ID", "0"))
STAFF_CHAT_CHANNEL_ID: int = int(os.getenv("STAFF_CHAT_CHANNEL_ID", "0"))
MOD_ROLE_ID: int = int(os.getenv("DISCORD_ADMIN_ROLE_ID", "0"))

LARK_BASE = "https://open.larksuite.com/open-apis"
LARK_APP_ID: str = os.getenv("LARK_APP_ID", "")
LARK_APP_SECRET: str = os.getenv("LARK_APP_SECRET", "")
LARK_SPREADSHEET_TOKEN: str = os.getenv("LARK_SPREADSHEET_TOKEN", "")
LARK_SHEET_ID: str = os.getenv("LARK_SHEET_ID", "")

REACTION_POOL = [
    "🎉", "🎊", "🔥", "💜", "✨", "🚀", "💰", "🎰",
    "👑", "🌟", "💎", "🙌", "😍", "🤩", "💪", "🎯",
    "⚡", "🏆", "🎁", "💫",
]

# ── Pure helpers (tested) ─────────────────────────────────────────────────────

def parse_rich_text(cell_value) -> str:
    """Convert Lark cell value (plain string or rich-text array) to plain text.

    URL nodes get https:// prepended if missing.
    """
    if cell_value is None:
        return ""
    if isinstance(cell_value, str):
        return cell_value
    if isinstance(cell_value, list):
        parts = []
        for node in cell_value:
            if not isinstance(node, dict):
                continue
            if node.get("type") == "url":
                link = node.get("link", "")
                if link and not link.startswith(("https://", "http://")):
                    link = "https://" + link
                parts.append(link)
            else:
                parts.append(node.get("text", ""))
        return "".join(parts)
    return str(cell_value)


def get_image_token(cell_value) -> Optional[str]:
    """Return Lark fileToken if cell contains an embed-image, else None."""
    if not cell_value:
        return None
    if isinstance(cell_value, str) and cell_value.strip() in ("无", ""):
        return None
    if isinstance(cell_value, dict) and cell_value.get("type") == "embed-image":
        return cell_value.get("fileToken")
    return None


def find_pending_row(
    rows: list,
    today: Optional[datetime.date] = None,
) -> Optional[tuple]:
    """Scan rows for the first exclusive-updates row that is 待发布 and due.

    Args:
        rows: raw values list from Lark Sheets API (0-indexed, row 0 = title).
        today: date to compare against; defaults to current BJT date.

    Returns:
        (sheet_row_1based: int, row: list) or None.
    """
    if today is None:
        today = datetime.datetime.now(_BJT).date()
    for i, row in enumerate(rows):
        if len(row) < 6:
            continue
        date_val, channel, _, _, _, status = row[0], row[1], row[2], row[3], row[4], row[5]
        if not date_val or not channel or not status:
            continue
        if str(channel).strip() != "exclusive-updates":
            continue
        if str(status).strip() != "待发布":
            continue
        try:
            row_date = datetime.datetime.strptime(str(date_val).strip(), "%Y-%m-%d %H:%M").date()
        except ValueError:
            continue
        if row_date <= today:
            return (i + 1, row)  # i+1 converts to 1-based sheet row
    return None
