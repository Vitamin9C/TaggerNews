"""API v1 router aggregator."""

from fastapi import APIRouter

from taggernews.api.v1.stories import router as stories_router

router = APIRouter(prefix="/api/v1")
router.include_router(stories_router)
