import pandas as pd
import pytest

from esai_collection.screening import (
    approved_mapping_rows,
    approved_tracker_rows,
    classify,
    deduplicate,
    review_queue,
    screen,
)


def record(**overrides: str) -> dict[str, str]:
    row = {
        "record_id": "r1",
        "source": "openreview",
        "source_id": "one",
        "title": "Ordinary Paper",
        "abstract": "An ordinary abstract.",
        "authors": "Ada Smith",
        "year": "2024",
        "venue": "ICLR",
        "venue_track": "main",
        "paper_url": "https://example.test/one",
        "openreview_id": "",
        "doi": "",
    }
    row.update(overrides)
    return row


def test_screening_tiers_have_distinct_evidence() -> None:
    assert classify(record(title="SafetyBench: A Benchmark"))[0] == "high"
    assert (
        classify(
            record(
                abstract="In this work we introduce a new benchmark for calibration."
            )
        )[0]
        == "medium"
    )
    assert (
        classify(record(abstract="Results are compared with a common benchmark."))[0]
        == "low"
    )
    assert classify(record()) == ("", "")


def test_deduplication_is_transitive() -> None:
    rows = [
        record(source_id="a", title="Shared Title", openreview_id=""),
        record(source_id="b", title="Shared Title", openreview_id="forum-1"),
        record(source_id="c", title="Alternate Title", openreview_id="forum-1"),
    ]
    for row in rows:
        row["screening_tier"] = "high"
    unique = deduplicate(rows)
    assert len(unique) == 1
    assert unique[0]["also_seen_at"].count("openreview:") == 2


def test_review_queue_excludes_existing_and_low_confidence() -> None:
    rows = [
        {
            **record(),
            "candidate_id": "a",
            "screening_tier": "high",
            "screening_reason": "title",
            "already_in_tracker": "False",
        },
        {
            **record(),
            "candidate_id": "b",
            "screening_tier": "low",
            "screening_reason": "abstract",
            "already_in_tracker": "False",
        },
        {
            **record(),
            "candidate_id": "c",
            "screening_tier": "high",
            "screening_reason": "title",
            "already_in_tracker": "True",
        },
    ]
    queue = review_queue(rows)
    assert [row["candidate_id"] for row in queue] == ["a"]
    assert queue[0]["suggested_quick_ref"] == "Smith2024"
    assert queue[0]["risk_relevance_status"] == "pending"


def test_screening_backfills_known_date_basis() -> None:
    rows = screen([record(title="Safety Benchmark")])
    assert rows[0]["publication_date_basis"] == "venue-edition-estimate"


def test_tracker_matching_handles_conservative_aliases(tmp_path) -> None:
    workbook = tmp_path / "tracker.xlsx"
    pd.DataFrame(
        [
            {
                "title": (
                    "Why Do Multi-Agent LLM Systems Fail? "
                    "MAST: A Taxonomy and Benchmark"
                )
            },
            {"title": "Benchmark for Safe AI"},
        ]
    ).to_excel(workbook, sheet_name="benchmarks", index=False)

    rows = screen(
        [
            record(
                source_id="alias",
                title="Why Do Multi-Agent LLM Systems Fail?",
                abstract="We introduce a benchmark for multi-agent failures.",
            ),
            record(source_id="generic", title="Benchmark"),
        ],
        workbook,
    )
    by_source = {row["source_id"]: row for row in rows}
    assert by_source["alias"]["already_in_tracker"] == "True"
    assert by_source["alias"]["tracker_match_method"] == ("conservative-title-alias")
    assert by_source["generic"]["already_in_tracker"] == "False"


def test_tracker_export_requires_coded_fields() -> None:
    incomplete = {
        "candidate_id": "a",
        "review_status": "approved",
        "title": "Benchmark",
        "description": "Description",
        "risk_relevance_status": "include",
        "priority_risk": "yes",
        "candidate_harm_ids": "1.01.01",
        "triage_notes": "Measures the target behavior directly.",
        "reviewer": "Reviewer",
    }
    with pytest.raises(ValueError, match="quick ref"):
        approved_tracker_rows([incomplete])

    complete = {
        **incomplete,
        "quick ref": "Smith2024",
        "task": "classification",
        "metric": "accuracy",
        "communicated_metric": "accuracy",
        "version": "1",
        "evidence_type": "model benchmark",
    }
    exported = approved_tracker_rows([complete])
    assert exported[0]["quick ref"] == "Smith2024"
    handoff = approved_mapping_rows([complete])
    assert handoff[0]["candidate_harm_ids"] == "1.01.01"


def test_tracker_export_requires_risk_triage() -> None:
    row = {
        "candidate_id": "a",
        "review_status": "approved",
        "title": "Benchmark",
        "description": "Description",
        "quick ref": "Smith2024",
        "task": "classification",
        "metric": "accuracy",
        "communicated_metric": "accuracy",
        "reviewer": "Reviewer",
    }
    with pytest.raises(ValueError, match="risk_relevance_status"):
        approved_tracker_rows([row])

    excluded = {
        **row,
        "risk_relevance_status": "exclude",
        "triage_notes": "Does not introduce a risk-relevant scored task.",
    }
    assert approved_tracker_rows([excluded]) == []


def test_tracker_export_rejects_quick_ref_collisions() -> None:
    row = {
        "candidate_id": "a",
        "review_status": "approved",
        "risk_relevance_status": "include",
        "priority_risk": "no",
        "candidate_harm_ids": "1.01.01",
        "triage_notes": "Measures a taxonomy harm.",
        "reviewer": "Reviewer",
        "title": "Benchmark",
        "description": "Description",
        "quick ref": "Smith2024",
        "task": "classification",
        "metric": "accuracy",
        "communicated_metric": "accuracy",
    }
    with pytest.raises(ValueError, match="already exist"):
        approved_tracker_rows([row], {"smith2024"})
