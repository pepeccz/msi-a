"""
MSI Automotive - FastAPI API Service Entry Point
"""

import asyncio
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from passlib.hash import bcrypt
from sqlalchemy import select, func

from api.routes import admin, billing, cases, chatwoot, conversation_images, conversations_admin, images, tariffs, public_tariffs, system, elements, token_usage, conversation_messages
from database.connection import get_async_session
from database.models import AdminUser

from shared.config import get_settings
from shared.logging_config import configure_logging
from shared.fastapi_errors import register_error_handlers

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

# Register unified error handlers
register_error_handlers(app)

# Include webhook routers
app.include_router(chatwoot.router, prefix="/webhook", tags=["webhooks"])

# Include unified inbox router BEFORE admin router so its specific paths
# (e.g. /api/admin/conversations/templates) match before admin.router's
# generic /conversations/{conversation_id:UUID} catches them and 422s.
app.include_router(conversations_admin.router, tags=["conversations-admin"])

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

# Include case images public serving router (no auth)
app.include_router(
    images.get_case_images_router(),
    prefix="/case-images",
    tags=["case-images"]
)

# Include conversation images serving router (auth required — JWT cookie)
app.include_router(conversation_images.router, tags=["conversation-images"])

# Include elements router
app.include_router(elements.router, tags=["elements"])

# Include cases (expedientes) router
app.include_router(cases.router, tags=["cases"])

# Include token usage tracking router
app.include_router(token_usage.router, tags=["token-usage"])

# Include billing router (invoices, payments, Stripe, fiscal details)
app.include_router(billing.router, tags=["billing"])

# Include conversation messages router
app.include_router(conversation_messages.router, tags=["conversation-messages"])

# conversations_admin.router is registered earlier (above admin.router)
# to avoid path-shadowing on /conversations/templates etc.

# Include validation metrics router (Phase 5: monitoring)
from api.routes import validation_metrics
app.include_router(validation_metrics.router, tags=["validation-metrics"])


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
                logger.warning(
                    "admin_password_deprecated: ADMIN_PASSWORD plaintext is deprecated. "
                    "Set ADMIN_PASSWORD_HASH instead. See .env.example for ADMIN_PASSWORD_HASH usage."
                )
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

    # NOTE: Seeds are now manual only. Run: python -m database.seeds.run_all_seeds

    # Initialize compiled LangGraph once and store on app.state.
    # Endpoints requiring the graph (pause/resume/send-message) will return 503
    # if this initialization fails (R1 risk mitigation, Design PR4).
    try:
        from agent.graph.conversation_graph import create_compiled_graph
        from agent.state.checkpointer import get_redis_checkpointer, initialize_redis_indexes

        checkpointer = get_redis_checkpointer()
        await initialize_redis_indexes(checkpointer)
        app.state.compiled_graph = await create_compiled_graph(checkpointer)
        logger.info("compiled_graph_initialized")
    except Exception as exc:
        logger.error(
            "compiled_graph_init_failed",
            extra={"error": str(exc)},
            exc_info=True,
        )
        app.state.compiled_graph = None

    # Start billing background worker
    from api.workers import billing_worker
    asyncio.create_task(billing_worker.run())

    # Start attachment download worker
    from api.workers import attachment_download_worker
    asyncio.create_task(attachment_download_worker.run())


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown."""
    logger.info("Shutting down API...")

    from api.workers import billing_worker
    await billing_worker.shutdown()

    from api.workers import attachment_download_worker
    await attachment_download_worker.shutdown()


# Exception handlers are now registered via register_error_handlers()
# See shared/fastapi_errors.py for implementation


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
