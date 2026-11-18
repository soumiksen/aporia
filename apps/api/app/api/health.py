from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import text

from app.config import get_settings
from app.db import engine

router = APIRouter()


class HealthResponse(BaseModel):
    status: str


class ReadyResponse(BaseModel):
    status: str
    postgres: str
    redis: str


@router.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/readyz", response_model=ReadyResponse)
async def readyz() -> ReadyResponse:
    pg = "ok"
    rd = "ok"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        pg = "error"
    client = Redis.from_url(get_settings().redis_url)
    try:
        await client.ping()  # pyright: ignore[reportGeneralTypeIssues]
    except Exception:
        rd = "error"
    finally:
        await client.aclose()
    if pg != "ok" or rd != "ok":
        raise HTTPException(status_code=503, detail={"postgres": pg, "redis": rd})
    return ReadyResponse(status="ok", postgres=pg, redis=rd)
