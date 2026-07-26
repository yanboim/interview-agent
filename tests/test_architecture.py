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
        "chat_context.py",
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
    for path in APP.rglob("*.py"):
        if path.name == "main.py":
            continue
        if "app.main" in imported_modules(path):
            violations.append(path.relative_to(ROOT).as_posix())
    assert violations == []


def test_composition_root_stays_transport_only_and_bounded() -> None:
    main_path = APP / "main.py"
    source = main_path.read_text(encoding="utf-8")

    assert len(source.splitlines()) <= 400
    assert '@app.get("/api/' not in source
    assert '@app.post("/api/' not in source
    assert '@app.put("/api/' not in source
    assert '@app.patch("/api/' not in source
    assert '@app.delete("/api/' not in source


def test_domain_api_routes_remain_registered() -> None:
    from app.main import app

    paths = app.openapi()["paths"]
    expected = {
        "/api/auth/login",
        "/api/profile",
        "/api/admin/runtime",
        "/api/chat",
        "/api/chat/stream",
        "/api/conversations",
        "/api/interviews/start",
        "/api/interviews/{interview_id}/answer",
        "/api/capability-profile",
        "/api/learning-tasks",
    }
    assert expected <= paths.keys()


def test_api_uses_one_sync_execution_boundary() -> None:
    violations = []
    for path in [APP / "main.py", *(APP / "api").rglob("*.py")]:
        source = path.read_text(encoding="utf-8")
        if "asyncio.to_thread" in source:
            violations.append(path.relative_to(ROOT).as_posix())
    assert violations == []

    executor_source = (
        APP / "application" / "execution.py"
    ).read_text(encoding="utf-8")
    assert executor_source.count("asyncio.to_thread") == 1


def test_store_business_operations_do_not_use_process_lock() -> None:
    source = (APP / "storage.py").read_text(encoding="utf-8")

    assert "self._lock" not in source
    assert "with self._initialization_lock, self.engine" not in source


def test_model_provider_construction_is_confined_to_adapters() -> None:
    allowed = {"model_gateway.py"}
    violations = []
    for path in APP.rglob("*.py"):
        imports = imported_modules(path)
        if any(matches_prefix(module, {"langchain_openai"}) for module in imports):
            if path.name not in allowed:
                violations.append(path.relative_to(ROOT).as_posix())
    assert violations == []
