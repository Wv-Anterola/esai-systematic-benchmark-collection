from __future__ import annotations

import random
from collections import defaultdict, deque
from collections.abc import Iterable

from .schema import SCREENING_FIELDS

RECALL_AUDIT_FIELDS = SCREENING_FIELDS + [
    "audit_status",
    "audit_decision",
    "auditor",
    "audit_notes",
]


def sample_recall_audit(
    rows: Iterable[dict[str, str]], *, size: int, seed: int = 20260701
) -> list[dict[str, str]]:
    if size < 1:
        raise ValueError("sample size must be positive")
    low_rows = [row for row in rows if row.get("screening_tier") == "low"]
    if size > len(low_rows):
        raise ValueError(
            f"requested {size} rows but only {len(low_rows)} low-tier rows exist"
        )
    groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in low_rows:
        groups[(row.get("venue", ""), row.get("year", ""))].append(row)
    rng = random.Random(seed)
    queues: list[deque[dict[str, str]]] = []
    for key in sorted(groups, key=lambda value: (len(groups[value]), value)):
        group = list(groups[key])
        rng.shuffle(group)
        queues.append(deque(group))
    selected: list[dict[str, str]] = []
    while len(selected) < size:
        made_progress = False
        for queue in queues:
            if queue and len(selected) < size:
                selected.append(queue.popleft())
                made_progress = True
        if not made_progress:
            break
    if len(selected) != size:
        raise RuntimeError("recall audit sampling did not reach the requested size")
    output: list[dict[str, str]] = []
    for row in selected:
        item = {field: row.get(field, "") for field in RECALL_AUDIT_FIELDS}
        item["audit_status"] = "pending"
        item["audit_decision"] = ""
        item["auditor"] = ""
        item["audit_notes"] = ""
        output.append(item)
    return output
