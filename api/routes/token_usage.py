"""
MSI Automotive - Token Usage API routes.

Provides endpoints for querying LLM token consumption and costs.
Protected by admin authentication.
"""

import logging
from datetime import datetime, UTC
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, desc

from api.models.token_usage import (
    TokenUsageResponse,
    TokenUsageListResponse,
    TokenPricingResponse,
    CurrentMonthUsageResponse,
)
from api.routes.admin import get_current_user, require_role
from database.connection import get_async_session
from database.models import AdminUser, TokenUsage
from shared.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/token-usage", tags=["token-usage"])


# =============================================================================
# Endpoints
# =============================================================================


@router.get(
    "",
    response_model=TokenUsageListResponse,
    summary="Get token usage history",
    description="Returns the last 12 months of token usage. Admin only.",
)
async def get_token_usage(
    current_user: AdminUser = Depends(require_role("admin")),
):
    """
    Get token usage for the last 12 months.

    Returns monthly aggregated data sorted by most recent first.
    """
    async with get_async_session() as session:
        result = await session.execute(
            select(TokenUsage)
            .order_by(desc(TokenUsage.year), desc(TokenUsage.month))
            .limit(12)
        )
        usage_list = result.scalars().all()

        return TokenUsageListResponse(
            items=[TokenUsageResponse.model_validate(u) for u in usage_list],
            total=len(usage_list),
        )


@router.get(
    "/current",
    response_model=CurrentMonthUsageResponse,
    summary="Get current month usage",
    description="Returns token usage for the current month. Admin only.",
)
async def get_current_month_usage(
    current_user: AdminUser = Depends(require_role("admin")),
):
    """
    Get token usage for the current month.

    Returns usage data with computed costs based on configured pricing.
    """
    now = datetime.now(UTC)
    settings = get_settings()

    async with get_async_session() as session:
        result = await session.execute(
            select(TokenUsage).where(
                TokenUsage.year == now.year,
                TokenUsage.month == now.month,
            )
        )
        usage = result.scalar_one_or_none()

        if not usage:
            # No data yet this month
            return CurrentMonthUsageResponse(
                year=now.year,
                month=now.month,
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
                total_requests=0,
                cost_input_eur=Decimal("0.00"),
                cost_output_eur=Decimal("0.00"),
                cost_total_eur=Decimal("0.00"),
            )

        # Calculate costs
        input_cost = (Decimal(usage.input_tokens) / Decimal(1_000_000)) * settings.TOKEN_PRICE_INPUT
        output_cost = (Decimal(usage.output_tokens) / Decimal(1_000_000)) * settings.TOKEN_PRICE_OUTPUT

        return CurrentMonthUsageResponse(
            year=usage.year,
            month=usage.month,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.input_tokens + usage.output_tokens,
            total_requests=usage.total_requests,
            cost_input_eur=input_cost,
            cost_output_eur=output_cost,
            cost_total_eur=input_cost + output_cost,
        )


@router.get(
    "/pricing",
    response_model=TokenPricingResponse,
    summary="Get current pricing",
    description="Returns the configured token pricing. Admin only.",
)
async def get_pricing(
    current_user: AdminUser = Depends(require_role("admin")),
):
    """
    Get current token pricing configuration.

    Returns the prices per million tokens for input and output.
    """
    settings = get_settings()

    return TokenPricingResponse(
        input_price_per_million=settings.TOKEN_PRICE_INPUT,
        output_price_per_million=settings.TOKEN_PRICE_OUTPUT,
    )
