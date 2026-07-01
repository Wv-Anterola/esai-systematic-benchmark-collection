from typing import Any

from esai_collection.hf_discovery import discover_hf_datasets


class FakeClient:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.urls: list[str] = []

    def get_json(
        self, url: str, *, headers: dict[str, str] | None = None
    ) -> tuple[dict[str, Any] | list[Any] | None, str]:
        self.urls.append(url)
        if self.fail:
            return None, "network unavailable"
        return (
            [
                {
                    "id": "org/safety-bench",
                    "author": "org",
                    "downloads": 123,
                    "likes": 4,
                    "lastModified": "2026-01-01T00:00:00.000Z",
                    "tags": ["benchmark", "safety"],
                    "pipeline_tag": "text-generation",
                }
            ],
            "",
        )


def test_discover_hf_datasets_uses_manual_and_candidate_queries() -> None:
    client = FakeClient()
    candidates = [
        {
            "record_id": "r1",
            "title": "SafetyBench: A Benchmark for Safety",
            "screening_tier": "high",
        },
        {
            "record_id": "r2",
            "title": "Low Tier Mention",
            "screening_tier": "low",
        },
    ]

    rows = discover_hf_datasets(
        client=client,
        candidates=candidates,
        queries=["red teaming"],
        max_candidate_queries=1,
        limit_per_query=2,
    )

    assert len(rows) == 2
    assert rows[0]["query"] == "red teaming"
    assert rows[0]["dataset_id"] == "org/safety-bench"
    assert rows[0]["review_status"] == "pending"
    assert rows[1]["query"] == "SafetyBench"
    assert rows[1]["source_record_id"] == "r1"
    assert "limit=2" in client.urls[0]


def test_discover_hf_datasets_records_query_errors() -> None:
    rows = discover_hf_datasets(
        client=FakeClient(fail=True),
        queries=["benchmark"],
        max_candidate_queries=0,
    )

    assert rows[0]["dataset_id"] == ""
    assert "network unavailable" in rows[0]["match_reason"]
