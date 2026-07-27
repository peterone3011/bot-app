from __future__ import annotations

import asyncio
from typing import Any

import discord
from discord.ext import commands

from cogs.db import (
    ACTIVITY_DB_MAX_WORKERS,
    aclaim_activity_reward,
    aget_activity_by_message,
)


ACTIVITY_LOAD_TIMEOUT = 2.0
TEMPORARY_ERROR_MESSAGE = (
    "Sorry, the activity service is temporarily unavailable. Please try again later."
)
PARTICIPANT_KEY_TAKEN_MESSAGE = (
    "That FortunePurple ID has already been used for this activity. "
    "Please check it and try again."
)
UNAVAILABLE_MESSAGE = "This activity is no longer available."


class ActivityModal(discord.ui.Modal):
    def __init__(self, activity: dict[str, Any], *, discord_username: str) -> None:
        questions = activity.get("questions") or []
        if not 1 <= len(questions) <= 5:
            raise ValueError("An activity Modal must contain 1 to 5 questions")

        super().__init__(
            title=activity.get("modal_title") or "Activity Entry",
            custom_id=f"activity_modal:{activity['id']}",
            timeout=300,
        )
        self.activity = activity
        self.inputs: dict[str, discord.ui.TextInput] = {}

        for question in questions:
            field_key = str(question["field_key"])
            max_length = int(question.get("max_length") or 100)
            default = (
                discord_username[:max_length]
                if question.get("prefill_discord_username")
                else None
            )
            item = discord.ui.TextInput(
                label=str(question["label"]),
                style=(
                    discord.TextStyle.paragraph
                    if question.get("input_style") == "paragraph"
                    else discord.TextStyle.short
                ),
                custom_id=field_key,
                placeholder=question.get("placeholder") or None,
                default=default,
                required=bool(question.get("required", True)),
                min_length=int(question.get("min_length") or 0) or None,
                max_length=max_length,
            )
            self.inputs[field_key] = item
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)

        answers = {
            field_key: input_item.value.strip()
            for field_key, input_item in self.inputs.items()
        }
        participant_key = next(
            (
                answers[str(question["field_key"])]
                for question in self.activity["questions"]
                if question.get("is_participant_key")
            ),
            None,
        )
        if participant_key is not None:
            participant_key = "".join(participant_key.split()).casefold()

        try:
            result = await aclaim_activity_reward(
                campaign_id=str(self.activity["id"]),
                discord_user_id=str(interaction.user.id),
                discord_username=interaction.user.name,
                answers=answers,
                participant_key=participant_key,
            )
        except Exception as exc:
            print(f"[activities] Claim failed: {exc}", flush=True)
            await interaction.edit_original_response(
                content=TEMPORARY_ERROR_MESSAGE
            )
            return

        outcome = result.get("outcome")
        if outcome in {"winner", "existing_winner"}:
            code = discord.utils.escape_markdown(str(result.get("reward_code") or ""))
            message = self.activity["winner_message"].replace("{code}", code)
        elif outcome in {"sold_out", "existing_sold_out"}:
            message = self.activity["sold_out_message"]
        elif outcome == "participant_key_taken":
            message = PARTICIPANT_KEY_TAKEN_MESSAGE
        elif outcome == "closed":
            message = self.activity["closed_message"]
        else:
            print(f"[activities] Unexpected claim outcome: {outcome}", flush=True)
            message = TEMPORARY_ERROR_MESSAGE

        await interaction.edit_original_response(content=message)

    async def on_error(
        self, interaction: discord.Interaction, error: Exception
    ) -> None:
        print(f"[activities] Modal error: {error}", flush=True)
        try:
            if interaction.response.is_done():
                await interaction.edit_original_response(
                    content=TEMPORARY_ERROR_MESSAGE
                )
            else:
                await interaction.response.send_message(
                    TEMPORARY_ERROR_MESSAGE, ephemeral=True
                )
        except Exception:
            pass


class ActivityJoinButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(
            label="Join Activity",
            style=discord.ButtonStyle.primary,
            custom_id="activity_join",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        try:
            activity = await asyncio.wait_for(
                aget_activity_by_message(str(interaction.message.id)),
                timeout=ACTIVITY_LOAD_TIMEOUT,
            )
        except Exception as exc:
            print(f"[activities] Failed to load activity: {exc}", flush=True)
            await interaction.response.send_message(
                TEMPORARY_ERROR_MESSAGE, ephemeral=True
            )
            return

        if activity is None:
            await interaction.response.send_message(
                UNAVAILABLE_MESSAGE, ephemeral=True
            )
            return
        if activity.get("status") != "active":
            await interaction.response.send_message(
                activity["closed_message"], ephemeral=True
            )
            return

        try:
            modal = ActivityModal(
                activity,
                discord_username=interaction.user.name,
            )
        except (KeyError, TypeError, ValueError) as exc:
            print(f"[activities] Invalid activity configuration: {exc}", flush=True)
            await interaction.response.send_message(
                TEMPORARY_ERROR_MESSAGE, ephemeral=True
            )
            return
        await interaction.response.send_modal(modal)


class ActivityView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.add_item(ActivityJoinButton())


class ActivitiesCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        bot.add_view(ActivityView())


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ActivitiesCog(bot))
