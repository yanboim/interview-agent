import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def matches_prefix(module: str, prefixes: set[str]) -> bool:
    return any(module == prefix or module.startswith(f"{prefix}.") for prefix in prefixes)


def test_domain_calculation_modules_remain_infrastructure_free() -> None:
    pure_modules = {
        "chunks.py",
        "evaluation.py",
        "learning.py",
    }
    forbidden = {
        "fastapi",
        "httpx",
        "langchain",
        "langchain_core",
        "langchain_openai",
        "langgraph",
        "qdrant_client",
        "redis",
        "sqlalchemy",
    }

    violations = {
        filename: sorted(
            module
            for module in imported_modules(APP / filename)
            if matches_prefix(module, forbidden)
        )
        for filename in pure_modules
    }
    assert not any(violations.values()), violations


def test_database_schema_has_no_transport_agent_or_network_dependencies() -> None:
    forbidden = {
        "app.agent",
        "app.auth",
        "app.main",
        "app.rag",
        "app.tools",
        "fastapi",
        "httpx",
        "langchain",
        "langgraph",
        "qdrant_client",
        "redis",
    }
    imports = imported_modules(APP / "database.py")
    violations = sorted(
        module for module in imports if matches_prefix(module, forbidden)
    )
    assert violations == []


def test_application_modules_do_not_import_composition_root() -> None:
    violations = []
    for path in APP.glob("*.py"):
        if path.name == "main.py":
            continue
        if "app.main" in imported_modules(path):
            violations.append(path.relative_to(ROOT).as_posix())
    assert violations == []


def test_model_provider_construction_is_confined_to_adapters() -> None:
    allowed = {
        "agent.py",
        "interview_engine.py",
        "llm_reranker.py",
        "multi_agent.py",
        "rag.py",
    }
    violations = []
    for path in APP.glob("*.py"):
        imports = imported_modules(path)
        if any(matches_prefix(module, {"langchain_openai"}) for module in imports):
            if path.name not in allowed:
                violations.append(path.relative_to(ROOT).as_posix())
    assert violations == []
