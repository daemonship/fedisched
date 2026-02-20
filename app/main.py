import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.config import settings
from app.database import create_db_and_tables
from app.api import health, auth, accounts

# Configure logging
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan events for startup and shutdown."""
    # Create database tables on startup
    logger.info("Creating database tables...")
    create_db_and_tables()
    logger.info("Database tables created.")
    yield
    # Cleanup on shutdown
    logger.info("Shutting down...")


app = FastAPI(
    title="Fedisched",
    description="Social Scheduler for Mastodon & Bluesky (Self-Hosted)",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(accounts.router, prefix="/api")

# Serve static files (frontend) in production
# We'll mount the built frontend later
# app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="frontend")


@app.get("/")
async def root():
    return {"message": "Fedisched API is running"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
