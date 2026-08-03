"""OpenTelemetry 配置的测试。"""

from pathlib import Path

from app.telemetry import _signal_endpoint


ROOT = Path(__file__).resolve().parents[1]


def test_signal_endpoint_replaces_existing_otlp_signal_path() -> None:
    configured = "http://otel-collector:4318/v1/traces"

    assert _signal_endpoint(configured, "traces") == configured
    assert (
        _signal_endpoint(configured, "metrics")
        == "http://otel-collector:4318/v1/metrics"
    )


def test_bundled_collector_accepts_traces_and_metrics() -> None:
    config = (ROOT / "monitoring" / "otel-collector.yml").read_text(
        encoding="utf-8"
    )

    assert "    traces:\n" in config
    assert "    metrics:\n" in config
