import asyncio
import discord
from discord.ext import commands

AUTO_ROLE_ID: int = 1519235045049634959
AUTO_ROLE_CAP: int = 3000


class AutoRoleCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._backfill_started = False
        self._task: asyncio.Task | None = None
        # Shared counter instead of len(role.members) — avoids stale cache race.
        # asyncio is single-threaded: increment before every await so the check
        # and reserve are atomic relative to other coroutines.
        self._role_count: int = 0

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if self._backfill_started:
            return
        self._backfill_started = True
        self._task = asyncio.create_task(self._backfill())
        self._task.add_done_callback(self._on_backfill_done)

    def _on_backfill_done(self, task: asyncio.Task) -> None:
        if not task.cancelled() and task.exception():
            print(f"[autorole] Backfill task failed: {task.exception()}", flush=True)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.bot:
            return
        role = member.guild.get_role(AUTO_ROLE_ID)
        if role is None:
            return
        if self._role_count >= AUTO_ROLE_CAP:
            return
        self._role_count += 1  # reserve slot before yielding
        try:
            await member.add_roles(role, reason="auto-role")
        except Exception as exc:
            self._role_count -= 1  # release slot on failure
            print(f"[autorole] on_member_join failed for {member}: {exc}", flush=True)

    async def _backfill(self) -> None:
        for guild in self.bot.guilds:
            role = guild.get_role(AUTO_ROLE_ID)
            if role is None:
                print(f"[autorole] Role {AUTO_ROLE_ID} not found in {guild.name}", flush=True)
                continue

            self._role_count = len(role.members)
            if self._role_count >= AUTO_ROLE_CAP:
                print(
                    f"[autorole] Cap already met ({self._role_count}/{AUTO_ROLE_CAP}), "
                    "skipping backfill",
                    flush=True,
                )
                continue

            assigned = 0
            for member in guild.members:
                if self._role_count >= AUTO_ROLE_CAP:
                    print(f"[autorole] Cap {AUTO_ROLE_CAP} reached, backfill stopped", flush=True)
                    break
                if member.bot or role in member.roles:
                    continue
                self._role_count += 1  # reserve slot before yielding
                try:
                    await member.add_roles(role, reason="auto-role backfill")
                    assigned += 1
                    await asyncio.sleep(0.5)
                except Exception as exc:
                    self._role_count -= 1  # release slot on failure
                    print(f"[autorole] Backfill failed for {member}: {exc}", flush=True)

            print(
                f"[autorole] Backfill done: assigned={assigned}, "
                f"total={self._role_count}/{AUTO_ROLE_CAP}",
                flush=True,
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AutoRoleCog(bot))
