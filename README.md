# ESAI systematic benchmark collection

This package collects accepted papers from in-scope venues, screens them for benchmark candidates,
and prepares review files for the ESAI tracker. It keeps venue collection separate from optional
metadata enrichment so the provenance of accepted papers stays clear.

The scope owned here is:

- ICLR, NeurIPS, and COLM through OpenReview;
- ICML through the official Proceedings of Machine Learning Research volumes;
- the major ACL Anthology venue families through the Anthology's own XML/venue metadata.

All sources emit the same raw schema and flow through one screening/review/export pipeline.
[SCHEMA.md](SCHEMA.md) defines the raw-data contract and [SOURCE_ADAPTERS.md](SOURCE_ADAPTERS.md)
explains how to add future sources without changing the pipeline.

## Installation

Python 3.11 or newer is required.

```bash
python -m pip install -e ".[dev]"
```

OpenReview credentials are optional. Anonymous access works; `OPENREVIEW_USERNAME` and
`OPENREVIEW_PASSWORD` may improve rate limits.

## Run the pipeline

```bash
esai-collect run \
  --workbook "path/to/workbook.xlsx" \
  --outdir outputs/latest
```

The command writes:

| File | Purpose |
|---|---|
| `papers_raw.csv` | Every accepted paper returned by successful in-scope source queries. |
| `collection_log.csv` | Every source attempt, with `ok`, `empty`, or `error` status. |
| `benchmark_candidates.csv` | Deduplicated candidates, screening evidence, and tracker matches. |
| `tracker_review_queue.csv` | High- and medium-tier candidates for human coding and risk triage. |
| `run_manifest.json` | Scope, parameters, Git state, workbook hash, output hashes, and counts. |

Low-tier candidates remain in the candidate catalog. Add `--include-low` to include them in the
review queue for a recall audit.

Source-specific and staged commands are also available:

```bash
esai-collect collect-openreview
esai-collect collect-icml
esai-collect collect-acl
esai-collect merge outputs/openreview_raw.csv outputs/icml_raw.csv outputs/acl_raw.csv
esai-collect screen \
  --input outputs/papers_raw.csv \
  --workbook "path/to/workbook.xlsx"
```

Every staged command writes a hash manifest beside its primary output.

`collect-acl` parses a local ACL Anthology `data/` checkout. Install `acl-anthology-py` and fetch
the corpus once (`python -c "from acl_anthology import Anthology; Anthology.from_repo()"`), or point
`--data-dir` / the `ACL_ANTHOLOGY_DATA` environment variable at any checkout of
`acl-org/acl-anthology/data`. The full `run` pipeline includes ACL by default; add `--skip-acl` to
omit it (for example when the Anthology data is not available).

## Optional sidecars

These commands do not change `papers_raw.csv` or the tracker export. They create separate files
for review and triage.

```bash
esai-collect enrich-metadata \
  --input outputs/benchmark_candidates.csv \
  --providers semantic-scholar,openalex \
  --limit 500 \
  --out outputs/metadata_enrichment.csv

esai-collect discover-hf-datasets \
  --candidates outputs/benchmark_candidates.csv \
  --queries "safety benchmark,red teaming,llm benchmark" \
  --max-candidate-queries 100 \
  --out outputs/hf_dataset_discovery.csv

esai-collect sample-recall-audit \
  --candidates outputs/benchmark_candidates.csv \
  --size 200 \
  --out outputs/low_tier_recall_audit.csv
```

`enrich-metadata` uses Semantic Scholar and OpenAlex to backfill abstracts, identifiers, citations,
open-access links, and venue/source metadata. `discover-hf-datasets` creates an artifact-discovery
queue from Hugging Face Hub dataset search. `sample-recall-audit` samples low-tier candidates so
screening recall can be measured by review instead of assumption.

## Review and tracker export

For each review-queue row, the reviewer determines whether the paper actually contributes a
benchmark relevant to the risk taxonomy. An approved included row must contain:

- `risk_relevance_status=include`;
- `priority_risk=yes` or `no`;
- candidate harm IDs and a triage rationale;
- a confirmed quick reference, description, task, metric, and communicated metric;
- a named reviewer.

`suggested_quick_ref` is only a drafting aid. Copy or correct it in `quick ref` after checking for
tracker collisions. Rows coded `risk_relevance_status=exclude` are retained in the review file but
are not exported.

```bash
esai-collect export \
  --review-queue outputs/tracker_review_queue.csv \
  --workbook "path/to/workbook.xlsx" \
  --out outputs/tracker_benchmarks.csv \
  --mapping-out outputs/tracker_mapping_handoff.csv
```

`tracker_benchmarks.csv` has exactly the 13 columns in the workbook's `benchmarks` sheet.
`tracker_mapping_handoff.csv` preserves candidate harm IDs and risk-triage evidence so mapping
work can continue after the tracker owner assigns benchmark IDs. Incomplete approved rows are
rejected rather than partially exported.

## Integration package

To clean the collection rows and package mapping-validation outputs for a shared-sheet update:

```bash
esai-collect prepare-sheet-package \
  --review-queue outputs/latest/tracker_review_queue.csv \
  --validation-issues ../mapping-validation/outputs/hardened/deterministic_issues.csv \
  --id-repairs ../mapping-validation/outputs/hardened/duplicate_edge_id_repairs.csv \
  --outdir outputs/sheet_package
```

The command writes clean import CSVs for candidate review rows, validation issue summaries,
duplicate edge ID repairs, and optional human-approved mapping patches. It does not write to the
live shared sheet; use the generated CSVs after confirming the exact sheet target and ranges.

To produce the HuggingFace-ready dataset package:

```bash
esai-collect export-hf-dataset \
  --papers outputs/latest/papers_raw.csv \
  --candidates outputs/latest/benchmark_candidates.csv \
  --review-queue outputs/latest/tracker_review_queue.csv \
  --mapping-edges ../mapping-validation/outputs/hardened/all_edges.csv \
  --source-registry ../mapping-validation/outputs/hardened/benchmark_sources.csv \
  --outdir outputs/hf_dataset
```

See [INTEGRATION_WORKFLOW.md](INTEGRATION_WORKFLOW.md) and
[HUGGINGFACE_DATASET_SCHEMA.md](HUGGINGFACE_DATASET_SCHEMA.md) for the weekly data workflow.

## Method

Collection and screening are separate and repeatable:

1. collect every accepted paper from each in-scope venue edition;
2. preserve source identifiers, links, date basis, venue track, query log, and hashes;
3. apply explicit high, medium, and low candidate rules;
4. deduplicate transitively by normalized title, OpenReview ID, and DOI;
5. match exact titles and narrowly defined title aliases against the current tracker;
6. require human benchmark coding and risk triage;
7. export tracker-shaped records and a separate mapping handoff.

See [METHODOLOGY.md](METHODOLOGY.md) for the inclusion policy and
[SOURCE_ADAPTERS.md](SOURCE_ADAPTERS.md) for source-adapter notes.

## Development

```bash
ruff format --check esai_collection tests
ruff check esai_collection tests
pytest -p no:cacheprovider --basetemp test-tmp
```

Generated data and downloaded workbooks are ignored by Git.
