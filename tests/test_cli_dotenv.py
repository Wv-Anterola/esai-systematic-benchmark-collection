from pathlib import Path

from esai_collection.cli import load_dotenv


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_load_dotenv_sets_missing_and_strips_quotes(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OPENREVIEW_USERNAME", raising=False)
    monkeypatch.delenv("OPENREVIEW_PASSWORD", raising=False)
    env = _write(
        tmp_path / ".env",
        "# comment\n\nOPENREVIEW_USERNAME='you@example.com'\n"
        'OPENREVIEW_PASSWORD="p@ss=w#rd"\n',
    )
    load_dotenv(env)
    import os

    assert os.environ["OPENREVIEW_USERNAME"] == "you@example.com"
    # split only on the first '=' so passwords may contain '='
    assert os.environ["OPENREVIEW_PASSWORD"] == "p@ss=w#rd"


def test_load_dotenv_does_not_override_existing(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPENREVIEW_USERNAME", "real@env.com")
    env = _write(tmp_path / ".env", "OPENREVIEW_USERNAME='file@example.com'\n")
    load_dotenv(env)
    import os

    assert os.environ["OPENREVIEW_USERNAME"] == "real@env.com"


def test_load_dotenv_missing_file_is_noop(tmp_path) -> None:
    load_dotenv(tmp_path / "nope.env")  # must not raise
