import json
import os
import uuid
from datetime import datetime, timezone, timedelta

TZ_CST = timezone(timedelta(hours=8))
DATA_FILE = "scheduled_messages.json"


def parse_time(text: str) -> datetime | None:
    try:
        dt = datetime.strptime(text.strip(), "%Y-%m-%d %H:%M")
        return dt.replace(tzinfo=TZ_CST)
    except ValueError:
        return None


def load_messages() -> list[dict]:
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_messages(messages: list[dict]) -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)


def is_due(message: dict) -> bool:
    send_at = datetime.fromisoformat(message["send_at"])
    return datetime.now(tz=TZ_CST) >= send_at
