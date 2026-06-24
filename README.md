# Work package: Systematic benchmark collection

Owner: Wilber + Emily. Window: 17.06.2026 - 24.06.2026.

## Goal (from the project doc)

- Collect all benchmark papers from major venues since Nov 2022.
- Build a methodology that transfers to new venues and to future re-runs of venues
  already covered.
- Venues of interest: ACL venues; ICML, ICLR, NeurIPS; COLM.

## Split of work

- Emily: ACL Anthology side (Python package + XML/YAML metadata).
- Wilber (this folder): the OpenReview side. ICLR / NeurIPS / COLM expose accepted
  papers through the OpenReview API. (ICML is on the doc's list but historically is
  not on OpenReview, so it needs a separate source; flagged, not yet handled.)

## The OpenReview pipeline (two stages)

Run in order. `openreview_common.py` holds the helpers the two stages share.

    pip install openreview-py

### 1. Collection -- `openreview_collect.py`

Harvests every accepted paper into a raw cache, enriched but unfiltered. The slow,
network-bound step you run once.

    python openreview_collect.py --years 2024 --limit 10     # quick smoke test
    python openreview_collect.py                             # full maximal sweep (2019 to 2025)
    python openreview_collect.py --venue-sets core           # lean run, skip adjacent + workshops

Coverage is maximal by default: both OpenReview APIs (v2 for recent years, v1 for 2022
and earlier via the Blind_Submission + decision route), ICLR + NeurIPS main + NeurIPS
D&B, adjacent ML venues (COLM, TMLR, RLC, CoRL), and workshops discovered from the
`venues` group (capped by `--max-workshops`). Writes `outputs/openreview_raw.csv` (all
accepted papers, enriched: decision, primary area, arXiv id/url, code link, forum/PDF
links, TLDR, author count, source API) and `outputs/openreview_run_log.csv`.

### 2. Validation (paper QC) -- `openreview_validate.py`

Turns the raw cache into a curated, deduplicated candidate list. Offline and fast, so it
can be re-run as the keywords are tuned without going back to the API.

    python openreview_validate.py                            # offline QC + workbook cross-check
    python openreview_validate.py --check-links              # also verify forum/PDF urls resolve

Keeps every D&B-track paper and keyword-filters the rest, dedups across venues (id, then
title, then arXiv id; keeps the best venue, lists the rest in `also_seen_at`), scores
`benchmark_confidence`, checks completeness, cross-checks titles against the local ESAI
`.xlsx` benchmarks (skips if none found), and with `--check-links` verifies links resolve.
Each row gets a `verification_status`. Writes `outputs/openreview_candidates.csv`.

Note: this is paper QC (is the collected paper a real, unique benchmark), which is part of
collection. It is NOT the project's separate "Mapping validation" work package, which
validates benchmark-to-harm edge assignments (see `../mapping-validation/`).

Output stays a discovery dump for triage: `task`, `metric`, and `evidence_type` are coded
by hand. Auth is optional; set `OPENREVIEW_USERNAME` / `OPENREVIEW_PASSWORD` for higher
rate limits. Both stages read OpenReview (and the local workbook, for the cross-check)
only; they never modify the workbook. `outputs/` is gitignored.

## Open / next

- Merge with Emily's ACL Anthology set (cross-source dedup) for the shared CSV.
- ICML source (not on OpenReview): decide on PMLR / proceedings scrape.
- Confirm the priority risks (open question flagged in the doc) to focus triage.
