from __future__ import annotations

import html
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser

from .text import stable_id, utc_now

ARCHIVE_URL = "https://proceedings.mlr.press/"
RAW_REPOSITORY = "https://raw.githubusercontent.com/mlresearch/{volume}/gh-pages/{file}"
USER_AGENT = "esai-benchmark-collection/0.1 (+https://github.com/Wv-Anterola)"


@dataclass(frozen=True)
class PmlrVolume:
    volume: str
    year: int
    label: str


class _ArchiveParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_item = False
        self.href = ""
        self.parts: list[str] = []
        self.items: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "li":
            self.in_item = True
            self.href = ""
            self.parts = []
        elif self.in_item and tag == "a" and not self.href:
            self.href = dict(attrs).get("href") or ""

    def handle_data(self, data: str) -> None:
        if self.in_item:
            self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "li" and self.in_item:
            self.items.append((self.href, " ".join(self.parts)))
            self.in_item = False


def _download(url: str, attempts: int = 3) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                return response.read().decode("utf-8")
        except (OSError, urllib.error.URLError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(2**attempt)
    raise RuntimeError(f"failed to download {url}: {last_error}")


def discover_icml_volumes(as_of_year: int | None = None) -> list[PmlrVolume]:
    parser = _ArchiveParser()
    parser.feed(_download(ARCHIVE_URL))
    ceiling = as_of_year or datetime.now(UTC).year
    volumes: list[PmlrVolume] = []
    for href, label in parser.items:
        match = re.search(
            r"\bProceedings\s+of\s+ICML\s+(20\d{2})\b", label, re.IGNORECASE
        )
        volume_match = re.search(r"v(\d+)", href)
        if not match or not volume_match:
            continue
        year = int(match.group(1))
        if 2023 <= year <= ceiling:
            clean_label = re.sub(r"\s+", " ", label).strip()
            volumes.append(PmlrVolume(f"v{volume_match.group(1)}", year, clean_label))
    return sorted(volumes, key=lambda item: item.year)


def _load_bibliography(volume: PmlrVolume) -> tuple[str, str]:
    year_short = str(volume.year)[-2:]
    names = [f"icml{year_short}_clean.bib", f"icml{year_short}.bib"]
    errors: list[str] = []
    for name in names:
        url = RAW_REPOSITORY.format(volume=volume.volume, file=name)
        try:
            return _download(url), url
        except RuntimeError as exc:
            errors.append(str(exc))
    raise RuntimeError("; ".join(errors))


def _plain_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = value.replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", value).strip()


def _authors(value: str) -> list[str]:
    result: list[str] = []
    for raw in re.split(r"\s+and\s+", value or ""):
        raw = _plain_text(raw)
        if not raw:
            continue
        if "," in raw:
            family, given = (part.strip() for part in raw.split(",", 1))
            raw = f"{given} {family}".strip()
        result.append(raw)
    return result


def collect_icml(
    *, as_of_year: int | None = None, volumes: list[PmlrVolume] | None = None
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Collect complete ICML proceedings metadata from authoritative PMLR volumes."""
    try:
        import bibtexparser
    except ImportError as exc:  # pragma: no cover - exercised by installation checks
        raise RuntimeError("bibtexparser is required for ICML collection") from exc

    selected = volumes or discover_icml_volumes(as_of_year)
    collected_at = utc_now()
    run_id = f"pmlr-{collected_at.replace(':', '').replace('+00:00', 'Z')}"
    records: list[dict[str, object]] = []
    logs: list[dict[str, object]] = []

    for volume in selected:
        try:
            bib_text, source_url = _load_bibliography(volume)
            database = bibtexparser.loads(bib_text)
            proceedings = next(
                (
                    entry
                    for entry in database.entries
                    if entry.get("ENTRYTYPE", "").casefold() == "proceedings"
                ),
                {},
            )
            publication_date = proceedings.get("published", f"{volume.year}-01-01")
            publication_date = publication_date.replace("/", "-")
            count_before = len(records)
            for entry in database.entries:
                if entry.get("ENTRYTYPE", "").casefold() != "inproceedings":
                    continue
                paper_id = entry.get("ID", "").strip()
                if not paper_id:
                    continue
                authors = _authors(entry.get("author", ""))
                openreview_id = _plain_text(entry.get("openreview", ""))
                paper_url = (
                    f"https://proceedings.mlr.press/{volume.volume}/{paper_id}.html"
                )
                source_id = f"{volume.volume}:{paper_id}"
                records.append(
                    {
                        "record_id": stable_id("pmlr", source_id),
                        "source": "pmlr",
                        "source_id": source_id,
                        "title": _plain_text(entry.get("title", "")),
                        "abstract": _plain_text(entry.get("abstract", "")),
                        "authors": "; ".join(authors),
                        "author_count": len(authors),
                        "publication_date": publication_date,
                        "publication_date_basis": "proceedings-publication-date",
                        "year": volume.year,
                        "venue": "ICML",
                        "venue_track": "main",
                        "decision": "accepted",
                        "keywords": _plain_text(entry.get("keywords", "")),
                        "tldr": "",
                        "paper_url": paper_url,
                        "pdf_url": f"https://proceedings.mlr.press/{volume.volume}/{paper_id}/{paper_id}.pdf",
                        "code_url": _plain_text(entry.get("software", "")),
                        "openreview_id": openreview_id,
                        "pmlr_id": source_id,
                        "doi": _plain_text(entry.get("doi", "")),
                        "collected_at": collected_at,
                        "run_id": run_id,
                    }
                )
            logs.append(
                {
                    "run_id": run_id,
                    "collected_at": collected_at,
                    "source": "pmlr",
                    "venue": "ICML",
                    "year": volume.year,
                    "track": "main",
                    "volume": volume.volume,
                    "source_url": source_url,
                    "status": "ok",
                    "records": len(records) - count_before,
                    "error": "",
                }
            )
        except Exception as exc:
            logs.append(
                {
                    "run_id": run_id,
                    "collected_at": collected_at,
                    "source": "pmlr",
                    "venue": "ICML",
                    "year": volume.year,
                    "track": "main",
                    "volume": volume.volume,
                    "source_url": "",
                    "status": "error",
                    "records": 0,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    return records, logs
