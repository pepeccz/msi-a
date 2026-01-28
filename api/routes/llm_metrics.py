"""
LLM Metrics API - Endpoints for hybrid LLM architecture monitoring.

Provides endpoints for:
- Viewing usage statistics by tier/provider
- Cost savings analysis
- Latency comparison
- Health status of LLM providers
"""

import logging
from datetime import datetime, timedelta, UTC
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, case

from database.connection import get_async_session
from database.models import LLMUsageMetric
from shared.config import get_settings
from shared.llm_router import get_llm_router, TaskType, ModelTier, Provider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/llm-metrics", tags=["LLM Metrics"])


# =============================================================================
# Response Models
# =============================================================================


class TierStats(BaseModel):
    """Statistics for a single model tier."""
    tier: str
    provider: str
    total_calls: int
    successful_calls: int
    failed_calls: int
    success_rate: float
    avg_latency_ms: float
    total_input_tokens: int | None
    total_output_tokens: int | None
    estimated_cost_usd: Decimal | None


class TaskTypeStats(BaseModel):
    """Statistics for a single task type."""
    task_type: str
    total_calls: int
    local_calls: int
    cloud_calls: int
    local_percentage: float
    avg_latency_ms: float


class CostSavingsAnalysis(BaseModel):
    """Cost savings from hybrid architecture."""
    period_days: int
    total_calls: int
    local_calls: int
    cloud_calls: int
    local_percentage: float
    actual_cost_usd: Decimal
    hypothetical_cloud_cost_usd: Decimal
    estimated_savings_usd: Decimal
    savings_percentage: float


class HourlyUsage(BaseModel):
    """Hourly usage data point."""
    hour: datetime
    local_calls: int
    cloud_calls: int
    total_calls: int


class LLMMetricsSummary(BaseModel):
    """Complete LLM metrics summary."""
    period_start: datetime
    period_end: datetime
    tier_stats: list[TierStats]
    task_type_stats: list[TaskTypeStats]
    cost_savings: CostSavingsAnalysis
    fallback_count: int
    fallback_rate: float


class ProviderHealth(BaseModel):
    """Health status of LLM providers."""
    ollama: dict[str, Any]
    openrouter: dict[str, Any]


# =============================================================================
# API Endpoints
# =============================================================================


@router.get("/summary", response_model=LLMMetricsSummary)
async def get_metrics_summary(
    days: int = Query(default=7, ge=1, le=90, description="Number of days to analyze"),
):
    """
    Get comprehensive LLM usage metrics summary.
    
    Includes tier statistics, task type breakdown, cost savings analysis,
    and fallback rates for the specified time period.
    """
    period_end = datetime.now(UTC)
    period_start = period_end - timedelta(days=days)
    
    async with get_async_session() as session:
        # Base query for period
        base_filter = LLMUsageMetric.created_at >= period_start
        
        # Tier statistics
        tier_query = (
            select(
                LLMUsageMetric.tier,
                LLMUsageMetric.provider,
                func.count().label("total_calls"),
                func.sum(case((LLMUsageMetric.success == True, 1), else_=0)).label("successful_calls"),
                func.sum(case((LLMUsageMetric.success == False, 1), else_=0)).label("failed_calls"),
                func.avg(LLMUsageMetric.latency_ms).label("avg_latency_ms"),
                func.sum(LLMUsageMetric.input_tokens).label("total_input_tokens"),
                func.sum(LLMUsageMetric.output_tokens).label("total_output_tokens"),
                func.sum(LLMUsageMetric.estimated_cost_usd).label("estimated_cost_usd"),
            )
            .where(base_filter)
            .group_by(LLMUsageMetric.tier, LLMUsageMetric.provider)
        )
        
        tier_result = await session.execute(tier_query)
        tier_rows = tier_result.fetchall()
        
        tier_stats = []
        for row in tier_rows:
            total = row.total_calls or 0
            successful = row.successful_calls or 0
            tier_stats.append(TierStats(
                tier=row.tier,
                provider=row.provider,
                total_calls=total,
                successful_calls=successful,
                failed_calls=row.failed_calls or 0,
                success_rate=(successful / total * 100) if total > 0 else 0,
                avg_latency_ms=float(row.avg_latency_ms or 0),
                total_input_tokens=row.total_input_tokens,
                total_output_tokens=row.total_output_tokens,
                estimated_cost_usd=row.estimated_cost_usd,
            ))
        
        # Task type statistics
        task_query = (
            select(
                LLMUsageMetric.task_type,
                func.count().label("total_calls"),
                func.sum(case(
                    (LLMUsageMetric.provider == "ollama", 1), else_=0
                )).label("local_calls"),
                func.sum(case(
                    (LLMUsageMetric.provider == "openrouter", 1), else_=0
                )).label("cloud_calls"),
                func.avg(LLMUsageMetric.latency_ms).label("avg_latency_ms"),
            )
            .where(base_filter)
            .group_by(LLMUsageMetric.task_type)
        )
        
        task_result = await session.execute(task_query)
        task_rows = task_result.fetchall()
        
        task_type_stats = []
        for row in task_rows:
            total = row.total_calls or 0
            local = row.local_calls or 0
            task_type_stats.append(TaskTypeStats(
                task_type=row.task_type,
                total_calls=total,
                local_calls=local,
                cloud_calls=row.cloud_calls or 0,
                local_percentage=(local / total * 100) if total > 0 else 0,
                avg_latency_ms=float(row.avg_latency_ms or 0),
            ))
        
        # Cost savings analysis
        total_calls = sum(t.total_calls for t in tier_stats)
        local_calls = sum(t.total_calls for t in tier_stats if t.provider == "ollama")
        cloud_calls = sum(t.total_calls for t in tier_stats if t.provider == "openrouter")
        actual_cost = sum((t.estimated_cost_usd or Decimal("0")) for t in tier_stats)
        
        # Estimate what it would have cost if all calls went to cloud
        total_input_tokens = sum((t.total_input_tokens or 0) for t in tier_stats)
        total_output_tokens = sum((t.total_output_tokens or 0) for t in tier_stats)
        
        # DeepSeek pricing: $0.14/1M input, $0.28/1M output
        hypothetical_cost = (
            Decimal(str(total_input_tokens)) * Decimal("0.00000014") +
            Decimal(str(total_output_tokens)) * Decimal("0.00000028")
        )
        
        savings = hypothetical_cost - actual_cost
        
        cost_savings = CostSavingsAnalysis(
            period_days=days,
            total_calls=total_calls,
            local_calls=local_calls,
            cloud_calls=cloud_calls,
            local_percentage=(local_calls / total_calls * 100) if total_calls > 0 else 0,
            actual_cost_usd=actual_cost,
            hypothetical_cloud_cost_usd=hypothetical_cost,
            estimated_savings_usd=max(savings, Decimal("0")),
            savings_percentage=float((savings / hypothetical_cost * 100) if hypothetical_cost > 0 else 0),
        )
        
        # Fallback statistics
        fallback_query = (
            select(
                func.count().label("total"),
                func.sum(case((LLMUsageMetric.fallback_used == True, 1), else_=0)).label("fallback_count"),
            )
            .where(base_filter)
        )
        fallback_result = await session.execute(fallback_query)
        fallback_row = fallback_result.fetchone()
        
        fallback_total = fallback_row.total if fallback_row and fallback_row.total else 0
        fallback_count = fallback_row.fallback_count if fallback_row and fallback_row.fallback_count else 0
    
    return LLMMetricsSummary(
        period_start=period_start,
        period_end=period_end,
        tier_stats=tier_stats,
        task_type_stats=task_type_stats,
        cost_savings=cost_savings,
        fallback_count=fallback_count,
        fallback_rate=(fallback_count / fallback_total * 100) if fallback_total > 0 else 0,
    )


@router.get("/hourly", response_model=list[HourlyUsage])
async def get_hourly_usage(
    hours: int = Query(default=24, ge=1, le=168, description="Number of hours"),
):
    """
    Get hourly LLM usage breakdown.
    
    Returns usage data grouped by hour for the specified time period,
    showing local vs cloud call distribution.
    """
    period_start = datetime.now(UTC) - timedelta(hours=hours)
    
    async with get_async_session() as session:
        # Use literal_column to reference the alias in GROUP BY and ORDER BY
        hour_trunc = func.date_trunc("hour", LLMUsageMetric.created_at).label("hour")
        query = (
            select(
                hour_trunc,
                func.sum(case(
                    (LLMUsageMetric.provider == "ollama", 1), else_=0
                )).label("local_calls"),
                func.sum(case(
                    (LLMUsageMetric.provider == "openrouter", 1), else_=0
                )).label("cloud_calls"),
                func.count().label("total_calls"),
            )
            .where(LLMUsageMetric.created_at >= period_start)
            .group_by(hour_trunc)
            .order_by(hour_trunc)
        )
        
        result = await session.execute(query)
        rows = result.fetchall()
    
    return [
        HourlyUsage(
            hour=row.hour,
            local_calls=row.local_calls or 0,
            cloud_calls=row.cloud_calls or 0,
            total_calls=row.total_calls or 0,
        )
        for row in rows
    ]


@router.get("/health", response_model=ProviderHealth)
async def get_provider_health():
    """
    Check health status of all LLM providers.
    
    Tests connectivity to Ollama (local) and OpenRouter (cloud)
    and returns their availability status.
    """
    router = get_llm_router()
    health = await router.health_check()
    
    return ProviderHealth(
        ollama=health.get("ollama", {"status": "unknown"}),
        openrouter=health.get("openrouter", {"status": "unknown"}),
    )


@router.get("/config")
async def get_hybrid_config():
    """
    Get current hybrid LLM configuration.
    
    Returns the current settings for the hybrid LLM architecture,
    including which tiers are enabled and model assignments.
    """
    settings = get_settings()
    
    return {
        "hybrid_enabled": settings.USE_HYBRID_LLM,
        "tiers": {
            "local_fast": {
                "model": settings.LOCAL_FAST_MODEL,
                "tasks": ["classification", "extraction"],
            },
            "local_capable": {
                "model": settings.LOCAL_CAPABLE_MODEL,
                "tasks": ["rag_simple", "summarization", "translation"],
            },
            "cloud_standard": {
                "model": settings.LLM_MODEL,
                "tasks": ["rag_complex", "conversation", "tool_calling"],
            },
        },
        "routing": {
            "vehicle_classification": {
                "use_local": settings.USE_LOCAL_VEHICLE_CLASSIFICATION,
                "model": settings.VEHICLE_CLASSIFICATION_MODEL,
            },
            "section_mapping": {
                "use_local": settings.USE_LOCAL_SECTION_MAPPING,
                "model": settings.SECTION_MAPPING_MODEL,
            },
            "rag_simple": {
                "use_local": settings.USE_LOCAL_FOR_SIMPLE_RAG,
                "model": settings.RAG_PRIMARY_MODEL,
            },
        },
        "metrics_enabled": settings.ENABLE_LLM_METRICS,
        "metrics_retention_days": settings.LLM_METRICS_RETENTION_DAYS,
    }
