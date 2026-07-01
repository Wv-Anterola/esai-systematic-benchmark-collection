#!/usr/bin/env python3
"""Validate a v1.0.0 ESAI benchmark-map dataset package.

Checks, in order:

1. manifest present and self-consistent (declared files exist);
2. per-file `sha256` and row counts match the manifest;
3. every record validates against its JSON Schema (requires `jsonschema`);
4. primary keys are unique within each file;
5. declared cross-file references resolve (foreign `*_uuid` -> entity `uuid`).

Exit code is non-zero if any check fails.

Usage:
    python scripts/validate_dataset_v1.py --dir <v1_dir>
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover
    Draft202012Validator = None


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{i}: invalid JSON: {exc}") from exc
    return rows


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _dotted(record: dict, path: str):
    cur: object = record
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.checks = 0

    def check(self, ok: bool, message: str) -> None:
        self.checks += 1
        if not ok:
            self.errors.append(message)


def validate(root: Path) -> Report:
    report = Report()
    manifest_path = root / "dataset_manifest.json"
    if not manifest_path.exists():
        report.check(False, f"missing manifest: {manifest_path}")
        return report
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = manifest["files"]

    if Draft202012Validator is None:
        report.errors.append(
            "WARNING: jsonschema not installed; schema validation skipped "
            "(pip install jsonschema)"
        )

    loaded: dict[str, list[dict]] = {}  # record_type -> records
    uuid_index: dict[str, set[str]] = {}  # record_type -> set of uuids

    for rel, meta in files.items():
        path = root / rel
        record_type = meta["record_type"]
        if not path.exists():
            report.check(False, f"declared file missing: {rel}")
            continue

        report.check(_sha256(path) == meta["sha256"], f"{rel}: sha256 mismatch")
        rows = _load_jsonl(path)
        loaded[record_type] = rows
        report.check(
            len(rows) == meta["rows"],
            f"{rel}: row count {len(rows)} != manifest {meta['rows']}",
        )

        # 3. schema validation
        if Draft202012Validator is not None:
            schema_path = root / meta["schema"]
            report.check(
                schema_path.exists(), f"{rel}: schema {meta['schema']} missing"
            )
            if schema_path.exists():
                schema = json.loads(schema_path.read_text(encoding="utf-8"))
                validator = Draft202012Validator(schema)
                bad = 0
                first = ""
                for idx, rec in enumerate(rows):
                    err = next(iter(validator.iter_errors(rec)), None)
                    if err is not None:
                        bad += 1
                        if not first:
                            loc = "/".join(str(p) for p in err.absolute_path)
                            first = f"row {idx} [{loc}]: {err.message}"
                report.check(
                    bad == 0,
                    f"{rel}: {bad} record(s) fail schema; first: {first}",
                )

        # 4. primary-key uniqueness
        pk = meta["primary_key"]
        keys = ["|".join(str(_dotted(r, p)) for p in pk) for r in rows]
        report.check(
            len(keys) == len(set(keys)),
            f"{rel}: primary key {pk} not unique "
            f"({len(keys) - len(set(keys))} duplicate(s))",
        )

        uuid_index[record_type] = {r["uuid"] for r in rows if "uuid" in r}

    # 5. referential integrity
    for ref in manifest.get("references", []):
        from_type, from_field = ref["from"].split(".", 1)
        to_type, _to_field = ref["to"].split(".", 1)
        rows = loaded.get(from_type, [])
        targets = uuid_index.get(to_type, set())
        missing = 0
        example = ""
        for rec in rows:
            value = _dotted(rec, from_field)
            values = value if isinstance(value, list) else [value]
            for v in values:
                if v in (None, ""):
                    continue
                if v not in targets:
                    missing += 1
                    if not example:
                        example = str(v)
        report.check(
            missing == 0,
            f"reference {ref['from']} -> {ref['to']}: "
            f"{missing} unresolved (e.g. {example})",
        )

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", dest="root", required=True, type=Path)
    args = parser.parse_args()

    report = validate(args.root)
    warnings = [e for e in report.errors if e.startswith("WARNING")]
    failures = [e for e in report.errors if not e.startswith("WARNING")]
    for warning in warnings:
        print(f"warn: {warning}")
    if failures:
        print(f"FAIL: {len(failures)} problem(s) across {report.checks} checks:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"OK: {report.checks} checks passed for {args.root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
