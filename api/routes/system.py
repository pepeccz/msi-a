"""
System Management API Endpoints for Admin Panel

Provides REST endpoints for:
- GET /api/admin/system/services - List all services with status
- GET /api/admin/system/{service}/logs - Stream logs (SSE)
- POST /api/admin/system/{service}/restart - Restart service
- POST /api/admin/system/{service}/stop - Stop service
- POST /api/admin/system/cache/clear - Clear Redis cache
"""

import asyncio
import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

from api.routes.admin import get_current_user, verify_token
from database.models import AdminUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/system", tags=["system"])

# Docker API configuration
DOCKER_API_VERSION = "v1.44"
DOCKER_SOCKET = "/var/run/docker.sock"
DOCKER_TCP_HOST = os.environ.get("DOCKER_HOST", "tcp://host.docker.internal:2375")


def get_docker_connection_type() -> tuple[str, str | None]:
    """
    Determine how to connect to Docker.

    Returns tuple of (type, base_url).
    Type can be: 'socket', 'tcp', or 'none'.
    """
    # First try Unix socket (Linux / Docker Desktop WSL2)
    socket_path = Path(DOCKER_SOCKET)
    if socket_path.exists() and os.access(DOCKER_SOCKET, os.R_OK | os.W_OK):
        return ("socket", "http://docker")

    # Fallback to TCP (Windows Docker Desktop with TCP enabled)
    docker_host = os.environ.get("DOCKER_HOST", "")
    if docker_host.startswith("tcp://"):
        tcp_url = docker_host.replace("tcp://", "http://")
        return ("tcp", tcp_url)

    return ("none", None)


def is_docker_available() -> bool:
    """Check if Docker is accessible (via socket or TCP)."""
    conn_type, _ = get_docker_connection_type()
    return conn_type != "none"


def create_docker_client(timeout: float | None = 10.0) -> httpx.AsyncClient | None:
    """
    Create a fresh httpx client configured for Docker API.

    IMPORTANT: Always create a new client for each request to avoid transport issues.
    """
    conn_type, base_url = get_docker_connection_type()

    if conn_type == "none":
        return None

    if conn_type == "socket":
        # Create fresh transport for each client
        transport = httpx.AsyncHTTPTransport(uds=DOCKER_SOCKET)
        return httpx.AsyncClient(
            transport=transport,
            base_url=base_url,
            timeout=timeout
        )
    else:
        # TCP connection
        return httpx.AsyncClient(base_url=base_url, timeout=timeout)

# Service to container name mapping for MSI-A
CONTAINER_MAP = {
    "api": "msia-api",
    "agent": "msia-agent",
    "postgres": "msia-postgres",
    "redis": "msia-redis",
    "admin-panel": "msia-admin-panel",
    "ollama": "msia-ollama",
    "qdrant": "msia-qdrant",
    "document-processor": "msia-document-processor",
}

# Services that can be controlled (all mapped services)
CONTROLLABLE_SERVICES = list(CONTAINER_MAP.keys())


# =============================================================================
# Pydantic Models
# =============================================================================


class ServiceStatus(BaseModel):
    """Status of a single service."""
    name: str
    container: str
    status: str  # running, exited, paused, etc.
    health: str | None = None  # healthy, unhealthy, starting, none


class ServicesResponse(BaseModel):
    """Response with all services status."""
    services: list[ServiceStatus]


class ServiceActionResponse(BaseModel):
    """Response for service actions (restart/stop)."""
    success: bool
    message: str


# =============================================================================
# Helper Functions
# =============================================================================


async def get_container_status(container_name: str) -> dict:
    """Get container status via Docker API."""
    client = create_docker_client()
    if not client:
        return {"status": "docker_unavailable", "health": None}

    try:
        async with client:
            response = await client.get(
                f"/{DOCKER_API_VERSION}/containers/{container_name}/json",
                timeout=10.0,
            )
            if response.status_code == 200:
                data = response.json()
                state = data.get("State", {})
                health = state.get("Health", {}).get("Status") if "Health" in state else None
                return {
                    "status": state.get("Status", "unknown"),
                    "health": health,
                }
            elif response.status_code == 404:
                return {"status": "not_found", "health": None}
            else:
                return {"status": "error", "health": None}
    except Exception as e:
        logger.error(f"Error getting container status for {container_name}: {e}")
        return {"status": "error", "health": None}


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/docker-status")
async def docker_status(
    current_user: Annotated[dict, Depends(get_current_user)],
) -> JSONResponse:
    """
    Check Docker connectivity.

    Returns status information about Docker connectivity.
    """
    conn_type, base_url = get_docker_connection_type()
    socket_exists = Path(DOCKER_SOCKET).exists()

    return JSONResponse(content={
        "available": conn_type != "none",
        "connection_type": conn_type,
        "socket_path": DOCKER_SOCKET,
        "socket_exists": socket_exists,
        "docker_host_env": os.environ.get("DOCKER_HOST", ""),
        "message": (
            f"Docker disponible via {conn_type}" if conn_type != "none"
            else "Docker no accesible. Opciones: 1) Monta docker.sock en docker-compose, "
                 "2) Define DOCKER_HOST=tcp://host.docker.internal:2375"
        )
    })


@router.get("/services", response_model=ServicesResponse)
async def list_services(
    current_user: Annotated[dict, Depends(get_current_user)],
) -> ServicesResponse:
    """
    List all services with their current status.

    Returns container status and health for each service.
    """
    services = []

    # Fetch status for all containers in parallel
    tasks = [
        get_container_status(container)
        for container in CONTAINER_MAP.values()
    ]
    results = await asyncio.gather(*tasks)

    for (service_name, container_name), status_info in zip(CONTAINER_MAP.items(), results):
        services.append(ServiceStatus(
            name=service_name,
            container=container_name,
            status=status_info["status"],
            health=status_info["health"],
        ))

    return ServicesResponse(services=services)


@router.get("/{service}/logs")
async def stream_logs(
    service: str,
    tail: int = 100,
    token: str | None = None,
):
    """
    Stream logs from a service container using Server-Sent Events (SSE).

    Uses Docker API to stream logs in real-time.

    Note: Accepts token as query param because EventSource doesn't support headers.
    """
    # Verify authentication via query param (EventSource doesn't support headers)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token required for log streaming",
        )

    try:
        payload = verify_token(token)
        username = payload.get("sub", "unknown")
    except HTTPException:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    if service not in CONTAINER_MAP:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service not found: {service}. Available: {list(CONTAINER_MAP.keys())}"
        )

    # Check Docker availability early
    if not is_docker_available():
        logger.warning("Docker socket not available for log streaming")
        # Return a simple SSE response with error message
        async def docker_unavailable():
            yield "data: Error: Docker socket no disponible. En Windows, habilita 'Expose daemon on tcp://localhost:2375' en Docker Desktop o usa WSL2.\n\n"
        return StreamingResponse(
            docker_unavailable(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
        )

    container_name = CONTAINER_MAP[service]
    logger.info(f"Starting log stream for {container_name} requested by {username}")

    conn_type, base_url = get_docker_connection_type()

    async def generate_logs():
        """Generator that streams Docker logs via Docker API."""
        try:
            # Create fresh client and transport inside the generator
            if conn_type == "socket":
                transport = httpx.AsyncHTTPTransport(uds=DOCKER_SOCKET)
                client = httpx.AsyncClient(
                    transport=transport,
                    base_url=base_url,
                    timeout=httpx.Timeout(connect=10.0, read=None, write=None, pool=None)
                )
            else:
                client = httpx.AsyncClient(
                    base_url=base_url,
                    timeout=httpx.Timeout(connect=10.0, read=None, write=None, pool=None)
                )

            async with client:
                # Docker logs API with follow and tail
                async with client.stream(
                    "GET",
                    f"/{DOCKER_API_VERSION}/containers/{container_name}/logs",
                    params={
                        "follow": "true",
                        "stdout": "true",
                        "stderr": "true",
                        "tail": str(tail),
                        "timestamps": "true",
                    },
                ) as response:
                    if response.status_code != 200:
                        error_text = await response.aread()
                        logger.error(f"Docker logs API error: {response.status_code} - {error_text}")
                        yield f"data: Error: Docker API respondio con {response.status_code}\n\n"
                        return

                    async for chunk in response.aiter_bytes():
                        if chunk:
                            # Docker logs have 8-byte header per frame
                            try:
                                pos = 0
                                while pos < len(chunk):
                                    if pos + 8 > len(chunk):
                                        break
                                    # Header: 1 byte stream type, 3 bytes padding, 4 bytes size
                                    size = int.from_bytes(chunk[pos+4:pos+8], 'big')
                                    if pos + 8 + size > len(chunk):
                                        break
                                    frame_data = chunk[pos+8:pos+8+size]
                                    line = frame_data.decode('utf-8', errors='replace').strip()
                                    if line:
                                        # Escape newlines for SSE
                                        escaped_line = line.replace('\n', '\\n')
                                        yield f"data: {escaped_line}\n\n"
                                    pos += 8 + size
                            except Exception:
                                # Fallback: decode entire chunk
                                try:
                                    text = chunk.decode('utf-8', errors='replace').strip()
                                    if text:
                                        yield f"data: {text}\n\n"
                                except:
                                    pass

        except httpx.ConnectError as e:
            logger.error(f"Docker connection error: {e}")
            yield f"data: Error: No se puede conectar a Docker daemon\n\n"
        except Exception as e:
            logger.error(f"Log streaming error: {type(e).__name__}: {e}")
            yield f"data: Error: {str(e)}\n\n"

    return StreamingResponse(
        generate_logs(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


@router.post("/{service}/restart", response_model=ServiceActionResponse)
async def restart_service(
    service: str,
    current_user: AdminUser = Depends(get_current_user),
) -> ServiceActionResponse:
    """
    Restart a service container.

    Uses Docker API to restart the container.
    """
    if service not in CONTROLLABLE_SERVICES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service not found: {service}. Available: {CONTROLLABLE_SERVICES}"
        )

    if not is_docker_available():
        return ServiceActionResponse(
            success=False,
            message="Docker socket no disponible. En Windows, habilita Docker socket en Docker Desktop."
        )

    container_name = CONTAINER_MAP[service]
    username = current_user.username
    logger.info(f"Service restart requested: {container_name} by {username}")

    try:
        client = create_docker_client()
        if not client:
            return ServiceActionResponse(
                success=False,
                message="No se pudo crear cliente Docker"
            )

        async with client:
            response = await client.post(
                f"/{DOCKER_API_VERSION}/containers/{container_name}/restart",
                timeout=60.0,
            )

        if response.status_code == 204:
            logger.info(f"Service {container_name} restarted successfully")
            return ServiceActionResponse(
                success=True,
                message=f"Servicio '{service}' reiniciado correctamente"
            )
        elif response.status_code == 404:
            logger.error(f"Container not found: {container_name}")
            return ServiceActionResponse(
                success=False,
                message=f"Contenedor '{container_name}' no encontrado"
            )
        else:
            error_detail = response.text
            logger.error(f"Docker API error: {response.status_code} - {error_detail}")
            return ServiceActionResponse(
                success=False,
                message=f"Error Docker API: {response.status_code}"
            )

    except httpx.ConnectError:
        logger.error("Cannot connect to Docker daemon")
        return ServiceActionResponse(
            success=False,
            message="No se puede conectar al Docker daemon"
        )
    except httpx.TimeoutException:
        logger.error("Service restart timed out")
        return ServiceActionResponse(
            success=False,
            message="Timeout al reiniciar servicio (>60s)"
        )
    except Exception as e:
        logger.error(f"Service restart error: {e}")
        return ServiceActionResponse(
            success=False,
            message=f"Error inesperado: {str(e)}"
        )


@router.post("/{service}/stop", response_model=ServiceActionResponse)
async def stop_service(
    service: str,
    current_user: AdminUser = Depends(get_current_user),
) -> ServiceActionResponse:
    """
    Stop a service container.

    Uses Docker API to stop the container.
    WARNING: This will stop the service until manually restarted.
    """
    if service not in CONTROLLABLE_SERVICES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service not found: {service}. Available: {CONTROLLABLE_SERVICES}"
        )

    # Extra protection: don't allow stopping critical services easily
    if service == "api":
        return ServiceActionResponse(
            success=False,
            message="No se puede detener la API desde el panel (se perderia la conexion)"
        )

    if not is_docker_available():
        return ServiceActionResponse(
            success=False,
            message="Docker socket no disponible. En Windows, habilita Docker socket en Docker Desktop."
        )

    container_name = CONTAINER_MAP[service]
    username = current_user.username
    logger.warning(f"Service STOP requested: {container_name} by {username}")

    try:
        client = create_docker_client()
        if not client:
            return ServiceActionResponse(
                success=False,
                message="No se pudo crear cliente Docker"
            )

        async with client:
            response = await client.post(
                f"/{DOCKER_API_VERSION}/containers/{container_name}/stop",
                timeout=30.0,
            )

        if response.status_code == 204:
            logger.info(f"Service {container_name} stopped successfully")
            return ServiceActionResponse(
                success=True,
                message=f"Servicio '{service}' detenido correctamente"
            )
        elif response.status_code == 304:
            return ServiceActionResponse(
                success=True,
                message=f"Servicio '{service}' ya estaba detenido"
            )
        elif response.status_code == 404:
            logger.error(f"Container not found: {container_name}")
            return ServiceActionResponse(
                success=False,
                message=f"Contenedor '{container_name}' no encontrado"
            )
        else:
            error_detail = response.text
            logger.error(f"Docker API error: {response.status_code} - {error_detail}")
            return ServiceActionResponse(
                success=False,
                message=f"Error Docker API: {response.status_code}"
            )

    except httpx.ConnectError:
        logger.error("Cannot connect to Docker daemon")
        return ServiceActionResponse(
            success=False,
            message="No se puede conectar al Docker daemon"
        )
    except httpx.TimeoutException:
        logger.error("Service stop timed out")
        return ServiceActionResponse(
            success=False,
            message="Timeout al detener servicio (>30s)"
        )
    except Exception as e:
        logger.error(f"Service stop error: {e}")
        return ServiceActionResponse(
            success=False,
            message=f"Error inesperado: {str(e)}"
        )


@router.post("/cache/clear", response_model=ServiceActionResponse)
async def clear_system_cache(
    current_user: AdminUser = Depends(get_current_user),
) -> ServiceActionResponse:
    """
    Clear Redis cache.

    Clears tariff cache and other cached data.
    """
    username = current_user.username
    logger.info(f"System cache clear requested by {username}")

    try:
        from shared.redis_client import get_redis_client

        redis = get_redis_client()

        # Clear tariff cache keys
        deleted = 0
        async for key in redis.scan_iter("tariffs:*"):
            await redis.delete(key)
            deleted += 1

        logger.info(f"Cleared {deleted} cache keys")

        return ServiceActionResponse(
            success=True,
            message=f"Cache del sistema limpiada ({deleted} claves eliminadas)"
        )

    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        return ServiceActionResponse(
            success=False,
            message=f"Error limpiando cache: {str(e)}"
        )


# =============================================================================
# Container Error Logs - Pydantic Models
# =============================================================================


class ContainerErrorLogResponse(BaseModel):
    """Response model for a single container error log."""
    id: str
    service_name: str
    container_name: str
    level: str
    message: str
    stack_trace: str | None = None
    context: dict | None = None
    log_timestamp: str
    status: str
    resolved_at: str | None = None
    resolved_by: str | None = None
    resolution_notes: str | None = None
    created_at: str


class ContainerErrorLogsListResponse(BaseModel):
    """Response model for paginated error logs list."""
    items: list[ContainerErrorLogResponse]
    total: int
    page: int
    page_size: int


class ContainerErrorResolveRequest(BaseModel):
    """Request model for resolving an error."""
    status: str = "resolved"  # resolved or ignored
    notes: str | None = None


class ContainerErrorStats(BaseModel):
    """Statistics for container error logs."""
    total_open: int
    by_service: dict[str, int]
    by_level: dict[str, int]
    last_24h: int


# =============================================================================
# Container Error Logs - Endpoints
# =============================================================================


@router.get("/errors", response_model=ContainerErrorLogsListResponse)
async def list_error_logs(
    current_user: Annotated[dict, Depends(get_current_user)],
    service: str | None = None,
    status: str = "open",
    level: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> ContainerErrorLogsListResponse:
    """
    List container error logs with filtering and pagination.

    Filters:
    - service: Filter by service name (api, agent, etc.)
    - status: Filter by status (open, resolved, ignored). Default: open
    - level: Filter by log level (ERROR, CRITICAL, etc.)
    """
    from sqlalchemy import select, func, desc
    from database.connection import get_async_session
    from database.models import ContainerErrorLog

    async with get_async_session() as session:
        # Build base query
        query = select(ContainerErrorLog)
        count_query = select(func.count(ContainerErrorLog.id))

        # Apply filters
        if service:
            query = query.where(ContainerErrorLog.service_name == service)
            count_query = count_query.where(ContainerErrorLog.service_name == service)
        if status:
            query = query.where(ContainerErrorLog.status == status)
            count_query = count_query.where(ContainerErrorLog.status == status)
        if level:
            query = query.where(ContainerErrorLog.level == level)
            count_query = count_query.where(ContainerErrorLog.level == level)

        # Get total count
        total = await session.scalar(count_query) or 0

        # Get paginated results
        query = query.order_by(desc(ContainerErrorLog.log_timestamp))
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await session.execute(query)
        errors = result.scalars().all()

        return ContainerErrorLogsListResponse(
            items=[
                ContainerErrorLogResponse(
                    id=str(e.id),
                    service_name=e.service_name,
                    container_name=e.container_name,
                    level=e.level,
                    message=e.message,
                    stack_trace=e.stack_trace,
                    context=e.context,
                    log_timestamp=e.log_timestamp.isoformat(),
                    status=e.status,
                    resolved_at=e.resolved_at.isoformat() if e.resolved_at else None,
                    resolved_by=e.resolved_by,
                    resolution_notes=e.resolution_notes,
                    created_at=e.created_at.isoformat(),
                )
                for e in errors
            ],
            total=total,
            page=page,
            page_size=page_size,
        )


@router.get("/errors/stats", response_model=ContainerErrorStats)
async def get_error_stats(
    current_user: Annotated[dict, Depends(get_current_user)],
) -> ContainerErrorStats:
    """
    Get statistics for container error logs.

    Returns counts of open errors by service and level.
    """
    from datetime import timedelta, UTC
    from sqlalchemy import select, func
    from database.connection import get_async_session
    from database.models import ContainerErrorLog

    async with get_async_session() as session:
        # Total open
        total_open = await session.scalar(
            select(func.count(ContainerErrorLog.id))
            .where(ContainerErrorLog.status == "open")
        ) or 0

        # By service
        result = await session.execute(
            select(ContainerErrorLog.service_name, func.count(ContainerErrorLog.id))
            .where(ContainerErrorLog.status == "open")
            .group_by(ContainerErrorLog.service_name)
        )
        by_service = {row[0]: row[1] for row in result}

        # By level
        result = await session.execute(
            select(ContainerErrorLog.level, func.count(ContainerErrorLog.id))
            .where(ContainerErrorLog.status == "open")
            .group_by(ContainerErrorLog.level)
        )
        by_level = {row[0]: row[1] for row in result}

        # Last 24h (all statuses)
        cutoff = datetime.now(UTC) - timedelta(hours=24)
        last_24h = await session.scalar(
            select(func.count(ContainerErrorLog.id))
            .where(ContainerErrorLog.log_timestamp >= cutoff)
        ) or 0

        return ContainerErrorStats(
            total_open=total_open,
            by_service=by_service,
            by_level=by_level,
            last_24h=last_24h,
        )


@router.post("/errors/{error_id}/resolve", response_model=ServiceActionResponse)
async def resolve_error_log(
    error_id: str,
    data: ContainerErrorResolveRequest,
    current_user: AdminUser = Depends(get_current_user),
) -> ServiceActionResponse:
    """
    Mark an error log as resolved or ignored.

    Status can be:
    - resolved: Error has been fixed
    - ignored: Error is acknowledged but not actionable
    """
    from datetime import datetime, UTC
    from sqlalchemy import select
    from database.connection import get_async_session
    from database.models import ContainerErrorLog

    if data.status not in ("resolved", "ignored"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Status must be 'resolved' or 'ignored'",
        )

    async with get_async_session() as session:
        result = await session.execute(
            select(ContainerErrorLog).where(ContainerErrorLog.id == error_id)
        )
        error_log = result.scalar_one_or_none()

        if not error_log:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Error log not found",
            )

        error_log.status = data.status
        error_log.resolved_at = datetime.now(UTC)
        error_log.resolved_by = current_user.username
        error_log.resolution_notes = data.notes

        await session.commit()

        logger.info(f"Error {error_id} marked as {data.status} by {current_user.username}")

        return ServiceActionResponse(
            success=True,
            message=f"Error marcado como {data.status}",
        )


@router.delete("/errors/{error_id}", response_model=ServiceActionResponse)
async def delete_error_log(
    error_id: str,
    current_user: AdminUser = Depends(get_current_user),
) -> ServiceActionResponse:
    """Delete a single error log entry."""
    from sqlalchemy import delete
    from database.connection import get_async_session
    from database.models import ContainerErrorLog

    async with get_async_session() as session:
        result = await session.execute(
            delete(ContainerErrorLog).where(ContainerErrorLog.id == error_id)
        )
        await session.commit()

        if result.rowcount == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Error log not found",
            )

        logger.info(f"Error log {error_id} deleted by {current_user.username}")

        return ServiceActionResponse(
            success=True,
            message="Error eliminado",
        )


@router.delete("/errors", response_model=ServiceActionResponse)
async def clear_resolved_errors(
    current_user: AdminUser = Depends(get_current_user),
) -> ServiceActionResponse:
    """Delete all resolved and ignored error logs."""
    from sqlalchemy import delete
    from database.connection import get_async_session
    from database.models import ContainerErrorLog

    async with get_async_session() as session:
        result = await session.execute(
            delete(ContainerErrorLog).where(
                ContainerErrorLog.status.in_(["resolved", "ignored"])
            )
        )
        await session.commit()

        logger.info(f"Cleared {result.rowcount} resolved errors by {current_user.username}")

        return ServiceActionResponse(
            success=True,
            message=f"Eliminados {result.rowcount} errores resueltos/ignorados",
        )
