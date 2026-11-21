"""OpenTelemetry setup. Off unless OTEL_EXPORTER_OTLP_ENDPOINT is set: without it nothing is
installed, nothing is instrumented and nothing is exported (the metric helpers are no-ops).

When set, traces and metrics go to the OTLP/HTTP endpoint (for example the Grafana
`grafana/otel-lgtm` container: `docker compose --profile observability up -d`, endpoint
http://localhost:4318), and FastAPI, SQLAlchemy, Redis and httpx are instrumented.
"""

import logging
from typing import Any

from app.config import Settings

logger = logging.getLogger("aporia.otel")

_initialized = False
SERVICE_NAME = "aporia-api"


def otel_enabled(settings: Settings) -> bool:
    return bool(settings.otel_exporter_otlp_endpoint.strip())


def init_otel(app: Any, settings: Settings, engine: Any = None) -> bool:
    """Installs providers and instrumentation. Returns whether OpenTelemetry is active.
    Safe to call more than once; never raises (observability must not stop the API)."""
    global _initialized
    if not otel_enabled(settings):
        return False
    if _initialized:
        return True
    try:
        from opentelemetry import metrics, trace
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.instrumentation.redis import RedisInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        endpoint = settings.otel_exporter_otlp_endpoint.rstrip("/")
        resource = Resource.create({"service.name": SERVICE_NAME})
        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces"))
        )
        trace.set_tracer_provider(tracer_provider)
        reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=f"{endpoint}/v1/metrics"), export_interval_millis=15_000
        )
        metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[reader]))

        FastAPIInstrumentor.instrument_app(app)
        if engine is not None:
            SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
        RedisInstrumentor().instrument()
        HTTPXClientInstrumentor().instrument()
        _initialized = True
        logger.info("OpenTelemetry enabled, exporting to %s", endpoint)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("OpenTelemetry could not start: %s", type(exc).__name__)
        return False
