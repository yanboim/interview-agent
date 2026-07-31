import argparse
"""检查依赖锁、容器镜像与构建输入是否满足可复现约束。"""

import hashlib
from pathlib import Path
import re


INPUT_DIGEST_PREFIX = "# input-sha256: "
DIGEST_PATTERN = re.compile(r"sha256:[a-f0-9]{64}$")
PIN_PATTERN = re.compile(
    r"^[A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_,.-]+\])?"
    r"==[^\s\\;]+(?:\s*\\)?$"
)


def input_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stamp_lock(root: Path) -> None:
    requirements_input = root / "requirements.in"
    lock_path = root / "requirements.txt"
    lines = [
        line
        for line in lock_path.read_text(encoding="utf-8").splitlines()
        if not line.startswith(INPUT_DIGEST_PREFIX)
    ]
    lines.insert(0, f"{INPUT_DIGEST_PREFIX}{input_digest(requirements_input)}")
    lock_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _lock_errors(root: Path) -> list[str]:
    errors: list[str] = []
    lock = (root / "requirements.txt").read_text(encoding="utf-8")
    expected_header = (
        f"{INPUT_DIGEST_PREFIX}{input_digest(root / 'requirements.in')}"
    )
    if expected_header not in lock.splitlines()[:3]:
        errors.append("requirements.txt input digest is missing or stale")

    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lock.splitlines():
        if line and not line[0].isspace() and not line.startswith(("#", "--")):
            if current:
                blocks.append(current)
            current = [line]
        elif current:
            current.append(line)
    if current:
        blocks.append(current)

    if not blocks:
        errors.append("requirements.txt contains no locked requirements")
    for block in blocks:
        requirement = block[0]
        if not PIN_PATTERN.fullmatch(requirement):
            errors.append(f"lock requirement is not exact: {requirement}")
        if not any("--hash=sha256:" in line for line in block):
            errors.append(f"lock requirement has no hash: {requirement}")
    return errors


def _image_errors(root: Path) -> list[str]:
    errors: list[str] = []
    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
    references = re.findall(r"^FROM\s+(\S+)", dockerfile, re.MULTILINE)
    references.extend(
        re.findall(r"^\s*image:\s*(\S+)", compose, re.MULTILINE)
    )
    for reference in references:
        if ":latest" in reference:
            errors.append(f"mutable latest image is prohibited: {reference}")
        if "@" not in reference:
            errors.append(f"image is not digest pinned: {reference}")
            continue
        readable, digest = reference.rsplit("@", 1)
        if ":" not in readable.rsplit("/", 1)[-1]:
            errors.append(f"image has no readable version tag: {reference}")
        if not DIGEST_PATTERN.fullmatch(digest):
            errors.append(f"image digest is invalid: {reference}")
    return errors


def _install_errors(root: Path) -> list[str]:
    errors: list[str] = []
    dockerfile = re.sub(
        r"\s+",
        " ",
        (root / "Dockerfile").read_text(encoding="utf-8"),
    )
    required = "pip install --require-hashes -r requirements.txt"
    if required not in dockerfile:
        errors.append("Dockerfile must install the hash-verified lock")

    for workflow_name in ("ci.yml", "release.yml"):
        workflow = (
            root / ".github" / "workflows" / workflow_name
        ).read_text(encoding="utf-8")
        if "pip install -r requirements.txt" in workflow:
            errors.append(
                f"{workflow_name} installs requirements without hashes"
            )
        if required not in workflow:
            errors.append(
                f"{workflow_name} does not install the hash-verified lock"
            )
    return errors


def validate_repository(root: Path) -> list[str]:
    return [
        *_lock_errors(root),
        *_image_errors(root),
        *_install_errors(root),
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stamp or validate reproducible build inputs."
    )
    parser.add_argument("command", choices=("stamp", "check"))
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    root = args.root.resolve()
    if args.command == "stamp":
        stamp_lock(root)
        return
    errors = validate_repository(root)
    if errors:
        raise SystemExit("\n".join(f"- {error}" for error in errors))
    print("Reproducibility inputs passed.")


if __name__ == "__main__":
    main()
