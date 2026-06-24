from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

import pandas as pd

from .schema import REVIEW_COLUMNS, TRACKER_COLUMNS
from .text import normalise_title, stable_id

TITLE_TERMS = (
    "benchmark",
    "data set",
    "dataset",
    "corpus",
    "testbed",
    "leaderboard",
    "evaluation suite",
    "shared task",
    "challenge",
)
ABSTRACT_NOUNS = r"benchmark|data\s?set|corpus|testbed|evaluation suite|leaderboard"
INTRODUCTION_PATTERN = re.compile(
    rf"\b(?:we|this (?:paper|work))\s+"
    rf"(?:introduce|present|release|propose|develop|build|create)"
    rf"\b.{{0,100}}\b(?:{ABSTRACT_NOUNS})s?\b",
    re.IGNORECASE | re.DOTALL,
)
ABSTRACT_PATTERN = re.compile(rf"\b(?:{ABSTRACT_NOUNS})s?\b", re.IGNORECASE)
TIER_RANK = {"high": 0, "medium": 1, "low": 2}


def classify(record: dict[str, str]) -> tuple[str, str]:
    title = record.get("title", "")
    abstract = record.get("abstract", "")
    if record.get("venue_track") == "datasets-and-benchmarks":
        return "high", "accepted in a datasets-and-benchmarks track"
    lowered_title = normalise_title(title)
    for term in TITLE_TERMS:
        if normalise_title(term) in lowered_title:
            return "high", f"title contains '{term}'"
    if INTRODUCTION_PATTERN.search(abstract):
        return "medium", "abstract introduces a benchmark or dataset artifact"
    match = ABSTRACT_PATTERN.search(abstract)
    if match:
        return (
            "low",
            f"abstract mentions '{match.group(0)}' without an introduction claim",
        )
    return "", ""


def _dedup_keys(row: dict[str, str]) -> list[str]:
    keys: list[str] = []
    title = normalise_title(row.get("title", ""))
    if title:
        keys.append(f"title:{title}")
    for field in ("openreview_id", "doi"):
        value = row.get(field, "").strip().casefold()
        if value:
            keys.append(f"{field}:{value}")
    return keys


def deduplicate(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Deduplicate records using transitive identifier and title matches."""
    parent = list(range(len(rows)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    seen: dict[str, int] = {}
    for index, row in enumerate(rows):
        for key in _dedup_keys(row):
            if key in seen:
                union(index, seen[key])
            else:
                seen[key] = index

    groups: dict[int, list[dict[str, str]]] = defaultdict(list)
    for index, row in enumerate(rows):
        groups[find(index)].append(row)

    output: list[dict[str, str]] = []
    for group in groups.values():
        group.sort(
            key=lambda row: (
                TIER_RANK.get(row.get("screening_tier", "low"), 9),
                -sum(
                    bool(row.get(field))
                    for field in (
                        "abstract",
                        "authors",
                        "paper_url",
                        "pdf_url",
                        "code_url",
                    )
                ),
                0 if row.get("source") == "pmlr" and row.get("venue") == "ICML" else 1,
            )
        )
        survivor = dict(group[0])
        for alternative in group[1:]:
            for field, value in alternative.items():
                if not survivor.get(field) and value:
                    survivor[field] = value
        survivor["also_seen_at"] = "; ".join(
            sorted(
                f"{row.get('source', '')}:{row.get('source_id', '')}"
                for row in group[1:]
            )
        )
        survivor["duplicate_key"] = next(iter(_dedup_keys(survivor)), "")
        output.append(survivor)
    return output


def _tracker_titles(workbook: Path | None) -> dict[str, str]:
    if workbook is None:
        return {}
    frame = pd.read_excel(workbook, sheet_name="benchmarks", dtype=str).fillna("")
    if "title" not in frame.columns:
        return {}
    return {
        normalise_title(title): title
        for title in frame["title"]
        if normalise_title(title)
    }


def screen(
    rows: Iterable[dict[str, str]], workbook: Path | None = None
) -> list[dict[str, str]]:
    tracker_titles = _tracker_titles(workbook)
    candidates: list[dict[str, str]] = []
    for source in rows:
        row = dict(source)
        tier, reason = classify(row)
        if not tier:
            continue
        row["screening_tier"] = tier
        row["screening_reason"] = reason
        title_key = normalise_title(row.get("title", ""))
        row["candidate_id"] = stable_id(
            "candidate", title_key or row.get("record_id", "")
        )
        match = tracker_titles.get(title_key, "")
        row["already_in_tracker"] = str(bool(match))
        row["tracker_match"] = match
        complete = all(
            row.get(field, "").strip()
            for field in ("title", "authors", "year", "paper_url")
        )
        row["verification_status"] = (
            "in-tracker"
            if match
            else ("metadata-complete" if complete else "metadata-incomplete")
        )
        candidates.append(row)
    return sorted(
        deduplicate(candidates),
        key=lambda row: (
            TIER_RANK.get(row.get("screening_tier", "low"), 9),
            -int(row.get("year", "0") or 0),
            row.get("venue", ""),
            row.get("title", ""),
        ),
    )


def review_queue(
    rows: Iterable[dict[str, str]], include_low: bool = False
) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for row in rows:
        if row.get("already_in_tracker") == "True":
            continue
        if row.get("screening_tier") == "low" and not include_low:
            continue
        item: dict[str, object] = {column: "" for column in REVIEW_COLUMNS}
        for field in (
            "candidate_id",
            "source",
            "source_id",
            "venue",
            "year",
            "paper_url",
            "screening_tier",
            "screening_reason",
            "already_in_tracker",
            "tracker_match",
        ):
            item[field] = row.get(field, "")
        item.update(
            {
                "title": row.get("title", ""),
                "description": row.get("abstract", ""),
                "version": "1",
                "notes": (
                    f"Collected from {row.get('venue', '')} {row.get('year', '')}; "
                    f"source: {row.get('paper_url', '')}"
                ),
                "evidence_type": "model benchmark",
            }
        )
        output.append(item)
    return output


def approved_tracker_rows(rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    required = (
        "title",
        "description",
        "quick ref",
        "task",
        "metric",
        "communicated_metric",
    )
    approved: list[dict[str, str]] = []
    for row in rows:
        if row.get("review_status", "").strip().casefold() != "approved":
            continue
        missing = [field for field in required if not row.get(field, "").strip()]
        if missing:
            candidate = row.get("candidate_id", "<unknown>")
            raise ValueError(
                f"approved candidate {candidate} is missing: {', '.join(missing)}"
            )
        approved.append({field: row.get(field, "") for field in TRACKER_COLUMNS})
    return approved
