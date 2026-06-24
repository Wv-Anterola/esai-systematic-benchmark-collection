# Collection methodology

## Scope and inclusion rule

The project cutoff is 1 November 2022. Venue editions are included as follows:

| Venue | Editions | Accepted-paper source |
|---|---|---|
| NeurIPS | 2022 onward | OpenReview conference and Datasets & Benchmarks tracks |
| ICLR | 2023 onward | OpenReview conference venue |
| ICML | 2023 onward | PMLR ICML proceedings volumes |
| COLM | 2024 onward | OpenReview conference venue |

This edition policy avoids treating the pre-cutoff ICLR and ICML 2022 proceedings as in scope.
NeurIPS 2022 is included because the conference edition falls after the cutoff.

ACL venues are outside this repository's ownership. A future cross-source merge should transform
the ACL output into `RAW_FIELDS` from `esai_collection/schema.py` and pass it through the same
screening command.

## Source choice

OpenReview venue identifiers represent accepted ICLR, NeurIPS, and COLM papers. Both API versions
are attempted because older conferences are not consistently exposed through the newer API.
Each attempt is logged separately. Network errors are not reported as empty venues.

PMLR is the accepted-proceedings source for ICML. The collector discovers ICML volumes from the
PMLR archive, downloads the volume bibliography maintained by PMLR, and retains its abstract,
authors, publication date, OpenReview cross-reference, and software link when present.

## Collection completeness

The raw layer contains every accepted paper returned by each successful in-scope source query.
Filtering never changes the raw layer. This makes it possible to revise the screening rules
without repeating network collection.

The collection log is part of the evidence. A run is not complete while an in-scope source query
has `status=error`. `status=empty` is reserved for a successful query that returned no accepted
papers, such as a future conference edition before decisions are released.

## Candidate screening

Screening assigns one of three tiers:

- `high`: accepted in a Datasets & Benchmarks track, or the title explicitly names a benchmark,
  dataset, corpus, challenge, testbed, leaderboard, evaluation suite, or shared task;
- `medium`: the abstract states that the paper introduces, presents, releases, proposes, develops,
  builds, or creates one of those evaluation artifacts;
- `low`: the abstract mentions such an artifact but does not claim to introduce one.

All tiers are retained in `benchmark_candidates.csv`. The default tracker review queue contains
high and medium tiers. Low-tier records can be included for a recall audit with `--include-low`.
The tier is evidence for triage, not a final determination that the paper is a benchmark.

## Deduplication

Candidate records are joined transitively on:

1. exact normalized title;
2. OpenReview forum ID;
3. DOI.

Transitive joining matters when one source shares a title with a second source and the second
shares an identifier with a third. The retained record is the highest-confidence and most
complete member of the group. Missing metadata is filled from other members, and all alternate
source records are preserved in `also_seen_at`.

## Tracker matching and export

When a workbook is supplied, candidate titles are matched exactly after case and punctuation
normalization against the `benchmarks` sheet. Existing titles are excluded from the default review
queue and remain visible in the candidate file.

The review queue carries the tracker fields alongside provenance and review fields. Export accepts
only rows marked `approved` and requires title, description, quick reference, task, metric, and
communicated metric. The resulting file uses the workbook's exact `benchmarks` column order.

## Reproducibility

Every full run records:

- UTC collection time and stable run IDs;
- queried venue, year, track, source identifier, API version, status, count, and error;
- package version and scope in `run_manifest.json`;
- the workbook path used for tracker matching;
- raw, screened, and review-queue record counts.

Generated outputs are not committed. A release or handoff should publish the manifest and the
reviewed tracker file together.

## Adding another venue

A new source adapter must:

1. use an authoritative accepted-paper list;
2. emit every field in `RAW_FIELDS` without changing field meaning;
3. produce query-level log rows with separate `ok`, `empty`, and `error` states;
4. include fixture-based tests for parsing and date boundaries;
5. document the venue's first in-scope edition;
6. pass its records through the shared screening, deduplication, tracker matching, and export code.

