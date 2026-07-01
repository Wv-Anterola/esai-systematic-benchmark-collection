import pytest

from esai_collection.recall import sample_recall_audit


def row(index: int, *, tier: str = "low", venue: str = "ICLR") -> dict[str, str]:
    return {
        "record_id": f"r{index}",
        "title": f"Paper {index}",
        "screening_tier": tier,
        "venue": venue,
        "year": "2025",
    }


def test_sample_recall_audit_balances_low_tier_rows() -> None:
    rows = [
        row(1, venue="ICLR"),
        row(2, venue="ICLR"),
        row(3, venue="NeurIPS"),
        row(4, venue="NeurIPS"),
        row(5, tier="high", venue="ICLR"),
    ]

    sample = sample_recall_audit(rows, size=3, seed=7)

    assert len(sample) == 3
    assert {item["audit_status"] for item in sample} == {"pending"}
    assert all(item["screening_tier"] == "low" for item in sample)
    assert {item["venue"] for item in sample} == {"ICLR", "NeurIPS"}


def test_sample_recall_audit_rejects_oversized_requests() -> None:
    with pytest.raises(ValueError, match="only 1 low-tier"):
        sample_recall_audit([row(1)], size=2)
