"""备份与恢复脚本的测试。"""

import json
from pathlib import Path

import pytest

from scripts.backup import backup_user_files
from scripts.restore import restore_user_files, validate_user_files


def test_user_files_backup_validates_and_restores(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source_file = source / "owner-hash" / "resume.docx"
    source_file.parent.mkdir(parents=True)
    source_file.write_bytes(b"private resume")
    backup = tmp_path / "backup"
    backup.mkdir()

    metadata = backup_user_files(source, backup)
    manifest = {"user_files": metadata}

    assert validate_user_files(backup, manifest) == 1
    restored = tmp_path / "restored"
    restore_user_files(backup, restored)
    assert (restored / "owner-hash" / "resume.docx").read_bytes() == b"private resume"


def test_user_files_validation_rejects_tampering(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "resume.pdf").write_bytes(b"%PDF-original")
    backup = tmp_path / "backup"
    backup.mkdir()
    manifest = {"user_files": backup_user_files(source, backup)}
    (backup / "user-files" / "resume.pdf").write_bytes(b"%PDF-modified")

    with pytest.raises(RuntimeError, match="校验失败"):
        validate_user_files(backup, manifest)


def test_user_files_validation_rejects_path_escape(tmp_path: Path) -> None:
    backup = tmp_path / "backup"
    backup.mkdir()
    manifest = {
        "user_files": {
            "included": True,
            "files": [
                {"path": "../outside", "size_bytes": 0, "sha256": "invalid"}
            ],
        }
    }

    with pytest.raises(RuntimeError, match="越界路径"):
        validate_user_files(backup, json.loads(json.dumps(manifest)))
