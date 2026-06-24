import pytest

from esai_collection.screening import (
    approved_tracker_rows,
    classify,
    deduplicate,
    review_queue,
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


def test_tracker_export_requires_coded_fields() -> None:
    incomplete = {
        "candidate_id": "a",
        "review_status": "approved",
        "title": "Benchmark",
        "description": "Description",
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
