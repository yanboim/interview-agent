"""仓库门禁契约（功能契约可执行引用）的测试。"""

import hashlib
import json
from pathlib import Path
import re
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "product-specs" / "feature-contract.json"
MANIFEST = ROOT / "docs" / "document-manifest.json"
STRUCTURE_BASELINE = (
    ROOT / "eval" / "reports" / "repository-structure-baseline-2026-08-01.json"
)
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
DEEP_WORKFLOW = ROOT / ".github" / "workflows" / "deep-verification.yml"
MAKEFILE = ROOT / "Makefile"
COMPOSE_FILE = ROOT / "docker-compose.yml"
DOCKERFILE = ROOT / "Dockerfile"


def test_required_harness_documents_exist() -> None:
    required = [
        ROOT / "AGENTS.md",
        ROOT / "CONTRIBUTING.md",
        ROOT / "ARCHITECTURE.md",
        ROOT / "docs" / "README.md",
        ROOT / "docs" / "documentation-guide.md",
        ROOT / "docs" / "development.md",
        ROOT / "docs" / "testing.md",
        ROOT / "docs" / "product-specs" / "README.md",
        ROOT / "docs" / "reliability" / "README.md",
        ROOT / "docs" / "security" / "README.md",
        ROOT / "docs" / "product" / "PRD.md",
        ROOT / "docs" / "ux" / "PROTOTYPE-SPEC.md",
        ROOT / "docs" / "architecture" / "README.md",
        ROOT / "docs" / "architecture" / "DOMAIN-MODEL.md",
        ROOT / "docs" / "architecture" / "DATA-ARCHITECTURE.md",
        ROOT / "docs" / "sdlc" / "DEVELOPMENT-LIFECYCLE.md",
        ROOT / "docs" / "sdlc" / "DEFINITION-OF-DONE.md",
        ROOT / "docs" / "quality" / "TEST-STRATEGY.md",
        ROOT / "docs" / "quality" / "QUALITY-GATES.md",
        ROOT / "docs" / "release" / "RELEASE-PROCESS.md",
        ROOT / "docs" / "release" / "ROLLBACK-RUNBOOK.md",
        ROOT / "docs" / "operations" / "INCIDENT-RESPONSE.md",
        ROOT / "docs" / "operations" / "BACKUP-RESTORE.md",
        ROOT / "docs" / "security" / "THREAT-MODEL.md",
        ROOT / "docs" / "security" / "DATA-CLASSIFICATION.md",
        ROOT / "docs" / "exec-plans" / "README.md",
        ROOT / "docs" / "exec-plans" / "active" / "README.md",
        ROOT / "docs" / "tech-debt-tracker.md",
        MANIFEST,
        CONTRACT,
        ROOT / "Makefile",
    ]
    missing = [path.relative_to(ROOT).as_posix() for path in required if not path.is_file()]
    assert missing == []


def test_repository_structure_baseline_is_traceable() -> None:
    payload = json.loads(STRUCTURE_BASELINE.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "repository-structure-baseline-v1"

    identity = payload["source_identity"]
    sources = {
        "agent_quality_suite_sha256": ROOT / "eval" / "agent_quality_suite.v1.json",
        "model_routing_report_sha256": (
            ROOT / "eval" / "reports" / "model-routing-canary-approved.json"
        ),
    }
    for field, path in sources.items():
        assert identity[field] == hashlib.sha256(path.read_bytes()).hexdigest()

    groups = payload["agent_quality"]["groups"]
    assert payload["agent_quality"]["gate_passed"] is True
    assert {name: group["cases"] for name, group in groups.items()} == {
        "routing": 100,
        "grounded_answer": 50,
        "multi_turn_delegation": 30,
        "safety": 30,
        "confirmation_workflow": 20,
    }
    assert all(group["pass_rate"] == 1.0 for group in groups.values())


def test_lifecycle_document_manifest_is_complete() -> None:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    lifecycle = payload["lifecycle"]
    assert set(lifecycle) == {
        "entrypoints",
        "product",
        "experience",
        "architecture",
        "delivery",
        "quality",
        "release",
        "operations",
        "security",
        "governance",
        "generated",
    }
    paths = [path for group in lifecycle.values() for path in group]
    assert len(paths) == len(set(paths))
    missing = [path for path in paths if not (ROOT / path).is_file()]
    assert missing == []


def test_generated_documentation_is_current() -> None:
    from scripts.generate_docs import expected_outputs

    stale = [
        path.relative_to(ROOT).as_posix()
        for path, expected in expected_outputs().items()
        if not path.is_file() or path.read_text(encoding="utf-8") != expected
    ]
    assert stale == []


def test_chinese_documentation_mirror_is_current_and_complete() -> None:
    from scripts.generate_chinese_docs import (
        check_translation_lock,
        expected_outputs,
        mirror_path,
        source_paths,
    )

    assert check_translation_lock() == []
    sources = source_paths()
    outputs = expected_outputs()
    stale = [
        path.relative_to(ROOT).as_posix()
        for path, expected in outputs.items()
        if not path.is_file() or path.read_text(encoding="utf-8") != expected
    ]
    assert stale == []
    assert len(sources) == len(set(sources))
    assert all(mirror_path(source).is_file() for source in sources)


def test_repository_markdown_links_resolve() -> None:
    markdown_link = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    broken: list[str] = []

    documents = [
        *sorted(ROOT.glob("*.md")),
        *sorted((ROOT / "docs").rglob("*.md")),
    ]
    for document in documents:
        if ROOT / "docs" / "i18n" in document.parents:
            continue
        for raw_target in markdown_link.findall(
            document.read_text(encoding="utf-8")
        ):
            target = raw_target.strip().strip("<>")
            if (
                not target
                or target.startswith(("#", "http://", "https://", "mailto:"))
            ):
                continue
            path_target = unquote(target.split("#", 1)[0])
            resolved = (document.parent / path_target).resolve()
            if not resolved.exists() or ROOT not in resolved.parents:
                broken.append(
                    f"{document.relative_to(ROOT).as_posix()} -> {raw_target}"
                )

    assert broken == []


def test_feature_contract_is_complete_and_traceable() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["status_values"] == ["passing", "planned"]

    features = payload["features"]
    ids = [feature["id"] for feature in features]
    assert len(ids) == len(set(ids))
    assert features

    for feature in features:
        assert feature["category"]
        assert feature["description"]
        assert len(feature["steps"]) >= 2
        assert feature["status"] in payload["status_values"]

        if feature["status"] == "passing":
            verification = feature.get("verification", [])
            assert verification, feature["id"]
            missing = [
                reference
                for reference in verification
                if not (ROOT / reference).is_file()
            ]
            assert missing == [], feature["id"]
        else:
            gap_path = feature.get("gap", "").split("#", 1)[0]
            assert gap_path, feature["id"]
            assert (ROOT / gap_path).is_file(), feature["id"]


def test_release_packaging_requires_the_complete_harness() -> None:
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    harness_job = workflow.index("  verify-harness:\n")
    package_job = workflow.index("  package:\n")
    harness_command = workflow.index(
        "make harness-check PYTHON=python NPM=npm",
        harness_job,
        package_job,
    )

    assert harness_job < harness_command < package_job
    package_block = workflow[package_job:]
    assert "    needs: verify-harness\n" in package_block
    assert package_block.index("needs: verify-harness") < package_block.index(
        "docker build"
    )
    assert "aquasecurity/trivy-action@v0.36.0" in package_block
    assert package_block.index("docker build") < package_block.index(
        "aquasecurity/trivy-action"
    ) < package_block.index("docker save")


def test_pull_request_and_deep_verification_are_tiered() -> None:
    makefile = MAKEFILE.read_text(encoding="utf-8")
    ci = CI_WORKFLOW.read_text(encoding="utf-8")
    deep = DEEP_WORKFLOW.read_text(encoding="utf-8")

    assert "dev-check:" in makefile
    assert (
        "pr-check: harness-static backend-fast-check frontend-check "
        "migration-check"
    ) in makefile
    assert "$(PYTHON) -m scripts.check_migrations" in makefile
    assert "harness-check: harness-static backend-check frontend-check e2e" in makefile
    assert "backend-check: frontend-build" in makefile
    assert "backend-fast-check: frontend-build" in makefile
    assert "frontend-check: frontend-fast-check frontend-build" in makefile

    assert "make pr-check PYTHON=python NPM=npm" in ci
    assert "cancel-in-progress: true" in ci
    for heavyweight_step in (
        "playwright install",
        "test:e2e",
        "pip-audit",
        "docker/build-push-action",
        "aquasecurity/trivy-action",
    ):
        assert heavyweight_step not in ci

    assert "branches: [main]" in deep
    assert "schedule:" in deep
    assert "workflow_dispatch:" in deep
    assert "make harness-check PYTHON=python NPM=npm" in deep
    assert "pip-audit -r requirements.txt" in deep
    assert "npm run audit:dependencies --prefix frontend" in deep
    assert "docker/build-push-action@v7" in deep
    assert "aquasecurity/trivy-action@v0.36.0" in deep
    assert "if: failure()" in deep


def test_runtime_data_and_seed_knowledge_have_explicit_ownership_semantics() -> None:
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    compose = COMPOSE_FILE.read_text(encoding="utf-8")
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert ".var/" in ignored
    assert "COPY knowledge knowledge" in dockerfile
    assert "knowledge_data:/app/knowledge" in compose
    assert "volume-nocopy" not in compose
