# HuggingFace dataset schema

The published dataset (`wvanterola/esai_benchmark_map`) uses the **v1.0.0**
format. It maps AI-safety **benchmarks** to a **harm taxonomy** and keeps the
collection and mapping-review provenance alongside.

The format follows the design discipline of EvalEval's *Every Eval Ever* schema
without copying its result-oriented fields (this dataset stores a
benchmark-to-harm map, not model scores):

- **stable UUID identity** (deterministic UUIDv5 from a fixed namespace);
- **normalized entities** (`paper`, `benchmark`, `harm`) separated from the
  **relationships** and **annotations** that connect them;
- **layered provenance** as a nested `provenance` object on entities;
- **closed controlled vocabularies** for grading and status fields;
- a **checksummed manifest** (`dataset_manifest.json`) that declares per-file
  `sha256`, row counts, primary keys, and cross-file references.

The canonical, generated specification ships inside the dataset as `SCHEMA.md`,
with machine-readable JSON Schema under `schema/`. `esai_collection/dataset_v1.py`
is the single source of truth: it generates both the JSON Schema and the record
transforms, so an emitted dataset cannot drift from its schema.

## Package layout

```
README.md               dataset card (HF configs -> data/*.jsonl)
SCHEMA.md               generated specification (fields, enums, references)
dataset_manifest.json   checksums, counts, primary keys, references
data/*.jsonl            one config per file
schema/*.schema.json    JSON Schema per record type
```

## Files

| File | Record type | Primary key | Kind |
|---|---|---|---|
| `data/papers.jsonl` | `paper` | `paper_id` | entity |
| `data/benchmarks.jsonl` | `benchmark` | `benchmark_id` | entity |
| `data/harms.jsonl` | `harm` | `harm_id` | entity |
| `data/benchmark_candidates.jsonl` | `benchmark_candidate` | `candidate_id` | relationship |
| `data/collection_review_queue.jsonl` | `collection_review_row` | `candidate_id` | annotation |
| `data/benchmark_harm_edges.jsonl` | `benchmark_harm_edge` | `edge_id` | relationship |
| `data/mapping_predictions.jsonl` | `mapping_prediction` | `edge_id` + assessor | annotation |
| `data/mapping_review.jsonl` | `mapping_review_row` | `edge_id` + assessor | annotation |

## Build and validate

Build a v1.0.0 package from a v0.1.0 export:

```bash
python scripts/build_dataset_v1.py \
  --in  outputs/hf_upload_esai_benchmark_map_2026_07_01_final \
  --out outputs/hf_upload_esai_benchmark_map_v1 \
  --dataset-name esai_benchmark_map
```

Validate a package (checksums, JSON Schema, primary keys, referential integrity):

```bash
python scripts/validate_dataset_v1.py --dir outputs/hf_upload_esai_benchmark_map_v1
```

`validate_dataset_v1.py` requires `jsonschema`; without it the structural and
referential checks still run and schema validation is skipped with a warning.

## Publishing

```bash
hf upload wvanterola/esai_benchmark_map \
  outputs/hf_upload_esai_benchmark_map_v1 . --repo-type=dataset
```

`mapping_predictions` and `mapping_review` are validator and human-review aids,
not final tracker decisions. Human approval is required before applying any
mapping change.

## Migrating from v0.1.0

v0.1.0 was a set of flat JSONL tables that denormalized benchmark and harm
metadata onto every edge and review row. v1.0.0 is a breaking change:

- `benchmark_sources.jsonl` becomes the `benchmark` entity, enriched with the
  benchmark metadata that previously lived only on edges;
- a new `harms.jsonl` entity is normalized out of the edge harm fields;
- edges and review rows reference entities by `*_uuid` instead of repeating
  their descriptive fields;
- `mapping_predictions` / `mapping_review` fold validator identity into a nested
  `assessor` object;
- files move under `data/`, and `schema.json` is replaced by
  `dataset_manifest.json` + `schema/`.

Regenerate with `build_dataset_v1.py`; there is no in-place upgrade.
