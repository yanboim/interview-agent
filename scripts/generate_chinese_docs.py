"""生成并校验文档的简体中文镜像。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.parse import unquote

from scripts import generate_docs


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
OUTPUT_ROOT = DOCS / "zh-CN"
TRANSLATION_ROOT = DOCS / "i18n" / "zh-CN"
LOCK_PATH = TRANSLATION_ROOT / "source-lock.json"
MANIFEST_PATH = DOCS / "document-manifest.json"
MIRROR_MANIFEST_PATH = OUTPUT_ROOT / "mirror-manifest.json"

MANUAL_TRANSLATIONS = {
    "AGENTS.md",
    "ARCHITECTURE.md",
    "CHANGELOG.md",
    "SECURITY.md",
    "docs/development.md",
    "docs/documentation-guide.md",
    "docs/design-docs/chat-context-budget.md",
    "docs/design-docs/chat-use-case-boundary.md",
    "docs/design-docs/durable-chat-turn-lifecycle.md",
    "docs/design-docs/durable-redis-jobs.md",
    "docs/design-docs/frontend-toolchain-audit.md",
    "docs/design-docs/interview-answer-idempotency.md",
    "docs/design-docs/model-policy-gateway.md",
    "docs/design-docs/modular-api-composition.md",
    "docs/design-docs/qdrant-versioned-publication.md",
    "docs/design-docs/reproducible-builds.md",
    "docs/design-docs/synchronous-persistence-boundary.md",
    "docs/design-docs/worktree-stack-isolation.md",
    "docs/exec-plans/README.md",
    "docs/generated/README.md",
    "docs/product-specs/README.md",
    "docs/reliability/README.md",
    "docs/reliability/nginx-gateway.md",
    "docs/tech-debt-tracker.md",
    "docs/testing.md",
}

GENERATED_MARKDOWN = {
    "docs/generated/api-routes.md",
    "docs/generated/configuration.md",
    "docs/generated/data-dictionary.md",
}
GENERATED_CONTRACT = "docs/product-specs/feature-contract.json"
MARKDOWN_LINK = re.compile(r"(\[[^\]]+\]\()([^)]+)(\))")


def source_paths() -> list[str]:
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    paths = [
        path
        for group in payload["lifecycle"].values()
        for path in group
    ]
    if len(paths) != len(set(paths)):
        raise ValueError("Lifecycle manifest contains duplicate paths.")
    return paths


def mirror_path(source: str) -> Path:
    path = Path(source)
    if path.parts[0] == "docs":
        return OUTPUT_ROOT.joinpath(*path.parts[1:])
    return OUTPUT_ROOT / "root" / path


def translation_path(source: str) -> Path:
    path = Path(source)
    if path.parts[0] == "docs":
        return TRANSLATION_ROOT.joinpath(*path.parts[1:])
    return TRANSLATION_ROOT / "root" / path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rewrite_links(content: str, source: str, sources: set[str]) -> str:
    source_file = ROOT / source
    output_file = mirror_path(source)

    def replace(match: re.Match[str]) -> str:
        raw_target = match.group(2)
        target = raw_target.strip().strip("<>")
        if (
            not target
            or target.startswith(("#", "http://", "https://", "mailto:"))
        ):
            return match.group(0)
        path_part, separator, anchor = target.partition("#")
        resolved = (source_file.parent / unquote(path_part)).resolve()
        try:
            relative_source = resolved.relative_to(ROOT).as_posix()
        except ValueError:
            return match.group(0)
        destination = (
            mirror_path(relative_source)
            if relative_source in sources
            else resolved
        )
        rewritten = os.path.relpath(destination, output_file.parent)
        if separator:
            rewritten += f"#{anchor}"
        if " " in rewritten:
            rewritten = f"<{rewritten}>"
        return f"{match.group(1)}{rewritten}{match.group(3)}"

    return MARKDOWN_LINK.sub(replace, content)


def chinese_configuration_reference() -> str:
    english = generate_docs.setting_reference()
    return (
        english.replace(
            generate_docs.HEADER,
            "<!-- 由 `python -m scripts.generate_chinese_docs` 自动生成，请勿编辑。 -->\n\n",
        )
        .replace("# Configuration reference", "# 配置参考")
        .replace(
            "Source: `app/config.py::Settings`. Regenerate with "
            "`python -m scripts.generate_docs`.",
            "来源：`app/config.py::Settings`。使用 "
            "`python -m scripts.generate_chinese_docs` 重新生成。",
        )
        .replace(
            "Secret values are intentionally not read or rendered. Production "
            "requirements are documented in `docs/sdlc/CONFIGURATION.md`.",
            "生成过程不会读取或输出Secret值。生产要求见"
            "[配置管理](../sdlc/CONFIGURATION.md)。",
        )
        .replace(
            "| Environment variable | Type | Code default |",
            "| 环境变量 | 类型 | 代码默认值 |",
        )
    )


def chinese_api_reference() -> str:
    english = generate_docs.api_reference()
    return (
        english.replace(
            generate_docs.HEADER,
            "<!-- 由 `python -m scripts.generate_chinese_docs` 自动生成，请勿编辑。 -->\n\n",
        )
        .replace("# API route reference", "# API路由参考")
        .replace(
            "Source: FastAPI decorators in `app/main.py` and "
            "`app/api/routers/`. Regenerate with "
            "`python -m scripts.generate_docs`.",
            "来源：`app/main.py` 和 `app/api/routers/` 中的FastAPI装饰器。使用 "
            "`python -m scripts.generate_chinese_docs` 重新生成。",
        )
        .replace(
            "Field-level request and response schemas remain authoritative in "
            "FastAPI OpenAPI and `app/api/schemas.py`.",
            "字段级请求和响应Schema以FastAPI OpenAPI和 `app/api/schemas.py` 为准。",
        )
        .replace(
            "| Method | Path | Handler | Source |",
            "| 方法 | 路径 | 处理器 | 来源 |",
        )
    )


def chinese_data_reference() -> str:
    english = generate_docs.data_reference()
    return (
        english.replace(
            generate_docs.HEADER,
            "<!-- 由 `python -m scripts.generate_chinese_docs` 自动生成，请勿编辑。 -->\n\n",
        )
        .replace("# Relational data dictionary", "# 关系数据字典")
        .replace(
            "Source: SQLAlchemy metadata in `app/database.py`. Regenerate with "
            "`python -m scripts.generate_docs`.",
            "来源：`app/database.py` 中的SQLAlchemy元数据。使用 "
            "`python -m scripts.generate_chinese_docs` 重新生成。",
        )
        .replace(
            "Alembic revisions remain authoritative for production schema history.",
            "生产Schema历史以Alembic Revision为准。",
        )
        .replace(
            "| Column | Type | Constraints | Reference |",
            "| 列 | 类型 | 约束 | 引用 |",
        )
        .replace("unique", "唯一")
        .replace("not null", "非空")
    )


def chinese_contract() -> str:
    source = json.loads((ROOT / GENERATED_CONTRACT).read_text(encoding="utf-8"))
    translations = json.loads(
        (TRANSLATION_ROOT / "feature-contract-text.json").read_text(
            encoding="utf-8"
        )
    )
    expected_ids = {feature["id"] for feature in source["features"]}
    if set(translations) != expected_ids:
        missing = sorted(expected_ids - set(translations))
        extra = sorted(set(translations) - expected_ids)
        raise ValueError(
            f"Feature-contract translations mismatch; missing={missing}, extra={extra}"
        )
    categories = {
        "security": "安全",
        "functional": "功能",
        "ai-quality": "AI质量",
        "operations": "运维",
        "user-experience": "用户体验",
        "reliability": "可靠性",
        "architecture": "架构",
    }
    source["status_labels_zh_CN"] = {
        "passing": "已通过",
        "planned": "已规划",
    }
    for feature in source["features"]:
        translated = translations[feature["id"]]
        feature["category_zh_CN"] = categories[feature["category"]]
        feature["description"] = translated["description"]
        feature["steps"] = translated["steps"]
    return json.dumps(source, ensure_ascii=False, indent=2) + "\n"


def expected_outputs() -> dict[Path, str]:
    sources = source_paths()
    source_set = set(sources)
    outputs: dict[Path, str] = {}
    localized_generated = {
        "docs/generated/api-routes.md": chinese_api_reference(),
        "docs/generated/configuration.md": chinese_configuration_reference(),
        "docs/generated/data-dictionary.md": chinese_data_reference(),
    }
    for source in sources:
        if source in localized_generated:
            content = localized_generated[source]
        elif source == GENERATED_CONTRACT:
            content = chinese_contract()
        elif source in MANUAL_TRANSLATIONS:
            translation = translation_path(source)
            if not translation.is_file():
                raise FileNotFoundError(
                    f"Missing Chinese translation: {translation.relative_to(ROOT)}"
                )
            content = translation.read_text(encoding="utf-8")
        else:
            content = (ROOT / source).read_text(encoding="utf-8")
        if source.endswith(".md"):
            content = rewrite_links(content, source, source_set)
            if source == "docs/README.md":
                content = (
                    "<!-- 本目录由 `python -m scripts.generate_chinese_docs` "
                    "生成；权威源文件见 `../` 和仓库根目录。 -->\n\n"
                    + content
                )
        outputs[mirror_path(source)] = content

    mirror_manifest = {
        "schema_version": 1,
        "locale": "zh-CN",
        "source_manifest": "../document-manifest.json",
        "documents": [
            {
                "source": source,
                "mirror": mirror_path(source).relative_to(ROOT).as_posix(),
                "mode": (
                    "translated"
                    if source in MANUAL_TRANSLATIONS
                    else "generated"
                    if source in GENERATED_MARKDOWN
                    or source == GENERATED_CONTRACT
                    else "mirrored"
                ),
            }
            for source in sources
        ],
    }
    outputs[MIRROR_MANIFEST_PATH] = (
        json.dumps(mirror_manifest, ensure_ascii=False, indent=2) + "\n"
    )
    return outputs


def translation_lock() -> dict[str, str]:
    return {
        source: digest(ROOT / source)
        for source in sorted(MANUAL_TRANSLATIONS)
    }


def check_translation_lock() -> list[str]:
    if not LOCK_PATH.is_file():
        return [LOCK_PATH.relative_to(ROOT).as_posix()]
    locked = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    current = translation_lock()
    return [
        source
        for source in sorted(set(locked) | set(current))
        if locked.get(source) != current.get(source)
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail when translations or generated Chinese documents are stale.",
    )
    parser.add_argument(
        "--update-lock",
        action="store_true",
        help="Record current English-source hashes after reviewing translations.",
    )
    args = parser.parse_args()

    if args.update_lock:
        LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
        LOCK_PATH.write_text(
            json.dumps(translation_lock(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    stale_translations = check_translation_lock()
    if stale_translations and not args.update_lock:
        raise SystemExit(
            "Chinese translations require review for changed sources: "
            + ", ".join(stale_translations)
        )

    outputs = expected_outputs()
    if args.check:
        stale = [
            path.relative_to(ROOT).as_posix()
            for path, content in outputs.items()
            if not path.is_file()
            or path.read_text(encoding="utf-8") != content
        ]
        if stale:
            raise SystemExit(
                "Chinese documentation is stale: "
                + ", ".join(stale)
                + ". Run `python -m scripts.generate_chinese_docs`."
            )
        print(f"Chinese documentation is current ({len(source_paths())} documents).")
        return

    for path, content in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
