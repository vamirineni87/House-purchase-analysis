"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pipa.core.database import healthcheck, init_db
from pipa.core.dependencies import get_engine
from pipa.core.logging import setup_logging


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

    # CORS for frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers
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

    @app.get("/health")
    async def health():
        engine = get_engine()
        db_ok = await healthcheck(engine)
        return {"status": "ok" if db_ok else "degraded", "db": db_ok}

    return app


app = create_app()
