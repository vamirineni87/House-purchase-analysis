"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from pipa.core.database import healthcheck, init_db
from pipa.core.dependencies import get_engine
from pipa.core.logging import setup_logging

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown."""
    setup_logging()
    engine = get_engine()
    await init_db(engine)

    # Start background scheduler (no-op if another process holds the lock)
    from pipa.workers.scheduler import start_scheduler, stop_scheduler
    await start_scheduler()

    yield

    await stop_scheduler()
    await engine.dispose()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="PIPA — Property Intelligence Platform",
        description="County-backed property research for Fairfax and Loudoun County, VA",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS — narrow to same-origin SPA dev server only
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:8000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── API Routers ──────────────────────────────────────────────────
    from pipa.api.v1.properties import router as properties_router
    from pipa.api.v1.watchlist import router as watchlist_router
    from pipa.api.v1.analysis import router as analysis_router
    from pipa.api.v1.county import router as county_router
    from pipa.api.v1.hoa import router as hoa_router
    from pipa.api.v1.alerts import router as alerts_router
    from pipa.api.v1.documents import router as documents_router
    from pipa.api.v1.notes import router as notes_router
    from pipa.api.v1.comparison import router as comparison_router
    from pipa.api.v1.rates import router as rates_router
    from pipa.api.v1.surrounding import router as surrounding_router
    from pipa.api.v1.decisions import router as decisions_router
    from pipa.api.v1.refresh import router as refresh_router
    from pipa.api.v1.comps import router as comps_router
    from pipa.api.v1.pipeline import router as pipeline_router
    from pipa.api.v1.settings import router as settings_router

    app.include_router(properties_router, prefix="/api/v1")
    app.include_router(watchlist_router, prefix="/api/v1")
    app.include_router(analysis_router, prefix="/api/v1")
    app.include_router(county_router, prefix="/api/v1")
    app.include_router(hoa_router, prefix="/api/v1")
    app.include_router(alerts_router, prefix="/api/v1")
    app.include_router(documents_router, prefix="/api/v1")
    app.include_router(notes_router, prefix="/api/v1")
    app.include_router(comparison_router, prefix="/api/v1")
    app.include_router(rates_router, prefix="/api/v1")
    app.include_router(surrounding_router, prefix="/api/v1")
    app.include_router(decisions_router, prefix="/api/v1")
    app.include_router(refresh_router, prefix="/api/v1")
    app.include_router(comps_router, prefix="/api/v1")
    app.include_router(pipeline_router, prefix="/api/v1")
    app.include_router(settings_router, prefix="/api/v1")

    @app.get("/health")
    async def health():
        engine = get_engine()
        db_ok = await healthcheck(engine)
        return {"status": "ok" if db_ok else "degraded", "db": db_ok}

    # ── Static file serving (AFTER all API routes) ───────────────────
    @app.get("/")
    async def serve_index():
        """Serve the SPA entry point."""
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    return app


app = create_app()
