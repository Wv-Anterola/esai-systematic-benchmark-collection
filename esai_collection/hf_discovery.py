from __future__ import annotations

import re
import urllib.parse
from collections.abc import Iterable
from typing import Any, Protocol

from .text import normalise_title

DEFAULT_HF_QUERIES = (
    "benchmark",
    "evaluation",
    "safety benchmark",
    "llm benchmark",
    "red teaming",
)

HF_DISCOVERY_FIELDS = [
    "query",
    "dataset_id",
    "url",
    "author",
    "downloads",
    "likes",
    "last_modified",
    "tags",
    "pipeline_tag",
    "source_record_id",
    "source_title",
    "match_reason",
    "review_status",
    "reviewer",
    "review_notes",
]


class JsonClient(Protocol):
    def get_json(
        self, url: str, *, headers: dict[str, str] | None = None
    ) -> tuple[dict[str, Any] | list[Any] | None, str]: ...


def _compact(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(str(item) for item in value if str(item).strip())
    return str(value)


def _queries_from_candidates(
    rows: Iterable[dict[str, str]], *, max_queries: int
) -> list[tuple[str, str, str, str]]:
    queries: list[tuple[str, str, str, str]] = []
    seen: set[str] = set()
    for row in rows:
        title = row.get("title", "").strip()
        if not title:
            continue
        if row.get("screening_tier") not in {"high", "medium"}:
            continue
        shortened = re.split(r"[:?]", title, maxsplit=1)[0].strip()
        candidates = [shortened, title]
        for query in candidates:
            key = normalise_title(query)
            if len(key) < 5 or key in seen:
                continue
            seen.add(key)
            queries.append(
                (
                    query,
                    row.get("record_id", ""),
                    title,
                    f"candidate-{row.get('screening_tier', '')}",
                )
            )
            break
        if len(queries) >= max_queries:
            break
    return queries


def _manual_queries(values: list[str]) -> list[tuple[str, str, str, str]]:
    output: list[tuple[str, str, str, str]] = []
    for query in values:
        query = query.strip()
        if query:
            output.append((query, "", "", "manual-query"))
    return output


def _dataset_rows(
    query: str,
    payload: dict[str, Any] | list[Any] | None,
    *,
    source_record_id: str,
    source_title: str,
    match_reason: str,
) -> list[dict[str, str]]:
    items = payload if isinstance(payload, list) else []
    rows: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        dataset_id = str(item.get("id") or item.get("modelId") or "").strip()
        if not dataset_id:
            continue
        rows.append(
            {
                "query": query,
                "dataset_id": dataset_id,
                "url": f"https://huggingface.co/datasets/{dataset_id}",
                "author": _compact(item.get("author")),
                "downloads": _compact(item.get("downloads")),
                "likes": _compact(item.get("likes")),
                "last_modified": _compact(item.get("lastModified")),
                "tags": _compact(item.get("tags")),
                "pipeline_tag": _compact(item.get("pipeline_tag")),
                "source_record_id": source_record_id,
                "source_title": source_title,
                "match_reason": match_reason,
                "review_status": "pending",
                "reviewer": "",
                "review_notes": "",
            }
        )
    return rows


def discover_hf_datasets(
    *,
    client: JsonClient,
    candidates: Iterable[dict[str, str]] | None = None,
    queries: list[str] | None = None,
    max_candidate_queries: int = 50,
    limit_per_query: int = 10,
) -> list[dict[str, str]]:
    query_specs = _manual_queries(queries or list(DEFAULT_HF_QUERIES))
    if candidates is not None and max_candidate_queries > 0:
        query_specs.extend(
            _queries_from_candidates(candidates, max_queries=max_candidate_queries)
        )
    output: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for query, source_record_id, source_title, match_reason in query_specs:
        url = (
            "https://huggingface.co/api/datasets?"
            f"search={urllib.parse.quote(query)}&limit={limit_per_query}&full=true"
        )
        payload, error = client.get_json(url)
        if error:
            output.append(
                {
                    "query": query,
                    "dataset_id": "",
                    "url": "",
                    "author": "",
                    "downloads": "",
                    "likes": "",
                    "last_modified": "",
                    "tags": "",
                    "pipeline_tag": "",
                    "source_record_id": source_record_id,
                    "source_title": source_title,
                    "match_reason": f"{match_reason}; error: {error}",
                    "review_status": "pending",
                    "reviewer": "",
                    "review_notes": "",
                }
            )
            continue
        for row in _dataset_rows(
            query,
            payload,
            source_record_id=source_record_id,
            source_title=source_title,
            match_reason=match_reason,
        ):
            key = (row["query"].casefold(), row["dataset_id"].casefold())
            if key in seen:
                continue
            seen.add(key)
            output.append(row)
    return output
