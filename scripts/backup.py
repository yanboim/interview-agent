import argparse
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import httpx
from sqlalchemy.engine import make_url

from app.config import get_settings


def dump_postgres(database_url: str, output: Path) -> None:
    clean_url = database_url.replace("+psycopg", "")
    if shutil.which("pg_dump"):
        subprocess.run(
            ["pg_dump", "--format=custom", "--file", str(output), clean_url],
            check=True,
        )
        return

    parsed = make_url(clean_url)
    if not parsed.username or not parsed.database:
        raise RuntimeError("DATABASE_URL 缺少 PostgreSQL 用户名或数据库名")
    with output.open("wb") as dump_file:
        subprocess.run(
            [
                "docker",
                "exec",
                "interview-postgres",
                "pg_dump",
                "--format=custom",
                "--username",
                parsed.username,
                parsed.database,
            ],
            check=True,
            stdout=dump_file,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Back up PostgreSQL and Qdrant.")
    parser.add_argument("--output", type=Path, default=Path("backups"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = args.output / stamp
    plan = {
        "target": str(target),
        "database_configured": bool(settings.database_url),
        "qdrant_collection": settings.qdrant_collection,
        "qdrant_url": settings.qdrant_url,
    }
    if args.dry_run:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return
    if not settings.database_url.startswith("postgresql"):
        raise RuntimeError("生产备份要求 DATABASE_URL 指向 PostgreSQL")
    target.mkdir(parents=True, exist_ok=False)
    dump_postgres(settings.database_url, target / "postgres.dump")
    response = httpx.post(
        f"{settings.qdrant_url}/collections/"
        f"{settings.qdrant_collection}/snapshots",
        timeout=60,
    )
    response.raise_for_status()
    metadata = {
        **plan,
        "created_at": datetime.now(UTC).isoformat(),
        "qdrant_snapshot": response.json(),
    }
    (target / "manifest.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(target)


if __name__ == "__main__":
    main()
