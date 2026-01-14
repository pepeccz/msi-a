"""
Docker Log Monitor Service

Monitors Docker container logs in real-time and extracts errors to database.
Runs as background task started from the API lifespan.
"""

import asyncio
import json
import logging
import re
from datetime import datetime, UTC
from typing import Any

import httpx

from database.connection import async_session_factory
from database.models import ContainerErrorLog

logger = logging.getLogger(__name__)

# Container map - must match api/routes/system.py
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

# Levels to capture (case-insensitive)
CAPTURE_LEVELS = {"ERROR", "CRITICAL", "EXCEPTION", "FATAL", "PANIC"}

# Patterns for detecting errors in different log formats
ERROR_PATTERNS = [
    # JSON structured logs with level field
    re.compile(r'"level"\s*:\s*"(ERROR|CRITICAL|EXCEPTION)"', re.IGNORECASE),
    # Standard Python/logging format: ERROR: or [ERROR]
    re.compile(r'\b(ERROR|CRITICAL|EXCEPTION|FATAL|PANIC)\b[\s:\[\]]', re.IGNORECASE),
    # PostgreSQL format
    re.compile(r'^(ERROR|FATAL|PANIC):', re.IGNORECASE),
    # Redis format
    re.compile(r'^#\s*(Error|Warning)', re.IGNORECASE),
]


class LogMonitor:
    """
    Monitor Docker container logs and extract errors to database.

    Usage:
        monitor = LogMonitor(docker_client)
        await monitor.start()
        # ... later ...
        await monitor.stop()
    """

    def __init__(
        self,
        docker_base_url: str,
        docker_transport: httpx.AsyncHTTPTransport | None = None,
    ):
        """
        Initialize the log monitor.

        Args:
            docker_base_url: Base URL for Docker API (e.g., "http://docker")
            docker_transport: Optional transport for Unix socket connection
        """
        self.docker_base_url = docker_base_url
        self.docker_transport = docker_transport
        self._running = False
        self._tasks: dict[str, asyncio.Task] = {}

    async def start(self) -> None:
        """Start monitoring all containers."""
        if self._running:
            logger.warning("LogMonitor already running")
            return

        self._running = True
        logger.info("Starting LogMonitor for %d containers", len(CONTAINER_MAP))

        for service_name, container_name in CONTAINER_MAP.items():
            task = asyncio.create_task(
                self._monitor_container(service_name, container_name),
                name=f"log_monitor_{service_name}",
            )
            self._tasks[service_name] = task
            logger.debug("Started monitoring for %s (%s)", service_name, container_name)

    async def stop(self) -> None:
        """Stop all monitoring tasks gracefully."""
        if not self._running:
            return

        self._running = False
        logger.info("Stopping LogMonitor...")

        # Cancel all tasks
        for task in self._tasks.values():
            task.cancel()

        # Wait for all to complete
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)

        self._tasks.clear()
        logger.info("LogMonitor stopped")

    def _create_client(self, timeout: float | None = None) -> httpx.AsyncClient:
        """Create a new HTTP client for Docker API."""
        if self.docker_transport:
            return httpx.AsyncClient(
                transport=self.docker_transport,
                base_url=self.docker_base_url,
                timeout=timeout,
            )
        return httpx.AsyncClient(
            base_url=self.docker_base_url,
            timeout=timeout,
        )

    async def _monitor_container(self, service_name: str, container_name: str) -> None:
        """
        Monitor a single container's logs continuously.

        Reconnects automatically on errors with exponential backoff.
        """
        backoff = 5  # Initial backoff seconds
        max_backoff = 60

        while self._running:
            try:
                await self._stream_container_logs(service_name, container_name)
                backoff = 5  # Reset on successful connection
            except asyncio.CancelledError:
                logger.debug("Monitoring cancelled for %s", service_name)
                break
            except Exception as e:
                if self._running:
                    logger.warning(
                        "Error monitoring %s, retrying in %ds: %s",
                        service_name, backoff, e
                    )
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, max_backoff)

    async def _stream_container_logs(
        self,
        service_name: str,
        container_name: str,
    ) -> None:
        """Stream logs from a container and process errors."""
        async with self._create_client(timeout=None) as client:
            # Use Docker API to stream logs
            async with client.stream(
                "GET",
                f"/v1.44/containers/{container_name}/logs",
                params={
                    "follow": "true",
                    "stdout": "true",
                    "stderr": "true",
                    "tail": "0",  # Only new logs from now
                    "timestamps": "true",
                },
            ) as response:
                if response.status_code == 404:
                    logger.debug("Container %s not found, skipping", container_name)
                    await asyncio.sleep(30)  # Wait before retry
                    return

                if response.status_code != 200:
                    logger.warning(
                        "Cannot stream logs for %s: HTTP %d",
                        container_name, response.status_code
                    )
                    await asyncio.sleep(30)
                    return

                logger.info("Connected to log stream for %s", service_name)

                # Buffer for accumulating multi-line stack traces
                error_buffer: dict[str, Any] | None = None
                stack_lines: list[str] = []

                async for chunk in response.aiter_bytes():
                    if not self._running:
                        break

                    lines = self._parse_docker_log_chunk(chunk)

                    for timestamp, line in lines:
                        is_error = self._is_error_line(line)
                        is_stack_continuation = self._is_stack_trace_line(line)

                        if is_error:
                            # Save previous error if exists
                            if error_buffer:
                                await self._save_error(
                                    service_name,
                                    container_name,
                                    error_buffer,
                                    stack_lines,
                                )

                            # Start new error
                            error_buffer = {
                                "timestamp": timestamp,
                                "line": line,
                            }
                            stack_lines = []

                        elif is_stack_continuation and error_buffer:
                            # Accumulate stack trace
                            stack_lines.append(line)

                        elif error_buffer and not line.strip():
                            # Empty line might end a stack trace
                            pass

                        elif error_buffer:
                            # Non-stack line ends the error context
                            await self._save_error(
                                service_name,
                                container_name,
                                error_buffer,
                                stack_lines,
                            )
                            error_buffer = None
                            stack_lines = []

    def _parse_docker_log_chunk(
        self,
        chunk: bytes,
    ) -> list[tuple[datetime | None, str]]:
        """
        Parse Docker log multiplexed stream format.

        Docker streams have 8-byte header: [STREAM_TYPE(1), 0, 0, 0, SIZE(4)]
        followed by SIZE bytes of log data.
        """
        results: list[tuple[datetime | None, str]] = []
        pos = 0

        while pos < len(chunk):
            # Need at least 8 bytes for header
            if pos + 8 > len(chunk):
                break

            # Parse header
            # stream_type = chunk[pos]  # 1=stdout, 2=stderr
            size = int.from_bytes(chunk[pos + 4:pos + 8], "big")

            if pos + 8 + size > len(chunk):
                break

            # Extract log line
            frame_data = chunk[pos + 8:pos + 8 + size]
            try:
                line = frame_data.decode("utf-8", errors="replace").strip()
            except Exception:
                pos += 8 + size
                continue

            # Extract timestamp (Docker format: 2024-01-14T10:30:45.123456789Z)
            timestamp = None
            if line:
                ts_match = re.match(
                    r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)\s*",
                    line,
                )
                if ts_match:
                    try:
                        ts_str = ts_match.group(1).rstrip("Z")
                        # Truncate to microseconds if needed
                        if "." in ts_str:
                            parts = ts_str.split(".")
                            ts_str = parts[0] + "." + parts[1][:6]
                        timestamp = datetime.fromisoformat(ts_str).replace(tzinfo=UTC)
                        line = line[ts_match.end():]
                    except ValueError:
                        pass

            if line:
                results.append((timestamp, line))

            pos += 8 + size

        return results

    def _is_error_line(self, line: str) -> bool:
        """Check if line contains an error indicator."""
        for pattern in ERROR_PATTERNS:
            if pattern.search(line):
                return True
        return False

    def _is_stack_trace_line(self, line: str) -> bool:
        """Check if line is part of a stack trace."""
        stripped = line.strip()
        return (
            stripped.startswith("File ")
            or stripped.startswith("at ")
            or stripped.startswith("Traceback")
            or (line.startswith("    ") and stripped)
            or stripped.startswith("^")
            or stripped.startswith("| ")
        )

    def _parse_error_line(
        self,
        line: str,
    ) -> tuple[str, str, dict[str, Any] | None]:
        """
        Parse error line to extract level, message, and context.

        Returns:
            Tuple of (level, message, context_dict)
        """
        # Try JSON format first (structured logging)
        try:
            data = json.loads(line)
            if isinstance(data, dict):
                level = str(data.get("level", "ERROR")).upper()
                message = data.get("message") or data.get("msg") or line

                # Extract context fields (exclude standard fields)
                context = {
                    k: v for k, v in data.items()
                    if k not in ("level", "message", "msg", "timestamp", "time", "logger")
                    and v is not None
                }

                return level, str(message), context if context else None
        except (json.JSONDecodeError, TypeError):
            pass

        # Try standard format: LEVEL: message or [LEVEL] message
        for pattern in [
            r"\b(ERROR|CRITICAL|EXCEPTION|FATAL|PANIC)\b[:\s]+(.+)",
            r"\[(ERROR|CRITICAL|EXCEPTION)\]\s*(.+)",
        ]:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                return match.group(1).upper(), match.group(2).strip(), None

        # Fallback
        return "ERROR", line, None

    async def _save_error(
        self,
        service_name: str,
        container_name: str,
        error_data: dict[str, Any],
        stack_lines: list[str],
    ) -> None:
        """Save an error to the database."""
        try:
            line = error_data["line"]
            timestamp = error_data["timestamp"] or datetime.now(UTC)

            level, message, context = self._parse_error_line(line)
            stack_trace = "\n".join(stack_lines) if stack_lines else None

            async with async_session_factory() as session:
                error_log = ContainerErrorLog(
                    service_name=service_name,
                    container_name=container_name,
                    level=level,
                    message=message[:2000] if len(message) > 2000 else message,
                    stack_trace=stack_trace,
                    context=context,
                    log_timestamp=timestamp,
                    raw_log=line[:5000] if len(line) > 5000 else line,
                    status="open",
                )
                session.add(error_log)
                await session.commit()

                logger.debug(
                    "Saved error from %s: %s - %s",
                    service_name,
                    level,
                    message[:100],
                )
        except Exception as e:
            logger.error("Failed to save error log: %s", e)


# Global instance (set during API startup)
_log_monitor: LogMonitor | None = None


def get_log_monitor() -> LogMonitor | None:
    """Get the global LogMonitor instance."""
    return _log_monitor


def set_log_monitor(monitor: LogMonitor | None) -> None:
    """Set the global LogMonitor instance."""
    global _log_monitor
    _log_monitor = monitor
