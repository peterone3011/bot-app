from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import ConfigError, enabled_project_slugs, load_projects


def project_yaml(
    *,
    slug: str = "alpha",
    guild_id: str = "101",
    token_env: str = "DISCORD_TOKEN_ALPHA",
    include_role_selector: bool = True,
    include_reactions: bool = True,
    include_feishu: bool = True,
) -> str:
    features = f"""
features:
  manual_embed: true
  role_selector: {str(include_role_selector).lower()}
  auto_reaction: {str(include_reactions).lower()}
  exclusive_updates_reaction: false
  daily_updates: {str(include_feishu).lower()}
  community_metrics: {str(include_feishu).lower()}
"""
    role_section = """
role_selector:
  title: Select notifications
  options:
    - label: Updates
      role_id: "202"
      description: Receive updates
""" if include_role_selector else ""
    reaction_section = """
auto_reactions:
  - channel_id: "303"
    emojis: ["🔥"]
    include_bot_messages: true
""" if include_reactions else ""
    feishu_section = """
feishu:
  app_id_env: FEISHU_ALPHA_APP_ID
  app_secret_env: FEISHU_ALPHA_APP_SECRET
  updates_base_env: FEISHU_ALPHA_UPDATES_BASE
  updates_table_env: FEISHU_ALPHA_UPDATES_TABLE
  metrics_base_env: FEISHU_ALPHA_METRICS_BASE
  metrics_table_env: FEISHU_ALPHA_METRICS_TABLE
""" if include_feishu else ""
    return f"""
project:
  slug: {slug}
  brand_name: Alpha
discord:
  token_env: {token_env}
  guild_id: "{guild_id}"
  admin_role_ids: ["404"]
  manual_embed_channel_ids: ["505"]
channels:
  roles: "606"
  exclusive_updates: "707"
  daily_updates: "808"
  staff_alerts: "909"
{features}
{role_section}
{reaction_section}
{feishu_section}
"""


def secrets() -> dict[str, str]:
    return {
        "DISCORD_TOKEN_ALPHA": "alpha-token",
        "DISCORD_TOKEN_BETA": "beta-token",
        "FEISHU_ALPHA_APP_ID": "alpha-app-id",
        "FEISHU_ALPHA_APP_SECRET": "alpha-app-secret",
        "FEISHU_ALPHA_UPDATES_BASE": "alpha-updates-base",
        "FEISHU_ALPHA_UPDATES_TABLE": "alpha-updates-table",
        "FEISHU_ALPHA_METRICS_BASE": "alpha-metrics-base",
        "FEISHU_ALPHA_METRICS_TABLE": "alpha-metrics-table",
    }


def write_project(root: Path, name: str, contents: str) -> None:
    directory = root / "projects"
    directory.mkdir(exist_ok=True)
    (directory / f"{name}.yaml").write_text(contents, encoding="utf-8")


def test_load_projects_resolves_secret_references_and_ids(tmp_path: Path) -> None:
    write_project(tmp_path, "alpha", project_yaml())

    [config] = load_projects(tmp_path, ["alpha"], secrets())

    assert config.slug == "alpha"
    assert config.brand_name == "Alpha"
    assert config.discord.token == "alpha-token"
    assert config.discord.guild_id == 101
    assert config.channels.roles == 606
    assert config.role_selector is not None
    assert config.role_selector.options[0].role_id == 202
    assert config.auto_reactions[0].channel_id == 303
    assert config.feishu is not None
    assert config.feishu.metrics_table_id == "alpha-metrics-table"


def test_load_projects_allows_legacy_name_based_role_selector(tmp_path: Path) -> None:
    contents = (
        project_yaml()
        .replace('  roles: "606"', '  roles_name: "🔔roles"')
        .replace('      role_id: "202"', '      role_name: "Updates"')
    )
    write_project(tmp_path, "alpha", contents)

    [config] = load_projects(tmp_path, ["alpha"], secrets())

    assert config.channels.roles is None
    assert config.channels.roles_name == "🔔roles"
    assert config.role_selector is not None
    assert config.role_selector.options[0].role_id is None
    assert config.role_selector.options[0].role_name == "Updates"


def test_load_projects_rejects_duplicate_guild_ids(tmp_path: Path) -> None:
    write_project(tmp_path, "alpha", project_yaml(slug="alpha", guild_id="101"))
    write_project(
        tmp_path,
        "beta",
        project_yaml(slug="beta", guild_id="101", token_env="DISCORD_TOKEN_BETA"),
    )

    with pytest.raises(
        ConfigError,
        match="Discord guild ID 101 is used by alpha and beta",
    ):
        load_projects(tmp_path, ["alpha", "beta"], secrets())


def test_load_projects_rejects_missing_feature_dependency(tmp_path: Path) -> None:
    write_project(
        tmp_path,
        "alpha",
        project_yaml(include_role_selector=False).replace(
            "  role_selector: false", "  role_selector: true"
        ),
    )

    with pytest.raises(ConfigError, match="role_selector configuration is required"):
        load_projects(tmp_path, ["alpha"], secrets())


def test_load_projects_rejects_missing_secret_value(tmp_path: Path) -> None:
    write_project(tmp_path, "alpha", project_yaml())
    environment = secrets()
    del environment["FEISHU_ALPHA_APP_SECRET"]

    with pytest.raises(ConfigError, match="FEISHU_ALPHA_APP_SECRET is not set"):
        load_projects(tmp_path, ["alpha"], environment)


def test_load_projects_requires_embed_admin_and_channel_allowlist(tmp_path: Path) -> None:
    write_project(
        tmp_path,
        "alpha",
        project_yaml().replace('  admin_role_ids: ["404"]', "  admin_role_ids: []"),
    )

    with pytest.raises(ConfigError, match="admin_role_ids must not be empty"):
        load_projects(tmp_path, ["alpha"], secrets())


def test_enabled_project_slugs_rejects_empty_and_duplicate_values() -> None:
    with pytest.raises(ConfigError, match="must name at least one project"):
        enabled_project_slugs({})

    with pytest.raises(ConfigError, match="contains a duplicate project slug"):
        enabled_project_slugs({"ENABLED_PROJECTS": "alpha, alpha"})


def test_fortunepurple_config_preserves_the_existing_project_setup() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    environment = {
        "TOKEN": "fortune-token",
        "FEISHU_APP_ID": "feishu-app-id",
        "FEISHU_APP_SECRET": "feishu-app-secret",
        "FEISHU_UPDATES_BASE_APP_TOKEN": "updates-base",
        "FEISHU_UPDATES_TABLE_ID": "updates-table",
        "FEISHU_METRICS_BASE_APP_TOKEN": "metrics-base",
        "FEISHU_METRICS_TABLE_ID": "metrics-table",
    }

    [config] = load_projects(repo_root, ["fortunepurple"], environment)

    assert config.discord.guild_id == 1498581314495053834
    assert config.discord.manual_embed_channel_ids == ()
    assert config.channels.roles_name == "🔔roles"
    assert config.channels.daily_updates == 1501874966940094687
    assert config.role_selector is not None
    assert config.role_selector.adopt_custom_ids == ("subscription_role_select",)
    assert config.auto_reactions[0].mode == "random"
    assert config.auto_reactions[0].random_count == 10
