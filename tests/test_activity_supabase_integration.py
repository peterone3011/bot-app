from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import os
import uuid
from urllib.request import Request, urlopen

import pytest


SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
RUN_INTEGRATION = os.getenv("RUN_SUPABASE_INTEGRATION") == "1"

pytestmark = pytest.mark.skipif(
    not (RUN_INTEGRATION and SUPABASE_URL and SUPABASE_SERVICE_KEY),
    reason="set RUN_SUPABASE_INTEGRATION=1 and Supabase service credentials",
)


def api(method: str, path: str, payload=None, *, prefer: str | None = None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "apikey": SUPABASE_SERVICE_KEY,
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    request = Request(
        f"{SUPABASE_URL}/rest/v1/{path}",
        data=body,
        headers=headers,
        method=method,
    )
    with urlopen(request, timeout=20) as response:
        content = response.read()
    return json.loads(content) if content else None


def create_campaign(limit: int) -> tuple[str, list[str]]:
    campaign_id = str(uuid.uuid4())
    message_id = str(uuid.uuid4().int)[:18]
    codes = [f"TEST-{campaign_id}-{index:02d}" for index in range(1, limit + 1)]
    try:
        api(
            "POST",
            "activity_campaigns",
            {
                "id": campaign_id,
                "name": f"Integration {campaign_id}",
                "status": "active",
                "winner_limit": limit,
                "discord_guild_id": "1",
                "discord_channel_id": "2",
                "discord_message_id": message_id,
                "ends_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                "winner_message": "Winner {code}",
                "sold_out_message": "Sold out",
                "closed_message": "Closed",
            },
        )
        api(
            "POST",
            "activity_codes",
            [
                {"campaign_id": campaign_id, "position": index, "code": code}
                for index, code in enumerate(codes, start=1)
            ],
        )
    except Exception:
        try:
            delete_campaign(campaign_id)
        except Exception:
            pass
        raise
    return campaign_id, codes


def claim(
    campaign_id: str,
    index: int,
    *,
    discord_id: str | None = None,
    key: str | None = None,
    username: str | None = None,
):
    participant_key = key or f"fp-{index}"
    return api(
        "POST",
        "rpc/claim_activity_reward",
        {
            "p_campaign_id": campaign_id,
            "p_discord_user_id": discord_id or str(900000 + index),
            "p_discord_username": username or f"player-{index}",
            "p_answers": {"fp_id": participant_key},
            "p_participant_key": participant_key,
        },
    )[0]


def delete_campaign(campaign_id: str) -> None:
    api("DELETE", f"activity_campaigns?id=eq.{campaign_id}")


def test_concurrent_claims_are_unique_ordered_and_the_21st_is_sold_out():
    campaign_id, expected_codes = create_campaign(20)
    try:
        with ThreadPoolExecutor(max_workers=25) as executor:
            results = list(
                executor.map(lambda index: claim(campaign_id, index), range(1, 26))
            )

        winners = [row for row in results if row["outcome"] == "winner"]
        sold_out = [row for row in results if row["outcome"] == "sold_out"]
        awarded = [row["reward_code"] for row in winners]
        assert len(winners) == 20
        assert len(sold_out) == 5
        assert len(set(awarded)) == 20
        assert set(awarded) == set(expected_codes)
    finally:
        delete_campaign(campaign_id)


def test_concurrent_duplicate_discord_user_recovers_one_original_code():
    campaign_id, expected_codes = create_campaign(1)
    try:
        with ThreadPoolExecutor(max_workers=10) as executor:
            results = list(
                executor.map(
                    lambda index: claim(
                        campaign_id,
                        index,
                        discord_id="999999999",
                        key="same-fp-id",
                    ),
                    range(10),
                )
            )

        outcomes = [row["outcome"] for row in results]
        assert outcomes.count("winner") == 1
        assert outcomes.count("existing_winner") == 9
        assert {row["reward_code"] for row in results} == {expected_codes[0]}
    finally:
        delete_campaign(campaign_id)


def test_concurrent_duplicate_participant_key_is_rejected():
    campaign_id, _ = create_campaign(2)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    lambda index: claim(campaign_id, index, key="shared-fp-id"),
                    (1, 2),
                )
            )

        assert sorted(row["outcome"] for row in results) == [
            "participant_key_taken",
            "winner",
        ]
    finally:
        delete_campaign(campaign_id)


def test_repeat_submission_updates_answers_but_expiry_blocks_further_updates():
    campaign_id, expected_codes = create_campaign(1)
    try:
        first = claim(
            campaign_id,
            1,
            discord_id="777777777",
            key="first-fp",
            username="first-name",
        )
        assert first == {"outcome": "winner", "reward_code": expected_codes[0]}
        before = api(
            "GET",
            "activity_submissions"
            f"?campaign_id=eq.{campaign_id}&discord_user_id=eq.777777777",
        )[0]

        repeated = claim(
            campaign_id,
            2,
            discord_id="777777777",
            key="latest-fp",
            username="latest-name",
        )
        assert repeated == {
            "outcome": "existing_winner",
            "reward_code": expected_codes[0],
        }
        latest = api(
            "GET",
            "activity_submissions"
            f"?campaign_id=eq.{campaign_id}&discord_user_id=eq.777777777",
        )[0]
        assert latest["discord_username"] == "latest-name"
        assert latest["answers"] == {"fp_id": "latest-fp"}
        assert latest["participant_key_normalized"] == "latest-fp"
        assert latest["submitted_at"] == before["submitted_at"]

        api(
            "PATCH",
            f"activity_campaigns?id=eq.{campaign_id}",
            {"ends_at": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()},
        )
        expired = claim(
            campaign_id,
            3,
            discord_id="777777777",
            key="must-not-update",
            username="must-not-update",
        )
        assert expired == {"outcome": "closed", "reward_code": None}
        after_expiry = api(
            "GET",
            "activity_submissions"
            f"?campaign_id=eq.{campaign_id}&discord_user_id=eq.777777777",
        )[0]
        assert after_expiry["discord_username"] == "latest-name"
        assert after_expiry["answers"] == {"fp_id": "latest-fp"}
    finally:
        delete_campaign(campaign_id)
