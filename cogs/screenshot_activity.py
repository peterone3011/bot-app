from __future__ import annotations

import asyncio
import datetime
import os
from dataclasses import dataclass
from typing import Any

import aiohttp
import discord
from discord.ext import commands

_BJT = datetime.timezone(datetime.timedelta(hours=8))
_UTC = datetime.timezone.utc

LARK_BASE = "https://open.larksuite.com/open-apis"
LARK_APP_ID = os.getenv("LARK_APP_ID", "")
LARK_APP_SECRET = os.getenv("LARK_APP_SECRET", "")

SCREENSHOT_ACTIVITY_CHANNEL_ID = int(os.getenv("SCREENSHOT_ACTIVITY_CHANNEL_ID", "0") or "0")
SCREENSHOT_CODES_SPREADSHEET_TOKEN = os.getenv(
    "SCREENSHOT_CODES_SPREADSHEET_TOKEN",
    os.getenv("COMMUNITY_METRICS_SPREADSHEET_TOKEN", "PA8usyjmshX40HtXaeTjkr4Apne"),
)
SCREENSHOT_CODES_SHEET_ID = os.getenv("SCREENSHOT_CODES_SHEET_ID", "")
SCREENSHOT_CODES_RANGE = os.getenv("SCREENSHOT_CODES_RANGE", "A:I")

_STATUS_AVAILABLE = {"", "available", "可用"}
_STATUS_RESERVED = "reserved"
_STATUS_SENT = "sent"
_STATUS_DM_FAILED = "dm_failed"

_SUCCESS_REPLY = "Thanks! Your reward code has been sent by DM."
_ALREADY_CLAIMED_REPLY = "You have already claimed this activity reward."
_NO_CODES_REPLY = "All reward codes have been claimed."
_DM_FAILED_REPLY = "Your reward was reserved, but I could not DM you. Please contact the team."
_NEED_SCREENSHOT_REPLY = "Please attach a screenshot to join this activity."
_DM_TEMPLATE = "Congratulations! Your reward code is: **{code}**"


@dataclass(frozen=True)
class CodeClaim:
    row_number: int
    code: str


def _now_bjt() -> datetime.datetime:
    return datetime.datetime.now(_BJT)


def _format_ts(dt: datetime.datetime) -> str:
    return dt.astimezone(_BJT).strftime("%Y/%m/%d %H:%M:%S")


def _cell(row: list[Any], index: int) -> str:
    if index >= len(row) or row[index] is None:
        return ""
    return str(row[index]).strip()


def _is_available_status(value: Any) -> bool:
    return str(value or "").strip().lower() in _STATUS_AVAILABLE


def _has_image_attachment(message: discord.Message) -> bool:
    return any(_is_image_attachment(attachment) for attachment in message.attachments)


def _is_image_attachment(attachment: discord.Attachment) -> bool:
    content_type = (attachment.content_type or "").lower()
    if content_type.startswith("image/"):
        return True
    filename = attachment.filename.lower()
    return filename.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp"))


def _first_image_url(message: discord.Message) -> str:
    for attachment in message.attachments:
        if _is_image_attachment(attachment):
            return attachment.url
    return ""


def _find_existing_claim(values: list[list[Any]], discord_user_id: int) -> int | None:
    user_id = str(discord_user_id)
    for index, row in enumerate(values[1:], start=2):
        if _cell(row, 2) == user_id and _cell(row, 1).lower() in {
            _STATUS_RESERVED,
            _STATUS_SENT,
            _STATUS_DM_FAILED,
        }:
            return index
    return None


def _find_next_available_code(values: list[list[Any]]) -> CodeClaim | None:
    for index, row in enumerate(values[1:], start=2):
        code = _cell(row, 0)
        if code and _is_available_status(_cell(row, 1)):
            return CodeClaim(row_number=index, code=code)
    return None


def _claim_row_values(
    *,
    status: str,
    user: discord.abc.User,
    message: discord.Message,
    screenshot_url: str,
    claimed_at: datetime.datetime,
    dm_status: str,
    note: str = "",
) -> list[Any]:
    return [
        status,
        str(user.id),
        getattr(user, "global_name", None) or user.name,
        str(message.id),
        screenshot_url,
        _format_ts(claimed_at),
        dm_status,
        note,
    ]


class ScreenshotCodeSheet:
    def __init__(self) -> None:
        self._token: str | None = None
        self._token_expires_at = datetime.datetime.min.replace(tzinfo=_UTC)

    async def _get_token(self) -> str:
        now = datetime.datetime.now(_UTC)
        if self._token and now < self._token_expires_at:
            return self._token
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{LARK_BASE}/auth/v3/app_access_token/internal",
                json={"app_id": LARK_APP_ID, "app_secret": LARK_APP_SECRET},
            ) as resp:
                data = await resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Lark token error: {data.get('msg')}")
        self._token = data["tenant_access_token"]
        self._token_expires_at = now + datetime.timedelta(seconds=int(data.get("expire", 3600)) - 300)
        return self._token

    async def read_codes(self) -> list[list[Any]]:
        token = await self._get_token()
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{LARK_BASE}/sheets/v2/spreadsheets/{SCREENSHOT_CODES_SPREADSHEET_TOKEN}"
                f"/values/{SCREENSHOT_CODES_SHEET_ID}!{SCREENSHOT_CODES_RANGE}",
                headers={"Authorization": f"Bearer {token}"},
            ) as resp:
                data = await resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Lark read error: {data.get('msg')}")
        return data["data"]["valueRange"].get("values", [])

    async def write_claim(self, row_number: int, values: list[Any]) -> None:
        token = await self._get_token()
        async with aiohttp.ClientSession() as session:
            async with session.put(
                f"{LARK_BASE}/sheets/v2/spreadsheets/{SCREENSHOT_CODES_SPREADSHEET_TOKEN}/values",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"},
                json={
                    "valueRange": {
                        "range": f"{SCREENSHOT_CODES_SHEET_ID}!B{row_number}:I{row_number}",
                        "values": [values],
                    }
                },
            ) as resp:
                data = await resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Lark write error: {data.get('msg')}")


class ScreenshotActivityCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.sheet = ScreenshotCodeSheet()
        self._lock = asyncio.Lock()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if not SCREENSHOT_ACTIVITY_CHANNEL_ID or message.channel.id != SCREENSHOT_ACTIVITY_CHANNEL_ID:
            return
        if not SCREENSHOT_CODES_SHEET_ID:
            print("[screenshot_activity] SCREENSHOT_CODES_SHEET_ID is not configured", flush=True)
            return
        if not _has_image_attachment(message):
            await message.reply(_NEED_SCREENSHOT_REPLY, mention_author=False)
            return
        await self._process_submission(message)

    async def _process_submission(self, message: discord.Message) -> None:
        async with self._lock:
            try:
                values = await self.sheet.read_codes()
                if _find_existing_claim(values, message.author.id) is not None:
                    await message.reply(_ALREADY_CLAIMED_REPLY, mention_author=False)
                    return

                claim = _find_next_available_code(values)
                if claim is None:
                    await message.reply(_NO_CODES_REPLY, mention_author=False)
                    return

                screenshot_url = _first_image_url(message)
                claimed_at = _now_bjt()
                await self.sheet.write_claim(
                    claim.row_number,
                    _claim_row_values(
                        status=_STATUS_RESERVED,
                        user=message.author,
                        message=message,
                        screenshot_url=screenshot_url,
                        claimed_at=claimed_at,
                        dm_status="pending",
                    ),
                )
            except Exception as exc:
                print(f"[screenshot_activity] Failed to reserve code: {exc}", flush=True)
                return

        try:
            await message.author.send(_DM_TEMPLATE.format(code=claim.code))
        except Exception as exc:
            print(f"[screenshot_activity] Failed to DM {message.author.id}: {exc}", flush=True)
            try:
                await self.sheet.write_claim(
                    claim.row_number,
                    _claim_row_values(
                        status=_STATUS_DM_FAILED,
                        user=message.author,
                        message=message,
                        screenshot_url=screenshot_url,
                        claimed_at=claimed_at,
                        dm_status="failed",
                        note=str(exc)[:200],
                    ),
                )
            except Exception as write_exc:
                print(f"[screenshot_activity] Failed to record DM failure: {write_exc}", flush=True)
            await message.reply(_DM_FAILED_REPLY, mention_author=False)
            return

        try:
            await self.sheet.write_claim(
                claim.row_number,
                _claim_row_values(
                    status=_STATUS_SENT,
                    user=message.author,
                    message=message,
                    screenshot_url=screenshot_url,
                    claimed_at=claimed_at,
                    dm_status="sent",
                ),
            )
        except Exception as exc:
            print(f"[screenshot_activity] Code sent but Lark final write failed: {exc}", flush=True)
        await message.reply(_SUCCESS_REPLY, mention_author=False)


async def setup(bot: commands.Bot) -> None:
    if not SCREENSHOT_ACTIVITY_CHANNEL_ID or not SCREENSHOT_CODES_SHEET_ID:
        print("[screenshot_activity] Disabled; channel or sheet is not configured", flush=True)
        return
    await bot.add_cog(ScreenshotActivityCog(bot))
