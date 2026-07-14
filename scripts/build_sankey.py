#!/usr/bin/env python3
"""Build the benchmark-coverage Sankey for the weekly figure (Zhijing's column-3).

The project's canonical figure reads Evidence -> Harm -> Legal. This Sankey
renders our benchmark collection as that flow, weighted by how many benchmarks
cover each risk:

    Risk domain  ->  Risk subdomain  ->  EU named systemic risk

Left/middle come from the MIT risk taxonomy (our harm hub); the right column is
the four CoP App. 1.4 systemic-risk categories, so the picture shows both our
coverage and its relevance to the EU AI Act. Flow width = number of
benchmark->harm edges.

Input : outputs/eu_risk_analysis/benchmark_eu_risk_edges.csv
Output: outputs/sankey/benchmark_coverage_sankey.html  (self-contained)
        outputs/sankey/benchmark_coverage_sankey.png   (if kaleido present)
"""
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

import plotly.graph_objects as go

EDGES = Path("outputs/eu_risk_analysis/benchmark_eu_risk_edges.csv")
OUTDIR = Path("outputs/sankey")

# Top-level MIT risk domains (first digit of the subdomain id).
DOMAIN_NAMES = {
    "1": "1 · Discrimination & toxicity",
    "2": "2 · Privacy & security",
    "3": "3 · Misinformation",
    "4": "4 · Malicious use",
    "5": "5 · Human-computer interaction",
    "6": "6 · Socioeconomic & environmental",
    "7": "7 · AI system safety & limitations",
}

# Palette: one hue per domain (qualitative, muted), grey for the unmapped sink.
DOMAIN_COLOR = {
    "1": "#4c78a8",
    "2": "#72b7b2",
    "3": "#e45756",
    "4": "#b279a2",
    "5": "#f58518",
    "6": "#54a24b",
    "7": "#9d755d",
}
NAMED_COLOR = "#3b6fd4"
UNMAPPED_COLOR = "#b6bec9"

NAMED_LABELS = {
    "CBRN": "CBRN",
    "loss-of-control": "Loss of control",
    "cyber-offence": "Cyber offence",
    "harmful-manipulation": "Harmful manipulation",
}
UNMAPPED = "Not a named systemic risk"


def short_subdomain(raw: str) -> str:
    """'6.6 > Environmental harm' -> '6.6 Environmental harm' (trimmed)."""
    txt = raw.replace(" > ", " ")
    return txt if len(txt) <= 46 else txt[:44] + "…"


def domain_key(subdomain_raw: str) -> str:
    return subdomain_raw.strip()[0]


def hex_to_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def main() -> int:
    rows = list(csv.DictReader(EDGES.open(encoding="utf-8-sig")))

    # Aggregate edge counts for the two link stages.
    dom_sub = Counter()  # (domain, subdomain) -> count
    sub_named = Counter()  # (subdomain, named-or-unmapped) -> count
    sub_domain: dict[str, str] = {}

    for row in rows:
        sub_raw = row["subdomain"].strip()
        dom = domain_key(sub_raw)
        if dom not in DOMAIN_NAMES:
            continue
        sub = short_subdomain(sub_raw)
        sub_domain[sub] = dom
        dom_sub[(dom, sub)] += 1

        named_field = (row.get("named_systemic_risks") or "").strip()
        if named_field:
            for tag in named_field.split(";"):
                tag = tag.strip()
                sub_named[(sub, NAMED_LABELS.get(tag, tag))] += 1
        else:
            sub_named[(sub, UNMAPPED)] += 1

    # Node registry (ordered: domains, then subdomains, then named risks).
    labels: list[str] = []
    colors: list[str] = []
    index: dict[str, int] = {}

    def add(node_id: str, label: str, color: str) -> int:
        if node_id not in index:
            index[node_id] = len(labels)
            labels.append(label)
            colors.append(color)
        return index[node_id]

    for dom in sorted({d for d, _ in dom_sub}):
        add(f"D:{dom}", DOMAIN_NAMES[dom], DOMAIN_COLOR[dom])
    for sub in sorted({s for _, s in dom_sub}, key=lambda s: (sub_domain[s], s)):
        add(f"S:{sub}", sub, DOMAIN_COLOR[sub_domain[sub]])
    named_order = ["Loss of control", "CBRN", "Cyber offence",
                   "Harmful manipulation", UNMAPPED]
    present_named = {n for _, n in sub_named}
    for name in named_order:
        if name in present_named:
            add(f"N:{name}", name,
                UNMAPPED_COLOR if name == UNMAPPED else NAMED_COLOR)

    src, tgt, val, link_color = [], [], [], []
    for (dom, sub), count in dom_sub.items():
        src.append(index[f"D:{dom}"])
        tgt.append(index[f"S:{sub}"])
        val.append(count)
        link_color.append(hex_to_rgba(DOMAIN_COLOR[dom], 0.35))
    for (sub, name), count in sub_named.items():
        src.append(index[f"S:{sub}"])
        tgt.append(index[f"N:{name}"])
        val.append(count)
        base = UNMAPPED_COLOR if name == UNMAPPED else DOMAIN_COLOR[sub_domain[sub]]
        link_color.append(hex_to_rgba(base, 0.30))

    total = sum(dom_sub.values())
    fig = go.Figure(
        go.Sankey(
            arrangement="snap",
            node=dict(
                label=labels,
                color=colors,
                pad=16,
                thickness=16,
                line=dict(color="rgba(0,0,0,0.15)", width=0.5),
            ),
            link=dict(source=src, target=tgt, value=val, color=link_color),
        )
    )
    fig.update_layout(
        title=dict(
            text=(
                "Benchmark coverage of EU-relevant AI risks<br>"
                f"<span style='font-size:13px;color:#667085'>"
                f"{total:,} benchmark–risk edges · risk domain → "
                f"subdomain → named systemic risk (CoP App. 1.4)</span>"
            ),
            x=0.01,
            font=dict(size=20),
        ),
        font=dict(family="Inter, Segoe UI, Helvetica, Arial", size=12,
                  color="#1d2433"),
        paper_bgcolor="white",
        margin=dict(l=10, r=10, t=70, b=20),
        height=760,
        width=1200,
    )

    OUTDIR.mkdir(parents=True, exist_ok=True)
    html_path = OUTDIR / "benchmark_coverage_sankey.html"
    fig.write_html(html_path, include_plotlyjs="inline", full_html=True)
    print(f"wrote {html_path}")

    try:
        png_path = OUTDIR / "benchmark_coverage_sankey.png"
        fig.write_image(png_path, scale=2)
        print(f"wrote {png_path}")
    except Exception as exc:  # noqa: BLE001 - kaleido optional
        print(f"(png skipped: {type(exc).__name__}: install kaleido for static export)")

    # Emit the underlying flow table for the slide / provenance.
    table_path = OUTDIR / "benchmark_coverage_sankey_flows.csv"
    with table_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["stage", "source", "target", "benchmark_edges"])
        for (dom, sub), count in sorted(dom_sub.items(), key=lambda x: -x[1]):
            w.writerow(["domain->subdomain", DOMAIN_NAMES[dom], sub, count])
        for (sub, name), count in sorted(sub_named.items(), key=lambda x: -x[1]):
            w.writerow(["subdomain->named", sub, name, count])
    print(f"wrote {table_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
