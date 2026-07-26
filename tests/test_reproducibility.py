from pathlib import Path

from scripts.reproducibility import (
    INPUT_DIGEST_PREFIX,
    input_digest,
    stamp_lock,
    validate_repository,
)


def test_repository_build_inputs_are_reproducible() -> None:
    assert validate_repository(Path(".")) == []


def test_stamp_lock_replaces_stale_input_digest(tmp_path) -> None:
    requirements_input = tmp_path / "requirements.in"
    requirements_input.write_text("example>=1\n", encoding="utf-8")
    lock = tmp_path / "requirements.txt"
    lock.write_text(
        f"{INPUT_DIGEST_PREFIX}{'0' * 64}\n"
        "example==1.0 \\\n"
        "    --hash=sha256:"
        f"{'1' * 64}\n",
        encoding="utf-8",
    )

    stamp_lock(tmp_path)

    stamped = lock.read_text(encoding="utf-8")
    assert stamped.count(INPUT_DIGEST_PREFIX) == 1
    assert (
        f"{INPUT_DIGEST_PREFIX}{input_digest(requirements_input)}"
        in stamped.splitlines()[:3]
    )


def test_verifier_rejects_mutable_or_unhashed_inputs(tmp_path) -> None:
    (tmp_path / "requirements.in").write_text(
        "example>=1\n",
        encoding="utf-8",
    )
    (tmp_path / "requirements.txt").write_text(
        f"{INPUT_DIGEST_PREFIX}"
        f"{input_digest(tmp_path / 'requirements.in')}\n"
        "example>=1\n",
        encoding="utf-8",
    )
    (tmp_path / "Dockerfile").write_text(
        "FROM python:latest\nRUN pip install -r requirements.txt\n",
        encoding="utf-8",
    )
    (tmp_path / "docker-compose.yml").write_text(
        "services:\n  db:\n    image: postgres:17\n",
        encoding="utf-8",
    )
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    for name in ("ci.yml", "release.yml"):
        (workflows / name).write_text(
            "- run: pip install -r requirements.txt\n",
            encoding="utf-8",
        )

    errors = validate_repository(tmp_path)

    assert any("not exact" in error for error in errors)
    assert any("no hash" in error for error in errors)
    assert any("latest" in error for error in errors)
    assert any("not digest pinned" in error for error in errors)
    assert any("without hashes" in error for error in errors)
