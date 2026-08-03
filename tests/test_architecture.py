"""架构契约：依赖方向、模块边界与执行边界的静态约束测试。"""

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


def calls_attribute(path: Path, *, owner: str, attribute: str) -> bool:
    """Return whether executable code calls ``owner.attribute``.

    Inspect the syntax tree instead of raw source text so architecture comments
    and docstrings can describe a prohibited call without becoming violations.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == attribute
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == owner
        for node in ast.walk(tree)
    )


def calls_method(path: Path, method: str) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == method
        for node in ast.walk(tree)
    )


def test_domain_calculation_modules_remain_infrastructure_free() -> None:
    pure_modules = {
        "agent_safety.py",
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


def test_runtime_modules_do_not_import_command_scripts() -> None:
    violations = [
        path.relative_to(ROOT).as_posix()
        for path in APP.rglob("*.py")
        if any(matches_prefix(module, {"scripts"}) for module in imported_modules(path))
    ]
    assert violations == []


def test_repository_slices_do_not_import_api_or_agent_composition() -> None:
    repository_root = APP / "repositories"
    forbidden = {
        "app.agent",
        "app.api",
        "app.main",
        "app.multi_agent",
        "app.tools",
        "fastapi",
        "langchain",
        "langgraph",
    }
    violations = {
        path.relative_to(ROOT).as_posix(): sorted(
            module
            for module in imported_modules(path)
            if matches_prefix(module, forbidden)
        )
        for path in repository_root.rglob("*.py")
    }
    assert not any(violations.values()), violations

    expected = {
        "administration.py",
        "chat_messages.py",
        "chat_turns.py",
        "interview_reviews.py",
        "interviews.py",
        "learning.py",
        "profiles.py",
        "resumes.py",
    }
    assert expected <= {path.name for path in repository_root.glob("*.py")}
    assert len((APP / "storage.py").read_text(encoding="utf-8").splitlines()) <= 400


def test_compatibility_facades_stay_bounded_after_capability_splits() -> None:
    limits = {"operations.py": 50, "storage.py": 400, "tools.py": 350}
    actual = {
        name: len((APP / name).read_text(encoding="utf-8").splitlines())
        for name in limits
    }
    assert all(actual[name] <= limit for name, limit in limits.items()), actual


def test_chat_router_does_not_invoke_or_compose_agents() -> None:
    path = APP / "api" / "routers" / "chat.py"
    forbidden = {
        "app.agent",
        "app.agent_budget",
        "app.agent_context",
        "app.model_gateway",
        "app.model_routing",
        "app.tool_context",
        "langchain_core",
        "langgraph",
    }
    violations = sorted(
        module
        for module in imported_modules(path)
        if matches_prefix(module, forbidden)
    )
    source = path.read_text(encoding="utf-8")
    assert violations == []
    assert ".ainvoke(" not in source
    assert ".astream(" not in source
    assert "build_citation_metadata(" not in source


def test_composition_root_stays_transport_only_and_bounded() -> None:
    main_path = APP / "main.py"
    source = main_path.read_text(encoding="utf-8")

    assert len(source.splitlines()) <= 400
    assert '@app.get("/api/' not in source
    assert '@app.post("/api/' not in source
    assert '@app.put("/api/' not in source
    assert '@app.patch("/api/' not in source
    assert '@app.delete("/api/' not in source
    assert "check_dir=False" in source


def test_domain_api_routes_remain_registered() -> None:
    from app.main import app

    paths = app.openapi()["paths"]
    expected = {
        "/api/auth/login",
        "/api/profile",
        "/api/admin/runtime",
        "/api/admin/resources",
        "/api/admin/audit-events",
        "/api/admin/interactions",
        "/api/admin/interactions/{interaction_type}/{interaction_id}/trace",
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
    violations = [
        path.relative_to(ROOT).as_posix()
        for path in [APP / "main.py", *(APP / "api").rglob("*.py")]
        if calls_attribute(path, owner="asyncio", attribute="to_thread")
    ]
    assert violations == []

    assert calls_attribute(
        APP / "application" / "execution.py",
        owner="asyncio",
        attribute="to_thread",
    )


def test_api_does_not_directly_invoke_non_streaming_agents() -> None:
    violations = [
        path.relative_to(ROOT).as_posix()
        for path in (APP / "api").rglob("*.py")
        if calls_method(path, "ainvoke")
    ]
    assert violations == []


def test_api_does_not_directly_stream_agents() -> None:
    violations = [
        path.relative_to(ROOT).as_posix()
        for path in (APP / "api").rglob("*.py")
        if calls_method(path, "astream")
    ]
    assert violations == []


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


def test_retired_supervisor_topology_is_absent_from_runtime_sources() -> None:
    retired_symbols = {
        "SUPERVISOR_PROMPT",
        "get_supervisor_agent",
        "select_interview_agent",
        "interview_supervisor",
    }
    runtime_files = (
        APP / "agent.py",
        APP / "multi_agent.py",
        APP / "chat_agent_executor.py",
        APP / "application" / "chat_workflow.py",
    )

    for path in runtime_files:
        source = path.read_text(encoding="utf-8")
        for symbol in retired_symbols:
            assert symbol not in source
