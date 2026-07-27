import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from cogs import activities


def campaign(*, status: str = "active", questions: list[dict] | None = None) -> dict:
    return {
        "id": "campaign-1",
        "status": status,
        "ends_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "modal_title": "FP Player Survey",
        "winner_message": "Winner: **{code}**",
        "sold_out_message": "All gone.",
        "closed_message": "This activity has ended.",
        "questions": questions
        if questions is not None
        else [
            {
                "field_key": "discord_username",
                "label": "Discord Username",
                "input_style": "short",
                "required": True,
                "placeholder": "Your username",
                "min_length": 1,
                "max_length": 100,
                "prefill_discord_username": True,
                "is_participant_key": False,
            },
            {
                "field_key": "fp_id",
                "label": "FortunePurple ID",
                "input_style": "short",
                "required": True,
                "placeholder": "Your ID",
                "min_length": 1,
                "max_length": 100,
                "prefill_discord_username": False,
                "is_participant_key": True,
            },
            {
                "field_key": "favorite_game",
                "label": "Favorite FP Game",
                "input_style": "paragraph",
                "required": True,
                "placeholder": "Your favorite",
                "min_length": 1,
                "max_length": 400,
                "prefill_discord_username": False,
                "is_participant_key": False,
            },
        ],
    }


def interaction(*, message_id: int = 999) -> SimpleNamespace:
    return SimpleNamespace(
        message=SimpleNamespace(id=message_id),
        user=SimpleNamespace(id=1234, name="real_username"),
        response=SimpleNamespace(
            send_modal=AsyncMock(),
            send_message=AsyncMock(),
            defer=AsyncMock(),
        ),
        edit_original_response=AsyncMock(),
    )


def set_modal_answers(modal: activities.ActivityModal, values: dict[str, str]) -> None:
    for field_key, item in modal.inputs.items():
        item._value = values[field_key]


def test_activity_modal_builds_dynamic_fields_and_prefills_username():
    modal = activities.ActivityModal(campaign(), discord_username="real_username")

    assert modal.title == "FP Player Survey"
    assert list(modal.inputs) == ["discord_username", "fp_id", "favorite_game"]
    assert modal.inputs["discord_username"].default == "real_username"
    assert modal.inputs["favorite_game"].style is discord.TextStyle.paragraph
    assert modal.inputs["fp_id"].required is True


def test_activity_modal_truncates_prefill_to_configured_max_length():
    configured = campaign()
    configured["questions"][0]["max_length"] = 4

    modal = activities.ActivityModal(
        configured, discord_username="long_username"
    )

    assert modal.inputs["discord_username"].default == "long"


@pytest.mark.parametrize("count", [1, 5])
def test_activity_modal_accepts_discord_question_boundaries(count):
    dynamic_questions = [
        {
            "field_key": f"field_{index}",
            "label": f"Field {index}",
            "input_style": "short",
            "required": True,
            "placeholder": None,
            "min_length": 0,
            "max_length": 100,
            "prefill_discord_username": False,
            "is_participant_key": False,
        }
        for index in range(count)
    ]

    modal = activities.ActivityModal(
        campaign(questions=dynamic_questions), discord_username="player"
    )

    assert len(modal.inputs) == count
    assert all(item.style is discord.TextStyle.short for item in modal.inputs.values())


def test_activity_modal_rejects_question_counts_outside_discord_limits():
    with pytest.raises(ValueError, match="1 to 5"):
        activities.ActivityModal(campaign(questions=[]), discord_username="player")

    too_many = [
        {
            "field_key": f"field_{index}",
            "label": f"Field {index}",
            "input_style": "short",
            "required": True,
            "placeholder": None,
            "min_length": 0,
            "max_length": 100,
            "prefill_discord_username": False,
            "is_participant_key": False,
        }
        for index in range(6)
    ]
    with pytest.raises(ValueError, match="1 to 5"):
        activities.ActivityModal(
            campaign(questions=too_many), discord_username="player"
        )


def test_activity_view_registers_persistent_join_button():
    view = activities.ActivityView()
    assert view.timeout is None
    assert len(view.children) == 1
    assert view.children[0].custom_id == "activity_join"


def test_join_button_loads_campaign_and_opens_modal(monkeypatch):
    monkeypatch.setattr(
        activities, "aget_activity_by_message", AsyncMock(return_value=campaign())
    )
    button = activities.ActivityJoinButton()
    ctx = interaction()

    asyncio.run(button.callback(ctx))

    activities.aget_activity_by_message.assert_awaited_once_with("999")
    ctx.response.send_modal.assert_awaited_once()
    modal = ctx.response.send_modal.await_args.args[0]
    assert isinstance(modal, activities.ActivityModal)
    assert modal.inputs["discord_username"].default == "real_username"


def test_join_button_returns_closed_copy_without_opening_modal(monkeypatch):
    monkeypatch.setattr(
        activities,
        "aget_activity_by_message",
        AsyncMock(return_value=campaign(status="closed")),
    )
    ctx = interaction()

    asyncio.run(activities.ActivityJoinButton().callback(ctx))

    ctx.response.send_message.assert_awaited_once_with(
        "This activity has ended.", ephemeral=True
    )
    ctx.response.send_modal.assert_not_awaited()


def test_join_button_returns_closed_copy_when_activity_has_expired(monkeypatch):
    expired = campaign()
    expired["ends_at"] = (
        datetime.now(timezone.utc) - timedelta(seconds=1)
    ).isoformat()
    monkeypatch.setattr(
        activities,
        "aget_activity_by_message",
        AsyncMock(return_value=expired),
    )
    ctx = interaction()

    asyncio.run(activities.ActivityJoinButton().callback(ctx))

    ctx.response.send_message.assert_awaited_once_with(
        "This activity has ended.", ephemeral=True
    )
    ctx.response.send_modal.assert_not_awaited()


def test_join_button_times_out_with_ephemeral_retry(monkeypatch):
    async def slow_load(_message_id):
        await asyncio.sleep(0.05)

    monkeypatch.setattr(activities, "ACTIVITY_LOAD_TIMEOUT", 0.001)
    monkeypatch.setattr(activities, "aget_activity_by_message", slow_load)
    ctx = interaction()

    asyncio.run(activities.ActivityJoinButton().callback(ctx))

    ctx.response.send_message.assert_awaited_once_with(
        activities.TEMPORARY_ERROR_MESSAGE, ephemeral=True
    )


@pytest.mark.parametrize(
    ("rpc_result", "expected"),
    [
        ({"outcome": "winner", "reward_code": "A*1"}, "Winner: **A\\*1**"),
        (
            {"outcome": "existing_winner", "reward_code": "A*1"},
            "Winner: **A\\*1**",
        ),
        ({"outcome": "sold_out", "reward_code": None}, "All gone."),
        ({"outcome": "existing_sold_out", "reward_code": None}, "All gone."),
        (
            {"outcome": "participant_key_taken", "reward_code": None},
            activities.PARTICIPANT_KEY_TAKEN_MESSAGE,
        ),
        ({"outcome": "closed", "reward_code": None}, "This activity has ended."),
    ],
)
def test_modal_submission_maps_every_rpc_outcome(monkeypatch, rpc_result, expected):
    claim = AsyncMock(return_value=rpc_result)
    monkeypatch.setattr(activities, "aclaim_activity_reward", claim)
    modal = activities.ActivityModal(campaign(), discord_username="real_username")
    set_modal_answers(
        modal,
        {
            "discord_username": "chosen_name",
            "fp_id": " FP 123 ",
            "favorite_game": "Lucky Penny",
        },
    )
    ctx = interaction()

    asyncio.run(modal.on_submit(ctx))

    ctx.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
    claim.assert_awaited_once_with(
        campaign_id="campaign-1",
        discord_user_id="1234",
        discord_username="real_username",
        answers={
            "discord_username": "chosen_name",
            "fp_id": "FP 123",
            "favorite_game": "Lucky Penny",
        },
        participant_key="fp123",
    )
    ctx.edit_original_response.assert_awaited_once_with(content=expected)


def test_modal_submission_handles_database_exception(monkeypatch):
    monkeypatch.setattr(
        activities,
        "aclaim_activity_reward",
        AsyncMock(side_effect=RuntimeError("database unavailable")),
    )
    modal = activities.ActivityModal(campaign(), discord_username="real_username")
    set_modal_answers(
        modal,
        {
            "discord_username": "chosen_name",
            "fp_id": "FP123",
            "favorite_game": "Lucky Penny",
        },
    )
    ctx = interaction()

    asyncio.run(modal.on_submit(ctx))

    ctx.edit_original_response.assert_awaited_once_with(
        content=activities.TEMPORARY_ERROR_MESSAGE
    )


def test_activities_cog_registers_persistent_view():
    bot = MagicMock()

    activities.ActivitiesCog(bot)

    bot.add_view.assert_called_once()
    assert isinstance(bot.add_view.call_args.args[0], activities.ActivityView)


def test_activity_database_calls_use_a_bounded_dedicated_executor():
    assert activities.ACTIVITY_DB_MAX_WORKERS <= 4
