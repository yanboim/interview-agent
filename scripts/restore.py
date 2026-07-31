"""经操作员显式确认后恢复数据库与用户文件，并执行恢复后校验。"""

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from sqlalchemy.engine import make_url

from app.config import get_settings


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_user_files(backup: Path, manifest: dict[str, object]) -> int:
    metadata = manifest.get("user_files")
    if not isinstance(metadata, dict) or not metadata.get("included"):
        return 0
    source = (backup / "user-files").resolve()
    files = metadata.get("files")
    if not isinstance(files, list):
        raise RuntimeError("用户文件备份清单无效")
    for item in files:
        if not isinstance(item, dict):
            raise RuntimeError("用户文件备份条目无效")
        relative = item.get("path")
        if not isinstance(relative, str) or not relative:
            raise RuntimeError("用户文件备份路径无效")
        candidate = (source / relative).resolve()
        if source not in candidate.parents:
            raise RuntimeError("用户文件备份包含越界路径")
        if (
            not candidate.is_file()
            or candidate.stat().st_size != item.get("size_bytes")
            or sha256_file(candidate) != item.get("sha256")
        ):
            raise RuntimeError(f"用户文件备份校验失败：{relative}")
    return len(files)


def restore_user_files(backup: Path, destination: Path) -> None:
    source = backup / "user-files"
    destination_parent = destination.resolve().parent
    destination_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".user-files-restore-", dir=destination_parent
    ) as temporary:
        staged = Path(temporary) / "data"
        shutil.copytree(source, staged)
        if destination.exists():
            if not destination.is_dir():
                raise RuntimeError(f"用户文件恢复目标不是目录：{destination}")
            shutil.rmtree(destination)
        staged.replace(destination)


def restore_postgres(database_url: str, dump_path: Path) -> None:
    clean_url = database_url.replace("+psycopg", "")
    if shutil.which("pg_restore"):
        subprocess.run(
            [
                "pg_restore",
                "--clean",
                "--if-exists",
                "--no-owner",
                "--dbname",
                clean_url,
                str(dump_path),
            ],
            check=True,
        )
        return

    parsed = make_url(clean_url)
    if not parsed.username or not parsed.database:
        raise RuntimeError("DATABASE_URL 缺少 PostgreSQL 用户名或数据库名")
    with dump_path.open("rb") as dump_file:
        subprocess.run(
            [
                "docker",
                "exec",
                "--interactive",
                "interview-postgres",
                "pg_restore",
                "--clean",
                "--if-exists",
                "--no-owner",
                "--username",
                parsed.username,
                "--dbname",
                parsed.database,
            ],
            check=True,
            stdin=dump_file,
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate or restore PostgreSQL and user-file backup."
    )
    parser.add_argument("backup", type=Path)
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    manifest_path = args.backup / "manifest.json"
    dump_path = args.backup / "postgres.dump"
    if not manifest_path.exists() or not dump_path.exists():
        raise RuntimeError("备份目录缺少 manifest.json 或 postgres.dump")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    user_file_count = validate_user_files(args.backup, manifest)
    if not args.confirm:
        print(
            json.dumps(
                {
                    "status": "validation_only",
                    "created_at": manifest.get("created_at"),
                    "database_target_configured": bool(settings.database_url),
                    "validated_user_files": user_file_count,
                    "hint": "确认维护窗口后添加 --confirm 执行数据库恢复",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    if not settings.database_url.startswith("postgresql"):
        raise RuntimeError("恢复要求 DATABASE_URL 指向 PostgreSQL")
    restore_postgres(settings.database_url, dump_path)
    user_files = manifest.get("user_files")
    if isinstance(user_files, dict) and user_files.get("included"):
        restore_user_files(args.backup, settings.user_files_dir)
    print(
        "PostgreSQL 与用户文件恢复完成；"
        "Qdrant snapshot 请按 manifest 手动确认后恢复。"
    )


if __name__ == "__main__":
    main()
