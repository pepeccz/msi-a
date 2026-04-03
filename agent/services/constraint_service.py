"""
MSI Automotive - Response Constraint Service.

Provides database-driven validation of LLM responses to prevent hallucinations.
Loads constraints from PostgreSQL and checks agent responses against them.
Constraints define regex patterns that detect potential violations and the
tools that must have been called to produce that information legitimately.
"""

import re
import structlog
import time
from typing import Any

from sqlalchemy import select

from database.connection import get_async_session
from database.models import ResponseConstraint

logger = structlog.get_logger(__name__)


# In-memory cache for constraints (per category)
_constraints_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_CACHE_TTL_SECONDS = 300  # 5 minutes

# Constraint types where regex detection is deterministic enough — skip LLM confirmation.
# These constraints have high-precision regex patterns that rarely produce false positives,
# making LLM confirmation unnecessary and potentially harmful (small models may misjudge).
_REGEX_ONLY_CONSTRAINTS: set[str] = {"price_requires_tool", "expediente_requires_tool"}


async def get_constraints_for_category(
    category_slug: str | None,
) -> list[dict[str, Any]]:
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
                select(ResponseConstraint).where(ResponseConstraint.is_active == True)  # noqa: E712
            )

            if category_id:
                query = query.where(
                    (ResponseConstraint.category_id == None)  # noqa: E711
                    | (ResponseConstraint.category_id == category_id)
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
                "constraints_loaded",
                count=len(constraint_dicts),
                category=cache_key,
            )
            return constraint_dicts

    except Exception as e:
        logger.error(
            "constraints_load_error",
            error=str(e),
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
                "constraint_skipped",
                constraint_type=constraint_type,
                sub_mode=expediente_sub_mode,
                has_tariff=has_tariff,
                presupuesto_done=presupuesto_done,
                has_tarifa_calculada=has_tarifa_calculada,
            )
            return True

    # Skip images_narration_blocked when images were already sent.
    # After delivery, the constraint's purpose (prevent narrating image
    # sending without calling the tool) is fulfilled.
    if constraint_type == "images_narration_blocked":
        if fsm_state.get("imagenes_enviadas"):
            logger.debug(
                "constraint_skipped",
                constraint_type=constraint_type,
                reason="imagenes_enviadas",
            )
            return True

    # Skip expediente_requires_tool when already in EXPEDIENTE mode.
    # In EXPEDIENTE mode, asking for personal data IS the correct behavior.
    # Note: if confirmar_presupuesto was called THIS turn, the
    # tools_called_this_turn check in validate_response_hybrid (line 323)
    # already handles it — the required tool WAS called.
    if constraint_type == "expediente_requires_tool":
        # expediente_sub_mode is set when in any EXPEDIENTE sub-mode
        expediente_sub_mode = fsm_state.get("expediente_sub_mode")
        # case_id is set when a case has been created (via confirmar_presupuesto)
        has_case = fsm_state.get("case_id") is not None
        if expediente_sub_mode or has_case:
            logger.debug(
                "constraint_skipped",
                constraint_type=constraint_type,
                sub_mode=expediente_sub_mode,
                has_case=has_case,
            )
            return True

    return False


def validate_response(
    response_text: str,
    tools_called_this_turn: set[str],
    constraints: list[dict[str, Any]],
    fsm_state: dict[str, Any] | None = None,
    available_tool_names: set[str] | None = None,
) -> tuple[bool, str | None]:
    """
    Validate an LLM response against loaded constraints (regex-only, synchronous).

    For each constraint, checks if the detection_pattern matches the response.
    If it does, verifies that the required_tool was called in this turn.
    If not, the response is invalid and the error_injection message is returned.

    Args:
        response_text: The LLM's generated response text.
        tools_called_this_turn: Set of tool names called during this turn.
        constraints: List of constraint dicts from get_constraints_for_category().
        fsm_state: Current FSM state (to determine if constraints should be skipped).
        available_tool_names: Set of tool names available in the current mode.
            If provided, constraints whose required tools are not available
            in this set will be skipped (prevents false violations in modes
            that don't have the required tools).

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

        # Skip constraint if required tools are not available in the current mode
        if available_tool_names is not None:
            required_tools = {t.strip() for t in required_tool_str.split("|")}
            if not required_tools.intersection(available_tool_names):
                if constraint_type == "price_requires_tool":
                    _fsm = fsm_state or {}
                    if _fsm.get("tarifa_calculada") is not None:
                        logger.debug(
                            "constraint_skipped_tarifa_exists",
                            constraint_type=constraint_type,
                            available_count=len(available_tool_names),
                        )
                        continue  # OK — price from previous calculation
                    # tarifa_calculada absent — fall through to enforcement
                else:
                    logger.debug(
                        "constraint_skipped_tools_unavailable",
                        constraint_type=constraint_type,
                        required_tools=list(required_tools),
                        available_count=len(available_tool_names),
                    )
                    continue

        try:
            # Check if the response matches the detection pattern
            if re.search(detection_pattern, response_text, re.IGNORECASE):
                # Pattern matched - check if required tool was called
                required_tools = {t.strip() for t in required_tool_str.split("|")}

                if not tools_called_this_turn.intersection(required_tools):
                    # Violation: pattern detected but required tool not called
                    logger.warning(
                        "constraint_violation",
                        constraint_type=constraint["constraint_type"],
                        required_tools=list(required_tools),
                        called_tools=list(tools_called_this_turn),
                    )
                    return False, error_injection

        except re.error as e:
            logger.error(
                "constraint_invalid_regex",
                constraint_type=constraint["constraint_type"],
                error=str(e),
            )
            continue

    return True, None


async def validate_response_hybrid(
    response_text: str,
    tools_called_this_turn: set[str],
    constraints: list[dict[str, Any]],
    fsm_state: dict[str, Any] | None = None,
    available_tool_names: set[str] | None = None,
) -> tuple[bool, str | None]:
    """
    Hybrid validation: regex pre-filter + LLM confirmation (async).

    Flow:
    1. Run regex validation (fast, 0ms)
    2. If regex says VALID → return valid immediately (no LLM needed)
    3. If regex says VIOLATION → ask LLM Tier 1 to confirm or discard
    4. If LLM says false positive → return valid (discard regex match)
    5. If LLM says real violation or LLM unavailable → return regex result

    Args:
        response_text: The LLM's generated response text.
        tools_called_this_turn: Set of tool names called during this turn.
        constraints: List of constraint dicts from get_constraints_for_category().
        fsm_state: Current FSM state (to determine if constraints should be skipped).
        available_tool_names: Set of tool names available in the current mode.
            If provided, constraints whose required tools are not available
            in this set will be skipped (prevents false violations in modes
            that don't have the required tools).

    Returns:
        Tuple of (is_valid, error_injection_or_none).
    """
    if not response_text or not constraints:
        return True, None

    # Step 1: Find the first constraint that triggers (regex pass)
    for constraint in constraints:
        constraint_type = constraint["constraint_type"]
        detection_pattern = constraint["detection_pattern"]
        required_tool_str = constraint["required_tool"]
        error_injection = constraint["error_injection"]

        if _should_skip_constraint(constraint_type, fsm_state):
            continue

        # Compute required_tools ONCE for both availability and called-tools checks
        required_tools = {t.strip() for t in required_tool_str.split("|")}

        # Skip constraint if required tools are not available in the current mode
        if available_tool_names is not None:
            if not required_tools.intersection(available_tool_names):
                if constraint_type == "price_requires_tool":
                    _fsm = fsm_state or {}
                    if _fsm.get("tarifa_calculada") is not None:
                        logger.debug(
                            "constraint_skipped_tarifa_exists",
                            constraint_type=constraint_type,
                            available_count=len(available_tool_names),
                        )
                        continue  # OK — price from previous calculation
                    # tarifa_calculada absent — fall through to enforcement
                else:
                    logger.debug(
                        "constraint_skipped_no_tools",
                        constraint_type=constraint_type,
                        required_tools=list(required_tools),
                        available_count=len(available_tool_names),
                    )
                    continue

        try:
            if re.search(detection_pattern, response_text, re.IGNORECASE):
                if not tools_called_this_turn.intersection(required_tools):
                    # For regex-only constraints, skip LLM confirmation entirely.
                    # The regex pattern is deterministic and sufficient; small LLMs
                    # (e.g. qwen2.5:3b) may incorrectly discard real violations.
                    if constraint_type in _REGEX_ONLY_CONSTRAINTS:
                        logger.warning(
                            "constraint_violation_regex_only",
                            constraint_type=constraint_type,
                            required_tools=list(required_tools),
                            tools_called=list(tools_called_this_turn),
                        )
                        return False, error_injection

                    # Regex says VIOLATION — Step 2: ask LLM to confirm
                    logger.info(
                        "constraint_regex_match_llm_check",
                        constraint_type=constraint_type,
                    )

                    is_false_positive = await validate_with_llm(
                        response_text,
                        tools_called_this_turn,
                        constraint_type,
                    )

                    if is_false_positive is True:
                        # LLM says false positive — discard regex match
                        logger.info(
                            "constraint_false_positive_discarded",
                            constraint_type=constraint_type,
                        )
                        logger.info(
                            "constraint_validation_optimized",
                            llm_skipped=False,
                            regex_confidence="inconclusive",
                            constraint_type=constraint_type,
                        )
                        continue  # Skip this constraint, check remaining ones

                    # LLM confirms violation (False) or is unavailable (None)
                    # → Trust regex result
                    logger.warning(
                        "constraint_violation_confirmed",
                        constraint_type=constraint_type,
                        llm_result="confirmed"
                        if is_false_positive is False
                        else "unavailable (regex fallback)",
                    )
                    logger.info(
                        "constraint_validation_optimized",
                        llm_skipped=False,
                        regex_confidence="low",
                        constraint_type=constraint_type,
                    )
                    return False, error_injection

        except re.error as e:
            logger.error(
                "constraint_invalid_regex",
                constraint_type=constraint_type,
                error=str(e),
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
    logger.info("constraint_cache_invalidated", category=category_slug or "all")


# ============================================================================
# PHASE 2: HYBRID VALIDATION (Regex pre-filter + LLM confirmation)
# ============================================================================

# Validation prompt template (~200 tokens input for qwen2.5:3b)
_VALIDATION_PROMPT = """You are a response validator for a vehicle homologation agent.
Analyze whether the AGENT RESPONSE contains information that should ONLY come from tools.

TOOLS CALLED THIS TURN: {tools_called}
CONSTRAINT TYPE: {constraint_type}
AGENT RESPONSE (truncated): {response_text}

RULES:
- If the agent SUMMARIZES or CONFIRMS information previously calculated by a tool → VALID
- If the agent INVENTS prices, variants, or documentation without any tool → INVALID
- If the agent mentions data that came from a tool result in this turn → VALID
- If the agent is transitioning modes or confirming next steps → VALID

Respond ONLY with JSON (no markdown, no explanation):
{{"valid": true}}
or
{{"valid": false, "reason": "brief explanation"}}"""


async def validate_with_llm(
    response_text: str,
    tools_called: set[str],
    constraint_type: str,
) -> bool | None:
    """
    Use LLM Tier 1 (qwen2.5:3b, local) to confirm or discard a regex constraint match.

    This is the second pass of hybrid validation:
    1. Regex detected a potential violation (fast, high recall, some false positives)
    2. LLM confirms whether it's a REAL violation or a false positive (slower, high precision)

    Args:
        response_text: The LLM response that matched the regex
        tools_called: Set of tool names called this turn
        constraint_type: Type of constraint that was triggered

    Returns:
        True if LLM confirms it IS a false positive (response is actually valid)
        False if LLM confirms the violation is real
        None if LLM is unavailable or errors (caller should fall back to regex result)
    """
    from shared.config import get_settings

    settings = get_settings()

    # Feature flag check
    if not settings.USE_LLM_CONSTRAINT_VALIDATION:
        logger.debug("LLM constraint validation disabled by config")
        return None

    if not settings.USE_HYBRID_LLM:
        logger.debug("Hybrid LLM disabled, skipping LLM constraint validation")
        return None

    import json  # Must be before try block so except json.JSONDecodeError is always bound

    try:
        from shared.llm_router import get_llm_router, TaskType

        router = get_llm_router()

        # Build validation prompt
        prompt = _VALIDATION_PROMPT.format(
            tools_called=", ".join(tools_called) if tools_called else "none",
            constraint_type=constraint_type,
            response_text=response_text[:300],  # Truncate for token efficiency
        )

        # Call LLM Tier 1 with disable_fallback=True (NEVER escalate to cloud)
        llm_response = await router.invoke(
            task_type=TaskType.CONSTRAINT_VALIDATION,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,  # Maximum determinism for binary classification
            max_tokens=100,  # Short JSON response expected
            disable_fallback=True,  # CRITICAL: Never use cloud for validation
        )

        if not llm_response.success or not llm_response.content:
            logger.warning(
                "llm_constraint_validation_failed",
                constraint_type=constraint_type,
                error=llm_response.error,
            )
            return None  # Fallback to regex

        # Parse JSON response
        content = llm_response.content.strip()

        # Handle common LLM quirks: markdown wrapping
        if content.startswith("```"):
            # Strip ```json ... ``` wrapper
            lines = content.split("\n")
            content = "\n".join(
                line for line in lines if not line.strip().startswith("```")
            ).strip()

        result = json.loads(content)

        is_valid = result.get("valid", False)
        reason = result.get("reason", "")

        logger.info(
            "llm_constraint_validation_result",
            constraint_type=constraint_type,
            llm_valid=is_valid,
            reason=reason,
            latency_ms=llm_response.latency_ms,
            model=llm_response.model,
        )

        # Return True if LLM says "valid" (= false positive from regex)
        return is_valid

    except json.JSONDecodeError as e:
        # llm_response is always bound here — JSONDecodeError only fires from
        # json.loads(content) which is after llm_response is assigned
        raw = llm_response.content[:200] if llm_response else "N/A"  # type: ignore[possibly-undefined]
        logger.warning(
            "llm_constraint_validation_json_parse_error",
            constraint_type=constraint_type,
            error=str(e),
            raw_content=raw,
        )
        return None  # Fallback to regex

    except Exception as e:
        logger.warning(
            "llm_constraint_validation_error",
            constraint_type=constraint_type,
            error=str(e),
        )
        return None  # Fallback to regex — NEVER block the agent


# ============================================================================
# PHASE 2 (EXISTING): SEMANTIC VALIDATION (Database-backed validators)
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
            logger.debug("cache_hit", cache_key=cache_key)
            return json.loads(cached)
    except Exception as e:
        logger.warning("redis_cache_read_error", cache_key=cache_key, error=str(e))

    # Query DB
    logger.debug("cache_miss", cache_key=cache_key)
    result = await db_query_func()

    # Cache result
    try:
        await redis.setex(cache_key, ttl, json.dumps(result))
    except Exception as e:
        logger.warning("redis_cache_write_error", cache_key=cache_key, error=str(e))

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
            f"El elemento '{code}' no existe en la categoría '{categoria_slug}'",
        )


async def validate_case_id(case_id: str) -> tuple[bool, str | None]:
    """
    Validate case exists and is in an active status.

    The Case model uses a `status` field (not `is_active` boolean).
    Active statuses: collecting, pending_images, pending_review, in_progress.
    Inactive statuses: resolved, cancelled, abandoned.

    Args:
        case_id: UUID string of the case

    Returns:
        Tuple of (is_valid, error_message_or_none)
    """
    from uuid import UUID

    ACTIVE_STATUSES = ["collecting", "pending_images", "pending_review", "in_progress"]

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
                select(Case.id, Case.status).where(Case.id == uuid_obj)
            )
            row = result.one_or_none()
            if not row:
                return {"exists": False, "status": None}
            return {"exists": True, "status": row.status}

    result = await cached_db_lookup(cache_key, query, ttl=60)  # Shorter TTL for cases

    if not result["exists"]:
        return (False, f"El expediente '{case_id}' no existe")
    elif result["status"] not in ACTIVE_STATUSES:
        return (False, f"El expediente '{case_id}' está {result['status']}")
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

            result = await session.execute(select(User.id).where(User.id == uuid_obj))
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
            f"La tarifa '{tier_id}' no existe en la categoría '{categoria_slug}'",
        )
