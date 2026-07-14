#!/usr/bin/env python3
"""Figure 1 (equivalent): the ESAI certificate pipeline, mirroring COMPL-AI Fig 1.

COMPL-AI Figure 1 is the end-to-end pipeline: EU AI Act regulatory requirements
-> (technical interpretation) -> technical requirements -> (map to benchmarks)
-> benchmarking suite -> model report / certificate. This is our version of
that, drawn as Zhijing framed it (line 303: regulation -> risk -> benchmark ->
model performance), with my benchmark-collection stage highlighted as column 3.

Companion: build_sankey.py renders Figure 2 (the suite-structure / coverage view).

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

INK = "#1b2230"
MUTED = "#5b6675"
FAINT = "#8a94a6"
ACCENT = "#3b6fd4"
ACCENT_FILL = "#eaf0fb"

# One quiet tint per stage; the benchmark stage carries the accent.
STAGES = [
    dict(
        header="Regulatory requirements",
        title="EU AI Act",
        lines=[
            'Art. 15(1) "accuracy,',
            '  robustness, cybersecurity"',
            "Art. 55(1)  model eval",
            "CoP App. 1.4  ·  4 named",
            "  systemic risks",
        ],
        fill="#f3efeb", edge="#9d755d", report=False, highlight=False,
    ),
    dict(
        header="AI harms / risks",
        title="MIT risk taxonomy",
        lines=[
            "280 harms · 17 subdomains",
            "5 domains: 1·3·5·6·7",
            "the research topics",
            "  (technical requirements)",
        ],
        fill="#eef6ec", edge="#54a24b", report=False, highlight=False,
    ),
    dict(
        header="Benchmark collection",
        title="My benchmarking suite",
        lines=[
            "417 collected · 310 mapped",
            "ACL · OpenReview · PMLR",
            "1,387 mapping edges",
            "citation-ranked priority",
        ],
        fill=ACCENT_FILL, edge=ACCENT, report=False, highlight=True,
    ),
    dict(
        header="Model report",
        title="Certificate",
        lines=[
            "per-risk scores",
            "N / M benchmarks run",
            "coverage & gaps",
            "downstream (Tae)",
        ],
        fill="#f6f7f9", edge="#c3cad6", report=True, highlight=False,
    ),
]

CONNECTORS = ["technical\ninterpretation", "map to\nbenchmarks", "evaluate\n→ report"]


def main() -> int:
    for name in ("Segoe UI", "Helvetica Neue", "Arial", "DejaVu Sans"):
        if any(f.name == name for f in fm.fontManager.ttflist):
            plt.rcParams["font.family"] = name
            break

    fig, ax = plt.subplots(figsize=(15.2, 6.6))
    ax.set_xlim(0, 20)
    ax.set_ylim(0, 9)
    ax.axis("off")
    fig.patch.set_facecolor("white")

    ax.text(0.35, 8.5, "The ESAI certificate pipeline",
            ha="left", va="center", fontsize=23, color=INK, fontweight="bold")
    ax.text(0.35, 7.95,
            "Our version of COMPL-AI Figure 1 — regulation → risk → benchmark "
            "→ report. My column: systematic benchmark collection.",
            ha="left", va="center", fontsize=12.5, color=MUTED)

    centers = [2.6, 7.5, 12.4, 17.3]
    w, h, y = 3.3, 3.6, 2.7

    for cx, st in zip(centers, STAGES):
        x = cx - w / 2
        ax.text(cx, y + h + 0.30, st["header"], ha="center", va="bottom",
                fontsize=11.5, color=MUTED, fontweight="bold",
                fontvariant="small-caps")
        if st["highlight"]:
            ax.add_patch(FancyBboxPatch(
                (x - 0.09, y - 0.09), w + 0.18, h + 0.18,
                boxstyle="round,pad=0.02,rounding_size=0.10",
                linewidth=2.4, edgecolor=ACCENT, facecolor="none", zorder=2))
        ax.add_patch(FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.10",
            linewidth=1.5, edgecolor=st["edge"], facecolor=st["fill"],
            linestyle="--" if st["report"] else "-", zorder=3))
        ax.text(cx, y + h - 0.48, st["title"], ha="center", va="center",
                fontsize=15.5, color=INK if not st["report"] else MUTED,
                fontweight="bold")
        for i, ln in enumerate(st["lines"]):
            ax.text(x + 0.26, y + h - 1.10 - i * 0.46, ln, ha="left",
                    va="center", fontsize=10.5,
                    color=INK if not st["report"] else FAINT)
        if st["highlight"]:
            ax.text(cx, y - 0.42, "my contribution  ·  column 3",
                    ha="center", va="center", fontsize=10, color="white",
                    fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.35", fc=ACCENT, ec="none"))

    for i, label in enumerate(CONNECTORS):
        x0 = centers[i] + w / 2
        x1 = centers[i + 1] - w / 2
        col = ACCENT if i < 2 else "#c3cad6"
        ax.add_patch(FancyArrowPatch(
            (x0, y + h / 2), (x1, y + h / 2), arrowstyle="-|>",
            mutation_scale=20, linewidth=2.2, color=col, zorder=1,
            linestyle="--" if i == 2 else "-", shrinkA=3, shrinkB=3))
        ax.text((x0 + x1) / 2, y + h / 2 + 0.34, label, ha="center",
                va="bottom", fontsize=8.5,
                color=ACCENT if i < 2 else MUTED, fontweight="bold",
                fontstyle="italic")

    ax.text(0.35, 1.35,
            "Harm is the join hub: labeling cost is O(#harms), not "
            "O(#benchmarks × #laws). Weekly delta = benchmarks added → "
            "newly-covered risks.",
            ha="left", va="center", fontsize=10.5, color=MUTED)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=200, bbox_inches="tight", facecolor="white")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
