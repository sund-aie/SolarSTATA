"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import data, health, stats
from .config import settings
from .session.middleware import SessionMiddleware
from .session.store import session_store


@asynccontextmanager
async def lifespan(app: FastAPI):
    eviction_task = await session_store.start_eviction_loop(
        settings.session_eviction_interval_seconds,
        settings.session_idle_timeout_seconds,
    )
    try:
        yield
    finally:
        eviction_task.cancel()


app = FastAPI(
    title="SolarSTATA",
    version="3.0.0a1",
    description="Point-and-click Stata replica — backend",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(SessionMiddleware)

app.include_router(health.router)
app.include_router(data.router, prefix="/api")
app.include_router(stats.router, prefix="/api")
