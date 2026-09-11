# Financial Support Keyword Redirect Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reply to financial-support questions in three Discord channels with a red Embed that directs players to the official live-support channel.

**Architecture:** Add an isolated Discord Cog with a typed environment configuration, pure text matcher, per-user/per-channel in-memory cooldown, and one message listener. Load it alongside existing Cogs without changing their behavior, and configure Railway before the production push.

**Tech Stack:** Python 3.13+, discord.py, pytest, pytest-asyncio, unittest.mock, Railway

## Global Constraints

- Listen only in channels `1546766591096787026`, `1546766625209065492`, and `1546766642820677652`.
- Direct players to Discord channel `1509148079566225480`.
- Cover deposit, withdrawal, cash-out, redemption, payment, refund, and missing-funds issues only.
- Exclude login, KYC, game, bonus, reward, and community-activity questions.
- Do not let `pending`, `missing`, or `failed` trigger without financial context.
- Reply without pinging the player and never create user, role, or everyone mentions.
- Apply a 600-second cooldown per guild, channel, and user after a successful reply.
- Keep all existing Bot workflows unchanged.

---

## File Structure

- Create `cogs/support_redirect.py`: configuration parsing, normalization, matching, Embed rendering, cooldown, listener, and extension setup.
- Create `tests/test_support_redirect.py`: pure matching, configuration, reply, filtering, cooldown, and failure tests.
- Modify `bot.py`: load the new extension once.
- Modify `.env.example`: document the four new environment variables.
- Modify `README.md`: list the new Cog, workflow, and operational variables.

### Task 1: Configuration And Financial-Issue Matcher

**Files:**
- Create: `cogs/support_redirect.py`
- Create: `tests/test_support_redirect.py`

**Interfaces:**
- Produces: `SupportRedirectConfig.from_env(environ: Mapping[str, str]) -> SupportRedirectConfig`
- Produces: `normalize_message(content: str) -> str`
- Produces: `is_financial_support_issue(content: str) -> bool`
- Consumes: no project modules; only Python standard library and `discord.py`

- [ ] **Step 1: Write failing matcher and configuration tests**

Create `tests/test_support_redirect.py` with these initial tests:

```python
from __future__ import annotations

import pytest

from cogs.support_redirect import (
    SupportRedirectConfig,
    is_financial_support_issue,
    normalize_message,
)


@pytest.mark.parametrize(
    "content",
    [
        "How do I withdraw?",
        "My WITHDRAWAL is still processing",
        "cash-out help please",
        "cashout",
        "I need to redeem SC",
        "redemption problem",
        "my deposit did not arrive",
        "Where is my refund?",
        "payment issue",
        "payment failed again",
        "my card was charged twice",
        "duplicate charge",
        "money missing from my balance",
        "funds not received",
    ],
)
def test_financial_messages_match(content: str) -> None:
    assert is_financial_support_issue(content) is True


@pytest.mark.parametrize(
    "content",
    [
        "pending",
        "missing",
        "failed",
        "bonus missing",
        "reward missing",
        "the game is not loading",
        "I cannot log in",
        "verification pending",
        "what is your favorite game?",
    ],
)
def test_non_financial_messages_do_not_match(content: str) -> None:
    assert is_financial_support_issue(content) is False


def test_normalization_handles_punctuation_and_spaces() -> None:
    assert normalize_message("  CASH--OUT!!!  pending ") == "cash out pending"


def test_config_parses_enabled_channel_list_and_cooldown() -> None:
    config = SupportRedirectConfig.from_env(
        {
            "SUPPORT_REDIRECT_ENABLED": "1",
            "SUPPORT_TRIGGER_CHANNEL_IDS": "1546766591096787026,1546766625209065492",
            "SUPPORT_CHANNEL_ID": "1509148079566225480",
            "SUPPORT_REDIRECT_COOLDOWN_SECONDS": "600",
        }
    )
    assert config.enabled is True
    assert config.trigger_channel_ids == frozenset(
        {1546766591096787026, 1546766625209065492}
    )
    assert config.support_channel_id == 1509148079566225480
    assert config.cooldown_seconds == 600


@pytest.mark.parametrize(
    "overrides",
    [
        {"SUPPORT_TRIGGER_CHANNEL_IDS": ""},
        {"SUPPORT_TRIGGER_CHANNEL_IDS": "not-a-channel"},
        {"SUPPORT_CHANNEL_ID": "0"},
        {"SUPPORT_REDIRECT_COOLDOWN_SECONDS": "-1"},
    ],
)
def test_enabled_config_rejects_invalid_values(overrides: dict[str, str]) -> None:
    environ = {
        "SUPPORT_REDIRECT_ENABLED": "1",
        "SUPPORT_TRIGGER_CHANNEL_IDS": "1546766591096787026",
        "SUPPORT_CHANNEL_ID": "1509148079566225480",
        "SUPPORT_REDIRECT_COOLDOWN_SECONDS": "600",
    }
    environ.update(overrides)
    with pytest.raises(ValueError):
        SupportRedirectConfig.from_env(environ)
```

- [ ] **Step 2: Run the new tests and verify the module is missing**

Run: `python -m pytest tests/test_support_redirect.py -v`

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'cogs.support_redirect'`.

- [ ] **Step 3: Implement the typed config, normalizer, and matcher**

Create `cogs/support_redirect.py` with these core definitions:

```python
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Callable, Mapping

import discord
from discord.ext import commands


_TRUE_VALUES = {"1", "true", "yes", "on"}
_DIRECT_PATTERNS = (
    re.compile(r"\bwithdraw(?:al|als|ing|n|s)?\b"),
    re.compile(r"\bcash\s*out\b"),
    re.compile(r"\bredeem(?:ed|ing)?\s+sc\b"),
    re.compile(r"\bredemption(?:s)?\b"),
    re.compile(r"\bdeposit(?:ed|ing|s)?\b"),
    re.compile(r"\brefund(?:ed|ing|s)?\b"),
)
_CONTEXT_PATTERNS = (
    re.compile(r"\bpayment\b.{0,40}\b(?:issue|problem|failed|declined|pending|missing|stuck|delayed|not received)\b"),
    re.compile(r"\b(?:issue|problem|failed|declined|pending|missing|stuck|delayed|not received)\b.{0,40}\bpayment\b"),
    re.compile(r"\b(?:money|funds)\b.{0,40}\b(?:missing|pending|stuck|delayed|not received)\b"),
    re.compile(r"\b(?:missing|pending|stuck|delayed|not received)\b.{0,40}\b(?:money|funds)\b"),
    re.compile(r"\bcharged\s+(?:twice|double|incorrectly|wrong)\b"),
    re.compile(r"\bduplicate\s+charge\b"),
    re.compile(r"\bwrong\s+amount\s+charged\b"),
)


@dataclass(frozen=True)
class SupportRedirectConfig:
    enabled: bool
    trigger_channel_ids: frozenset[int]
    support_channel_id: int
    cooldown_seconds: int = 600

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "SupportRedirectConfig":
        values = os.environ if environ is None else environ
        enabled = values.get("SUPPORT_REDIRECT_ENABLED", "0").strip().casefold() in _TRUE_VALUES
        if not enabled:
            return cls(False, frozenset(), 0, 600)
        try:
            channels = frozenset(
                int(value.strip())
                for value in values.get("SUPPORT_TRIGGER_CHANNEL_IDS", "").split(",")
                if value.strip()
            )
            support_channel_id = int(values.get("SUPPORT_CHANNEL_ID", "0"))
            cooldown_seconds = int(values.get("SUPPORT_REDIRECT_COOLDOWN_SECONDS", "600"))
        except ValueError as exc:
            raise ValueError("support redirect configuration contains a non-integer value") from exc
        if not channels or any(channel_id <= 0 for channel_id in channels):
            raise ValueError("SUPPORT_TRIGGER_CHANNEL_IDS must contain positive channel IDs")
        if support_channel_id <= 0:
            raise ValueError("SUPPORT_CHANNEL_ID must be a positive channel ID")
        if cooldown_seconds < 0:
            raise ValueError("SUPPORT_REDIRECT_COOLDOWN_SECONDS cannot be negative")
        return cls(True, channels, support_channel_id, cooldown_seconds)


def normalize_message(content: str) -> str:
    lowered = content.casefold()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", lowered)).strip()


def is_financial_support_issue(content: str) -> bool:
    normalized = normalize_message(content)
    if not normalized:
        return False
    return any(pattern.search(normalized) for pattern in _DIRECT_PATTERNS + _CONTEXT_PATTERNS)
```

- [ ] **Step 4: Run matcher and configuration tests**

Run: `python -m pytest tests/test_support_redirect.py -v`

Expected: all tests created in Step 1 PASS.

- [ ] **Step 5: Commit the matcher and configuration**

```bash
git add cogs/support_redirect.py tests/test_support_redirect.py
git commit -m "feat: add financial support message matcher"
```

### Task 2: Discord Embed Reply And Cooldown

**Files:**
- Modify: `cogs/support_redirect.py`
- Modify: `tests/test_support_redirect.py`

**Interfaces:**
- Consumes: `SupportRedirectConfig`, `is_financial_support_issue`
- Produces: `build_support_embed(support_channel_id: int) -> discord.Embed`
- Produces: `SupportRedirectCog(bot: commands.Bot, config: SupportRedirectConfig, clock: Callable[[], float] = time.monotonic)`
- Produces: `SupportRedirectCog.on_message(message: discord.Message) -> None`
- Produces: `setup(bot: commands.Bot) -> None`

- [ ] **Step 1: Add failing Embed and listener tests**

Append tests using lightweight Discord-shaped mocks:

```python
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord

from cogs.support_redirect import (
    SupportRedirectCog,
    build_support_embed,
)


def make_message(*, content: str = "withdrawal pending", channel_id: int = 101, user_id: int = 202, bot: bool = False):
    return SimpleNamespace(
        id=303,
        content=content,
        guild=SimpleNamespace(id=404),
        channel=SimpleNamespace(id=channel_id),
        author=SimpleNamespace(id=user_id, bot=bot),
        reply=AsyncMock(),
    )


def enabled_config() -> SupportRedirectConfig:
    return SupportRedirectConfig(True, frozenset({101, 102, 103}), 505, 600)


def test_support_embed_contains_approved_copy() -> None:
    embed = build_support_embed(505)
    assert embed.title == "⚠️ Discord cannot handle order-related issues"
    assert embed.color.value == 0xED4245
    assert "deposit, withdrawal, or refund issues" in embed.description
    assert "<#505>" in embed.description
    assert "queue" not in embed.description.casefold()
    assert "reward" not in embed.description.casefold()


@pytest.mark.asyncio
async def test_listener_replies_without_mentions() -> None:
    message = make_message()
    cog = SupportRedirectCog(SimpleNamespace(), enabled_config(), clock=lambda: 1000.0)
    await cog.on_message(message)
    message.reply.assert_awaited_once()
    kwargs = message.reply.await_args.kwargs
    assert kwargs["mention_author"] is False
    assert kwargs["embed"].title == "⚠️ Discord cannot handle order-related issues"
    assert kwargs["allowed_mentions"].everyone is False
    assert kwargs["allowed_mentions"].roles is False
    assert kwargs["allowed_mentions"].users is False


@pytest.mark.asyncio
async def test_listener_ignores_bots_unlisted_channels_and_nonmatches() -> None:
    cog = SupportRedirectCog(SimpleNamespace(), enabled_config(), clock=lambda: 1000.0)
    messages = [
        make_message(bot=True),
        make_message(channel_id=999),
        make_message(content="reward missing"),
    ]
    for message in messages:
        await cog.on_message(message)
        message.reply.assert_not_awaited()


@pytest.mark.asyncio
async def test_cooldown_is_per_user_and_channel() -> None:
    now = [1000.0]
    cog = SupportRedirectCog(SimpleNamespace(), enabled_config(), clock=lambda: now[0])
    first = make_message()
    repeated = make_message()
    other_user = make_message(user_id=203)
    other_channel = make_message(channel_id=102)
    await cog.on_message(first)
    await cog.on_message(repeated)
    await cog.on_message(other_user)
    await cog.on_message(other_channel)
    first.reply.assert_awaited_once()
    repeated.reply.assert_not_awaited()
    other_user.reply.assert_awaited_once()
    other_channel.reply.assert_awaited_once()
    now[0] += 601
    await cog.on_message(repeated)
    repeated.reply.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_reply_does_not_start_cooldown() -> None:
    message = make_message()
    message.reply.side_effect = [RuntimeError("network"), None]
    cog = SupportRedirectCog(SimpleNamespace(), enabled_config(), clock=lambda: 1000.0)
    await cog.on_message(message)
    await cog.on_message(message)
    assert message.reply.await_count == 2
```

- [ ] **Step 2: Run listener tests and verify missing interfaces fail**

Run: `python -m pytest tests/test_support_redirect.py -v`

Expected: FAIL importing `SupportRedirectCog` and `build_support_embed`.

- [ ] **Step 3: Implement Embed, listener, cooldown, and safe setup**

Append these definitions to `cogs/support_redirect.py`:

```python
_TITLE = "⚠️ Discord cannot handle order-related issues"


def build_support_embed(support_channel_id: int) -> discord.Embed:
    description = (
        "For any deposit, withdrawal, or refund issues, please contact our live "
        f"support in <#{support_channel_id}>.\n\n"
        "Please fill out the form to start a chat with our support team and "
        "describe your issue clearly."
    )
    return discord.Embed(title=_TITLE, description=description, color=0xED4245)


class SupportRedirectCog(commands.Cog):
    def __init__(
        self,
        bot: commands.Bot,
        config: SupportRedirectConfig,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.bot = bot
        self.config = config
        self._clock = clock
        self._cooldowns: dict[tuple[int, int, int], float] = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return
        if message.channel.id not in self.config.trigger_channel_ids:
            return
        if not is_financial_support_issue(message.content):
            return
        now = self._clock()
        key = (message.guild.id, message.channel.id, message.author.id)
        last_reply = self._cooldowns.get(key)
        if last_reply is not None and now - last_reply < self.config.cooldown_seconds:
            return
        self._cooldowns = {
            existing_key: timestamp
            for existing_key, timestamp in self._cooldowns.items()
            if now - timestamp < self.config.cooldown_seconds
        }
        try:
            await message.reply(
                embed=build_support_embed(self.config.support_channel_id),
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except Exception as exc:
            print(
                "[support_redirect] Reply failed "
                f"guild={message.guild.id} channel={message.channel.id} "
                f"message={message.id} user={message.author.id}: {exc}",
                flush=True,
            )
            return
        self._cooldowns[key] = now


async def setup(bot: commands.Bot) -> None:
    try:
        config = SupportRedirectConfig.from_env()
    except ValueError as exc:
        print(f"[support_redirect] Disabled: {exc}", flush=True)
        return
    if not config.enabled:
        print("[support_redirect] Disabled by configuration", flush=True)
        return
    await bot.add_cog(SupportRedirectCog(bot, config))
    channels = ",".join(str(value) for value in sorted(config.trigger_channel_ids))
    print(
        f"[support_redirect] Enabled channels={channels} "
        f"support_channel={config.support_channel_id} "
        f"cooldown={config.cooldown_seconds}s",
        flush=True,
    )
```

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest tests/test_support_redirect.py -v`

Expected: all support redirect tests PASS.

- [ ] **Step 5: Commit Discord behavior**

```bash
git add cogs/support_redirect.py tests/test_support_redirect.py
git commit -m "feat: reply with financial support redirect"
```

### Task 3: Bot Integration, Documentation, And Production Rollout

**Files:**
- Modify: `bot.py`
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `tests/test_support_redirect.py`

**Interfaces:**
- Consumes: extension entry point `cogs.support_redirect.setup(bot)`
- Produces: Bot startup load for `cogs.support_redirect`
- Produces: documented Railway variables and production runbook

- [ ] **Step 1: Add a failing static integration test**

Append:

```python
from pathlib import Path


def test_bot_loads_support_redirect_extension() -> None:
    bot_source = Path("bot.py").read_text(encoding="utf-8")
    assert 'await bot.load_extension("cogs.support_redirect")' in bot_source
```

- [ ] **Step 2: Run the integration test and verify it fails**

Run: `python -m pytest tests/test_support_redirect.py::test_bot_loads_support_redirect_extension -v`

Expected: FAIL because `bot.py` does not yet load the extension.

- [ ] **Step 3: Load the extension in `bot.py`**

Add one line after `cogs.community_metrics` is loaded:

```python
await bot.load_extension("cogs.support_redirect")
```

- [ ] **Step 4: Document environment variables**

Append to `.env.example`:

```dotenv
# Financial support keyword redirect
SUPPORT_REDIRECT_ENABLED=0
SUPPORT_TRIGGER_CHANNEL_IDS=1546766591096787026,1546766625209065492,1546766642820677652
SUPPORT_CHANNEL_ID=1509148079566225480
SUPPORT_REDIRECT_COOLDOWN_SECONDS=600
```

Add `cogs/support_redirect.py` to the README architecture list. Add a workflow note stating that it replies only to financial-support phrases in configured channels, and add the four variable names to the Bot environment-variable table.

- [ ] **Step 5: Run focused and full verification**

Run:

```bash
python -m pytest tests/test_support_redirect.py -v
python -m pytest
python -m py_compile cogs/support_redirect.py bot.py
git diff --check
```

Expected: all focused tests PASS, the full suite has no failures, compilation exits `0`, and `git diff --check` prints nothing.

- [ ] **Step 6: Review the final diff for isolation**

Run:

```bash
git status --short
git diff --stat HEAD
git diff HEAD -- bot.py cogs/support_redirect.py tests/test_support_redirect.py .env.example README.md
```

Confirm that no existing Cog implementation changed and that the only `bot.py` behavior change is one extension load line.

- [ ] **Step 7: Commit integration and documentation**

```bash
git add bot.py .env.example README.md tests/test_support_redirect.py
git commit -m "feat: enable financial support redirect cog"
```

- [ ] **Step 8: Configure Railway without deploying**

Set all values with `--skip-deploys` before pushing:

```bash
railway variable set SUPPORT_REDIRECT_ENABLED=1 --skip-deploys --project ed6d7768-d97e-465a-b2bc-222f4066c81a --service bot-app --environment production
railway variable set SUPPORT_TRIGGER_CHANNEL_IDS=1546766591096787026,1546766625209065492,1546766642820677652 --skip-deploys --project ed6d7768-d97e-465a-b2bc-222f4066c81a --service bot-app --environment production
railway variable set SUPPORT_CHANNEL_ID=1509148079566225480 --skip-deploys --project ed6d7768-d97e-465a-b2bc-222f4066c81a --service bot-app --environment production
railway variable set SUPPORT_REDIRECT_COOLDOWN_SECONDS=600 --skip-deploys --project ed6d7768-d97e-465a-b2bc-222f4066c81a --service bot-app --environment production
```

List variable names without printing raw values and verify all four names exist.

- [ ] **Step 9: Push the tested branch to production**

Run: `git push origin HEAD:main`

Expected: remote `main` advances to the final feature commit and Railway starts one deployment.

- [ ] **Step 10: Verify production**

Check Railway deployment status and logs. Required evidence:

- deployment status is `SUCCESS`
- deployed commit matches local `HEAD`
- log contains `[support_redirect] Enabled channels=1546766591096787026,1546766625209065492,1546766642820677652 support_channel=1509148079566225480 cooldown=600s`
- log contains `Logged in as FortunePurple#0802`
- no new `error`-level logs appear after startup

Do not post a synthetic trigger into a public Discord channel. Ask the user to send a real financial phrase in one monitored channel when they are ready to validate the visible Embed.

