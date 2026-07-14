#!/usr/bin/env python3
"""Figure 1 (ESAI): our benchmark→harm→law map in the COMPL-AI Figure 1 layout.

Same structure as COMPL-AI Fig 1 (build_complai_fig1_replica.py) but populated
with real ESAI content: EU AI Act provisions we map to -> named systemic risks
(MIT taxonomy) -> our collected benchmarks -> a coverage report. Counts and
benchmark names are pulled live from the collection so re-running reflects
current progress; the report exposes the real coverage skew (heavy on loss of
control, thin on harmful manipulation, gaps on cyber offence / CBRN).

Companion: build_sankey.py = Figure 2. build_complai_fig1_replica.py = template.

Output: outputs/framework/framework_figure.png
"""
from __future__ import annotations

import collections
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.font_manager as fm  # noqa: E402
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, RegularPolygon  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

EDGES = Path("outputs/eu_risk_analysis/benchmark_eu_risk_edges.csv")
PRIOR = Path("outputs/eu_risk_analysis/prioritized_eu_benchmarks.csv")
OUT = Path("outputs/framework/framework_figure.png")

BLUE = "#2f5fb0"
BLUE_DK = "#1f4e9c"
BAND = "#eef3fb"
CARD_EDGE = "#cdd7ea"
ORANGE = "#df7b12"
GOLD = "#e0a516"
GREEN = "#2f9e52"
AMBER = "#c9891a"
RED = "#d0342c"
INK = "#232a36"
MUTED = "#66707f"
FAINT = "#9aa4b4"
GLYPH = "DejaVu Sans"


def load_counts():
    edges = list(csv.DictReader(EDGES.open(encoding="utf-8-sig")))
    per = collections.defaultdict(set)
    for r in edges:
        for risk in (r.get("named_systemic_risks") or "").split(";"):
            risk = risk.strip()
            if risk:
                per[risk].add(r["benchmark_id"])
    # Prefer a recognizable short name: the acronym before the ":" in the
    # title (e.g. "PromptBench: Towards ..." -> "PromptBench"), else quick_ref.
    def short_name(title: str, quick_ref: str) -> tuple[int, str]:
        head = (title or "").split(":")[0].strip()
        if 1 < len(head) <= 22 and " " not in head.strip(" -"):
            return 0, head  # single-token acronym: rank first
        if 1 < len(head) <= 22:
            return 1, head
        return 2, quick_ref

    named = collections.defaultdict(list)
    for r in csv.DictReader(PRIOR.open(encoding="utf-8-sig")):
        for risk in (r.get("named_systemic_risks") or "").split(";"):
            risk = risk.strip()
            if risk:
                named[risk].append(short_name(r.get("title", ""),
                                              r.get("quick_ref", "")))
    names = {}
    for k, v in named.items():
        seen, ordered = set(), []
        for _, nm in sorted(v, key=lambda t: t[0]):
            if nm and nm not in seen:
                seen.add(nm)
                ordered.append(nm)
        names[k] = ordered
    return {k: len(v) for k, v in per.items()}, names, len(edges)


def rbox(ax, x, y, w, h, *, fill, edge, lw=1.4, ls="-", z=2, r=0.06):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle=f"round,pad=0.01,rounding_size={r}",
        facecolor=fill, edgecolor=edge, linewidth=lw, linestyle=ls, zorder=z,
        mutation_aspect=1.0))


def check(ax, x, y, text, *, ok=True, color=None):
    ax.text(x, y, "✓" if ok else "✗", ha="left", va="center", family=GLYPH,
            fontsize=10.5, color=(color or (GREEN if ok else RED)),
            fontweight="bold")
    ax.text(x + 0.28, y, text, ha="left", va="center", fontsize=9.3, color=INK)


def hexmarker(ax, x, y, lines):
    ax.add_patch(RegularPolygon((x, y), numVertices=6, radius=0.22,
                 orientation=0, facecolor="#fdf6e3", edgecolor=GOLD,
                 linewidth=1.8, zorder=3))
    for i, ln in enumerate(lines):
        ax.text(x + 0.4, y + 0.16 - i * 0.32, ln, ha="left", va="center",
                fontsize=10.5, color=INK, fontweight="bold")


def ai_act_icon(ax, cx, cy):
    for dx, dy in ((0.16, -0.16), (0.0, 0.0)):
        rbox(ax, cx - 0.5 + dx, cy - 0.62 + dy, 1.0, 1.24,
             fill="white", edge=BLUE, lw=1.6, z=5, r=0.05)
    for i in range(3):
        ax.plot([cx - 0.28, cx + 0.32], [cy + 0.28 - i * 0.26] * 2,
                color="#c3cee2", lw=1.4, zorder=6)
    ax.text(cx, cy - 0.42, "AI Act", ha="center", va="center", fontsize=9.5,
            color=BLUE_DK, fontweight="bold", zorder=6)


def report_row(ax, x, y, score, title, sub, item, *, tone=BLUE):
    ax.add_patch(Circle((x + 0.36, y), 0.34, facecolor="white",
                 edgecolor=tone, linewidth=2.0, zorder=4))
    fs = 9.5 if len(score) <= 3 else 8.5
    ax.text(x + 0.36, y, score, ha="center", va="center", fontsize=fs,
            color=tone, fontweight="bold", zorder=5)
    ax.text(x + 0.9, y + 0.12, title, ha="left", va="center", fontsize=10,
            color=INK, fontweight="bold")
    if sub:
        ax.text(x + 0.9, y - 0.20, sub, ha="left", va="center", fontsize=8.5,
                color=MUTED)
    if item:
        txt, ok = item
        check(ax, x + 0.95, y - 0.56, txt, ok=ok,
              color=(GREEN if ok else RED))


def main() -> int:
    for name in ("Segoe UI", "Helvetica Neue", "Arial", "DejaVu Sans"):
        if any(f.name == name for f in fm.fontManager.ttflist):
            plt.rcParams["font.family"] = name
            break

    counts, names, n_edges = load_counts()
    n_loc = counts.get("loss-of-control", 0)
    n_hm = counts.get("harmful-manipulation", 0)
    n_cyber = counts.get("cyber-offence", 0)
    loc_names = (names.get("loss-of-control") or ["PromptBench"])[:4]
    hm_names = (names.get("harmful-manipulation") or ["SocialHarmBench"])[:3]

    fig, ax = plt.subplots(figsize=(15.8, 8.7))
    ax.set_xlim(0, 19)
    ax.set_ylim(0, 11.0)
    ax.axis("off")
    fig.patch.set_facecolor("white")

    ax.text(0.3, 10.6, "The ESAI benchmark → harm → law map",
            ha="left", va="center", fontsize=17, color=INK, fontweight="bold")
    ax.text(0.3, 10.15, "our EU AI Act mapping in the COMPL-AI Figure 1 layout "
            "· my column: benchmark collection",
            ha="left", va="center", fontsize=11, color=MUTED)

    ai_act_icon(ax, 1.05, 8.0)
    ax.add_patch(FancyArrowPatch((1.75, 8.0), (2.45, 8.0), arrowstyle="-|>",
                 mutation_scale=16, linewidth=1.8, color=BLUE, zorder=4))

    rbox(ax, 2.4, 0.5, 10.6, 9.2, fill="white", edge=BLUE, lw=2.2, z=1, r=0.05)

    # ---- Band 1: Regulatory Requirements ----
    rbox(ax, 2.6, 7.3, 10.2, 2.2, fill=BAND, edge="none", z=1, r=0.04)
    ax.text(2.9, 8.7, "[EU AI Act]", ha="left", va="center", fontsize=10,
            color=BLUE, fontweight="bold")
    ax.text(2.9, 8.3, "Regulatory", ha="left", va="center", fontsize=11.5,
            color=INK, fontweight="bold")
    ax.text(2.9, 7.97, "Requirements", ha="left", va="center", fontsize=11.5,
            color=INK, fontweight="bold")

    rbox(ax, 5.15, 7.5, 2.9, 1.8, fill="white", edge=CARD_EDGE, lw=1.3, z=3)
    ax.text(5.35, 9.02, "Art. 55(1)", ha="left", va="center", fontsize=9.5,
            color=BLUE_DK, fontweight="bold")
    ax.text(5.35, 8.66, '"perform model', ha="left", va="center", fontsize=8.6,
            color=INK)
    ax.text(5.35, 8.38, "evaluation ...", ha="left", va="center", fontsize=8.6,
            color=INK)
    ax.text(5.35, 8.10, "documenting", ha="left", va="center", fontsize=8.6,
            color=INK)
    ax.text(5.35, 7.82, 'adversarial testing"', ha="left", va="center",
            fontsize=8.6, color=ORANGE, fontweight="bold")

    rbox(ax, 8.25, 7.5, 2.9, 1.8, fill="white", edge=CARD_EDGE, lw=1.3, z=3)
    ax.text(8.45, 9.02, "CoP App. 1.4", ha="left", va="center", fontsize=9.5,
            color=BLUE_DK, fontweight="bold")
    ax.text(8.45, 8.66, '"specified systemic', ha="left", va="center",
            fontsize=8.6, color=INK)
    ax.text(8.45, 8.38, "risks include:", ha="left", va="center", fontsize=8.6,
            color=INK)
    ax.text(8.45, 8.10, "loss of control,", ha="left", va="center",
            fontsize=8.6, color=ORANGE, fontweight="bold")
    ax.text(8.45, 7.82, 'harmful manipulation"', ha="left", va="center",
            fontsize=8.6, color=ORANGE, fontweight="bold")
    ax.text(11.6, 8.35, "…", ha="center", va="center", fontsize=16, color=MUTED)

    ax.add_patch(FancyArrowPatch((6.2, 7.25), (6.2, 6.25), arrowstyle="-|>",
                 mutation_scale=18, linewidth=2.0, color=BLUE, zorder=4))
    ax.text(6.45, 6.75, "Technical Interpretation", ha="left", va="center",
            fontsize=9.5, color=BLUE, fontstyle="italic", fontweight="bold")

    # ---- Band 2: Technical Requirements (named systemic risks) ----
    ax.text(2.9, 5.7, "Technical", ha="left", va="center", fontsize=11.5,
            color=INK, fontweight="bold")
    ax.text(2.9, 5.37, "Requirements", ha="left", va="center", fontsize=11.5,
            color=INK, fontweight="bold")
    hexmarker(ax, 5.35, 5.55, ["Loss of control"])
    ax.text(5.75, 5.25, "(7.1 · 7.3 · 7.6)", ha="left", va="center",
            fontsize=8.5, color=MUTED)
    hexmarker(ax, 8.45, 5.55, ["Harmful", "manipulation"])
    ax.text(11.6, 5.4, "…", ha="center", va="center", fontsize=16, color=MUTED)

    ax.add_patch(FancyArrowPatch((6.2, 4.75), (6.2, 3.75), arrowstyle="-|>",
                 mutation_scale=18, linewidth=2.0, color=BLUE, zorder=4))
    ax.text(6.45, 4.25, "Map Requirements to Benchmarks", ha="left",
            va="center", fontsize=9.5, color=BLUE, fontstyle="italic",
            fontweight="bold")

    # ---- Band 3: Benchmarking Suite (our collection) ----
    rbox(ax, 2.6, 0.75, 10.2, 2.85, fill=BAND, edge="none", z=1, r=0.04)
    ax.text(2.9, 2.4, "Benchmarking", ha="left", va="center", fontsize=11.5,
            color=INK, fontweight="bold")
    ax.text(2.9, 2.07, "Suite (ours)", ha="left", va="center", fontsize=11.5,
            color=INK, fontweight="bold")

    rbox(ax, 5.05, 1.3, 3.05, 2.15, fill="white", edge="#b9c4d8", lw=1.2,
         ls=(0, (4, 3)), z=3)
    ax.text(5.2, 3.28, f"Loss of control · {n_loc}", ha="left", va="center",
            fontsize=8.3, color=BLUE_DK, fontweight="bold")
    for i, nm in enumerate(loc_names):
        check(ax, 5.25, 2.92 - i * 0.4, nm)

    rbox(ax, 8.3, 2.05, 3.05, 1.4, fill="white", edge="#b9c4d8", lw=1.2,
         ls=(0, (4, 3)), z=3)
    ax.text(8.45, 3.28, f"Harmful manip. · {n_hm}", ha="left", va="center",
            fontsize=8.3, color=BLUE_DK, fontweight="bold")
    for i, nm in enumerate(hm_names[:2]):
        check(ax, 8.5, 2.92 - i * 0.4, nm)

    ax.text(11.6, 2.7, "…", ha="center", va="center", fontsize=16, color=MUTED)
    ax.text(8.35, 1.15, "↻", ha="left", va="center", family=GLYPH, fontsize=11,
            color=BLUE, fontweight="bold")
    ax.text(8.7, 1.15, "Collect, Add, and Update  ·  417 collected",
            ha="left", va="center", fontsize=9, color=BLUE,
            fontstyle="italic", fontweight="bold")

    # ---- Right: Coverage report (sample) ----
    ax.add_patch(FancyArrowPatch((13.0, 5.1), (13.7, 5.1), arrowstyle="-|>",
                 mutation_scale=18, linewidth=2.0, color=BLUE, zorder=4))
    rbox(ax, 13.8, 1.2, 4.5, 7.4, fill="white", edge=BLUE, lw=1.8, z=3, r=0.04)
    report_row(ax, 14.05, 7.85, "310", "Coverage report", None, None)
    ax.text(15.05, 7.5, "417 collected · 1,387 edges", ha="left", va="center",
            fontsize=8.5, color=MUTED)
    ax.text(14.42, 6.9, "⋮", ha="center", va="center", family=GLYPH,
            fontsize=13, color=FAINT)
    report_row(ax, 14.05, 6.2, str(n_loc), "Loss of control",
               "well covered", (loc_names[0], True), tone=GREEN)
    ax.text(14.42, 5.25, "⋮", ha="center", va="center", family=GLYPH,
            fontsize=13, color=FAINT)
    report_row(ax, 14.05, 4.55, str(n_hm), "Harmful manipulation",
               "thin coverage", (hm_names[0], True), tone=AMBER)
    ax.text(14.42, 3.6, "⋮", ha="center", va="center", family=GLYPH,
            fontsize=13, color=FAINT)
    report_row(ax, 14.05, 2.9, str(n_cyber), "Cyber offence / CBRN",
               "gap — none yet", ("no benchmarks", False), tone=RED)

    ax.text(13.85, 0.75, "illustrative · model scores are downstream (Tae)",
            ha="left", va="center", fontsize=8, color=FAINT, fontstyle="italic")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=200, bbox_inches="tight", facecolor="white")
    print(f"wrote {OUT}  (loss-of-control={n_loc}, harmful-manip={n_hm}, "
          f"cyber/cbrn={n_cyber})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
