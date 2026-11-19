from fastapi import FastAPI

from app.api import health, hint, internal

app = FastAPI(title="Aporia API", version="0.1.0")
app.include_router(health.router)
app.include_router(hint.router)
app.include_router(internal.router)
