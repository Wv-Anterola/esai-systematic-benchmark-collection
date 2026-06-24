#!/usr/bin/env python3
"""
openreview_collect.py  --  COLLECTION work package (stage 1 of 2).

Read-only harvest of accepted papers from OpenReview into a raw cache CSV. This
is the slow, network-bound step: resolve venues, fetch every accepted paper
(API v2 for recent years, API v1 for 2022 and earlier), and enrich each into a
structured record (arXiv id, code link, PDF, primary area, decision, TLDR).

It does NOT decide what counts as a benchmark and does NOT dedup. Collection
casts the wide net; openreview_validate.py turns the raw cache into the curated
candidate list. Splitting them means the keyword/dedup/QC logic can be re-run
and tuned without re-hitting the API.

Usage
-----
  pip install openreview-py
  python openreview_collect.py                                  # maximal sweep
  python openreview_collect.py --years 2024 --limit 10          # fast smoke test
  python openreview_collect.py --years 2021 --api v1 --limit 10 # legacy path
  python openreview_collect.py --venue-sets core adjacent       # skip workshops

Auth is optional. Public accepted papers need none; set OPENREVIEW_USERNAME /
OPENREVIEW_PASSWORD env vars for higher rate limits.

Output
------
  outputs/openreview_raw.csv       -- every accepted paper, enriched, no filter
  outputs/openreview_run_log.csv   -- per-venue counts and status
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import time
from pathlib import Path

from openreview_common import FORUM_URL, SITE, as_text, cval, first_present, is_dnb

DEFAULT_YEARS = list(range(2019, 2026))
DEFAULT_VENUE_SETS = ["core", "adjacent", "workshops"]

BASEURL_V2 = "https://api2.openreview.net"
BASEURL_V1 = "https://api.openreview.net"
V1_CUTOFF_YEAR = 2022  # this year and earlier are served by API v1

OUT_DEFAULT = Path("outputs/openreview_raw.csv")
LOG_DEFAULT = Path("outputs/openreview_run_log.csv")

RAW_COLUMNS = [
    "openreview_id", "title", "authors", "author_count", "year",
    "source_venue", "venueid", "venue_set", "source_api", "is_dnb", "priority",
    "decision", "primary_area", "abstract", "keywords", "tldr",
    "arxiv_id", "arxiv_url", "code_url", "forum_url", "pdf_url",
]

ARXIV_RE = re.compile(r"arxiv\.org/abs/(\d{4}\.\d{4,5})|arxiv[:\s]+(\d{4}\.\d{4,5})", re.I)
GITHUB_RE = re.compile(r"https?://github\.com/[\w.\-]+/[\w.\-]+", re.I)


# ---------------------------------------------------------------------------
# venue resolution
# ---------------------------------------------------------------------------

def core_venues(year: int) -> list[str]:
    # NeurIPS renamed the D&B track in 2024, so both spellings are tried; the
    # form that does not exist for a given year returns no notes and is skipped.
    return [
        f"NeurIPS.cc/{year}/Track/Datasets_and_Benchmarks",
        f"NeurIPS.cc/{year}/Datasets_and_Benchmarks_Track",
        # 2021 ran the D&B track in two rounds under their own ids
        f"NeurIPS.cc/{year}/Track/Datasets_and_Benchmarks_Round1",
        f"NeurIPS.cc/{year}/Track/Datasets_and_Benchmarks_Round2",
        f"NeurIPS.cc/{year}/Conference",
        f"ICLR.cc/{year}/Conference",
    ]


def adjacent_venues(year: int) -> list[str]:
    # other ML venues hosted on OpenReview. wrong/non-existent ids return
    # nothing and are skipped, so listing optimistically is safe.
    return [
        f"colmweb.org/COLM/{year}/Conference",
        f"rl-conference.cc/RLC/{year}/Conference",
        f"robot-learning.org/CoRL/{year}/Conference",
        "TMLR",  # rolling journal, not year-scoped
    ]


def discover_workshops(client, years: list[int], cap: int) -> tuple[list[str], int]:
    # scan the venues group for workshop ids in the requested years. returns the
    # (capped) list and how many were dropped so the cap is never silent.
    try:
        members = client.get_group("venues").members or []
    except Exception as exc:
        print(f"  (workshop discovery skipped: {exc})", file=sys.stderr)
        return [], 0
    year_strs = {str(y) for y in years}
    hits = sorted(
        vid for vid in members
        if "workshop" in vid.lower() and any(y in vid for y in year_strs)
    )
    if len(hits) > cap:
        return hits[:cap], len(hits) - cap
    return hits, 0


def venue_priority(venueid: str, venue_set: str) -> int:
    # dedup precedence used downstream: D&B > main conference > adjacent > workshop
    if is_dnb(venueid):
        return 0
    return {"core": 1, "adjacent": 2, "workshops": 3}.get(venue_set, 4)


def api_for_year(year: int | None) -> str:
    return "v1" if (year and year <= V1_CUTOFF_YEAR) else "v2"


def resolve_venues(args, clients: dict) -> list[tuple[str, str]]:
    # returns (venueid, venue_set) pairs, de-duplicated, in priority order.
    pairs: list[tuple[str, str]] = []
    for year in args.years:
        if "core" in args.venue_sets:
            pairs += [(v, "core") for v in core_venues(year)]
        if "adjacent" in args.venue_sets:
            pairs += [(v, "adjacent") for v in adjacent_venues(year)]
    if "workshops" in args.venue_sets and not args.no_discover:
        client = clients.get("v2") or clients.get("v1")
        shops, dropped = discover_workshops(client, args.years, args.max_workshops) if client else ([], 0)
        pairs += [(v, "workshops") for v in shops]
        if dropped:
            print(f"  NOTE: {dropped} workshop venues over --max-workshops={args.max_workshops} were dropped")
    pairs += [(v, "core") for v in args.venues]
    seen, ordered = set(), []
    for venueid, vset in sorted(pairs, key=lambda p: venue_priority(p[0], p[1])):
        if venueid not in seen:
            seen.add(venueid)
            ordered.append((venueid, vset))
    return ordered


# ---------------------------------------------------------------------------
# fetch (v1 + v2)
# ---------------------------------------------------------------------------

def with_retry(fn, label: str, tries: int = 3):
    # retry a few times to absorb rate-limiting and transient API errors.
    for attempt in range(1, tries + 1):
        try:
            return fn()
        except Exception as exc:
            if attempt == tries:
                print(f"  ! {label}: giving up after {tries} tries ({exc})", file=sys.stderr)
                return []
            wait = 2 * attempt
            print(f"  . {label}: retry {attempt}/{tries} in {wait}s ({exc})", file=sys.stderr)
            time.sleep(wait)
    return []


def fetch_v2(client, venueid: str) -> list[tuple]:
    # accepted papers in API v2 share the venue group id in content.venueid.
    notes = client.get_all_notes(content={"venueid": venueid})
    return [(n.id, getattr(n, "content", None) or {}, {}) for n in notes]


def fetch_v1(client, venueid: str) -> list[tuple]:
    # legacy double-blind venues: pull submissions, keep those whose decision
    # reply says Accept. real authors live on the de-anonymised `original`.
    out: list[tuple] = []
    for suffix in ("Blind_Submission", "Submission"):
        subs = client.get_all_notes(
            invitation=f"{venueid}/-/{suffix}", details="directReplies,original")
        if not subs:
            continue
        for s in subs:
            details = getattr(s, "details", None) or {}
            decision = ""
            for reply in details.get("directReplies", []) or []:
                if str(reply.get("invitation", "")).endswith("Decision"):
                    dec = (reply.get("content", {}) or {}).get("decision", "")
                    decision = dec.get("value", dec) if isinstance(dec, dict) else dec
                    break
            if "accept" not in str(decision).lower():
                continue
            extra = (details.get("original") or {}).get("content", {}) or {}
            out.append((s.id, getattr(s, "content", None) or {}, extra))
        if out:
            break  # found the invitation this venue actually uses
    return out


def fetch_venue(venueid: str, year: int | None, clients: dict, api_mode: str,
                limit: int | None) -> tuple[list[tuple], str]:
    # try the API the year suggests first, then fall back to the other one.
    preferred = api_for_year(year)
    order = [preferred, "v2" if preferred == "v1" else "v1"]
    if api_mode != "both":
        order = [api_mode]
    fetchers = {"v1": fetch_v1, "v2": fetch_v2}
    for api in order:
        client = clients.get(api)
        if client is None:
            continue
        notes = with_retry(lambda: fetchers[api](client, venueid), venueid)
        if notes:
            return (notes[:limit] if limit else notes), api
    return [], preferred


# ---------------------------------------------------------------------------
# enrich
# ---------------------------------------------------------------------------

def year_of(venueid: str, venue_str: str) -> str:
    for text in (venueid, venue_str):
        m = re.search(r"/(\d{4})/", text) or re.search(r"\b(20\d{2})\b", text)
        if m:
            return m.group(1)
    return ""


def pdf_url_of(content: dict) -> str:
    pdf = cval(content, "pdf")
    if not pdf:
        return ""
    pdf = str(pdf)
    return SITE + pdf if pdf.startswith("/") else pdf


def extract_arxiv(content: dict, abstract: str) -> tuple[str, str]:
    explicit = as_text(first_present(content, {}, "arxiv", "arxiv_id", "_arxiv"))
    m = ARXIV_RE.search(explicit) if explicit else None
    if not m:
        blob = " ".join(as_text(cval(content, k)) for k in ("_bibtex", "bibtex", "code"))
        m = ARXIV_RE.search(f"{blob} {abstract}")
    if not m:
        return "", ""
    arxiv_id = m.group(1) or m.group(2)
    return arxiv_id, f"https://arxiv.org/abs/{arxiv_id}"


def extract_code(content: dict, abstract: str) -> str:
    for key in ("code", "github", "supplementary_material", "_bibtex"):
        m = GITHUB_RE.search(as_text(cval(content, key)))
        if m:
            return m.group(0).rstrip(".,);")
    m = GITHUB_RE.search(abstract)
    return m.group(0).rstrip(".,);") if m else ""


def parse_decision(venue_str: str) -> str:
    low = venue_str.lower()
    for tier in ("oral", "spotlight", "poster"):
        if tier in low:
            return tier
    return "accepted"


def build_record(nid: str, content: dict, extra: dict,
                 venueid: str, venue_set: str, source_api: str) -> dict:
    title = as_text(cval(content, "title"))
    abstract = as_text(cval(content, "abstract"))
    keywords = as_text(cval(content, "keywords"))
    venue_str = as_text(cval(content, "venue"))
    authors_raw = first_present(content, extra, "authors")
    arxiv_id, arxiv_url = extract_arxiv(content, abstract)
    return {
        "openreview_id": nid,
        "title": title,
        "authors": as_text(authors_raw),
        "author_count": len(authors_raw) if isinstance(authors_raw, (list, tuple)) else (1 if authors_raw else 0),
        "year": year_of(venueid, venue_str),
        "source_venue": venue_str or venueid,
        "venueid": venueid,
        "venue_set": venue_set,
        "source_api": source_api,
        "is_dnb": is_dnb(venueid),
        "priority": venue_priority(venueid, venue_set),
        "decision": parse_decision(venue_str),
        "primary_area": as_text(first_present(content, {}, "primary_area", "subject_areas", "track"))
                        or (keywords.split(";")[0].strip() if keywords else ""),
        "abstract": abstract,
        "keywords": keywords,
        "tldr": as_text(first_present(content, {}, "TLDR", "tldr")),
        "arxiv_id": arxiv_id,
        "arxiv_url": arxiv_url,
        "code_url": extract_code(content, abstract),
        "forum_url": FORUM_URL.format(nid),
        "pdf_url": pdf_url_of(content),
    }


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------

def build_clients(api_mode: str) -> dict:
    try:
        import openreview
    except ImportError:
        print("ERROR: openreview-py is not installed. Run: pip install openreview-py",
              file=sys.stderr)
        raise SystemExit(2)
    user = os.environ.get("OPENREVIEW_USERNAME")
    pw = os.environ.get("OPENREVIEW_PASSWORD")
    clients: dict = {}
    if api_mode in ("v2", "both"):
        clients["v2"] = openreview.api.OpenReviewClient(baseurl=BASEURL_V2, username=user, password=pw)
    if api_mode in ("v1", "both"):
        clients["v1"] = openreview.Client(baseurl=BASEURL_V1, username=user, password=pw)
    return clients


def main() -> int:
    ap = argparse.ArgumentParser(description="OpenReview collection: harvest accepted papers into a raw cache.")
    ap.add_argument("--years", type=int, nargs="+", default=DEFAULT_YEARS,
                    help=f"venue years to sweep (default: {DEFAULT_YEARS[0]}-{DEFAULT_YEARS[-1]})")
    ap.add_argument("--venues", nargs="+", default=[], help="extra venue ids to include verbatim")
    ap.add_argument("--api", choices=["v1", "v2", "both"], default="both",
                    help="which OpenReview API to query (default: both)")
    ap.add_argument("--venue-sets", nargs="+", default=DEFAULT_VENUE_SETS,
                    choices=["core", "adjacent", "workshops"],
                    help="which venue groups to include (default: all three)")
    ap.add_argument("--max-workshops", type=int, default=60,
                    help="cap on discovered workshop venues (default: 60)")
    ap.add_argument("--out", type=Path, default=OUT_DEFAULT, help="raw cache CSV path")
    ap.add_argument("--log", type=Path, default=LOG_DEFAULT, help="per-venue run log path")
    ap.add_argument("--limit", type=int, default=None, help="cap notes per venue (smoke testing)")
    ap.add_argument("--no-discover", action="store_true", help="skip workshop auto-discovery")
    args = ap.parse_args()

    clients = build_clients(args.api)
    venues = resolve_venues(args, clients)

    print("=" * 64)
    print("OPENREVIEW COLLECTION (stage 1 of 2)")
    print("=" * 64)
    print(f"years      : {args.years[0]}-{args.years[-1]}")
    print(f"venue sets : {args.venue_sets}")
    print(f"api        : {args.api}")
    print(f"venues     : {len(venues)} candidate ids")
    print(f"limit/venue: {args.limit or 'none'}")
    print("-" * 64)

    rows: list[dict] = []
    log_rows: list[dict] = []
    skipped = 0

    for venueid, venue_set in venues:
        year = int(year_of(venueid, "")) if year_of(venueid, "") else None
        notes, api = fetch_venue(venueid, year, clients, args.api, args.limit)
        if not notes:
            skipped += 1
            log_rows.append({"venueid": venueid, "venue_set": venue_set, "source_api": "",
                             "n_accepted": 0, "status": "empty/skipped"})
            print(f"  -  {venueid}: 0 papers")
            continue
        for nid, content, extra in notes:
            rows.append(build_record(nid, content, extra, venueid, venue_set, api))
        log_rows.append({"venueid": venueid, "venue_set": venue_set, "source_api": api,
                         "n_accepted": len(notes), "status": "ok"})
        print(f"  +  {venueid} [{api}]: {len(notes)} papers")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=RAW_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    with args.log.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["venueid", "venue_set", "source_api", "n_accepted", "status"])
        w.writeheader()
        w.writerows(log_rows)

    print("-" * 64)
    print(f"papers collected: {len(rows)}")
    print(f"venues with data: {sum(1 for r in log_rows if r['n_accepted'])}")
    if skipped:
        print(f"venues skipped  : {skipped} (0 papers; wrong-form id or no data for that year/api)")
    print(f"wrote {args.out}")
    print(f"wrote {args.log}")
    print("next: python openreview_validate.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
