from __future__ import annotations

from pathlib import Path

from esai_collection.acl_source import collect_acl

VENUE_ACL = """\
acronym: ACL
name: Annual Meeting of the Association for Computational Linguistics
is_toplevel: true
is_acl: true
"""

VENUE_FINDINGS = """\
acronym: Findings
name: Findings of the Association for Computational Linguistics
is_toplevel: true
is_acl: true
"""

VENUE_WS = """\
acronym: WS
name: Workshop
is_toplevel: false
is_acl: true
"""

# One in-scope ACL main paper, one in-scope Findings paper, and a workshop volume
# (non-major) plus a pre-cutoff volume that must both be excluded.
ACL_XML = """\
<collection id="2024.acl">
  <volume id="long">
    <meta>
      <year>2024</year>
      <month>August</month>
      <venue>acl</venue>
    </meta>
    <paper id="1">
      <title>A <fixed-case>S</fixed-case>afety Benchmark</title>
      <author><first>Ada</first><last>Smith</last></author>
      <author><first>James</first><last>Doe</last></author>
      <abstract>We introduce a benchmark for safety.</abstract>
      <url>2024.acl-long.1</url>
      <doi>10.18653/v1/2024.acl-long.1</doi>
    </paper>
    <paper id="2">
      <author><first>No</first><last>Title</last></author>
      <url>2024.acl-long.2</url>
    </paper>
  </volume>
  <volume id="findings">
    <meta>
      <year>2024</year>
      <month>August</month>
      <venue>findings</venue>
      <venue>acl</venue>
    </meta>
    <paper id="9">
      <title>A Findings Dataset</title>
      <author><first>Mary</first><last>Roe</last></author>
      <url>2024.findings-acl.9</url>
    </paper>
  </volume>
</collection>
"""

WS_XML = """\
<collection id="2024.someworkshop">
  <volume id="1">
    <meta>
      <year>2024</year>
      <month>August</month>
      <venue>ws</venue>
    </meta>
    <paper id="1">
      <title>A Workshop Benchmark</title>
      <url>2024.someworkshop.1</url>
    </paper>
  </volume>
</collection>
"""

OLD_XML = """\
<collection id="2021.acl">
  <volume id="long">
    <meta>
      <year>2021</year>
      <month>August</month>
      <venue>acl</venue>
    </meta>
    <paper id="1">
      <title>An Old Benchmark</title>
      <url>2021.acl-long.1</url>
    </paper>
  </volume>
</collection>
"""


def _fixture_data_dir(tmp_path: Path) -> Path:
    data_dir = tmp_path / "data"
    xml_dir = data_dir / "xml"
    venue_dir = data_dir / "yaml" / "venues"
    xml_dir.mkdir(parents=True)
    venue_dir.mkdir(parents=True)
    (xml_dir / "2024.acl.xml").write_text(ACL_XML, encoding="utf-8")
    (xml_dir / "2024.someworkshop.xml").write_text(WS_XML, encoding="utf-8")
    (xml_dir / "2021.acl.xml").write_text(OLD_XML, encoding="utf-8")
    (venue_dir / "acl.yaml").write_text(VENUE_ACL, encoding="utf-8")
    (venue_dir / "findings.yaml").write_text(VENUE_FINDINGS, encoding="utf-8")
    (venue_dir / "ws.yaml").write_text(VENUE_WS, encoding="utf-8")
    return data_dir


def test_collect_acl_emits_shared_schema(tmp_path: Path) -> None:
    records, logs = collect_acl(data_dir=_fixture_data_dir(tmp_path), as_of_year=2024)

    titles = {record["title"] for record in records}
    # Major venues only; the workshop and the pre-cutoff volume are excluded, and
    # the untitled paper is dropped.
    assert titles == {"A Safety Benchmark", "A Findings Dataset"}

    paper = next(r for r in records if r["title"] == "A Safety Benchmark")
    assert paper["source"] == "acl"
    assert paper["source_id"] == "2024.acl-long.1"
    assert paper["authors"] == "Ada Smith; James Doe"
    assert paper["author_count"] == 2
    assert paper["venue"] == "ACL"
    assert paper["venue_track"] == "main"
    assert paper["decision"] == "accepted"
    assert paper["publication_date"] == "2024-08-01"
    assert paper["publication_date_basis"] == "anthology-volume-month"
    assert paper["year"] == 2024
    assert paper["paper_url"] == "https://aclanthology.org/2024.acl-long.1/"
    assert paper["pdf_url"] == "https://aclanthology.org/2024.acl-long.1.pdf"
    assert paper["doi"] == "10.18653/v1/2024.acl-long.1"

    findings = next(r for r in records if r["title"] == "A Findings Dataset")
    assert findings["venue"] == "Findings"
    assert findings["venue_track"] == "findings"

    # One ok log per collection file that yielded in-scope records; the workshop
    # and pre-cutoff files produce none.
    assert [log["venue"] for log in logs] == ["2024.acl"]
    assert logs[0]["status"] == "ok"
    assert logs[0]["records"] == 2


def test_collect_acl_reports_parse_errors(tmp_path: Path) -> None:
    data_dir = _fixture_data_dir(tmp_path)
    (data_dir / "xml" / "2024.broken.xml").write_text(
        "<collection><vol", encoding="utf-8"
    )

    records, logs = collect_acl(data_dir=data_dir, as_of_year=2024)

    error_logs = [log for log in logs if log["status"] == "error"]
    assert len(error_logs) == 1
    assert error_logs[0]["venue"] == "2024.broken"
    assert records  # valid files are still collected despite the broken one
