"""显式回收进程崩溃遗留的超龄聊天回合。"""

import argparse
from datetime import UTC, datetime, timedelta

from app.config import get_settings
from app.storage import ConversationStore


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Owner-fence stale generating chat turns after a process crash."
    )
    parser.add_argument("--older-than-seconds", type=int, default=600)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required because this changes durable turn state to failed.",
    )
    args = parser.parse_args()
    if args.older_than_seconds < 60:
        raise SystemExit("--older-than-seconds must be at least 60")
    if not args.confirm:
        raise SystemExit("Refusing state change without --confirm")
    settings = get_settings()
    store = ConversationStore(
        settings.database_url or settings.conversation_db_path,
        auto_create_schema=settings.auto_create_schema,
    )
    recovered = store.recover_stale_chat_turns(
        stale_before=datetime.now(UTC) - timedelta(seconds=args.older_than_seconds),
        limit=args.limit,
    )
    print(f"recovered_stale_chat_turns={len(recovered)}")


if __name__ == "__main__":
    main()
