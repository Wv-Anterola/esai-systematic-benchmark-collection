import json

from esai_collection.hf_dataset import export_hf_dataset


def test_export_hf_dataset_writes_separate_jsonl_files(tmp_path) -> None:
    outputs, counts = export_hf_dataset(
        outdir=tmp_path,
        dataset_name="test-map",
        papers=[
            {
                "record_id": "openreview:abc",
                "source": "openreview",
                "source_id": "abc",
                "title": "Safety Bench",
                "authors": "Ada Lovelace; Grace Hopper",
                "author_count": "2",
                "year": "2025",
            }
        ],
        candidates=[
            {
                "candidate_id": "candidate-1",
                "record_id": "openreview:abc",
                "title": "Safety Bench",
                "screening_tier": "high",
                "already_in_tracker": "False",
            }
        ],
        review_queue=[{"candidate_id": "candidate-1", "quick ref": "Lovelace2025"}],
        mapping_edges=[
            {
                "edge_id": "edge-1",
                "benchmark_id": "bench-1",
                "harm_id": "harm-1",
                "current_strength": "strong-proxy",
            }
        ],
        source_registry=[{"benchmark_id": "bench-1", "quick_ref": "Lovelace2025"}],
    )

    assert counts == {
        "papers": 1,
        "benchmark_candidates": 1,
        "collection_review_queue": 1,
        "benchmark_harm_edges": 1,
        "benchmark_sources": 1,
    }
    assert tmp_path.joinpath("schema.json").exists()
    assert tmp_path.joinpath("README.md").exists()
    assert {path.name for path in outputs} >= {
        "papers.jsonl",
        "benchmark_candidates.jsonl",
        "benchmark_harm_edges.jsonl",
    }

    paper = json.loads(tmp_path.joinpath("papers.jsonl").read_text().splitlines()[0])
    assert paper["authors"] == ["Ada Lovelace", "Grace Hopper"]
    assert paper["year"] == 2025

    edge = json.loads(
        tmp_path.joinpath("benchmark_harm_edges.jsonl").read_text().splitlines()[0]
    )
    assert edge["record_type"] == "benchmark_harm_edge"
    assert edge["strength"] == "strong-proxy"
