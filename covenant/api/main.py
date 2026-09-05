"""FastAPI Application Entrypoint for Covenant."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from covenant.api.routes import repo, router, supervisor
from covenant.agents.base import AgentContext
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

app.include_router(router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("covenant.api.main:app", host="0.0.0.0", port=8000, reload=True)
