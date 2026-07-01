"""ESAI benchmark-map dataset format, version 1.0.0.

This module is the single source of truth for the v1.0.0 HuggingFace dataset
format. It defines:

- the controlled vocabularies (enums) observed in the data;
- the stable UUIDv5 identity scheme (deterministic from a natural key);
- the JSON Schema for every record type (``build_schemas``);
- the record transforms that turn a v0.1.0 export into v1.0.0 records.

The format is a redesign of the flat v0.1.0 tables toward the discipline of
EvalEval's "Every Eval Ever" schema: stable conflict-free identity, normalized
entities separated from the relationships that connect them, layered
provenance, closed controlled vocabularies, and a checksummed manifest that
declares cross-file references.

Because the schemas and the record transforms are generated from the same enum
and field definitions here, an emitted dataset cannot drift from its schema.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

SCHEMA_VERSION = "1.0.0"
SOURCE_SCHEMA_VERSION = "0.1.0"

# Stable namespace for UUIDv5 derivation. Derived once from the dataset URL so
# that every deployment computes identical record UUIDs from the same keys:
#   uuid.uuid5(uuid.NAMESPACE_URL,
#              "https://huggingface.co/datasets/wvanterola/esai_benchmark_map")
NAMESPACE = uuid.UUID("1e093b0b-ead6-526f-b109-fd3d9b9b5219")

UUID5_PATTERN = "^[0-9a-f]{8}-[0-9a-f]{4}-5[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"


def record_uuid(kind: str, key: str) -> str:
    """Deterministic UUIDv5 for a record from its kind and natural key."""
    return str(uuid.uuid5(NAMESPACE, f"{kind}:{key}"))


# --- Controlled vocabularies -------------------------------------------------
# Closed enums are supersets of the values observed in the v0.1.0 data so that
# validation passes today and reserved lifecycle values are documented. Extend
# these lists (never repurpose a value) when the vocabulary grows.

ENUMS: dict[str, list[str]] = {
    # benchmark -> harm edge grading
    "strength": ["direct", "strong-proxy", "weak-proxy", "indirect", "contested"],
    "basis": ["validated-against-downstream", "face-validity-only"],
    "confidence": ["certain", "probable", "possible", "tentative", "uncertain"],
    "context_status": ["source-grounded", "metadata-complete", "metadata-incomplete"],
    "evidence_type": [
        "model benchmark",
        "human-subjects study",
        "red-team probe",
        "dataset audit",
        "automated metric",
    ],
    # assessment (validator / reviewer) verdicts
    "verdict": [
        "VALID",
        "UP-RATE",
        "DOWN-RATE",
        "REVISE-BASIS",
        "REVISE-STRENGTH",
        "INSUFFICIENT-EVIDENCE",
    ],
    "assessor_type": ["deterministic", "model", "human"],
    # collection / screening lifecycle
    "screening_tier": ["high", "medium", "low"],
    "verification_status": ["metadata-complete", "metadata-incomplete", "in-tracker"],
    "source_status": ["pending", "verified", "unreachable", "not-found"],
    "review_status": ["", "pending", "approved", "rejected", "needs-info"],
}


# --- JSON Schema building blocks --------------------------------------------

_UUID = {"type": "string", "pattern": UUID5_PATTERN}
_STR = {"type": "string"}
_STR_ARRAY = {"type": "array", "items": {"type": "string"}}
_UUID_ARRAY = {"type": "array", "items": _UUID}
_INT_OR_NULL = {"type": ["integer", "null"]}
_BOOL_OR_NULL = {"type": ["boolean", "null"]}

_PROVENANCE = {
    "type": "object",
    "additionalProperties": False,
    "required": ["source"],
    "properties": {
        "source": {"type": "string"},
        "source_id": {"type": ["string", "null"]},
        "retrieved_at": {"type": ["string", "null"]},
        "run_id": {"type": ["string", "null"]},
        "pipeline_version": {"type": ["string", "null"]},
        "git_commit": {"type": ["string", "null"]},
    },
}


def _enum(name: str) -> dict[str, Any]:
    return {"type": "string", "enum": list(ENUMS[name])}


def _enum_or_null(name: str) -> dict[str, Any]:
    return {"anyOf": [{"type": "null"}, {"type": "string", "enum": list(ENUMS[name])}]}


def _record(title: str, record_type: str, props: dict[str, Any]) -> dict[str, Any]:
    full = {
        "schema_version": {"const": SCHEMA_VERSION},
        "record_type": {"const": record_type},
        "uuid": _UUID,
        **props,
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": (
            "https://huggingface.co/datasets/wvanterola/esai_benchmark_map/"
            f"schema/{record_type}.schema.json"
        ),
        "title": title,
        "type": "object",
        "additionalProperties": False,
        "required": list(full.keys()),
        "properties": full,
    }


def build_schemas() -> dict[str, dict[str, Any]]:
    """Return {record_type: json_schema} for every record type."""
    schemas: dict[str, dict[str, Any]] = {}

    schemas["paper"] = _record(
        "ESAI paper (bibliographic provenance)",
        "paper",
        {
            "paper_id": _STR,
            "title": _STR,
            "abstract": _STR,
            "authors": _STR_ARRAY,
            "author_count": _INT_OR_NULL,
            "tldr": _STR,
            "keywords": _STR_ARRAY,
            "publication_date": _STR,
            "publication_date_basis": _STR,
            "year": _INT_OR_NULL,
            "venue": _STR,
            "venue_track": _STR,
            "decision": _STR,
            "paper_url": _STR,
            "pdf_url": _STR,
            "code_url": _STR,
            "external_ids": {
                "type": "object",
                "additionalProperties": False,
                "required": ["openreview", "pmlr", "doi"],
                "properties": {"openreview": _STR, "pmlr": _STR, "doi": _STR},
            },
            "provenance": _PROVENANCE,
        },
    )

    schemas["benchmark"] = _record(
        "ESAI benchmark (evaluation) entity",
        "benchmark",
        {
            "benchmark_id": _STR,
            "quick_ref": _STR,
            "title": _STR,
            "description": _STR,
            "task": _STR,
            "metric": _STR,
            "evidence_type": _enum_or_null("evidence_type"),
            "source_url": _STR,
            "source_abstract": _STR,
            "source_status": _enum("source_status"),
            "verified_at": _STR,
            "notes": _STR,
            "provenance": _PROVENANCE,
        },
    )

    schemas["harm"] = _record(
        "ESAI harm taxonomy node",
        "harm",
        {
            "harm_id": _STR,
            "label": _STR,
            "description": _STR,
            "domain": _STR,
            "subdomain": _STR,
            "taxonomy": _STR,
        },
    )

    schemas["benchmark_candidate"] = _record(
        "Screened benchmark candidate (paper -> candidate)",
        "benchmark_candidate",
        {
            "candidate_id": _STR,
            "paper_id": _STR,
            "paper_uuid": _UUID,
            "title": _STR,
            "description": _STR,
            "venue": _STR,
            "venue_track": _STR,
            "year": _INT_OR_NULL,
            "paper_url": _STR,
            "pdf_url": _STR,
            "doi": _STR,
            "screening_tier": _enum("screening_tier"),
            "screening_reason": _STR,
            "duplicate_key": _STR,
            "also_seen_at": _STR_ARRAY,
            "already_in_tracker": _BOOL_OR_NULL,
            "tracker_match": _STR,
            "tracker_match_method": _STR,
            "verification_status": _enum_or_null("verification_status"),
            "candidate_harm_ids": _STR_ARRAY,
            "candidate_harm_uuids": _UUID_ARRAY,
            "priority_risk": _STR,
            "risk_relevance_status": _STR,
            "review_status": _enum("review_status"),
            "provenance": _PROVENANCE,
        },
    )

    schemas["collection_review_row"] = _record(
        "Human collection-review row",
        "collection_review_row",
        {
            "candidate_id": _STR,
            "candidate_uuid": _UUID,
            "venue": _STR,
            "year": _INT_OR_NULL,
            "paper_url": _STR,
            "screening_tier": _enum("screening_tier"),
            "screening_reason": _STR,
            "suggested_quick_ref": _STR,
            "risk_relevance_status": _STR,
            "priority_risk": _STR,
            "candidate_harm_ids": _STR_ARRAY,
            "triage_notes": _STR,
            "review_status": _enum("review_status"),
            "reviewer": _STR,
            "review_notes": _STR,
            "benchmark": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "quick_ref",
                    "title",
                    "description",
                    "task",
                    "metric",
                    "communicated_metric",
                    "modality",
                    "interaction_horizon",
                    "aggregation_scale",
                    "version",
                    "notes",
                    "evidence_type",
                ],
                "properties": {
                    "quick_ref": _STR,
                    "title": _STR,
                    "description": _STR,
                    "task": _STR,
                    "metric": _STR,
                    "communicated_metric": _STR,
                    "modality": _STR,
                    "interaction_horizon": _STR,
                    "aggregation_scale": _STR,
                    "version": _STR,
                    "notes": _STR,
                    "evidence_type": _enum_or_null("evidence_type"),
                },
            },
            "provenance": _PROVENANCE,
        },
    )

    schemas["benchmark_harm_edge"] = _record(
        "Benchmark -> harm mapping edge",
        "benchmark_harm_edge",
        {
            "edge_id": _STR,
            "benchmark_id": _STR,
            "benchmark_uuid": _UUID,
            "harm_id": _STR,
            "harm_uuid": _UUID,
            "strength": _enum("strength"),
            "basis": _enum("basis"),
            "confidence": _enum("confidence"),
            "context_status": _enum("context_status"),
            "source_match_method": _STR,
            "notes": _STR,
        },
    )

    schemas["mapping_prediction"] = _record(
        "Validator assessment of a mapping edge",
        "mapping_prediction",
        {
            "edge_id": _STR,
            "edge_uuid": _UUID,
            "verdict": _enum("verdict"),
            "corrected_strength": _enum_or_null("strength"),
            "corrected_basis": _enum_or_null("basis"),
            "scored_construct": _STR,
            "confidence": _enum_or_null("confidence"),
            "needs_human_review": _BOOL_OR_NULL,
            "reason": _STR,
            "evidence_used": _STR,
            "inference_steps": _INT_OR_NULL,
            "parse_error": _STR,
            "raw_response": _STR,
            "assessor": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "assessor_type",
                    "assessor_name",
                    "model",
                    "prompt_name",
                    "prompt_sha256",
                    "created_at",
                ],
                "properties": {
                    "assessor_type": _enum_or_null("assessor_type"),
                    "assessor_name": _STR,
                    "model": _STR,
                    "prompt_name": _STR,
                    "prompt_sha256": _STR,
                    "created_at": _STR,
                },
            },
        },
    )

    schemas["mapping_review_row"] = _record(
        "Human-review row for a mapping edge",
        "mapping_review_row",
        {
            "edge_id": _STR,
            "edge_uuid": _UUID,
            "benchmark_id": _STR,
            "benchmark_uuid": _UUID,
            "harm_id": _STR,
            "harm_uuid": _UUID,
            "current_strength": _enum_or_null("strength"),
            "current_basis": _enum_or_null("basis"),
            "current_confidence": _enum_or_null("confidence"),
            "verdict": _enum("verdict"),
            "proposed_strength": _enum_or_null("strength"),
            "proposed_basis": _enum_or_null("basis"),
            "scored_construct": _STR,
            "confidence": _enum_or_null("confidence"),
            "reason": _STR,
            "evidence_used": _STR,
            "inference_steps": _INT_OR_NULL,
            "needs_human_review": _BOOL_OR_NULL,
            "assessor": {
                "type": "object",
                "additionalProperties": False,
                "required": ["assessor_type", "assessor_name"],
                "properties": {
                    "assessor_type": _enum_or_null("assessor_type"),
                    "assessor_name": _STR,
                },
            },
            "review": {
                "type": "object",
                "additionalProperties": False,
                "required": ["review_status", "reviewer", "review_notes"],
                "properties": {
                    "review_status": _enum("review_status"),
                    "reviewer": _STR,
                    "review_notes": _STR,
                },
            },
        },
    )

    return schemas


# --- File layout -------------------------------------------------------------
# Each entry: record_type -> (relative path, primary key fields, kind).

FILES: dict[str, tuple[str, list[str], str]] = {
    "paper": ("data/papers.jsonl", ["paper_id"], "entity"),
    "benchmark": ("data/benchmarks.jsonl", ["benchmark_id"], "entity"),
    "harm": ("data/harms.jsonl", ["harm_id"], "entity"),
    "benchmark_candidate": (
        "data/benchmark_candidates.jsonl",
        ["candidate_id"],
        "relationship",
    ),
    "collection_review_row": (
        "data/collection_review_queue.jsonl",
        ["candidate_id"],
        "annotation",
    ),
    "benchmark_harm_edge": (
        "data/benchmark_harm_edges.jsonl",
        ["edge_id"],
        "relationship",
    ),
    "mapping_prediction": (
        "data/mapping_predictions.jsonl",
        ["edge_id", "assessor.assessor_name"],
        "annotation",
    ),
    "mapping_review_row": (
        "data/mapping_review.jsonl",
        ["edge_id", "assessor.assessor_name"],
        "annotation",
    ),
}

# Declared cross-file references (foreign key -> target). Checked by the
# validator for referential integrity.
REFERENCES: list[dict[str, str]] = [
    {"from": "benchmark_candidate.paper_uuid", "to": "paper.uuid"},
    {"from": "benchmark_harm_edge.benchmark_uuid", "to": "benchmark.uuid"},
    {"from": "benchmark_harm_edge.harm_uuid", "to": "harm.uuid"},
    {"from": "collection_review_row.candidate_uuid", "to": "benchmark_candidate.uuid"},
    {"from": "mapping_prediction.edge_uuid", "to": "benchmark_harm_edge.uuid"},
    {"from": "mapping_review_row.edge_uuid", "to": "benchmark_harm_edge.uuid"},
]


# --- Value coercion ----------------------------------------------------------


def _text(value: object) -> str:
    return str(value or "").strip()


def _or_none(value: object) -> str | None:
    text = _text(value)
    return text or None


def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    text = _text(value)
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _str_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [_text(v) for v in value if _text(v)]
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


def _head(record: Mapping[str, object], record_type: str, key: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "record_type": record_type,
        "uuid": record_uuid(record_type, key),
    }


# --- Record transforms (v0.1.0 record -> v1.0.0 record) ----------------------


def paper_v1(row: Mapping[str, object]) -> dict[str, Any]:
    paper_id = _text(row.get("paper_id"))
    rec = _head(row, "paper", paper_id)
    rec.update(
        paper_id=paper_id,
        title=_text(row.get("title")),
        abstract=_text(row.get("abstract")),
        authors=_str_list(row.get("authors")),
        author_count=_int_or_none(row.get("author_count")),
        tldr=_text(row.get("tldr")),
        keywords=_str_list(row.get("keywords")),
        publication_date=_text(row.get("publication_date")),
        publication_date_basis=_text(row.get("publication_date_basis")),
        year=_int_or_none(row.get("year")),
        venue=_text(row.get("venue")),
        venue_track=_text(row.get("venue_track")),
        decision=_text(row.get("decision")),
        paper_url=_text(row.get("paper_url")),
        pdf_url=_text(row.get("pdf_url")),
        code_url=_text(row.get("code_url")),
        external_ids={
            "openreview": _text(row.get("openreview_id")),
            "pmlr": _text(row.get("pmlr_id")),
            "doi": _text(row.get("doi")),
        },
        provenance={
            "source": _text(row.get("source")),
            "source_id": _or_none(row.get("source_id")),
            "retrieved_at": _or_none(row.get("collected_at")),
            "run_id": _or_none(row.get("run_id")),
            "pipeline_version": None,
            "git_commit": None,
        },
    )
    return rec


def harm_v1(agg: Mapping[str, object]) -> dict[str, Any]:
    harm_id = _text(agg.get("harm_id"))
    rec = _head(agg, "harm", harm_id)
    rec.update(
        harm_id=harm_id,
        label=_text(agg.get("harm_label")),
        description=_text(agg.get("harm_description")),
        domain=_text(agg.get("harm_domain")),
        subdomain=_text(agg.get("harm_subdomain")),
        taxonomy="esai-harm-taxonomy",
    )
    return rec


def benchmark_v1(agg: Mapping[str, object]) -> dict[str, Any]:
    benchmark_id = _text(agg.get("benchmark_id"))
    rec = _head(agg, "benchmark", benchmark_id)
    rec.update(
        benchmark_id=benchmark_id,
        quick_ref=_text(agg.get("quick_ref")),
        title=_text(agg.get("title")),
        description=_text(agg.get("description")),
        task=_text(agg.get("task")),
        metric=_text(agg.get("metric")),
        evidence_type=_or_none(agg.get("evidence_type")),
        source_url=_text(agg.get("source_url")),
        source_abstract=_text(agg.get("source_abstract")),
        source_status=_text(agg.get("source_status")) or "pending",
        verified_at=_text(agg.get("verified_at")),
        notes=_text(agg.get("notes")),
        provenance={
            "source": "esai-tracker",
            "source_id": benchmark_id,
            "retrieved_at": None,
            "run_id": None,
            "pipeline_version": None,
            "git_commit": None,
        },
    )
    return rec


def candidate_v1(
    row: Mapping[str, object], harm_uuid_of: Mapping[str, str]
) -> dict[str, Any]:
    candidate_id = _text(row.get("candidate_id"))
    paper_id = _text(row.get("paper_id"))
    harm_ids = _str_list(row.get("candidate_harm_ids"))
    rec = _head(row, "benchmark_candidate", candidate_id)
    rec.update(
        candidate_id=candidate_id,
        paper_id=paper_id,
        paper_uuid=record_uuid("paper", paper_id),
        title=_text(row.get("title")),
        description=_text(row.get("description")),
        venue=_text(row.get("venue")),
        venue_track=_text(row.get("venue_track")),
        year=_int_or_none(row.get("year")),
        paper_url=_text(row.get("paper_url")),
        pdf_url=_text(row.get("pdf_url")),
        doi=_text(row.get("doi")),
        screening_tier=_text(row.get("screening_tier")),
        screening_reason=_text(row.get("screening_reason")),
        duplicate_key=_text(row.get("duplicate_key")),
        also_seen_at=_str_list(row.get("also_seen_at")),
        already_in_tracker=_bool_or_none(row.get("already_in_tracker")),
        tracker_match=_text(row.get("tracker_match")),
        tracker_match_method=_text(row.get("tracker_match_method")),
        verification_status=_or_none(row.get("verification_status")),
        candidate_harm_ids=harm_ids,
        candidate_harm_uuids=[harm_uuid_of[h] for h in harm_ids if h in harm_uuid_of],
        priority_risk=_text(row.get("priority_risk")),
        risk_relevance_status=_text(row.get("risk_relevance_status")),
        review_status=_text(row.get("review_status")),
        provenance={
            "source": _text(row.get("source")),
            "source_id": _or_none(row.get("source_id")),
            "retrieved_at": None,
            "run_id": None,
            "pipeline_version": None,
            "git_commit": None,
        },
    )
    return rec


def collection_review_v1(row: Mapping[str, object]) -> dict[str, Any]:
    candidate_id = _text(row.get("candidate_id"))
    rec = _head(row, "collection_review_row", candidate_id)
    rec.update(
        candidate_id=candidate_id,
        candidate_uuid=record_uuid("benchmark_candidate", candidate_id),
        venue=_text(row.get("venue")),
        year=_int_or_none(row.get("year")),
        paper_url=_text(row.get("paper_url")),
        screening_tier=_text(row.get("screening_tier")),
        screening_reason=_text(row.get("screening_reason")),
        suggested_quick_ref=_text(row.get("suggested_quick_ref")),
        risk_relevance_status=_text(row.get("risk_relevance_status")),
        priority_risk=_text(row.get("priority_risk")),
        candidate_harm_ids=_str_list(row.get("candidate_harm_ids")),
        triage_notes=_text(row.get("triage_notes")),
        review_status=_text(row.get("review_status")),
        reviewer=_text(row.get("reviewer")),
        review_notes=_text(row.get("review_notes")),
        benchmark={
            "quick_ref": _text(row.get("benchmark_quick_ref")),
            "title": _text(row.get("benchmark_title")),
            "description": _text(row.get("benchmark_description")),
            "task": _text(row.get("benchmark_task")),
            "metric": _text(row.get("benchmark_metric")),
            "communicated_metric": _text(row.get("benchmark_communicated_metric")),
            "modality": _text(row.get("benchmark_modality")),
            "interaction_horizon": _text(row.get("benchmark_interaction_horizon")),
            "aggregation_scale": _text(row.get("benchmark_aggregation_scale")),
            "version": _text(row.get("benchmark_version")),
            "notes": _text(row.get("benchmark_notes")),
            "evidence_type": _or_none(row.get("benchmark_evidence_type")),
        },
        provenance={
            "source": _text(row.get("source")),
            "source_id": _or_none(row.get("source_id")),
            "retrieved_at": None,
            "run_id": None,
            "pipeline_version": None,
            "git_commit": None,
        },
    )
    return rec


def edge_v1(row: Mapping[str, object]) -> dict[str, Any]:
    edge_id = _text(row.get("edge_id"))
    benchmark_id = _text(row.get("benchmark_id"))
    harm_id = _text(row.get("harm_id"))
    rec = _head(row, "benchmark_harm_edge", edge_id)
    rec.update(
        edge_id=edge_id,
        benchmark_id=benchmark_id,
        benchmark_uuid=record_uuid("benchmark", benchmark_id),
        harm_id=harm_id,
        harm_uuid=record_uuid("harm", harm_id),
        strength=_text(row.get("strength")),
        basis=_text(row.get("basis")),
        confidence=_text(row.get("confidence")),
        context_status=_text(row.get("context_status")),
        source_match_method=_text(row.get("source_match_method")),
        notes=_text(row.get("notes")),
    )
    return rec


def prediction_v1(row: Mapping[str, object]) -> dict[str, Any]:
    edge_id = _text(row.get("edge_id"))
    assessor_name = _text(row.get("validator_name"))
    rec = _head(row, "mapping_prediction", f"{edge_id}|{assessor_name}")
    rec.update(
        edge_id=edge_id,
        edge_uuid=record_uuid("benchmark_harm_edge", edge_id),
        verdict=_text(row.get("verdict")),
        corrected_strength=_or_none(row.get("corrected_strength")),
        corrected_basis=_or_none(row.get("corrected_basis")),
        scored_construct=_text(row.get("scored_construct")),
        confidence=_or_none(row.get("confidence")),
        needs_human_review=_bool_or_none(row.get("needs_human_review")),
        reason=_text(row.get("reason")),
        evidence_used=_text(row.get("evidence_used")),
        inference_steps=_int_or_none(row.get("inference_steps")),
        parse_error=_text(row.get("parse_error")),
        raw_response=_text(row.get("raw_response")),
        assessor={
            "assessor_type": _or_none(row.get("validator_type")),
            "assessor_name": assessor_name,
            "model": _text(row.get("model")),
            "prompt_name": _text(row.get("prompt_name")),
            "prompt_sha256": _text(row.get("prompt_sha256")),
            "created_at": _text(row.get("created_at")),
        },
    )
    return rec


def review_edge_v1(row: Mapping[str, object]) -> dict[str, Any]:
    edge_id = _text(row.get("edge_id"))
    assessor_name = _text(row.get("validator_name"))
    benchmark_id = _text(row.get("benchmark_id"))
    harm_id = _text(row.get("harm_id"))
    rec = _head(row, "mapping_review_row", f"{edge_id}|{assessor_name}")
    rec.update(
        edge_id=edge_id,
        edge_uuid=record_uuid("benchmark_harm_edge", edge_id),
        benchmark_id=benchmark_id,
        benchmark_uuid=record_uuid("benchmark", benchmark_id),
        harm_id=harm_id,
        harm_uuid=record_uuid("harm", harm_id),
        current_strength=_or_none(row.get("current_strength")),
        current_basis=_or_none(row.get("current_basis")),
        current_confidence=_or_none(row.get("current_confidence")),
        verdict=_text(row.get("verdict")),
        proposed_strength=_or_none(row.get("proposed_strength")),
        proposed_basis=_or_none(row.get("proposed_basis")),
        scored_construct=_text(row.get("scored_construct")),
        confidence=_or_none(row.get("confidence")),
        reason=_text(row.get("reason")),
        evidence_used=_text(row.get("evidence_used")),
        inference_steps=_int_or_none(row.get("inference_steps")),
        needs_human_review=_bool_or_none(row.get("needs_human_review")),
        assessor={
            "assessor_type": "deterministic"
            if assessor_name.startswith("deterministic-")
            else ("model" if assessor_name else None),
            "assessor_name": assessor_name,
        },
        review={
            "review_status": _text(row.get("review_status")),
            "reviewer": _text(row.get("reviewer")),
            "review_notes": _text(row.get("review_notes")),
        },
    )
    return rec


def normalize_harms(edges: list[Mapping[str, object]]) -> list[dict[str, Any]]:
    """Extract one harm entity per distinct harm_id from denormalized edges."""
    seen: dict[str, dict[str, Any]] = {}
    for edge in edges:
        harm_id = _text(edge.get("harm_id"))
        if not harm_id or harm_id in seen:
            continue
        seen[harm_id] = harm_v1(edge)
    return [seen[k] for k in sorted(seen)]


def normalize_benchmarks(
    sources: list[Mapping[str, object]], edges: list[Mapping[str, object]]
) -> list[dict[str, Any]]:
    """Union the source registry with benchmark metadata carried on edges."""
    agg: dict[str, dict[str, object]] = {}

    def slot(bid: str) -> dict[str, object]:
        return agg.setdefault(bid, {"benchmark_id": bid})

    for src in sources:
        bid = _text(src.get("benchmark_id"))
        if not bid:
            continue
        slot(bid).update(
            title=_text(src.get("title")),
            quick_ref=_text(src.get("quick_ref")),
            source_url=_text(src.get("source_url")),
            source_abstract=_text(src.get("source_abstract")),
            source_status=_text(src.get("source_status")),
            verified_at=_text(src.get("verified_at")),
            notes=_text(src.get("notes")),
        )
    for edge in edges:
        bid = _text(edge.get("benchmark_id"))
        if not bid:
            continue
        cur = slot(bid)
        # Edges carry richer benchmark metadata; fill only missing fields.
        for dst, key in (
            ("title", "benchmark_title"),
            ("quick_ref", "benchmark_quick_ref"),
            ("description", "benchmark_description"),
            ("task", "benchmark_task"),
            ("metric", "benchmark_metric"),
            ("evidence_type", "benchmark_evidence_type"),
            ("source_url", "benchmark_source_url"),
        ):
            if not _text(cur.get(dst)):
                value = _text(edge.get(key))
                if value:
                    cur[dst] = value
    return [benchmark_v1(agg[bid]) for bid in sorted(agg)]
