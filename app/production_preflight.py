"""Production release configuration checks that never expose secret values."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PreflightFinding:
    """A stable, sanitized reason a production release must stop."""

    code: str
    message: str


_PLACEHOLDERS = {
    "admin",
    "change-me-now",
    "changeme",
    "interview-local-password",
    "password",
    "please-change-me",
    "请替换为强密码",
    "替换为你的智谱_coding_plan_key",
    "替换为你的智谱标准_api_key",
}


def _enabled(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _secret_value(
    environment: Mapping[str, object],
    value_name: str,
    file_name: str | None,
) -> tuple[str, str | None]:
    direct = str(environment.get(value_name) or "").strip()
    if direct:
        return direct, None
    if not file_name:
        return "", None
    configured_path = str(environment.get(file_name) or "").strip()
    if not configured_path:
        return "", None
    try:
        return Path(configured_path).read_text(encoding="utf-8").strip(), None
    except OSError:
        return "", "secret_file_unreadable"


def _check_secret(
    environment: Mapping[str, object],
    *,
    value_name: str,
    file_name: str | None,
    code_prefix: str,
    minimum_length: int,
) -> list[PreflightFinding]:
    value, error = _secret_value(environment, value_name, file_name)
    if error:
        return [
            PreflightFinding(
                f"{code_prefix}_{error}",
                f"{code_prefix} secret file is not readable",
            )
        ]
    if not value:
        return [
            PreflightFinding(
                f"{code_prefix}_missing",
                f"{code_prefix} secret is required",
            )
        ]
    normalized = value.casefold()
    if normalized in _PLACEHOLDERS or "请替换" in normalized:
        return [
            PreflightFinding(
                f"{code_prefix}_placeholder",
                f"{code_prefix} secret still uses a known placeholder",
            )
        ]
    if len(value) < minimum_length:
        return [
            PreflightFinding(
                f"{code_prefix}_weak",
                f"{code_prefix} secret does not meet the minimum length",
            )
        ]
    return []


def validate_production_environment(
    environment: Mapping[str, object],
    *,
    require_workflow_v2: bool = False,
) -> list[PreflightFinding]:
    """Return sanitized reasons the supplied environment is unsafe to release."""
    findings: list[PreflightFinding] = []
    findings.extend(
        _check_secret(
            environment,
            value_name="POSTGRES_PASSWORD",
            file_name=None,
            code_prefix="postgres_password",
            minimum_length=24,
        )
    )
    findings.extend(
        _check_secret(
            environment,
            value_name="GRAFANA_ADMIN_PASSWORD",
            file_name=None,
            code_prefix="grafana_admin_password",
            minimum_length=24,
        )
    )
    findings.extend(
        _check_secret(
            environment,
            value_name="ZHIPU_API_KEY",
            file_name="ZHIPU_API_KEY_FILE",
            code_prefix="model_api_key",
            minimum_length=16,
        )
    )
    findings.extend(
        _check_secret(
            environment,
            value_name="APP_API_KEY",
            file_name="APP_API_KEY_FILE",
            code_prefix="app_api_key",
            minimum_length=24,
        )
    )

    if not _enabled(environment.get("AUTH_REQUIRED")):
        findings.append(
            PreflightFinding(
                "authentication_not_required",
                "AUTH_REQUIRED must be explicitly enabled",
            )
        )
    if str(environment.get("AUTO_CREATE_SCHEMA") or "").strip().lower() != "false":
        findings.append(
            PreflightFinding(
                "automatic_schema_creation_enabled",
                "AUTO_CREATE_SCHEMA must be explicitly disabled",
            )
        )

    if _enabled(environment.get("WEB_SEARCH_ENABLED")):
        findings.extend(
            _check_secret(
                environment,
                value_name="WEB_SEARCH_API_KEY",
                file_name="WEB_SEARCH_API_KEY_FILE",
                code_prefix="web_search_api_key",
                minimum_length=16,
            )
        )
    if _enabled(environment.get("TRANSCRIPTION_ENABLED")):
        if not str(environment.get("TRANSCRIPTION_API_URL") or "").strip():
            findings.append(
                PreflightFinding(
                    "transcription_api_url_missing",
                    "transcription API URL is required when transcription is enabled",
                )
            )
        findings.extend(
            _check_secret(
                environment,
                value_name="TRANSCRIPTION_API_KEY",
                file_name="TRANSCRIPTION_API_KEY_FILE",
                code_prefix="transcription_api_key",
                minimum_length=16,
            )
        )

    if require_workflow_v2:
        if not _enabled(environment.get("MULTI_AGENT_ENABLED")):
            findings.append(
                PreflightFinding(
                    "workflow_v2_disabled",
                    "MULTI_AGENT_ENABLED must be explicitly enabled",
                )
            )
    return findings
