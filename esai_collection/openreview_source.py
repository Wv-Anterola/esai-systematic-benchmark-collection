from __future__ import annotations

import os
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from .schema import VenueSpec, default_openreview_venues
from .text import stable_id, utc_now, year_from_text

API_V1 = "https://api.openreview.net"
API_V2 = "https://api2.openreview.net"
SITE = "https://openreview.net"


def content_value(content: dict[str, Any], key: str) -> Any:
    value = content.get(key)
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    return value


def as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list | tuple):
        return "; ".join(str(item) for item in value)
    return str(value)


def first_value(primary: dict[str, Any], secondary: dict[str, Any], *keys: str) -> Any:
    for source in (primary, secondary):
        for key in keys:
            value = content_value(source, key)
            if value:
                return value
    return None


def _retry(
    call: Callable[[], list[Any]], label: str, attempts: int = 3
) -> tuple[list[Any], str]:
    last_error = ""
    for attempt in range(1, attempts + 1):
        try:
            return call(), ""
        except Exception as exc:  # network and API exceptions vary by client version
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < attempts:
                time.sleep(2 ** (attempt - 1))
    return [], f"{label}: {last_error}"


def _fetch_v2(client: Any, venue_id: str) -> tuple[list[tuple[str, dict, dict]], str]:
    notes, error = _retry(
        lambda: client.get_all_notes(content={"venueid": venue_id}), venue_id
    )
    return [
        (note.id, getattr(note, "content", None) or {}, {}) for note in notes
    ], error


def _fetch_v1(client: Any, venue_id: str) -> tuple[list[tuple[str, dict, dict]], str]:
    errors: list[str] = []
    for suffix in ("Blind_Submission", "Submission"):
        submissions, error = _retry(
            lambda suffix=suffix: client.get_all_notes(
                invitation=f"{venue_id}/-/{suffix}",
                details="directReplies,original",
            ),
            f"{venue_id}/{suffix}",
        )
        if error:
            errors.append(error)
            continue
        if not submissions:
            continue
        accepted: list[tuple[str, dict, dict]] = []
        for submission in submissions:
            details = getattr(submission, "details", None) or {}
            decision = ""
            for reply in details.get("directReplies", []) or []:
                if str(reply.get("invitation", "")).endswith("Decision"):
                    raw = (reply.get("content", {}) or {}).get("decision", "")
                    decision = raw.get("value", raw) if isinstance(raw, dict) else raw
                    break
            if "accept" not in str(decision).casefold():
                continue
            original = (details.get("original") or {}).get("content", {}) or {}
            accepted.append(
                (submission.id, getattr(submission, "content", None) or {}, original)
            )
        return accepted, ""
    return [], "; ".join(errors)


def _publication_date(venue: str, year: int) -> str:
    month = {"ICLR": 5, "NeurIPS": 12, "COLM": 10}.get(venue, 1)
    return f"{year:04d}-{month:02d}-01"


def _record(
    note_id: str,
    content: dict[str, Any],
    extra: dict[str, Any],
    spec: VenueSpec,
    collected_at: str,
    run_id: str,
) -> dict[str, object]:
    title = as_text(content_value(content, "title"))
    abstract = as_text(content_value(content, "abstract"))
    keywords = as_text(content_value(content, "keywords"))
    venue_text = as_text(content_value(content, "venue"))
    authors_raw = first_value(content, extra, "authors")
    pdf = as_text(content_value(content, "pdf"))
    if pdf.startswith("/"):
        pdf = f"{SITE}{pdf}"
    code = as_text(first_value(content, {}, "code", "github"))
    return {
        "record_id": stable_id("openreview", note_id),
        "source": "openreview",
        "source_id": note_id,
        "title": title,
        "abstract": abstract,
        "authors": as_text(authors_raw),
        "author_count": len(authors_raw)
        if isinstance(authors_raw, list | tuple)
        else int(bool(authors_raw)),
        "publication_date": _publication_date(spec.venue, spec.year),
        "publication_date_basis": "venue-edition-estimate",
        "year": year_from_text(venue_text, str(spec.year)),
        "venue": spec.venue,
        "venue_track": spec.track,
        "decision": venue_text or "accepted",
        "keywords": keywords,
        "tldr": as_text(first_value(content, {}, "TLDR", "tldr")),
        "paper_url": f"{SITE}/forum?id={note_id}",
        "pdf_url": pdf,
        "code_url": code,
        "openreview_id": note_id,
        "pmlr_id": "",
        "doi": as_text(first_value(content, {}, "doi")),
        "collected_at": collected_at,
        "run_id": run_id,
    }


def build_clients() -> tuple[Any, Any]:
    try:
        import openreview
    except ImportError as exc:  # pragma: no cover - exercised by installation checks
        raise RuntimeError(
            "openreview-py is required for OpenReview collection"
        ) from exc
    username = os.environ.get("OPENREVIEW_USERNAME")
    password = os.environ.get("OPENREVIEW_PASSWORD")
    v2 = openreview.api.OpenReviewClient(
        baseurl=API_V2, username=username, password=password
    )
    v1 = openreview.Client(baseurl=API_V1, username=username, password=password)
    return v2, v1


def collect_openreview(
    *,
    as_of_year: int | None = None,
    specs: list[VenueSpec] | None = None,
    limit_per_venue: int | None = None,
    clients: tuple[Any, Any] | None = None,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Collect accepted papers from supported OpenReview venues.

    Every attempted venue identifier receives its own run-log entry. API errors
    and valid empty results are recorded separately.
    """
    year = as_of_year or datetime.now(UTC).year
    selected = specs or default_openreview_venues(year)
    v2, v1 = clients or build_clients()
    collected_at = utc_now()
    run_id = f"openreview-{collected_at.replace(':', '').replace('+00:00', 'Z')}"
    records: list[dict[str, object]] = []
    logs: list[dict[str, object]] = []

    for spec in selected:
        resolved = False
        for venue_id in spec.venue_ids:
            notes, v2_error = _fetch_v2(v2, venue_id)
            source_api = "v2"
            error = v2_error
            if not notes:
                legacy, v1_error = _fetch_v1(v1, venue_id)
                if legacy:
                    notes, source_api, error = legacy, "v1", ""
                elif v1_error:
                    error = "; ".join(filter(None, (v2_error, v1_error)))

            if limit_per_venue:
                notes = notes[:limit_per_venue]
            status = "ok" if notes else ("error" if error else "empty")
            logs.append(
                {
                    "run_id": run_id,
                    "collected_at": collected_at,
                    "source": "openreview",
                    "venue": spec.venue,
                    "year": spec.year,
                    "track": spec.track,
                    "venue_id": venue_id,
                    "source_api": source_api,
                    "status": status,
                    "records": len(notes),
                    "error": error,
                }
            )
            if notes:
                records.extend(
                    _record(note_id, content, extra, spec, collected_at, run_id)
                    for note_id, content, extra in notes
                )
                resolved = True
                break
        if not resolved:
            continue
    return records, logs
