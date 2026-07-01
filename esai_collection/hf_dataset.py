from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path

from .io import write_jsonl

SCHEMA_VERSION = "0.1.0"

PAPER_FIELDS = [
    "schema_version",
    "record_type",
    "paper_id",
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

BENCHMARK_CANDIDATE_FIELDS = [
    "schema_version",
    "record_type",
    "candidate_id",
    "paper_id",
    "title",
    "description",
    "source",
    "source_id",
    "venue",
    "venue_track",
    "year",
    "paper_url",
    "pdf_url",
    "doi",
    "screening_tier",
    "screening_reason",
    "duplicate_key",
    "also_seen_at",
    "already_in_tracker",
    "tracker_match",
    "tracker_match_method",
    "verification_status",
    "candidate_harm_ids",
    "priority_risk",
    "risk_relevance_status",
    "review_status",
]

REVIEW_QUEUE_FIELDS = [
    "schema_version",
    "record_type",
    "candidate_id",
    "source",
    "source_id",
    "venue",
    "year",
    "paper_url",
    "screening_tier",
    "screening_reason",
    "suggested_quick_ref",
    "risk_relevance_status",
    "priority_risk",
    "candidate_harm_ids",
    "triage_notes",
    "review_status",
    "reviewer",
    "review_notes",
    "benchmark_quick_ref",
    "benchmark_title",
    "benchmark_description",
    "benchmark_task",
    "benchmark_metric",
    "benchmark_communicated_metric",
    "benchmark_modality",
    "benchmark_interaction_horizon",
    "benchmark_aggregation_scale",
    "benchmark_version",
    "benchmark_notes",
    "benchmark_evidence_type",
]

MAPPING_EDGE_FIELDS = [
    "schema_version",
    "record_type",
    "edge_id",
    "benchmark_id",
    "harm_id",
    "benchmark_quick_ref",
    "benchmark_title",
    "benchmark_description",
    "benchmark_task",
    "benchmark_metric",
    "benchmark_evidence_type",
    "benchmark_source_url",
    "source_match_method",
    "context_status",
    "harm_label",
    "harm_description",
    "harm_domain",
    "harm_subdomain",
    "strength",
    "basis",
    "confidence",
    "notes",
]

SOURCE_REGISTRY_FIELDS = [
    "schema_version",
    "record_type",
    "benchmark_id",
    "title",
    "quick_ref",
    "source_url",
    "source_abstract",
    "source_status",
    "verified_at",
    "notes",
]

MAPPING_PREDICTION_FIELDS = [
    "schema_version",
    "record_type",
    "edge_id",
    "validator_type",
    "validator_name",
    "prompt_name",
    "prompt_sha256",
    "model",
    "created_at",
    "verdict",
    "corrected_strength",
    "corrected_basis",
    "scored_construct",
    "evidence_used",
    "inference_steps",
    "reason",
    "confidence",
    "needs_human_review",
    "parse_error",
    "raw_response",
]

MAPPING_REVIEW_FIELDS = [
    "schema_version",
    "record_type",
    "edge_id",
    "benchmark_id",
    "harm_id",
    "benchmark_title",
    "benchmark_task",
    "benchmark_metric",
    "benchmark_evidence_type",
    "context_status",
    "harm_label",
    "harm_domain",
    "current_strength",
    "current_basis",
    "current_confidence",
    "verdict",
    "proposed_strength",
    "proposed_basis",
    "scored_construct",
    "evidence_used",
    "inference_steps",
    "confidence",
    "reason",
    "needs_human_review",
    "validator_name",
    "review_status",
    "reviewer",
    "review_notes",
]


def _text(value: object) -> str:
    return str(value or "").strip()


def _integer(value: object) -> int | None:
    text = _text(value)
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _semicolon_list(value: object) -> list[str]:
    return [item.strip() for item in _text(value).split(";") if item.strip()]


def _bool_or_none(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    text = _text(value).casefold()
    if text in {"true", "yes", "1"}:
        return True
    if text in {"false", "no", "0"}:
        return False
    return None


def _pick(row: Mapping[str, object], key: str) -> str:
    return _text(row.get(key, ""))


def paper_record(
    row: Mapping[str, object], *, schema_version: str = SCHEMA_VERSION
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "record_type": "paper",
        "paper_id": _pick(row, "record_id"),
        "source": _pick(row, "source"),
        "source_id": _pick(row, "source_id"),
        "title": _pick(row, "title"),
        "abstract": _pick(row, "abstract"),
        "authors": _semicolon_list(row.get("authors", "")),
        "author_count": _integer(row.get("author_count", "")),
        "publication_date": _pick(row, "publication_date"),
        "publication_date_basis": _pick(row, "publication_date_basis"),
        "year": _integer(row.get("year", "")),
        "venue": _pick(row, "venue"),
        "venue_track": _pick(row, "venue_track"),
        "decision": _pick(row, "decision"),
        "keywords": _semicolon_list(row.get("keywords", "")),
        "tldr": _pick(row, "tldr"),
        "paper_url": _pick(row, "paper_url"),
        "pdf_url": _pick(row, "pdf_url"),
        "code_url": _pick(row, "code_url"),
        "openreview_id": _pick(row, "openreview_id"),
        "pmlr_id": _pick(row, "pmlr_id"),
        "doi": _pick(row, "doi"),
        "collected_at": _pick(row, "collected_at"),
        "run_id": _pick(row, "run_id"),
    }


def benchmark_candidate_record(
    row: Mapping[str, object], *, schema_version: str = SCHEMA_VERSION
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "record_type": "benchmark_candidate",
        "candidate_id": _pick(row, "candidate_id"),
        "paper_id": _pick(row, "record_id"),
        "title": _pick(row, "title"),
        "description": _pick(row, "abstract"),
        "source": _pick(row, "source"),
        "source_id": _pick(row, "source_id"),
        "venue": _pick(row, "venue"),
        "venue_track": _pick(row, "venue_track"),
        "year": _integer(row.get("year", "")),
        "paper_url": _pick(row, "paper_url"),
        "pdf_url": _pick(row, "pdf_url"),
        "doi": _pick(row, "doi"),
        "screening_tier": _pick(row, "screening_tier"),
        "screening_reason": _pick(row, "screening_reason"),
        "duplicate_key": _pick(row, "duplicate_key"),
        "also_seen_at": _semicolon_list(row.get("also_seen_at", "")),
        "already_in_tracker": _bool_or_none(row.get("already_in_tracker", "")),
        "tracker_match": _pick(row, "tracker_match"),
        "tracker_match_method": _pick(row, "tracker_match_method"),
        "verification_status": _pick(row, "verification_status"),
        "candidate_harm_ids": _semicolon_list(row.get("candidate_harm_ids", "")),
        "priority_risk": _pick(row, "priority_risk"),
        "risk_relevance_status": _pick(row, "risk_relevance_status"),
        "review_status": _pick(row, "review_status"),
    }


def review_queue_record(
    row: Mapping[str, object], *, schema_version: str = SCHEMA_VERSION
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "record_type": "collection_review_row",
        "candidate_id": _pick(row, "candidate_id"),
        "source": _pick(row, "source"),
        "source_id": _pick(row, "source_id"),
        "venue": _pick(row, "venue"),
        "year": _integer(row.get("year", "")),
        "paper_url": _pick(row, "paper_url"),
        "screening_tier": _pick(row, "screening_tier"),
        "screening_reason": _pick(row, "screening_reason"),
        "suggested_quick_ref": _pick(row, "suggested_quick_ref"),
        "risk_relevance_status": _pick(row, "risk_relevance_status"),
        "priority_risk": _pick(row, "priority_risk"),
        "candidate_harm_ids": _semicolon_list(row.get("candidate_harm_ids", "")),
        "triage_notes": _pick(row, "triage_notes"),
        "review_status": _pick(row, "review_status"),
        "reviewer": _pick(row, "reviewer"),
        "review_notes": _pick(row, "review_notes"),
        "benchmark_quick_ref": _pick(row, "quick ref"),
        "benchmark_title": _pick(row, "title"),
        "benchmark_description": _pick(row, "description"),
        "benchmark_task": _pick(row, "task"),
        "benchmark_metric": _pick(row, "metric"),
        "benchmark_communicated_metric": _pick(row, "communicated_metric"),
        "benchmark_modality": _pick(row, "modality"),
        "benchmark_interaction_horizon": _pick(row, "interaction horizon"),
        "benchmark_aggregation_scale": _pick(row, "aggregation scale"),
        "benchmark_version": _pick(row, "version"),
        "benchmark_notes": _pick(row, "notes"),
        "benchmark_evidence_type": _pick(row, "evidence_type"),
    }


def mapping_edge_record(
    row: Mapping[str, object], *, schema_version: str = SCHEMA_VERSION
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "record_type": "benchmark_harm_edge",
        "edge_id": _pick(row, "edge_id"),
        "benchmark_id": _pick(row, "benchmark_id"),
        "harm_id": _pick(row, "harm_id"),
        "benchmark_quick_ref": _pick(row, "benchmark_quick_ref"),
        "benchmark_title": _pick(row, "benchmark_title"),
        "benchmark_description": _pick(row, "benchmark_description"),
        "benchmark_task": _pick(row, "benchmark_task"),
        "benchmark_metric": _pick(row, "benchmark_metric"),
        "benchmark_evidence_type": _pick(row, "benchmark_evidence_type"),
        "benchmark_source_url": _pick(row, "benchmark_source_url"),
        "source_match_method": _pick(row, "source_match_method"),
        "context_status": _pick(row, "context_status"),
        "harm_label": _pick(row, "harm_label"),
        "harm_description": _pick(row, "harm_description"),
        "harm_domain": _pick(row, "harm_domain"),
        "harm_subdomain": _pick(row, "harm_subdomain"),
        "strength": _pick(row, "current_strength"),
        "basis": _pick(row, "current_basis"),
        "confidence": _pick(row, "current_confidence"),
        "notes": _pick(row, "current_notes"),
    }


def source_registry_record(
    row: Mapping[str, object], *, schema_version: str = SCHEMA_VERSION
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "record_type": "benchmark_source",
        "benchmark_id": _pick(row, "benchmark_id"),
        "title": _pick(row, "title"),
        "quick_ref": _pick(row, "quick_ref"),
        "source_url": _pick(row, "source_url"),
        "source_abstract": _pick(row, "source_abstract"),
        "source_status": _pick(row, "source_status"),
        "verified_at": _pick(row, "verified_at"),
        "notes": _pick(row, "notes"),
    }


def mapping_prediction_record(
    row: Mapping[str, object], *, schema_version: str = SCHEMA_VERSION
) -> dict[str, object]:
    validator_name = _pick(row, "model") or _pick(row, "prompt_name")
    validator_type = (
        "deterministic"
        if validator_name.startswith("deterministic-")
        else "model"
        if validator_name
        else ""
    )
    return {
        "schema_version": schema_version,
        "record_type": "mapping_prediction",
        "edge_id": _pick(row, "edge_id"),
        "validator_type": validator_type,
        "validator_name": validator_name,
        "prompt_name": _pick(row, "prompt_name"),
        "prompt_sha256": _pick(row, "prompt_sha256"),
        "model": _pick(row, "model"),
        "created_at": _pick(row, "created_at"),
        "verdict": _pick(row, "verdict"),
        "corrected_strength": _pick(row, "corrected_strength"),
        "corrected_basis": _pick(row, "corrected_basis"),
        "scored_construct": _pick(row, "scored_construct"),
        "evidence_used": _pick(row, "evidence_used"),
        "inference_steps": _integer(row.get("inference_steps", "")),
        "reason": _pick(row, "reason"),
        "confidence": _pick(row, "confidence"),
        "needs_human_review": _bool_or_none(row.get("needs_human_review", "")),
        "parse_error": _pick(row, "parse_error"),
        "raw_response": _pick(row, "raw_response"),
    }


def mapping_review_record(
    row: Mapping[str, object], *, schema_version: str = SCHEMA_VERSION
) -> dict[str, object]:
    validator_name = _pick(row, "model") or _pick(row, "prompt_name")
    return {
        "schema_version": schema_version,
        "record_type": "mapping_review_row",
        "edge_id": _pick(row, "edge_id"),
        "benchmark_id": _pick(row, "benchmark_id"),
        "harm_id": _pick(row, "harm_id"),
        "benchmark_title": _pick(row, "benchmark_title"),
        "benchmark_task": _pick(row, "benchmark_task"),
        "benchmark_metric": _pick(row, "benchmark_metric"),
        "benchmark_evidence_type": _pick(row, "benchmark_evidence_type"),
        "context_status": _pick(row, "context_status"),
        "harm_label": _pick(row, "harm_label"),
        "harm_domain": _pick(row, "harm_domain"),
        "current_strength": _pick(row, "current_strength"),
        "current_basis": _pick(row, "current_basis"),
        "current_confidence": _pick(row, "current_confidence"),
        "verdict": _pick(row, "verdict"),
        "proposed_strength": _pick(row, "proposed_strength"),
        "proposed_basis": _pick(row, "proposed_basis"),
        "scored_construct": _pick(row, "scored_construct"),
        "evidence_used": _pick(row, "evidence_used"),
        "inference_steps": _integer(row.get("inference_steps", "")),
        "confidence": _pick(row, "model_confidence"),
        "reason": _pick(row, "reason"),
        "needs_human_review": _bool_or_none(row.get("needs_human_review", "")),
        "validator_name": validator_name,
        "review_status": _pick(row, "review_status"),
        "reviewer": _pick(row, "reviewer"),
        "review_notes": _pick(row, "review_notes"),
    }


def _write_schema(outdir: Path, *, schema_version: str) -> Path:
    schema = {
        "schema_version": schema_version,
        "created_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "files": {
            "papers.jsonl": {
                "record_type": "paper",
                "primary_key": "paper_id",
                "fields": PAPER_FIELDS,
            },
            "benchmark_candidates.jsonl": {
                "record_type": "benchmark_candidate",
                "primary_key": "candidate_id",
                "fields": BENCHMARK_CANDIDATE_FIELDS,
            },
            "collection_review_queue.jsonl": {
                "record_type": "collection_review_row",
                "primary_key": "candidate_id",
                "fields": REVIEW_QUEUE_FIELDS,
            },
            "benchmark_harm_edges.jsonl": {
                "record_type": "benchmark_harm_edge",
                "primary_key": "edge_id",
                "fields": MAPPING_EDGE_FIELDS,
            },
            "benchmark_sources.jsonl": {
                "record_type": "benchmark_source",
                "primary_key": "benchmark_id",
                "fields": SOURCE_REGISTRY_FIELDS,
            },
            "mapping_predictions.jsonl": {
                "record_type": "mapping_prediction",
                "primary_key": "edge_id + validator_name",
                "fields": MAPPING_PREDICTION_FIELDS,
            },
            "mapping_review.jsonl": {
                "record_type": "mapping_review_row",
                "primary_key": "edge_id + validator_name",
                "fields": MAPPING_REVIEW_FIELDS,
            },
        },
    }
    path = outdir / "schema.json"
    path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", "utf-8")
    return path


def _write_card(
    outdir: Path, *, dataset_name: str, schema_version: str, counts: Mapping[str, int]
) -> Path:
    path = outdir / "README.md"
    paper_count = counts.get("papers", 0)
    candidate_count = counts.get("benchmark_candidates", 0)
    review_count = counts.get("collection_review_queue", 0)
    edge_count = counts.get("benchmark_harm_edges", 0)
    source_count = counts.get("benchmark_sources", 0)
    prediction_count = counts.get("mapping_predictions", 0)
    mapping_review_count = counts.get("mapping_review", 0)
    body = f"""---
license: other
language:
  - en
task_categories:
  - text-classification
  - tabular-classification
configs:
  - config_name: papers
    data_files:
      - split: train
        path: papers.jsonl
  - config_name: benchmark_candidates
    data_files:
      - split: train
        path: benchmark_candidates.jsonl
  - config_name: collection_review_queue
    data_files:
      - split: train
        path: collection_review_queue.jsonl
  - config_name: benchmark_harm_edges
    data_files:
      - split: train
        path: benchmark_harm_edges.jsonl
  - config_name: benchmark_sources
    data_files:
      - split: train
        path: benchmark_sources.jsonl
  - config_name: mapping_predictions
    data_files:
      - split: train
        path: mapping_predictions.jsonl
  - config_name: mapping_review
    data_files:
      - split: train
        path: mapping_review.jsonl
---

# {dataset_name}

Schema version: `{schema_version}`

This dataset package stores ESAI benchmark collection and benchmark-to-risk
mapping data as JSONL files. It separates paper provenance, screened benchmark
candidates, collection review rows, current benchmark-risk edges, and benchmark
source verification.

## Files

| File | Rows | Key |
|---|---:|---|
| `papers.jsonl` | {paper_count} | `paper_id` |
| `benchmark_candidates.jsonl` | {candidate_count} | `candidate_id` |
| `collection_review_queue.jsonl` | {review_count} | `candidate_id` |
| `benchmark_harm_edges.jsonl` | {edge_count} | `edge_id` |
| `benchmark_sources.jsonl` | {source_count} | `benchmark_id` |
| `mapping_predictions.jsonl` | {prediction_count} | `edge_id + validator_name` |
| `mapping_review.jsonl` | {mapping_review_count} | `edge_id + validator_name` |

See `schema.json` for field lists and primary keys.

## Use Notes

This export is intended for research and data-engineering review. The mapping
prediction and review files contain deterministic validator output and should
not be interpreted as final tracker decisions. Human approval is still required
before applying any mapping patch.
"""
    path.write_text(body, "utf-8")
    return path


def export_hf_dataset(
    *,
    outdir: Path,
    dataset_name: str,
    papers: Iterable[Mapping[str, object]] = (),
    candidates: Iterable[Mapping[str, object]] = (),
    review_queue: Iterable[Mapping[str, object]] = (),
    mapping_edges: Iterable[Mapping[str, object]] = (),
    source_registry: Iterable[Mapping[str, object]] = (),
    mapping_predictions: Iterable[Mapping[str, object]] = (),
    mapping_review: Iterable[Mapping[str, object]] = (),
    schema_version: str = SCHEMA_VERSION,
) -> tuple[list[Path], dict[str, int]]:
    outdir.mkdir(parents=True, exist_ok=True)
    paper_rows = [paper_record(row, schema_version=schema_version) for row in papers]
    candidate_rows = [
        benchmark_candidate_record(row, schema_version=schema_version)
        for row in candidates
    ]
    review_rows = [
        review_queue_record(row, schema_version=schema_version) for row in review_queue
    ]
    edge_rows = [
        mapping_edge_record(row, schema_version=schema_version) for row in mapping_edges
    ]
    source_rows = [
        source_registry_record(row, schema_version=schema_version)
        for row in source_registry
    ]
    prediction_rows = [
        mapping_prediction_record(row, schema_version=schema_version)
        for row in mapping_predictions
    ]
    mapping_review_rows = [
        mapping_review_record(row, schema_version=schema_version)
        for row in mapping_review
    ]
    files = [
        outdir / "papers.jsonl",
        outdir / "benchmark_candidates.jsonl",
        outdir / "collection_review_queue.jsonl",
        outdir / "benchmark_harm_edges.jsonl",
        outdir / "benchmark_sources.jsonl",
        outdir / "mapping_predictions.jsonl",
        outdir / "mapping_review.jsonl",
    ]
    for path, rows in zip(
        files,
        [
            paper_rows,
            candidate_rows,
            review_rows,
            edge_rows,
            source_rows,
            prediction_rows,
            mapping_review_rows,
        ],
        strict=True,
    ):
        write_jsonl(path, rows)
    counts = {
        "papers": len(paper_rows),
        "benchmark_candidates": len(candidate_rows),
        "collection_review_queue": len(review_rows),
        "benchmark_harm_edges": len(edge_rows),
        "benchmark_sources": len(source_rows),
        "mapping_predictions": len(prediction_rows),
        "mapping_review": len(mapping_review_rows),
    }
    files.append(_write_schema(outdir, schema_version=schema_version))
    files.append(
        _write_card(
            outdir,
            dataset_name=dataset_name,
            schema_version=schema_version,
            counts=counts,
        )
    )
    return files, counts
