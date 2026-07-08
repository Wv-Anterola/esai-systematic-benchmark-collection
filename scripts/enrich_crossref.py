"""Resumable Crossref citation enrichment.

OpenAlex and Semantic Scholar both rate-limited (429) this IP during the full run,
so citation counts come from Crossref's ``is-referenced-by-count`` instead. Crossref
is lenient in its polite pool (add a ``mailto``) and matches titles cleanly. This
driver:

- looks up each candidate by DOI when present, else by bibliographic title search;
- accepts a title-search hit only when the normalised titles match (guarding
  against attributing a different paper's citations);
- retries on 429/5xx with backoff, and appends after each chunk so the job is
  durable and resumes (skips record_ids already written).

Output columns feed ``esai_collection.citations.coalesce_citations`` via the
``crossref_cited_by_count`` field.

Usage:
    python scripts/enrich_crossref.py \
        --input outputs/full_run/candidates_relevant.csv \
        --out outputs/full_run/metadata_enrichment.csv \
        --delay-seconds 0.1 --chunk-size 250
"""

from __future__ import annotations

import argparse
import csv
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

from esai_collection.io import read_csv
from esai_collection.text import normalise_title

MAILTO = os.environ.get("CROSSREF_MAILTO", "acqresearch2025@gmail.com")
USER_AGENT = f"esai-benchmark-collection/0.2 (mailto:{MAILTO})"

CROSSREF_FIELDS = [
    "record_id",
    "title",
    "doi",
    "crossref_status",
    "crossref_cited_by_count",
    "crossref_title",
    "crossref_doi",
    "crossref_notes",
]


def _get_json(
    url: str, *, timeout: int, max_retries: int = 4
) -> tuple[dict | None, str]:
    backoff = 3.0
    last = ""
    for attempt in range(max_retries):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                import json

                return json.loads(response.read().decode("utf-8")), ""
        except Exception as exc:  # noqa: BLE001 - report and optionally retry
            last = f"{type(exc).__name__}: {exc}"
            transient = "429" in last or " 50" in last or "timed out" in last.lower()
            if not transient or attempt == max_retries - 1:
                return None, last
            time.sleep(backoff)
            backoff *= 2
    return None, last


def _token_overlap(a: str, b: str) -> float:
    sa, sb = set(a.split()), set(b.split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def lookup(
    row: dict[str, str], *, timeout: int, doi_only: bool = False
) -> dict[str, str]:
    record_id = row.get("record_id", "")
    title = row.get("title", "").strip()
    doi = row.get("doi", "").strip()
    item: dict[str, str] = {field: "" for field in CROSSREF_FIELDS}
    item.update({"record_id": record_id, "title": title, "doi": doi})

    if doi_only and not doi:
        item["crossref_status"] = "no-doi"
        item["crossref_notes"] = "skipped: no DOI (title search disabled)"
        return item

    if doi:
        url = (
            f"https://api.crossref.org/works/{urllib.parse.quote(doi)}"
            f"?mailto={urllib.parse.quote(MAILTO)}"
        )
        payload, error = _get_json(url, timeout=timeout)
        if error:
            item["crossref_status"] = "error"
            item["crossref_notes"] = error
            return item
        message = (payload or {}).get("message") or {}
        item["crossref_status"] = "ok" if message else "empty"
        _fill(item, message)
        return item

    if not title:
        item["crossref_status"] = "empty"
        item["crossref_notes"] = "no title or doi"
        return item

    query = urllib.parse.quote(title)
    url = (
        f"https://api.crossref.org/works?query.bibliographic={query}&rows=1"
        f"&select=DOI,title,is-referenced-by-count&mailto={urllib.parse.quote(MAILTO)}"
    )
    payload, error = _get_json(url, timeout=timeout)
    if error:
        item["crossref_status"] = "error"
        item["crossref_notes"] = error
        return item
    items = ((payload or {}).get("message") or {}).get("items") or []
    if not items:
        item["crossref_status"] = "empty"
        return item
    best = items[0]
    got_title = (best.get("title") or [""])[0]
    want_key, got_key = normalise_title(title), normalise_title(got_title)
    if want_key == got_key or _token_overlap(want_key, got_key) >= 0.8:
        item["crossref_status"] = "ok"
        _fill(item, best)
    else:
        item["crossref_status"] = "unmatched"
        item["crossref_title"] = got_title
        item["crossref_notes"] = "title mismatch; citation count withheld"
    return item


def _fill(item: dict[str, str], message: dict) -> None:
    count = message.get("is-referenced-by-count")
    item["crossref_cited_by_count"] = "" if count is None else str(count)
    item["crossref_title"] = (message.get("title") or [""])[0]
    item["crossref_doi"] = str(message.get("DOI", ""))


def _done_ids(out: Path) -> set[str]:
    if not out.exists():
        return set()
    with out.open(encoding="utf-8-sig", newline="") as handle:
        return {
            r.get("record_id", "")
            for r in csv.DictReader(handle)
            if r.get("record_id")
        }


def _append(out: Path, rows: list[dict[str, str]], write_header: bool) -> None:
    mode = "w" if write_header else "a"
    with out.open(mode, encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=CROSSREF_FIELDS, extrasaction="ignore"
        )
        if write_header:
            writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--delay-seconds", type=float, default=0.1)
    parser.add_argument("--chunk-size", type=int, default=100)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument(
        "--max-rows",
        type=int,
        help="process at most this many remaining rows this run (for bounded, "
        "resumable batches); omit to process all remaining",
    )
    parser.add_argument(
        "--doi-only",
        action="store_true",
        help="only look up papers that have a DOI (fast, exact); mark the rest "
        "'no-doi'. Title search is slow (~5s/row), so skip it at scale.",
    )
    args = parser.parse_args(argv)

    candidates = read_csv(args.input)
    done = _done_ids(args.out)
    remaining = [row for row in candidates if row.get("record_id", "") not in done]
    if args.max_rows is not None:
        remaining = remaining[: args.max_rows]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    print(
        f"Total: {len(candidates)} | done: {len(done)} | remaining: {len(remaining)}",
        flush=True,
    )

    buffer: list[dict[str, str]] = []
    processed = 0
    ok = 0
    for row in remaining:
        will_request = bool(row.get("doi", "").strip()) or not args.doi_only
        if args.delay_seconds and will_request:
            time.sleep(args.delay_seconds)
        result = lookup(row, timeout=args.timeout, doi_only=args.doi_only)
        buffer.append(result)
        processed += 1
        if result["crossref_status"] == "ok":
            ok += 1
        if len(buffer) >= args.chunk_size:
            _append(args.out, buffer, write_header=not args.out.exists())
            print(
                f"  wrote {len(done) + processed}/{len(candidates)} "
                f"(resolved {ok}/{processed})",
                flush=True,
            )
            buffer = []
    if buffer:
        _append(args.out, buffer, write_header=not args.out.exists())
    print(
        f"Done. {len(done) + processed}/{len(candidates)} rows, "
        f"resolved {ok}/{processed} -> {args.out}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
