"""API v1 router aggregator."""

from fastapi import APIRouter

from taggernews.api.v1.agents import router as agents_router
from taggernews.api.v1.stories import router as stories_router
from taggernews.config import get_settings

router = APIRouter(prefix="/api/v1")
router.include_router(stories_router)
settings = get_settings()

if not settings.is_production:
    router.include_router(agents_router)
