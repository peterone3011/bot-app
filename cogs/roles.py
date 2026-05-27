import discord
from discord.ext import commands

from cogs.db import get_config

EMBED_TITLE = "Select Your Notifications"
EMBED_DESCRIPTION = (
    "Subscribe to the channels you want to follow.\n"
    "Click once to **subscribe** — click again to **unsubscribe**."
)

SUBSCRIPTION_ROLES = [
    discord.SelectOption(
        label="📢 Exclusive Updates",
        value="📢 Exclusive Updates",
        description="Access our exclusive updates channel",
    ),
    discord.SelectOption(
        label="🎰Gaming Alerts",
        value="🎰Gaming Alerts",
        description="Get notified for jackpots and big wins",
    ),
]


async def handle_role(interaction: discord.Interaction, selected: str) -> None:
    member = interaction.user
    guild  = interaction.guild

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
        await interaction.followup.send(
            content=f"✅ Subscribed to **{selected}**!", ephemeral=True
        )


class SubscriptionSelect(discord.ui.Select):
    def __init__(self) -> None:
        super().__init__(
            placeholder="Subscribe / unsubscribe to notifications...",
            min_values=1,
            max_values=1,
            options=SUBSCRIPTION_ROLES,
            custom_id="subscription_role_select",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        await handle_role(interaction, self.values[0])
        # Reset the select so the same option can be clicked again next time
        await interaction.message.edit(view=RoleView())


class RoleView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.add_item(SubscriptionSelect())


class RolesCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        bot.add_view(RoleView())

    async def _post_role_embeds(self) -> None:
        channel_name = get_config("roles_channel_name", "🔔roles")
        for guild in self.bot.guilds:
            channel = discord.utils.get(guild.text_channels, name=channel_name)
            if not channel:
                continue
            # Find any existing bot embed and update it; post fresh if none found
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
                    await existing.edit(embed=embed, view=RoleView())
                else:
                    await channel.send(embed=embed, view=RoleView())
            except Exception as e:
                print(f"[roles] Failed to post/update role embed: {e}")

    async def cog_load(self) -> None:
        if self.bot.is_ready():
            await self._post_role_embeds()

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        await self._post_role_embeds()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RolesCog(bot))
