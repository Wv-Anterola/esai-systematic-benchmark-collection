from __future__ import annotations

from dataclasses import dataclass
from datetime import date

CUTOFF_DATE = date(2022, 11, 1)

RAW_FIELDS = [
    "record_id",
    "source",
    "source_id",
    "title",
    "abstract",
    "authors",
    "author_count",
    "publication_date",
    "publication_date_basis",
    "year",
    "venue",
    "venue_track",
    "decision",
    "keywords",
    "tldr",
    "paper_url",
    "pdf_url",
    "code_url",
    "openreview_id",
    "pmlr_id",
    "doi",
    "collected_at",
    "run_id",
]

SCREENING_FIELDS = RAW_FIELDS + [
    "candidate_id",
    "screening_tier",
    "screening_reason",
    "duplicate_key",
    "also_seen_at",
    "already_in_tracker",
    "tracker_match",
    "tracker_match_method",
    "verification_status",
]

TRACKER_COLUMNS = [
    "benchmark_id",
    "quick ref",
    "title",
    "description",
    "task",
    "metric",
    "communicated_metric",
    "modality",
    "interaction horizon",
    "aggregation scale",
    "version",
    "notes",
    "evidence_type",
]

REVIEW_COLUMNS = [
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
    "suggested_quick_ref",
    "risk_relevance_status",
    "priority_risk",
    "candidate_harm_ids",
    "triage_notes",
    "review_status",
    "reviewer",
    "review_notes",
] + TRACKER_COLUMNS

MAPPING_HANDOFF_COLUMNS = [
    "candidate_id",
    "quick ref",
    "title",
    "priority_risk",
    "candidate_harm_ids",
    "triage_notes",
    "reviewer",
    "review_notes",
]


@dataclass(frozen=True)
class VenueSpec:
    venue: str
    year: int
    track: str
    venue_ids: tuple[str, ...]


def default_openreview_venues(as_of_year: int) -> list[VenueSpec]:
    """Return supported venue identifiers through ``as_of_year``.

    The lower bounds enforce the November 2022 scope without admitting ICLR or
    ICML editions that concluded before the cutoff.
    """
    specs: list[VenueSpec] = []
    for year in range(2023, as_of_year + 1):
        specs.append(VenueSpec("ICLR", year, "main", (f"ICLR.cc/{year}/Conference",)))
    for year in range(2022, as_of_year + 1):
        specs.append(
            VenueSpec("NeurIPS", year, "main", (f"NeurIPS.cc/{year}/Conference",))
        )
        specs.append(
            VenueSpec(
                "NeurIPS",
                year,
                "datasets-and-benchmarks",
                (
                    f"NeurIPS.cc/{year}/Track/Datasets_and_Benchmarks",
                    f"NeurIPS.cc/{year}/Datasets_and_Benchmarks_Track",
                ),
            )
        )
    for year in range(2024, as_of_year + 1):
        specs.append(
            VenueSpec("COLM", year, "main", (f"colmweb.org/COLM/{year}/Conference",))
        )
    return specs
