from __future__ import annotations

from typing import Any


async def import_fortunepurple_embed_messages() -> list[dict[str, Any]]:
    """Read legacy FortunePurple Embed records only during one-time migration."""
    from cogs.db import aload_messages

    return [dict(message) for message in await aload_messages()]
