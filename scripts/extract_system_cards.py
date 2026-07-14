#!/usr/bin/env python3
"""Extract text from the frontier system-card PDFs and cross-reference the named
benchmarks/evals against the ESAI 417-benchmark set.

Provider grouping (a benchmark is flagged for a provider if it appears in ANY of
that provider's cards):
  openai  -> openai_*.pdf
  claude  -> anthropic_*.pdf
  gemini  -> google_*.pdf

Outputs (into --outdir):
  text/<card>.txt                 cached plain text per card
  system_card_match_report.csv    per-benchmark alias hits with the matched card + snippet (auditable)
  system_card_flags.csv           benchmark_id, if_in_openai, if_in_claude, if_in_gemini

Matching is alias-based and conservative: each benchmark contributes distinctive
name aliases (parenthetical acronyms, a short pre-colon name) that must be
mixed-case / hyphenated / contain a digit, so generic English words don't match.
Every hit is written to the report with a text snippet for human verification.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

from pypdf import PdfReader

PROVIDER_BY_PREFIX = {"openai": "openai", "anthropic": "claude", "google": "gemini"}


def token_re(name: str) -> re.Pattern:
    # exact, hyphen-aware boundaries -- used to recognize known evals inside our
    # (clean) benchmark titles. "MMLU" must NOT match inside "MMLU-Pro".
    return re.compile(r"(?<![A-Za-z0-9-])" + re.escape(name) + r"(?![A-Za-z0-9-])",
                      re.IGNORECASE)


def fuzzy_token_re(name: str) -> re.Pattern:
    """Gap-tolerant matcher for CARD text, where PDF/figure/table extraction splits
    names with stray spaces or hyphens ("SWE-Bench Verified", "S W E bench",
    "Simple QA"). Allow <=2 non-alphanumerics between characters, but keep
    hyphen-aware OUTER boundaries so "MMLU" still won't match inside "MMLU-Pro"."""
    chars = [re.escape(c) for c in name if c.isalnum()]
    body = r"[^A-Za-z0-9]{0,2}".join(chars)
    return re.compile(r"(?<![A-Za-z0-9-])" + body + r"(?![A-Za-z0-9-])", re.IGNORECASE)


LIGATURES = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl",
             "‐": "-", "‑": "-", "‒": "-", "–": "-",
             "—": "-", "­": ""}


def normalize_text(t: str) -> str:
    for k, v in LIGATURES.items():
        t = t.replace(k, v)
    return t

# Distinctive-form guard: an alias is only usable if it looks like a proper
# benchmark name, not a common word. Require length>=4 AND at least one of:
# an internal uppercase, a hyphen, or a digit.
DISTINCTIVE = re.compile(r"[a-z][A-Z]|[A-Z][a-z].*[A-Z]|-|\d")
# Aliases that pass the distinctive test but are provider/model names or generic
# words -> would match everywhere. Compared case-insensitively.
STOPLIST = {s.lower() for s in {
    "LLMs", "LLM", "AI", "GPT", "NLP", "OpenAI", "Anthropic", "Google", "Claude",
    "Gemini", "Llama", "Mistral", "DeepSeek", "CaLM", "calm", "SAD", "MASK",
    "PAIR", "FAIR", "GAME", "BOLD", "TRUE", "BASE", "CARE", "PROSE",
}}

# Curated well-known evals frequently named in frontier system cards. Bidirectional:
# used both to recognize the eval inside our benchmark titles and to search the
# card text. Distinctive enough for case-insensitive word-boundary matching.
KNOWN_EVALS = [
    "GPQA", "MMLU-Pro", "Global-MMLU", "MMLU", "MMMU", "WMDP", "HarmBench",
    "StrongREJECT", "AgentHarm", "GAIA", "tau-bench", "TruthfulQA", "BBQ",
    "AdvBench", "CyberSecEval", "RepliBench", "MACHIAVELLI", "AgentBench",
    "SimpleQA", "FActScore", "SWE-bench", "SWE-Lancer", "WebArena", "MLE-bench",
    "GDPval", "BrowseComp", "FrontierMath", "AIME", "HumanEval", "Do-Not-Answer",
]


def provider_of(path: Path) -> str | None:
    stem = path.stem.lower()
    for prefix, prov in PROVIDER_BY_PREFIX.items():
        if stem.startswith(prefix):
            return prov
    return None


def extract_text(pdf: Path, cache_dir: Path) -> str:
    cache = cache_dir / (pdf.stem + ".txt")
    if cache.exists() and cache.stat().st_mtime >= pdf.stat().st_mtime:
        return cache.read_text(encoding="utf-8", errors="ignore")
    reader = PdfReader(str(pdf))
    parts = []
    for pg in reader.pages:
        try:
            parts.append(pg.extract_text() or "")
        except Exception:
            parts.append("")
    text = normalize_text("\n".join(parts))
    cache.write_text(text, encoding="utf-8")
    return text


def aliases_for(title: str) -> set[str]:
    out: set[str] = set()
    # 1) curated known evals appearing anywhere in the title (handles ||-merged
    #    records and mid-title names the heuristic below would miss)
    for name in KNOWN_EVALS:
        if token_re(name).search(title):
            out.add(name)
    # 2) heuristic: parenthetical acronyms  (SAD), (CFPD-Benchmark)
    for m in re.findall(r"\(([A-Za-z][A-Za-z0-9\-]{2,20})\)", title):
        out.add(m.strip())
    # 3) heuristic: pre-colon short name  "ProSA: ...", "MultiAgentBench: ..."
    if ":" in title:
        head = title.split(":", 1)[0].strip()
        if 3 <= len(head) <= 25 and len(head.split()) <= 3:
            out.add(head)
            out.add(head.split()[-1])
    keep = set()
    for a in out:
        a = a.strip().strip("-")
        if len(a) < 4 or a.lower() in STOPLIST:
            continue
        if a in KNOWN_EVALS or DISTINCTIVE.search(a):
            keep.add(a)
    return keep


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cards-dir", default="../../references/system_cards")
    ap.add_argument("--benchmarks",
                    default="outputs/hf_upload_esai_benchmark_map_v1/data/benchmarks.jsonl")
    ap.add_argument("--outdir", default="outputs/system_cards")
    args = ap.parse_args()

    cards_dir = Path(args.cards_dir).resolve()
    outdir = Path(args.outdir)
    text_dir = outdir / "text"
    text_dir.mkdir(parents=True, exist_ok=True)

    # 1) provider -> concatenated text
    provider_text: dict[str, str] = {"openai": "", "claude": "", "gemini": ""}
    cards_seen: dict[str, list[str]] = {"openai": [], "claude": [], "gemini": []}
    for pdf in sorted(cards_dir.glob("*.pdf")):
        prov = provider_of(pdf)
        if prov is None:
            print(f"  skip (unknown provider): {pdf.name}")
            continue
        txt = extract_text(pdf, text_dir)
        provider_text[prov] += "\n" + txt
        cards_seen[prov].append(pdf.stem)
        print(f"  {prov:7s} <- {pdf.name} ({len(txt):,} chars)")
    for prov, cards in cards_seen.items():
        print(f"provider {prov}: {len(cards)} cards")

    # 2) benchmarks + aliases
    benches = [json.loads(l) for l in open(args.benchmarks, encoding="utf-8")]

    report_rows = []
    flags = {}
    for b in benches:
        bid = b["benchmark_id"]
        title = b["title"]
        al = aliases_for(title)
        prov_hit = {"openai": False, "claude": False, "gemini": False}
        for prov, text in provider_text.items():
            for a in al:
                m = fuzzy_token_re(a).search(text)
                if m:
                    prov_hit[prov] = True
                    s = max(0, m.start() - 45)
                    snippet = text[s:m.end() + 45].replace("\n", " ")
                    report_rows.append({
                        "benchmark_id": bid, "title": title[:60],
                        "alias": a, "provider": prov, "matched": m.group(0),
                        "snippet": re.sub(r"\s+", " ", snippet).strip(),
                    })
                    break
        flags[bid] = prov_hit

    outdir.mkdir(parents=True, exist_ok=True)
    with open(outdir / "system_card_match_report.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["benchmark_id", "title", "alias", "provider", "matched", "snippet"])
        w.writeheader()
        w.writerows(sorted(report_rows, key=lambda r: (r["benchmark_id"], r["provider"])))

    with open(outdir / "system_card_flags.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["benchmark_id", "if_in_openai_system_card", "if_in_claude", "if_in_gemini"])
        for bid, h in flags.items():
            w.writerow([bid, h["openai"], h["claude"], h["gemini"]])

    n_any = sum(1 for h in flags.values() if any(h.values()))
    n_o = sum(1 for h in flags.values() if h["openai"])
    n_c = sum(1 for h in flags.values() if h["claude"])
    n_g = sum(1 for h in flags.values() if h["gemini"])
    print(f"\nbenchmarks with >=1 card hit: {n_any}  (openai={n_o} claude={n_c} gemini={n_g})")
    print(f"match report rows: {len(report_rows)}")
    print(f"wrote {outdir/'system_card_match_report.csv'} and system_card_flags.csv")


if __name__ == "__main__":
    main()
