"""FastAPI application — CPAP Analyzer backend."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .models.database import create_db_engine, init_db, get_session_factory
from .api import upload, sessions, analytics, ai

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    settings = get_settings()

    # Ensure upload directory exists
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)

    # Initialize database
    engine = create_db_engine(settings.database_url)
    init_db(engine)
    app.state.db_engine = engine
    app.state.db_session_factory = get_session_factory(engine)
    app.state.settings = settings

    logger.info(f"CPAP Analyzer backend started — uploads: {settings.upload_dir}")
    yield

    # Cleanup
    engine.dispose()


app = FastAPI(
    title="CPAP Analyzer",
    description="Upload and analyze ResMed CPAP data with AI-powered insights",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(upload.router, prefix="/api", tags=["upload"])
app.include_router(sessions.router, prefix="/api", tags=["sessions"])
app.include_router(analytics.router, prefix="/api", tags=["analytics"])
app.include_router(ai.router, prefix="/api/ai", tags=["ai"])


@app.get("/api/health")
async def health():
    return {"status": "ok", "app": "CPAP Analyzer"}
