import hmac

from fastapi import APIRouter, Depends, Header, HTTPException

from app.config import Settings, get_settings
from app.reference.queue import Enqueue, get_enqueue
from app.schemas.hint import ProblemContext

router = APIRouter(prefix="/v1/internal")


async def require_internal(
    x_aporia_internal: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    """Open outside production; in production a matching internal token is required."""
    if settings.aporia_env != "production":
        return
    token = settings.aporia_internal_token
    if not token or not x_aporia_internal or not hmac.compare_digest(x_aporia_internal, token):
        raise HTTPException(status_code=403, detail="forbidden")


@router.post("/reference/{slug}", status_code=202, dependencies=[Depends(require_internal)])
async def enqueue_reference_build(
    slug: str, problem: ProblemContext, enqueue: Enqueue = Depends(get_enqueue)
) -> dict[str, bool]:
    payload = problem.model_dump()
    payload["slug"] = slug
    return {"enqueued": await enqueue(slug, payload)}
