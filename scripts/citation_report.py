"""Build a citation histogram image + consolidated markdown report.

Joins the enrichment citation counts onto screened candidates, buckets the
distribution, renders a histogram PNG, and writes a markdown report with the
distribution table, suggested min-citation cutoffs, and a filter preview. All
numbers reuse ``esai_collection.citations`` so they match the CLI stages exactly.

Usage:
    python scripts/citation_report.py \
        --candidates outputs/full_run/candidates_relevant.csv \
        --enrichment outputs/full_run/metadata_enrichment.csv \
        --as-of-year 2026 \
        --outdir outputs/full_run/report
"""

from __future__ import annotations

import argparse
import statistics
from datetime import UTC, datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from esai_collection.citations import (  # noqa: E402
    CITATION_FIELDS,
    HISTOGRAM_FIELDS,
    _parse_int,
    citation_histogram,
    filter_by_citations,
    join_citations,
    suggest_cutoffs,
)
from esai_collection.io import read_csv, write_csv  # noqa: E402

# Single sequential hue for magnitude; a muted neutral for the "missing" bucket.
BAR_COLOR = "#3b6fd4"
MISSING_COLOR = "#9aa4b2"
INK = "#1b2430"
MUTED = "#5b6472"
GRID = "#e6e9ee"


def _stats(rows: list[dict[str, str]]) -> dict[str, object]:
    values = [_parse_int(row.get("citation_count")) for row in rows]
    known = [value for value in values if value is not None]
    total = len(values)
    resolved = len(known)
    return {
        "total": total,
        "with_citations": resolved,
        "without_citations": total - resolved,
        "coverage_pct": round(100.0 * resolved / total, 2) if total else 0.0,
        "min": min(known) if known else 0,
        "median": int(statistics.median(known)) if known else 0,
        "mean": round(statistics.mean(known), 2) if known else 0.0,
        "p90": int(_percentile(known, 90)) if known else 0,
        "max": max(known) if known else 0,
    }


def _percentile(values: list[int], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = (pct / 100.0) * (len(ordered) - 1)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


def _recommended_cutoff(cutoffs: list[dict[str, object]]) -> dict[str, object] | None:
    """Pick the highest threshold that still keeps at least 25% of papers.

    A pragmatic 'natural cutoff' aid: aggressive enough to shrink the queue, but
    not so aggressive it discards most of the corpus.
    """
    viable = [row for row in cutoffs if float(row["kept_pct"]) >= 25.0]
    return viable[-1] if viable else (cutoffs[0] if cutoffs else None)


def render_histogram(histogram: list[dict[str, object]], out_png: Path) -> None:
    labels = [str(row["citation_bucket"]) for row in histogram]
    papers = [int(row["papers"]) for row in histogram]
    shares = [float(row["share_pct"]) for row in histogram]
    colors = [MISSING_COLOR if lbl == "missing" else BAR_COLOR for lbl in labels]

    fig, ax = plt.subplots(figsize=(10, 5.2), dpi=150)
    ax.set_axisbelow(True)
    ax.yaxis.grid(True, color=GRID, linewidth=1)
    bars = ax.bar(labels, papers, color=colors, width=0.68, zorder=3)

    top = max(papers) if papers else 1
    for rect, count, share in zip(bars, papers, shares, strict=True):
        ax.text(
            rect.get_x() + rect.get_width() / 2,
            rect.get_height() + top * 0.012,
            f"{count:,}\n{share:g}%",
            ha="center",
            va="bottom",
            fontsize=8,
            color=MUTED,
            linespacing=1.15,
        )

    ax.set_title(
        "Citation distribution of relevant benchmark candidates "
        "(Crossref + Semantic Scholar)",
        fontsize=13,
        color=INK,
        pad=14,
        loc="left",
    )
    ax.set_xlabel("Citations", fontsize=10, color=MUTED)
    ax.set_ylabel("Papers", fontsize=10, color=MUTED)
    ax.set_ylim(0, top * 1.16)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9, length=0)
    fig.tight_layout()
    fig.savefig(out_png, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _md_table(headers: list[str], rows: list[list[object]]) -> str:
    line = "| " + " | ".join(headers) + " |"
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    body = "\n".join(
        "| " + " | ".join(str(cell) for cell in row) + " |" for row in rows
    )
    return "\n".join([line, sep, body])


def build_report(
    *,
    candidates: Path,
    enrichment: Path,
    as_of_year: int,
    outdir: Path,
) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    joined = join_citations(
        read_csv(candidates), read_csv(enrichment), as_of_year=as_of_year
    )
    histogram = citation_histogram(joined)
    cutoffs = suggest_cutoffs(joined)
    stats = _stats(joined)
    recommended = _recommended_cutoff(cutoffs)

    # Result artifacts.
    png = outdir / "citation_histogram.png"
    render_histogram(histogram, png)
    write_csv(outdir / "citation_histogram.csv", histogram, HISTOGRAM_FIELDS)
    write_csv(
        outdir / "citation_cutoffs.csv",
        cutoffs,
        ["min_citations", "kept", "kept_pct", "dropped"],
    )

    # Filter preview: Zhijing's rule (age+citation) and the operative global cutoff.
    zhijing_kept, zhijing_counts = filter_by_citations(
        joined, min_citations=10, max_age_years=5
    )
    write_csv(
        outdir / "benchmark_candidates_filtered_zhijing.csv",
        zhijing_kept,
        CITATION_FIELDS,
    )
    # Operative priority queue: cited papers only, ranked. max_age_years=-1 makes the
    # citation cutoff apply regardless of age (every paper counts as "old"), so this is
    # a pure global cutoff; drop_missing removes no-DOI papers with no resolved count.
    priority_kept, _ = filter_by_citations(
        joined, min_citations=1, max_age_years=-1, drop_missing=True
    )
    write_csv(
        outdir / "benchmark_candidates_priority_cited.csv",
        priority_kept,
        CITATION_FIELDS,
    )

    md = outdir / "CITATION_REPORT.md"
    lines: list[str] = []
    lines.append("# Citation filtering report: relevant benchmark candidates\n")
    lines.append(
        f"Generated {datetime.now(UTC).replace(microsecond=0).isoformat()} from "
        f"`{candidates.name}` + `{enrichment.name}` (as-of year {as_of_year}).\n"
    )
    lines.append(
        "Citation counts are the max of two sources: **Crossref** "
        "(`is-referenced-by-count`, by DOI, covers the ACL papers) and **Semantic "
        "Scholar** (bulk search by title, covers the no-DOI OpenReview/PMLR papers). "
        "OpenAlex was IP-blocked (429) throughout, so counts are still a lower bound. "
        "Papers whose title did not confidently match are counted as missing rather "
        "than assigned a wrong citation total.\n"
    )

    lines.append("## Summary\n")
    lines.append(
        _md_table(
            ["metric", "value"],
            [
                ["Relevant candidates (high+medium tier)", f"{stats['total']:,}"],
                ["With a citation count", f"{stats['with_citations']:,} "
                 f"({stats['coverage_pct']}%)"],
                ["Without a citation count", f"{stats['without_citations']:,}"],
                ["Median citations", stats["median"]],
                ["Mean citations", stats["mean"]],
                ["90th percentile", stats["p90"]],
                ["Max citations", f"{stats['max']:,}"],
            ],
        )
    )
    lines.append("")

    lines.append("## Citation histogram\n")
    lines.append("![Citation histogram](citation_histogram.png)\n")
    lines.append(
        _md_table(
            ["citations", "papers", "share", "cumulative papers", "cumulative %"],
            [
                [
                    row["citation_bucket"],
                    f"{int(row['papers']):,}",
                    f"{row['share_pct']}%",
                    f"{int(row['cumulative_papers']):,}",
                    f"{row['cumulative_pct']}%",
                ]
                for row in histogram
            ],
        )
    )
    lines.append("")

    lines.append("## Suggested min-citation cutoffs\n")
    lines.append(
        "How many papers survive a global citation threshold (papers with no "
        "resolved count are treated as dropped):\n"
    )
    lines.append(
        _md_table(
            ["min citations", "kept", "kept %", "dropped"],
            [
                [
                    f"≥ {row['min_citations']}",
                    f"{int(row['kept']):,}",
                    f"{row['kept_pct']}%",
                    f"{int(row['dropped']):,}",
                ]
                for row in cutoffs
            ],
        )
    )
    lines.append("")
    if recommended is not None:
        lines.append(
            f"**Recommended starting cutoff:** ≥ {recommended['min_citations']} "
            f"citations (keeps {int(recommended['kept']):,}, "
            f"{recommended['kept_pct']}% of the set). Process highest-cited first.\n"
        )

    ages = [
        _parse_int(row.get("citation_age_years"))
        for row in joined
        if _parse_int(row.get("citation_age_years")) is not None
    ]
    oldest_age = max(ages) if ages else 0
    newest_year = as_of_year - min(ages) if ages else as_of_year
    oldest_year = as_of_year - oldest_age if ages else as_of_year

    lines.append("## Filter preview (Zhijing's rule)\n")
    lines.append(
        "Drop papers older than 5 years with fewer than 10 citations; keep recent "
        "papers and rank survivors by citations descending "
        "(`filter-citations --min-citations 10 --max-age-years 5`):\n"
    )
    lines.append(
        _md_table(
            ["status", "papers"],
            [
                [status, f"{count:,}"]
                for status, count in sorted(zhijing_counts.items())
            ],
        )
    )
    lines.append(
        f"\n**Note:** this corpus spans {oldest_year}-{newest_year} (collection cutoff "
        f"is November 2022), so no paper is older than 5 years and the age gate never "
        f"fires: Zhijing's rule keeps everything here. For a recent corpus the "
        f"**operative lever is the global citation cutoff above**, not the age rule.\n"
    )
    lines.append(
        "Caveat: 'missing' means neither Crossref nor Semantic Scholar returned a "
        "confident title/DOI match, **not** that the paper is uncited.\n"
    )

    lines.append("## Operative priority queue\n")
    lines.append(
        f"Applying the global citation cutoff instead of the age rule: "
        f"**{len(priority_kept):,} papers with at least one citation**, ranked "
        f"highest-first, to process before the rest "
        f"(`filter-citations --min-citations 1 --max-age-years -1 --drop-missing`). "
        f"This is the actionable output for prioritising extraction.\n"
    )

    lines.append("## Files in this report\n")
    for name, desc in [
        ("citation_histogram.png", "histogram image"),
        ("citation_histogram.csv", "bucket counts + cumulative shares"),
        ("citation_cutoffs.csv", "coverage per threshold"),
        ("benchmark_candidates_filtered_zhijing.csv",
         "candidates surviving Zhijing's rule, ranked by citations"),
        ("benchmark_candidates_priority_cited.csv",
         "cited papers only (>=1), ranked highest-first: the process-first queue"),
        ("CITATION_REPORT.md", "this report"),
    ]:
        lines.append(f"- `{name}` — {desc}")
    lines.append("")

    md.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report: {md}")
    print(f"Histogram image: {png}")
    print(f"Candidates: {stats['total']:,} | coverage {stats['coverage_pct']}% | "
          f"median {stats['median']} | Zhijing kept {len(zhijing_kept):,}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--candidates",
        type=Path,
        default=Path("outputs/full_run/candidates_relevant.csv"),
    )
    parser.add_argument(
        "--enrichment",
        type=Path,
        default=Path("outputs/full_run/metadata_enrichment.csv"),
    )
    parser.add_argument("--as-of-year", type=int, default=2026)
    parser.add_argument(
        "--outdir", type=Path, default=Path("outputs/full_run/report")
    )
    args = parser.parse_args(argv)
    build_report(
        candidates=args.candidates,
        enrichment=args.enrichment,
        as_of_year=args.as_of_year,
        outdir=args.outdir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
