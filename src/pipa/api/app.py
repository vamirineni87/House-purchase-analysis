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
from pipa.core.logging import setup_logging, install_sqlalchemy_slow_query_listener
from pipa.core.middleware import RequestTimingMiddleware
from pipa.core.tracing import autotrace_package

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown."""
    setup_logging()
    engine = get_engine()
    install_sqlalchemy_slow_query_listener(engine)
    await init_db(engine)

    # Auto-trace all currently-loaded pipa.* modules. This wraps every
    # public function and method in our codebase with entry/exit/duration
    # logging. ORM models / Pydantic schemas are skipped automatically.
    # Run AFTER routers and services have been imported (lifespan startup
    # is invoked after FastAPI route registration) so we catch everything.
    autotrace_package("pipa.services")
    autotrace_package("pipa.clients")
    autotrace_package("pipa.api.v1")
    autotrace_package("pipa.report")

    # Start background scheduler (no-op if another process holds the lock).
    # Importing the scheduler module loads pipa.workers.* — we re-run
    # autotrace for that prefix afterwards so the worker callables get
    # wrapped too.
    from pipa.workers.scheduler import start_scheduler, stop_scheduler
    autotrace_package("pipa.workers")
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

    # Request timing & logging — added FIRST so it wraps everything,
    # including the static-file no-cache middleware below.
    app.add_middleware(RequestTimingMiddleware)

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
    from pipa.api.v1.market import router as market_router

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
    app.include_router(market_router, prefix="/api/v1")

    @app.get("/health")
    async def health():
        engine = get_engine()
        db_ok = await healthcheck(engine)
        return {"status": "ok" if db_ok else "degraded", "db": db_ok}

    # ── No-cache for JS files during development ─────────────────────
    @app.middleware("http")
    async def no_cache_js(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static/js/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        return response

    # ── Static file serving (AFTER all API routes) ───────────────────
    @app.get("/")
    async def serve_index():
        """Serve the SPA entry point."""
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    return app


app = create_app()
