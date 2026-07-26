from pathlib import Path

import pytest

from scripts.worktree_env import (
    PORT_OFFSETS,
    generate_environment,
    render_environment,
    write_environment,
)


def test_environment_is_stable_for_the_same_resolved_worktree(
    tmp_path,
) -> None:
    worktree = tmp_path / "feature-one"
    worktree.mkdir()

    first = generate_environment(worktree)
    second = generate_environment(worktree / ".")

    assert first == second
    assert first.project_name.startswith("interview-agent-feature-one-")
    assert len(set(first.ports.values())) == len(PORT_OFFSETS)
    assert all(20000 <= port < 45000 for port in first.ports.values())


def test_two_worktrees_have_distinct_projects_and_port_blocks(
    tmp_path,
) -> None:
    first_path = tmp_path / "feature-one"
    second_path = tmp_path / "feature-two"
    first_path.mkdir()
    second_path.mkdir()

    first = generate_environment(first_path)
    second = generate_environment(second_path)

    assert first.suffix != second.suffix
    assert first.project_name != second.project_name
    assert set(first.ports.values()).isdisjoint(second.ports.values())
    assert f"{first.project_name}_postgres_data" != (
        f"{second.project_name}_postgres_data"
    )


def test_rendered_environment_contains_only_isolation_settings(
    tmp_path,
) -> None:
    worktree = tmp_path / "feature"
    worktree.mkdir()
    environment = generate_environment(worktree)

    rendered = render_environment(environment)

    assert f"COMPOSE_PROJECT_NAME={environment.project_name}" in rendered
    assert f"E2E_PORT={environment.ports['E2E_PORT']}" in rendered
    assert "PASSWORD" not in rendered
    assert "API_KEY" not in rendered


def test_environment_file_is_written_beneath_the_selected_worktree(
    tmp_path,
) -> None:
    worktree = tmp_path / "feature"
    worktree.mkdir()
    environment = generate_environment(worktree)

    destination = write_environment(environment, ".env.worktree")

    assert destination == worktree / ".env.worktree"
    assert destination.read_text(encoding="utf-8") == render_environment(
        environment
    )


def test_unsafe_explicit_suffix_is_rejected(tmp_path) -> None:
    with pytest.raises(ValueError, match="suffix"):
        generate_environment(Path(tmp_path), suffix="../../shared")


def test_compose_has_no_fixed_names_and_parameterizes_host_ports() -> None:
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")

    assert "container_name:" not in compose
    for variable in PORT_OFFSETS:
        if variable == "E2E_PORT":
            continue
        assert f"${{{variable}:-" in compose


def test_stack_and_browser_commands_consume_generated_settings() -> None:
    makefile = Path("Makefile").read_text(encoding="utf-8")
    playwright = Path("frontend/playwright.config.ts").read_text(
        encoding="utf-8"
    )

    assert "--env-file $(WORKTREE_ENV)" in makefile
    assert "E2E_PORT=$(E2E_PORT)" in makefile
    assert "process.env.E2E_PORT" in playwright
    assert "--port ${e2ePort}" in playwright
