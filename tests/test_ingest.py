from pathlib import Path

from scripts.ingest import load_documents


def test_load_documents_reads_supported_files(tmp_path: Path) -> None:
    (tmp_path / "b.txt").write_text("text", encoding="utf-8")
    (tmp_path / "a.md").write_text("# title", encoding="utf-8")
    (tmp_path / "ignored.json").write_text("{}", encoding="utf-8")

    documents = load_documents(tmp_path)

    assert [doc.metadata["filename"] for doc in documents] == ["a.md", "b.txt"]
