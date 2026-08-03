"""Fail closed before a production release without printing secret material."""

from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import dotenv_values

from app.production_preflight import validate_production_environment


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate sanitized production release prerequisites."
    )
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--require-workflow-v2", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if not args.env_file.is_file():
        raise SystemExit("production_preflight=blocked code=environment_file_missing")
    if args.env_file.stat().st_mode & 0o077:
        raise SystemExit("production_preflight=blocked code=environment_file_permissions")

    environment = {
        key: value or "" for key, value in dotenv_values(args.env_file).items()
    }
    findings = validate_production_environment(
        environment,
        require_workflow_v2=args.require_workflow_v2,
    )
    if findings:
        for finding in findings:
            print(f"preflight_error={finding.code} message={finding.message}")
        raise SystemExit("production_preflight=blocked")
    print("production_preflight=approved")


if __name__ == "__main__":
    main()
