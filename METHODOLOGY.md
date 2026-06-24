# Collection methodology

## Scope and inclusion rule

The cutoff is 1 November 2022. Whole venue editions are included as follows:

| Venue | Editions | Accepted-paper source |
|---|---|---|
| NeurIPS | 2022 onward | OpenReview main and Datasets & Benchmarks tracks |
| ICLR | 2023 onward | OpenReview conference venue |
| ICML | 2023 onward | PMLR ICML proceedings volumes |
| COLM | 2024 onward | OpenReview conference venue |

This avoids treating the pre-cutoff ICLR and ICML 2022 proceedings as in scope. NeurIPS 2022 is
included because the conference edition occurred after the cutoff. ACL collection is maintained
separately and joins through the raw schema contract.

## Source and date provenance

OpenReview venue identifiers provide accepted ICLR, NeurIPS, and COLM papers. Both API versions
are attempted because older editions are not uniformly exposed through the newer API. Each
identifier attempt is logged separately, and network failures are distinct from successful empty
results.

OpenReview does not provide a consistent paper-level publication date for every edition. Its
`publication_date` is therefore a documented venue-month estimate and
`publication_date_basis=venue-edition-estimate`. PMLR records use the proceedings publication
date with `publication_date_basis=proceedings-publication-date`. Edition inclusion, not the
estimated first day of a month, determines cutoff eligibility.

## Collection completeness

The raw layer contains every accepted paper returned by every successful in-scope query. Screening
never modifies the raw layer, so rules can be revised without repeating network collection.

A run is incomplete while any required query has `status=error`. `status=empty` means the query
succeeded but returned no accepted papers, which is expected for a future edition before decisions
are released. The collection log is part of the evidence and must accompany a handoff.

## Candidate screening

Screening assigns:

- `high` when the paper is in a Datasets & Benchmarks track or its title explicitly names an
  evaluation artifact;
- `medium` when the abstract states that the paper introduces, presents, releases, proposes,
  develops, builds, or creates an evaluation artifact;
- `low` when the abstract mentions such an artifact without an introduction claim.

All tiers remain in the candidate catalog. The default review queue contains high and medium
tiers; low-tier rows can be added for a recall audit. A tier is triage evidence, not a final
inclusion judgment.

## Deduplication and tracker matching

Candidate records are joined transitively by exact normalized title, OpenReview forum ID, and DOI.
The retained row is the highest-tier, most complete record, with missing fields filled from its
duplicates and alternate source IDs retained in `also_seen_at`.

Tracker matching first uses exact normalized titles. It then accepts a conservative alias only
when one unique tracker title either contains the other as a multi-token phrase or has token
Jaccard similarity of at least 0.90. A distinctive single-token containment must be at least eight
characters and cannot be a generic term such as `benchmark` or `dataset`. Multiple alias matches
are marked ambiguous and remain in the review queue. The match method is always recorded.

## Risk relevance and export

A candidate is not tracker-ready merely because it introduces a benchmark. A reviewer must state
whether its scored task and metric are relevant to at least one risk, identify candidate harm IDs,
record whether those harms are in the project's priority set, and explain the triage decision.
The project owner must provide the current priority-risk list; the collector does not infer it.

Exported benchmark rows retain the workbook's exact column order. A separate mapping handoff
preserves candidate ID, quick reference, title, priority status, harm IDs, triage rationale, and
review attribution until the tracker owner assigns a benchmark ID.

## Reproducibility

Every command records the package version, UTC time, Git commit and dirty state, parameters, input
hashes, workbook hash where applicable, output hashes, and counts. Full collection additionally
records source enablement, cutoff policy, record counts, and source error count. Generated data is
not committed; publish the manifest, collection log, reviewed queue, tracker import, and mapping
handoff together.

## Adding another venue

A new adapter must:

1. use an authoritative accepted-paper list;
2. emit every field in `RAW_FIELDS` with unchanged meaning;
3. state the exact or estimated basis for `publication_date`;
4. log each query with separate `ok`, `empty`, and `error` states;
5. include fixture-based parser and date-boundary tests;
6. document the first in-scope edition;
7. pass records through the shared screening, deduplication, matching, risk-triage, and export
   workflow.
