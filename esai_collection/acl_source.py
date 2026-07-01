"""ACL Anthology source adapter for the shared raw benchmark schema.

The ACL Anthology is the authoritative record for the *ACL venue families (ACL,
EMNLP, NAACL, EACL, AACL, COLING, LREC, CL, TACL, CoNLL, Findings, ...). It ships
the full corpus as per-collection XML plus YAML venue metadata in its GitHub repo
(https://github.com/acl-org/acl-anthology), which the ``acl-anthology-py`` package
downloads and caches under the XDG data home.

We parse the Anthology XML *directly* rather than relying on the package object
model: parsing is independent of the package's pinned data-schema version, so a
new venue is just a new ``YYYY.<venue>.xml`` file and a future edition of an
existing venue is just a new ``<volume>`` -- both are picked up with no code
change. "Major venue" is read from the Anthology's own ``is_toplevel`` flag, so a
newly promoted venue is included the moment its YAML flips, with no edit here.

This adapter emits the shared raw schema (:data:`esai_collection.schema.RAW_FIELDS`)
so ACL records merge with OpenReview/PMLR records and flow through the same
screening, review, and export steps. Benchmark detection is left to the shared
screening step; this adapter collects every in-scope accepted paper, exactly like
the OpenReview and PMLR adapters.
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from .schema import CUTOFF_DATE
from .text import stable_id, utc_now

MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
_MONTH_PREFIX = {name[:3]: number for name, number in MONTHS.items()}


def find_data_dir(explicit: str | Path | None = None) -> Path:
    """Locate an ACL Anthology ``data/`` checkout that contains an ``xml/`` folder.

    Reuses the ``acl-anthology-py`` package cache under the XDG data home so we do
    not re-clone. ``ACL_ANTHOLOGY_DATA`` overrides the location for any checkout of
    ``acl-org/acl-anthology/data``.
    """
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    if os.environ.get("ACL_ANTHOLOGY_DATA"):
        candidates.append(Path(os.environ["ACL_ANTHOLOGY_DATA"]))
    xdg = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
    candidates.append(
        Path(xdg) / "acl-anthology" / "git" / "acl-org-acl-anthology-git" / "data"
    )
    for candidate in candidates:
        if (candidate / "xml").is_dir():
            return candidate
    try:  # pragma: no cover - exercised only with the package installed
        from acl_anthology import Anthology

        anthology = Anthology.from_repo()
        path = Path(anthology.datadir)
        if (path / "xml").is_dir():
            return path
    except Exception:  # pragma: no cover - optional dependency / network
        pass
    raise RuntimeError(
        "Could not find an ACL Anthology data/ checkout with an xml/ folder. "
        'Set ACL_ANTHOLOGY_DATA, or run `python -c "from acl_anthology import '
        'Anthology; Anthology.from_repo()"` once to download it.'
    )


def _month_number(text: str | None) -> int | None:
    if not text:
        return None
    for token in re.split(r"[\s\-/]+", text.strip().casefold()):
        if token in MONTHS:
            return MONTHS[token]
        if token[:3] in _MONTH_PREFIX:
            return _MONTH_PREFIX[token[:3]]
        if token.isdigit() and 1 <= int(token) <= 12:
            return int(token)
    return None


def _flatten(element: ET.Element | None) -> str:
    """Flatten an element's text, dropping inline markup like ``<fixed-case>``."""
    if element is None:
        return ""
    return re.sub(r"\s+", " ", "".join(element.itertext())).strip()


def load_venues(data_dir: Path) -> dict[str, dict[str, object]]:
    """Read ``data/yaml/venues/*.yaml`` into ``{venue_id: metadata}``.

    Metadata carries ``acronym`` and ``is_toplevel``. Top-level venues are the
    Anthology's own "major" flag; reading it here is what makes new venues appear
    automatically.
    """
    venues: dict[str, dict[str, object]] = {}
    venue_dir = data_dir / "yaml" / "venues"
    if not venue_dir.is_dir():
        return venues
    for path in sorted(venue_dir.glob("*.yaml")):
        meta: dict[str, object] = {
            "acronym": path.stem.upper(),
            "is_toplevel": False,
        }
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.rstrip()
            if line.startswith("acronym:"):
                meta["acronym"] = line.split(":", 1)[1].strip()
            elif line.startswith("is_toplevel:"):
                meta["is_toplevel"] = line.split(":", 1)[1].strip().casefold() == "true"
        venues[path.stem] = meta
    return venues


def major_venue_ids(venues: dict[str, dict[str, object]]) -> set[str]:
    return {venue_id for venue_id, meta in venues.items() if meta.get("is_toplevel")}


def _authors(paper: ET.Element) -> list[str]:
    names: list[str] = []
    for author in paper.findall("author"):
        first = (author.findtext("first") or "").strip()
        last = (author.findtext("last") or "").strip()
        name = " ".join(part for part in (first, last) if part) or _flatten(author)
        if name:
            names.append(name)
    return names


def _in_scope(
    year: int | None, month: int | None, since_year: int, since_month: int, ceiling: int
) -> bool:
    if year is None or year > ceiling:
        return False
    if year > since_year:
        return True
    if year < since_year:
        return False
    # Same year as the cutoff: require month >= cutoff; unknown month is permissive.
    return month is None or month >= since_month


def _iter_scoped_files(xml_dir: Path, since_year: int):
    for xml_file in sorted(xml_dir.glob("*.xml")):
        # Modern collections are ``YYYY.<venue>.xml``; a cheap year prefilter skips
        # legacy letter-prefixed files (e.g. ``J89.xml``) and pre-cutoff years.
        match = re.match(r"^(\d{4})\.", xml_file.name)
        if match and int(match.group(1)) < since_year:
            continue
        yield xml_file


def collect_acl(
    *,
    data_dir: str | Path | None = None,
    since_year: int = CUTOFF_DATE.year,
    since_month: int = CUTOFF_DATE.month,
    as_of_year: int | None = None,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Collect in-scope accepted papers from major ACL Anthology venues.

    Returns ``(records, logs)`` where records use the shared raw schema. One log
    entry is emitted per collection file with in-scope content or a parse error,
    giving query-level ``ok``/``empty``/``error`` provenance.
    """
    resolved_dir = find_data_dir(data_dir)
    venues = load_venues(resolved_dir)
    major = major_venue_ids(venues)
    ceiling = as_of_year or datetime.now(UTC).year

    collected_at = utc_now()
    run_id = f"acl-{collected_at.replace(':', '').replace('+00:00', 'Z')}"
    records: list[dict[str, object]] = []
    logs: list[dict[str, object]] = []

    for xml_file in _iter_scoped_files(resolved_dir / "xml", since_year):
        try:
            root = ET.parse(xml_file).getroot()
        except ET.ParseError as exc:
            logs.append(
                _log(run_id, collected_at, xml_file.stem, None, "error", 0, str(exc))
            )
            continue

        collection_id = root.get("id", xml_file.stem)
        file_count = 0
        for volume in root.findall("volume"):
            meta = volume.find("meta")
            if meta is None:
                continue
            year_text = meta.findtext("year")
            year = int(year_text) if year_text and year_text.isdigit() else None
            month = _month_number(meta.findtext("month"))
            venue_ids = [
                venue_id
                for element in meta.findall("venue")
                if (venue_id := (element.text or "").strip())
            ]
            major_here = [venue_id for venue_id in venue_ids if venue_id in major]
            if not major_here:
                continue
            if not _in_scope(year, month, since_year, since_month, ceiling):
                continue

            acronym = str(venues.get(major_here[0], {}).get("acronym", major_here[0]))
            track = "findings" if "findings" in venue_ids else "main"
            volume_id = volume.get("id", "")
            for paper in volume.findall("paper"):
                record = _record(
                    paper,
                    collection_id=collection_id,
                    volume_id=volume_id,
                    venue=acronym,
                    track=track,
                    year=year,
                    month=month,
                    collected_at=collected_at,
                    run_id=run_id,
                )
                if record is not None:
                    records.append(record)
                    file_count += 1

        if file_count:
            logs.append(
                _log(run_id, collected_at, collection_id, ceiling, "ok", file_count, "")
            )
    return records, logs


def _record(
    paper: ET.Element,
    *,
    collection_id: str,
    volume_id: str,
    venue: str,
    track: str,
    year: int | None,
    month: int | None,
    collected_at: str,
    run_id: str,
) -> dict[str, object] | None:
    title = _flatten(paper.find("title"))
    if not title:
        return None
    paper_id = paper.get("id", "")
    source_id = (
        f"{collection_id}-{volume_id}.{paper_id}"
        if volume_id
        else f"{collection_id}.{paper_id}"
    )
    anthology_id = (paper.findtext("url") or "").strip()
    paper_url = f"https://aclanthology.org/{anthology_id}/" if anthology_id else ""
    pdf_url = f"https://aclanthology.org/{anthology_id}.pdf" if anthology_id else ""
    authors = _authors(paper)
    if month:
        publication_date = f"{year:04d}-{month:02d}-01"
        basis = "anthology-volume-month"
    else:
        publication_date = f"{year:04d}-01-01"
        basis = "anthology-volume-year"
    return {
        "record_id": stable_id("acl", source_id),
        "source": "acl",
        "source_id": source_id,
        "title": title,
        "abstract": _flatten(paper.find("abstract")),
        "authors": "; ".join(authors),
        "author_count": len(authors),
        "publication_date": publication_date,
        "publication_date_basis": basis,
        "year": year,
        "venue": venue,
        "venue_track": track,
        "decision": "accepted",
        "keywords": "",
        "tldr": "",
        "paper_url": paper_url,
        "pdf_url": pdf_url,
        "code_url": "",
        "openreview_id": "",
        "pmlr_id": "",
        "doi": (paper.findtext("doi") or "").strip(),
        "collected_at": collected_at,
        "run_id": run_id,
    }


def _log(
    run_id: str,
    collected_at: str,
    collection_id: str,
    year: int | None,
    status: str,
    records: int,
    error: str,
) -> dict[str, object]:
    return {
        "run_id": run_id,
        "collected_at": collected_at,
        "source": "acl",
        "venue": collection_id,
        "year": year if year is not None else "",
        "track": "",
        "volume": collection_id,
        "source_url": f"https://aclanthology.org/{collection_id}/",
        "status": status,
        "records": records,
        "error": error,
    }
