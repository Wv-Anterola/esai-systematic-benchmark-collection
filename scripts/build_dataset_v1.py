#!/usr/bin/env python3
"""Build a v1.0.0 ESAI benchmark-map dataset package from a v0.1.0 export.

Reads the flat v0.1.0 JSONL export (papers, benchmark_candidates,
collection_review_queue, benchmark_harm_edges, benchmark_sources,
mapping_predictions, mapping_review) and writes a v1.0.0 package:

    <outdir>/
      README.md                 dataset card (HF configs point at data/*.jsonl)
      SCHEMA.md                 generated human-readable specification
      dataset_manifest.json     per-file checksums, counts, cross-references
      data/*.jsonl              normalized records
      schema/*.schema.json      one JSON Schema per record type

Usage:
    python scripts/build_dataset_v1.py --in <v0_dir> --out <v1_dir> \
        [--dataset-name esai_benchmark_map]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from esai_collection import dataset_v1 as d1  # noqa: E402


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_records(v0: Path) -> dict[str, list[dict]]:
    papers_v0 = _load_jsonl(v0 / "papers.jsonl")
    candidates_v0 = _load_jsonl(v0 / "benchmark_candidates.jsonl")
    review_v0 = _load_jsonl(v0 / "collection_review_queue.jsonl")
    edges_v0 = _load_jsonl(v0 / "benchmark_harm_edges.jsonl")
    sources_v0 = _load_jsonl(v0 / "benchmark_sources.jsonl")
    preds_v0 = _load_jsonl(v0 / "mapping_predictions.jsonl")
    mreview_v0 = _load_jsonl(v0 / "mapping_review.jsonl")

    harms = d1.normalize_harms(edges_v0)
    harm_uuid_of = {h["harm_id"]: h["uuid"] for h in harms}
    benchmarks = d1.normalize_benchmarks(sources_v0, edges_v0)

    return {
        "paper": [d1.paper_v1(r) for r in papers_v0],
        "benchmark": benchmarks,
        "harm": harms,
        "benchmark_candidate": [
            d1.candidate_v1(r, harm_uuid_of) for r in candidates_v0
        ],
        "collection_review_row": [d1.collection_review_v1(r) for r in review_v0],
        "benchmark_harm_edge": [d1.edge_v1(r) for r in edges_v0],
        "mapping_prediction": [d1.prediction_v1(r) for r in preds_v0],
        "mapping_review_row": [d1.review_edge_v1(r) for r in mreview_v0],
    }


def _write_schemas(outdir: Path) -> None:
    schema_dir = outdir / "schema"
    schema_dir.mkdir(parents=True, exist_ok=True)
    for record_type, schema in d1.build_schemas().items():
        path = schema_dir / f"{record_type}.schema.json"
        path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")


def _write_manifest(
    outdir: Path, *, dataset_name: str, records: dict[str, list[dict]]
) -> None:
    files: dict[str, dict] = {}
    for record_type, (rel, pk, kind) in d1.FILES.items():
        path = outdir / rel
        files[rel] = {
            "record_type": record_type,
            "schema": f"schema/{record_type}.schema.json",
            "primary_key": pk,
            "kind": kind,
            "rows": len(records[record_type]),
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
    manifest = {
        "schema_version": d1.SCHEMA_VERSION,
        "dataset_name": dataset_name,
        "namespace_uuid": str(d1.NAMESPACE),
        "created_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "generator": {
            "tool": "build_dataset_v1.py",
            "source_schema_version": d1.SOURCE_SCHEMA_VERSION,
        },
        "controlled_vocabularies": d1.ENUMS,
        "files": files,
        "references": d1.REFERENCES,
    }
    (outdir / "dataset_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _config_block() -> str:
    lines = []
    for _record_type, (rel, _pk, _kind) in d1.FILES.items():
        name = Path(rel).stem
        lines.append(f"  - config_name: {name}")
        lines.append("    data_files:")
        lines.append("      - split: train")
        lines.append(f"        path: {rel}")
    return "\n".join(lines)


def _write_card(
    outdir: Path, *, dataset_name: str, records: dict[str, list[dict]]
) -> None:
    rows_table = "\n".join(
        f"| `{rel}` | {record_type} | {', '.join(pk)} | {kind} | "
        f"{len(records[record_type])} |"
        for record_type, (rel, pk, kind) in d1.FILES.items()
    )
    body = f"""---
license: other
language:
  - en
pretty_name: ESAI Benchmark Map
task_categories:
  - text-classification
  - tabular-classification
tags:
  - ai-safety
  - benchmarks
  - risk-taxonomy
  - knowledge-graph
configs:
{_config_block()}
---

# {dataset_name}

Schema version: `{d1.SCHEMA_VERSION}`

A map of AI-safety **benchmarks** to a **harm taxonomy**. The dataset separates
normalized entities (papers, benchmarks, harms) from the relationships and
assessments that connect them, following the design discipline of EvalEval's
*Every Eval Ever* schema: stable UUID identity, layered provenance, closed
controlled vocabularies, and a checksummed manifest that declares cross-file
references.

## Files

| File | Record type | Primary key | Kind | Rows |
|---|---|---|---|---:|
{rows_table}

Entities carry a deterministic `uuid` (UUIDv5 from `{d1.NAMESPACE}`). Relationship
and annotation records reference entities by `*_uuid`. See `SCHEMA.md` for the
full specification, `schema/` for machine-readable JSON Schema, and
`dataset_manifest.json` for checksums and declared references.

## Loading

```python
from datasets import load_dataset

benchmarks = load_dataset("{dataset_name}", "benchmarks", split="train")
edges = load_dataset("{dataset_name}", "benchmark_harm_edges", split="train")
```

## Use notes

`mapping_predictions` and `mapping_review` are validator and human-review aids,
not final tracker decisions. Human approval is required before applying any
mapping change.
"""
    (outdir / "README.md").write_text(body, encoding="utf-8")


def _field_type(spec: dict) -> str:
    if "const" in spec:
        return f"const `{spec['const']}`"
    if "enum" in spec:
        return "enum"
    if "anyOf" in spec:
        parts = [_field_type(s) for s in spec["anyOf"]]
        return " or ".join(parts)
    if "pattern" in spec:
        return "uuid"
    typ = spec.get("type")
    if typ == "array":
        return f"array<{_field_type(spec.get('items', {}))}>"
    if typ == "object":
        return "object"
    if isinstance(typ, list):
        return "|".join(typ)
    return str(typ)


def _write_spec(outdir: Path, *, dataset_name: str) -> None:
    schemas = d1.build_schemas()
    out = [
        f"# {dataset_name} data format",
        "",
        f"Schema version: `{d1.SCHEMA_VERSION}` "
        f"(supersedes `{d1.SOURCE_SCHEMA_VERSION}`).",
        "",
        "## Design",
        "",
        "This format is a redesign of the flat v0.1.0 tables toward the design "
        "discipline of EvalEval's *Every Eval Ever* schema:",
        "",
        "- **Stable identity.** Every record has a `uuid` computed as "
        "`uuid5(namespace, \"{record_type}:{natural_key}\")` with a fixed "
        f"namespace `{d1.NAMESPACE}`, so IDs are reproducible and "
        "conflict-free.",
        "- **Normalized entities.** `benchmark` and `harm` are first-class "
        "entity tables. Relationship and annotation records reference them by "
        "`*_uuid` instead of duplicating their descriptive fields.",
        "- **Layered provenance.** Entities carry a nested `provenance` object "
        "(`source`, `source_id`, `retrieved_at`, `run_id`, `pipeline_version`, "
        "`git_commit`).",
        "- **Closed vocabularies.** Grading and status fields use the enums "
        "below.",
        "- **Checksummed manifest.** `dataset_manifest.json` records per-file "
        "`sha256`, row counts, primary keys, and declared cross-file "
        "references.",
        "",
        "## Layout",
        "",
        "```",
        "README.md               dataset card",
        "SCHEMA.md               this specification",
        "dataset_manifest.json   checksums, counts, references",
        "data/*.jsonl            records (one config per file)",
        "schema/*.schema.json    JSON Schema per record type",
        "```",
        "",
        "## Files",
        "",
        "| File | Record type | Primary key | Kind |",
        "|---|---|---|---|",
    ]
    for record_type, (rel, pk, kind) in d1.FILES.items():
        out.append(f"| `{rel}` | `{record_type}` | {', '.join(pk)} | {kind} |")
    out += ["", "## Controlled vocabularies", ""]
    for name, values in d1.ENUMS.items():
        shown = ", ".join(f"`{v}`" if v else "`` (empty)" for v in values)
        out.append(f"- **{name}**: {shown}")
    out += ["", "## Cross-file references", ""]
    for ref in d1.REFERENCES:
        out.append(f"- `{ref['from']}` -> `{ref['to']}`")
    out += ["", "## Record fields", ""]
    for record_type, schema in schemas.items():
        out.append(f"### `{record_type}`")
        out.append("")
        out.append("| Field | Type | Required |")
        out.append("|---|---|---|")
        required = set(schema.get("required", []))
        for field, spec in schema["properties"].items():
            out.append(
                f"| `{field}` | {_field_type(spec)} | "
                f"{'yes' if field in required else 'no'} |"
            )
        out.append("")
    (outdir / "SCHEMA.md").write_text("\n".join(out) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="indir", required=True, type=Path)
    parser.add_argument("--out", dest="outdir", required=True, type=Path)
    parser.add_argument("--dataset-name", default="esai_benchmark_map")
    args = parser.parse_args()

    records = build_records(args.indir)
    args.outdir.mkdir(parents=True, exist_ok=True)
    for record_type, (rel, _pk, _kind) in d1.FILES.items():
        _write_jsonl(args.outdir / rel, records[record_type])
    _write_schemas(args.outdir)
    _write_manifest(args.outdir, dataset_name=args.dataset_name, records=records)
    _write_card(args.outdir, dataset_name=args.dataset_name, records=records)
    _write_spec(args.outdir, dataset_name=args.dataset_name)

    print(f"Wrote v{d1.SCHEMA_VERSION} package to {args.outdir}")
    for record_type, (rel, _pk, _kind) in d1.FILES.items():
        print(f"  {rel:42s} {len(records[record_type]):>7d} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
