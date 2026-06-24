from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime


def normalise_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def stable_id(namespace: str, value: str, length: int = 16) -> str:
    digest = hashlib.sha256(f"{namespace}:{value}".encode()).hexdigest()
    return digest[:length]


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def year_from_text(*values: str) -> str:
    for value in values:
        match = re.search(r"\b(20\d{2})\b", value or "")
        if match:
            return match.group(1)
    return ""
