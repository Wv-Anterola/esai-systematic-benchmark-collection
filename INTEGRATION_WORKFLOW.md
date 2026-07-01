# Integration workflow

This workflow is for the weekly benchmark-side data engineering pass: clean the collection review
sheet, fold validation outputs into the shared mapping, keep ACL and non-ACL collection in one
pipeline, and refresh the dataset export.

## 1. Collect ACL and non-ACL papers

ACL is a first-class source. `run` collects OpenReview, PMLR, and ACL Anthology together, then
merges, screens, and builds the review queue in one pass:

```bash
esai-collect run --workbook "path/to/workbook.xlsx" --outdir outputs/latest
```

ACL needs an Anthology `data/` checkout. Provide it one of three ways:

- install the optional dependency (`pip install -e ".[acl]"`) so the adapter downloads and caches
  the Anthology on first use;
- point `--acl-data-dir path/to/acl-anthology/data` (or set `ACL_ANTHOLOGY_DATA`) at an existing
  checkout;
- pass `--skip-acl` to run OpenReview and PMLR only.

If a collaborator hands off an ACL raw CSV collected elsewhere, it must follow
[SCHEMA.md](SCHEMA.md); fold it in with `merge` before screening:

```bash
esai-collect merge \
  outputs/latest/papers_raw.csv \
  path/to/handoff_acl_raw.csv \
  --out outputs/combined/papers_raw.csv

esai-collect screen \
  --input outputs/combined/papers_raw.csv \
  --workbook "path/to/workbook.xlsx" \
  --out outputs/combined/benchmark_candidates.csv \
  --review-queue outputs/combined/tracker_review_queue.csv
```

Do not add source-specific ACL columns to the shared raw file. Keep extra Anthology metadata in a
sidecar keyed by `record_id`.

## 2. Clean collection rows for the shared sheet

The sheet package command normalizes whitespace and statuses, prevents formula-like cells from
being interpreted by spreadsheet software, and produces separate import files for collection and
validation work:

```bash
esai-collect prepare-sheet-package \
  --review-queue outputs/combined/tracker_review_queue.csv \
  --validation-issues ../mapping-validation/outputs/hardened/deterministic_issues.csv \
  --id-repairs ../mapping-validation/outputs/hardened/duplicate_edge_id_repairs.csv \
  --mapping-patch ../mapping-validation/outputs/tracker_patch.csv \
  --outdir outputs/sheet_package
```

Outputs:

| File | Use |
|---|---|
| `collection_review_clean.csv` | Import/update candidate review rows. |
| `validation_issues_summary.csv` | Triage sheet for workbook cleanup before semantic updates. |
| `duplicate_edge_id_repairs_clean.csv` | Row-addressed edge ID repairs. |
| `mapping_patch_clean.csv` | Human-approved mapping updates/deletions, if a patch file exists. |
| `sheet_package_manifest.json` | Counts and file hashes for the import packet. |

Live shared-sheet updates should use the exact sheet URL/ID and a final range check before writing.

## 3. Apply mapping validation outputs

Use the mapping-validation package to produce approved patches:

```bash
esai-validate prepare-review \
  --workbook "path/to/workbook.xlsx" \
  --predictions outputs/predictions.jsonl \
  --source-registry outputs/hardened/benchmark_sources.csv \
  --candidate-catalog ../systematic-benchmark-collection/outputs/combined/benchmark_candidates.csv \
  --out outputs/tracker_mapping_review.csv

esai-validate export \
  --review outputs/tracker_mapping_review.csv \
  --out outputs/tracker_patch.csv
```

Only import rows from `tracker_patch.csv` after human approval. Deterministic repairs such as
duplicate edge IDs should be applied before semantic mapping updates.

## 4. Refresh the HuggingFace dataset package

```bash
esai-collect export-hf-dataset \
  --papers outputs/combined/papers_raw.csv \
  --candidates outputs/combined/benchmark_candidates.csv \
  --review-queue outputs/combined/tracker_review_queue.csv \
  --mapping-edges ../mapping-validation/outputs/hardened/all_edges.csv \
  --source-registry ../mapping-validation/outputs/hardened/benchmark_sources.csv \
  --mapping-predictions ../mapping-validation/outputs/hardened/heuristic_predictions.jsonl \
  --mapping-review ../mapping-validation/outputs/hardened/heuristic_mapping_review.csv \
  --outdir outputs/hf_dataset
```

See [HUGGINGFACE_DATASET_SCHEMA.md](HUGGINGFACE_DATASET_SCHEMA.md) for file-level schema details.
