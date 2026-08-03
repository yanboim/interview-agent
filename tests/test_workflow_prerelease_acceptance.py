"""Static safety properties of the live pre-release acceptance cohort."""

from app.model_routing import explicit_workflow_routes
from scripts.run_workflow_prerelease_acceptance import CASES


def test_live_cohort_is_bounded_and_covers_every_specialist() -> None:
    routes = [explicit_workflow_routes(prompt) for _, prompt in CASES]

    assert len(CASES) == 6
    assert sum(len(item) > 1 for item in routes) >= 2
    assert {route for item in routes for route in item} == {
        "knowledge",
        "interviewer",
        "evaluator",
        "planner",
    }
    assert len({case_id for case_id, _ in CASES}) == len(CASES)


def test_live_report_writer_never_includes_prompts_or_answers() -> None:
    source = __import__(
        "inspect"
    ).getsource(__import__(
        "scripts.run_workflow_prerelease_acceptance",
        fromlist=["main"],
    ).main)

    report_source = source[source.index("report = {") :]
    assert '"prompt"' not in report_source
    assert '"answer"' not in report_source
