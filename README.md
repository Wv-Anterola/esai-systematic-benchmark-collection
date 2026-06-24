# ESAI systematic benchmark collection

This repository collects benchmark papers published at major machine-learning venues from
November 2022 onward and prepares reviewed records for the ESAI benchmark tracker.

The scope owned here is:

- ICLR, NeurIPS, and COLM through the OpenReview API;
- ICML through the official Proceedings of Machine Learning Research (PMLR) volumes.

ACL Anthology collection is maintained separately by Emily and is intentionally not implemented
in this repository. Its output can be merged later using the common raw schema.

## Installation

Python 3.11 or newer is required.

```bash
python -m pip install -e ".[dev]"
```

OpenReview credentials are optional. Anonymous access works, while `OPENREVIEW_USERNAME` and
`OPENREVIEW_PASSWORD` can improve rate limits.

## Run the pipeline

The complete non-ACL workflow is one command:

```bash
esai-collect run \
  --workbook "path/to/ESAI Harm-Bench-Legal Map.xlsx" \
  --outdir outputs/latest
```

The command writes:

| File | Purpose |
|---|---|
| `papers_raw.csv` | Every accepted paper returned by the supported venue sources. |
| `collection_log.csv` | One row per source query, distinguishing success, empty results, and errors. |
| `benchmark_candidates.csv` | Deduplicated benchmark candidates with screening evidence and tracker matches. |
| `tracker_review_queue.csv` | High- and medium-confidence candidates prepared for manual coding. |
| `run_manifest.json` | Scope, tool version, input workbook, record counts, and source-error count. |

Low-confidence candidates remain in `benchmark_candidates.csv`; add `--include-low` to place
them in the manual review queue.

Source-specific and staged commands are also available:

```bash
esai-collect collect-openreview
esai-collect collect-icml
esai-collect merge outputs/openreview_raw.csv outputs/icml_raw.csv
esai-collect screen --workbook "path/to/workbook.xlsx"
```

Use `esai-collect <command> --help` for all options.

## Tracker integration

Reviewers work in `tracker_review_queue.csv`. Set `review_status` to `approved` only after coding
the benchmark's quick reference, task, metric, and communicated metric. Then run:

```bash
esai-collect export \
  --review-queue outputs/tracker_review_queue.csv \
  --out outputs/tracker_benchmarks.csv
```

`tracker_benchmarks.csv` has exactly the 13 columns used by the workbook's `benchmarks` sheet.
Approved rows with incomplete required coding are rejected instead of silently producing a
partial import. Benchmark IDs remain under tracker-owner control.

## Method

Collection and candidate screening are deliberately separate:

1. Collect all accepted papers from in-scope venue editions.
2. Preserve source identifiers, links, dates, venue tracks, and run provenance.
3. Classify likely benchmark papers using explicit, reviewable rules.
4. Deduplicate transitively by normalized title, OpenReview ID, and DOI.
5. Match exact normalized titles against the current tracker workbook.
6. Export only human-approved and fully coded records to tracker schema.

See [METHODOLOGY.md](METHODOLOGY.md) for the inclusion policy, screening tiers, reproducibility
requirements, and the procedure for adding another venue.

## Development

```bash
ruff format --check esai_collection tests
ruff check esai_collection tests
pytest
```

Generated data and downloaded workbooks are ignored by Git.

