from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from .enrichment import ENRICHMENT_FIELDS, enrich_records
from .hf_dataset import SCHEMA_VERSION, export_hf_dataset
from .hf_discovery import HF_DISCOVERY_FIELDS, discover_hf_datasets
from .http import JsonHttpClient
from .io import read_csv, write_csv
from .openreview_source import collect_openreview
from .pmlr_source import collect_icml
from .provenance import write_manifest
from .recall import RECALL_AUDIT_FIELDS, sample_recall_audit
from .schema import (
    MAPPING_HANDOFF_COLUMNS,
    RAW_FIELDS,
    REVIEW_COLUMNS,
    SCREENING_FIELDS,
    TRACKER_COLUMNS,
)
from .screening import (
    approved_mapping_rows,
    approved_tracker_rows,
    review_queue,
    screen,
    tracker_quick_refs,
)
from .sheet_package import (
    COLLECTION_SHEET_FIELDS,
    ID_REPAIR_SHEET_FIELDS,
    MAPPING_PATCH_SHEET_FIELDS,
    VALIDATION_ISSUE_SUMMARY_FIELDS,
    clean_collection_review_rows,
    clean_id_repair_rows,
    clean_mapping_patch_rows,
    package_counts,
    summarize_validation_issues,
)

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


def _sidecar(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".manifest.json")


def _providers(value: str) -> set[str]:
    providers = {item.strip().casefold() for item in value.split(",") if item.strip()}
    allowed = {"semantic-scholar", "openalex"}
    unknown = providers - allowed
    if unknown:
        raise argparse.ArgumentTypeError(
            f"unknown providers: {', '.join(sorted(unknown))}"
        )
    if not providers:
        raise argparse.ArgumentTypeError("at least one provider is required")
    return providers


def _queries(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def collect_openreview_command(args: argparse.Namespace) -> int:
    records, logs = collect_openreview(
        as_of_year=args.as_of_year, limit_per_venue=args.limit_per_venue
    )
    write_csv(args.out, records, RAW_FIELDS)
    write_csv(args.log, logs, LOG_FIELDS)
    write_manifest(
        _sidecar(args.out),
        command="collect-openreview",
        outputs=[args.out, args.log],
        parameters={
            "as_of_year": args.as_of_year,
            "limit_per_venue": args.limit_per_venue,
        },
        counts={
            "records": len(records),
            "source_errors": sum(row.get("status") == "error" for row in logs),
        },
    )
    print(f"OpenReview records: {len(records)}")
    print(f"Run log: {args.log}")
    print(f"Raw data: {args.out}")
    return int(any(row.get("status") == "error" for row in logs))


def collect_icml_command(args: argparse.Namespace) -> int:
    records, logs = collect_icml(as_of_year=args.as_of_year)
    write_csv(args.out, records, RAW_FIELDS)
    write_csv(args.log, logs, LOG_FIELDS)
    write_manifest(
        _sidecar(args.out),
        command="collect-icml",
        outputs=[args.out, args.log],
        parameters={"as_of_year": args.as_of_year},
        counts={
            "records": len(records),
            "source_errors": sum(row.get("status") == "error" for row in logs),
        },
    )
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
    write_manifest(
        _sidecar(args.out),
        command="merge",
        inputs=args.inputs,
        outputs=[args.out],
        counts={"records": len(rows)},
    )
    print(f"Merged records: {len(rows)}")
    print(f"Raw data: {args.out}")
    return 0


def screen_command(args: argparse.Namespace) -> int:
    workbook = args.workbook.resolve() if args.workbook else None
    candidates = screen(read_csv(args.input), workbook)
    queue = review_queue(candidates, include_low=args.include_low)
    write_csv(args.out, candidates, SCREENING_FIELDS)
    write_csv(args.review_queue, queue, REVIEW_COLUMNS)
    write_manifest(
        _sidecar(args.out),
        command="screen",
        inputs=[args.input],
        outputs=[args.out, args.review_queue],
        workbook=workbook,
        parameters={"include_low": args.include_low},
        counts={"candidates": len(candidates), "review_queue": len(queue)},
    )
    print(f"Screened candidates: {len(candidates)}")
    print(f"Review queue: {len(queue)}")
    print(f"Candidates: {args.out}")
    print(f"Tracker review queue: {args.review_queue}")
    return 0


def export_command(args: argparse.Namespace) -> int:
    review_rows = read_csv(args.review_queue)
    workbook = args.workbook.resolve()
    tracker_rows = approved_tracker_rows(review_rows, tracker_quick_refs(workbook))
    mapping_rows = approved_mapping_rows(review_rows)
    write_csv(args.out, tracker_rows, TRACKER_COLUMNS)
    write_csv(args.mapping_out, mapping_rows, MAPPING_HANDOFF_COLUMNS)
    write_manifest(
        _sidecar(args.out),
        command="export",
        inputs=[args.review_queue],
        outputs=[args.out, args.mapping_out],
        workbook=workbook,
        counts={"approved_tracker_rows": len(tracker_rows)},
    )
    print(f"Approved tracker rows: {len(tracker_rows)}")
    print(f"Tracker import: {args.out}")
    print(f"Mapping handoff: {args.mapping_out}")
    return 0


def enrich_metadata_command(args: argparse.Namespace) -> int:
    rows = read_csv(args.input)
    client = JsonHttpClient(timeout=args.timeout, delay_seconds=args.delay_seconds)
    enriched = enrich_records(
        rows,
        client=client,
        providers=args.providers,
        limit=args.limit,
        semantic_scholar_api_key=args.semantic_scholar_api_key,
        openalex_api_key=args.openalex_api_key,
    )
    write_csv(args.out, enriched, ENRICHMENT_FIELDS)
    write_manifest(
        _sidecar(args.out),
        command="enrich-metadata",
        inputs=[args.input],
        outputs=[args.out],
        parameters={
            "providers": sorted(args.providers),
            "limit": args.limit,
            "timeout": args.timeout,
            "delay_seconds": args.delay_seconds,
            "semantic_scholar_api_key": bool(args.semantic_scholar_api_key),
            "openalex_api_key": bool(args.openalex_api_key),
        },
        counts={
            "input_rows": len(rows),
            "output_rows": len(enriched),
            "semantic_scholar_ok": sum(
                row.get("semantic_scholar_status") == "ok" for row in enriched
            ),
            "openalex_ok": sum(row.get("openalex_status") == "ok" for row in enriched),
        },
    )
    print(f"Enriched rows: {len(enriched)}")
    print(f"Output: {args.out}")
    return 0


def discover_hf_datasets_command(args: argparse.Namespace) -> int:
    candidates = read_csv(args.candidates) if args.candidates else None
    client = JsonHttpClient(timeout=args.timeout, delay_seconds=args.delay_seconds)
    rows = discover_hf_datasets(
        client=client,
        candidates=candidates,
        queries=args.queries,
        max_candidate_queries=args.max_candidate_queries,
        limit_per_query=args.limit_per_query,
    )
    write_csv(args.out, rows, HF_DISCOVERY_FIELDS)
    inputs = [args.candidates] if args.candidates else []
    write_manifest(
        _sidecar(args.out),
        command="discover-hf-datasets",
        inputs=inputs,
        outputs=[args.out],
        parameters={
            "queries": args.queries,
            "max_candidate_queries": args.max_candidate_queries,
            "limit_per_query": args.limit_per_query,
            "timeout": args.timeout,
            "delay_seconds": args.delay_seconds,
        },
        counts={
            "rows": len(rows),
            "unique_datasets": len(
                {row.get("dataset_id", "") for row in rows if row.get("dataset_id")}
            ),
        },
    )
    print(f"Dataset discovery rows: {len(rows)}")
    print(f"Output: {args.out}")
    return 0


def recall_audit_command(args: argparse.Namespace) -> int:
    rows = read_csv(args.candidates)
    sample = sample_recall_audit(rows, size=args.size, seed=args.seed)
    write_csv(args.out, sample, RECALL_AUDIT_FIELDS)
    write_manifest(
        _sidecar(args.out),
        command="sample-recall-audit",
        inputs=[args.candidates],
        outputs=[args.out],
        parameters={"size": args.size, "seed": args.seed},
        counts={
            "rows": len(sample),
            "venues": len({row.get("venue", "") for row in sample}),
        },
    )
    print(f"Recall audit rows: {len(sample)}")
    print(f"Output: {args.out}")
    return 0


def prepare_sheet_package_command(args: argparse.Namespace) -> int:
    args.outdir.mkdir(parents=True, exist_ok=True)
    collection_rows = clean_collection_review_rows(read_csv(args.review_queue))
    issue_rows = (
        summarize_validation_issues(read_csv(args.validation_issues))
        if args.validation_issues.exists()
        else []
    )
    id_repair_rows = (
        clean_id_repair_rows(read_csv(args.id_repairs))
        if args.id_repairs.exists()
        else []
    )
    mapping_patch_rows = (
        clean_mapping_patch_rows(read_csv(args.mapping_patch))
        if args.mapping_patch and args.mapping_patch.exists()
        else []
    )
    outputs = [
        args.outdir / "collection_review_clean.csv",
        args.outdir / "validation_issues_summary.csv",
        args.outdir / "duplicate_edge_id_repairs_clean.csv",
        args.outdir / "mapping_patch_clean.csv",
    ]
    write_csv(outputs[0], collection_rows, COLLECTION_SHEET_FIELDS)
    write_csv(outputs[1], issue_rows, VALIDATION_ISSUE_SUMMARY_FIELDS)
    write_csv(outputs[2], id_repair_rows, ID_REPAIR_SHEET_FIELDS)
    write_csv(outputs[3], mapping_patch_rows, MAPPING_PATCH_SHEET_FIELDS)
    inputs = [
        path
        for path in (
            args.review_queue,
            args.validation_issues,
            args.id_repairs,
            args.mapping_patch,
        )
        if path and path.exists()
    ]
    counts = package_counts(
        collection_rows=collection_rows,
        issue_summary_rows=issue_rows,
        id_repair_rows=id_repair_rows,
        mapping_patch_rows=mapping_patch_rows,
    )
    write_manifest(
        args.outdir / "sheet_package_manifest.json",
        command="prepare-sheet-package",
        inputs=inputs,
        outputs=outputs,
        counts=counts,
    )
    print(json.dumps(counts, indent=2, sort_keys=True))
    print(f"Sheet package: {args.outdir}")
    return 0


def _read_existing_csv(path: Path | None) -> list[dict[str, str]]:
    return read_csv(path) if path and path.exists() else []


def export_hf_dataset_command(args: argparse.Namespace) -> int:
    outputs, counts = export_hf_dataset(
        outdir=args.outdir,
        dataset_name=args.dataset_name,
        papers=_read_existing_csv(args.papers),
        candidates=_read_existing_csv(args.candidates),
        review_queue=_read_existing_csv(args.review_queue),
        mapping_edges=_read_existing_csv(args.mapping_edges),
        source_registry=_read_existing_csv(args.source_registry),
        schema_version=args.schema_version,
    )
    inputs = [
        path
        for path in (
            args.papers,
            args.candidates,
            args.review_queue,
            args.mapping_edges,
            args.source_registry,
        )
        if path and path.exists()
    ]
    write_manifest(
        args.outdir / "dataset_manifest.json",
        command="export-hf-dataset",
        inputs=inputs,
        outputs=outputs,
        parameters={
            "dataset_name": args.dataset_name,
            "schema_version": args.schema_version,
        },
        counts=counts,
    )
    print(json.dumps(counts, indent=2, sort_keys=True))
    print(f"HuggingFace dataset package: {args.outdir}")
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
    output_paths = [
        args.outdir / "papers_raw.csv",
        args.outdir / "collection_log.csv",
        args.outdir / "benchmark_candidates.csv",
        args.outdir / "tracker_review_queue.csv",
    ]
    counts = {
        "raw_records": len(merged),
        "candidate_records": len(candidates),
        "review_queue_records": len(queue),
        "source_errors": sum(row.get("status") == "error" for row in logs),
    }
    write_manifest(
        args.outdir / "run_manifest.json",
        command="run",
        outputs=output_paths,
        workbook=args.workbook.resolve() if args.workbook else None,
        parameters={
            "as_of_year": args.as_of_year,
            "cutoff_policy": "ICLR 2023+, ICML 2023+, NeurIPS 2022+, COLM 2024+",
            "acl_included": False,
            "openreview_enabled": not args.skip_openreview,
            "pmlr_icml_enabled": not args.skip_icml,
            "limit_per_venue": args.limit_per_venue,
            "include_low": args.include_low,
        },
        counts=counts,
    )
    print(json.dumps(counts, indent=2))
    print(f"Outputs: {args.outdir}")
    return int(counts["source_errors"] > 0)


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
    export.add_argument("--workbook", type=Path, required=True)
    export.add_argument(
        "--out", type=Path, default=Path("outputs/tracker_benchmarks.csv")
    )
    export.add_argument(
        "--mapping-out",
        type=Path,
        default=Path("outputs/tracker_mapping_handoff.csv"),
    )
    export.set_defaults(handler=export_command)

    enrich = subparsers.add_parser(
        "enrich-metadata",
        help="create Semantic Scholar/OpenAlex metadata sidecars",
    )
    enrich.add_argument("--input", type=Path, default=Path("outputs/papers_raw.csv"))
    enrich.add_argument(
        "--providers",
        type=_providers,
        default={"semantic-scholar", "openalex"},
        help="comma-separated providers: semantic-scholar,openalex",
    )
    enrich.add_argument("--limit", type=int)
    enrich.add_argument("--timeout", type=int, default=30)
    enrich.add_argument("--delay-seconds", type=float, default=0.0)
    enrich.add_argument("--semantic-scholar-api-key")
    enrich.add_argument("--openalex-api-key")
    enrich.add_argument(
        "--out", type=Path, default=Path("outputs/metadata_enrichment.csv")
    )
    enrich.set_defaults(handler=enrich_metadata_command)

    hf = subparsers.add_parser(
        "discover-hf-datasets",
        help="search Hugging Face datasets for benchmark artifacts",
    )
    hf.add_argument("--candidates", type=Path)
    hf.add_argument("--queries", type=_queries, default=[])
    hf.add_argument("--max-candidate-queries", type=int, default=50)
    hf.add_argument("--limit-per-query", type=int, default=10)
    hf.add_argument("--timeout", type=int, default=30)
    hf.add_argument("--delay-seconds", type=float, default=0.0)
    hf.add_argument(
        "--out", type=Path, default=Path("outputs/hf_dataset_discovery.csv")
    )
    hf.set_defaults(handler=discover_hf_datasets_command)

    recall = subparsers.add_parser(
        "sample-recall-audit",
        help="sample low-tier candidates for screening recall checks",
    )
    recall.add_argument(
        "--candidates", type=Path, default=Path("outputs/benchmark_candidates.csv")
    )
    recall.add_argument("--size", type=int, default=200)
    recall.add_argument("--seed", type=int, default=20260701)
    recall.add_argument(
        "--out", type=Path, default=Path("outputs/low_tier_recall_audit.csv")
    )
    recall.set_defaults(handler=recall_audit_command)

    sheet = subparsers.add_parser(
        "prepare-sheet-package",
        help="clean collection and validation outputs for shared-sheet import",
    )
    sheet.add_argument(
        "--review-queue",
        type=Path,
        default=Path("outputs/latest/tracker_review_queue.csv"),
    )
    sheet.add_argument(
        "--validation-issues",
        type=Path,
        default=Path("../mapping-validation/outputs/hardened/deterministic_issues.csv"),
    )
    sheet.add_argument(
        "--id-repairs",
        type=Path,
        default=Path(
            "../mapping-validation/outputs/hardened/duplicate_edge_id_repairs.csv"
        ),
    )
    sheet.add_argument("--mapping-patch", type=Path)
    sheet.add_argument("--outdir", type=Path, default=Path("outputs/sheet_package"))
    sheet.set_defaults(handler=prepare_sheet_package_command)

    dataset = subparsers.add_parser(
        "export-hf-dataset",
        help="write a HuggingFace-ready JSONL dataset package",
    )
    dataset.add_argument(
        "--papers", type=Path, default=Path("outputs/latest/papers_raw.csv")
    )
    dataset.add_argument(
        "--candidates",
        type=Path,
        default=Path("outputs/latest/benchmark_candidates.csv"),
    )
    dataset.add_argument(
        "--review-queue",
        type=Path,
        default=Path("outputs/latest/tracker_review_queue.csv"),
    )
    dataset.add_argument(
        "--mapping-edges",
        type=Path,
        default=Path("../mapping-validation/outputs/hardened/all_edges.csv"),
    )
    dataset.add_argument(
        "--source-registry",
        type=Path,
        default=Path("../mapping-validation/outputs/hardened/benchmark_sources.csv"),
    )
    dataset.add_argument("--outdir", type=Path, default=Path("outputs/hf_dataset"))
    dataset.add_argument("--dataset-name", default="esai-benchmark-map")
    dataset.add_argument("--schema-version", default=SCHEMA_VERSION)
    dataset.set_defaults(handler=export_hf_dataset_command)

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
