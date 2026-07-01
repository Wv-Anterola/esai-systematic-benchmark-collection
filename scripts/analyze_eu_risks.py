#!/usr/bin/env python3
"""EU four-risk citation analysis over the v1.0.0 benchmark-map package.

Maps each benchmark->harm edge to the EU CoP Appendix 1.4 named systemic risks
(CBRN, loss-of-control, cyber-offence, harmful-manipulation) using the
subdomain crosswalk from esai-work/6-four-risk-mvp/mvp-plan.md, enriches the
benchmarks that touch those risks with OpenAlex citation counts, and writes a
prioritized ranking plus citation histograms.

Outputs (into --outdir):
  named_systemic_risk_crosswalk.csv   subdomain -> risk(s)
  benchmark_eu_risk_edges.csv         per-edge risk tags (seed for backfill)
  prioritized_eu_benchmarks.csv       benchmarks in the 4 risks, ranked by cites
  citation_histogram.png              overall + per-risk citation distribution
  eu_risk_summary.json                coverage + citation summary

Usage:
  python scripts/analyze_eu_risks.py --package outputs/hf_upload_esai_benchmark_map_v1 \
      --outdir outputs/eu_risk_analysis
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import urllib.parse  # noqa: E402

from esai_collection.http import JsonHttpClient  # noqa: E402

OPENALEX_MAILTO = "acqresearch2025@gmail.com"


def openalex_citations(
    title: str, client: JsonHttpClient, *, attempts: int = 3
) -> int | None:
    """Best-effort OpenAlex citation count by title. None if unavailable."""
    if not title.strip():
        return None
    query = urllib.parse.quote(title.strip(), safe="")
    url = (
        f"https://api.openalex.org/works?search={query}&per-page=1"
        f"&select=id,display_name,cited_by_count&mailto={OPENALEX_MAILTO}"
    )
    for _ in range(attempts):
        payload, error = client.get_json(url)
        if isinstance(payload, dict) and payload.get("results"):
            return int(payload["results"][0].get("cited_by_count") or 0)
        if not error:  # valid empty result (no match)
            return None
    return None  # service error after retries (e.g. OpenAlex 503)


# Subdomain -> named systemic risk(s), from mvp-plan.md. A subdomain may seed
# more than one risk (e.g. 4.2 covers cyber-offence and CBRN weaponization);
# these are flagged for human disambiguation, not treated as settled.
CROSSWALK: dict[str, list[str]] = {
    "4.1": ["harmful-manipulation"],
    "4.3": ["harmful-manipulation"],
    "5.2": ["harmful-manipulation"],
    "3.2": ["harmful-manipulation"],
    "2.2": ["cyber-offence"],
    "4.2": ["cyber-offence", "CBRN"],
    "7.2": ["CBRN", "loss-of-control"],
    "7.1": ["loss-of-control"],
    "7.3": ["loss-of-control"],
    "7.6": ["loss-of-control"],
}
RISKS = ["CBRN", "loss-of-control", "cyber-offence", "harmful-manipulation"]


def _load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _subdomain_code(harm_id: str) -> str:
    parts = harm_id.split(".")
    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
        return f"{int(parts[0])}.{int(parts[1])}"
    return ""


def _risks_for(harm_id: str) -> list[str]:
    return CROSSWALK.get(_subdomain_code(harm_id), [])


def _write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--delay-seconds", type=float, default=0.1)
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    data = args.package / "data"
    harms = {h["harm_id"]: h for h in _load_jsonl(data / "harms.jsonl")}
    edges = _load_jsonl(data / "benchmark_harm_edges.jsonl")
    benchmarks = {b["benchmark_id"]: b for b in _load_jsonl(data / "benchmarks.jsonl")}
    args.outdir.mkdir(parents=True, exist_ok=True)

    # 1. crosswalk table
    _write_csv(
        args.outdir / "named_systemic_risk_crosswalk.csv",
        [
            {"subdomain": code, "named_systemic_risks": ";".join(risks)}
            for code, risks in sorted(CROSSWALK.items())
        ],
        ["subdomain", "named_systemic_risks"],
    )

    # 2. per-edge risk tags + benchmark -> risk rollup
    edge_rows: list[dict] = []
    bench_risks: dict[str, set[str]] = {}
    coverage = {risk: 0 for risk in RISKS}
    for edge in edges:
        risks = _risks_for(edge["harm_id"])
        harm = harms.get(edge["harm_id"], {})
        edge_rows.append(
            {
                "edge_id": edge["edge_id"],
                "benchmark_id": edge["benchmark_id"],
                "harm_id": edge["harm_id"],
                "subdomain": harm.get("subdomain", ""),
                "named_systemic_risks": ";".join(risks),
            }
        )
        for risk in risks:
            coverage[risk] += 1
            bench_risks.setdefault(edge["benchmark_id"], set()).add(risk)
    _write_csv(
        args.outdir / "benchmark_eu_risk_edges.csv",
        edge_rows,
        ["edge_id", "benchmark_id", "harm_id", "subdomain", "named_systemic_risks"],
    )

    # 3. enrich the in-scope benchmarks with OpenAlex citations (best-effort)
    scope_ids = sorted(bench_risks)
    client = JsonHttpClient(timeout=args.timeout, delay_seconds=args.delay_seconds)
    cites_by_id: dict[str, int | None] = {}
    for bid in scope_ids:
        cites_by_id[bid] = openalex_citations(
            benchmarks.get(bid, {}).get("title", ""), client
        )
    matched = [bid for bid in scope_ids if cites_by_id[bid] is not None]
    citations_available = bool(matched)

    ranked = sorted(scope_ids, key=lambda bid: (cites_by_id[bid] or 0), reverse=True)
    _write_csv(
        args.outdir / "prioritized_eu_benchmarks.csv",
        [
            {
                "rank": i + 1,
                "benchmark_id": bid,
                "quick_ref": benchmarks.get(bid, {}).get("quick_ref", ""),
                "title": benchmarks.get(bid, {}).get("title", ""),
                "named_systemic_risks": ";".join(sorted(bench_risks[bid])),
                "citations": "" if cites_by_id[bid] is None else cites_by_id[bid],
            }
            for i, bid in enumerate(ranked)
        ],
        [
            "rank",
            "benchmark_id",
            "quick_ref",
            "title",
            "named_systemic_risks",
            "citations",
        ],
    )

    # 4. charts: coverage always; citation histogram only when data is available
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    bench_by_risk = {
        risk: sum(1 for b in bench_risks.values() if risk in b) for risk in RISKS
    }
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    axes[0].bar(RISKS, [coverage[r] for r in RISKS], color="#c44", label="edges")
    axes[0].bar(
        RISKS, [bench_by_risk[r] for r in RISKS], color="#36b", label="benchmarks"
    )
    axes[0].set_title("Current dataset coverage per EU named risk")
    axes[0].set_ylabel("count")
    axes[0].tick_params(axis="x", labelsize=8, rotation=20)
    axes[0].legend()

    if citations_available:
        values = [cites_by_id[bid] for bid in matched]
        axes[1].hist(values, bins=30, color="#3b6", edgecolor="black")
        axes[1].set_title(f"Citations of in-scope benchmarks (n={len(matched)})")
        axes[1].set_xlabel("OpenAlex citations")
        axes[1].set_ylabel("benchmarks")
    else:
        axes[1].axis("off")
        axes[1].text(
            0.5,
            0.5,
            "Citation data unavailable\n(OpenAlex search returned 503).\n"
            "Re-run this script when the\nservice recovers.",
            ha="center",
            va="center",
            fontsize=12,
        )
    fig.tight_layout()
    fig.savefig(args.outdir / "citation_histogram.png", dpi=120)

    # 5. summary
    values = [cites_by_id[bid] for bid in matched]
    summary = {
        "benchmarks_in_scope": len(scope_ids),
        "edge_coverage_by_risk": coverage,
        "benchmark_coverage_by_risk": bench_by_risk,
        "citations_available": citations_available,
        "citation_stats": {
            "matched": len(matched),
            "max": max(values) if values else None,
            "median": sorted(values)[len(values) // 2] if values else None,
        },
        "top_10": [
            {
                "benchmark_id": bid,
                "title": benchmarks.get(bid, {}).get("title", "")[:80],
                "risks": sorted(bench_risks[bid]),
                "citations": cites_by_id[bid],
            }
            for bid in ranked[:10]
        ],
    }
    (args.outdir / "eu_risk_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    print(f"\nWrote EU risk analysis to {args.outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
