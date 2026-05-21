"""One-time migration: import messages.json into Supabase messages table."""
import json
import os
import sys
from pathlib import Path

from supabase import create_client

MESSAGES_FILE = Path(os.environ.get("MESSAGES_FILE", "messages.json"))


def main() -> None:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_KEY must be set.")
        sys.exit(1)

    if not MESSAGES_FILE.exists():
        print(f"No file at {MESSAGES_FILE} — nothing to migrate.")
        return

    messages = json.loads(MESSAGES_FILE.read_text(encoding="utf-8"))
    if not messages:
        print("File is empty — nothing to migrate.")
        return

    client = create_client(url, key)
    client.table("messages").upsert(messages).execute()
    print(f"Migrated {len(messages)} messages to Supabase.")


if __name__ == "__main__":
    main()
