import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import settings
from app.db.session import init_db, AsyncSessionLocal
from app.api.cdc import router as cdc_router
from app.services.poller import poller

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("CDMS_Backend")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for CDMS application."""
    logger.info("Initializing CDMS Database tables...")
    try:
        await init_db()
        logger.info("Database tables initialized successfully.")
    except Exception as e:
        logger.error(f"Error initializing database: {e}", exc_info=True)

    # Start Scheduled Poller background task
    logger.info("Starting Scheduled Poller background worker...")
    poller.start()

    yield

    # Shutdown
    logger.info("Stopping Scheduled Poller...")
    await poller.stop()
    logger.info("CDMS Shutdown complete.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Change Data Management Service (CDMS) - Capture, Deduplicate, and Store Only Changed Data.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Routers
app.include_router(cdc_router, prefix=settings.API_V1_STR)


@app.get("/health", tags=["System"])
async def health_check():
    """Health check validating PostgreSQL connectivity and Poller status."""
    db_healthy = False
    try:
        async with AsyncSessionLocal() as session:
            res = await session.execute(text("SELECT 1"))
            if res.scalar() == 1:
                db_healthy = True
    except Exception as e:
        logger.error(f"Health check DB probe failed: {e}")

    return {
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "healthy" if db_healthy else "degraded",
        "database_connected": db_healthy,
        "poller": poller.get_status()
    }
