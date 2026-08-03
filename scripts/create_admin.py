"""创建或升级管理员账号的运维脚本。"""

import argparse

from app.auth import AuthService
from app.config import get_settings
from app.storage import ConversationStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Create an administrator account.")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    args = parser.parse_args()
    if len(args.password) < 10:
        raise ValueError("管理员密码至少需要 10 个字符。")

    settings = get_settings()
    store = ConversationStore(
        settings.database_url or settings.conversation_db_path,
        auto_create_schema=settings.auto_create_schema,
    )
    store.initialize()
    user = AuthService(store.engine).create_user(
        args.username.strip().casefold(),
        args.password,
        role="admin",
    )
    print(f"管理员创建完成：{user.username} ({user.user_id})")


if __name__ == "__main__":
    main()
