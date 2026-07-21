import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord

from cogs import roles


def test_subscription_select_resets_through_interaction_response(monkeypatch):
    events: list[str] = []
    options = [
        discord.SelectOption(
            label="🎉Lucky Drops",
            value="🎉Lucky Drops",
            description="Access exclusive events and rewards",
        )
    ]
    select = roles.SubscriptionSelect(options)
    select._values = ["🎉Lucky Drops"]

    async def edit_message(**kwargs):
        events.append("reset")
        assert isinstance(kwargs["view"], roles.RoleView)

    async def handle_role(interaction, selected):
        events.append("toggle")
        assert selected == "🎉Lucky Drops"

    monkeypatch.setattr(roles, "handle_role", handle_role)
    monkeypatch.setattr(roles, "_build_options", AsyncMock(return_value=options))

    interactions = []
    for _ in range(2):
        interaction = SimpleNamespace(
            response=SimpleNamespace(
                defer=AsyncMock(),
                edit_message=AsyncMock(side_effect=edit_message),
            ),
            edit_original_response=AsyncMock(),
            message=SimpleNamespace(edit=AsyncMock()),
        )
        interactions.append(interaction)
        asyncio.run(select.callback(interaction))

    assert events == ["reset", "toggle", "reset", "toggle"]
    for interaction in interactions:
        interaction.response.edit_message.assert_awaited_once()
        interaction.response.defer.assert_not_awaited()
        interaction.edit_original_response.assert_not_awaited()
        interaction.message.edit.assert_not_awaited()


def test_subscription_select_refreshes_changed_database_options(monkeypatch):
    current = [discord.SelectOption(label="Role A", value="Role A")]
    fresh = [
        discord.SelectOption(label="Role A", value="Role A"),
        discord.SelectOption(label="Role B", value="Role B"),
    ]
    select = roles.SubscriptionSelect(current)
    select._values = ["Role A"]
    interaction = SimpleNamespace(
        response=SimpleNamespace(edit_message=AsyncMock()),
        edit_original_response=AsyncMock(),
    )
    monkeypatch.setattr(roles, "handle_role", AsyncMock())
    monkeypatch.setattr(roles, "_build_options", AsyncMock(return_value=fresh))

    asyncio.run(select.callback(interaction))

    interaction.response.edit_message.assert_awaited_once()
    interaction.edit_original_response.assert_awaited_once()
    refreshed_view = interaction.edit_original_response.await_args.kwargs["view"]
    assert [option.label for option in refreshed_view.children[0].options] == [
        "Role A",
        "Role B",
    ]


def test_handle_role_subscribes_then_unsubscribes(monkeypatch):
    role = SimpleNamespace(name="🎉Lucky Drops")

    class Member:
        def __init__(self):
            self.id = 123
            self.roles = []

        async def add_roles(self, added_role):
            self.roles.append(added_role)

        async def remove_roles(self, removed_role):
            self.roles.remove(removed_role)

    member = Member()
    interaction = SimpleNamespace(
        user=member,
        guild=SimpleNamespace(roles=[role]),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    metric = AsyncMock()
    monkeypatch.setattr(roles, "record_metric_event", metric)

    asyncio.run(roles.handle_role(interaction, role.name))
    assert member.roles == [role]

    asyncio.run(roles.handle_role(interaction, role.name))
    assert member.roles == []
    assert "Subscribed" in interaction.followup.send.await_args_list[0].kwargs["content"]
    assert "Unsubscribed" in interaction.followup.send.await_args_list[1].kwargs["content"]
    assert all(call.kwargs["ephemeral"] for call in interaction.followup.send.await_args_list)
    metric.assert_awaited_once_with("role_subscribe", member_id=123, role=role.name)
