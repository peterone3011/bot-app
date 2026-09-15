# Multi-Project Discord Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn FortunePurple into the first instance of a shared, multi-project Discord Bot core that supports manual embeds, role selection, channel reactions, Feishu daily updates, and Feishu community metrics.

**Architecture:** Add a configuration-driven runtime that starts one isolated `discord.ext.commands.Bot` per enabled project. Shared Cogs receive a `ProjectRuntime` instead of reading process-global environment variables. FortunePurple is migrated first with one enabled project; only after its acceptance can another project be enabled in the same Railway service.

**Tech Stack:** Python 3, discord.py 2.x, aiohttp, PyYAML, Feishu Open API, Railway Volume, pytest, pytest-asyncio.

## Global Constraints

- Keep the current `bot.py` deployment entrypoint until the single-project FortunePurple cutover is explicitly approved.
- Do not run old and new Discord clients with the same FortunePurple token at the same time.
- Do not modify FortunePurple's existing Feishu Base or Bitable schemas during this migration.
- Treat all Discord IDs as strings in YAML and convert them to integers only in validated runtime objects.
- Keep secrets exclusively in Railway/local environment variables; YAML references environment-variable names and never contains secret values.
- Preserve daily updates: BJT `00:01`, retry only at `00:06` and `00:16`, startup catch-up only during BJT `00:00-00:30`, no daytime read/publish, and no duplicate send when Feishu status write-back fails.
- Preserve daily community metrics: BJT `23:59`, fields `日期`, `当前总人数`, `新增人数`, `离开人数`, `净增长`.
- Every log line produced by the new runtime begins with `[<project slug>][<feature>]`.
- Do not remove the legacy cogs, Dashboard, Supabase, Upstash, or Railway/Vercel variables in this plan; that is handled by the follow-up cleanup plan after stable production acceptance.

---

## Target File Structure

```text
app/
  __init__.py
  runner.py
  core/
    __init__.py
    config.py
    feishu.py
    runtime.py
    state.py
  cogs/
    __init__.py
    manual_embed.py
    role_selector.py
    auto_reaction.py
    daily_updates.py
    community_metrics.py
projects/
  example.yaml
  fortunepurple.yaml
tests/
  test_project_config.py
  test_runner.py
  test_manual_embed.py
  test_role_selector.py
  test_auto_reaction.py
  test_daily_updates_runtime.py
  test_community_metrics_runtime.py
scripts/
  validate_projects.py
bot.py
requirements.txt
README.md
Procfile
```

`cogs/` remains untouched until FortunePurple has run successfully on `app/`. The new package is deliberately separate so the production cutover is a single entrypoint change and a revert is a single Git/Railway rollback.

### Shared Interfaces

```python
# app/core/config.py
@dataclass(frozen=True)
class ProjectConfig:
    slug: str
    brand_name: str
    discord: DiscordConfig
    features: FeatureFlags
    channels: ChannelConfig
    role_selector: RoleSelectorConfig | None
    auto_reactions: tuple[ReactionRule, ...]
    feishu: FeishuConfig | None

def load_projects(repo_root: Path, enabled_slugs: Sequence[str], environ: Mapping[str, str]) -> list[ProjectConfig]: ...

# app/core/runtime.py
@dataclass
class ProjectRuntime:
    config: ProjectConfig
    bot: commands.Bot
    state_dir: Path
    feishu: FeishuClient | None

async def run_project(config: ProjectConfig, state_root: Path) -> None: ...
async def run_enabled_projects(repo_root: Path, environ: Mapping[str, str]) -> None: ...

# app/core/feishu.py
class FeishuClient:
    async def list_records(self, app_token: str, table_id: str) -> list[dict[str, Any]]: ...
    async def update_record(self, app_token: str, table_id: str, record_id: str, fields: dict[str, Any]) -> None: ...
    async def upsert_record_by_text_field(self, app_token: str, table_id: str, key_field: str, key: str, fields: dict[str, Any]) -> Literal["created", "updated"]: ...

# app/cogs/<name>.py
async def install(runtime: ProjectRuntime) -> None: ...
```

## Task 1: Add Validated Project Configuration

**Files:**
- Create: `app/__init__.py`
- Create: `app/core/__init__.py`
- Create: `app/core/config.py`
- Create: `projects/example.yaml`
- Test: `tests/test_project_config.py`
- Modify: `requirements.txt`

**Consumes:** Railway environment variables and checked-in `projects/<slug>.yaml` files.

**Produces:** `ProjectConfig`, `load_projects()`, `enabled_project_slugs()`, and explicit `ConfigError` messages used by the runner and preflight script.

- [ ] **Step 1: Write failing configuration tests**

```python
def test_load_projects_resolves_secret_env_references(tmp_path: Path):
    (tmp_path / "projects").mkdir()
    (tmp_path / "projects" / "alpha.yaml").write_text(VALID_YAML)
    configs = load_projects(tmp_path, ["alpha"], {
        "DISCORD_TOKEN_ALPHA": "token-value",
        "FEISHU_ALPHA_APP_ID": "app-id",
        "FEISHU_ALPHA_APP_SECRET": "app-secret",
        "FEISHU_ALPHA_UPDATES_BASE": "base",
        "FEISHU_ALPHA_UPDATES_TABLE": "table",
        "FEISHU_ALPHA_METRICS_BASE": "metrics-base",
        "FEISHU_ALPHA_METRICS_TABLE": "metrics-table",
    })
    assert configs[0].slug == "alpha"
    assert configs[0].discord.token == "token-value"
    assert configs[0].channels.roles == 101

def test_load_projects_rejects_duplicate_guilds(tmp_path: Path):
    write_project(tmp_path, "alpha", guild_id="101")
    write_project(tmp_path, "beta", guild_id="101")
    with pytest.raises(ConfigError, match="Discord guild ID 101 is used by alpha and beta"):
        load_projects(tmp_path, ["alpha", "beta"], ALL_SECRETS)
```

- [ ] **Step 2: Run the configuration tests to verify they fail**

Run: `python -m pytest tests/test_project_config.py -q`  
Expected: FAIL because `app.core.config` does not exist.

- [ ] **Step 3: Add the parser and exact validation contract**

Add `PyYAML>=6.0.2` to `requirements.txt`. In `app/core/config.py`, load one YAML mapping per requested slug using `yaml.safe_load`, reject unrequested/missing files, and create immutable dataclasses. Implement these rules:

```python
def enabled_project_slugs(environ: Mapping[str, str]) -> tuple[str, ...]:
    slugs = tuple(item.strip() for item in environ.get("ENABLED_PROJECTS", "").split(",") if item.strip())
    if not slugs:
        raise ConfigError("ENABLED_PROJECTS must name at least one project")
    if len(set(slugs)) != len(slugs):
        raise ConfigError("ENABLED_PROJECTS contains a duplicate project slug")
    return slugs

def require_positive_id(value: object, path: str) -> int:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{path} must be a positive Discord ID") from exc
    if parsed <= 0:
        raise ConfigError(f"{path} must be a positive Discord ID")
    return parsed
```

Require a token environment value for every project. Require `role_selector` and either `channels.roles` or the FortunePurple compatibility field `channels.roles_name` when `features.role_selector` is true. Require a non-empty `auto_reactions` list only when at least one reaction feature is true. Require all six Feishu environment references when either Feishu feature is true. Validate globally unique project slug, Guild ID and resolved Discord token. Do not log resolved secret values.

Create `projects/example.yaml` with the exact sections in the approved design document and only `<...>` identifiers as examples.

- [ ] **Step 4: Run the parser tests**

Run: `python -m pytest tests/test_project_config.py -q`  
Expected: PASS, including missing-secret, invalid-ID, feature-dependency, duplicate-slug, duplicate-Guild and duplicate-token cases.

- [ ] **Step 5: Commit the configuration foundation**

```bash
git add requirements.txt app/__init__.py app/core/__init__.py app/core/config.py projects/example.yaml tests/test_project_config.py
git commit -m "feat: add validated project configuration"
```

## Task 2: Create Project-Scoped State and Feishu Services

**Files:**
- Create: `app/core/state.py`
- Create: `app/core/feishu.py`
- Test: `tests/test_community_metrics_runtime.py`
- Test: `tests/test_daily_updates_runtime.py`

**Consumes:** `ProjectConfig.feishu`, Railway Volume root (`RAILWAY_VOLUME_MOUNT_PATH`, default `/data`), and aiohttp.

**Produces:** project-isolated paths and a single token-caching Feishu client used by both retained Feishu Cogs.

- [ ] **Step 1: Write failing state-isolation and Feishu-client tests**

```python
def test_project_state_paths_do_not_overlap(tmp_path: Path):
    alpha = ProjectState(tmp_path, "alpha")
    beta = ProjectState(tmp_path, "beta")
    assert alpha.events_file == tmp_path / "alpha" / "community-events.jsonl"
    assert beta.pending_rollups_file == tmp_path / "beta" / "pending-rollups.json"
    assert alpha.events_file != beta.events_file

@pytest.mark.asyncio
async def test_feishu_client_reuses_a_tenant_token(aiohttp_mock):
    client = FeishuClient(app_id="id", app_secret="secret")
    await client.list_records("base", "table")
    await client.list_records("base", "table")
    assert aiohttp_mock.token_requests == 1
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `python -m pytest tests/test_community_metrics_runtime.py tests/test_daily_updates_runtime.py -q`  
Expected: FAIL because `ProjectState` and `FeishuClient` do not exist.

- [ ] **Step 3: Implement project-scoped files and Feishu HTTP operations**

Implement `ProjectState(root: Path, slug: str)` with these exact properties:

```python
@property
def events_file(self) -> Path:
    return self.directory / "community-events.jsonl"

@property
def pending_rollups_file(self) -> Path:
    return self.directory / "pending-rollups.json"
```

Create the project directory lazily. Preserve atomic pending-rollup replacement using a same-directory `.tmp` file and lock. Do not reuse legacy global file names.

Implement `FeishuClient(app_id, app_secret)` with a cached tenant token that expires five minutes before Feishu's reported expiry. Use one `_request()` method with a 30-second aiohttp timeout, `Authorization: Bearer <token>`, strict JSON/code validation, and token invalidation on request failure. Implement pagination for `list_records`, record update, record create, and upsert-by-text-field. Include deterministic `client_token` creation based on app token, table ID and key so Feishu retries remain idempotent.

- [ ] **Step 4: Run the focused tests**

Run: `python -m pytest tests/test_community_metrics_runtime.py tests/test_daily_updates_runtime.py -q`  
Expected: PASS for isolated path construction, token reuse, non-JSON/API failures, pagination and deterministic create tokens.

- [ ] **Step 5: Commit the shared service layer**

```bash
git add app/core/state.py app/core/feishu.py tests/test_community_metrics_runtime.py tests/test_daily_updates_runtime.py
git commit -m "feat: add project scoped feishu services"
```

## Task 3: Add the Multi-Bot Runner and Cog Registry

**Files:**
- Create: `app/core/runtime.py`
- Create: `app/runner.py`
- Test: `tests/test_runner.py`

**Consumes:** `ProjectConfig`, `ProjectState`, `FeishuClient`, and the five Cog `install(runtime)` factories introduced in later tasks.

**Produces:** one independently supervised Discord client per project, with project-scoped command sync and error handling.

- [ ] **Step 1: Write failing runner tests**

```python
@pytest.mark.asyncio
async def test_run_enabled_projects_supervises_projects_independently(monkeypatch, tmp_path):
    calls: list[str] = []
    async def fake_run_project(config, state_root):
        calls.append(config.slug)
    monkeypatch.setattr(runner, "run_project", fake_run_project)
    await runner.run_enabled_projects(tmp_path, {"ENABLED_PROJECTS": "alpha,beta", **ALL_SECRETS})
    assert calls == ["alpha", "beta"]

@pytest.mark.asyncio
async def test_project_ready_syncs_only_its_configured_guild(fake_runtime):
    await runtime.on_ready()
    runtime.bot.tree.copy_global_to.assert_awaited_once_with(guild=discord.Object(id=runtime.config.discord.guild_id))
```

- [ ] **Step 2: Run the runner tests to verify they fail**

Run: `python -m pytest tests/test_runner.py -q`  
Expected: FAIL because `app.runner` does not exist.

- [ ] **Step 3: Implement `ProjectRuntime` and supervision**

Create one `commands.Bot` per `ProjectConfig`, always enabling `members` and `message_content` intents. Build a dedicated proxy connector per Bot if `PROXY` exists; never share an aiohttp connector between projects. Register an app-command error handler that returns one ephemeral generic error and logs the full traceback with the project slug.

Implement the lifecycle exactly as follows:

```python
async def run_project(config: ProjectConfig, state_root: Path) -> None:
    while True:
        bot = create_project_bot(config)
        runtime = ProjectRuntime(config=config, bot=bot, state_dir=state_root / config.slug, feishu=make_feishu_client(config))
        try:
            await install_enabled_cogs(runtime)
            await bot.start(config.discord.token)
        except asyncio.CancelledError:
            await bot.close()
            raise
        except Exception:
            log_exception(config.slug, "runner")
            await bot.close()
            await asyncio.sleep(10)
```

`on_ready` must call `bot.tree.copy_global_to(guild=discord.Object(id=config.discord.guild_id))`, then `await bot.tree.sync(guild=...)`, and log the project, logged-in user, Guild and enabled feature names. `run_enabled_projects` must use `asyncio.gather` with one `run_project` task per valid project so a reconnect loop remains local to that project.

Do not modify `bot.py` or `Procfile` in this task. The current production entrypoint remains intact until all shared Cogs, the real FortunePurple configuration and preflight verification have been completed and the administrator explicitly approves the Railway cutover.

- [ ] **Step 4: Run runner tests**

Run: `python -m pytest tests/test_runner.py -q`  
Expected: PASS for one-Bot-per-project creation, Guild-limited sync, per-project reconnection and cancellation cleanup.

- [ ] **Step 5: Commit the runner**

```bash
git add app/core/runtime.py app/runner.py tests/test_runner.py
git commit -m "feat: add multi project bot runner"
```

## Task 4: Replace the Dashboard Embed Builder with an Admin Slash Command

**Files:**
- Create: `app/cogs/__init__.py`
- Create: `app/cogs/manual_embed.py`
- Test: `tests/test_manual_embed.py`

**Consumes:** `ProjectRuntime.config.discord.admin_role_ids` and the configured `manual_embed_channel_ids` list.

**Produces:** `/embed` that immediately posts a configured Embed without Supabase or Dashboard persistence.

- [ ] **Step 1: Write failing permission and publish tests**

```python
@pytest.mark.asyncio
async def test_embed_command_rejects_non_admin(runtime, interaction):
    await ManualEmbedCog(runtime).publish.callback(interaction, channel, "Title", "Body", None, None, None, None)
    interaction.response.send_message.assert_awaited_once_with("You are not allowed to use this command.", ephemeral=True)

@pytest.mark.asyncio
async def test_embed_command_sends_link_button_for_allowed_admin(runtime, admin_interaction, channel):
    await ManualEmbedCog(runtime).publish.callback(admin_interaction, channel, "Title", "Body", "FF9933", None, "Claim", "https://example.com")
    channel.send.assert_awaited_once()
```

- [ ] **Step 2: Run the embed tests to verify they fail**

Run: `python -m pytest tests/test_manual_embed.py -q`  
Expected: FAIL because `ManualEmbedCog` does not exist.

- [ ] **Step 3: Implement `/embed`**

Create one app command with this exact argument contract:

```python
@app_commands.command(name="embed", description="Publish an embed message")
async def publish(
    self,
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    title: str,
    description: str,
    color: str | None = None,
    image_url: str | None = None,
    button_label: str | None = None,
    button_url: str | None = None,
) -> None: ...
```

Reject users whose roles do not intersect `admin_role_ids`. When `manual_embed_channel_ids` is non-empty, reject channels outside it; an empty list explicitly permits any text channel for FortunePurple compatibility. Require button label and URL together, require an absolute `http` or `https` URL for image/button fields, and parse color as optional six-digit RGB hex. Send the final Embed to the target channel, then reply ephemerally with a permalink to the posted message. Use `allowed_mentions=discord.AllowedMentions.none()` for the command acknowledgement and never persist drafts.

- [ ] **Step 4: Run embed tests**

Run: `python -m pytest tests/test_manual_embed.py -q`  
Expected: PASS for authorization, channel whitelist, color/URL validation, embed rendering and optional link button.

- [ ] **Step 5: Commit the manual embed cog**

```bash
git add app/cogs/__init__.py app/cogs/manual_embed.py tests/test_manual_embed.py
git commit -m "feat: add manual embed command"
```

## Task 5: Port Role Selection to Project Configuration

**Files:**
- Create: `app/cogs/role_selector.py`
- Test: `tests/test_role_selector.py`

**Consumes:** `ProjectRuntime`, `RoleSelectorConfig`, project Roles channel ID, and configured Role IDs.

**Produces:** a persistent project-specific selector with subscribe/unsubscribe behavior and no Supabase dependency.

- [ ] **Step 1: Write failing selector tests**

```python
def test_role_select_custom_id_is_project_scoped(runtime):
    view = RoleSelectorView(runtime)
    assert view.children[0].custom_id == "roles:alpha"

@pytest.mark.asyncio
async def test_select_removes_existing_role(runtime, interaction, member, role):
    await handle_selection(runtime, interaction, role.id)
    member.remove_roles.assert_awaited_once_with(role, reason="notification role opt-out")
```

- [ ] **Step 2: Run selector tests to verify they fail**

Run: `python -m pytest tests/test_role_selector.py -q`  
Expected: FAIL because `RoleSelectorView` and `handle_selection` do not exist.

- [ ] **Step 3: Implement the persistent selector**

`RoleSelectorView(runtime)` must use `timeout=None`, custom ID `roles:<slug>`, and options from the project configuration. On ready, fetch the configured Roles channel by ID, find the most recent message authored by this Bot whose first component custom ID matches `roles:<slug>`, then edit it; send a new selector only when none exists. Resolve the selected Role by configured numeric Role ID, never by name. Toggle it with reasons `notification role opt-in` and `notification role opt-out`. Send a single ephemeral outcome response. Log and return a non-sensitive ephemeral error if the configured Role or channel is unavailable.

- [ ] **Step 4: Run selector tests**

Run: `python -m pytest tests/test_role_selector.py -q`  
Expected: PASS for project-specific custom IDs, one selector message, Role add/remove, missing Role and missing permissions.

- [ ] **Step 5: Commit the role selector**

```bash
git add app/cogs/role_selector.py tests/test_role_selector.py
git commit -m "feat: add configured role selector"
```

## Task 6: Add Configured Auto-Reaction Rules

**Files:**
- Create: `app/cogs/auto_reaction.py`
- Test: `tests/test_auto_reaction.py`

**Consumes:** `ProjectRuntime.config.auto_reactions`, `features.auto_reaction`, and `features.exclusive_updates_reaction`.

**Produces:** a single listener that adds configured emojis to each matching message, including Bot messages when a rule permits them.

- [ ] **Step 1: Write failing reaction tests**

```python
@pytest.mark.asyncio
async def test_reacts_with_every_configured_emoji(runtime, message):
    await AutoReactionCog(runtime).on_message(message)
    assert message.add_reaction.await_args_list == [call("🔥"), call("🎉")]

@pytest.mark.asyncio
async def test_bot_message_is_skipped_when_rule_excludes_bots(runtime, bot_message):
    await AutoReactionCog(runtime).on_message(bot_message)
    bot_message.add_reaction.assert_not_awaited()
```

- [ ] **Step 2: Run reaction tests to verify they fail**

Run: `python -m pytest tests/test_auto_reaction.py -q`  
Expected: FAIL because `AutoReactionCog` does not exist.

- [ ] **Step 3: Implement matching and error isolation**

Build a map from configured channel ID to immutable reaction rules at Cog construction. A rule belongs to `exclusive-updates` only when its channel ID equals the configured `channels.exclusive_updates`; do not apply that rule when `exclusive_updates_reaction` is false. For each message in a matching Guild and channel, skip Bot authors only when every matching rule has `include_bot_messages` false. Call `await message.add_reaction(emoji)` in configuration order. Catch `discord.Forbidden`, `discord.HTTPException`, and invalid-emoji failures per emoji, log `[slug][auto_reaction]`, then continue with the remaining emoji/rules.

- [ ] **Step 4: Run reaction tests**

Run: `python -m pytest tests/test_auto_reaction.py -q`  
Expected: PASS for multiple rules, emoji order, Bot-message option, disabled exclusive rule, unrelated Guild/channel and per-emoji failures.

- [ ] **Step 5: Commit the auto-reaction cog**

```bash
git add app/cogs/auto_reaction.py tests/test_auto_reaction.py
git commit -m "feat: add project auto reactions"
```

## Task 7: Port Daily Updates Without Changing Its Operational Contract

**Files:**
- Create: `app/cogs/daily_updates.py`
- Test: `tests/test_daily_updates_runtime.py`
- Reference: `cogs/updates.py`, `tests/test_updates.py`

**Consumes:** `ProjectRuntime`, `FeishuClient`, update Base/table IDs, update/staff channel IDs and project state-free Bitable status fields.

**Produces:** a project-scoped daily updates Cog with the existing schedule and duplicate-prevention semantics.

- [ ] **Step 1: Copy the existing high-risk behavioral tests into runtime tests**

Port these exact test cases from `tests/test_updates.py` before implementing the new Cog: `test_success_stops_later_slots`, `test_failure_allows_next_slot_but_not_duplicate_slot`, `test_same_slot_concurrent_attempts_only_post_once`, `test_auto_post_ignores_delayed_daytime_callback`, `test_startup_catchup_ignores_daytime`, `test_do_post_preserves_posting_discord_done_inside_deadline`, and `test_do_post_stops_after_done_status_failure`.

- [ ] **Step 2: Run the ported tests to verify they fail**

Run: `python -m pytest tests/test_daily_updates_runtime.py -q`  
Expected: FAIL because `app.cogs.daily_updates` does not exist.

- [ ] **Step 3: Implement the project-scoped scheduler and publisher**

Extract pure helpers with the same public behavior as the legacy module: `extract_text`, `is_due`, `startup_window_contains`, `slot_for_time`, and `update_status_with_retry`. `DailyUpdatesCog(runtime)` owns an `asyncio.Lock`, a BJT-date/slot completion map, and exactly three UTC task times: `16:01`, `16:06`, `16:16`.

For each slot, acquire the lock before reading Feishu; exit if an earlier successful slot completed. Read records only while the BJT slot is active. A record is eligible only when `状态 == 待发布` and its `日期` is earlier than the BJT current day. Mark one record `发布中`, send its text and optional image, then write `已发布` with three immediate retry attempts. If send fails, restore `待发布` with three attempts. If send succeeds but final status still fails, do not send it again that night. Startup calls the same slot method only when BJT time is within `00:00-00:30`.

Use `runtime.feishu`, project Base/table settings, and project channels exclusively. Preserve the existing Feishu field names `日期`, `发布文案`, `配图`, `状态`.

- [ ] **Step 4: Run both legacy and runtime daily-update suites**

Run: `python -m pytest tests/test_updates.py tests/test_daily_updates_runtime.py -q`  
Expected: PASS. The legacy tests demonstrate unchanged current behavior; the new suite demonstrates that the runtime port preserves it.

- [ ] **Step 5: Commit daily update migration**

```bash
git add app/cogs/daily_updates.py tests/test_daily_updates_runtime.py
git commit -m "feat: add project daily updates cog"
```

## Task 8: Port Community Metrics With Project-Scoped Persistence

**Files:**
- Create: `app/cogs/community_metrics.py`
- Test: `tests/test_community_metrics_runtime.py`
- Reference: `cogs/community_metrics.py`, `tests/test_community_metrics.py`

**Consumes:** `ProjectRuntime`, `ProjectState`, `FeishuClient`, and the project metrics Base/table IDs.

**Produces:** independent daily event collection, queue/replay and BJT 23:59 report creation for every project.

- [ ] **Step 1: Write failing project-isolation rollup tests**

```python
@pytest.mark.asyncio
async def test_rollup_writes_daily_fields_to_its_own_feishu_table(alpha_runtime, alpha_guild):
    cog = CommunityMetricsCog(alpha_runtime)
    await cog.write_daily(date(2026, 9, 15))
    alpha_runtime.feishu.upsert_record_by_text_field.assert_awaited_once_with(
        "alpha-metrics-base", "alpha-metrics-table", "日期", "2026/09/15",
        {"日期": "2026/09/15", "当前总人数": 540, "新增人数": 2, "离开人数": 1, "净增长": 1},
    )

def test_alpha_pending_file_never_contains_beta_events(tmp_path: Path):
    assert ProjectState(tmp_path, "alpha").pending_rollups_file.parent != ProjectState(tmp_path, "beta").pending_rollups_file.parent
```

- [ ] **Step 2: Run the metrics runtime tests to verify they fail**

Run: `python -m pytest tests/test_community_metrics_runtime.py -q`  
Expected: FAIL because the project-scoped metrics Cog does not exist.

- [ ] **Step 3: Implement the port using shared services**

Port `_day_window`, `_count_events`, `_format_metric_date`, append-only event logging, pending upsert queue and replay from `cogs/community_metrics.py`. Move file access through `runtime.state_dir`/`ProjectState`; no path may refer to the old global `community_metrics_events.jsonl` or `pending_rollups.json` names. Replace `FeishuBaseClient` calls with `runtime.feishu.upsert_record_by_text_field(base, table, "日期", date_text, fields)`.

`CommunityMetricsCog` listens to non-Bot `on_member_join` and `on_member_remove`, starts one UTC `15:59` daily loop, replays pending payloads after the project Bot is ready, and builds only these fields:

```python
fields = {
    "日期": date_text,
    "当前总人数": total_members,
    "新增人数": joins,
    "离开人数": leaves,
    "净增长": joins - leaves,
}
```

Queue the exact fields before the remote upsert. Remove a pending payload only if the stored payload exactly equals the successful payload. This preserves an event that arrives while an older retry is in flight.

- [ ] **Step 4: Run both metrics suites**

Run: `python -m pytest tests/test_community_metrics.py tests/test_community_metrics_runtime.py -q`  
Expected: PASS, including BJT timing, field set, pending queue replay, transient retries and alpha/beta file isolation.

- [ ] **Step 5: Commit community metrics migration**

```bash
git add app/cogs/community_metrics.py tests/test_community_metrics_runtime.py
git commit -m "feat: add project community metrics cog"
```

## Task 9: Register Cogs, Add FortunePurple Configuration, and Build a No-Login Preflight

**Files:**
- Modify: `app/runner.py`
- Create: `projects/fortunepurple.yaml`
- Create: `scripts/validate_projects.py`
- Modify: `README.md`
- Test: `tests/test_runner.py`

**Consumes:** tasks 1-8 and the current production FortunePurple Railway variables.

**Produces:** a complete but not-yet-cut-over FortunePurple runtime configuration and a safe command that validates it without logging into Discord or calling Feishu.

- [ ] **Step 1: Write failing registry and preflight tests**

```python
@pytest.mark.asyncio
async def test_registry_installs_only_enabled_features(runtime, monkeypatch):
    installed: list[str] = []
    monkeypatch.setattr(runner, "COG_INSTALLERS", {
        "manual_embed": record("manual_embed", installed),
        "role_selector": record("role_selector", installed),
        "auto_reaction": record("auto_reaction", installed),
    })
    await runner.install_enabled_cogs(runtime)
    assert installed == ["manual_embed", "role_selector"]

def test_validate_projects_does_not_call_discord_or_feishu(monkeypatch):
    assert validate_projects.main(["--projects", "fortunepurple"]) == 0
```

- [ ] **Step 2: Run the registry/preflight tests to verify they fail**

Run: `python -m pytest tests/test_runner.py -q`  
Expected: FAIL until the cog registry and validation script exist.

- [ ] **Step 3: Add the registry and FortunePurple config**

Add a `COG_INSTALLERS` map in `app/runner.py`:

```python
COG_INSTALLERS = {
    "manual_embed": manual_embed.install,
    "role_selector": role_selector.install,
    "auto_reaction": auto_reaction.install,
    "daily_updates": daily_updates.install,
    "community_metrics": community_metrics.install,
}
```

Iterate in this fixed order and call an installer only when its feature flag is true. `projects/fortunepurple.yaml` must contain only currently active FortunePurple IDs/labels and environment-variable references. Copy non-secret channel/Role IDs and feature settings from the current live configuration. Map existing `FEISHU_APP_ID`, `FEISHU_APP_SECRET`, `FEISHU_UPDATES_BASE_APP_TOKEN`, `FEISHU_UPDATES_TABLE_ID`, `FEISHU_METRICS_BASE_APP_TOKEN`, and `FEISHU_METRICS_TABLE_ID` to the new names before cutover; do not delete the old variables yet.

`scripts/validate_projects.py` must call only `load_projects()` and print one redacted line per validated project:

```text
OK fortunepurple guild=1498581314495053834 features=manual_embed,role_selector,auto_reaction,daily_updates,community_metrics
```

It must never instantiate `commands.Bot`, import a Cog, make an HTTP request or print a secret.

- [ ] **Step 4: Run preflight and tests locally with a redacted local environment**

Run: `python scripts/validate_projects.py --projects fortunepurple`  
Expected: one `OK fortunepurple ...` line and exit code 0.

Run: `python -m pytest tests/test_project_config.py tests/test_runner.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit registry and preflight**

```bash
git add app/runner.py projects/fortunepurple.yaml scripts/validate_projects.py README.md tests/test_runner.py
git commit -m "feat: configure fortunepurple shared core"
```

## Task 10: Complete Verification and Production Cutover

**Files:**
- Modify: `README.md`
- No source deletion in this task.

**Consumes:** all prior tasks and production FortunePurple configuration.

**Produces:** FortunePurple running as the sole enabled project through the new multi-project runner, with a documented rollback commit.

- [ ] **Step 1: Run complete local regression suites**

Run: `python -m pytest tests -q`  
Expected: PASS with legacy and new runtime suites.

Run: `python scripts/validate_projects.py --projects fortunepurple`  
Expected: the redacted FortunePurple `OK` line; no Discord or Feishu network call.

- [ ] **Step 2: Review the deployment diff before changing Railway**

Run: `git diff origin/main...HEAD -- bot.py Procfile requirements.txt app projects/fortunepurple.yaml`  
Expected: `Procfile` remains `worker: python bot.py`; only the new runner replaces legacy extension loading; no token literal occurs.

- [ ] **Step 3: Add the new Railway variables without removing legacy variables**

Set `ENABLED_PROJECTS=fortunepurple`, `DISCORD_TOKEN_FORTUNEPURPLE`, and every `FEISHU_FP_*` secret referenced by `projects/fortunepurple.yaml`. Compare each value against the live legacy variable before saving. Do not deploy until all configuration names pass `validate_projects.py` in an equivalent local redacted environment.

- [ ] **Step 4: After explicit administrator approval, switch the entrypoint and deploy once**

Replace `bot.py` with the small `app.runner.main` entrypoint in the approved production commit. Keep `Procfile` as `worker: python bot.py`. No Railway deployment, service restart or production Bot change may happen before this explicit approval.

Deploy the committed revision to the existing Railway Bot service. Confirm exactly one FortunePurple login line, its configured Guild sync line, the five expected Cog registration lines, and no legacy Cog load line. Confirm there is no second login using the same token.

- [ ] **Step 5: Run a controlled production smoke test**

In the FortunePurple Discord Guild, verify in this order:

1. The existing roles selector is edited or recreated once and toggles a configured Role both directions.
2. An authorized admin can send `/embed` into an allowlisted channel; a non-admin cannot.
3. A test message in each configured reaction channel receives the configured emoji; a Bot message respects `include_bot_messages`.
4. The daily update Cog log reports the three BJT slots and does not read or publish during daytime restart.
5. The metrics Cog log reports its BJT `23:59` task and pending-replay initialization; do not force a production daily record.

- [ ] **Step 6: Document the accepted cutover and commit**

Add the deployed Git SHA, Railway deployment ID, enabled project list, and smoke-test date to the operational section of `README.md`. Do not include secrets or user IDs.

```bash
git add README.md
git commit -m "docs: record shared core cutover"
```

---

## Follow-Up Plan: Legacy Service Retirement

Run this plan only after FortunePurple has operated through the shared core for seven consecutive days, including one successful daily update cycle and one successful daily metrics rollup. The user must explicitly approve deleting the old services/configuration after that observation period.

### Task 11: Remove Unused Runtime Code and Dependencies

**Files:**
- Delete: `cogs/bigwin.py`
- Delete: `cogs/jackpot.py`
- Delete: `cogs/embed.py`
- Delete: `cogs/db.py`
- Delete: `cogs/activities.py`
- Delete: `cogs/screenshot_activity.py`
- Delete: `cogs/support_redirect.py`
- Delete: `cogs/autorole.py`
- Delete: `cogs/roles.py`
- Delete: `cogs/updates.py`
- Delete: `cogs/community_metrics.py`
- Delete: `dashboard/`
- Delete: `supabase/`
- Modify: `requirements.txt`
- Modify: `README.md`
- Modify: `.gitignore`
- Create: `tests/test_legacy_absence.py`

**Consumes:** the accepted shared-core cutover and no active references to legacy modules.

**Produces:** one Bot-only repository with no Dashboard, Supabase, Upstash or Lark activity dependencies.

- [ ] **Step 1: Write a failing repository-absence test**

```python
def test_runtime_does_not_import_legacy_services():
    forbidden = ("supabase", "upstash", "dashboard", "cogs.bigwin", "cogs.activities")
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in Path("app").rglob("*.py")
    )
    assert not any(token in source for token in forbidden)
```

- [ ] **Step 2: Run the absence test to verify the expected pre-cleanup failure**

Run: `python -m pytest tests/test_legacy_absence.py -q`  
Expected: FAIL until obsolete dependencies and references are removed.

- [ ] **Step 3: Delete legacy implementation only after confirming no active imports**

Remove the listed legacy code and directory trees. Remove `supabase>=2.0.0` from `requirements.txt`; retain `discord.py`, `aiohttp-socks`, `aiohttp` and `PyYAML`. Rewrite the README to document only the shared core, project YAML onboarding, Railway variable naming, preflight and per-project error isolation. Remove obsolete `.gitignore` entries only when they apply exclusively to deleted Dashboard artifacts.

- [ ] **Step 4: Run all tests and static import scan**

Run: `python -m pytest tests -q`  
Expected: PASS with all tests referring only to `app/`.

Run: `rg -n "supabase|upstash|dashboard|cogs\\.(bigwin|jackpot|activities|screenshot_activity|support_redirect|autorole)" app bot.py requirements.txt README.md`  
Expected: no matches.

- [ ] **Step 5: Commit service retirement**

```bash
git add -A
git commit -m "refactor: retire legacy dashboard bot features"
```

### Task 12: Retire Cloud Resources and Legacy Variables

**Files:**
- Modify: `README.md`

**Consumes:** task 11, a production deployment from the post-cleanup commit, and user approval.

**Produces:** Railway and Vercel resources containing only variables/services required by the shared Bot core.

- [ ] **Step 1: Produce the exact before/after variable inventory**

Run: `railway variable list --service bot-app --environment production`  
Expected: inventory containing `ENABLED_PROJECTS`, per-project Discord Tokens, per-project Feishu variables, proxy/volume variables if used, and legacy variables.

Create an inventory table in `README.md` listing retained variable prefixes:

```text
ENABLED_PROJECTS
DISCORD_TOKEN_<PROJECT>
FEISHU_<PROJECT>_APP_ID
FEISHU_<PROJECT>_APP_SECRET
FEISHU_<PROJECT>_UPDATES_BASE
FEISHU_<PROJECT>_UPDATES_TABLE
FEISHU_<PROJECT>_METRICS_BASE
FEISHU_<PROJECT>_METRICS_TABLE
```

- [ ] **Step 2: Remove only named obsolete variables after review**

Delete only confirmed-unreferenced variables: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `DASHBOARD_URL`, `CRON_SECRET`, `BIGWIN_BUTTON_URL`, `JACKPOT_CHANNEL_ID`, `JACKPOT_ENABLED`, `LARK_APP_ID`, `LARK_APP_SECRET`, screenshot activity variables, support redirect variables and old unprefixed Feishu variables. Keep `RAILWAY_VOLUME_MOUNT_PATH` and `PROXY` if they remain used by the shared runner.

- [ ] **Step 3: Decommission Vercel Dashboard only after Bot health verification**

After the post-cleanup Railway deployment has logged a successful FortunePurple startup and has served at least one controlled Discord smoke test, remove the Vercel Dashboard project. Do not remove the Git repository or Railway project.

- [ ] **Step 4: Verify final production health**

Run: `railway logs --service bot-app --environment production --lines 100`  
Expected: exactly the enabled project instances, no missing-environment errors, no Supabase/Big Win/Dashboard calls and no legacy Cog names.

- [ ] **Step 5: Commit final operational documentation**

```bash
git add README.md
git commit -m "docs: document shared bot operations"
```

## Plan Self-Review

- Spec coverage: Tasks 1-10 implement shared core, multiple Bot Tokens, project configuration, feature flags, the five retained workflows, single Railway multi-instance operation, FortunePurple-first migration, per-project Feishu tables, resilience and tests. Tasks 11-12 explicitly defer and then retire Dashboard, Big Win and other confirmed out-of-scope functionality.
- No-secret rule: all configuration examples use environment-variable references or literal placeholders; no production token, secret, Base token or Role/channel ID appears in this plan.
- Cutover safety: the old and new runtime never log in with the same token concurrently; legacy code remains until a seven-day, explicitly approved stability window has passed.
- Type consistency: every Cog factory is `install(runtime: ProjectRuntime)`, configuration is `ProjectConfig`, and all project state is below `ProjectState(root, slug)`.
