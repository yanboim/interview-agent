"""Run every Alembic revision against a fresh, disposable SQLite database."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile

from alembic import command
from alembic.config import Config


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    descriptor, database_path = tempfile.mkstemp(
        prefix="interview-agent-migration-",
        suffix=".db",
    )
    os.close(descriptor)
    previous_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = f"sqlite:///{database_path}"
    try:
        config = Config(str(ROOT / "alembic.ini"))
        # Keep successful CI output concise. Exceptions still surface normally.
        config.config_file_name = None
        config.set_main_option("script_location", str(ROOT / "migrations"))
        command.upgrade(config, "head")
    finally:
        if previous_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_url
        Path(database_path).unlink(missing_ok=True)

    print("Fresh SQLite migration passed.")


if __name__ == "__main__":
    main()
