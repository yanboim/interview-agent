"""Request, dependency, product, and model-run metric aggregation."""

import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass

from app.operational_metrics import OperationalMetricInstruments


WORKFLOW_DURATION_BUCKETS = (0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 90.0)
WORKFLOW_NAMES = {"chat-supervisor-v1", "chat-workflow-v2"}
WORKFLOW_OUTCOMES = {"completed", "failed", "cancelled"}


@dataclass
class MetricsSnapshot:
    requests_total: int
    errors_total: int
    active_requests: int
    duration_seconds_total: float


class RequestMetrics:
    def __init__(self, telemetry: OperationalMetricInstruments | None = None) -> None:
        self._requests_total = 0
        self._errors_total = 0
        self._active_requests = 0
        self._duration_seconds_total = 0.0
        self._lock = threading.Lock()
        self._dependencies: dict[str, list[float | int]] = {}
        self._token_usage: dict[str, list[int]] = {}
        self._product_counters: dict[str, float] = {}
        self._product_gauges: dict[str, float] = {}
        self._model_runs: dict[tuple[str, str], list[float]] = {}
        self._workflow_runs: dict[tuple[str, str], int] = {}
        self._workflow_duration: dict[str, list[float | int]] = {}
        self._workflow_cost: dict[str, float] = {}
        self._telemetry = telemetry or OperationalMetricInstruments()

    def start(self) -> float:
        with self._lock:
            self._active_requests += 1
        self._telemetry.request_started()
        return time.monotonic()

    def finish(self, started_at: float, status_code: int) -> None:
        duration = time.monotonic() - started_at
        with self._lock:
            self._active_requests -= 1
            self._requests_total += 1
            self._duration_seconds_total += duration
            if status_code >= 500:
                self._errors_total += 1
        self._telemetry.request_finished(status_code, duration)

    def snapshot(self) -> MetricsSnapshot:
        with self._lock:
            return MetricsSnapshot(
                requests_total=self._requests_total,
                errors_total=self._errors_total,
                active_requests=self._active_requests,
                duration_seconds_total=self._duration_seconds_total,
            )

    def render_prometheus(self) -> str:
        snapshot = self.snapshot()
        lines = [
            "# TYPE interview_agent_requests_total counter",
            f"interview_agent_requests_total {snapshot.requests_total}",
            "# TYPE interview_agent_errors_total counter",
            f"interview_agent_errors_total {snapshot.errors_total}",
            "# TYPE interview_agent_active_requests gauge",
            f"interview_agent_active_requests {snapshot.active_requests}",
            "# TYPE interview_agent_request_duration_seconds_total counter",
            (
                "interview_agent_request_duration_seconds_total "
                f"{snapshot.duration_seconds_total:.6f}"
            ),
        ]
        with self._lock:
            for name, values in sorted(self._dependencies.items()):
                count, errors, duration = values
                lines.extend([
                    f'interview_agent_dependency_calls_total{{dependency="{name}"}} {int(count)}',
                    f'interview_agent_dependency_errors_total{{dependency="{name}"}} {int(errors)}',
                    f'interview_agent_dependency_duration_seconds_total{{dependency="{name}"}} {float(duration):.6f}',
                ])
            for name, values in sorted(self._token_usage.items()):
                input_tokens, output_tokens = values
                lines.extend([
                    f'interview_agent_llm_input_tokens_total{{agent="{name}"}} {input_tokens}',
                    f'interview_agent_llm_output_tokens_total{{agent="{name}"}} {output_tokens}',
                ])
            for name, value in sorted(self._product_counters.items()):
                lines.append(
                    f'interview_agent_product_events_total{{metric="{name}"}} {value:.6f}'
                )
            for name, value in sorted(self._product_gauges.items()):
                lines.append(
                    f'interview_agent_product_quality{{metric="{name}"}} {value:.6f}'
                )
            for (request_class, price_version), values in sorted(self._model_runs.items()):
                runs, calls, input_tokens, output_tokens, cost, wall_ms, first_ms = values
                labels = f'request_class="{request_class}",price_version="{price_version}"'
                lines.extend([
                    f"interview_agent_model_runs_total{{{labels}}} {runs:.0f}",
                    f"interview_agent_model_run_calls_total{{{labels}}} {calls:.0f}",
                    f"interview_agent_model_run_input_tokens_total{{{labels}}} {input_tokens:.0f}",
                    f"interview_agent_model_run_output_tokens_total{{{labels}}} {output_tokens:.0f}",
                    f"interview_agent_model_run_cost_usd_total{{{labels}}} {cost:.8f}",
                    f"interview_agent_model_run_wall_time_ms_total{{{labels}}} {wall_ms:.0f}",
                    f"interview_agent_model_run_first_token_ms_total{{{labels}}} {first_ms:.0f}",
                ])
            for (workflow, outcome), count in sorted(self._workflow_runs.items()):
                labels = f'workflow="{workflow}",outcome="{outcome}"'
                lines.append(
                    f"interview_agent_workflow_runs_total{{{labels}}} {count}"
                )
            for workflow, values in sorted(self._workflow_duration.items()):
                *bucket_counts, count, duration_sum = values
                labels = f'workflow="{workflow}"'
                for upper_bound, bucket_count in zip(
                    WORKFLOW_DURATION_BUCKETS, bucket_counts, strict=True
                ):
                    lines.append(
                        "interview_agent_workflow_duration_seconds_bucket"
                        f'{{{labels},le="{upper_bound:g}"}} {int(bucket_count)}'
                    )
                lines.extend(
                    [
                        "interview_agent_workflow_duration_seconds_bucket"
                        f'{{{labels},le="+Inf"}} {int(count)}',
                        "interview_agent_workflow_duration_seconds_count"
                        f"{{{labels}}} {int(count)}",
                        "interview_agent_workflow_duration_seconds_sum"
                        f"{{{labels}}} {float(duration_sum):.6f}",
                    ]
                )
            for workflow, cost in sorted(self._workflow_cost.items()):
                lines.append(
                    "interview_agent_workflow_cost_usd_total"
                    f'{{workflow="{workflow}"}} {cost:.8f}'
                )
        return "\n".join([*lines, ""])

    @contextmanager
    def dependency(self, name: str):
        started = time.monotonic()
        success = False
        try:
            yield
            success = True
        finally:
            duration = time.monotonic() - started
            with self._lock:
                values = self._dependencies.setdefault(name, [0, 0, 0.0])
                values[0] += 1
                values[1] += int(not success)
                values[2] += duration
            self._telemetry.dependency_finished(name, duration, success=success)

    def observe_tokens(self, agent_name: str, input_tokens: int, output_tokens: int) -> None:
        with self._lock:
            values = self._token_usage.setdefault(agent_name, [0, 0])
            values[0] += max(0, int(input_tokens))
            values[1] += max(0, int(output_tokens))
        self._telemetry.tokens_observed(agent_name, input_tokens, output_tokens)

    def observe_product(self, name: str, value: float = 1.0) -> None:
        with self._lock:
            self._product_counters[name] = self._product_counters.get(name, 0.0) + max(
                0.0, float(value)
            )
        self._telemetry.product_event(name, value)

    def set_product_gauge(self, name: str, value: float) -> None:
        with self._lock:
            self._product_gauges[name] = float(value)
        self._telemetry.product_gauge(name, value)

    def observe_model_run(self, snapshot: dict[str, object]) -> None:
        key = (str(snapshot["request_class"]), str(snapshot["price_version"]))
        with self._lock:
            values = self._model_runs.setdefault(key, [0.0] * 7)
            values[0] += 1
            values[1] += float(snapshot["call_count"])
            values[2] += float(snapshot["input_tokens"])
            values[3] += float(snapshot["output_tokens"])
            values[4] += float(snapshot["cost_usd"])
            values[5] += float(snapshot["wall_time_ms"])
            values[6] += float(snapshot["first_token_ms"] or 0)
        self._telemetry.model_run(snapshot)

    def observe_workflow_run(
        self,
        workflow: str,
        *,
        outcome: str,
        duration_seconds: float,
        cost_usd: float,
    ) -> None:
        """Record one bounded workflow outcome without user-controlled labels."""
        if workflow not in WORKFLOW_NAMES:
            raise ValueError("unsupported workflow metric name")
        if outcome not in WORKFLOW_OUTCOMES:
            raise ValueError("unsupported workflow metric outcome")
        duration = max(0.0, float(duration_seconds))
        cost = max(0.0, float(cost_usd))
        with self._lock:
            key = (workflow, outcome)
            self._workflow_runs[key] = self._workflow_runs.get(key, 0) + 1
            values = self._workflow_duration.setdefault(
                workflow, [0] * len(WORKFLOW_DURATION_BUCKETS) + [0, 0.0]
            )
            for index, upper_bound in enumerate(WORKFLOW_DURATION_BUCKETS):
                if duration <= upper_bound:
                    values[index] += 1
            values[-2] += 1
            values[-1] += duration
            self._workflow_cost[workflow] = (
                self._workflow_cost.get(workflow, 0.0) + cost
            )
        self._telemetry.workflow_run(
            workflow,
            outcome=outcome,
            duration_seconds=duration,
            cost_usd=cost,
        )


request_metrics = RequestMetrics()
