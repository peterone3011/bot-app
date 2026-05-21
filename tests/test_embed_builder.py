from unittest.mock import patch
import pytest
import cogs.embed as eb


# ---------------------------------------------------------------------------
# new_draft
# ---------------------------------------------------------------------------

def test_new_draft_structure():
    draft = eb.new_draft(123456789)
    assert draft["status"] == "draft"
    assert draft["channel_id"] == 123456789
    assert draft["label"] is None
    assert draft["title"] is None
    assert draft["send_at"] is None
    assert draft["message_id"] is None
    assert draft["color"] is None
    assert "id" in draft
    assert "created_at" in draft


def test_new_draft_with_label():
    draft = eb.new_draft(111, label="May Announcement")
    assert draft["label"] == "May Announcement"


def test_new_draft_with_color():
    draft = eb.new_draft(111, color=0x9B59B6)
    assert draft["color"] == 0x9B59B6


# ---------------------------------------------------------------------------
# parse_color
# ---------------------------------------------------------------------------

def test_parse_color_valid_no_hash():
    assert eb.parse_color("9B59B6") == 0x9B59B6


def test_parse_color_valid_with_hash():
    assert eb.parse_color("#FF0000") == 0xFF0000


def test_parse_color_black():
    assert eb.parse_color("000000") == 0


def test_parse_color_empty():
    assert eb.parse_color("") is None
    assert eb.parse_color("   ") is None


def test_parse_color_invalid_chars():
    assert eb.parse_color("ZZZZZZ") == -1


def test_parse_color_wrong_length():
    assert eb.parse_color("FFF") == -1
    assert eb.parse_color("1234567") == -1


# ---------------------------------------------------------------------------
# parse_send_at
# ---------------------------------------------------------------------------

def test_parse_send_at_valid_future():
    from datetime import datetime, timedelta, timezone
    cst = timezone(timedelta(hours=8))
    future = (datetime.now(cst) + timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
    result = eb.parse_send_at(future)
    assert result is not None
    assert "+08:00" in result


def test_parse_send_at_past():
    assert eb.parse_send_at("2000-01-01 00:00") is None


def test_parse_send_at_invalid_format():
    assert eb.parse_send_at("not a date") is None
    assert eb.parse_send_at("2026/05/20 15:00") is None


# ---------------------------------------------------------------------------
# build_embed / build_view
# ---------------------------------------------------------------------------

def _full_msg(**overrides):
    base = {
        "title": "Test Title",
        "description": "Test body",
        "footer": "Footer text",
        "image_url": "https://example.com/img.png",
        "color": 0xFF0000,
        "button_label": "Click",
        "button_url": "https://example.com",
    }
    return {**base, **overrides}


def test_build_embed_sets_all_fields():
    embed = eb.build_embed(_full_msg())
    assert embed.title == "Test Title"
    assert embed.description == "Test body"
    assert embed.color.value == 0xFF0000
    assert embed.footer.text == "Footer text"
    assert embed.image.url == "https://example.com/img.png"


def test_build_embed_no_footer_or_image():
    embed = eb.build_embed(_full_msg(footer=None, image_url=None))
    assert embed.title == "Test Title"
    assert embed.description == "Test body"


def test_build_view_with_button():
    view = eb.build_view(_full_msg())
    assert view is not None
    assert len(view.children) == 1
    btn = view.children[0]
    assert btn.url == "https://example.com"
    assert btn.label == "Click"


def test_build_view_no_button():
    assert eb.build_view(_full_msg(button_label=None, button_url=None)) is None


def test_build_view_partial_button():
    assert eb.build_view(_full_msg(button_url=None)) is None


# ---------------------------------------------------------------------------
# last_used_color (mocked — storage tested in test_db.py)
# ---------------------------------------------------------------------------

def test_last_used_color_no_messages():
    with patch("cogs.embed.load_messages", return_value=[]):
        assert eb.last_used_color() is None


def test_last_used_color_returns_most_recent():
    old = {**eb.new_draft(1, color=0xFF0000), "created_at": "2026-01-01T00:00:00+08:00"}
    new = {**eb.new_draft(2, color=0x00FF00), "created_at": "2026-06-01T00:00:00+08:00"}
    with patch("cogs.embed.load_messages", return_value=[old, new]):
        assert eb.last_used_color() == 0x00FF00


def test_last_used_color_skips_uncolored():
    no_color = eb.new_draft(1)
    colored = eb.new_draft(2, color=0xABCDEF)
    with patch("cogs.embed.load_messages", return_value=[no_color, colored]):
        assert eb.last_used_color() == 0xABCDEF


# ---------------------------------------------------------------------------
# display_label
# ---------------------------------------------------------------------------

class _FakeChannel:
    name = "announcements"


class _FakeBot:
    def get_channel(self, _id):
        return _FakeChannel()


def test_display_label_uses_custom_label():
    msg = {"label": "My Post", "channel_id": 1, "created_at": "2026-05-18T10:00:00+08:00", "title": "X"}
    assert eb.display_label(msg, bot=None) == "My Post"


def test_display_label_auto_with_title():
    msg = {"label": None, "channel_id": 1, "created_at": "2026-05-18T10:00:00+08:00", "title": "Hello World"}
    label = eb.display_label(msg, bot=_FakeBot())
    assert "#announcements" in label
    assert "2026-05-18" in label
    assert "Hello World" in label


def test_display_label_auto_no_title():
    msg = {"label": None, "channel_id": 1, "created_at": "2026-05-18T10:00:00+08:00", "title": None}
    label = eb.display_label(msg, bot=_FakeBot())
    assert "(untitled)" in label


# ---------------------------------------------------------------------------
# parse_message_link
# ---------------------------------------------------------------------------

def test_parse_message_link_valid():
    link = "https://discord.com/channels/111/222333/444555"
    assert eb.parse_message_link(link) == (222333, 444555)


def test_parse_message_link_ptb():
    link = "https://ptb.discord.com/channels/111/222333/444555"
    assert eb.parse_message_link(link) == (222333, 444555)


def test_parse_message_link_invalid():
    assert eb.parse_message_link("not a link") is None
    assert eb.parse_message_link("https://discord.com/channels/111") is None


# ---------------------------------------------------------------------------
# draft_from_message
# ---------------------------------------------------------------------------

class _FakeEmbed:
    title = "Test Title"
    description = "Body text"
    color = type("C", (), {"value": 0xFF0000})()
    footer = type("F", (), {"text": "Footer"})()
    image = type("I", (), {"url": "https://example.com/img.png"})()


class _FakeButton:
    url = "https://example.com"
    label = "Click me"


class _FakeRow:
    children = [_FakeButton()]


class _FakeChannel2:
    id = 999


class _FakeMessage:
    id = 12345
    embeds = [_FakeEmbed()]
    components = [_FakeRow()]
    channel = _FakeChannel2()


def test_draft_from_message_fields():
    draft = eb.draft_from_message(_FakeMessage())
    assert draft["title"] == "Test Title"
    assert draft["description"] == "Body text"
    assert draft["footer"] == "Footer"
    assert draft["image_url"] == "https://example.com/img.png"
    assert draft["color"] == 0xFF0000
    assert draft["button_label"] == "Click me"
    assert draft["button_url"] == "https://example.com"
    assert draft["message_id"] == 12345
    assert draft["channel_id"] == 999


def test_draft_from_message_no_button():
    class _NoButtonRow:
        children = []

    class _MsgNoBtn:
        id = 1
        embeds = [_FakeEmbed()]
        components = [_NoButtonRow()]
        channel = _FakeChannel2()

    draft = eb.draft_from_message(_MsgNoBtn())
    assert draft["button_label"] is None
    assert draft["button_url"] is None
