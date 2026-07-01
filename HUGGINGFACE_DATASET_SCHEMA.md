# HuggingFace dataset schema

This package can export the collection and mapping work as a HuggingFace-ready JSONL directory:

```bash
esai-collect export-hf-dataset \
  --papers outputs/latest/papers_raw.csv \
  --candidates outputs/latest/benchmark_candidates.csv \
  --review-queue outputs/latest/tracker_review_queue.csv \
  --mapping-edges ../mapping-validation/outputs/hardened/all_edges.csv \
  --source-registry ../mapping-validation/outputs/hardened/benchmark_sources.csv \
  --outdir outputs/hf_dataset
```

The format borrows two practical ideas from EvalEval's Every Eval Ever schema:

- version every record and keep stable IDs;
- separate aggregate/provenance records from more detailed downstream records.

This project is not storing model-evaluation scores, so it uses flat JSONL tables rather than
EvalEval's run-level and instance-level score files.

## Files

| File | Unit | Primary key | Purpose |
|---|---|---|---|
| `papers.jsonl` | accepted paper | `paper_id` | Authoritative paper provenance from OpenReview, PMLR, ACL handoff, or future accepted-paper sources. |
| `benchmark_candidates.jsonl` | screened candidate | `candidate_id` | Deduplicated benchmark candidates and screening evidence. |
| `collection_review_queue.jsonl` | review row | `candidate_id` | Human review fields for benchmark inclusion and risk triage. |
| `benchmark_harm_edges.jsonl` | mapping edge | `edge_id` | Current benchmark-to-harm relations with source context. |
| `benchmark_sources.jsonl` | benchmark source record | `benchmark_id` | Source-verification status for benchmarks already in the tracker. |
| `schema.json` | schema manifest | none | Field lists, primary keys, and schema version. |
| `README.md` | dataset card | none | HuggingFace dataset card stub with row counts. |

## Record rules

- Every row has `schema_version` and `record_type`.
- Empty unknown values are empty strings in CSV inputs and become empty strings or `null` in JSONL
  where a numeric or boolean value is expected.
- Semicolon-separated CSV fields such as `authors`, `keywords`, `candidate_harm_ids`, and
  `also_seen_at` become JSON arrays.
- `paper_id`, `candidate_id`, `edge_id`, and `benchmark_id` are stable identifiers, not row
  numbers.
- ACL Anthology output should enter through the shared raw schema first, then the exported dataset
  should be regenerated from the merged candidate catalog.

## Minimal record examples

```json
{
  "schema_version": "0.1.0",
  "record_type": "paper",
  "paper_id": "openreview:abc123",
  "source": "openreview",
  "source_id": "abc123",
  "title": "Example Safety Benchmark",
  "authors": ["First Author", "Second Author"],
  "year": 2025,
  "venue": "ICLR",
  "paper_url": "https://openreview.net/forum?id=abc123"
}
```

```json
{
  "schema_version": "0.1.0",
  "record_type": "benchmark_harm_edge",
  "edge_id": "edge-001",
  "benchmark_id": "bench-001",
  "harm_id": "harm-001",
  "strength": "strong-proxy",
  "basis": "face-validity-only",
  "confidence": "possible"
}
```

## Loading locally

Each file can be loaded as a separate HuggingFace config:

```python
from datasets import load_dataset

papers = load_dataset("json", data_files="papers.jsonl", split="train")
edges = load_dataset("json", data_files="benchmark_harm_edges.jsonl", split="train")
```
