from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

import pandas as pd

from .schema import MAPPING_HANDOFF_COLUMNS, REVIEW_COLUMNS, TRACKER_COLUMNS
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
GENERIC_SINGLE_TOKEN_TITLES = {
    "benchmark",
    "challenge",
    "corpus",
    "dataset",
    "evaluation",
    "leaderboard",
    "testbed",
}
TITLE_INDEX_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "in",
    "is",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "towards",
    "using",
    "via",
    "we",
    "why",
    "with",
}


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


def _tracker_titles(workbook: Path | None) -> list[tuple[str, str]]:
    if workbook is None:
        return []
    frame = pd.read_excel(workbook, sheet_name="benchmarks", dtype=str).fillna("")
    if "title" not in frame.columns:
        return []
    return sorted(
        {
            (normalise_title(title), title)
            for title in frame["title"]
            if normalise_title(title)
        }
    )


def tracker_quick_refs(workbook: Path) -> set[str]:
    frame = pd.read_excel(workbook, sheet_name="benchmarks", dtype=str).fillna("")
    if "quick ref" not in frame.columns:
        raise ValueError("benchmarks sheet is missing the 'quick ref' column")
    return {value.strip().casefold() for value in frame["quick ref"] if value.strip()}


def _is_safe_containment(left: str, right: str) -> bool:
    if not left or not right:
        return False
    shorter, longer = sorted((left, right), key=len)
    if shorter not in longer:
        return False
    tokens = shorter.split()
    if len(tokens) >= 2:
        return True
    return len(tokens[0]) >= 8 and tokens[0] not in GENERIC_SINGLE_TOKEN_TITLES


def _title_similarity(left: str, right: str) -> float:
    left_tokens, right_tokens = set(left.split()), set(right.split())
    union = left_tokens | right_tokens
    return len(left_tokens & right_tokens) / len(union) if union else 0.0


def _tracker_token_index(
    tracker_titles: list[tuple[str, str]],
) -> dict[str, set[int]]:
    index: dict[str, set[int]] = defaultdict(set)
    for position, (title_key, _) in enumerate(tracker_titles):
        for token in title_key.split():
            if token in TITLE_INDEX_STOPWORDS:
                continue
            index[token].add(position)
    return index


def _match_tracker_title(
    title_key: str,
    tracker_titles: list[tuple[str, str]],
    token_index: dict[str, set[int]],
    exact_index: dict[str, set[str]],
) -> tuple[str, str]:
    exact = sorted(exact_index.get(title_key, set()))
    if len(exact) == 1:
        return exact[0], "exact-normalized-title"
    candidate_positions: set[int] = set()
    for token in title_key.split():
        if token in TITLE_INDEX_STOPWORDS:
            continue
        candidate_positions.update(token_index.get(token, set()))
    possible_titles = [tracker_titles[position] for position in candidate_positions]
    aliases = sorted(
        {
            title
            for key, title in possible_titles
            if _is_safe_containment(title_key, key)
            or _title_similarity(title_key, key) >= 0.90
        }
    )
    if len(aliases) == 1:
        return aliases[0], "conservative-title-alias"
    if aliases:
        return " || ".join(aliases), "ambiguous-title-alias"
    return "", ""


def _suggested_quick_ref(authors: str, year: str) -> str:
    first_author = authors.split(";")[0].strip()
    if not first_author or not year:
        return ""
    family = (
        first_author.split(",", 1)[0]
        if "," in first_author
        else first_author.split()[-1]
    )
    family = re.sub(r"[^A-Za-z0-9]", "", family)
    return f"{family}{year}" if family else ""


def screen(
    rows: Iterable[dict[str, str]], workbook: Path | None = None
) -> list[dict[str, str]]:
    tracker_titles = _tracker_titles(workbook)
    token_index = _tracker_token_index(tracker_titles)
    exact_index: dict[str, set[str]] = defaultdict(set)
    for title_key, title in tracker_titles:
        exact_index[title_key].add(title)
    candidates: list[dict[str, str]] = []
    for source in rows:
        row = dict(source)
        if not row.get("publication_date_basis"):
            row["publication_date_basis"] = {
                "openreview": "venue-edition-estimate",
                "pmlr": "proceedings-publication-date",
            }.get(row.get("source", "").casefold(), "")
        tier, reason = classify(row)
        if not tier:
            continue
        row["screening_tier"] = tier
        row["screening_reason"] = reason
        title_key = normalise_title(row.get("title", ""))
        row["candidate_id"] = stable_id(
            "candidate", title_key or row.get("record_id", "")
        )
        match, match_method = _match_tracker_title(
            title_key, tracker_titles, token_index, exact_index
        )
        ambiguous_match = match_method == "ambiguous-title-alias"
        row["already_in_tracker"] = str(bool(match) and not ambiguous_match)
        row["tracker_match"] = match
        row["tracker_match_method"] = match_method
        complete = all(
            row.get(field, "").strip()
            for field in ("title", "authors", "year", "paper_url")
        )
        row["verification_status"] = (
            "ambiguous-tracker-match"
            if ambiguous_match
            else "in-tracker"
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
            "tracker_match_method",
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
                "suggested_quick_ref": _suggested_quick_ref(
                    str(row.get("authors", "")), str(row.get("year", ""))
                ),
                "risk_relevance_status": "pending",
                "priority_risk": "pending",
            }
        )
        output.append(item)
    return output


def _included_approved_rows(
    rows: Iterable[dict[str, str]],
    reserved_quick_refs: set[str] | None = None,
) -> list[dict[str, str]]:
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
        review_status = row.get("review_status", "").strip().casefold()
        if review_status not in {"", "pending", "approved", "rejected"}:
            candidate = row.get("candidate_id", "<unknown>")
            raise ValueError(
                f"candidate {candidate} has invalid review_status: {review_status}"
            )
        if review_status != "approved":
            continue
        relevance = row.get("risk_relevance_status", "").strip().casefold()
        if relevance not in {"include", "exclude"}:
            candidate = row.get("candidate_id", "<unknown>")
            raise ValueError(
                f"approved candidate {candidate} must set risk_relevance_status "
                "to include or exclude"
            )
        if not row.get("reviewer", "").strip():
            candidate = row.get("candidate_id", "<unknown>")
            raise ValueError(f"approved candidate {candidate} is missing a reviewer")
        if not row.get("triage_notes", "").strip():
            candidate = row.get("candidate_id", "<unknown>")
            raise ValueError(f"approved candidate {candidate} is missing triage_notes")
        if relevance == "exclude":
            continue
        priority = row.get("priority_risk", "").strip().casefold()
        if priority not in {"yes", "no"}:
            candidate = row.get("candidate_id", "<unknown>")
            raise ValueError(
                f"approved candidate {candidate} must set priority_risk to yes or no"
            )
        if not row.get("candidate_harm_ids", "").strip():
            candidate = row.get("candidate_id", "<unknown>")
            raise ValueError(
                f"approved candidate {candidate} is missing candidate_harm_ids"
            )
        missing = [field for field in required if not row.get(field, "").strip()]
        if missing:
            candidate = row.get("candidate_id", "<unknown>")
            raise ValueError(
                f"approved candidate {candidate} is missing: {', '.join(missing)}"
            )
        approved.append(row)
    quick_refs = [row["quick ref"].strip().casefold() for row in approved]
    duplicates = sorted(
        quick_ref for quick_ref in set(quick_refs) if quick_refs.count(quick_ref) > 1
    )
    if duplicates:
        raise ValueError(f"approved rows contain duplicate quick refs: {duplicates}")
    collisions = sorted(set(quick_refs) & (reserved_quick_refs or set()))
    if collisions:
        raise ValueError(f"approved quick refs already exist in tracker: {collisions}")
    return approved


def approved_tracker_rows(
    rows: Iterable[dict[str, str]],
    reserved_quick_refs: set[str] | None = None,
) -> list[dict[str, str]]:
    return [
        {field: row.get(field, "") for field in TRACKER_COLUMNS}
        for row in _included_approved_rows(rows, reserved_quick_refs)
    ]


def approved_mapping_rows(rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {field: row.get(field, "") for field in MAPPING_HANDOFF_COLUMNS}
        for row in _included_approved_rows(rows)
    ]
