import datetime
from types import SimpleNamespace

import cogs.screenshot_activity as sa


def test_is_available_status_allows_blank_and_available_labels():
    assert sa._is_available_status("") is True
    assert sa._is_available_status(None) is True
    assert sa._is_available_status("available") is True
    assert sa._is_available_status("可用") is True
    assert sa._is_available_status("sent") is False


def test_find_existing_claim_checks_reserved_sent_and_failed():
    values = [
        ["code", "status", "discord id"],
        ["A", "available", ""],
        ["B", "reserved", "123"],
        ["C", "sent", "456"],
        ["D", "dm_failed", "789"],
    ]
    assert sa._find_existing_claim(values, 123) == 3
    assert sa._find_existing_claim(values, 456) == 4
    assert sa._find_existing_claim(values, 789) == 5
    assert sa._find_existing_claim(values, 999) is None


def test_find_next_available_code_uses_sheet_order():
    values = [
        ["code", "status"],
        ["", ""],
        ["CODE1", "sent"],
        ["CODE2", ""],
        ["CODE3", "available"],
    ]
    claim = sa._find_next_available_code(values)
    assert claim == sa.CodeClaim(row_number=4, code="CODE2")


def test_claim_row_values_records_submission_metadata():
    user = SimpleNamespace(id=123, name="player", global_name=None)
    message = SimpleNamespace(id=456)
    claimed_at = datetime.datetime(2026, 7, 21, 13, 14, 15, tzinfo=sa._BJT)
    values = sa._claim_row_values(
        status="sent",
        user=user,
        message=message,
        screenshot_url="https://cdn.example/screenshot.png",
        claimed_at=claimed_at,
        dm_status="sent",
    )
    assert values == [
        "sent",
        "123",
        "player",
        "456",
        "https://cdn.example/screenshot.png",
        "2026/07/21 13:14:15",
        "sent",
        "",
    ]


def test_is_image_attachment_accepts_image_content_type_or_filename():
    assert sa._is_image_attachment(SimpleNamespace(content_type="image/png", filename="proof.bin")) is True
    assert sa._is_image_attachment(SimpleNamespace(content_type=None, filename="proof.JPG")) is True
    assert sa._is_image_attachment(SimpleNamespace(content_type="text/plain", filename="proof.txt")) is False
