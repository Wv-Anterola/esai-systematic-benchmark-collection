# Cross-repository raw schema

The ACL collector can be developed independently and merged with this repository by emitting a
UTF-8 CSV with the following columns in order:

```text
record_id,source,source_id,title,abstract,authors,author_count,publication_date,publication_date_basis,year,venue,venue_track,decision,keywords,tldr,paper_url,pdf_url,code_url,openreview_id,pmlr_id,doi,collected_at,run_id
```

Required semantics:

- `record_id`: stable, source-namespaced identifier; never a row number;
- `source_id`: the authoritative source's persistent paper identifier;
- `authors`: semicolon-separated display names and `author_count`: parsed author count;
- `publication_date`: ISO `YYYY-MM-DD` where exact, otherwise a documented estimate;
- `publication_date_basis`: short controlled description such as
  `anthology-publication-date`, `proceedings-publication-date`, or
  `venue-edition-estimate`;
- `venue` and `venue_track`: canonical venue family and track, not free-form proceedings text;
- `decision`: evidence that the source record is accepted or published;
- `paper_url` and `pdf_url`: canonical metadata and PDF links where available;
- source-specific IDs such as `openreview_id`, `pmlr_id`, and `doi`: blank when unavailable;
- `collected_at`: UTC ISO timestamp and `run_id`: stable identifier shared by one source run.

Unknown values are empty strings. Do not use placeholder text such as `N/A`. The merge command
requires `record_id` and preserves only the declared schema, so source-specific fields must be
mapped before handoff. The source repository should also provide a query-level log and a manifest
with source scope, errors, code version, and file hash.
