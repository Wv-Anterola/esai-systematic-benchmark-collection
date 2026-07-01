from __future__ import annotations

import os
import urllib.parse
from collections.abc import Iterable
from typing import Any, Protocol

from .text import normalise_title

SEMANTIC_SCHOLAR_FIELDS = ",".join(
    [
        "paperId",
        "url",
        "title",
        "abstract",
        "venue",
        "year",
        "publicationDate",
        "externalIds",
        "openAccessPdf",
        "citationCount",
    ]
)
OPENALEX_SELECT = ",".join(
    [
        "id",
        "doi",
        "title",
        "display_name",
        "publication_date",
        "primary_location",
        "cited_by_count",
        "concepts",
        "abstract_inverted_index",
    ]
)


class JsonClient(Protocol):
    def get_json(
        self, url: str, *, headers: dict[str, str] | None = None
    ) -> tuple[dict[str, Any] | list[Any] | None, str]: ...


ENRICHMENT_FIELDS = [
    "record_id",
    "title",
    "doi",
    "query_key",
    "semantic_scholar_status",
    "semantic_scholar_id",
    "semantic_scholar_url",
    "semantic_scholar_title",
    "semantic_scholar_year",
    "semantic_scholar_publication_date",
    "semantic_scholar_venue",
    "semantic_scholar_citation_count",
    "semantic_scholar_open_access_pdf",
    "semantic_scholar_abstract",
    "semantic_scholar_external_ids",
    "openalex_status",
    "openalex_id",
    "openalex_url",
    "openalex_title",
    "openalex_publication_date",
    "openalex_source",
    "openalex_doi",
    "openalex_cited_by_count",
    "openalex_concepts",
    "openalex_abstract",
    "enrichment_notes",
]


def _quote(value: str) -> str:
    return urllib.parse.quote(value.strip(), safe="")


def _compact(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str | int | float | bool):
        return str(value)
    if isinstance(value, list):
        return "; ".join(_compact(item) for item in value if _compact(item))
    if isinstance(value, dict):
        return "; ".join(
            f"{key}={_compact(item)}"
            for key, item in sorted(value.items())
            if _compact(item)
        )
    return str(value)


def _abstract_from_inverted_index(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    words: list[tuple[int, str]] = []
    for word, positions in value.items():
        if not isinstance(positions, list):
            continue
        for position in positions:
            if isinstance(position, int):
                words.append((position, str(word)))
    return " ".join(word for _, word in sorted(words))


def _primary_source(work: dict[str, Any]) -> str:
    location = work.get("primary_location")
    if not isinstance(location, dict):
        return ""
    source = location.get("source")
    if not isinstance(source, dict):
        return ""
    return str(source.get("display_name") or source.get("id") or "")


def _concepts(work: dict[str, Any]) -> str:
    concepts = work.get("concepts")
    if not isinstance(concepts, list):
        return ""
    labels: list[str] = []
    for concept in concepts[:8]:
        if isinstance(concept, dict) and concept.get("display_name"):
            score = concept.get("score")
            if isinstance(score, int | float):
                labels.append(f"{concept['display_name']} ({score:.2f})")
            else:
                labels.append(str(concept["display_name"]))
    return "; ".join(labels)


def semantic_scholar_url(row: dict[str, str]) -> tuple[str, str]:
    doi = row.get("doi", "").strip()
    if doi:
        return (
            "https://api.semanticscholar.org/graph/v1/paper/"
            f"DOI:{_quote(doi)}?fields={SEMANTIC_SCHOLAR_FIELDS}",
            f"doi:{doi.casefold()}",
        )
    title = row.get("title", "").strip()
    return (
        "https://api.semanticscholar.org/graph/v1/paper/search?"
        f"query={_quote(title)}&limit=1&fields={SEMANTIC_SCHOLAR_FIELDS}",
        f"title:{normalise_title(title)}",
    )


def openalex_url(row: dict[str, str], api_key: str | None = None) -> tuple[str, str]:
    doi = row.get("doi", "").strip()
    params = f"select={OPENALEX_SELECT}"
    if api_key:
        params += f"&api_key={_quote(api_key)}"
    if doi:
        return (
            f"https://api.openalex.org/works/https://doi.org/{_quote(doi)}?{params}",
            f"doi:{doi.casefold()}",
        )
    title = row.get("title", "").strip()
    return (
        f"https://api.openalex.org/works?search={_quote(title)}&per-page=1&{params}",
        f"title:{normalise_title(title)}",
    )


def _pick_semantic_scholar(
    payload: dict[str, Any] | list[Any] | None,
) -> dict[str, Any]:
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        first = payload["data"][0] if payload["data"] else {}
        return first if isinstance(first, dict) else {}
    return payload if isinstance(payload, dict) else {}


def _pick_openalex(payload: dict[str, Any] | list[Any] | None) -> dict[str, Any]:
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        first = payload["results"][0] if payload["results"] else {}
        return first if isinstance(first, dict) else {}
    return payload if isinstance(payload, dict) else {}


def enrich_records(
    rows: Iterable[dict[str, str]],
    *,
    client: JsonClient,
    providers: set[str] | None = None,
    limit: int | None = None,
    semantic_scholar_api_key: str | None = None,
    openalex_api_key: str | None = None,
) -> list[dict[str, str]]:
    active = providers or {"semantic-scholar", "openalex"}
    semantic_scholar_api_key = semantic_scholar_api_key or os.environ.get(
        "SEMANTIC_SCHOLAR_API_KEY"
    )
    openalex_api_key = openalex_api_key or os.environ.get("OPENALEX_API_KEY")
    output: list[dict[str, str]] = []
    for index, row in enumerate(rows):
        if limit is not None and index >= limit:
            break
        item = {field: "" for field in ENRICHMENT_FIELDS}
        item.update(
            {
                "record_id": row.get("record_id", ""),
                "title": row.get("title", ""),
                "doi": row.get("doi", ""),
            }
        )
        notes: list[str] = []
        query_keys: list[str] = []
        if "semantic-scholar" in active:
            url, query_key = semantic_scholar_url(row)
            query_keys.append(query_key)
            headers = (
                {"x-api-key": semantic_scholar_api_key}
                if semantic_scholar_api_key
                else None
            )
            payload, error = client.get_json(url, headers=headers)
            paper = _pick_semantic_scholar(payload)
            item["semantic_scholar_status"] = (
                "error" if error else ("ok" if paper else "empty")
            )
            if error:
                notes.append(f"semantic-scholar: {error}")
            item.update(
                {
                    "semantic_scholar_id": _compact(paper.get("paperId")),
                    "semantic_scholar_url": _compact(paper.get("url")),
                    "semantic_scholar_title": _compact(paper.get("title")),
                    "semantic_scholar_year": _compact(paper.get("year")),
                    "semantic_scholar_publication_date": _compact(
                        paper.get("publicationDate")
                    ),
                    "semantic_scholar_venue": _compact(paper.get("venue")),
                    "semantic_scholar_citation_count": _compact(
                        paper.get("citationCount")
                    ),
                    "semantic_scholar_open_access_pdf": _compact(
                        (paper.get("openAccessPdf") or {}).get("url")
                        if isinstance(paper.get("openAccessPdf"), dict)
                        else ""
                    ),
                    "semantic_scholar_abstract": _compact(paper.get("abstract")),
                    "semantic_scholar_external_ids": _compact(paper.get("externalIds")),
                }
            )
        if "openalex" in active:
            url, query_key = openalex_url(row, openalex_api_key)
            query_keys.append(query_key)
            payload, error = client.get_json(url)
            work = _pick_openalex(payload)
            item["openalex_status"] = "error" if error else ("ok" if work else "empty")
            if error:
                notes.append(f"openalex: {error}")
            item.update(
                {
                    "openalex_id": _compact(work.get("id")),
                    "openalex_url": _compact(work.get("id")),
                    "openalex_title": _compact(
                        work.get("display_name") or work.get("title")
                    ),
                    "openalex_publication_date": _compact(work.get("publication_date")),
                    "openalex_source": _primary_source(work),
                    "openalex_doi": _compact(work.get("doi")),
                    "openalex_cited_by_count": _compact(work.get("cited_by_count")),
                    "openalex_concepts": _concepts(work),
                    "openalex_abstract": _abstract_from_inverted_index(
                        work.get("abstract_inverted_index")
                    ),
                }
            )
        item["query_key"] = " || ".join(sorted(set(query_keys)))
        item["enrichment_notes"] = " | ".join(notes)
        output.append(item)
    return output
