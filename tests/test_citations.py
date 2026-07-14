from esai_collection.citations import (
    citation_histogram,
    coalesce_citations,
    filter_by_citations,
    join_citations,
    suggest_cutoffs,
)


def test_coalesce_prefers_max_and_records_source() -> None:
    count, source = coalesce_citations(
        {"semantic_scholar_citation_count": "12", "openalex_cited_by_count": "5"}
    )
    assert count == 12
    assert source == "semantic-scholar"


def test_coalesce_uses_crossref_when_present() -> None:
    # Crossref-only row (OpenAlex/S2 blank because they were rate-limited).
    assert coalesce_citations({"crossref_cited_by_count": "7"}) == (7, "crossref")
    # Max across all three providers wins.
    assert coalesce_citations(
        {
            "semantic_scholar_citation_count": "3",
            "openalex_cited_by_count": "5",
            "crossref_cited_by_count": "9",
        }
    ) == (9, "crossref")


def test_coalesce_blank_and_junk_are_missing() -> None:
    assert coalesce_citations(
        {"semantic_scholar_citation_count": "", "openalex_cited_by_count": "n/a"}
    ) == (None, "")
    assert coalesce_citations(None) == (None, "")
    # One provider present still resolves.
    assert coalesce_citations(
        {"semantic_scholar_citation_count": "", "openalex_cited_by_count": "3"}
    ) == (3, "openalex")


def test_join_computes_age_and_matches_by_record_id() -> None:
    candidates = [
        {"record_id": "r1", "year": "2020"},
        {"record_id": "r2", "year": "2025"},
        {"record_id": "r3", "year": ""},  # unknown year -> blank age
    ]
    enrichment = [
        {"record_id": "r1", "semantic_scholar_citation_count": "40"},
        {"record_id": "r2", "openalex_cited_by_count": "1"},
    ]
    joined = join_citations(candidates, enrichment, as_of_year=2026)
    by_id = {row["record_id"]: row for row in joined}
    assert by_id["r1"]["citation_count"] == "40"
    assert by_id["r1"]["citation_age_years"] == "6"
    assert by_id["r2"]["citation_age_years"] == "1"
    assert by_id["r3"]["citation_count"] == ""  # unmatched -> missing
    assert by_id["r3"]["citation_age_years"] == ""


def test_histogram_buckets_and_cumulative() -> None:
    rows = [
        {"citation_count": "0"},
        {"citation_count": "1"},
        {"citation_count": "4"},
        {"citation_count": "150"},
        {"citation_count": ""},  # missing bucket
    ]
    histogram = {row["citation_bucket"]: row for row in citation_histogram(rows)}
    assert histogram["0"]["papers"] == 1
    assert histogram["3-5"]["papers"] == 1
    assert histogram["100+"]["papers"] == 1
    assert histogram["missing"]["papers"] == 1
    # Cumulative reaches 100% at the trailing missing bucket.
    assert histogram["missing"]["cumulative_pct"] == 100.0


def test_suggest_cutoffs_coverage() -> None:
    rows = [
        {"citation_count": "0"},
        {"citation_count": "3"},
        {"citation_count": "20"},
        {"citation_count": ""},  # counted as dropped
    ]
    cutoffs = {row["min_citations"]: row for row in suggest_cutoffs(rows)}
    assert cutoffs[1]["kept"] == 2  # 3 and 20
    assert cutoffs[5]["kept"] == 1  # only 20
    assert cutoffs[1]["dropped"] == 2  # the 0 and the missing


def test_filter_applies_zhijing_rule_and_ranks() -> None:
    rows = [
        {"record_id": "recent-low", "citation_count": "1", "citation_age_years": "1"},
        {"record_id": "old-low", "citation_count": "2", "citation_age_years": "7"},
        {"record_id": "old-high", "citation_count": "80", "citation_age_years": "8"},
        {"record_id": "missing", "citation_count": "", "citation_age_years": "9"},
    ]
    kept, counts = filter_by_citations(rows, min_citations=10, max_age_years=5)
    kept_ids = [row["record_id"] for row in kept]

    # Old + low-cited drops; recent low-cited, old high-cited, and missing all stay.
    assert "old-low" not in kept_ids
    assert kept_ids[0] == "old-high"  # ranked by citations desc
    assert set(kept_ids) == {"old-high", "recent-low", "missing"}
    assert counts["dropped-old-lowcite"] == 1
    assert counts["kept"] == 3


def test_filter_annotate_only_when_no_threshold() -> None:
    rows = [
        {"record_id": "old-low", "citation_count": "1", "citation_age_years": "9"},
    ]
    kept, counts = filter_by_citations(rows, min_citations=None)
    assert len(kept) == 1
    assert counts["kept"] == 1


def test_filter_drop_missing_flag() -> None:
    rows = [
        {"record_id": "missing", "citation_count": "", "citation_age_years": "9"},
    ]
    kept, counts = filter_by_citations(rows, min_citations=10, drop_missing=True)
    assert kept == []
    assert counts["dropped-missing"] == 1
