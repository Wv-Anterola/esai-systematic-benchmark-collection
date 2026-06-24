#!/usr/bin/env python3
"""
openreview_common.py  --  helpers shared by the OpenReview collection and
validation work packages (openreview_collect.py, openreview_validate.py).
"""
from __future__ import annotations

import re

SITE = "https://openreview.net"
FORUM_URL = "https://openreview.net/forum?id={}"


def cval(content: dict, key: str):
    # API v2 nests values as {'value': x}; v1 is flat. handle both.
    v = content.get(key)
    if isinstance(v, dict) and "value" in v:
        return v["value"]
    return v


def as_text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return "; ".join(str(x) for x in v)
    return str(v)


def first_present(content: dict, extra: dict, *keys):
    for src in (content, extra):
        for key in keys:
            v = cval(src, key)
            if v:
                return v
    return None


def norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def is_dnb(venueid: str) -> bool:
    return "datasets_and_benchmarks" in venueid.lower()
