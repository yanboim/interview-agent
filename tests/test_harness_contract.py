import json
from pathlib import Path
import re
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "product-specs" / "feature-contract.json"
MANIFEST = ROOT / "docs" / "document-manifest.json"


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


def test_repository_markdown_links_resolve() -> None:
    markdown_link = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    broken: list[str] = []

    documents = [
        *sorted(ROOT.glob("*.md")),
        *sorted((ROOT / "docs").rglob("*.md")),
    ]
    for document in documents:
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
