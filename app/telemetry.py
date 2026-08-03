"""OpenTelemetry 可选初始化；观测后端不可用时不影响请求正确性。"""

import logging
from urllib.parse import urlsplit, urlunsplit

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


logger = logging.getLogger(__name__)


def _signal_endpoint(endpoint: str, signal: str) -> str:
    """Derive a sibling OTLP/HTTP signal endpoint from configured trace URL."""

    if not endpoint:
        return ""
    parsed = urlsplit(endpoint)
    path = parsed.path.rstrip("/")
    for suffix in ("/v1/traces", "/v1/metrics"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
            break
    return urlunsplit(parsed._replace(path=f"{path}/v1/{signal}"))


def configure_telemetry(
    app,
    engine,
    *,
    enabled: bool,
    service_name: str,
    endpoint: str,
) -> None:
    if not enabled:
        return
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    if endpoint:
        provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=_signal_endpoint(endpoint, "traces"))
            )
        )
        metrics.set_meter_provider(
            MeterProvider(
                resource=resource,
                metric_readers=[
                    PeriodicExportingMetricReader(
                        OTLPMetricExporter(
                            endpoint=_signal_endpoint(endpoint, "metrics")
                        )
                    )
                ],
            )
        )
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
    SQLAlchemyInstrumentor().instrument(engine=engine)
    logger.info("OpenTelemetry trace and metric instrumentation enabled")
