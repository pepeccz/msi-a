"""
MSI Automotive - FastAPI API Service Entry Point
"""

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from passlib.hash import bcrypt
from sqlalchemy import select, func

from api.routes import admin, chatwoot, images, tariffs, public_tariffs, system, regulatory_documents, rag_query, elements
from database.connection import get_async_session
from database.models import AdminUser
from database.seeds.run_all_seeds import run_all_seeds
from shared.config import get_settings
from shared.logging_config import configure_logging

# Configure structured JSON logging on startup
configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="MSI Automotive API",
    description="API for MSI Automotive WhatsApp agent and admin panel",
    version="1.0.0",
)

# Load settings for CORS configuration
settings = get_settings()
origins = settings.CORS_ORIGINS.split(",")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
)

# Include webhook routers
app.include_router(chatwoot.router, prefix="/webhook", tags=["webhooks"])

# Include admin panel router
app.include_router(admin.router, tags=["admin"])

# Include tariff management router
app.include_router(tariffs.router, tags=["tariffs"])

# Include public tariff API for agent
app.include_router(public_tariffs.router, tags=["public-tariffs"])

# Include system management router
app.include_router(system.router, tags=["system"])

# Include image management router (admin protected)
app.include_router(images.router, prefix="/api/admin", tags=["images"])

# Include public image serving router (no auth)
app.include_router(
    images.get_public_image_router(),
    prefix="/images",
    tags=["public-images"]
)

# Include RAG regulatory documents router
app.include_router(regulatory_documents.router, tags=["regulatory-documents"])

# Include RAG query router
app.include_router(rag_query.router, tags=["rag"])

# Include elements router
app.include_router(elements.router, tags=["elements"])


async def seed_admin_user():
    """Seed initial admin user if none exists."""
    async with get_async_session() as session:
        # Check if any admin users exist
        result = await session.execute(select(func.count(AdminUser.id)))
        count = result.scalar() or 0

        if count == 0:
            # Get credentials from env
            username = settings.ADMIN_USERNAME
            password = settings.ADMIN_PASSWORD

            if username and password:
                password_hash = bcrypt.hash(password)

                admin = AdminUser(
                    username=username.lower(),
                    password_hash=password_hash,
                    role="admin",
                    display_name="Administrador",
                )
                session.add(admin)
                await session.commit()
                logger.info(f"Seeded initial admin user: {username}")
            else:
                logger.warning("No ADMIN_USERNAME/ADMIN_PASSWORD set, skipping admin seed")


@app.on_event("startup")
async def startup_event():
    """Log startup information and seed initial data."""
    logger.info(f"Starting {settings.PROJECT_NAME} API...")
    logger.info(f"Environment: {settings.ENVIRONMENT}")

    # Seed admin user if table is empty
    try:
        await seed_admin_user()
    except Exception as e:
        logger.error(f"Failed to seed admin user: {e}")

    # Seed tariff data (categories, tiers, elements)
    try:
        await run_all_seeds()
    except Exception as e:
        logger.error(f"Failed to seed data: {e}")


# Exception handler for validation errors
@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: ValidationError) -> JSONResponse:
    """Return 400 with validation error details."""
    return JSONResponse(
        status_code=400,
        content={"error": "Validation error", "details": exc.errors()},
    )


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Global exception handler that ensures CORS headers are present.
    """
    logger.error(f"Unhandled exception: {exc}", exc_info=True)

    # Get CORS origins from settings
    settings_exc = get_settings()
    origins = settings_exc.CORS_ORIGINS.split(",")

    # Get origin from request
    origin = request.headers.get("origin", "")

    # Build response
    response = JSONResponse(
        status_code=500,
        content={"error": "Internal server error"},
    )

    # Add CORS headers if origin is allowed
    if origin in origins or "*" in origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"

    return response


@app.get("/health")
async def health_check() -> JSONResponse:
    """
    Health check endpoint for Docker health checks and monitoring.

    Checks:
    - Redis connectivity (PING command)
    - PostgreSQL connectivity (SELECT 1 query)

    Returns:
        200 OK if all systems healthy
        503 Service Unavailable if degraded
    """
    from sqlalchemy import text

    from database.connection import get_async_session
    from shared.redis_client import get_redis_client

    health_status = {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "redis": "unknown",
        "postgres": "unknown",
    }
    status_code = 200

    # Check Redis connectivity
    try:
        redis_client = get_redis_client()
        await redis_client.ping()
        health_status["redis"] = "connected"
    except Exception:
        health_status["redis"] = "disconnected"
        health_status["status"] = "degraded"
        status_code = 503

    # Check PostgreSQL connectivity
    try:
        async with get_async_session() as session:
            await session.execute(text("SELECT 1"))
            health_status["postgres"] = "connected"
    except Exception:
        health_status["postgres"] = "disconnected"
        health_status["status"] = "degraded"
        status_code = 503

    return JSONResponse(status_code=status_code, content=health_status)


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint"""
    return {
        "message": f"{settings.PROJECT_NAME} API",
        "version": "1.0.0",
        "health": "/health",
    }
