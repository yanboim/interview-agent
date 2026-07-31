"""OpenTelemetry 可选初始化；观测后端不可用时不影响请求正确性。"""

import logging

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


logger = logging.getLogger(__name__)


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
    provider = TracerProvider(
        resource=Resource.create({"service.name": service_name})
    )
    if endpoint:
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint))
        )
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
    SQLAlchemyInstrumentor().instrument(engine=engine)
    logger.info("OpenTelemetry instrumentation enabled")
