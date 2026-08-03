"""向管理员发版记录簿写入一次部署结果。"""

import argparse
from datetime import UTC, datetime
import os

from app.config import get_settings
from app.storage import ConversationStore


TERMINAL_STATUSES = {"succeeded", "failed", "rolled_back"}


def _key_values(items: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in items:
        key, separator, value = item.partition("=")
        if not separator or not key.strip() or not value.strip():
            raise ValueError("验证项必须使用 name=value 格式")
        result[key.strip()] = value.strip()
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Record a verified deployment for the administrator console."
    )
    parser.add_argument(
        "--release-id",
        default=os.getenv("RELEASE_ID", ""),
        help="Stable idempotency key reused across deployment status updates.",
    )
    parser.add_argument(
        "--version",
        default=(
            os.getenv("RELEASE_VERSION")
            or os.getenv("GITHUB_REF_NAME")
            or ""
        ),
    )
    parser.add_argument("--title", required=True)
    parser.add_argument("--summary", default="")
    parser.add_argument(
        "--environment",
        choices=("canary", "production"),
        default=os.getenv("RELEASE_ENVIRONMENT", "production"),
    )
    parser.add_argument(
        "--status",
        choices=("deploying", "succeeded", "failed", "rolled_back"),
        required=True,
    )
    parser.add_argument(
        "--commit-sha",
        default=os.getenv("RELEASE_COMMIT") or os.getenv("GITHUB_SHA") or "",
    )
    parser.add_argument("--change", action="append", default=[])
    parser.add_argument(
        "--verification",
        action="append",
        default=[],
        metavar="NAME=RESULT",
    )
    parser.add_argument("--app-image", default="")
    parser.add_argument("--worker-image", default="")
    parser.add_argument("--migration-revision", default="")
    parser.add_argument("--recovery-point", default="")
    parser.add_argument(
        "--triggered-by",
        default=(
            os.getenv("RELEASE_TRIGGERED_BY")
            or os.getenv("GITHUB_ACTOR")
            or "deployment"
        ),
    )
    parser.add_argument("--started-at", default="")
    parser.add_argument("--completed-at", default="")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    now = datetime.now(UTC).isoformat()
    release_id = args.release_id.strip()
    version = args.version.strip()
    if not release_id:
        if not version:
            raise ValueError("必须提供 --release-id 或 --version")
        release_id = f"{args.environment}-{version}"
    if not version:
        raise ValueError("必须提供 --version")

    settings = get_settings()
    store = ConversationStore(
        settings.database_url or settings.conversation_db_path,
        auto_create_schema=settings.auto_create_schema,
    )
    release = store.record_deployment_release(
        release_id=release_id,
        version=version,
        title=args.title,
        summary=args.summary,
        environment=args.environment,
        status=args.status,
        commit_sha=args.commit_sha or None,
        changes=args.change,
        verification=_key_values(args.verification),
        app_image=args.app_image or None,
        worker_image=args.worker_image or None,
        migration_revision=args.migration_revision or None,
        recovery_point=args.recovery_point or None,
        triggered_by=args.triggered_by,
        started_at=args.started_at or now,
        completed_at=(
            args.completed_at
            or (now if args.status in TERMINAL_STATUSES else None)
        ),
    )
    print(
        f"发版记录已写入：{release['version']} "
        f"({release['environment']}/{release['status']})"
    )


if __name__ == "__main__":
    main()
