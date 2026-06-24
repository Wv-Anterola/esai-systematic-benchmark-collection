from types import SimpleNamespace

from esai_collection.openreview_source import collect_openreview
from esai_collection.schema import VenueSpec


class V2Client:
    def get_all_notes(self, **kwargs):
        assert kwargs == {"content": {"venueid": "ICLR.cc/2025/Conference"}}
        return [
            SimpleNamespace(
                id="forum-1",
                content={
                    "title": {"value": "A Safety Benchmark"},
                    "abstract": {"value": "We introduce a benchmark."},
                    "authors": {"value": ["Ada Smith", "James Doe"]},
                    "venue": {"value": "ICLR 2025 Poster"},
                    "pdf": {"value": "/pdf/forum-1"},
                },
            )
        ]


class UnusedV1Client:
    def get_all_notes(self, **kwargs):
        raise AssertionError("v1 should not be used after a successful v2 query")


def test_collect_openreview_normalises_v2_records() -> None:
    records, logs = collect_openreview(
        specs=[VenueSpec("ICLR", 2025, "main", ("ICLR.cc/2025/Conference",))],
        clients=(V2Client(), UnusedV1Client()),
    )

    assert len(records) == 1
    assert records[0]["authors"] == "Ada Smith; James Doe"
    assert records[0]["author_count"] == 2
    assert records[0]["publication_date"] == "2025-05-01"
    assert records[0]["publication_date_basis"] == "venue-edition-estimate"
    assert records[0]["paper_url"].endswith("forum?id=forum-1")
    assert logs[0]["status"] == "ok"
    assert logs[0]["source_api"] == "v2"


class EmptyV2Client:
    def get_all_notes(self, **kwargs):
        return []


class AcceptedV1Client:
    def get_all_notes(self, **kwargs):
        return [
            SimpleNamespace(
                id="legacy-1",
                content={
                    "title": "Legacy Benchmark",
                    "abstract": "We introduce a benchmark.",
                    "authors": ["Ada Smith"],
                },
                details={
                    "directReplies": [
                        {
                            "invitation": "ICLR.cc/2023/Conference/-/Decision",
                            "content": {"decision": "Accept (Poster)"},
                        }
                    ],
                    "original": {"content": {}},
                },
            )
        ]


def test_collect_openreview_falls_back_to_accepted_v1_submissions() -> None:
    records, logs = collect_openreview(
        specs=[VenueSpec("ICLR", 2023, "main", ("ICLR.cc/2023/Conference",))],
        clients=(EmptyV2Client(), AcceptedV1Client()),
    )

    assert [record["source_id"] for record in records] == ["legacy-1"]
    assert logs[0]["source_api"] == "v1"
    assert logs[0]["status"] == "ok"
