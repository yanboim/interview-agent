import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "product-specs" / "feature-contract.json"


def test_required_harness_documents_exist() -> None:
    required = [
        ROOT / "AGENTS.md",
        ROOT / "ARCHITECTURE.md",
        ROOT / "docs" / "README.md",
        ROOT / "docs" / "exec-plans" / "README.md",
        ROOT / "docs" / "exec-plans" / "active" / "README.md",
        ROOT / "docs" / "tech-debt-tracker.md",
        CONTRACT,
        ROOT / "Makefile",
    ]
    missing = [path.relative_to(ROOT).as_posix() for path in required if not path.is_file()]
    assert missing == []


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
