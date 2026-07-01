# Source adapters

## Current authoritative collectors

| Source | Status | Role | Why it belongs in the raw layer |
|---|---|---|---|
| OpenReview | implemented | ICLR, NeurIPS, COLM accepted papers | Venue decision records are authoritative enough for accepted-paper collection. |
| PMLR | implemented | ICML proceedings | Official proceedings volumes give stable paper metadata and publication dates. |
| ACL Anthology | implemented (`collect-acl`) | Major *ACL venue families | The Anthology XML/venue metadata is the authoritative record; `esai_collection/acl_source.py` emits the shared raw schema and flows through the same merge, screen, review, and export steps. |

## Adapter contract

Every source adapter produces:

- `raw.csv` with exactly the columns in [SCHEMA.md](SCHEMA.md);
- `log.csv` with query-level `ok`, `empty`, and `error` rows;
- a manifest with source scope, code version, input/output hashes, parameters, and record counts;
- fixture tests for parsing, date cutoff boundaries, and empty/error behavior;
- a methodology note naming the authoritative source and the first in-scope edition.

Adapters should avoid source-specific columns in the shared raw file. If a source has extra useful
metadata, keep it in a sidecar file keyed by `record_id`.

## ACL and non-ACL consolidation

ACL collection is implemented in `esai_collection/acl_source.py` and exposed as `collect-acl`. It
parses the ACL Anthology XML directly (version-independent of `acl-anthology-py`) and reads the
Anthology's own `is_toplevel` venue flag, so new major venues and new editions are picked up with no
code change. It emits the shared raw schema, so consolidation is just the normal pipeline:

1. `collect-acl` writes `acl_raw.csv`, `acl_log.csv`, and a manifest.
2. `merge` combines `acl_raw.csv` with OpenReview/PMLR raw records.
3. Screening, tracker matching, sheet cleanup, mapping handoff, and HuggingFace export run once on
   the combined file.

The `run` command performs all three steps across every enabled source in one pass. Benchmark
detection is left to the shared screening step, so the ACL adapter collects every in-scope accepted
paper rather than pre-filtering — matching the OpenReview and PMLR adapters.

## Candidate future sources

These sources are useful outside the authoritative accepted-paper layer.

| Source | Best use | Risk | Recommended layer |
|---|---|---|---|
| Semantic Scholar Academic Graph API | backfill abstracts, citations, open-access links, related work, and DOI/S2 IDs | not a venue-acceptance source; can include preprints and duplicates | implemented: `enrich-metadata` |
| OpenAlex | broad bibliographic coverage, venue/source normalization, DOI/Crossref enrichment | source/venue filters need validation; not sufficient alone for acceptance decisions | implemented: `enrich-metadata` |
| Hugging Face Hub datasets search | discover benchmark artifacts that never appear as formal papers | repository metadata may be incomplete and not risk-relevant | implemented: `discover-hf-datasets` |
| Papers with Code / benchmark leaderboards | identify benchmark names, tasks, metrics, datasets, code, and popularity | coverage and freshness vary; may duplicate paper sources | benchmark-metadata enrichment |
| arXiv | early discovery before venue publication | preprints are not accepted venue papers and may later change title/metadata | watchlist only, then reconcile to accepted source |
| GitHub code search | find released eval harnesses and benchmark datasets | noisy, not publication-grade provenance | artifact/source verification sidecar |

Reference docs checked for the source-options plan:

- Semantic Scholar Academic Graph API: `https://api.semanticscholar.org/api-docs/`
- OpenAlex developer docs: `https://developers.openalex.org/`
- Hugging Face Hub API/search docs: `https://huggingface.co/docs/hub/api` and
  `https://huggingface.co/docs/huggingface_hub/guides/search`

## Priority additions

1. Run `collect-acl` and merge it with OpenReview/PMLR, then screen the combined corpus (done; see `collect-acl`).
2. Use `enrich-metadata` on reviewed candidates to fill source abstracts and identifiers.
3. Use `discover-hf-datasets` to build a separate queue for benchmark artifacts missed by papers.
4. Use `sample-recall-audit` on low-tier candidates before changing screening terms.

## Acceptance rules for new adapters

A new source is allowed into the authoritative raw layer only if it can answer:

- Which exact venue or collection is in scope?
- Why does the source prove the paper was accepted or officially published?
- What date basis is used for the November 2022 cutoff?
- How are duplicate records reconciled with OpenReview/PMLR/ACL outputs?
- What does a successful empty query mean?

Sources that cannot answer these questions should be enrichment or artifact-discovery sources, not
authoritative accepted-paper sources.
