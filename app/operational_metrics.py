"""OpenTelemetry instruments for process-safe operational metric export."""

import threading

from opentelemetry import metrics
from opentelemetry.metrics import Meter


class OperationalMetricInstruments:
    """Emit low-cardinality metrics through the configured OTel provider.

    The existing ``RequestMetrics`` adapter keeps its local snapshot for the
    administrator page and its Prometheus compatibility endpoint. These
    instruments are the aggregation path across instances and process restarts.
    Attributes are deliberately limited to bounded operational dimensions.
    """

    def __init__(self, meter: Meter | None = None) -> None:
        meter = meter or metrics.get_meter("interview-agent.operations")
        self.requests = meter.create_counter("interview_agent.requests")
        self.errors = meter.create_counter("interview_agent.errors")
        self.active_requests = meter.create_up_down_counter(
            "interview_agent.active_requests"
        )
        self.request_duration = meter.create_histogram(
            "interview_agent.request.duration",
            unit="s",
        )
        self.dependency_calls = meter.create_counter(
            "interview_agent.dependency.calls"
        )
        self.dependency_errors = meter.create_counter(
            "interview_agent.dependency.errors"
        )
        self.dependency_duration = meter.create_histogram(
            "interview_agent.dependency.duration",
            unit="s",
        )
        self.input_tokens = meter.create_counter(
            "interview_agent.model.input_tokens",
            unit="{token}",
        )
        self.output_tokens = meter.create_counter(
            "interview_agent.model.output_tokens",
            unit="{token}",
        )
        self.product_events = meter.create_counter(
            "interview_agent.product.events"
        )
        self.product_quality = meter.create_up_down_counter(
            "interview_agent.product.quality"
        )
        self.model_runs = meter.create_counter("interview_agent.model.runs")
        self.model_calls = meter.create_counter("interview_agent.model.calls")
        self.model_cost = meter.create_counter(
            "interview_agent.model.cost",
            unit="USD",
        )
        self.model_wall_time = meter.create_histogram(
            "interview_agent.model.wall_time",
            unit="ms",
        )
        self.model_first_token = meter.create_histogram(
            "interview_agent.model.first_token",
            unit="ms",
        )
        self.workflow_runs = meter.create_counter("interview_agent.workflow.runs")
        self.workflow_duration = meter.create_histogram(
            "interview_agent.workflow.duration",
            unit="s",
        )
        self.workflow_cost = meter.create_counter(
            "interview_agent.workflow.cost",
            unit="USD",
        )
        self._product_quality_values: dict[str, float] = {}
        self._product_quality_lock = threading.Lock()

    def request_started(self) -> None:
        self.active_requests.add(1)

    def request_finished(self, status_code: int, duration: float) -> None:
        attributes = {"status_class": f"{status_code // 100}xx"}
        self.active_requests.add(-1)
        self.requests.add(1, attributes)
        if status_code >= 500:
            self.errors.add(1, attributes)
        self.request_duration.record(max(0.0, duration), attributes)

    def dependency_finished(
        self,
        name: str,
        duration: float,
        *,
        success: bool,
    ) -> None:
        attributes = {"dependency": name}
        self.dependency_calls.add(1, attributes)
        if not success:
            self.dependency_errors.add(1, attributes)
        self.dependency_duration.record(max(0.0, duration), attributes)

    def tokens_observed(
        self,
        agent_name: str,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        attributes = {"agent": agent_name}
        self.input_tokens.add(max(0, int(input_tokens)), attributes)
        self.output_tokens.add(max(0, int(output_tokens)), attributes)

    def product_event(self, name: str, value: float) -> None:
        self.product_events.add(max(0.0, float(value)), {"metric": name})

    def product_gauge(self, name: str, value: float) -> None:
        next_value = float(value)
        with self._product_quality_lock:
            previous = self._product_quality_values.get(name, 0.0)
            self._product_quality_values[name] = next_value
        self.product_quality.add(next_value - previous, {"metric": name})

    def model_run(self, snapshot: dict[str, object]) -> None:
        attributes = {
            "request_class": str(snapshot["request_class"]),
            "price_version": str(snapshot["price_version"]),
        }
        self.model_runs.add(1, attributes)
        self.model_calls.add(int(snapshot["call_count"]), attributes)
        self.input_tokens.add(int(snapshot["input_tokens"]), attributes)
        self.output_tokens.add(int(snapshot["output_tokens"]), attributes)
        self.model_cost.add(float(snapshot["cost_usd"]), attributes)
        self.model_wall_time.record(float(snapshot["wall_time_ms"]), attributes)
        first_token = snapshot.get("first_token_ms")
        if first_token is not None:
            self.model_first_token.record(float(first_token), attributes)

    def workflow_run(
        self,
        workflow: str,
        *,
        outcome: str,
        duration_seconds: float,
        cost_usd: float,
    ) -> None:
        attributes = {"workflow": workflow, "outcome": outcome}
        self.workflow_runs.add(1, attributes)
        self.workflow_duration.record(
            duration_seconds,
            {"workflow": workflow},
        )
        self.workflow_cost.add(cost_usd, {"workflow": workflow})
