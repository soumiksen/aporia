from fastapi import FastAPI

from app.api import attempts, events, health, hint, internal
from app.config import get_settings
from app.db import engine
from app.llm import calls as llm_calls
from app.observability import init_sentry
from app.telemetry.metrics import get_metrics
from app.telemetry.otel import init_otel

init_sentry(get_settings())  # no-op without SENTRY_DSN

app = FastAPI(title="Aporia API", version="0.1.0")
init_otel(app, get_settings(), engine)  # no-op unless OTEL_EXPORTER_OTLP_ENDPOINT is set
llm_calls.add_hook(lambda rec: get_metrics().observe_cost(rec.cost_usd, rec.purpose))
app.include_router(health.router)
app.include_router(hint.router)
app.include_router(internal.router)
app.include_router(events.router)
app.include_router(attempts.router)
