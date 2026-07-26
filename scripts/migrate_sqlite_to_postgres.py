import argparse
from pathlib import Path

from sqlalchemy import create_engine, func, insert, select

from app.database import (
    chat_turns,
    conversations,
    interview_turns,
    interviews,
    learning_tasks,
    messages,
    normalize_database_url,
)


TABLES = (
    conversations,
    interviews,
    messages,
    chat_turns,
    interview_turns,
    learning_tasks,
)


def row_count(connection, table) -> int:
    return int(connection.execute(select(func.count()).select_from(table)).scalar_one())


def migrate(source_url: str, target_url: str) -> dict[str, int]:
    source_engine = create_engine(source_url)
    target_engine = create_engine(target_url, pool_pre_ping=True)
    counts: dict[str, int] = {}

    with source_engine.connect() as source, target_engine.begin() as target:
        nonempty = {
            table.name: row_count(target, table)
            for table in TABLES
            if row_count(target, table)
        }
        if nonempty:
            raise RuntimeError(
                f"目标数据库不是空库，已停止迁移：{nonempty}"
            )

        for table in TABLES:
            rows = [
                dict(row)
                for row in source.execute(select(table)).mappings().all()
            ]
            if table in (messages, interview_turns):
                for row in rows:
                    row.pop("id", None)
            if rows:
                target.execute(insert(table), rows)
            counts[table.name] = len(rows)

        for table in TABLES:
            migrated = row_count(target, table)
            if migrated != counts[table.name]:
                raise RuntimeError(
                    f"{table.name} 数量校验失败："
                    f"expected={counts[table.name]}, actual={migrated}"
                )
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate local SQLite data into an empty PostgreSQL schema."
    )
    parser.add_argument(
        "--source",
        default="data/interview-agent.db",
        help="SQLite path or SQLAlchemy URL.",
    )
    parser.add_argument(
        "--target",
        required=True,
        help="Target PostgreSQL SQLAlchemy URL.",
    )
    args = parser.parse_args()
    source = (
        normalize_database_url(Path(args.source))
        if "://" not in args.source
        else args.source
    )
    counts = migrate(source, args.target)
    print("SQLite -> PostgreSQL 迁移完成")
    for table_name, count in counts.items():
        print(f"{table_name}: {count}")


if __name__ == "__main__":
    main()
