from esai_collection.sheet_package import (
    clean_collection_review_rows,
    clean_id_repair_rows,
    clean_mapping_patch_rows,
    summarize_validation_issues,
)


def test_clean_collection_review_rows_normalizes_statuses_and_cells() -> None:
    rows = clean_collection_review_rows(
        [
            {
                "candidate_id": "c1",
                "title": "=Formula",
                "venue": "NeurIPS",
                "year": "2025",
                "screening_tier": "high",
                "risk_relevance_status": "Included",
                "priority_risk": "Y",
                "review_status": "",
                "description": "Line one\nline two",
            }
        ]
    )

    assert rows[0]["title"] == "'=Formula"
    assert rows[0]["description"] == "Line one line two"
    assert rows[0]["risk_relevance_status"] == "include"
    assert rows[0]["priority_risk"] == "yes"
    assert rows[0]["review_status"] == "pending"
    assert rows[0]["cleaning_flags"] == ""


def test_summarize_validation_issues_groups_counts() -> None:
    rows = summarize_validation_issues(
        [
            {"issue_type": "duplicate_edge_id", "severity": "error"},
            {"issue_type": "duplicate_edge_id", "severity": "error"},
            {"issue_type": "invalid_strength", "severity": "error"},
        ]
    )

    assert rows[0]["issue_type"] == "duplicate_edge_id"
    assert rows[0]["rows"] == 2
    assert "edge ID repairs" in rows[0]["suggested_resolution"]


def test_clean_patch_rows_flags_missing_required_fields() -> None:
    id_rows = clean_id_repair_rows(
        [{"sheet": "bench_measures_harm", "row_number": "", "new_edge_id": ""}]
    )
    patch_rows = clean_mapping_patch_rows(
        [{"operation": "edit", "edge_id": "", "benchmark_id": "b1"}]
    )

    assert "missing_row_number" in id_rows[0]["cleaning_flags"]
    assert "missing_new_edge_id" in id_rows[0]["cleaning_flags"]
    assert "invalid_operation" in patch_rows[0]["cleaning_flags"]
    assert "missing_edge_id" in patch_rows[0]["cleaning_flags"]
    assert "missing_harm_id" in patch_rows[0]["cleaning_flags"]
