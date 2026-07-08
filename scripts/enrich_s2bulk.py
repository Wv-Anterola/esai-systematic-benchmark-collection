"""Resumable Semantic Scholar (bulk-search) citation enrichment for the no-DOI gap.

Crossref only covers DOI-bearing papers (ACL); the OpenReview/PMLR papers have no
DOI. OpenAlex and S2's regular search are 429-blocked, but S2's ``/paper/search/bulk``
endpoint still responds. Queried with the exact title as a phrase it returns the
matching paper's ``citationCount``. This driver fills the gap left by Crossref:

- processes only candidates that lack a Crossref citation count (via --gap-from);
- accepts a hit only when the normalised titles match (guard against wrong paper);
- retries on 429/5xx with backoff, appends per chunk (durable + resumable).

Output column ``semantic_scholar_citation_count`` is consumed by
``esai_collection.citations.coalesce_citations``.

Usage:
    python scripts/enrich_s2bulk.py \
        --input outputs/full_run/candidates_relevant.csv \
        --gap-from outputs/full_run/metadata_enrichment.csv \
        --out outputs/full_run/s2_enrichment.csv \
        --delay-seconds 1.0 --chunk-size 100
"""

from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

from esai_collection.io import read_csv
from esai_collection.text import normalise_title

MAILTO = "acqresearch2025@gmail.com"
USER_AGENT = f"esai-benchmark-collection/0.2 (mailto:{MAILTO})"
BULK_URL = "https://api.semanticscholar.org/graph/v1/paper/search/bulk"

S2_FIELDS = [
    "record_id",
    "title",
    "semantic_scholar_status",
    "semantic_scholar_citation_count",
    "semantic_scholar_title",
    "semantic_scholar_notes",
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


def lookup(row: dict[str, str], *, timeout: int) -> dict[str, str]:
    title = row.get("title", "").strip()
    item = {field: "" for field in S2_FIELDS}
    item.update({"record_id": row.get("record_id", ""), "title": title})
    if not title:
        item["semantic_scholar_status"] = "empty"
        item["semantic_scholar_notes"] = "no title"
        return item
    query = urllib.parse.quote(f'"{title}"')
    url = f"{BULK_URL}?query={query}&fields=title,citationCount"
    payload, error = _get_json(url, timeout=timeout)
    if error:
        item["semantic_scholar_status"] = "error"
        item["semantic_scholar_notes"] = error
        return item
    data = (payload or {}).get("data") or []
    if not data:
        item["semantic_scholar_status"] = "empty"
        return item
    best = data[0]
    got_title = best.get("title") or ""
    want_key, got_key = normalise_title(title), normalise_title(got_title)
    if want_key == got_key or _token_overlap(want_key, got_key) >= 0.8:
        count = best.get("citationCount")
        item["semantic_scholar_status"] = "ok"
        item["semantic_scholar_citation_count"] = "" if count is None else str(count)
        item["semantic_scholar_title"] = got_title
    else:
        item["semantic_scholar_status"] = "unmatched"
        item["semantic_scholar_title"] = got_title
        item["semantic_scholar_notes"] = "title mismatch; citation count withheld"
    return item


def _done_ids(out: Path) -> set[str]:
    if not out.exists():
        return set()
    with out.open(encoding="utf-8-sig", newline="") as handle:
        return {
            r.get("record_id", "")
            for r in csv.DictReader(handle)
            if r.get("record_id")
        }


def _gap_ids(gap_from: Path) -> set[str]:
    """record_ids in the Crossref enrichment that still lack a citation count."""
    with gap_from.open(encoding="utf-8-sig", newline="") as handle:
        return {
            r.get("record_id", "")
            for r in csv.DictReader(handle)
            if r.get("record_id")
            and not (r.get("crossref_cited_by_count") or "").strip()
        }


def _append(out: Path, rows: list[dict[str, str]], write_header: bool) -> None:
    mode = "w" if write_header else "a"
    with out.open(mode, encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=S2_FIELDS, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--gap-from",
        type=Path,
        help="Crossref enrichment CSV; only process records with no count there",
    )
    parser.add_argument("--delay-seconds", type=float, default=1.0)
    parser.add_argument("--chunk-size", type=int, default=100)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--max-rows", type=int)
    args = parser.parse_args(argv)

    candidates = read_csv(args.input)
    if args.gap_from:
        gap = _gap_ids(args.gap_from)
        candidates = [r for r in candidates if r.get("record_id", "") in gap]
    done = _done_ids(args.out)
    remaining = [r for r in candidates if r.get("record_id", "") not in done]
    if args.max_rows is not None:
        remaining = remaining[: args.max_rows]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    print(
        f"Gap candidates: {len(candidates)} | done: {len(done)} | "
        f"remaining: {len(remaining)}",
        flush=True,
    )

    buffer: list[dict[str, str]] = []
    processed = 0
    ok = 0
    for row in remaining:
        if args.delay_seconds:
            time.sleep(args.delay_seconds)
        result = lookup(row, timeout=args.timeout)
        buffer.append(result)
        processed += 1
        if result["semantic_scholar_status"] == "ok":
            ok += 1
        if len(buffer) >= args.chunk_size:
            _append(args.out, buffer, write_header=not args.out.exists())
            print(
                f"  wrote {len(done) + processed} (resolved {ok}/{processed})",
                flush=True,
            )
            buffer = []
    if buffer:
        _append(args.out, buffer, write_header=not args.out.exists())
    print(f"Done. resolved {ok}/{processed} -> {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
