"""Run a sanitized, isolated live-model cohort for Workflow V2 retirement."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import secrets
import time

import httpx

from app.config import get_settings
from app.model_routing import explicit_workflow_routes


CASES = (
    ("live-knowledge", "解释 Redis 缓存击穿原理。"),
    ("live-interviewer", "请出一道 JVM GC 高级面试题。"),
    ("live-evaluator", "请评价这段回答：volatile 能保证复合操作原子性。"),
    ("live-planner", "根据当前训练进度制定三天学习计划。"),
    ("live-knowledge-planner", "解释 Redis 缓存击穿原理，并制定三天学习计划。"),
    ("live-evaluator-interviewer", "请评价我的回答并继续追问：CAS 一定不会有 ABA 问题。"),
)


def _write_private_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.chmod(path, 0o600)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run isolated live Workflow V2 acceptance without retaining content."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".var/workflow-v2-prerelease-live-acceptance.json"),
    )
    parser.add_argument(
        "--cleanup-locator",
        type=Path,
        default=Path(".var/workflow-v2-prerelease-cleanup-locator.json"),
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    api_key = get_settings().app_api_key
    if not api_key:
        raise SystemExit("workflow_prerelease_live=blocked app_api_key_missing")

    suffix = secrets.token_hex(6)
    username = f"workflow-prerelease-{suffix}"
    password = f"Wf2!{secrets.token_urlsafe(18)}"
    common_headers = {"x-api-key": api_key}
    results: list[dict[str, object]] = []
    user_id = ""
    refresh_token = ""
    attempted_sessions: list[str] = []
    started_at = datetime.now(UTC)

    with httpx.Client(base_url=args.base_url, timeout=120.0) as client:
        response = client.post(
            "/api/auth/register",
            headers=common_headers,
            json={"username": username, "password": password},
        )
        response.raise_for_status()
        auth = response.json()
        access_token = str(auth["access_token"])
        refresh_token = str(auth["refresh_token"])
        user_id = str(auth["user"]["user_id"])
        headers = {
            **common_headers,
            "authorization": f"Bearer {access_token}",
        }
        _write_private_json(
            args.cleanup_locator,
            {"username": username, "user_id": user_id},
        )

        try:
            for index, (case_id, prompt) in enumerate(CASES, start=1):
                expected_routes = explicit_workflow_routes(prompt)
                session_id = f"prerelease-{suffix}-{index}"
                attempted_sessions.append(session_id)
                call_started = time.monotonic()
                response = client.post(
                    "/api/chat",
                    headers={**headers, "Idempotency-Key": f"{case_id}-{suffix}"},
                    json={
                        "user_id": user_id,
                        "session_id": session_id,
                        "message": prompt,
                    },
                )
                response.raise_for_status()
                chat = response.json()
                if not str(chat.get("answer") or "").strip():
                    raise RuntimeError(f"{case_id} returned an empty answer")
                history = client.get(
                    f"/api/conversations/{session_id}/messages",
                    headers=headers,
                    params={"user_id": user_id},
                )
                history.raise_for_status()
                assistant = [
                    item for item in history.json() if item.get("role") == "assistant"
                ]
                if len(assistant) != 1:
                    raise RuntimeError(f"{case_id} did not persist one assistant result")
                model_version = str(assistant[0].get("metadata", {}).get("model_version") or "")
                model_count = len([item for item in model_version.split("+") if item])
                if model_count != len(expected_routes):
                    raise RuntimeError(f"{case_id} model provenance count mismatch")
                results.append(
                    {
                        "case_id": case_id,
                        "status": "passed",
                        "expected_routes": list(expected_routes),
                        "model_provenance_count": model_count,
                        "duration_ms": int((time.monotonic() - call_started) * 1000),
                    }
                )
        finally:
            for session_id in attempted_sessions:
                deleted = client.delete(
                    f"/api/conversations/{session_id}",
                    headers=headers,
                    params={"user_id": user_id},
                )
                deleted.raise_for_status()
            client.post(
                "/api/auth/logout",
                headers=headers,
                json={"refresh_token": refresh_token},
            ).raise_for_status()

    ended_at = datetime.now(UTC)
    coverage = sorted(
        {route for result in results for route in result["expected_routes"]}
    )
    report = {
        "schema_version": "workflow-v2-prerelease-live-v1",
        "started_at": started_at.isoformat(),
        "ended_at": ended_at.isoformat(),
        "total_cases": len(CASES),
        "passed_cases": len(results),
        "multi_intent_cases": sum(
            len(result["expected_routes"]) > 1 for result in results
        ),
        "specialist_coverage": coverage,
        "zero_tolerance_failures": 0,
        "contains_user_content": False,
        "api_conversation_cleanup_verified": len(attempted_sessions) == len(CASES),
        "identity_cleanup_verified": False,
        "cases": results,
    }
    _write_private_json(args.output, report)
    print(
        "workflow_prerelease_live=pending_identity_cleanup "
        f"passed={len(results)} total={len(CASES)}"
    )


if __name__ == "__main__":
    main()
