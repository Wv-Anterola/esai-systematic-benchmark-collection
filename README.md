# ESAI systematic benchmark collection

This repository collects accepted papers from major machine-learning venues since the November
2022 cutoff, identifies benchmark candidates, checks the existing tracker, and prepares reviewed
tracker imports.

The scope owned here is:

- ICLR, NeurIPS, and COLM through OpenReview;
- ICML through the official Proceedings of Machine Learning Research volumes.

ACL Anthology collection belongs to Emily's separate repository. [SCHEMA.md](SCHEMA.md) defines
the raw-data contract for merging that output without coupling the two implementations.

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
esai-collect merge outputs/openreview_raw.csv outputs/icml_raw.csv
esai-collect screen \
  --input outputs/papers_raw.csv \
  --workbook "path/to/workbook.xlsx"
```

Every staged command writes a hash manifest beside its primary output.

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

## Method

Collection and screening are separate and repeatable:

1. collect every accepted paper from each in-scope venue edition;
2. preserve source identifiers, links, date basis, venue track, query log, and hashes;
3. apply explicit high, medium, and low candidate rules;
4. deduplicate transitively by normalized title, OpenReview ID, and DOI;
5. match exact titles and narrowly defined title aliases against the current tracker;
6. require human benchmark coding and risk triage;
7. export tracker-shaped records and a separate mapping handoff.

See [METHODOLOGY.md](METHODOLOGY.md) for the inclusion policy and extension procedure.

## Development

```bash
ruff format --check esai_collection tests
ruff check esai_collection tests
pytest
```

Generated data and downloaded workbooks are ignored by Git.
