"""Fail closed unless Workflow V2 has approved production observation evidence."""

import argparse
import json
from pathlib import Path

from app.config import get_settings
from app.storage import ConversationStore
from app.workflow_rollout_gate import validate_workflow_rollout_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Authorize Supervisor retirement from production evidence."
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("eval/reports/workflow-v2-production-observation.json"),
    )
    parser.add_argument(
        "--skip-release-ledger",
        action="store_true",
        help="For isolated policy tests only; never use for retirement approval.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if not args.report.is_file():
        raise SystemExit(f"workflow_retirement_gate=blocked missing_report={args.report}")
    report = json.loads(args.report.read_text(encoding="utf-8"))
    release = None
    rollback_release = None
    if not args.skip_release_ledger:
        release_id = str(report.get("release_id") or "")
        settings = get_settings()
        store = ConversationStore(
            settings.database_url or settings.conversation_db_path,
            auto_create_schema=settings.auto_create_schema,
        )
        try:
            release = store.get_deployment_release(release_id)
        except KeyError:
            raise SystemExit(
                "workflow_retirement_gate=blocked release_ledger_entry_missing"
            ) from None
        rollback_id = str(
            (report.get("rollback") or {}).get("exercise_release_id") or ""
        )
        try:
            rollback_release = store.get_deployment_release(rollback_id)
        except KeyError:
            raise SystemExit(
                "workflow_retirement_gate=blocked rollback_ledger_entry_missing"
            ) from None
    errors = validate_workflow_rollout_report(
        report,
        release=release,
        rollback_release=rollback_release,
    )
    if errors:
        for error in errors:
            print(f"gate_error={error}")
        raise SystemExit("workflow_retirement_gate=blocked")
    print("workflow_retirement_gate=approved")


if __name__ == "__main__":
    main()
