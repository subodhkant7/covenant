"""FastAPI Application Entrypoint for Covenant."""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from covenant.api.routes import repo, router, supervisor
from covenant.agents.base import AgentContext
from covenant.config import PROJECT_ROOT, settings
from covenant.orchestration.background_monitor import BackgroundMonitor

# Instantiate background monitor
background_monitor = BackgroundMonitor(
    supervisor=supervisor,
    commitment_repo=repo,
    event_repo=repo,
    interval_seconds=10,  # Runs scan cycle every 10 seconds in local runtime
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup & shutdown events."""
    # 1. Initialize database tables
    await repo.initialize()
    
    # 2. Auto-seed if database is empty
    count = await repo.count()
    if count == 0:
        ctx = AgentContext(session_id="startup_initialization")
        await supervisor.run(ctx)

    # 3. Start autonomous Background Monitor loop
    background_monitor.start()

    yield

    # 4. Graceful shutdown of background monitor
    await background_monitor.stop()


app = FastAPI(
    title="Covenant API",
    description="Autonomous commitment-resolution agent system for professional services.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include backend API routes
app.include_router(router)


def get_frontend_dist() -> Optional[Path]:
    """Resolve production frontend dist directory."""
    if os.environ.get("COVENANT_FRONTEND_DIST"):
        explicit = Path(os.environ["COVENANT_FRONTEND_DIST"])
        if explicit.is_dir() and (explicit / "index.html").is_file():
            return explicit.resolve()
        return None

    candidates = [
        Path("/app/frontend/dist"),
        PROJECT_ROOT / "frontend" / "dist",
        Path.cwd() / "frontend" / "dist",
    ]
    for candidate in candidates:
        if candidate and candidate.is_dir() and (candidate / "index.html").is_file():
            return candidate.resolve()
    return None


@app.get("/", include_in_schema=False)
@app.get("/{full_path:path}", include_in_schema=False)
async def serve_spa(full_path: str = ""):
    """Serve production frontend Single Page Application (SPA)."""
    # Never intercept API, OpenAPI, or docs routes
    if full_path.startswith("api/") or full_path == "api" or full_path in ("docs", "redoc", "openapi.json"):
        raise HTTPException(status_code=404, detail="Not Found")

    dist_dir = get_frontend_dist()
    if not dist_dir or not (dist_dir / "index.html").is_file():
        raise HTTPException(
            status_code=404,
            detail="Frontend production build not found at frontend/dist. Run 'npm run build' inside frontend/ directory."
        )

    # If a specific static asset directly inside dist is requested (e.g. assets/..., vite.svg, favicon.ico)
    if full_path:
        requested_file = (dist_dir / full_path).resolve()
        if requested_file.is_file() and requested_file.is_relative_to(dist_dir):
            return FileResponse(requested_file)

    return FileResponse(dist_dir / "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("covenant.api.main:app", host=settings.host, port=settings.port, reload=True)
