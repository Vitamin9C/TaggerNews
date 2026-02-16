"""FastAPI application entry point."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from taggernews.api.dev import router as dev_router
from taggernews.api.v1.router import router as api_router
from taggernews.api.web.views import router as web_router
from taggernews.config import get_settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler for startup/shutdown."""
    from taggernews.scheduler.jobs import get_scheduler

    logger.info("Starting TaggerNews application...")
    logger.info(f"Environment: {settings.environment}")

    # Startup: initialize scheduler
    scheduler = get_scheduler()
    scheduler.start()

    yield

    # Shutdown: cleanup scheduler
    scheduler.shutdown()
    logger.info("Shutting down TaggerNews application...")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="TaggerNews",
        description="A Modern Hacker News Aggregator with AI-Powered Summaries",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Mount static files
    app.mount("/static", StaticFiles(directory="static"), name="static")

    # Include routers
    app.include_router(api_router)
    app.include_router(web_router)

    # Dev-only router (guarded internally)
    if not settings.is_production:
        app.include_router(dev_router)

    return app


# Create app instance
app = create_app()
