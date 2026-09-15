from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.cogs.role_selector import RoleSelectorView, handle_selection, selector_custom_ids
from app.core.config import (
    ChannelConfig,
    DiscordConfig,
    FeatureFlags,
    ProjectConfig,
    RoleOption,
    RoleSelectorConfig,
)
from app.core.runtime import ProjectRuntime
from app.core.state import ProjectState


def runtime() -> ProjectRuntime:
    config = ProjectConfig(
        slug="alpha",
        brand_name="Alpha",
        discord=DiscordConfig("token", 101, (), ()),
        features=FeatureFlags(False, True, False, False, False, False),
        channels=ChannelConfig(600, None, None, None),
        role_selector=RoleSelectorConfig(
            title="Choose roles",
            description="Subscribe to alerts.",
            options=(RoleOption("Updates", 700, "Product news"),),
        ),
        auto_reactions=(),
        feishu=None,
    )
    return ProjectRuntime(config, SimpleNamespace(), ProjectState(Path("/tmp"), "alpha"), None)


def test_persistent_selector_uses_a_project_scoped_custom_id() -> None:
    view = RoleSelectorView(runtime())

    assert view.children[0].custom_id == "roles:alpha"
    assert view.children[0].options[0].value == "700"


def test_selector_uses_a_name_value_for_legacy_role_configuration() -> None:
    active = runtime()
    active = ProjectRuntime(
        replace(
            active.config,
            channels=replace(active.config.channels, roles=None, roles_name="🔔roles"),
            role_selector=RoleSelectorConfig(
                title="Choose roles",
                description="Subscribe to alerts.",
                options=(RoleOption("Updates", None, "Product news", role_name="Updates"),),
            ),
        ),
        active.bot,
        active.state,
        active.feishu,
    )

    view = RoleSelectorView(active)

    assert view.children[0].options[0].value == "name:Updates"


def test_selector_adopts_only_the_configured_legacy_component_ids() -> None:
    active = runtime()
    active = ProjectRuntime(
        replace(
            active.config,
            role_selector=RoleSelectorConfig(
                title="Choose roles",
                description="Subscribe to alerts.",
                options=(RoleOption("Updates", 700, "Product news"),),
                adopt_custom_ids=("legacy-role-select",),
            ),
        ),
        active.bot,
        active.state,
        active.feishu,
    )

    assert selector_custom_ids(active) == {"roles:alpha", "legacy-role-select"}


@pytest.mark.asyncio
async def test_existing_role_is_removed() -> None:
    selected_role = SimpleNamespace(id=700, name="Updates")
    member = SimpleNamespace(roles=[selected_role], remove_roles=AsyncMock(), add_roles=AsyncMock())
    interaction = SimpleNamespace(
        user=member,
        guild=SimpleNamespace(get_role=lambda role_id: selected_role if role_id == 700 else None),
        followup=SimpleNamespace(send=AsyncMock()),
    )

    await handle_selection(runtime(), interaction, 700)

    member.remove_roles.assert_awaited_once_with(selected_role, reason="notification role opt-out")
    interaction.followup.send.assert_awaited_once_with(
        "Unsubscribed from **Updates**.", ephemeral=True
    )


@pytest.mark.asyncio
async def test_selector_callback_renders_a_fresh_view_before_handling_selection() -> None:
    active = runtime()
    selected_role = SimpleNamespace(id=700, name="Updates")
    member = SimpleNamespace(roles=[selected_role], remove_roles=AsyncMock(), add_roles=AsyncMock())
    interaction = SimpleNamespace(
        user=member,
        guild=SimpleNamespace(get_role=lambda role_id: selected_role if role_id == 700 else None),
        response=SimpleNamespace(defer=AsyncMock(), edit_message=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    view = RoleSelectorView(active)
    select = view.children[0]
    select._values = ["700"]

    await select.callback(interaction)

    interaction.response.edit_message.assert_awaited_once()
    refreshed_view = interaction.response.edit_message.await_args.kwargs["view"]
    assert isinstance(refreshed_view, RoleSelectorView)
    interaction.followup.send.assert_awaited_once_with(
        "Unsubscribed from **Updates**.", ephemeral=True
    )


@pytest.mark.asyncio
async def test_missing_configured_role_returns_private_error() -> None:
    member = SimpleNamespace(roles=[], remove_roles=AsyncMock(), add_roles=AsyncMock())
    interaction = SimpleNamespace(
        user=member,
        guild=SimpleNamespace(get_role=lambda _: None),
        followup=SimpleNamespace(send=AsyncMock()),
    )

    await handle_selection(runtime(), interaction, 700)

    interaction.followup.send.assert_awaited_once_with(
        "This notification role is unavailable. Please contact an admin.",
        ephemeral=True,
    )


@pytest.mark.asyncio
async def test_legacy_named_role_is_resolved_before_subscription() -> None:
    active = runtime()
    active = ProjectRuntime(
        replace(
            active.config,
            role_selector=RoleSelectorConfig(
                title="Choose roles",
                description="Subscribe to alerts.",
                options=(RoleOption("Updates", None, "Product news", role_name="Updates"),),
            ),
        ),
        active.bot,
        active.state,
        active.feishu,
    )
    selected_role = SimpleNamespace(id=700, name="Updates")
    member = SimpleNamespace(roles=[], remove_roles=AsyncMock(), add_roles=AsyncMock())
    interaction = SimpleNamespace(
        user=member,
        guild=SimpleNamespace(roles=[selected_role]),
        followup=SimpleNamespace(send=AsyncMock()),
    )

    await handle_selection(active, interaction, "name:Updates")

    member.add_roles.assert_awaited_once_with(selected_role, reason="notification role opt-in")
