import discord
import asyncio
import os
import traceback

TOKEN = os.environ["TOKEN"]
PROXY = os.environ.get("PROXY")  # 本地开发时设置，服务器上留空
ROLES_CHANNEL_NAME = "🔔roles"

# ✅ 站点列表 — 后续把序号替换成真实站点名称
SITES = [
    "Fortune Purple",
] + [f"站点 {i}" for i in range(2, 51)]

intents = discord.Intents.default()
intents.members = True
intents.message_content = True


async def handle_role(interaction: discord.Interaction, selected: str):
    guild = interaction.guild
    member = await guild.fetch_member(interaction.user.id)

    role = discord.utils.get(guild.roles, name=selected)
    if not role:
        role = await guild.create_role(name=selected, reason="站点角色自动创建")

    for site in SITES:
        if site == selected:
            continue
        old_role = discord.utils.get(guild.roles, name=site)
        if old_role and old_role in member.roles:
            await member.remove_roles(old_role)

    if role in member.roles:
        await member.remove_roles(role)
        await interaction.followup.send(f"✅ 已移除角色：**{selected}**", ephemeral=True)
    else:
        await member.add_roles(role)
        await interaction.followup.send(f"✅ 已为你分配角色：**{selected}**，欢迎加入！", ephemeral=True)


class Page2Select(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=s, value=s) for s in SITES[25:]]
        super().__init__(
            placeholder="选择站点（26-50）...",
            min_values=1, max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await handle_role(interaction, self.values[0])


class Page2View(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.add_item(Page2Select())


class Page1Select(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=s, value=s) for s in SITES[:25]]
        super().__init__(
            placeholder="选择站点（1-25）...",
            min_values=1, max_values=1,
            options=options,
            custom_id="site_role_select_1",
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await handle_role(interaction, self.values[0])


class NextPageButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="下一页（26-50）▶",
            style=discord.ButtonStyle.secondary,
            custom_id="next_page_btn",
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=discord.Embed(
                title="选择你的站点（26-50）",
                description="从下方选择你所在的站点。",
                color=0x9B59B6,
            ),
            view=Page2View(),
            ephemeral=True,
        )


class RoleView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(Page1Select())
        self.add_item(NextPageButton())


async def main():
    while True:
        try:
            if PROXY:
                from aiohttp_socks import ProxyConnector
                connector = ProxyConnector.from_url(PROXY)
            else:
                connector = None

            client = discord.Client(intents=intents, connector=connector)

            @client.event
            async def on_ready():
                client.add_view(RoleView())
                for guild in client.guilds:
                    channel = discord.utils.get(guild.text_channels, name=ROLES_CHANNEL_NAME)
                    if not channel:
                        continue

                    already_posted = False
                    async for msg in channel.history(limit=50):
                        if msg.author == client.user and msg.embeds:
                            if msg.embeds[0].title == "选择你的站点":
                                already_posted = True
                                break

                    if not already_posted:
                        try:
                            embed = discord.Embed(
                                title="选择你的站点",
                                description="请从下方菜单选择你所在的站点，Bot 将自动为你分配对应角色。",
                                color=0x9B59B6,
                            )
                            await channel.send(embed=embed, view=RoleView())
                        except Exception:
                            pass

            await client.start(TOKEN)

        except Exception:
            print(traceback.format_exc())
            await asyncio.sleep(10)


asyncio.run(main())
