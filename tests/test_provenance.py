import json

from esai_collection.provenance import sha256_file, write_manifest


def test_manifest_hashes_inputs_and_outputs(tmp_path) -> None:
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    manifest = tmp_path / "manifest.json"
    source.write_text("input\n", encoding="utf-8")
    output.write_text("output\n", encoding="utf-8")

    write_manifest(
        manifest,
        command="test",
        inputs=[source],
        outputs=[output],
        counts={"records": 1},
    )

    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["command"] == "test"
    assert payload["inputs"][0]["sha256"] == sha256_file(source)
    assert payload["outputs"][0]["sha256"] == sha256_file(output)
