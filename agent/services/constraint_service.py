"""
MSI Automotive - Response Constraint Service.

Provides database-driven validation of LLM responses to prevent hallucinations.
Loads constraints from PostgreSQL and checks agent responses against them.
Constraints define regex patterns that detect potential violations and the
tools that must have been called to produce that information legitimately.
"""

import logging
import re
import time
from typing import Any

from sqlalchemy import select

from database.connection import get_async_session
from database.models import ResponseConstraint

logger = logging.getLogger(__name__)


# In-memory cache for constraints (per category)
_constraints_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_CACHE_TTL_SECONDS = 300  # 5 minutes


async def get_constraints_for_category(category_slug: str | None) -> list[dict[str, Any]]:
    """
    Load active constraints for a category (with in-memory cache).

    Returns constraints that apply to the specific category OR are global (category_id=NULL).
    Results are cached for 5 minutes to avoid repeated DB queries.

    Args:
        category_slug: The vehicle category slug, or None for global-only constraints.

    Returns:
        List of constraint dicts with keys: constraint_type, detection_pattern,
        required_tool, error_injection, priority.
    """
    cache_key = category_slug or "__global__"
    now = time.time()

    # Check cache
    if cache_key in _constraints_cache:
        cached_time, cached_data = _constraints_cache[cache_key]
        if now - cached_time < _CACHE_TTL_SECONDS:
            return cached_data

    try:
        async with get_async_session() as session:
            # Get category UUID if slug provided
            category_id = None
            if category_slug:
                from database.models import VehicleCategory
                cat_result = await session.execute(
                    select(VehicleCategory.id).where(
                        VehicleCategory.slug == category_slug,
                        VehicleCategory.is_active == True,  # noqa: E712
                    )
                )
                cat_row = cat_result.scalar_one_or_none()
                if cat_row:
                    category_id = cat_row

            # Query constraints: global (category_id IS NULL) + category-specific
            query = (
                select(ResponseConstraint)
                .where(ResponseConstraint.is_active == True)  # noqa: E712
            )

            if category_id:
                query = query.where(
                    (ResponseConstraint.category_id == None) |  # noqa: E711
                    (ResponseConstraint.category_id == category_id)
                )
            else:
                query = query.where(ResponseConstraint.category_id == None)  # noqa: E711

            query = query.order_by(ResponseConstraint.priority.desc())

            result = await session.execute(query)
            constraints = result.scalars().all()

            # Convert to dicts for cache
            constraint_dicts = [
                {
                    "constraint_type": c.constraint_type,
                    "detection_pattern": c.detection_pattern,
                    "required_tool": c.required_tool,
                    "error_injection": c.error_injection,
                    "priority": c.priority,
                }
                for c in constraints
            ]

            # Update cache
            _constraints_cache[cache_key] = (now, constraint_dicts)

            logger.info(
                f"Loaded {len(constraint_dicts)} constraints for category '{cache_key}'",
            )
            return constraint_dicts

    except Exception as e:
        logger.error(
            f"Error loading constraints: {e}",
            exc_info=True,
        )
        # On error, return empty list (fail open - don't block agent)
        return []


def validate_response(
    response_text: str,
    tools_called_this_turn: set[str],
    constraints: list[dict[str, Any]],
) -> tuple[bool, str | None]:
    """
    Validate an LLM response against loaded constraints.

    For each constraint, checks if the detection_pattern matches the response.
    If it does, verifies that the required_tool was called in this turn.
    If not, the response is invalid and the error_injection message is returned.

    Args:
        response_text: The LLM's generated response text.
        tools_called_this_turn: Set of tool names called during this turn.
        constraints: List of constraint dicts from get_constraints_for_category().

    Returns:
        Tuple of (is_valid, error_injection_or_none).
        If is_valid is False, error_injection contains the correction message.
    """
    if not response_text or not constraints:
        return True, None

    for constraint in constraints:
        detection_pattern = constraint["detection_pattern"]
        required_tool_str = constraint["required_tool"]
        error_injection = constraint["error_injection"]

        try:
            # Check if the response matches the detection pattern
            if re.search(detection_pattern, response_text, re.IGNORECASE):
                # Pattern matched - check if required tool was called
                required_tools = {t.strip() for t in required_tool_str.split("|")}

                if not tools_called_this_turn.intersection(required_tools):
                    # Violation: pattern detected but required tool not called
                    logger.warning(
                        f"Constraint violation: '{constraint['constraint_type']}' | "
                        f"Pattern matched but required tools {required_tools} not in "
                        f"called tools {tools_called_this_turn}",
                    )
                    return False, error_injection

        except re.error as e:
            logger.error(
                f"Invalid regex in constraint '{constraint['constraint_type']}': {e}",
            )
            continue

    return True, None


def invalidate_cache(category_slug: str | None = None) -> None:
    """
    Invalidate the constraint cache.

    Args:
        category_slug: If provided, only invalidate for this category.
                       If None, invalidate all cached constraints.
    """
    if category_slug:
        cache_key = category_slug
        _constraints_cache.pop(cache_key, None)
    else:
        _constraints_cache.clear()
    logger.info(f"Constraint cache invalidated: {category_slug or 'all'}")
