from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Mapping


_TRUE_VALUES = {"1", "true", "yes", "on"}
_DIRECT_PATTERNS = (
    re.compile(r"\bwithdraw(?:al|als|ing|n|s)?\b"),
    re.compile(r"\bcash\s*out\b"),
    re.compile(r"\bredeem(?:ed|ing)?\s+sc\b"),
    re.compile(r"\bredemption(?:s)?\b"),
    re.compile(r"\bdeposit(?:ed|ing|s)?\b"),
    re.compile(r"\brefund(?:ed|ing|s)?\b"),
)
_STATUS = r"(?:issue|problem|failed|declined|pending|missing|stuck|delayed|not received)"
_CONTEXT_PATTERNS = (
    re.compile(rf"\bpayment\b.{{0,40}}\b{_STATUS}\b"),
    re.compile(rf"\b{_STATUS}\b.{{0,40}}\bpayment\b"),
    re.compile(rf"\b(?:money|funds)\b.{{0,40}}\b{_STATUS}\b"),
    re.compile(rf"\b{_STATUS}\b.{{0,40}}\b(?:money|funds)\b"),
    re.compile(r"\bcharged\s+(?:twice|double|incorrectly|wrong)\b"),
    re.compile(r"\bduplicate\s+charge\b"),
    re.compile(r"\bwrong\s+amount\s+charged\b"),
)


@dataclass(frozen=True)
class SupportRedirectConfig:
    enabled: bool
    trigger_channel_ids: frozenset[int]
    support_channel_id: int
    cooldown_seconds: int = 600

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> "SupportRedirectConfig":
        values = os.environ if environ is None else environ
        enabled = (
            values.get("SUPPORT_REDIRECT_ENABLED", "0").strip().casefold()
            in _TRUE_VALUES
        )
        if not enabled:
            return cls(False, frozenset(), 0, 600)

        try:
            channels = frozenset(
                int(value.strip())
                for value in values.get("SUPPORT_TRIGGER_CHANNEL_IDS", "").split(",")
                if value.strip()
            )
            support_channel_id = int(values.get("SUPPORT_CHANNEL_ID", "0"))
            cooldown_seconds = int(
                values.get("SUPPORT_REDIRECT_COOLDOWN_SECONDS", "600")
            )
        except ValueError as exc:
            raise ValueError(
                "support redirect configuration contains a non-integer value"
            ) from exc

        if not channels or any(channel_id <= 0 for channel_id in channels):
            raise ValueError(
                "SUPPORT_TRIGGER_CHANNEL_IDS must contain positive channel IDs"
            )
        if support_channel_id <= 0:
            raise ValueError("SUPPORT_CHANNEL_ID must be a positive channel ID")
        if cooldown_seconds < 0:
            raise ValueError("SUPPORT_REDIRECT_COOLDOWN_SECONDS cannot be negative")
        return cls(True, channels, support_channel_id, cooldown_seconds)


def normalize_message(content: str) -> str:
    lowered = content.casefold()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", lowered)).strip()


def is_financial_support_issue(content: str) -> bool:
    normalized = normalize_message(content)
    if not normalized:
        return False
    return any(
        pattern.search(normalized)
        for pattern in _DIRECT_PATTERNS + _CONTEXT_PATTERNS
    )
