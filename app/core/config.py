from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml


class ConfigError(ValueError):
    """Raised when a project configuration cannot safely be started."""


@dataclass(frozen=True)
class DiscordConfig:
    token: str
    guild_id: int
    admin_role_ids: tuple[int, ...]
    manual_embed_channel_ids: tuple[int, ...]


@dataclass(frozen=True)
class FeatureFlags:
    manual_embed: bool
    role_selector: bool
    auto_reaction: bool
    exclusive_updates_reaction: bool
    daily_updates: bool
    community_metrics: bool


@dataclass(frozen=True)
class ChannelConfig:
    roles: int | None
    exclusive_updates: int | None
    daily_updates: int | None
    staff_alerts: int | None


@dataclass(frozen=True)
class RoleOption:
    label: str
    role_id: int
    description: str


@dataclass(frozen=True)
class RoleSelectorConfig:
    title: str
    description: str
    options: tuple[RoleOption, ...]


@dataclass(frozen=True)
class ReactionRule:
    channel_id: int
    emojis: tuple[str, ...]
    include_bot_messages: bool


@dataclass(frozen=True)
class FeishuConfig:
    app_id: str
    app_secret: str
    updates_base_id: str
    updates_table_id: str
    metrics_base_id: str
    metrics_table_id: str


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


def enabled_project_slugs(environ: Mapping[str, str]) -> tuple[str, ...]:
    slugs = tuple(
        value.strip()
        for value in environ.get("ENABLED_PROJECTS", "").split(",")
        if value.strip()
    )
    if not slugs:
        raise ConfigError("ENABLED_PROJECTS must name at least one project")
    if len(set(slugs)) != len(slugs):
        raise ConfigError("ENABLED_PROJECTS contains a duplicate project slug")
    return slugs


def _mapping(value: object, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigError(f"{path} must be an object")
    return value


def _text(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{path} must be a non-empty string")
    return value.strip()


def _bool(value: object, path: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(f"{path} must be true or false")
    return value


def require_positive_id(value: object, path: str) -> int:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{path} must be a positive Discord ID") from exc
    if parsed <= 0:
        raise ConfigError(f"{path} must be a positive Discord ID")
    return parsed


def _optional_id(mapping: Mapping[str, Any], key: str, path: str) -> int | None:
    value = mapping.get(key)
    if value is None or value == "":
        return None
    return require_positive_id(value, f"{path}.{key}")


def _id_list(value: object, path: str) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise ConfigError(f"{path} must be a list")
    ids = tuple(require_positive_id(item, path) for item in value)
    if len(set(ids)) != len(ids):
        raise ConfigError(f"{path} contains a duplicate Discord ID")
    return ids


def _resolve_secret(environ: Mapping[str, str], variable_name: object) -> str:
    name = _text(variable_name, "secret environment variable reference")
    value = environ.get(name, "").strip()
    if not value:
        raise ConfigError(f"{name} is not set")
    return value


def _parse_features(raw: Mapping[str, Any]) -> FeatureFlags:
    return FeatureFlags(
        manual_embed=_bool(raw.get("manual_embed"), "features.manual_embed"),
        role_selector=_bool(raw.get("role_selector"), "features.role_selector"),
        auto_reaction=_bool(raw.get("auto_reaction"), "features.auto_reaction"),
        exclusive_updates_reaction=_bool(
            raw.get("exclusive_updates_reaction"),
            "features.exclusive_updates_reaction",
        ),
        daily_updates=_bool(raw.get("daily_updates"), "features.daily_updates"),
        community_metrics=_bool(
            raw.get("community_metrics"), "features.community_metrics"
        ),
    )


def _parse_role_selector(raw: object) -> RoleSelectorConfig:
    section = _mapping(raw, "role_selector")
    options_raw = section.get("options")
    if not isinstance(options_raw, list) or not options_raw:
        raise ConfigError("role_selector.options must be a non-empty list")
    options: list[RoleOption] = []
    seen_role_ids: set[int] = set()
    for index, item in enumerate(options_raw):
        option = _mapping(item, f"role_selector.options[{index}]")
        role_id = require_positive_id(
            option.get("role_id"), f"role_selector.options[{index}].role_id"
        )
        if role_id in seen_role_ids:
            raise ConfigError("role_selector.options contains a duplicate role_id")
        seen_role_ids.add(role_id)
        options.append(
            RoleOption(
                label=_text(option.get("label"), f"role_selector.options[{index}].label"),
                role_id=role_id,
                description=_text(
                    option.get("description"),
                    f"role_selector.options[{index}].description",
                ),
            )
        )
    return RoleSelectorConfig(
        title=_text(section.get("title"), "role_selector.title"),
        description=str(section.get("description") or ""),
        options=tuple(options),
    )


def _parse_reactions(raw: object) -> tuple[ReactionRule, ...]:
    if not isinstance(raw, list) or not raw:
        raise ConfigError("auto_reactions must be a non-empty list")
    rules: list[ReactionRule] = []
    for index, item in enumerate(raw):
        rule = _mapping(item, f"auto_reactions[{index}]")
        emojis = rule.get("emojis")
        if not isinstance(emojis, list) or not emojis:
            raise ConfigError(f"auto_reactions[{index}].emojis must be a non-empty list")
        parsed_emojis = tuple(_text(emoji, f"auto_reactions[{index}].emojis") for emoji in emojis)
        rules.append(
            ReactionRule(
                channel_id=require_positive_id(
                    rule.get("channel_id"), f"auto_reactions[{index}].channel_id"
                ),
                emojis=parsed_emojis,
                include_bot_messages=_bool(
                    rule.get("include_bot_messages", False),
                    f"auto_reactions[{index}].include_bot_messages",
                ),
            )
        )
    return tuple(rules)


def _parse_feishu(raw: object, environ: Mapping[str, str]) -> FeishuConfig:
    section = _mapping(raw, "feishu")
    return FeishuConfig(
        app_id=_resolve_secret(environ, section.get("app_id_env")),
        app_secret=_resolve_secret(environ, section.get("app_secret_env")),
        updates_base_id=_resolve_secret(environ, section.get("updates_base_env")),
        updates_table_id=_resolve_secret(environ, section.get("updates_table_env")),
        metrics_base_id=_resolve_secret(environ, section.get("metrics_base_env")),
        metrics_table_id=_resolve_secret(environ, section.get("metrics_table_env")),
    )


def _load_project(path: Path, expected_slug: str, environ: Mapping[str, str]) -> ProjectConfig:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"cannot read project config {path.name}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {path.name}: {exc}") from exc
    config = _mapping(raw, path.name)
    project = _mapping(config.get("project"), "project")
    slug = _text(project.get("slug"), "project.slug")
    if slug != expected_slug:
        raise ConfigError(
            f"project.slug {slug!r} does not match requested project {expected_slug!r}"
        )

    discord = _mapping(config.get("discord"), "discord")
    features = _parse_features(_mapping(config.get("features"), "features"))
    channels_raw = _mapping(config.get("channels"), "channels")
    channels = ChannelConfig(
        roles=_optional_id(channels_raw, "roles", "channels"),
        exclusive_updates=_optional_id(channels_raw, "exclusive_updates", "channels"),
        daily_updates=_optional_id(channels_raw, "daily_updates", "channels"),
        staff_alerts=_optional_id(channels_raw, "staff_alerts", "channels"),
    )
    if features.role_selector and "role_selector" not in config:
        raise ConfigError("role_selector configuration is required")
    role_selector = (
        _parse_role_selector(config.get("role_selector"))
        if features.role_selector
        else None
    )
    if features.role_selector and channels.roles is None:
        raise ConfigError("channels.roles is required when role_selector is enabled")

    reactions_enabled = features.auto_reaction or features.exclusive_updates_reaction
    auto_reactions = _parse_reactions(config.get("auto_reactions")) if reactions_enabled else ()
    if features.exclusive_updates_reaction and channels.exclusive_updates is None:
        raise ConfigError(
            "channels.exclusive_updates is required when exclusive_updates_reaction is enabled"
        )

    feishu_enabled = features.daily_updates or features.community_metrics
    feishu = _parse_feishu(config.get("feishu"), environ) if feishu_enabled else None
    if features.daily_updates and channels.daily_updates is None:
        raise ConfigError("channels.daily_updates is required when daily_updates is enabled")

    discord_config = DiscordConfig(
        token=_resolve_secret(environ, discord.get("token_env")),
        guild_id=require_positive_id(discord.get("guild_id"), "discord.guild_id"),
        admin_role_ids=_id_list(discord.get("admin_role_ids", []), "discord.admin_role_ids"),
        manual_embed_channel_ids=_id_list(
            discord.get("manual_embed_channel_ids", []),
            "discord.manual_embed_channel_ids",
        ),
    )
    if features.manual_embed and not discord_config.admin_role_ids:
        raise ConfigError("discord.admin_role_ids must not be empty when manual_embed is enabled")
    if features.manual_embed and not discord_config.manual_embed_channel_ids:
        raise ConfigError(
            "discord.manual_embed_channel_ids must not be empty when manual_embed is enabled"
        )

    return ProjectConfig(
        slug=slug,
        brand_name=_text(project.get("brand_name"), "project.brand_name"),
        discord=discord_config,
        features=features,
        channels=channels,
        role_selector=role_selector,
        auto_reactions=auto_reactions,
        feishu=feishu,
    )


def load_projects(
    repo_root: Path,
    enabled_slugs: Sequence[str],
    environ: Mapping[str, str],
) -> list[ProjectConfig]:
    configs = [
        _load_project(repo_root / "projects" / f"{slug}.yaml", slug, environ)
        for slug in enabled_slugs
    ]
    seen_guilds: dict[int, str] = {}
    seen_tokens: dict[str, str] = {}
    for config in configs:
        previous_guild = seen_guilds.get(config.discord.guild_id)
        if previous_guild:
            raise ConfigError(
                f"Discord guild ID {config.discord.guild_id} is used by "
                f"{previous_guild} and {config.slug}"
            )
        seen_guilds[config.discord.guild_id] = config.slug
        previous_token = seen_tokens.get(config.discord.token)
        if previous_token:
            raise ConfigError(
                f"Discord token environment value is used by {previous_token} and {config.slug}"
            )
        seen_tokens[config.discord.token] = config.slug
    return configs
