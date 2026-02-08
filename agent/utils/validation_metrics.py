"""
Phase 5: Validation Metrics & Observability

Tracks validation failure rates, retry patterns, and tool-specific issues.

Metrics collected:
- Total validation attempts
- Validation failures (by layer: syntax/state/semantic)
- Failures per tool
- Retry success rate
- Average retries before success
- Escalation rate

Usage:
    from agent.utils.validation_metrics import get_validation_metrics
    
    metrics = get_validation_metrics()
    metrics.record_validation_attempt("my_tool")
    metrics.record_validation_failure("my_tool", "syntax", ["Missing param: foo"])
    
    # Get stats
    stats = await metrics.get_stats()
"""

import structlog
from datetime import datetime, UTC, timedelta
from typing import Any
from collections import defaultdict
from dataclasses import dataclass, field

logger = structlog.get_logger(__name__)


@dataclass
class ValidationStats:
    """Aggregated validation statistics."""
    
    # Overall metrics
    total_attempts: int = 0
    total_failures: int = 0
    total_retries: int = 0
    total_successes_after_retry: int = 0
    total_escalations: int = 0
    
    # By layer
    syntax_failures: int = 0
    state_failures: int = 0
    semantic_failures: int = 0
    
    # By tool (top 10)
    failures_by_tool: dict[str, int] = field(default_factory=dict)
    
    # Calculated metrics
    failure_rate: float = 0.0
    retry_success_rate: float = 0.0
    avg_retries_before_success: float = 0.0
    escalation_rate: float = 0.0
    
    # Time window
    window_start: str = ""
    window_end: str = ""


class ValidationMetrics:
    """
    Tracks validation metrics for monitoring and observability.
    
    Thread-safe in-memory metrics storage.
    """
    
    def __init__(self):
        # Counters
        self.validation_attempts = 0
        self.validation_failures = 0
        self.retry_attempts = 0
        self.retry_successes = 0
        self.escalations = 0
        
        # Failure breakdown
        self.failure_by_layer = defaultdict(int)  # {layer: count}
        self.failure_by_tool = defaultdict(int)   # {tool_name: count}
        
        # Retry tracking
        self.retry_counts = []  # List of retry counts for successful recoveries
        
        # Time tracking
        self.window_start = datetime.now(UTC)
    
    def record_validation_attempt(self, tool_name: str):
        """
        Record a validation attempt.
        
        Args:
            tool_name: Name of the tool being validated
        """
        self.validation_attempts += 1
        
        logger.debug(
            "validation_metric_attempt",
            tool_name=tool_name,
            total_attempts=self.validation_attempts,
        )
    
    def record_validation_failure(
        self,
        tool_name: str,
        failed_layer: str,
        errors: list[str],
    ):
        """
        Record a validation failure.
        
        Args:
            tool_name: Name of the tool that failed validation
            failed_layer: Layer that failed (syntax/state/semantic)
            errors: List of validation errors
        """
        self.validation_failures += 1
        self.failure_by_layer[failed_layer] += 1
        self.failure_by_tool[tool_name] += 1
        
        logger.info(
            "validation_metric_failure",
            tool_name=tool_name,
            failed_layer=failed_layer,
            error_count=len(errors),
            total_failures=self.validation_failures,
        )
    
    def record_retry_attempt(self, tool_name: str, retry_count: int):
        """
        Record a retry attempt after validation failure.
        
        Args:
            tool_name: Name of the tool being retried
            retry_count: Current retry count
        """
        self.retry_attempts += 1
        
        logger.debug(
            "validation_metric_retry",
            tool_name=tool_name,
            retry_count=retry_count,
            total_retries=self.retry_attempts,
        )
    
    def record_retry_success(self, tool_name: str, retry_count: int):
        """
        Record successful execution after retry.
        
        Args:
            tool_name: Name of the tool that succeeded
            retry_count: Number of retries before success
        """
        self.retry_successes += 1
        self.retry_counts.append(retry_count)
        
        logger.info(
            "validation_metric_retry_success",
            tool_name=tool_name,
            retry_count=retry_count,
            total_retry_successes=self.retry_successes,
        )
    
    def record_escalation(self, tool_name: str, reason: str):
        """
        Record escalation to human after max retries.
        
        Args:
            tool_name: Name of the tool that escalated
            reason: Reason for escalation
        """
        self.escalations += 1
        
        logger.warning(
            "validation_metric_escalation",
            tool_name=tool_name,
            reason=reason,
            total_escalations=self.escalations,
        )
    
    def get_stats(self) -> ValidationStats:
        """
        Get aggregated statistics.
        
        Returns:
            ValidationStats object with calculated metrics
        """
        stats = ValidationStats()
        
        # Overall counts
        stats.total_attempts = self.validation_attempts
        stats.total_failures = self.validation_failures
        stats.total_retries = self.retry_attempts
        stats.total_successes_after_retry = self.retry_successes
        stats.total_escalations = self.escalations
        
        # By layer
        stats.syntax_failures = self.failure_by_layer.get("syntax", 0)
        stats.state_failures = self.failure_by_layer.get("state", 0)
        stats.semantic_failures = self.failure_by_layer.get("semantic", 0)
        
        # By tool (top 10)
        sorted_tools = sorted(
            self.failure_by_tool.items(),
            key=lambda x: x[1],
            reverse=True
        )
        stats.failures_by_tool = dict(sorted_tools[:10])
        
        # Calculated metrics
        if stats.total_attempts > 0:
            stats.failure_rate = (stats.total_failures / stats.total_attempts) * 100
        
        if stats.total_retries > 0:
            stats.retry_success_rate = (stats.total_successes_after_retry / stats.total_retries) * 100
        
        if len(self.retry_counts) > 0:
            stats.avg_retries_before_success = sum(self.retry_counts) / len(self.retry_counts)
        
        if stats.total_failures > 0:
            stats.escalation_rate = (stats.total_escalations / stats.total_failures) * 100
        
        # Time window
        stats.window_start = self.window_start.isoformat()
        stats.window_end = datetime.now(UTC).isoformat()
        
        return stats
    
    def reset(self):
        """Reset all metrics (useful for testing or daily rollover)."""
        self.validation_attempts = 0
        self.validation_failures = 0
        self.retry_attempts = 0
        self.retry_successes = 0
        self.escalations = 0
        self.failure_by_layer.clear()
        self.failure_by_tool.clear()
        self.retry_counts.clear()
        self.window_start = datetime.now(UTC)
        
        logger.info("validation_metrics_reset")
    
    def export_dict(self) -> dict[str, Any]:
        """
        Export metrics as dictionary (for API/logging).
        
        Returns:
            Dict with all metrics
        """
        stats = self.get_stats()
        
        return {
            "overall": {
                "total_attempts": stats.total_attempts,
                "total_failures": stats.total_failures,
                "total_retries": stats.total_retries,
                "total_successes_after_retry": stats.total_successes_after_retry,
                "total_escalations": stats.total_escalations,
            },
            "rates": {
                "failure_rate": round(stats.failure_rate, 2),
                "retry_success_rate": round(stats.retry_success_rate, 2),
                "avg_retries_before_success": round(stats.avg_retries_before_success, 2),
                "escalation_rate": round(stats.escalation_rate, 2),
            },
            "breakdown": {
                "by_layer": {
                    "syntax": stats.syntax_failures,
                    "state": stats.state_failures,
                    "semantic": stats.semantic_failures,
                },
                "by_tool": stats.failures_by_tool,
            },
            "time_window": {
                "start": stats.window_start,
                "end": stats.window_end,
            },
        }


# Global singleton instance
_metrics_instance: ValidationMetrics | None = None


def get_validation_metrics() -> ValidationMetrics:
    """
    Get singleton ValidationMetrics instance.
    
    Returns:
        Global ValidationMetrics instance
    """
    global _metrics_instance
    if _metrics_instance is None:
        _metrics_instance = ValidationMetrics()
    return _metrics_instance
