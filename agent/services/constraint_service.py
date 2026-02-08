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


def _should_skip_constraint(
    constraint_type: str,
    fsm_state: dict[str, Any] | None,
) -> bool:
    """
    Determine if a constraint should be skipped based on FSM context.
    
    Args:
        constraint_type: Type of constraint (e.g., 'price_requires_tool')
        fsm_state: Current FSM state (mode_context in v2 architecture)
        
    Returns:
        True if constraint should be skipped
    """
    if not fsm_state:
        return False
    
    # Skip price_requires_tool during active case collection OR when price already calculated
    # Rationale: When user has an active case OR tariff was calculated in previous turn,
    # LLM should be able to reference the price freely without being forced to recalculate.
    if constraint_type == "price_requires_tool":
        # v2 mode_context keys (mode_context is passed as fsm_state)
        expediente_sub_mode = fsm_state.get("expediente_sub_mode")
        has_tariff = fsm_state.get("tariff_amount") is not None
        presupuesto_done = fsm_state.get("presupuesto_completado", False)
        
        # ✅ Check if tariff was calculated in PRESUPUESTO mode (previous turn)
        # REFACTOR-001: Removed redundant precio_calculado check - tarifa_calculada is sufficient
        has_tarifa_calculada = fsm_state.get("tarifa_calculada") is not None
        
        # Skip constraint if:
        # 1. In expediente with tariff calculated (existing logic)
        # 2. Presupuesto completed (existing logic)
        # 3. Tariff was calculated in previous turn (prevents false positives)
        if (
            (expediente_sub_mode and has_tariff) 
            or presupuesto_done
            or has_tarifa_calculada
        ):
            logger.debug(
                f"Skipping constraint '{constraint_type}' | "
                f"sub_mode={expediente_sub_mode}, has_tariff={has_tariff}, "
                f"presupuesto_done={presupuesto_done}, "
                f"has_tarifa_calculada={has_tarifa_calculada}"
            )
            return True
    
    return False


def validate_response(
    response_text: str,
    tools_called_this_turn: set[str],
    constraints: list[dict[str, Any]],
    fsm_state: dict[str, Any] | None = None,
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
        fsm_state: Current FSM state (to determine if constraints should be skipped).

    Returns:
        Tuple of (is_valid, error_injection_or_none).
        If is_valid is False, error_injection contains the correction message.
    """
    if not response_text or not constraints:
        return True, None

    for constraint in constraints:
        constraint_type = constraint["constraint_type"]
        detection_pattern = constraint["detection_pattern"]
        required_tool_str = constraint["required_tool"]
        error_injection = constraint["error_injection"]
        
        # Check if constraint should be skipped based on FSM context
        if _should_skip_constraint(constraint_type, fsm_state):
            continue

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


# ============================================================================
# PHASE 2: SEMANTIC VALIDATION (Database-backed validators)
# ============================================================================


async def cached_db_lookup(
    cache_key: str,
    db_query_func,
    ttl: int = 300,  # 5 minutes
) -> Any:
    """
    Generic cached DB lookup with Redis.
    
    Args:
        cache_key: Redis cache key
        db_query_func: Async function that performs the DB query
        ttl: Time-to-live in seconds (default 5 minutes)
        
    Returns:
        Query result (cached or fresh)
    """
    import json
    from shared.redis_client import get_redis_client
    
    redis = get_redis_client()
    
    # Try cache first
    try:
        cached = await redis.get(cache_key)
        if cached:
            logger.debug(f"Cache HIT: {cache_key}")
            return json.loads(cached)
    except Exception as e:
        logger.warning(f"Redis cache read error: {e}")
    
    # Query DB
    logger.debug(f"Cache MISS: {cache_key}")
    result = await db_query_func()
    
    # Cache result
    try:
        await redis.setex(cache_key, ttl, json.dumps(result))
    except Exception as e:
        logger.warning(f"Redis cache write error: {e}")
    
    return result


async def validate_categoria_slug(slug: str) -> tuple[bool, str | None]:
    """
    Validate categoria_slug exists in database.
    
    Args:
        slug: Category slug (e.g., 'motos-part')
        
    Returns:
        Tuple of (is_valid, error_message_or_none)
    """
    cache_key = f"semantic_validation:categoria:{slug}"
    
    async def query():
        async with get_async_session() as session:
            from database.models import VehicleCategory
            result = await session.execute(
                select(VehicleCategory.id).where(
                    VehicleCategory.slug == slug,
                    VehicleCategory.is_active == True,  # noqa: E712
                )
            )
            exists = result.scalar_one_or_none() is not None
            return {"exists": exists}
    
    result = await cached_db_lookup(cache_key, query)
    
    if result["exists"]:
        return (True, None)
    else:
        return (False, f"La categoría '{slug}' no existe en el sistema")


async def validate_element_code(
    code: str,
    categoria_slug: str,
) -> tuple[bool, str | None]:
    """
    Validate element_code exists for the given category.
    
    Args:
        code: Element code (e.g., 'ESCAPE')
        categoria_slug: Category slug to check element belongs to
        
    Returns:
        Tuple of (is_valid, error_message_or_none)
    """
    cache_key = f"semantic_validation:element:{categoria_slug}:{code}"
    
    async def query():
        async with get_async_session() as session:
            from database.models import Element, VehicleCategory
            result = await session.execute(
                select(Element.id)
                .join(VehicleCategory)
                .where(
                    Element.code == code,
                    VehicleCategory.slug == categoria_slug,
                    Element.is_active == True,  # noqa: E712
                    VehicleCategory.is_active == True,  # noqa: E712
                )
            )
            exists = result.scalar_one_or_none() is not None
            return {"exists": exists}
    
    result = await cached_db_lookup(cache_key, query)
    
    if result["exists"]:
        return (True, None)
    else:
        return (
            False,
            f"El elemento '{code}' no existe en la categoría '{categoria_slug}'"
        )


async def validate_case_id(case_id: str) -> tuple[bool, str | None]:
    """
    Validate case exists and is active.
    
    Args:
        case_id: UUID string of the case
        
    Returns:
        Tuple of (is_valid, error_message_or_none)
    """
    from uuid import UUID
    
    # Validate UUID format first
    try:
        uuid_obj = UUID(case_id)
    except (ValueError, TypeError):
        return (False, f"El ID de expediente '{case_id}' no tiene formato válido")
    
    cache_key = f"semantic_validation:case:{case_id}"
    
    async def query():
        async with get_async_session() as session:
            from database.models import Case
            result = await session.execute(
                select(Case.id, Case.is_active).where(Case.id == uuid_obj)
            )
            row = result.one_or_none()
            if not row:
                return {"exists": False, "is_active": False}
            return {"exists": True, "is_active": row.is_active}
    
    result = await cached_db_lookup(cache_key, query, ttl=60)  # Shorter TTL for cases
    
    if not result["exists"]:
        return (False, f"El expediente '{case_id}' no existe")
    elif not result["is_active"]:
        return (False, f"El expediente '{case_id}' está inactivo")
    else:
        return (True, None)


async def validate_user_id(user_id: str) -> tuple[bool, str | None]:
    """
    Validate user exists.
    
    Args:
        user_id: UUID string of the user
        
    Returns:
        Tuple of (is_valid, error_message_or_none)
    """
    from uuid import UUID
    
    # Validate UUID format first
    try:
        uuid_obj = UUID(user_id)
    except (ValueError, TypeError):
        return (False, f"El ID de usuario '{user_id}' no tiene formato válido")
    
    cache_key = f"semantic_validation:user:{user_id}"
    
    async def query():
        async with get_async_session() as session:
            from database.models import User
            result = await session.execute(
                select(User.id).where(User.id == uuid_obj)
            )
            exists = result.scalar_one_or_none() is not None
            return {"exists": exists}
    
    result = await cached_db_lookup(cache_key, query)
    
    if result["exists"]:
        return (True, None)
    else:
        return (False, f"El usuario '{user_id}' no existe")


async def validate_tier_id(
    tier_id: str,
    categoria_slug: str,
) -> tuple[bool, str | None]:
    """
    Validate tier exists for the given category.
    
    Args:
        tier_id: UUID string of the tier
        categoria_slug: Category slug to check tier belongs to
        
    Returns:
        Tuple of (is_valid, error_message_or_none)
    """
    from uuid import UUID
    
    # Validate UUID format first
    try:
        uuid_obj = UUID(tier_id)
    except (ValueError, TypeError):
        return (False, f"El ID de tarifa '{tier_id}' no tiene formato válido")
    
    cache_key = f"semantic_validation:tier:{categoria_slug}:{tier_id}"
    
    async def query():
        async with get_async_session() as session:
            from database.models import TariffTier, VehicleCategory
            result = await session.execute(
                select(TariffTier.id)
                .join(VehicleCategory)
                .where(
                    TariffTier.id == uuid_obj,
                    VehicleCategory.slug == categoria_slug,
                    TariffTier.is_active == True,  # noqa: E712
                    VehicleCategory.is_active == True,  # noqa: E712
                )
            )
            exists = result.scalar_one_or_none() is not None
            return {"exists": exists}
    
    result = await cached_db_lookup(cache_key, query)
    
    if result["exists"]:
        return (True, None)
    else:
        return (
            False,
            f"La tarifa '{tier_id}' no existe en la categoría '{categoria_slug}'"
        )
