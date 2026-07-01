from jsonschema import Draft202012Validator

from esai_collection import dataset_v1 as d1


def _validate(record_type: str, record: dict) -> list[str]:
    schema = d1.build_schemas()[record_type]
    validator = Draft202012Validator(schema)
    return [
        f"{'/'.join(str(p) for p in e.absolute_path)}: {e.message}"
        for e in validator.iter_errors(record)
    ]


def test_record_uuid_is_deterministic_and_distinct() -> None:
    assert d1.record_uuid("benchmark", "B6.01.01") == d1.record_uuid(
        "benchmark", "B6.01.01"
    )
    assert d1.record_uuid("benchmark", "B6.01.01") != d1.record_uuid(
        "harm", "B6.01.01"
    )
    # Fixed namespace: the value must not change silently.
    assert d1.record_uuid("harm", "7.03.01") == "ca23e1af-9613-5017-9eb4-ed08b9f60351"


def test_all_schemas_are_valid_metaschemas() -> None:
    for record_type, schema in d1.build_schemas().items():
        Draft202012Validator.check_schema(schema)
        assert schema["properties"]["record_type"]["const"] == record_type


def test_paper_transform_validates() -> None:
    row = {
        "paper_id": "openreview:abc",
        "source": "openreview",
        "source_id": "abc",
        "title": "A Safety Benchmark",
        "authors": ["Ada Lovelace", "Alan Turing"],
        "author_count": "2",
        "year": "2025",
        "openreview_id": "abc",
        "collected_at": "2026-06-24T00:00:00+00:00",
    }
    record = d1.paper_v1(row)
    assert _validate("paper", record) == []
    assert record["external_ids"]["openreview"] == "abc"
    assert record["provenance"]["retrieved_at"] == "2026-06-24T00:00:00+00:00"


def test_normalize_harms_dedups_by_harm_id() -> None:
    edges = [
        {"harm_id": "7.03.01", "harm_label": "Prompt sensitivity", "harm_domain": "7"},
        {"harm_id": "7.03.01", "harm_label": "Prompt sensitivity", "harm_domain": "7"},
        {"harm_id": "1.00.01", "harm_label": "Stereotyping", "harm_domain": "1"},
    ]
    harms = d1.normalize_harms(edges)
    assert {h["harm_id"] for h in harms} == {"7.03.01", "1.00.01"}
    assert all(_validate("harm", h) == [] for h in harms)


def test_normalize_benchmarks_enriches_from_edges() -> None:
    sources = [
        {"benchmark_id": "B6.01.01", "title": "FormatSpread", "quick_ref": "S24"}
    ]
    edges = [
        {
            "benchmark_id": "B6.01.01",
            "benchmark_task": "prompt-format sensitivity",
            "benchmark_metric": "performance spread",
            "benchmark_evidence_type": "model benchmark",
        }
    ]
    (benchmark,) = d1.normalize_benchmarks(sources, edges)
    assert benchmark["task"] == "prompt-format sensitivity"
    assert benchmark["metric"] == "performance spread"
    assert _validate("benchmark", benchmark) == []


def test_edge_references_resolve_to_entity_uuids() -> None:
    edge = d1.edge_v1(
        {
            "edge_id": "bmh2",
            "benchmark_id": "B6.01.01",
            "harm_id": "7.03.01",
            "strength": "direct",
            "basis": "face-validity-only",
            "confidence": "probable",
            "context_status": "metadata-complete",
        }
    )
    assert _validate("benchmark_harm_edge", edge) == []
    assert edge["benchmark_uuid"] == d1.record_uuid("benchmark", "B6.01.01")
    assert edge["harm_uuid"] == d1.record_uuid("harm", "7.03.01")


def test_prediction_empty_corrections_become_null() -> None:
    record = d1.prediction_v1(
        {
            "edge_id": "bmh2",
            "validator_name": "deterministic-heuristics-v1",
            "validator_type": "deterministic",
            "verdict": "INSUFFICIENT-EVIDENCE",
            "corrected_strength": "",
            "confidence": "uncertain",
            "needs_human_review": True,
        }
    )
    assert record["corrected_strength"] is None
    assert record["edge_uuid"] == d1.record_uuid("benchmark_harm_edge", "bmh2")
    assert _validate("mapping_prediction", record) == []
