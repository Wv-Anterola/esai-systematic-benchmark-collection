#!/usr/bin/env python3
"""Figure 1 (equivalent): the ESAI benchmark -> harm -> law framework schematic.

Zhijing's take-home asks each member for their own version of the paper's
Figure 1 and Figure 2. Figure 2 is the coverage Sankey (build_sankey.py); this
is Figure 1: the conceptual pipeline, drawn the way the team reads it
(Legal provision -> AI harm -> Benchmark, benchmark = "column 3"), with the
benchmark-collection column highlighted as my contribution and real node counts.

Harm is the join hub (per the ontology): legal provisions *address* harms and
benchmarks *measure* harms, so both edges point inward.

Output: outputs/framework/framework_figure.png
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.font_manager as fm  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

OUT = Path("outputs/framework/framework_figure.png")

# Palette shared with the Sankey so the two figures read as a set.
INK = "#1b2230"
MUTED = "#5b6675"
ACCENT = "#3b6fd4"
ACCENT_FILL = "#eaf0fb"
HARM_EDGE = "#54a24b"
HARM_FILL = "#eef6ec"
LEGAL_EDGE = "#9d755d"
LEGAL_FILL = "#f3efeb"
CARD_EDGE = "#dfe3ea"

for name in ("Segoe UI", "Helvetica Neue", "Arial", "DejaVu Sans"):
    if any(f.name == name for f in fm.fontManager.ttflist):
        plt.rcParams["font.family"] = name
        break


def card(ax, x, y, w, h, *, fill, edge, lw=1.4):
    ax.add_patch(
        FancyBboxPatch(
            (x, y), w, h,
            boxstyle="round,pad=0.02,rounding_size=0.10",
            linewidth=lw, edgecolor=edge, facecolor=fill, zorder=2,
            mutation_aspect=1.0,
        )
    )


def column(ax, cx, *, header, title, count, lines, fill, edge, highlight=False):
    w, h = 3.0, 3.4
    x, y = cx - w / 2, 3.0
    # eyebrow header above the card
    ax.text(cx, y + h + 0.28, header, ha="center", va="bottom",
            fontsize=11.5, color=MUTED, fontweight="bold",
            fontvariant="small-caps")
    if highlight:
        card(ax, x - 0.09, y - 0.09, w + 0.18, h + 0.18,
             fill="none", edge=ACCENT, lw=2.4)
    card(ax, x, y, w, h, fill=fill, edge=edge)
    ax.text(cx, y + h - 0.42, title, ha="center", va="center",
            fontsize=15, color=INK, fontweight="bold", wrap=True)
    ax.text(cx, y + h - 0.92, count, ha="center", va="center",
            fontsize=11.0, color=ACCENT if highlight else MUTED,
            fontweight="bold")
    for i, ln in enumerate(lines):
        ax.text(x + 0.28, y + h - 1.42 - i * 0.42, ln, ha="left", va="center",
                fontsize=10.5, color=INK)
    if highlight:
        ax.text(cx, y - 0.42, "my contribution  ·  column 3",
                ha="center", va="center", fontsize=10, color="white",
                fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.35", fc=ACCENT, ec="none"))


def inward_arrow(ax, x0, x1, y, label):
    ax.add_patch(
        FancyArrowPatch(
            (x0, y), (x1, y), arrowstyle="-|>", mutation_scale=20,
            linewidth=2.2, color=ACCENT, zorder=1,
            shrinkA=4, shrinkB=6,
        )
    )
    ax.text((x0 + x1) / 2, y + 0.22, label, ha="center", va="bottom",
            fontsize=10.5, color=ACCENT, fontweight="bold", fontstyle="italic")


def main() -> int:
    fig, ax = plt.subplots(figsize=(12.6, 7.4))
    ax.set_xlim(0, 15)
    ax.set_ylim(0, 9)
    ax.axis("off")
    fig.patch.set_facecolor("white")

    ax.text(0.35, 8.5, "The ESAI benchmark → harm → law map",
            ha="left", va="center", fontsize=22, color=INK, fontweight="bold")
    ax.text(0.35, 7.95,
            "My column of the pipeline: systematic benchmark collection, "
            "joined to EU-relevant AI harms and legal provisions",
            ha="left", va="center", fontsize=12.5, color=MUTED)

    cx_legal, cx_harm, cx_bench = 2.9, 7.5, 12.1

    column(
        ax, cx_legal,
        header="Legal provision", title="EU AI Act", count="Ch. V + CoP App. 1",
        lines=[
            "CoP App. 1.4  ·  4 named",
            "  systemic risks",
            "Art. 3(65), 55, 56(1)",
            "GPAI obligations",
        ],
        fill=LEGAL_FILL, edge=LEGAL_EDGE,
    )
    column(
        ax, cx_harm,
        header="AI harm  (the join hub)", title="MIT risk taxonomy",
        count="280 harms  ·  17 subdomains",
        lines=[
            "5 domains: 1 · 3 · 5 · 6 · 7",
            "discrimination, misinfo,",
            "  HCI, socioeconomic,",
            "  system safety",
        ],
        fill=HARM_FILL, edge=HARM_EDGE,
    )
    column(
        ax, cx_bench,
        header="Benchmark  (evidence)", title="Benchmark collection",
        count="417 collected  ·  310 mapped",
        lines=[
            "ACL · OpenReview · PMLR",
            "1,387 benchmark–harm",
            "  edges",
            "citation-ranked priority",
        ],
        fill=ACCENT_FILL, edge=ACCENT, highlight=True,
    )

    # Both edges point inward to the harm hub.
    inward_arrow(ax, cx_legal + 1.6, cx_harm - 1.6, 4.7, "addresses")
    inward_arrow(ax, cx_bench - 1.6, cx_harm + 1.6, 4.7, "measures")

    ax.text(0.35, 1.7,
            "Weekly delta: +N benchmarks in the benchmark column → M "
            "newly-covered harms in the middle column.",
            ha="left", va="center", fontsize=11, color=MUTED,
            fontstyle="italic")
    ax.text(0.35, 1.25,
            "Harm is the hub: labeling cost is O(#harms), not "
            "O(#benchmarks × #laws). The benchmark–law edge is the join.",
            ha="left", va="center", fontsize=11, color=MUTED)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=200, bbox_inches="tight", facecolor="white")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
