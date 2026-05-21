import discord
from discord.ext import commands

from cogs.db import get_config, load_sites

EMBED_TITLE = "Select Your Site"


async def handle_role(interaction: discord.Interaction, selected: str) -> None:
    member = interaction.user
    guild = interaction.guild
    sites = load_sites()

    role = discord.utils.get(guild.roles, name=selected)
    if not role:
        await interaction.followup.send(content="⚠️ No role found for this site.", ephemeral=True)
        return

    roles_to_remove = []
    for site in sites:
        if site == selected:
            continue
        r = discord.utils.get(guild.roles, name=site)
        if r and r in member.roles:
            roles_to_remove.append(r)

    if roles_to_remove:
        await member.remove_roles(*roles_to_remove)

    if role in member.roles:
        await member.remove_roles(role)
        await interaction.followup.send(content=f"✅ Role removed: **{selected}**", ephemeral=True)
    else:
        await member.add_roles(role)
        await interaction.followup.send(
            content=f"✅ Role assigned: **{selected}**. Welcome!", ephemeral=True
        )


class SiteSelect(discord.ui.Select):
    def __init__(self, sites: list[str], placeholder: str, custom_id: str):
        options = [discord.SelectOption(label=s, value=s) for s in sites]
        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            options=options,
            custom_id=custom_id,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        await handle_role(interaction, self.values[0])


class RoleView(discord.ui.View):
    def __init__(self, sites: list[str]):
        super().__init__(timeout=None)
        self.add_item(SiteSelect(sites[:25], "Select site (1-25)...", "site_role_select_1"))
        self.add_item(SiteSelect(sites[25:], "Select site (26-50)...", "site_role_select_2"))


class RolesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bot.add_view(RoleView(load_sites()))

    async def _post_role_embeds(self) -> None:
        channel_name = get_config("roles_channel_name", "🔔roles")
        sites = load_sites()
        for guild in self.bot.guilds:
            channel = discord.utils.get(guild.text_channels, name=channel_name)
            if not channel:
                continue
            already_posted = False
            async for msg in channel.history(limit=50):
                if msg.author == self.bot.user and msg.embeds:
                    if msg.embeds[0].title in (EMBED_TITLE, "选择你的站点"):
                        already_posted = True
                        break
            if not already_posted:
                try:
                    embed = discord.Embed(
                        title=EMBED_TITLE,
                        description="Please select your site from the menu below. The bot will automatically assign you the corresponding role.",
                        color=0x9B59B6,
                    )
                    await channel.send(embed=embed, view=RoleView(sites))
                except Exception as e:
                    print(f"Failed to post role embed: {e}")

    async def cog_load(self) -> None:
        if self.bot.is_ready():
            await self._post_role_embeds()

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        await self._post_role_embeds()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RolesCog(bot))
