from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from . import __version__
from .io import read_csv, write_csv
from .openreview_source import collect_openreview
from .pmlr_source import collect_icml
from .schema import RAW_FIELDS, REVIEW_COLUMNS, SCREENING_FIELDS, TRACKER_COLUMNS
from .screening import approved_tracker_rows, review_queue, screen
from .text import utc_now

LOG_FIELDS = [
    "run_id",
    "collected_at",
    "source",
    "venue",
    "year",
    "track",
    "venue_id",
    "volume",
    "source_url",
    "source_api",
    "status",
    "records",
    "error",
]


def _year(value: str) -> int:
    year = int(value)
    if year < 2022 or year > 2100:
        raise argparse.ArgumentTypeError("year must be between 2022 and 2100")
    return year


def _write_manifest(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def collect_openreview_command(args: argparse.Namespace) -> int:
    records, logs = collect_openreview(
        as_of_year=args.as_of_year, limit_per_venue=args.limit_per_venue
    )
    write_csv(args.out, records, RAW_FIELDS)
    write_csv(args.log, logs, LOG_FIELDS)
    print(f"OpenReview records: {len(records)}")
    print(f"Run log: {args.log}")
    print(f"Raw data: {args.out}")
    return int(any(row.get("status") == "error" for row in logs))


def collect_icml_command(args: argparse.Namespace) -> int:
    records, logs = collect_icml(as_of_year=args.as_of_year)
    write_csv(args.out, records, RAW_FIELDS)
    write_csv(args.log, logs, LOG_FIELDS)
    print(f"ICML records: {len(records)}")
    print(f"Run log: {args.log}")
    print(f"Raw data: {args.out}")
    return int(any(row.get("status") == "error" for row in logs))


def merge_command(args: argparse.Namespace) -> int:
    by_id: dict[str, dict[str, str]] = {}
    for path in args.inputs:
        for row in read_csv(path):
            record_id = row.get("record_id", "")
            if not record_id:
                raise ValueError(f"{path} contains a row without record_id")
            by_id.setdefault(record_id, row)
    rows = sorted(
        by_id.values(),
        key=lambda row: (
            row.get("venue", ""),
            row.get("year", ""),
            row.get("title", ""),
        ),
    )
    write_csv(args.out, rows, RAW_FIELDS)
    print(f"Merged records: {len(rows)}")
    print(f"Raw data: {args.out}")
    return 0


def screen_command(args: argparse.Namespace) -> int:
    workbook = args.workbook.resolve() if args.workbook else None
    candidates = screen(read_csv(args.input), workbook)
    queue = review_queue(candidates, include_low=args.include_low)
    write_csv(args.out, candidates, SCREENING_FIELDS)
    write_csv(args.review_queue, queue, REVIEW_COLUMNS)
    print(f"Screened candidates: {len(candidates)}")
    print(f"Review queue: {len(queue)}")
    print(f"Candidates: {args.out}")
    print(f"Tracker review queue: {args.review_queue}")
    return 0


def export_command(args: argparse.Namespace) -> int:
    rows = approved_tracker_rows(read_csv(args.review_queue))
    write_csv(args.out, rows, TRACKER_COLUMNS)
    print(f"Approved tracker rows: {len(rows)}")
    print(f"Tracker import: {args.out}")
    return 0


def run_command(args: argparse.Namespace) -> int:
    args.outdir.mkdir(parents=True, exist_ok=True)
    raw: list[dict[str, object]] = []
    logs: list[dict[str, object]] = []
    if not args.skip_openreview:
        source_rows, source_logs = collect_openreview(
            as_of_year=args.as_of_year, limit_per_venue=args.limit_per_venue
        )
        raw.extend(source_rows)
        logs.extend(source_logs)
    if not args.skip_icml:
        source_rows, source_logs = collect_icml(as_of_year=args.as_of_year)
        raw.extend(source_rows)
        logs.extend(source_logs)

    unique = {str(row["record_id"]): row for row in raw}
    merged = list(unique.values())
    candidates = screen(
        [{key: str(value) for key, value in row.items()} for row in merged],
        args.workbook.resolve() if args.workbook else None,
    )
    queue = review_queue(candidates, include_low=args.include_low)

    write_csv(args.outdir / "papers_raw.csv", merged, RAW_FIELDS)
    write_csv(args.outdir / "collection_log.csv", logs, LOG_FIELDS)
    write_csv(args.outdir / "benchmark_candidates.csv", candidates, SCREENING_FIELDS)
    write_csv(args.outdir / "tracker_review_queue.csv", queue, REVIEW_COLUMNS)
    manifest = {
        "tool_version": __version__,
        "created_at": utc_now(),
        "as_of_year": args.as_of_year,
        "cutoff_policy": "ICLR 2023+, ICML 2023+, NeurIPS 2022+, COLM 2024+",
        "acl_included": False,
        "sources": {
            "openreview": not args.skip_openreview,
            "pmlr_icml": not args.skip_icml,
        },
        "counts": {
            "raw_records": len(merged),
            "candidate_records": len(candidates),
            "review_queue_records": len(queue),
            "source_errors": sum(row.get("status") == "error" for row in logs),
        },
        "workbook": str(args.workbook.resolve()) if args.workbook else None,
    }
    _write_manifest(args.outdir / "run_manifest.json", manifest)
    print(json.dumps(manifest["counts"], indent=2))
    print(f"Outputs: {args.outdir}")
    return int(manifest["counts"]["source_errors"] > 0)


def build_parser() -> argparse.ArgumentParser:
    current_year = datetime.now(UTC).year
    parser = argparse.ArgumentParser(
        prog="esai-collect",
        description="Collect benchmark papers and prepare ESAI tracker imports.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    openreview = subparsers.add_parser(
        "collect-openreview", help="collect ICLR, NeurIPS, and COLM"
    )
    openreview.add_argument("--as-of-year", type=_year, default=current_year)
    openreview.add_argument("--limit-per-venue", type=int)
    openreview.add_argument(
        "--out", type=Path, default=Path("outputs/openreview_raw.csv")
    )
    openreview.add_argument(
        "--log", type=Path, default=Path("outputs/openreview_log.csv")
    )
    openreview.set_defaults(handler=collect_openreview_command)

    icml = subparsers.add_parser("collect-icml", help="collect ICML from PMLR")
    icml.add_argument("--as-of-year", type=_year, default=current_year)
    icml.add_argument("--out", type=Path, default=Path("outputs/icml_raw.csv"))
    icml.add_argument("--log", type=Path, default=Path("outputs/icml_log.csv"))
    icml.set_defaults(handler=collect_icml_command)

    merge = subparsers.add_parser("merge", help="merge source-specific raw files")
    merge.add_argument("inputs", type=Path, nargs="+")
    merge.add_argument("--out", type=Path, default=Path("outputs/papers_raw.csv"))
    merge.set_defaults(handler=merge_command)

    screening = subparsers.add_parser(
        "screen", help="screen merged papers and create a review queue"
    )
    screening.add_argument("--input", type=Path, default=Path("outputs/papers_raw.csv"))
    screening.add_argument("--workbook", type=Path)
    screening.add_argument("--include-low", action="store_true")
    screening.add_argument(
        "--out", type=Path, default=Path("outputs/benchmark_candidates.csv")
    )
    screening.add_argument(
        "--review-queue", type=Path, default=Path("outputs/tracker_review_queue.csv")
    )
    screening.set_defaults(handler=screen_command)

    export = subparsers.add_parser(
        "export", help="export approved review rows to tracker schema"
    )
    export.add_argument(
        "--review-queue", type=Path, default=Path("outputs/tracker_review_queue.csv")
    )
    export.add_argument(
        "--out", type=Path, default=Path("outputs/tracker_benchmarks.csv")
    )
    export.set_defaults(handler=export_command)

    run = subparsers.add_parser(
        "run", help="run collection, screening, and tracker preparation"
    )
    run.add_argument("--as-of-year", type=_year, default=current_year)
    run.add_argument("--workbook", type=Path)
    run.add_argument("--outdir", type=Path, default=Path("outputs/run"))
    run.add_argument("--limit-per-venue", type=int)
    run.add_argument("--include-low", action="store_true")
    run.add_argument("--skip-openreview", action="store_true")
    run.add_argument("--skip-icml", action="store_true")
    run.set_defaults(handler=run_command)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
