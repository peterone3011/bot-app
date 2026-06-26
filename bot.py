import discord
from discord.ext import commands
import asyncio
import os
import traceback

TOKEN = os.environ["TOKEN"]
PROXY = os.environ.get("PROXY")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True


async def main():
    while True:
        try:
            if PROXY:
                from aiohttp_socks import ProxyConnector
                connector = ProxyConnector.from_url(PROXY)
            else:
                connector = None

            bot = commands.Bot(command_prefix="!", intents=intents, connector=connector)

            @bot.command(name="reload")
            @commands.is_owner()
            async def reload_cog(ctx, cog: str):
                try:
                    await ctx.message.delete()
                except discord.Forbidden:
                    pass
                try:
                    await bot.reload_extension(f"cogs.{cog}")
                except Exception as e:
                    await ctx.author.send(f"❌ Reload failed: {e}")

            await bot.load_extension("cogs.roles")
            await bot.load_extension("cogs.embed")
            await bot.load_extension("cogs.bigwin")
            await bot.load_extension("cogs.jackpot")
            await bot.load_extension("cogs.updates")
            await bot.load_extension("cogs.autorole")

            @bot.tree.error
            async def on_app_command_error(interaction: discord.Interaction, error: Exception):
                import traceback
                print(f"[app_command_error] {error}\n{traceback.format_exc()}", flush=True)
                msg = "❌ 出错了，请稍后再试。"
                try:
                    if interaction.response.is_done():
                        await interaction.followup.send(msg)
                    else:
                        await interaction.response.send_message(msg, ephemeral=True)
                except Exception:
                    pass

            @bot.event
            async def on_ready():
                await bot.tree.sync()
                print(f"Logged in as {bot.user}")

            await bot.start(TOKEN)

        except Exception:
            print(traceback.format_exc())
            await asyncio.sleep(10)


asyncio.run(main())
