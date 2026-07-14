"""Citation-based filtering and histogram helpers for screened candidates.

Citation counts come from the ``enrich-metadata`` stage (Semantic Scholar and
OpenAlex). These pure functions join those counts onto screened candidates, bucket
the distribution so a natural cutoff is visible, and apply Zhijing's rule (drop
old, low-cited papers) as an explicit, configurable step. Nothing is dropped until
a threshold is supplied.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from .schema import SCREENING_FIELDS

CITATION_FIELDS = SCREENING_FIELDS + [
    "citation_count",
    "citation_source",
    "citation_age_years",
    "citation_filter_status",
]

HISTOGRAM_FIELDS = [
    "citation_bucket",
    "papers",
    "share_pct",
    "cumulative_papers",
    "cumulative_pct",
]

# Ordered buckets as (label, lower_inclusive, upper_inclusive); None upper == open.
DEFAULT_BUCKETS: list[tuple[str, int, int | None]] = [
    ("0", 0, 0),
    ("1", 1, 1),
    ("2", 2, 2),
    ("3-5", 3, 5),
    ("6-10", 6, 10),
    ("11-20", 11, 20),
    ("21-50", 21, 50),
    ("51-100", 51, 100),
    ("100+", 101, None),
]
MISSING_BUCKET = "missing"


def _parse_int(value: object) -> int | None:
    """Parse a CSV cell to an int, treating blanks and junk as missing."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None


def _pct(part: int, total: int) -> float:
    return round(100.0 * part / total, 2) if total else 0.0


def coalesce_citations(enrichment_row: dict[str, str] | None) -> tuple[int | None, str]:
    """Return the highest available citation count and which provider supplied it.

    Semantic Scholar, OpenAlex, and Crossref often disagree; we take the maximum of
    whatever is present. Blank or non-numeric values are treated as missing.
    """
    if not enrichment_row:
        return None, ""
    provided = [
        (count, source)
        for count, source in (
            (
                _parse_int(enrichment_row.get("semantic_scholar_citation_count")),
                "semantic-scholar",
            ),
            (_parse_int(enrichment_row.get("openalex_cited_by_count")), "openalex"),
            (_parse_int(enrichment_row.get("crossref_cited_by_count")), "crossref"),
        )
        if count is not None
    ]
    if not provided:
        return None, ""
    return max(provided, key=lambda item: item[0])


def join_citations(
    candidates: Iterable[dict[str, str]],
    enrichment: Iterable[dict[str, str]],
    *,
    as_of_year: int,
) -> list[dict[str, str]]:
    """Attach citation_count, citation_source, and citation_age_years to candidates."""
    by_id = {
        row.get("record_id", ""): row for row in enrichment if row.get("record_id")
    }
    output: list[dict[str, str]] = []
    for source in candidates:
        row = dict(source)
        count, citation_source = coalesce_citations(by_id.get(row.get("record_id", "")))
        row["citation_count"] = "" if count is None else str(count)
        row["citation_source"] = citation_source
        year = _parse_int(row.get("year"))
        row["citation_age_years"] = "" if year is None else str(as_of_year - year)
        output.append(row)
    return output


def citation_histogram(
    rows: Iterable[dict[str, str]],
    buckets: list[tuple[str, int, int | None]] = DEFAULT_BUCKETS,
) -> list[dict[str, object]]:
    """Bucket joined rows by citation count with cumulative shares.

    Papers without a resolved citation count land in a trailing ``missing`` bucket.
    """
    counts = {label: 0 for label, _, _ in buckets}
    missing = 0
    total = 0
    for row in rows:
        total += 1
        value = _parse_int(row.get("citation_count"))
        if value is None:
            missing += 1
            continue
        for label, low, high in buckets:
            if value >= low and (high is None or value <= high):
                counts[label] += 1
                break
    ordered = [(label, counts[label]) for label, _, _ in buckets]
    ordered.append((MISSING_BUCKET, missing))
    output: list[dict[str, object]] = []
    cumulative = 0
    for label, papers in ordered:
        cumulative += papers
        output.append(
            {
                "citation_bucket": label,
                "papers": papers,
                "share_pct": _pct(papers, total),
                "cumulative_papers": cumulative,
                "cumulative_pct": _pct(cumulative, total),
            }
        )
    return output


def suggest_cutoffs(
    rows: Iterable[dict[str, str]],
    thresholds: tuple[int, ...] = (1, 2, 3, 5, 10),
) -> list[dict[str, object]]:
    """For each candidate min-citation threshold, how many papers survive.

    A coverage aid for choosing the cutoff: papers with a missing citation count
    are counted as dropped, matching how ``filter_by_citations`` treats them under
    ``drop_missing``.
    """
    values = [_parse_int(row.get("citation_count")) for row in rows]
    total = len(values)
    known = [value for value in values if value is not None]
    output: list[dict[str, object]] = []
    for threshold in thresholds:
        kept = sum(1 for value in known if value >= threshold)
        output.append(
            {
                "min_citations": threshold,
                "kept": kept,
                "kept_pct": _pct(kept, total),
                "dropped": total - kept,
            }
        )
    return output


def _filter_status(
    *,
    count: int | None,
    age: int | None,
    min_citations: int | None,
    max_age_years: int,
    drop_missing: bool,
) -> str:
    if count is None:
        return "dropped-missing" if drop_missing else "kept"
    if min_citations is None:
        return "kept"
    if age is not None and age > max_age_years and count < min_citations:
        return "dropped-old-lowcite"
    return "kept"


def filter_by_citations(
    rows: Iterable[dict[str, str]],
    *,
    min_citations: int | None,
    max_age_years: int = 5,
    drop_missing: bool = False,
) -> tuple[list[dict[str, str]], dict[str, int]]:
    """Apply Zhijing's rule; return kept rows (citations desc) and status counts.

    A row is dropped only when it is both older than ``max_age_years`` and has fewer
    than ``min_citations`` citations. Recent papers are always kept. When
    ``min_citations`` is None nothing citation-based is dropped (annotate-only).
    Missing-citation papers are kept unless ``drop_missing`` is set.
    """
    annotated: list[dict[str, str]] = []
    for source in rows:
        row = dict(source)
        row["citation_filter_status"] = _filter_status(
            count=_parse_int(row.get("citation_count")),
            age=_parse_int(row.get("citation_age_years")),
            min_citations=min_citations,
            max_age_years=max_age_years,
            drop_missing=drop_missing,
        )
        annotated.append(row)
    counts = dict(Counter(row["citation_filter_status"] for row in annotated))
    kept = [row for row in annotated if row["citation_filter_status"] == "kept"]
    kept.sort(key=lambda row: _parse_int(row.get("citation_count")) or -1, reverse=True)
    return kept, counts
