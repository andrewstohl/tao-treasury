"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1 import router as api_router
from app.core.database import init_db, close_db
from app.core.redis import close_redis
from app.core.scheduler import start_scheduler, stop_scheduler

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting TAO Treasury Management API", version=__version__)

    # Initialize database tables
    await init_db()
    logger.info("Database initialized")

    # Start background scheduler for automatic data sync
    start_scheduler()

    yield

    # Shutdown
    logger.info("Shutting down...")
    stop_scheduler()
    await close_db()
    await close_redis()
    logger.info("Cleanup complete")


# Create FastAPI app
app = FastAPI(
    title="TAO Treasury Management API",
    description="API for managing TAO treasury across Root and dTAO subnets",
    version=__version__,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3050",
        "http://127.0.0.1:3050",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
app.include_router(api_router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "TAO Treasury Management API",
        "version": __version__,
        "docs": "/api/docs",
        "health": "/api/v1/health",
    }
