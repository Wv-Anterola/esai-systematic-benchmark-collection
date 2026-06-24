#!/usr/bin/env python3
"""
openreview_validate.py  --  VALIDATION work package (stage 2 of 2).

Turns the raw cache from openreview_collect.py into a curated, deduplicated
candidate list. Offline and fast, so it can be re-run and tuned without going
back to the API.

Checks:
  * benchmark filter  -- keep all D&B-track papers; keep main/adjacent/workshop
    papers only when a keyword (benchmark, dataset, ...) hits title/abstract/keywords.
  * dedup             -- collapse the same paper across venues (id, then title,
    then arXiv id), keeping the highest-priority venue and noting the others.
  * completeness      -- flag rows missing a title, abstract, authors, or links.
  * benchmark_confidence -- high/medium/low from where the keyword matched.
  * workbook cross-check -- flag candidates whose title already matches a benchmark
    in the local ESAI .xlsx (skipped if no workbook is found).
  * link verification (opt-in, --check-links) -- HEAD/GET the forum/PDF/arXiv
    urls to confirm they resolve.
Each row gets a verification_status summarising the above.

Usage
-----
  python openreview_validate.py
  python openreview_validate.py --in outputs/openreview_raw.csv --check-links
  python openreview_validate.py --keywords benchmark "evaluation suite" leaderboard
  python openreview_validate.py --no-workbook-check

Output
------
  outputs/openreview_candidates.csv  -- validated, deduplicated candidate papers
"""
from __future__ import annotations

import argparse
import csv
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from openreview_common import norm_title

DEFAULT_KEYWORDS = ["benchmark", "dataset", "evaluation suite", "leaderboard", "eval harness"]
IN_DEFAULT = Path("outputs/openreview_raw.csv")
OUT_DEFAULT = Path("outputs/openreview_candidates.csv")

CANDIDATE_COLUMNS = [
    "openreview_id", "title", "authors", "author_count", "year",
    "source_venue", "venueid", "venue_set", "source_api", "decision",
    "primary_area", "abstract", "keywords", "tldr",
    "arxiv_id", "arxiv_url", "code_url", "forum_url", "pdf_url",
    "match_reason", "harvested_via", "benchmark_confidence", "completeness_ok",
    "links_ok", "already_in_workbook", "workbook_match", "also_seen_at",
    "verification_status",
]


# ---------------------------------------------------------------------------
# filter + confidence
# ---------------------------------------------------------------------------

def match_keyword(title: str, keywords: str, abstract: str, needles: list[str]):
    # returns (matched_keyword, where) with where in {title, keywords, abstract}.
    fields = [("title", title), ("keywords", keywords), ("abstract", abstract)]
    for kw in needles:
        low = kw.lower()
        for where, text in fields:
            if low in text.lower():
                return kw, where
    return None, None


def confidence_of(is_dnb: bool, where: str | None) -> str:
    # D&B papers are benchmarks by construction; otherwise trust a title hit
    # most and an abstract-only hit least.
    if is_dnb:
        return "high"
    return {"title": "high", "keywords": "medium", "abstract": "low"}.get(where, "low")


def is_complete(row: dict) -> bool:
    return all(row.get(f, "").strip() for f in ("title", "abstract", "authors", "forum_url"))


# ---------------------------------------------------------------------------
# dedup (priority precedence, carried over from collection)
# ---------------------------------------------------------------------------

def dedup(rows: list[dict]) -> list[dict]:
    # keep the highest-priority venue for each paper and note the others. sort by
    # priority first so the survivor is always the best venue (D&B > main > ...).
    rows = sorted(rows, key=lambda r: int(r.get("priority", 9) or 9))
    seen = {"id": {}, "title": {}, "arxiv": {}}
    unique: list[dict] = []
    for r in rows:
        keys = [("id", r["openreview_id"])]
        nt = norm_title(r["title"])
        if nt:
            keys.append(("title", nt))
        if r["arxiv_id"]:
            keys.append(("arxiv", r["arxiv_id"]))
        hit = next((seen[t][v] for t, v in keys if v in seen[t]), None)
        if hit is not None:
            also = set(filter(None, unique[hit]["also_seen_at"].split("; ")))
            also.add(r["source_venue"])
            unique[hit]["also_seen_at"] = "; ".join(sorted(also))
            continue
        idx = len(unique)
        unique.append(r)
        for t, v in keys:
            seen[t][v] = idx
    return unique


# ---------------------------------------------------------------------------
# workbook cross-check
# ---------------------------------------------------------------------------

def find_workbook(explicit: str | None = None) -> Path | None:
    # same resolution as the audit scripts: --workbook, ESAI_WORKBOOK, ./data, root.
    import os
    if explicit:
        return Path(explicit)
    if os.environ.get("ESAI_WORKBOOK"):
        return Path(os.environ["ESAI_WORKBOOK"])
    for folder in ("data", "."):
        hits = sorted(Path(folder).glob("*.xlsx"))
        if hits:
            return hits[0]
    return None


def load_workbook_titles(wb: Path) -> dict[str, str]:
    # map normalised benchmark title -> original, from the benchmarks sheet.
    import pandas as pd
    df = pd.read_excel(wb, sheet_name="benchmarks")
    col = next((c for c in ("title", "name", "benchmark_name", "benchmark") if c in df.columns), None)
    if col is None:
        return {}
    titles = {}
    for raw in df[col].dropna().astype(str):
        titles[norm_title(raw)] = raw
    return titles


def workbook_match(nt: str, wb_titles: dict[str, str]) -> str:
    if nt in wb_titles:
        return wb_titles[nt]
    # also catch short benchmark names (e.g. "swe bench") embedded in a paper title
    for wb_nt, orig in wb_titles.items():
        if len(wb_nt.split()) <= 3 and wb_nt and wb_nt in nt:
            return orig
    return ""


# ---------------------------------------------------------------------------
# link verification (opt-in)
# ---------------------------------------------------------------------------

def check_url(url: str, timeout: int = 12) -> bool:
    # best-effort: a browser-like UA and a couple of attempts cut down on
    # false "broken" verdicts from anti-bot blocks or transient throttling.
    import time
    import urllib.request
    if not url:
        return True
    ua = "Mozilla/5.0 (compatible; esai-benchmark-toolkit/1.0)"
    for attempt in range(2):
        for method, extra in (("HEAD", {}), ("GET", {"Range": "bytes=0-0"})):
            try:
                req = urllib.request.Request(url, method=method, headers={"User-Agent": ua, **extra})
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return 200 <= resp.status < 400
            except Exception:
                continue
        time.sleep(1)
    return False


def verify_links(rows: list[dict]) -> None:
    # check the forum and PDF urls (the two that matter for triage). keep
    # concurrency low so OpenReview does not throttle us into false negatives.
    def one(row):
        urls = [row.get("forum_url", ""), row.get("pdf_url", "")]
        results = [check_url(u) for u in urls if u]
        row["links_ok"] = "ok" if all(results) else "broken"
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(one, rows))


# ---------------------------------------------------------------------------
# status + driver
# ---------------------------------------------------------------------------

def verification_status(row: dict, checked_links: bool) -> str:
    if row["already_in_workbook"] == "True":
        return "in-workbook"
    if row["completeness_ok"] != "True":
        return "incomplete"
    if checked_links and row["links_ok"] == "broken":
        return "links-broken"
    if row["benchmark_confidence"] == "low":
        return "needs-review"
    return "candidate"


def main() -> int:
    ap = argparse.ArgumentParser(description="OpenReview validation: curate the raw cache into candidates.")
    ap.add_argument("--in", dest="infile", type=Path, default=IN_DEFAULT, help="raw cache CSV from collection")
    ap.add_argument("--out", type=Path, default=OUT_DEFAULT, help="validated candidates CSV path")
    ap.add_argument("--keywords", nargs="+", default=DEFAULT_KEYWORDS,
                    help="benchmark keyword filter (D&B track is always kept)")
    ap.add_argument("--check-links", action="store_true", help="verify forum/PDF urls resolve (slower, network)")
    ap.add_argument("--no-workbook-check", action="store_true", help="skip the local .xlsx cross-check")
    ap.add_argument("--workbook", default=None, help="explicit workbook path for the cross-check")
    args = ap.parse_args()

    if not args.infile.exists():
        print(f"ERROR: {args.infile} not found. Run python openreview_collect.py first.", file=sys.stderr)
        return 2

    with args.infile.open(encoding="utf-8") as fh:
        raw = list(csv.DictReader(fh))

    print("=" * 64)
    print("OPENREVIEW VALIDATION (stage 2 of 2)")
    print("=" * 64)
    print(f"input      : {args.infile} ({len(raw)} papers)")
    print(f"keywords   : {args.keywords}")
    print(f"link check : {'on' if args.check_links else 'off'}")
    print("-" * 64)

    # filter to benchmark candidates + score confidence
    kept: list[dict] = []
    for r in raw:
        dnb = r.get("is_dnb", "") == "True"
        if dnb:
            r["match_reason"], where = "neurips_dnb_track", None
        else:
            kw, where = match_keyword(r["title"], r["keywords"], r["abstract"], args.keywords)
            if not kw:
                continue
            r["match_reason"] = f"keyword:{kw}"
        r["harvested_via"] = "dnb_track" if dnb else f"{r.get('venue_set', 'core')}_keyword"
        r["benchmark_confidence"] = confidence_of(dnb, where)
        r["also_seen_at"] = ""
        kept.append(r)

    unique = dedup(kept)
    for r in unique:
        r["completeness_ok"] = str(is_complete(r))

    # workbook cross-check
    wb_titles: dict[str, str] = {}
    if not args.no_workbook_check:
        wb = find_workbook(args.workbook)
        if wb and wb.exists():
            try:
                wb_titles = load_workbook_titles(wb)
                print(f"workbook   : {wb.name} ({len(wb_titles)} benchmark titles)")
            except Exception as exc:
                print(f"workbook   : cross-check skipped ({exc})", file=sys.stderr)
        else:
            print("workbook   : none found, cross-check skipped")
    for r in unique:
        match = workbook_match(norm_title(r["title"]), wb_titles)
        r["already_in_workbook"] = str(bool(match))
        r["workbook_match"] = match

    # link verification
    if args.check_links:
        print(f"checking links for {len(unique)} candidates ...")
        verify_links(unique)
    else:
        for r in unique:
            r["links_ok"] = ""

    for r in unique:
        r["verification_status"] = verification_status(r, args.check_links)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CANDIDATE_COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(unique)

    print("-" * 64)
    status_counts: dict[str, int] = {}
    for r in unique:
        s = r["verification_status"]
        status_counts[s] = status_counts.get(s, 0) + 1
    print(f"candidates kept : {len(kept)} (before dedup)")
    print(f"unique papers   : {len(unique)}")
    for status in sorted(status_counts):
        print(f"  {status:<14}: {status_counts[status]}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
