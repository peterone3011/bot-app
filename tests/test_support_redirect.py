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
