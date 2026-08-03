"""Authorize pre-release Supervisor retirement from bounded acceptance evidence."""

import argparse
import json
from pathlib import Path

from app.config import get_settings
from app.storage import ConversationStore
from app.workflow_prerelease_gate import (
    validate_workflow_prerelease_evidence_files,
    validate_workflow_prerelease_report,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("eval/reports/workflow-v2-prerelease-acceptance.json"),
    )
    parser.add_argument("--skip-release-ledger", action="store_true")
    parser.add_argument(
        "--evidence-root",
        type=Path,
        default=Path("."),
        help="Root containing the fixed relative evidence paths.",
    )
    args = parser.parse_args()
    if not args.report.is_file():
        raise SystemExit(f"workflow_prerelease_gate=blocked missing_report={args.report}")
    report = json.loads(args.report.read_text(encoding="utf-8"))
    release = rollback_release = None
    if not args.skip_release_ledger:
        settings = get_settings()
        store = ConversationStore(
            settings.database_url or settings.conversation_db_path,
            auto_create_schema=settings.auto_create_schema,
        )
        try:
            release = store.get_deployment_release(str(report.get("release_id") or ""))
            rollback_release = store.get_deployment_release(
                str((report.get("rollback") or {}).get("exercise_release_id") or "")
            )
        except KeyError:
            raise SystemExit("workflow_prerelease_gate=blocked release_ledger_entry_missing") from None
    errors = validate_workflow_prerelease_report(
        report,
        release=release,
        rollback_release=rollback_release,
    )
    errors.extend(
        validate_workflow_prerelease_evidence_files(
            report,
            evidence_root=args.evidence_root,
        )
    )
    if errors:
        for error in errors:
            print(f"gate_error={error}")
        raise SystemExit("workflow_prerelease_gate=blocked")
    print("workflow_prerelease_gate=approved")


if __name__ == "__main__":
    main()
