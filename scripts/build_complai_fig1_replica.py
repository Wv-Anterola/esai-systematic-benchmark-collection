#!/usr/bin/env python3
"""Faithful replica of COMPL-AI Figure 1 (Guldimann et al.).

Reproduces the reference figure Zhijing points to: the AI Act feeds three
stacked bands -- Regulatory Requirements (article cards) -> (Technical
Interpretation) -> Technical Requirements (hexagon markers) -> (Map
Requirements to Benchmarks) -> Benchmarking Suite (checked benchmarks) -- and
the suite produces a "My Model Report" card on the right. Original content kept
so it matches the paper; swap text to make the ESAI version.

Output: outputs/framework/complai_fig1_replica.png
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.font_manager as fm  # noqa: E402
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, RegularPolygon  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

OUT = Path("outputs/framework/complai_fig1_replica.png")

BLUE = "#2f5fb0"
BLUE_DK = "#1f4e9c"
BAND = "#eef3fb"
CARD_EDGE = "#cdd7ea"
ORANGE = "#df7b12"
GOLD = "#e0a516"
GREEN = "#2f9e52"
RED = "#d0342c"
INK = "#232a36"
MUTED = "#66707f"
FAINT = "#9aa4b4"


def rbox(ax, x, y, w, h, *, fill, edge, lw=1.4, ls="-", z=2, r=0.06):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle=f"round,pad=0.01,rounding_size={r}",
        facecolor=fill, edgecolor=edge, linewidth=lw, linestyle=ls, zorder=z,
        mutation_aspect=1.0))


def down_arrow(ax, x, y0, y1, label):
    ax.add_patch(FancyArrowPatch((x, y0), (x, y1), arrowstyle="-|>",
                 mutation_scale=18, linewidth=2.0, color=BLUE, zorder=4))
    ax.text(x + 0.22, (y0 + y1) / 2, label, ha="left", va="center",
            fontsize=9.5, color=BLUE, fontstyle="italic", fontweight="bold")


GLYPH = "DejaVu Sans"  # has the check / cross / ellipsis / cycle glyphs


def check(ax, x, y, text, *, ok=True):
    ax.text(x, y, "✓" if ok else "✗", ha="left", va="center", family=GLYPH,
            fontsize=10.5, color=GREEN if ok else RED, fontweight="bold")
    ax.text(x + 0.28, y, text, ha="left", va="center", fontsize=9.3, color=INK)


def hexmarker(ax, x, y, text):
    ax.add_patch(RegularPolygon((x, y), numVertices=6, radius=0.22,
                 orientation=0, facecolor="#fdf6e3", edgecolor=GOLD,
                 linewidth=1.8, zorder=3))
    ax.text(x + 0.4, y, text, ha="left", va="center", fontsize=10.5,
            color=INK, fontweight="bold")


def ai_act_icon(ax, cx, cy):
    for dx, dy in ((0.16, -0.16), (0.0, 0.0)):
        rbox(ax, cx - 0.5 + dx, cy - 0.62 + dy, 1.0, 1.24,
             fill="white", edge=BLUE, lw=1.6, z=5, r=0.05)
    for i in range(3):
        ax.plot([cx - 0.28, cx + 0.32], [cy + 0.28 - i * 0.26] * 2,
                color="#c3cee2", lw=1.4, zorder=6)
    ax.text(cx, cy - 0.42, "AI Act", ha="center", va="center", fontsize=9.5,
            color=BLUE_DK, fontweight="bold", zorder=6)


def report_row(ax, x, y, score, title, frac, items, *, na=False):
    col = RED if na else BLUE
    ax.add_patch(Circle((x + 0.35, y), 0.30, facecolor="white",
                 edgecolor=col, linewidth=2.0, zorder=4))
    ax.text(x + 0.35, y, score, ha="center", va="center", fontsize=9.5,
            color=col, fontweight="bold", zorder=5)
    ax.text(x + 0.85, y + 0.10, title, ha="left", va="center", fontsize=10,
            color=INK, fontweight="bold")
    if frac:
        ax.text(x + 0.85, y - 0.22, frac, ha="left", va="center",
                fontsize=8.5, color=MUTED)
    for i, (txt, ok) in enumerate(items):
        check(ax, x + 0.9, y - 0.55 - i * 0.34, txt, ok=ok)


def main() -> int:
    for name in ("Segoe UI", "Helvetica Neue", "Arial", "DejaVu Sans"):
        if any(f.name == name for f in fm.fontManager.ttflist):
            plt.rcParams["font.family"] = name
            break

    fig, ax = plt.subplots(figsize=(15.6, 8.4))
    ax.set_xlim(0, 19)
    ax.set_ylim(0, 10.6)
    ax.axis("off")
    fig.patch.set_facecolor("white")

    ai_act_icon(ax, 1.05, 8.3)
    ax.add_patch(FancyArrowPatch((1.75, 8.3), (2.45, 8.3), arrowstyle="-|>",
                 mutation_scale=16, linewidth=1.8, color=BLUE, zorder=4))

    # Outer container.
    rbox(ax, 2.4, 0.6, 10.6, 9.4, fill="white", edge=BLUE, lw=2.2, z=1, r=0.05)

    # ---- Band 1: Regulatory Requirements ----
    rbox(ax, 2.6, 7.55, 10.2, 2.25, fill=BAND, edge="none", z=1, r=0.04)
    ax.text(2.9, 8.95, "[EU AI Act]", ha="left", va="center", fontsize=10,
            color=BLUE, fontweight="bold")
    ax.text(2.9, 8.55, "Regulatory", ha="left", va="center", fontsize=11.5,
            color=INK, fontweight="bold")
    ax.text(2.9, 8.22, "Requirements", ha="left", va="center", fontsize=11.5,
            color=INK, fontweight="bold")

    rbox(ax, 5.15, 7.75, 2.9, 1.85, fill="white", edge=CARD_EDGE, lw=1.3, z=3)
    ax.text(5.35, 9.30, "Article 15 (1)", ha="left", va="center", fontsize=9.5,
            color=BLUE_DK, fontweight="bold")
    ax.text(5.35, 8.92, '"achieve an appropriate', ha="left", va="center",
            fontsize=8.6, color=INK)
    ax.text(5.35, 8.62, "level of accuracy,", ha="left", va="center",
            fontsize=8.6, color=INK)
    ax.text(5.35, 8.32, "robustness, and", ha="left", va="center",
            fontsize=8.6, color=ORANGE, fontweight="bold")
    ax.text(5.35, 8.02, 'cybersecurity"', ha="left", va="center",
            fontsize=8.6, color=ORANGE, fontweight="bold")

    rbox(ax, 8.25, 7.75, 2.9, 1.85, fill="white", edge=CARD_EDGE, lw=1.3, z=3)
    ax.text(8.45, 9.30, "Article 53 (1c)", ha="left", va="center", fontsize=9.5,
            color=BLUE_DK, fontweight="bold")
    ax.text(8.45, 8.92, '"put in place a policy', ha="left", va="center",
            fontsize=8.6, color=INK)
    ax.text(8.45, 8.62, "to comply with Union", ha="left", va="center",
            fontsize=8.6, color=INK)
    ax.text(8.45, 8.32, 'copyright law"', ha="left", va="center",
            fontsize=8.6, color=ORANGE, fontweight="bold")
    ax.text(11.6, 8.6, "…", ha="center", va="center", fontsize=16,
            color=MUTED)

    ax.add_patch(FancyArrowPatch((6.2, 7.5), (6.2, 6.5), arrowstyle="-|>",
                 mutation_scale=18, linewidth=2.0, color=BLUE, zorder=4))
    ax.text(6.45, 7.0, "Technical Interpretation", ha="left", va="center",
            fontsize=9.5, color=BLUE, fontstyle="italic", fontweight="bold")

    # ---- Band 2: Technical Requirements ----
    ax.text(2.9, 5.95, "Technical", ha="left", va="center", fontsize=11.5,
            color=INK, fontweight="bold")
    ax.text(2.9, 5.62, "Requirements", ha="left", va="center", fontsize=11.5,
            color=INK, fontweight="bold")
    hexmarker(ax, 5.35, 5.8, "Robustness and")
    ax.text(5.75, 5.5, "Predictability", ha="left", va="center", fontsize=10.5,
            color=INK, fontweight="bold")
    hexmarker(ax, 8.45, 5.8, "No Copyright")
    ax.text(8.85, 5.5, "Infringement", ha="left", va="center", fontsize=10.5,
            color=INK, fontweight="bold")
    ax.text(11.6, 5.65, "…", ha="center", va="center", fontsize=16,
            color=MUTED)

    ax.add_patch(FancyArrowPatch((6.2, 5.0), (6.2, 4.0), arrowstyle="-|>",
                 mutation_scale=18, linewidth=2.0, color=BLUE, zorder=4))
    ax.text(6.45, 4.5, "Map Requirements to Benchmarks", ha="left",
            va="center", fontsize=9.5, color=BLUE, fontstyle="italic",
            fontweight="bold")

    # ---- Band 3: Benchmarking Suite ----
    rbox(ax, 2.6, 0.85, 10.2, 2.9, fill=BAND, edge="none", z=1, r=0.04)
    ax.text(2.9, 2.55, "Benchmarking", ha="left", va="center", fontsize=11.5,
            color=INK, fontweight="bold")
    ax.text(2.9, 2.22, "Suite (LLMs)", ha="left", va="center", fontsize=11.5,
            color=INK, fontweight="bold")

    rbox(ax, 5.05, 1.4, 3.05, 2.15, fill="white", edge="#b9c4d8", lw=1.2,
         ls=(0, (4, 3)), z=3)
    for i, t in enumerate(["Monotonicity BoolQ Contrast",
                           "Self-Check Consistency", "Robust MMLU",
                           "IMDB Contrast"]):
        check(ax, 5.25, 3.2 - i * 0.42, t)

    rbox(ax, 8.3, 2.45, 3.05, 1.05, fill="white", edge="#b9c4d8", lw=1.2,
         ls=(0, (4, 3)), z=3)
    check(ax, 8.5, 2.95, "Copyrighted Material")
    ax.text(8.78, 2.6, "Memorization", ha="left", va="center", fontsize=9.3,
            color=INK)
    ax.text(11.6, 2.9, "…", ha="center", va="center", fontsize=16,
            color=MUTED)
    ax.text(8.5, 1.25, "↻", ha="left", va="center", family=GLYPH,
            fontsize=11, color=BLUE, fontweight="bold")
    ax.text(8.85, 1.25, "Collect, Add, and Update Benchmarks",
            ha="left", va="center", fontsize=9.5, color=BLUE,
            fontstyle="italic", fontweight="bold")

    # ---- Right: My Model Report ----
    ax.add_patch(FancyArrowPatch((13.0, 5.3), (13.7, 5.3), arrowstyle="-|>",
                 mutation_scale=18, linewidth=2.0, color=BLUE, zorder=4))
    rbox(ax, 13.8, 1.5, 4.4, 7.2, fill="white", edge=BLUE, lw=1.8, z=3, r=0.04)
    report_row(ax, 14.1, 7.9, "0.81", "My Model Report", "",
               [], na=False)
    ax.text(14.95, 7.55, "20/27 Benchmarks Completed", ha="left", va="center",
            fontsize=8.5, color=MUTED)
    ax.text(14.45, 6.95, "⋮", ha="center", va="center", family=GLYPH,
            fontsize=13, color=FAINT)
    report_row(ax, 14.1, 6.25, "0.75", "Robustness and", "Predictability  2/3",
               [("Monotonicity, BoolQ Contrast", True)])
    ax.text(14.45, 5.15, "⋮", ha="center", va="center", family=GLYPH,
            fontsize=13, color=FAINT)
    report_row(ax, 14.1, 4.4, "N/A", "No Copyright", "Infringement",
               [("Copyrighted Material Memorization", False)], na=True)
    ax.text(14.45, 3.25, "⋮", ha="center", va="center", family=GLYPH,
            fontsize=13, color=FAINT)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=200, bbox_inches="tight", facecolor="white")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
