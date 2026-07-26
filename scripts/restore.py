import argparse
import json
import shutil
import subprocess
from pathlib import Path

from sqlalchemy.engine import make_url

from app.config import get_settings


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
    parser = argparse.ArgumentParser(description="Restore PostgreSQL backup.")
    parser.add_argument("backup", type=Path)
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    manifest_path = args.backup / "manifest.json"
    dump_path = args.backup / "postgres.dump"
    if not manifest_path.exists() or not dump_path.exists():
        raise RuntimeError("备份目录缺少 manifest.json 或 postgres.dump")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not args.confirm:
        print(
            json.dumps(
                {
                    "status": "validation_only",
                    "created_at": manifest.get("created_at"),
                    "database_target_configured": bool(settings.database_url),
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
    print("PostgreSQL 恢复完成；Qdrant snapshot 请按 manifest 手动确认后恢复。")


if __name__ == "__main__":
    main()
