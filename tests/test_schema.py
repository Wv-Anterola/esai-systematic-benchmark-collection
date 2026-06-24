from esai_collection.schema import default_openreview_venues


def test_default_venues_enforce_cutoff_policy() -> None:
    specs = default_openreview_venues(2025)
    editions = {(spec.venue, spec.year, spec.track) for spec in specs}

    assert ("NeurIPS", 2022, "main") in editions
    assert ("ICLR", 2022, "main") not in editions
    assert ("ICLR", 2023, "main") in editions
    assert ("COLM", 2023, "main") not in editions
    assert ("COLM", 2024, "main") in editions
    assert all(year <= 2025 for _, year, _ in editions)


def test_supported_venues_exclude_acl() -> None:
    specs = default_openreview_venues(2026)
    assert {spec.venue for spec in specs} == {"ICLR", "NeurIPS", "COLM"}
