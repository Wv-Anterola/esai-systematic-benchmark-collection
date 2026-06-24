from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import __version__

REPOSITORY = Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=REPOSITORY,
        capture_output=True,
        check=False,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPOSITORY).as_posix()
    except ValueError:
        return resolved.name


def write_manifest(
    path: Path,
    *,
    command: str,
    inputs: list[Path] | None = None,
    outputs: list[Path] | None = None,
    workbook: Path | None = None,
    parameters: dict[str, Any] | None = None,
    counts: dict[str, int] | None = None,
) -> None:
    payload: dict[str, Any] = {
        "command": command,
        "created_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "tool_version": __version__,
        "git_commit": _git(["rev-parse", "HEAD"]),
        "git_dirty": bool(_git(["status", "--porcelain"])),
        "parameters": parameters or {},
        "counts": counts or {},
        "inputs": [],
        "outputs": [],
    }
    for source in inputs or []:
        payload["inputs"].append(
            {"path": _display_path(source), "sha256": sha256_file(source)}
        )
    for output in outputs or []:
        payload["outputs"].append(
            {"path": _display_path(output), "sha256": sha256_file(output)}
        )
    if workbook is not None:
        payload["workbook"] = {
            "path": _display_path(workbook),
            "sha256": sha256_file(workbook),
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
