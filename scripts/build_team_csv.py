#!/usr/bin/env python3
"""Assemble the team benchmark-metadata CSV requested in the 2026-07-08 meeting.

Required columns (Zhijing's schema):
  data_uniq_id, human_readable_50_char_summary, download_url,
  regulation_id, risk_id, if_in_openai_system_card, if_in_claude, if_in_gemini

Mapping chain: benchmark --edge--> harm (risk_id) --subdomain--> CoP provision (regulation_id).
Top-down cut (meeting priority): keep every benchmark named in a frontier system
card, then fill to --cap total by citation rank.

Inputs are all already in the repo; run extract_system_cards.py first so
system_card_flags.csv exists.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote_plus

DATA = Path("outputs/hf_upload_esai_benchmark_map_v1/data")


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def load_jsonl(p: Path):
    return [json.loads(l) for l in open(p, encoding="utf-8")]


def subdomain_of(harm_id: str) -> str:
    parts = harm_id.split(".")
    return f"{int(parts[0])}.{int(parts[1])}"


# Canonical EU GPAI Code of Practice Appendix 1.4 numbering for the four specified
# systemic risks (order verified against the published CoP: 1.4.1 CBRN, 1.4.2 loss
# of control, 1.4.3 cyber offence, 1.4.4 harmful manipulation). Used to render a
# uniform regulation_id instead of the crosswalk's mixed prose/number cop_ref.
COP_REF = {
    "CBRN": "CoP App 1.4.1",
    "loss of control": "CoP App 1.4.2",
    "cyber offence": "CoP App 1.4.3",
    "harmful manipulation": "CoP App 1.4.4",
}

# Hand-written <=50-char summaries for the flagged, well-known system-card evals
# (the headline rows). Everything else uses the auto-derived summary below.
SUMMARY_OVERRIDES = {
    "B44.01.01":  "MMLU-Pro: harder multi-task knowledge test",
    "B25.01.01":  "MMLU: 57-subject multitask knowledge test",
    "B374.01.01": "Global-MMLU: multilingual culture-aware MMLU",
    "B342.01.01": "GPQA: graduate-level google-proof Q&A",
    "B45.01.01":  "Humanity's Last Exam: frontier expert Q&A",
    "B215.01.01": "LiveCodeBench: contamination-free code eval",
    "B379.01.01": "SWE-bench: resolve real GitHub issues",
    "B380.01.01": "MLE-bench: ML-engineering agent tasks",
    "B384.01.01": "SWE-Lancer: real freelance software tasks",
    "B383.01.01": "GDPval: economically valuable real-world tasks",
    "B385.01.01": "WebArena: web-agent tasks on realistic sites",
    "B281.01.01": "FActScore: atomic factual precision of LLMs",
    "B284.01.01": "SimpleQA: short-form factuality eval",
    "B333.01.01": "StrongREJECT: jailbreak-refusal robustness",
}

# Face-validity risk mappings the mapper added for cut benchmarks that had NO
# benchmark->harm edge in the dataset (||-merged or newly-added records). Harm
# ids chosen to match how sibling benchmarks were mapped (e.g. GPQA -> the same
# 7.03 capability nodes as MMLU). Basis: face-validity-only.
MAPPING_OVERRIDES = {
    "B333.01.01": ["7.03.10"],                       # jailbreak / refusal robustness
    "B342.01.01": ["7.03.13", "7.03.63", "7.03.64"], # GPQA: knowledge/task capability (as MMLU)
    "B398.01.01": ["6.03.03"],                       # output homogenization / loss of diversity
    "B257.01.01": ["6.03.01"],                       # training-data provenance / memorization
    "B358.02.01": ["7.03.64"],                       # backdoor: robustness/integrity failure
    "B280.01.01": ["7.03.12", "7.03.13"],            # historical capability: factual accuracy + task
    "B296.01.01": ["3.02.02"],                       # deepfake detection: info-ecosystem pollution
    "B1.01.01":   ["1.02.18"],                       # cross-country content moderation: toxic content
}


# Function words a truncated title must not END on (reads as cut-off mid-phrase,
# e.g. "A Comprehensive Benchmark for" / "Rethinking Temporal Signal of").
_TRAIL_STOP = {
    "for", "of", "the", "a", "an", "and", "or", "to", "in", "on", "with", "from",
    "as", "at", "by", "into", "via", "using", "towards", "toward", "through",
    "under", "over", "about", "that", "this", "their", "its", "our",
}


def _trim_trailing(s: str) -> str:
    words = s.split()
    while len(words) > 1 and re.sub(r"[^\w]", "", words[-1]).lower() in _TRAIL_STOP:
        words.pop()
    return " ".join(words)


def _clip(s: str, n: int = 50) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) <= n:
        return _trim_trailing(s)
    cut = s[:n].rsplit(" ", 1)[0]
    cut = cut if len(cut) >= n - 12 else s[:n]
    return _trim_trailing(cut.strip())


def summary_50(bid: str, title: str) -> str:
    if bid in SUMMARY_OVERRIDES:
        return SUMMARY_OVERRIDES[bid]
    title = title.split("||", 1)[0].strip()  # ||-merged: describe the first paper
    # If the title is "Name: descriptive clause" and Name looks like a benchmark
    # name, keep the name so the row is identifiable (fixes "A Dynamic ..." blurbs).
    if ":" in title:
        head, body = (p.strip() for p in title.split(":", 1))
        if 2 <= len(head) <= 20 and len(head.split()) <= 3 and re.search(r"[A-Za-z]", head):
            return _clip(f"{head}: {body}")
        return _clip(body)
    return _clip(title)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cap", type=int, default=200)
    ap.add_argument("--outdir", default="outputs/team_deliverable")
    args = ap.parse_args()
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)

    benches = load_jsonl(DATA / "benchmarks.jsonl")
    edges = load_jsonl(DATA / "benchmark_harm_edges.jsonl")

    # benchmark -> set(harm_id)
    bid_harms = defaultdict(set)
    for e in edges:
        bid_harms[e["benchmark_id"]].add(e["harm_id"])

    # CoP crosswalk: subdomain -> [(cop_ref, named_risk), ...]
    # NB the crosswalk is many-to-many: subdomain 4.2 -> {CBRN, cyber} and 7.2 ->
    # {CBRN, loss of control}. Accumulate all pairs (a plain dict silently kept
    # only the last row, dropping CBRN/cyber assignments).
    cop = defaultdict(list)
    for r in csv.DictReader(open("../../esai-work/6-four-risk-mvp/risk-to-benchmark-crosswalk.csv",
                                 encoding="utf-8")):
        cop[r["mit_subdomain"]].append((r["cop_ref"], r["named_systemic_risk"]))

    # system-card flags
    flags = {}
    fp = Path("outputs/system_cards/system_card_flags.csv")
    for r in csv.DictReader(open(fp, encoding="utf-8")):
        flags[r["benchmark_id"]] = (
            r["if_in_openai_system_card"] == "True",
            r["if_in_claude"] == "True",
            r["if_in_gemini"] == "True",
        )

    # citations by normalized title (max of providers)
    cites = {}
    mp = Path("outputs/full_run/metadata_enrichment_merged.csv")
    if mp.exists():
        for r in csv.DictReader(open(mp, encoding="utf-8")):
            vals = []
            for k in ("crossref_cited_by_count", "semantic_scholar_citation_count",
                      "openalex_cited_by_count"):
                v = r.get(k, "")
                if v not in ("", None):
                    try:
                        vals.append(int(float(v)))
                    except ValueError:
                        pass
            if vals:
                cites[norm(r["title"])] = max(vals)

    # download url: (1) human-verified arxiv from Wilber's 6.x source sheets by benchmark_id,
    # (2) title match to ACL papers / candidates
    url_by_bid = {}
    for f in Path("../../esai-work").rglob("*sources*.csv"):
        for r in csv.DictReader(open(f, encoding="utf-8")):
            u = r.get("source_citation_url") or r.get("source_url") or ""
            if r.get("benchmark_id") and u.strip():
                url_by_bid.setdefault(r["benchmark_id"], u.strip())

    # DOI by normalized title (stable id + the key Crossref citation enrichment uses).
    # DOIs are scarce here (mostly ACL); most of our set is arXiv/OpenReview.
    doi_by_title = {}
    def add_doi(title, doi):
        if title and doi:
            doi_by_title.setdefault(norm(title), doi.strip())
    for r in load_jsonl(DATA / "papers.jsonl"):
        add_doi(r.get("title", ""), (r.get("external_ids") or {}).get("doi", ""))
    for l in open(DATA / "benchmark_candidates.jsonl", encoding="utf-8"):
        r = json.loads(l)
        add_doi(r.get("title", ""), r.get("doi", ""))
    _cand = Path("outputs/full_run/candidates_relevant.csv")
    if _cand.exists():
        for r in csv.DictReader(open(_cand, encoding="utf-8")):
            add_doi(r.get("title", ""), r.get("doi", ""))

    url_by_title = {}
    def add_urls(rows, tkey="title"):
        for r in rows:
            t = norm(r.get(tkey, ""))
            if not t or t in url_by_title:
                continue
            u = (r.get("code_url") or r.get("paper_url") or r.get("pdf_url") or "").strip()
            if not u:
                doi = (r.get("doi") or "").strip()
                if not doi and isinstance(r.get("external_ids"), dict):
                    doi = r["external_ids"].get("doi", "")
                if doi:
                    u = doi if doi.startswith("http") else f"https://doi.org/{doi}"
            if u:
                url_by_title[t] = u
    cand = Path("outputs/full_run/candidates_relevant.csv")
    if cand.exists():
        add_urls(list(csv.DictReader(open(cand, encoding="utf-8"))))
    add_urls(load_jsonl(DATA / "papers.jsonl"))

    # verified citation backfills (S2 bulk, strict title match) for headline rows
    cit_override = {}
    _cb = Path("outputs/team_deliverable/_citation_backfill.json")
    if _cb.exists():
        cit_override = {k: int(v) for k, v in json.load(open(_cb)).items()}

    # loadable-data URLs (HF dataset / GitHub repo) for Tae's pipeline: mined from
    # the paper's code_url in the corpus + a hand-curated, existence-verified set
    # for the headline benchmarks. Only authoritative matches; NOT fuzzy name hits.
    dataset_url = {}
    _du = Path("outputs/team_deliverable/_dataset_urls.json")
    if _du.exists():
        dataset_url = json.load(open(_du))

    # direct paper-link upgrades for rows that would otherwise be a search-fallback
    # (resolved by strict title match via S2/arXiv). Overrides the fallback link.
    url_upgrade = {}
    _uu = Path("outputs/team_deliverable/_url_upgrades.json")
    if _uu.exists():
        url_upgrade = json.load(open(_uu))

    rows = []
    for b in benches:
        bid = b["benchmark_id"]
        title = b["title"]
        if bid in MAPPING_OVERRIDES:
            harms = sorted(MAPPING_OVERRIDES[bid])
            risk_src = "mapper-face-validity"
        else:
            harms = sorted(bid_harms.get(bid, []))
            risk_src = "dataset-edge" if harms else ""
        subs = sorted({subdomain_of(h) for h in harms})
        risks = sorted({risk for s in subs for _, risk in cop.get(s, [])})
        # uniform CoP Appendix 1.4 numbering (canonical order, verified against the
        # published Code of Practice); derived from the named risk so the label is
        # consistent regardless of the crosswalk's cop_ref formatting.
        regs = sorted({COP_REF[r] for r in risks if r in COP_REF})
        o, c, g = flags.get(bid, (False, False, False))
        cit = cit_override.get(bid, cites.get(norm(title), -1))
        url = url_by_bid.get(bid) or url_by_title.get(norm(title), "")
        if url:
            url_source = "corpus"
        elif bid in url_upgrade:
            # strict title-matched direct link (arXiv/DOI/PDF) resolved for a row
            # that had no corpus URL -- better than a search box.
            url = url_upgrade[bid]
            url_source = "resolved-direct"
        else:
            # honest fallback: a resolver that finds the paper/dataset by title.
            url = "https://www.semanticscholar.org/search?q=" + quote_plus(title) + "&sort=relevance"
            url_source = "title-search-fallback"
        rows.append({
            "data_uniq_id": bid,
            "human_readable_50_char_summary": summary_50(bid, title),
            "download_url": url,
            "dataset_url": dataset_url.get(bid, ""),
            "download_url_source": url_source,
            "doi": doi_by_title.get(norm(title), ""),
            "regulation_id": ";".join(regs),
            "risk_id": ";".join(harms),
            "risk_id_source": risk_src,
            "if_in_openai_system_card": o,
            "if_in_claude": c,
            "if_in_gemini": g,
            # helpful extras (beyond the required 8)
            "benchmark_uuid": b["uuid"],
            "quick_ref": b.get("quick_ref", ""),
            "title": title,
            "named_systemic_risks": ";".join(risks),
            "citations": cit if cit >= 0 else "",
            "in_any_system_card": o or c or g,
        })

    # Top-down cut, tiered per the meeting priority ("heavily used = system card
    # and highly cited" + "start from regulation ID and risk ID"):
    #   tier 0: named in a frontier system card   (always kept)
    #   tier 1: mapped to an EU CoP systemic risk  (regulation_id present)
    #   tier 2: everything else
    # within each tier, rank by citation count (missing -> last).
    def cit_key(r):
        return r["citations"] if r["citations"] != "" else -1

    def tier(r):
        if r["in_any_system_card"]:
            return 0
        if r["regulation_id"]:
            return 1
        return 2

    # De-duplicate the cut pool: some benchmarks appear as two extraction records
    # with byte-identical titles but different UUIDs (e.g. SimpleQA, RAGTruth).
    # Collapse by normalized title, keeping the best-populated representative
    # (system-card > real url > more citations > lower id) so a team slot is never
    # spent twice on the same benchmark. The full all417 file keeps every record.
    def rep_key(r):
        # keep the most complete twin: system-card > has a risk mapping > real url
        # > more citations > lower id. "has risk mapping" guards the hand-mapped
        # twin (e.g. BackdoorLLM B358.02.01) from losing to its unmapped copy.
        return (r["in_any_system_card"], bool(r["risk_id"]),
                r["download_url_source"] == "corpus", cit_key(r),
                -int(re.sub(r"\D", "", r["data_uniq_id"]) or 0))

    best_by_title = {}
    for r in rows:
        t = norm(r["title"].split("||", 1)[0])
        if t not in best_by_title or rep_key(r) > rep_key(best_by_title[t]):
            best_by_title[t] = r
    deduped = list(best_by_title.values())
    n_dups = len(rows) - len(deduped)

    ranked = sorted(deduped, key=lambda r: (tier(r), -cit_key(r)))
    cut = ranked[: args.cap]

    cols = ["data_uniq_id", "human_readable_50_char_summary", "download_url",
            "dataset_url", "regulation_id", "risk_id", "if_in_openai_system_card",
            "if_in_claude", "if_in_gemini", "doi", "risk_id_source",
            "download_url_source", "benchmark_uuid", "quick_ref", "title",
            "named_systemic_risks", "citations", "in_any_system_card"]

    def write(path, data):
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(data)

    write(out / "benchmark_metadata_team.csv", cut)
    write(out / "benchmark_metadata_all417.csv", rows)

    n_sc = sum(1 for r in cut if r["in_any_system_card"])
    n_real = sum(1 for r in cut if r["download_url_source"] == "corpus")
    n_reg = sum(1 for r in cut if r["regulation_id"])
    print(f"total benchmarks: {len(rows)}  | system-card hits (all): "
          f"{sum(1 for r in rows if r['in_any_system_card'])}  | cut: {len(cut)}")
    print(f"cut: system_card {n_sc}  regulation_mapped {n_reg}  real_url {n_real}")
    print(f"deduped title-duplicates before cut: {n_dups}")
    print(f"wrote {out/'benchmark_metadata_team.csv'} (cut) and benchmark_metadata_all417.csv (full)")


if __name__ == "__main__":
    main()
