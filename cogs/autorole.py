import asyncio
import discord
from discord.ext import commands

AUTO_ROLE_ID: int = 1519235045049634959
AUTO_ROLE_CAP: int = 3000


class AutoRoleCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._backfill_started = False

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if self._backfill_started:
            return
        self._backfill_started = True
        asyncio.create_task(self._backfill())

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.bot:
            return
        role = member.guild.get_role(AUTO_ROLE_ID)
        if role is None:
            return
        if len(role.members) >= AUTO_ROLE_CAP:
            return
        try:
            await member.add_roles(role, reason="auto-role")
        except Exception as exc:
            print(f"[autorole] on_member_join failed for {member}: {exc}", flush=True)

    async def _backfill(self) -> None:
        for guild in self.bot.guilds:
            role = guild.get_role(AUTO_ROLE_ID)
            if role is None:
                print(f"[autorole] Role {AUTO_ROLE_ID} not found in {guild.name}", flush=True)
                continue

            assigned = 0
            for member in guild.members:
                if len(role.members) >= AUTO_ROLE_CAP:
                    print(f"[autorole] Cap {AUTO_ROLE_CAP} reached, backfill stopped", flush=True)
                    break
                if member.bot or role in member.roles:
                    continue
                try:
                    await member.add_roles(role, reason="auto-role backfill")
                    assigned += 1
                    await asyncio.sleep(0.5)  # ~2 assignments/sec, stays within rate limit
                except Exception as exc:
                    print(f"[autorole] Backfill failed for {member}: {exc}", flush=True)

            print(
                f"[autorole] Backfill done: assigned={assigned}, "
                f"total with role={len(role.members)}/{AUTO_ROLE_CAP}",
                flush=True,
            )
