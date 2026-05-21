# Supabase + Bot Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate bot data storage from local file (messages.json on Railway Volume) to Supabase PostgreSQL, and replace hardcoded config in roles.py with database-driven values.

**Architecture:** A new `cogs/db.py` module owns all Supabase I/O. Both `embed.py` and `roles.py` import from it, replacing their current file/hardcoded logic. The Supabase sync client is used (not async) so it can be called from synchronous contexts. Slash commands remain fully functional — they just read from Supabase instead of a file.

**Tech Stack:** Python `supabase` SDK (sync client), Supabase PostgreSQL, Railway (bot host unchanged)

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `cogs/db.py` | Supabase client singleton + all CRUD functions |
| Create | `tests/test_db.py` | Unit tests for db.py (mocked Supabase client) |
| Modify | `tests/test_embed_builder.py` | Fix import, replace file-based tests with mocked versions |
| Modify | `cogs/embed.py` | Remove file I/O, import CRUD from db.py |
| Modify | `cogs/roles.py` | Remove hardcoded SITES + channel name, read from db.py |
| Modify | `requirements.txt` | Add `supabase>=2.0.0` |
| Create | `scripts/migrate_messages.py` | One-time script: import messages.json → Supabase |
| Create | `.env.example` | Document all required env vars |

---

## Task 1: Supabase Project Setup (Manual — User Action Required)

**Files:** None (done in Supabase web dashboard)

- [ ] **Step 1: Create Supabase project**

  Go to https://supabase.com → New project → choose a region close to your server → note down the project URL and service role key (Settings → API).

- [ ] **Step 2: Run schema SQL in Supabase SQL Editor**

  Go to SQL Editor in your Supabase dashboard and run:

  ```sql
  -- Messages table (mirrors existing messages.json fields exactly)
  create table messages (
    id uuid primary key,
    status text not null default 'draft',
    label text,
    created_at timestamptz not null default now(),
    channel_id bigint not null,
    send_at timestamptz,
    message_id bigint,
    title text,
    description text,
    footer text,
    image_url text,
    button_label text,
    button_url text,
    color integer
  );

  -- Sites table (replaces hardcoded SITES list in roles.py)
  create table sites (
    id uuid primary key default gen_random_uuid(),
    name text not null unique,
    display_order integer not null default 0,
    created_at timestamptz not null default now()
  );

  -- Config table (replaces hardcoded constants)
  create table config (
    key text primary key,
    value text not null
  );

  -- Enable RLS: service key bypasses it, anon key gets no access
  alter table messages enable row level security;
  alter table sites enable row level security;
  alter table config enable row level security;

  -- Seed sites (Fortune Purple + Site 2-50)
  insert into sites (name, display_order) values ('Fortune Purple', 1);
  insert into sites (name, display_order)
  select 'Site ' || n, n
  from generate_series(2, 50) as n;

  -- Seed config
  insert into config (key, value) values ('roles_channel_name', '🔔roles');
  ```

- [ ] **Step 3: Verify tables exist**

  In Supabase → Table Editor, confirm `messages`, `sites`, `config` are present. `sites` should have 50 rows. `config` should have 1 row.

---

## Task 2: Add Dependency and Env Vars

**Files:**
- Modify: `requirements.txt`
- Create: `.env.example`

- [ ] **Step 1: Update requirements.txt**

  ```txt
  discord.py>=2.0.0
  aiohttp-socks
  supabase>=2.0.0
  ```

- [ ] **Step 2: Create .env.example**

  ```
  # Discord Bot
  TOKEN=your_discord_bot_token
  PROXY=socks5://127.0.0.1:10808

  # Supabase (get from Supabase dashboard → Settings → API)
  SUPABASE_URL=https://your-project-ref.supabase.co
  SUPABASE_SERVICE_KEY=your-service-role-key
  ```

- [ ] **Step 3: Commit**

  ```bash
  git add requirements.txt .env.example
  git commit -m "chore: add supabase dependency and env example"
  ```

---

## Task 3: Create cogs/db.py (TDD)

**Files:**
- Create: `tests/test_db.py`
- Create: `cogs/db.py`

- [ ] **Step 1: Write failing tests — create tests/test_db.py**

  ```python
  from unittest.mock import MagicMock
  import pytest
  import cogs.db as db_module


  def make_response(data):
      m = MagicMock()
      m.data = data
      return m


  @pytest.fixture
  def client(monkeypatch):
      # Reset singleton, then inject mock
      monkeypatch.setattr(db_module, "_client", None)
      mock = MagicMock()
      monkeypatch.setattr(db_module, "_client", mock)
      return mock


  # --- load_messages ---

  def test_load_messages_empty(client):
      client.table.return_value.select.return_value.execute.return_value = make_response([])
      assert db_module.load_messages() == []


  def test_load_messages_returns_rows(client):
      rows = [{"id": "a", "title": "Hello", "status": "draft"}]
      client.table.return_value.select.return_value.execute.return_value = make_response(rows)
      assert db_module.load_messages() == rows


  # --- get_message ---

  def test_get_message_found(client):
      row = {"id": "abc", "title": "Test"}
      client.table.return_value.select.return_value.eq.return_value.execute.return_value = make_response([row])
      assert db_module.get_message("abc") == row


  def test_get_message_not_found(client):
      client.table.return_value.select.return_value.eq.return_value.execute.return_value = make_response([])
      assert db_module.get_message("missing") is None


  # --- upsert_message ---

  def test_upsert_message_calls_upsert(client):
      msg = {"id": "abc", "title": "T", "status": "draft"}
      db_module.upsert_message(msg)
      client.table.assert_called_with("messages")
      client.table.return_value.upsert.assert_called_with(msg)


  # --- delete_message ---

  def test_delete_message_calls_delete(client):
      db_module.delete_message("abc")
      client.table.return_value.delete.return_value.eq.assert_called_with("id", "abc")


  # --- load_sites ---

  def test_load_sites_returns_names(client):
      rows = [{"name": "Fortune Purple"}, {"name": "Site 2"}]
      client.table.return_value.select.return_value.order.return_value.execute.return_value = make_response(rows)
      assert db_module.load_sites() == ["Fortune Purple", "Site 2"]


  def test_load_sites_empty(client):
      client.table.return_value.select.return_value.order.return_value.execute.return_value = make_response([])
      assert db_module.load_sites() == []


  # --- get_config ---

  def test_get_config_found(client):
      client.table.return_value.select.return_value.eq.return_value.execute.return_value = make_response(
          [{"value": "🔔roles"}]
      )
      assert db_module.get_config("roles_channel_name") == "🔔roles"


  def test_get_config_missing_returns_default(client):
      client.table.return_value.select.return_value.eq.return_value.execute.return_value = make_response([])
      assert db_module.get_config("nonexistent", "fallback") == "fallback"
  ```

- [ ] **Step 2: Run tests — expect ImportError**

  ```bash
  pytest tests/test_db.py -v
  ```

  Expected: `ImportError: No module named 'cogs.db'`

- [ ] **Step 3: Create cogs/db.py**

  ```python
  from __future__ import annotations

  import os
  from typing import Any

  from supabase import Client, create_client

  _client: Client | None = None


  def get_client() -> Client:
      global _client
      if _client is None:
          _client = create_client(
              os.environ["SUPABASE_URL"],
              os.environ["SUPABASE_SERVICE_KEY"],
          )
      return _client


  # ---------------------------------------------------------------------------
  # Messages
  # ---------------------------------------------------------------------------

  def load_messages() -> list[dict[str, Any]]:
      return get_client().table("messages").select("*").execute().data


  def get_message(msg_id: str) -> dict[str, Any] | None:
      rows = get_client().table("messages").select("*").eq("id", msg_id).execute().data
      return rows[0] if rows else None


  def upsert_message(msg: dict[str, Any]) -> None:
      get_client().table("messages").upsert(msg).execute()


  def delete_message(msg_id: str) -> None:
      get_client().table("messages").delete().eq("id", msg_id).execute()


  # ---------------------------------------------------------------------------
  # Sites
  # ---------------------------------------------------------------------------

  def load_sites() -> list[str]:
      rows = get_client().table("sites").select("name").order("display_order").execute().data
      return [row["name"] for row in rows]


  # ---------------------------------------------------------------------------
  # Config
  # ---------------------------------------------------------------------------

  def get_config(key: str, default: str = "") -> str:
      rows = get_client().table("config").select("value").eq("key", key).execute().data
      return rows[0]["value"] if rows else default
  ```

- [ ] **Step 4: Run tests — expect all pass**

  ```bash
  pytest tests/test_db.py -v
  ```

  Expected: 11 tests PASSED

- [ ] **Step 5: Commit**

  ```bash
  git add cogs/db.py tests/test_db.py
  git commit -m "feat: add db.py Supabase CRUD module with tests"
  ```

---

## Task 4: Update Existing Test File

**Files:**
- Modify: `tests/test_embed_builder.py`

The existing test file imports `cogs.embed_builder` (renamed to `cogs.embed`) and tests file-based storage via `MESSAGES_FILE` monkeypatching. After migration those storage functions move to `cogs.db` (covered by `test_db.py`). This task rewrites the affected tests.

- [ ] **Step 1: Replace the entire tests/test_embed_builder.py**

  ```python
  from unittest.mock import patch
  import pytest
  import cogs.embed as eb


  # ---------------------------------------------------------------------------
  # new_draft
  # ---------------------------------------------------------------------------

  def test_new_draft_structure():
      draft = eb.new_draft(123456789)
      assert draft["status"] == "draft"
      assert draft["channel_id"] == 123456789
      assert draft["label"] is None
      assert draft["title"] is None
      assert draft["send_at"] is None
      assert draft["message_id"] is None
      assert draft["color"] is None
      assert "id" in draft
      assert "created_at" in draft


  def test_new_draft_with_label():
      draft = eb.new_draft(111, label="May Announcement")
      assert draft["label"] == "May Announcement"


  def test_new_draft_with_color():
      draft = eb.new_draft(111, color=0x9B59B6)
      assert draft["color"] == 0x9B59B6


  # ---------------------------------------------------------------------------
  # parse_color
  # ---------------------------------------------------------------------------

  def test_parse_color_valid_no_hash():
      assert eb.parse_color("9B59B6") == 0x9B59B6


  def test_parse_color_valid_with_hash():
      assert eb.parse_color("#FF0000") == 0xFF0000


  def test_parse_color_black():
      assert eb.parse_color("000000") == 0


  def test_parse_color_empty():
      assert eb.parse_color("") is None
      assert eb.parse_color("   ") is None


  def test_parse_color_invalid_chars():
      assert eb.parse_color("ZZZZZZ") == -1


  def test_parse_color_wrong_length():
      assert eb.parse_color("FFF") == -1
      assert eb.parse_color("1234567") == -1


  # ---------------------------------------------------------------------------
  # parse_send_at
  # ---------------------------------------------------------------------------

  def test_parse_send_at_valid_future():
      from datetime import datetime, timedelta, timezone
      cst = timezone(timedelta(hours=8))
      future = (datetime.now(cst) + timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
      result = eb.parse_send_at(future)
      assert result is not None
      assert "+08:00" in result


  def test_parse_send_at_past():
      assert eb.parse_send_at("2000-01-01 00:00") is None


  def test_parse_send_at_invalid_format():
      assert eb.parse_send_at("not a date") is None
      assert eb.parse_send_at("2026/05/20 15:00") is None


  # ---------------------------------------------------------------------------
  # build_embed / build_view
  # ---------------------------------------------------------------------------

  def _full_msg(**overrides):
      base = {
          "title": "Test Title",
          "description": "Test body",
          "footer": "Footer text",
          "image_url": "https://example.com/img.png",
          "color": 0xFF0000,
          "button_label": "Click",
          "button_url": "https://example.com",
      }
      return {**base, **overrides}


  def test_build_embed_sets_all_fields():
      embed = eb.build_embed(_full_msg())
      assert embed.title == "Test Title"
      assert embed.description == "Test body"
      assert embed.color.value == 0xFF0000
      assert embed.footer.text == "Footer text"
      assert embed.image.url == "https://example.com/img.png"


  def test_build_embed_no_footer_or_image():
      embed = eb.build_embed(_full_msg(footer=None, image_url=None))
      assert embed.title == "Test Title"
      assert embed.description == "Test body"


  def test_build_view_with_button():
      view = eb.build_view(_full_msg())
      assert view is not None
      assert len(view.children) == 1
      btn = view.children[0]
      assert btn.url == "https://example.com"
      assert btn.label == "Click"


  def test_build_view_no_button():
      assert eb.build_view(_full_msg(button_label=None, button_url=None)) is None


  def test_build_view_partial_button():
      assert eb.build_view(_full_msg(button_url=None)) is None


  # ---------------------------------------------------------------------------
  # last_used_color (mocked — storage tested in test_db.py)
  # ---------------------------------------------------------------------------

  def test_last_used_color_no_messages():
      with patch("cogs.embed.load_messages", return_value=[]):
          assert eb.last_used_color() is None


  def test_last_used_color_returns_most_recent():
      old = {**eb.new_draft(1, color=0xFF0000), "created_at": "2026-01-01T00:00:00+08:00"}
      new = {**eb.new_draft(2, color=0x00FF00), "created_at": "2026-06-01T00:00:00+08:00"}
      with patch("cogs.embed.load_messages", return_value=[old, new]):
          assert eb.last_used_color() == 0x00FF00


  def test_last_used_color_skips_uncolored():
      no_color = eb.new_draft(1)
      colored = eb.new_draft(2, color=0xABCDEF)
      with patch("cogs.embed.load_messages", return_value=[no_color, colored]):
          assert eb.last_used_color() == 0xABCDEF


  # ---------------------------------------------------------------------------
  # display_label
  # ---------------------------------------------------------------------------

  class _FakeChannel:
      name = "announcements"


  class _FakeBot:
      def get_channel(self, _id):
          return _FakeChannel()


  def test_display_label_uses_custom_label():
      msg = {"label": "My Post", "channel_id": 1, "created_at": "2026-05-18T10:00:00+08:00", "title": "X"}
      assert eb.display_label(msg, bot=None) == "My Post"


  def test_display_label_auto_with_title():
      msg = {"label": None, "channel_id": 1, "created_at": "2026-05-18T10:00:00+08:00", "title": "Hello World"}
      label = eb.display_label(msg, bot=_FakeBot())
      assert "#announcements" in label
      assert "2026-05-18" in label
      assert "Hello World" in label


  def test_display_label_auto_no_title():
      msg = {"label": None, "channel_id": 1, "created_at": "2026-05-18T10:00:00+08:00", "title": None}
      label = eb.display_label(msg, bot=_FakeBot())
      assert "(untitled)" in label


  # ---------------------------------------------------------------------------
  # parse_message_link
  # ---------------------------------------------------------------------------

  def test_parse_message_link_valid():
      link = "https://discord.com/channels/111/222333/444555"
      assert eb.parse_message_link(link) == (222333, 444555)


  def test_parse_message_link_ptb():
      link = "https://ptb.discord.com/channels/111/222333/444555"
      assert eb.parse_message_link(link) == (222333, 444555)


  def test_parse_message_link_invalid():
      assert eb.parse_message_link("not a link") is None
      assert eb.parse_message_link("https://discord.com/channels/111") is None


  # ---------------------------------------------------------------------------
  # draft_from_message
  # ---------------------------------------------------------------------------

  class _FakeEmbed:
      title = "Test Title"
      description = "Body text"
      color = type("C", (), {"value": 0xFF0000})()
      footer = type("F", (), {"text": "Footer"})()
      image = type("I", (), {"url": "https://example.com/img.png"})()


  class _FakeButton:
      url = "https://example.com"
      label = "Click me"


  class _FakeRow:
      children = [_FakeButton()]


  class _FakeChannel2:
      id = 999


  class _FakeMessage:
      id = 12345
      embeds = [_FakeEmbed()]
      components = [_FakeRow()]
      channel = _FakeChannel2()


  def test_draft_from_message_fields():
      draft = eb.draft_from_message(_FakeMessage())
      assert draft["title"] == "Test Title"
      assert draft["description"] == "Body text"
      assert draft["footer"] == "Footer"
      assert draft["image_url"] == "https://example.com/img.png"
      assert draft["color"] == 0xFF0000
      assert draft["button_label"] == "Click me"
      assert draft["button_url"] == "https://example.com"
      assert draft["message_id"] == 12345
      assert draft["channel_id"] == 999


  def test_draft_from_message_no_button():
      class _NoButtonRow:
          children = []

      class _MsgNoBtn:
          id = 1
          embeds = [_FakeEmbed()]
          components = [_NoButtonRow()]
          channel = _FakeChannel2()

      draft = eb.draft_from_message(_MsgNoBtn())
      assert draft["button_label"] is None
      assert draft["button_url"] is None
  ```

- [ ] **Step 2: Run all tests — expect failures on embed tests (embed.py still uses file storage)**

  ```bash
  pytest tests/ -v
  ```

  Expected: `test_db.py` passes, `test_embed_builder.py` fails with `ModuleNotFoundError: No module named 'cogs.embed_builder'` → now fails with import errors on `cogs.db` because embed.py hasn't been migrated yet. That's correct — tests are ahead of implementation.

- [ ] **Step 3: Commit**

  ```bash
  git add tests/test_embed_builder.py
  git commit -m "test: update embed tests to use cogs.embed and mock storage layer"
  ```

---

## Task 5: Migrate embed.py to Use db.py

**Files:**
- Modify: `cogs/embed.py`

- [ ] **Step 1: Replace the imports and Storage section at the top of embed.py**

  Remove everything from `from __future__ import annotations` down through the closing line of `last_used_color()` (the entire top block including all imports and the five storage functions: `load_messages`, `save_messages`, `get_message`, `upsert_message`, `delete_message`, and `last_used_color`).

  Replace with:

  ```python
  from __future__ import annotations

  import re
  import uuid
  from datetime import datetime, timedelta, timezone
  from typing import Any

  import discord
  from discord import app_commands
  from discord.ext import commands, tasks

  from cogs.db import delete_message, get_message, load_messages, upsert_message

  CST = timezone(timedelta(hours=8))


  def last_used_color() -> int | None:
      colored = [m for m in load_messages() if m.get("color") is not None]
      if not colored:
          return None
      colored.sort(key=lambda m: m.get("created_at", ""), reverse=True)
      return colored[0]["color"]
  ```

  Everything from `new_draft()` onwards stays exactly as-is.

- [ ] **Step 2: Run all tests**

  ```bash
  pytest tests/ -v
  ```

  Expected: all tests in `test_db.py` and `test_embed_builder.py` PASS

- [ ] **Step 3: Commit**

  ```bash
  git add cogs/embed.py
  git commit -m "feat: migrate embed.py storage from file to Supabase"
  ```

---

## Task 6: Migrate roles.py to Use db.py

**Files:**
- Modify: `cogs/roles.py`

- [ ] **Step 1: Replace the entire cogs/roles.py**

  ```python
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
  ```

- [ ] **Step 2: Run all tests**

  ```bash
  pytest tests/ -v
  ```

  Expected: all tests PASS

- [ ] **Step 3: Commit**

  ```bash
  git add cogs/roles.py
  git commit -m "feat: migrate roles.py config from hardcoded to Supabase"
  ```

---

## Task 7: Data Migration Script

**Files:**
- Create: `scripts/migrate_messages.py`

- [ ] **Step 1: Create scripts/migrate_messages.py**

  ```python
  """One-time migration: import messages.json into Supabase messages table."""
  import json
  import os
  import sys
  from pathlib import Path

  from supabase import create_client

  MESSAGES_FILE = Path(os.environ.get("MESSAGES_FILE", "messages.json"))


  def main() -> None:
      url = os.environ.get("SUPABASE_URL")
      key = os.environ.get("SUPABASE_SERVICE_KEY")
      if not url or not key:
          print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_KEY must be set.")
          sys.exit(1)

      if not MESSAGES_FILE.exists():
          print(f"No file at {MESSAGES_FILE} — nothing to migrate.")
          return

      messages = json.loads(MESSAGES_FILE.read_text(encoding="utf-8"))
      if not messages:
          print("File is empty — nothing to migrate.")
          return

      client = create_client(url, key)
      client.table("messages").upsert(messages).execute()
      print(f"Migrated {len(messages)} messages to Supabase.")


  if __name__ == "__main__":
      main()
  ```

- [ ] **Step 2: Commit**

  ```bash
  git add scripts/migrate_messages.py
  git commit -m "chore: add one-time messages.json to Supabase migration script"
  ```

---

## Task 8: Deploy and Verify (Manual — User Action Required)

- [ ] **Step 1: Set env vars on Railway**

  In Railway → your bot service → Variables, add:
  ```
  SUPABASE_URL=https://your-project-ref.supabase.co
  SUPABASE_SERVICE_KEY=your-service-role-key
  ```

- [ ] **Step 2: Run migration script to import existing messages**

  On your local machine (with env vars set in your terminal session):
  ```bash
  pip install supabase
  python scripts/migrate_messages.py
  ```

  Expected output: `Migrated N messages to Supabase.`

  Verify in Supabase → Table Editor → messages that the rows appear.

- [ ] **Step 3: Push to Railway**

  ```bash
  git push origin main
  ```

  Watch Railway deploy logs — bot should start with no errors.

- [ ] **Step 4: Verify bot functions in Discord**

  - `/embed` → create, edit, schedule, send an embed ✅
  - Role selection dropdown → assigns/removes role correctly ✅
  - Check Supabase `messages` table updates when you create/send embeds ✅

- [ ] **Step 5: Start 3-day observation period**

  Note today's date. Do not remove the Railway Volume until Task 9.

---

## Task 9: Remove Railway Volume (Manual — After 3-Day Observation)

**Only proceed after bot has run normally on Supabase for 3+ days with no issues.**

- [ ] **Step 1: Remove MESSAGES_FILE env var from Railway**

  In Railway → Variables, delete `MESSAGES_FILE` (no longer used).

- [ ] **Step 2: Remove Railway Volume**

  In Railway → your service → Volumes → detach and delete the volume.

- [ ] **Step 3: Final commit**

  ```bash
  git commit --allow-empty -m "chore: Railway Volume removed, fully migrated to Supabase"
  ```
