import discord
from discord.ext import commands

from cogs.community_metrics import record_metric_event
from cogs.db import aload_roles

EMBED_TITLE = "Select Your Notifications"
EMBED_DESCRIPTION = (
    "Subscribe to the channels you want to follow.\n"
    "Click once to **subscribe** — click again to **unsubscribe**."
)

CHANNEL_NAME = "🔔roles"


async def _build_options() -> list[discord.SelectOption]:
    roles = await aload_roles()
    return [
        discord.SelectOption(
            label=r["label"],
            value=r["label"],
            description=r.get("description", ""),
        )
        for r in roles
    ]


async def handle_role(interaction: discord.Interaction, selected: str) -> None:
    member = interaction.user
    guild = interaction.guild

    role = discord.utils.get(guild.roles, name=selected)
    if not role:
        await interaction.followup.send(
            content=f"⚠️ Role **{selected}** not found. Please contact an admin.",
            ephemeral=True,
        )
        return

    if role in member.roles:
        await member.remove_roles(role)
        await interaction.followup.send(
            content=f"✅ Unsubscribed from **{selected}**.", ephemeral=True
        )
    else:
        await member.add_roles(role)
        await record_metric_event("role_subscribe", member_id=member.id, role=role.name)
        await interaction.followup.send(
            content=f"✅ Subscribed to **{selected}**!", ephemeral=True
        )


class SubscriptionSelect(discord.ui.Select):
    def __init__(self, options: list[discord.SelectOption]) -> None:
        super().__init__(
            placeholder="Subscribe / unsubscribe to notifications...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="subscription_role_select",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        selected = self.values[0]
        options = [
            discord.SelectOption(
                label=option.label,
                value=option.value,
                description=option.description,
                emoji=option.emoji,
                default=False,
            )
            for option in self.options
        ]
        await interaction.response.edit_message(view=RoleView(options))
        await handle_role(interaction, selected)
        try:
            fresh = await _build_options()
            current_signature = [
                (option.label, option.value, option.description, str(option.emoji))
                for option in options
            ]
            fresh_signature = [
                (option.label, option.value, option.description, str(option.emoji))
                for option in fresh
            ]
            if fresh and fresh_signature != current_signature:
                await interaction.edit_original_response(view=RoleView(fresh))
        except Exception as exc:
            print(f"[roles] Failed to refresh view after interaction: {exc}", flush=True)


class RoleView(discord.ui.View):
    def __init__(self, options: list[discord.SelectOption]) -> None:
        super().__init__(timeout=None)
        self.add_item(SubscriptionSelect(options))


class RolesCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # Register persistent view handler for interactions on existing Discord messages.
        # A single placeholder option is enough to register the custom_id;
        # real options are loaded from DB in _post_role_embeds().
        bot.add_view(RoleView([discord.SelectOption(label="loading", value="loading")]))

    def cog_unload(self) -> None:
        pass

    async def _post_role_embeds(self) -> None:
        try:
            opts = await _build_options()
        except Exception as e:
            print(f"[roles] Failed to load roles from DB: {e}", flush=True)
            return
        if not opts:
            print("[roles] No roles found in DB, skipping embed update", flush=True)
            return

        for guild in self.bot.guilds:
            channel = discord.utils.get(guild.text_channels, name=CHANNEL_NAME)
            if not channel:
                continue
            existing: discord.Message | None = None
            async for msg in channel.history(limit=50):
                if msg.author == self.bot.user and msg.embeds:
                    existing = msg
                    break
            embed = discord.Embed(
                title=EMBED_TITLE,
                description=EMBED_DESCRIPTION,
                color=0x9B59B6,
            )
            try:
                if existing:
                    await existing.edit(embed=embed, view=RoleView(opts))
                else:
                    await channel.send(embed=embed, view=RoleView(opts))
            except Exception as e:
                print(f"[roles] Failed to post/update role embed: {e}", flush=True)

    async def cog_load(self) -> None:
        if self.bot.is_ready():
            await self._post_role_embeds()

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        await self._post_role_embeds()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RolesCog(bot))
