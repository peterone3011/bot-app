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
                    await bot.reload_extension(f"cogs.{cog}")
                    await ctx.send(f"✅ 已重载：{cog}")
                except Exception as e:
                    await ctx.send(f"❌ 重载失败：{e}")

            await bot.load_extension("cogs.roles")
            await bot.start(TOKEN)

        except Exception:
            print(traceback.format_exc())
            await asyncio.sleep(10)


asyncio.run(main())
