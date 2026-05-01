"""
Cookie Cutters Staff Scheduling API

A multi-project FastAPI platform backed by Snowflake.
This is the main entry point — register new project routers here.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from app.config import get_settings
from app.db.snowflake import get_pool
import logging
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("Starting Cookie Cutters API...")
    logger.info("Environment: %s", get_settings().app_env)
    yield
    # Shutdown: close all Snowflake connections
    logger.info("Shutting down — closing Snowflake connections...")
    get_pool().close_all()


app = FastAPI(
    title="Cookie Cutters API",
    description="Staff scheduling platform for Cookie Cutters Haircuts for Kids",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow your frontend origins
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# Register routers
# Each project gets its own router module. To add a new project:
#   1. Create app/routers/your_project.py
#   2. Import and include it here
# =============================================================================

from app.routers import health, users, shifts, time_off, templates, admin, autoschedule

# Core
app.include_router(health.router)

# Scheduling project (Cookie Cutters)
app.include_router(users.router)
app.include_router(shifts.router)
app.include_router(time_off.router)
app.include_router(templates.router)
app.include_router(admin.router)
app.include_router(autoschedule.router)

# Future: AI Analytics project
# from app.routers import analytics
# app.include_router(analytics.router)


@app.get("/")
async def root():
    """Serve the frontend app."""
    static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
    return FileResponse(os.path.join(static_dir, "index.html"))
