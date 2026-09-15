from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.cogs.role_selector import RoleSelectorView, handle_selection
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
