from fastapi import FastAPI

from app.api import attempts, events, health, hint, internal
from app.config import get_settings
from app.observability import init_sentry

init_sentry(get_settings())  # no-op without SENTRY_DSN

app = FastAPI(title="Aporia API", version="0.1.0")
app.include_router(health.router)
app.include_router(hint.router)
app.include_router(internal.router)
app.include_router(events.router)
app.include_router(attempts.router)
