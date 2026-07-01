from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping

from .schema import REVIEW_COLUMNS

COLLECTION_SHEET_FIELDS = ["import_action", "cleaning_flags"] + REVIEW_COLUMNS

VALIDATION_ISSUE_SUMMARY_FIELDS = [
    "issue_type",
    "severity",
    "rows",
    "suggested_resolution",
]

ID_REPAIR_SHEET_FIELDS = [
    "import_action",
    "cleaning_flags",
    "sheet",
    "row_number",
    "operation",
    "old_edge_id",
    "benchmark_id",
    "harm_id",
    "new_edge_id",
    "reason",
]

MAPPING_PATCH_SHEET_FIELDS = [
    "import_action",
    "cleaning_flags",
    "sheet",
    "operation",
    "edge_id",
    "benchmark_id",
    "harm_id",
    "strength",
    "basis",
    "confidence",
    "notes",
    "reviewer",
]

_MULTISPACE = re.compile(r"[ \t]+")
_LINEBREAKS = re.compile(r"\r\n?|\n")
_FORMULA_PREFIXES = ("=", "+", "-", "@")
_TIER_ORDER = {"high": 0, "medium": 1, "low": 2, "": 9}


def _clean_cell(value: object) -> str:
    text = str(value or "")
    text = _LINEBREAKS.sub(" ", text)
    text = _MULTISPACE.sub(" ", text).strip()
    if text.startswith(_FORMULA_PREFIXES):
        return f"'{text}"
    return text


def _status(
    value: object, *, allowed: set[str], default: str, flags: list[str], field: str
) -> str:
    text = _clean_cell(value).casefold()
    if not text:
        return default
    synonyms = {
        "yes": "yes",
        "y": "yes",
        "true": "yes",
        "no": "no",
        "n": "no",
        "false": "no",
        "include": "include",
        "included": "include",
        "exclude": "exclude",
        "excluded": "exclude",
        "pending": "pending",
        "approve": "approved",
        "approved": "approved",
        "reject": "rejected",
        "rejected": "rejected",
    }
    normalized = synonyms.get(text, text)
    if normalized in allowed:
        return normalized
    flags.append(f"invalid_{field}:{text}")
    return text


def _year(row: Mapping[str, object]) -> int:
    try:
        return int(str(row.get("year", "") or 0))
    except ValueError:
        return 0


def clean_collection_review_rows(
    rows: Iterable[Mapping[str, object]],
) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    for row in rows:
        flags: list[str] = []
        item = {field: _clean_cell(row.get(field, "")) for field in REVIEW_COLUMNS}
        item["risk_relevance_status"] = _status(
            item.get("risk_relevance_status", ""),
            allowed={"include", "exclude", "pending"},
            default="pending",
            flags=flags,
            field="risk_relevance_status",
        )
        item["priority_risk"] = _status(
            item.get("priority_risk", ""),
            allowed={"yes", "no", "pending"},
            default="pending",
            flags=flags,
            field="priority_risk",
        )
        item["review_status"] = _status(
            item.get("review_status", ""),
            allowed={"approved", "rejected", "pending"},
            default="pending",
            flags=flags,
            field="review_status",
        )
        if item["review_status"] == "approved" and item["risk_relevance_status"]:
            if not item.get("reviewer"):
                flags.append("approved_missing_reviewer")
            if not item.get("triage_notes"):
                flags.append("approved_missing_triage_notes")
        cleaned.append(
            {
                "import_action": "review-candidate",
                "cleaning_flags": "; ".join(flags),
                **item,
            }
        )
    return sorted(
        cleaned,
        key=lambda row: (
            _TIER_ORDER.get(row.get("screening_tier", ""), 9),
            row.get("venue", ""),
            -_year(row),
            row.get("title", ""),
        ),
    )


def _suggested_resolution(issue_type: str) -> str:
    suggestions = {
        "benchmark_source_missing": (
            "Verify source URL and abstract in benchmark source registry."
        ),
        "harm_description_missing": (
            "Fill harm taxonomy description before semantic validation."
        ),
        "direct_face_validity_review": (
            "Review direct mappings that only have face-validity evidence."
        ),
        "duplicate_edge_id": (
            "Apply row-addressed duplicate edge ID repairs before importing patches."
        ),
        "non_model_evidence_scope": (
            "Confirm whether the benchmark is a model benchmark or out of scope."
        ),
        "ambiguous_benchmark_id": (
            "Resolve benchmark ID collisions before mapping updates."
        ),
        "invalid_strength": "Replace strength with a controlled value.",
        "benchmark_metadata_incomplete": (
            "Complete benchmark title, task, metric, and evidence fields."
        ),
    }
    return suggestions.get(issue_type, "Review and resolve before shared-sheet import.")


def summarize_validation_issues(
    rows: Iterable[Mapping[str, object]],
) -> list[dict[str, object]]:
    counts: Counter[tuple[str, str]] = Counter()
    for row in rows:
        issue_type = _clean_cell(row.get("issue_type", "unknown")) or "unknown"
        severity = _clean_cell(row.get("severity", "unknown")) or "unknown"
        counts[(issue_type, severity)] += 1
    return [
        {
            "issue_type": issue_type,
            "severity": severity,
            "rows": count,
            "suggested_resolution": _suggested_resolution(issue_type),
        }
        for (issue_type, severity), count in sorted(
            counts.items(), key=lambda item: (-item[1], item[0][0], item[0][1])
        )
    ]


def clean_id_repair_rows(
    rows: Iterable[Mapping[str, object]],
) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for row in rows:
        item = {
            field: _clean_cell(row.get(field, ""))
            for field in ID_REPAIR_SHEET_FIELDS
            if field not in {"import_action", "cleaning_flags"}
        }
        flags: list[str] = []
        if not item.get("row_number"):
            flags.append("missing_row_number")
        if not item.get("new_edge_id"):
            flags.append("missing_new_edge_id")
        output.append(
            {
                "import_action": "repair-edge-id",
                "cleaning_flags": "; ".join(flags),
                **item,
            }
        )
    return output


def clean_mapping_patch_rows(
    rows: Iterable[Mapping[str, object]],
) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for row in rows:
        item = {
            field: _clean_cell(row.get(field, ""))
            for field in MAPPING_PATCH_SHEET_FIELDS
            if field not in {"import_action", "cleaning_flags"}
        }
        flags: list[str] = []
        if item.get("operation") not in {"update", "delete"}:
            flags.append("invalid_operation")
        for key in ("edge_id", "benchmark_id", "harm_id"):
            if not item.get(key):
                flags.append(f"missing_{key}")
        if not item.get("reviewer"):
            flags.append("missing_reviewer")
        output.append(
            {
                "import_action": f"mapping-{item.get('operation', 'review')}",
                "cleaning_flags": "; ".join(flags),
                **item,
            }
        )
    return output


def package_counts(
    *,
    collection_rows: Iterable[Mapping[str, object]],
    issue_summary_rows: Iterable[Mapping[str, object]],
    id_repair_rows: Iterable[Mapping[str, object]],
    mapping_patch_rows: Iterable[Mapping[str, object]],
) -> dict[str, int]:
    materialized = {
        "collection_review_rows": list(collection_rows),
        "issue_summary_rows": list(issue_summary_rows),
        "id_repair_rows": list(id_repair_rows),
        "mapping_patch_rows": list(mapping_patch_rows),
    }
    flagged = defaultdict(int)
    for key, rows in materialized.items():
        flagged[f"{key}_flagged"] = sum(
            bool(str(row.get("cleaning_flags", "")).strip()) for row in rows
        )
    return {key: len(rows) for key, rows in materialized.items()} | dict(flagged)
