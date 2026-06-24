from esai_collection import pmlr_source
from esai_collection.pmlr_source import PmlrVolume

ARCHIVE = """
<ul>
  <li><a href="v202"><b>Volume 202</b></a> Proceedings of ICML 2023</li>
  <li><a href="v235"><b>Volume 235</b></a> Proceedings of ICML 2024</li>
  <li><a href="v251"><b>Volume 251</b></a> Proceedings of GRaM at ICML 2024</li>
  <li><a href="v999"><b>Volume 999</b></a> Unrelated Conference 2025</li>
</ul>
"""

BIBLIOGRAPHY = r"""
@Proceedings{ICML-2023,
  name = {International Conference on Machine Learning},
  year = {2023},
  published = {2023-07-23}
}
@InProceedings{smith23a,
  title = {A Benchmark for Reliable Models},
  openreview = {abc123},
  author = {Smith, Ada and Doe, James},
  abstract = {We introduce a benchmark for reliability.},
  software = {https://github.com/example/reliable}
}
"""


def test_discover_icml_volumes(monkeypatch) -> None:
    monkeypatch.setattr(pmlr_source, "_download", lambda _: ARCHIVE)
    volumes = pmlr_source.discover_icml_volumes(2023)
    assert volumes == [PmlrVolume("v202", 2023, "Volume 202 Proceedings of ICML 2023")]


def test_collect_icml_normalises_bibliography(monkeypatch) -> None:
    monkeypatch.setattr(
        pmlr_source,
        "_load_bibliography",
        lambda volume: (BIBLIOGRAPHY, "https://example.test/icml23.bib"),
    )
    records, logs = pmlr_source.collect_icml(
        volumes=[PmlrVolume("v202", 2023, "ICML 2023")]
    )

    assert len(records) == 1
    assert records[0]["title"] == "A Benchmark for Reliable Models"
    assert records[0]["authors"] == "Ada Smith; James Doe"
    assert records[0]["openreview_id"] == "abc123"
    assert records[0]["publication_date"] == "2023-07-23"
    assert logs[0]["status"] == "ok"
