import os
from pathlib import Path
import subprocess
import sys

from app.production_preflight import validate_production_environment


ROOT = Path(__file__).resolve().parents[1]


def _valid_environment() -> dict[str, str]:
    return {
        "POSTGRES_PASSWORD": "p" * 32,
        "GRAFANA_ADMIN_PASSWORD": "g" * 32,
        "ZHIPU_API_KEY": "z" * 24,
        "APP_API_KEY": "a" * 32,
        "AUTH_REQUIRED": "true",
        "AUTO_CREATE_SCHEMA": "false",
        "WEB_SEARCH_ENABLED": "false",
        "TRANSCRIPTION_ENABLED": "false",
        "MULTI_AGENT_ENABLED": "true",
    }


def test_valid_production_environment_is_approved() -> None:
    assert not validate_production_environment(
        _valid_environment(), require_workflow_v2=True
    )


def test_defaults_and_unsafe_flags_fail_closed_without_secret_values() -> None:
    environment = _valid_environment()
    leaked_secret = "short-secret-value"
    environment.update(
        {
            "POSTGRES_PASSWORD": "interview-local-password",
            "GRAFANA_ADMIN_PASSWORD": "change-me-now",
            "APP_API_KEY": leaked_secret,
            "AUTH_REQUIRED": "false",
            "AUTO_CREATE_SCHEMA": "true",
            "MULTI_AGENT_ENABLED": "false",
        }
    )

    findings = validate_production_environment(
        environment, require_workflow_v2=True
    )
    codes = {finding.code for finding in findings}
    assert {
        "postgres_password_placeholder",
        "grafana_admin_password_placeholder",
        "app_api_key_weak",
        "authentication_not_required",
        "automatic_schema_creation_enabled",
        "workflow_v2_disabled",
    } <= codes
    rendered = " ".join(f"{item.code} {item.message}" for item in findings)
    assert leaked_secret not in rendered
    assert "interview-local-password" not in rendered
    assert "change-me-now" not in rendered


def test_enabled_optional_provider_requires_complete_configuration() -> None:
    environment = _valid_environment()
    environment.update(
        {
            "WEB_SEARCH_ENABLED": "true",
            "WEB_SEARCH_API_KEY": "",
            "TRANSCRIPTION_ENABLED": "true",
            "TRANSCRIPTION_API_URL": "",
            "TRANSCRIPTION_API_KEY": "",
        }
    )

    codes = {
        finding.code for finding in validate_production_environment(environment)
    }
    assert codes == {
        "web_search_api_key_missing",
        "transcription_api_url_missing",
        "transcription_api_key_missing",
    }


def test_secret_file_is_supported_and_unreadable_file_is_sanitized(tmp_path) -> None:
    environment = _valid_environment()
    model_secret = tmp_path / "model-secret"
    model_secret.write_text("z" * 24, encoding="utf-8")
    environment["ZHIPU_API_KEY"] = ""
    environment["ZHIPU_API_KEY_FILE"] = str(model_secret)
    assert not validate_production_environment(environment)

    environment["ZHIPU_API_KEY_FILE"] = str(tmp_path / "private-missing-name")
    findings = validate_production_environment(environment)
    assert [item.code for item in findings] == ["model_api_key_secret_file_unreadable"]
    assert str(tmp_path) not in findings[0].message


def test_cli_rejects_broad_permissions_and_approves_safe_file(tmp_path) -> None:
    env_file = tmp_path / "production.env"
    env_file.write_text(
        "\n".join(f"{key}={value}" for key, value in _valid_environment().items()),
        encoding="utf-8",
    )
    env_file.chmod(0o644)
    command = [
        sys.executable,
        "-m",
        "scripts.check_production_preflight",
        "--env-file",
        os.fspath(env_file),
        "--require-workflow-v2",
    ]
    rejected = subprocess.run(
        command, cwd=ROOT, text=True, capture_output=True, check=False
    )
    assert rejected.returncode != 0
    assert "code=environment_file_permissions" in (
        rejected.stdout + rejected.stderr
    )

    env_file.chmod(0o600)
    approved = subprocess.run(
        command, cwd=ROOT, text=True, capture_output=True, check=False
    )
    assert approved.returncode == 0
    assert approved.stdout.strip() == "production_preflight=approved"
