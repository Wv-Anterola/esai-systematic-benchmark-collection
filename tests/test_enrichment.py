from typing import Any

from esai_collection.enrichment import (
    enrich_records,
    openalex_url,
    semantic_scholar_url,
)


class FakeClient:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def get_json(
        self, url: str, *, headers: dict[str, str] | None = None
    ) -> tuple[dict[str, Any] | list[Any] | None, str]:
        self.urls.append(url)
        if "semanticscholar" in url:
            return (
                {
                    "paperId": "s2-1",
                    "url": "https://semanticscholar.org/paper/s2-1",
                    "title": "Safety Benchmark",
                    "year": 2025,
                    "publicationDate": "2025-05-01",
                    "venue": "ICLR",
                    "citationCount": 12,
                    "openAccessPdf": {"url": "https://example.test/paper.pdf"},
                    "abstract": "A benchmark paper.",
                    "externalIds": {"DOI": "10.123/test"},
                },
                "",
            )
        return (
            {
                "id": "https://openalex.org/W1",
                "doi": "https://doi.org/10.123/test",
                "display_name": "Safety Benchmark",
                "publication_date": "2025-05-01",
                "primary_location": {"source": {"display_name": "ICLR"}},
                "cited_by_count": 5,
                "concepts": [{"display_name": "Artificial intelligence", "score": 0.9}],
                "abstract_inverted_index": {
                    "A": [0],
                    "benchmark": [1],
                    "paper": [2],
                },
            },
            "",
        )


def test_provider_urls_prefer_doi() -> None:
    row = {"title": "Safety Benchmark", "doi": "10.123/test"}
    semantic_url, semantic_key = semantic_scholar_url(row)
    openalex, openalex_key = openalex_url(row, "key")

    assert "DOI:10.123%2Ftest" in semantic_url
    assert semantic_key == "doi:10.123/test"
    assert "https%3A" not in openalex
    assert "10.123%2Ftest" in openalex
    assert "api_key=key" in openalex
    assert openalex_key == "doi:10.123/test"


def test_enrich_records_parses_semantic_scholar_and_openalex() -> None:
    client = FakeClient()
    rows = [{"record_id": "r1", "title": "Safety Benchmark", "doi": "10.123/test"}]
    enriched = enrich_records(rows, client=client)

    assert len(enriched) == 1
    row = enriched[0]
    assert row["semantic_scholar_status"] == "ok"
    assert row["semantic_scholar_id"] == "s2-1"
    assert row["semantic_scholar_open_access_pdf"] == "https://example.test/paper.pdf"
    assert row["openalex_status"] == "ok"
    assert row["openalex_source"] == "ICLR"
    assert row["openalex_abstract"] == "A benchmark paper"
    assert len(client.urls) == 2


def test_enrich_records_can_run_one_provider() -> None:
    client = FakeClient()
    rows = [{"record_id": "r1", "title": "Safety Benchmark", "doi": ""}]
    enriched = enrich_records(rows, client=client, providers={"semantic-scholar"})

    assert enriched[0]["semantic_scholar_status"] == "ok"
    assert enriched[0]["openalex_status"] == ""
    assert len(client.urls) == 1
