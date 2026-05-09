import discord
from discord.ext import commands

ROLES_CHANNEL_NAME = "🔔roles"

SITES = [
    "Fortune Purple",
] + [f"Site {i}" for i in range(2, 51)]


async def handle_role(interaction: discord.Interaction, selected: str):
    guild = interaction.guild
    member = await guild.fetch_member(interaction.user.id)

    role = discord.utils.get(guild.roles, name=selected)
    if not role:
        await interaction.followup.send(content="⚠️ No role found for this site.", ephemeral=True)
        return

    for site in SITES:
        if site == selected:
            continue
        old_role = discord.utils.get(guild.roles, name=site)
        if old_role and old_role in member.roles:
            await member.remove_roles(old_role)

    if role in member.roles:
        await member.remove_roles(role)
        await interaction.followup.send(content=f"✅ Role removed: **{selected}**", ephemeral=True)
    else:
        await member.add_roles(role)
        await interaction.followup.send(content=f"✅ Role assigned: **{selected}**. Welcome!", ephemeral=True)


class Site1Select(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=s, value=s) for s in SITES[:25]]
        super().__init__(
            placeholder="Select site (1-25)...",
            min_values=1, max_values=1,
            options=options,
            custom_id="site_role_select_1",
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await handle_role(interaction, self.values[0])


class Site2Select(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=s, value=s) for s in SITES[25:]]
        super().__init__(
            placeholder="Select site (26-50)...",
            min_values=1, max_values=1,
            options=options,
            custom_id="site_role_select_2",
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await handle_role(interaction, self.values[0])


class RoleView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(Site1Select())
        self.add_item(Site2Select())


class RolesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bot.add_view(RoleView())

    async def _post_role_embeds(self):
        for guild in self.bot.guilds:
            channel = discord.utils.get(guild.text_channels, name=ROLES_CHANNEL_NAME)
            if not channel:
                continue

            already_posted = False
            async for msg in channel.history(limit=50):
                if msg.author == self.bot.user and msg.embeds:
                    if msg.embeds[0].title in ("Select Your Site", "选择你的站点"):
                        already_posted = True
                        break

            if not already_posted:
                try:
                    embed = discord.Embed(
                        title="Select Your Site",
                        description="Please select your site from the menu below. The bot will automatically assign you the corresponding role.",
                        color=0x9B59B6,
                    )
                    await channel.send(embed=embed, view=RoleView())
                except Exception:
                    pass

    async def cog_load(self):
        if self.bot.is_ready():
            await self._post_role_embeds()

    @commands.Cog.listener()
    async def on_ready(self):
        await self._post_role_embeds()


async def setup(bot: commands.Bot):
    await bot.add_cog(RolesCog(bot))
