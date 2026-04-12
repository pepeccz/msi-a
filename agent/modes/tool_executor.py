"""
MSI-a — Standalone Tool Executor (Phase 3 extraction).

Provides a standalone async function ``execute_and_log_tool()`` that was
previously embedded in BaseModeNode._execute_and_log_tool as an instance
method.

Extracts the full execution pipeline:
- Parameter validation (via get_tool_validator)
- Dedup guard (per-turn cache)
- Timing measurement
- Tool execution
- Result classification
- Structured logging via structlog

Both ``BaseModeNode._execute_and_log_tool`` and ``generic_loop.py`` delegate
to this function — no logic duplication.
"""

from __future__ import annotations

import json as _json
import time as _time
from typing import Any

import structlog
from langchain_core.runnables import RunnableConfig

from agent.utils.tool_helpers import structured_validation_error
from agent.utils.tool_validation import get_tool_validator

logger = structlog.get_logger(__name__)

# Tools excluded from per-turn dedup guard.
# Mirrors the same constant in base_mode.py.
TOOL_DEDUP_EXCLUDED: frozenset[str] = frozenset(
    {
        "escalar_a_humano",
        "enviar_imagenes_ejemplo",
        "iniciar_expediente",
        "finalizar_expediente",
    }
)


def _classify_tool_result(result: str) -> tuple[str, str | None]:
    """
    Classify a tool result string as "success", "error", or "blocked".

    Mirrors BaseModeNode._classify_tool_result — kept as a pure function
    here so it can be used without instantiating BaseModeNode.

    Returns:
        Tuple of (result_type, error_message).
    """
    if not result:
        return ("success", None)

    try:
        data = _json.loads(result)
    except (ValueError, TypeError):
        return (
            "error",
            result[:500] if isinstance(result, str) else str(result)[:500],
        )

    if not isinstance(data, dict):
        return ("success", None)

    if data.get("success") is False or "error" in data:
        error_msg: str | None = (
            data.get("error") or data.get("message") or "Tool returned failure"
        )
        if isinstance(error_msg, str):
            error_msg = error_msg[:500]
        _block_phrases = (
            "ya fueron enviadas",
            "no vuelvas a enviar",
            "ya fue enviada",
            "bloqueando duplicado",
        )
        result_lower = result.lower()
        if any(p in result_lower for p in _block_phrases):
            return ("blocked", None)
        return ("error", error_msg)

    return ("success", None)


def _get_required_params(tool: Any) -> list[str]:
    """Extract required parameter names from tool schema."""
    if not tool.args_schema:
        return []
    required = []
    for field_name, field_info in tool.args_schema.model_fields.items():
        if field_info.is_required():
            required.append(field_name)
    return required


def _generate_fix_suggestion(tool: Any, errors: list[str]) -> str:
    """Generate helpful suggestion for LLM to fix parameters."""
    missing_params = []
    for error in errors:
        if "Missing required parameter:" in error:
            param_name = error.split(":")[-1].strip()
            missing_params.append(param_name)

    if not missing_params:
        return "Please check the parameter values and try again."

    hints = {
        "categoria_slug": "Extract from mode_context['categoria_slug']",
        "tarifa_calculada": "Extract from mode_context['tarifa_calculada']['datos']['price']",
        "tier_id": "Extract from mode_context['tarifa_calculada']['datos']['tier_id']",
        "case_id": "Extract from state or mode_context['case_id']",
        "user_id": "Extract from state['user_id']",
        "datos": (
            'Provide as dict with field_key: value pairs from obtener_campos_elemento(). '
            'Example: guardar_datos_elemento(datos={"marca_placa": "SOLARFAM", "modelo_regulador": "MPPT 100-30I"})'
        ),
    }

    suggestions = []
    for param in missing_params:
        hint = hints.get(param, f"Provide {param}")
        suggestions.append(f"- {param}: {hint}")

    return "Please provide the following parameters:\n" + "\n".join(suggestions)


async def _execute_tool_raw(
    tool_name: str,
    tool_args: dict[str, Any],
    tools: list,
    config: RunnableConfig | None = None,
) -> str:
    """
    Execute a tool by name and return its JSON-encoded result string.

    Finds the tool in the provided list, invokes it with the provided
    RunnableConfig (so tools can access state via get_tool_state(config)),
    and ensures the result is always a string.
    """
    tool_fn = next((t for t in tools if t.name == tool_name), None)

    if tool_fn is None:
        return _json.dumps(
            {"success": False, "error": f"Tool '{tool_name}' not found"},
            ensure_ascii=False,
        )

    try:
        raw = await tool_fn.ainvoke(tool_args, config=config)
        if isinstance(raw, dict):
            return _json.dumps(raw, ensure_ascii=False)
        return str(raw)
    except Exception as exc:
        logger.error("tool_execution_error", tool=tool_name, error=str(exc))
        return _json.dumps(
            {"success": False, "error": str(exc)},
            ensure_ascii=False,
        )


async def execute_and_log_tool(
    *,
    conversation_id: str,
    tool_name: str,
    tool_args: dict[str, Any],
    tools: list,
    tool_call_id: str = "",
    iteration: int = 0,
    dedup_cache: dict[str, str] | None = None,
    bound_logger: Any | None = None,
    log_fn=None,
    config: RunnableConfig | None = None,
) -> str:
    """
    Execute a tool with validation, timing, dedup guard, and persistent logging.

    This is the standalone version of BaseModeNode._execute_and_log_tool.
    Both BaseModeNode and generic_loop.py delegate to this function.

    Args:
        conversation_id: Conversation ID for logging.
        tool_name: Name of the tool to execute.
        tool_args: Tool arguments dict.
        tools: List of available LangChain tool instances.
        tool_call_id: Unique ID of this tool call (for dedup guard). If empty,
            dedup uses (tool_name, args) as key instead.
        iteration: Current tool loop iteration (1-based).
        dedup_cache: Per-turn dedup cache dict. None = guard inactive.
            Pass an empty dict {} to activate the guard.
        bound_logger: Optional bound structlog logger. Defaults to module logger.

    Returns:
        String result from the tool execution (or validation/error JSON).
    """
    _log = bound_logger if bound_logger is not None else logger

    async def _log_tool_call_fn(
        conversation_id: str,
        tool_name: str,
        parameters: dict[str, Any],
        result_summary: str,
        execution_time_ms: int | None = None,
        iteration: int = 0,
        result_type: str = "success",
        error_message: str | None = None,
    ) -> None:
        """Log tool call via structlog (fire-and-forget)."""
        if log_fn is not None:
            await log_fn(
                conversation_id=conversation_id,
                tool_name=tool_name,
                parameters=parameters,
                result_summary=result_summary,
                execution_time_ms=execution_time_ms,
                iteration=iteration,
                result_type=result_type,
                error_message=error_message,
            )
        else:
            _log.info(
                "tool_call",
                conversation_id=conversation_id,
                tool_name=tool_name,
                result_type=result_type,
                execution_time_ms=execution_time_ms,
                iteration=iteration,
                result_summary=result_summary[:200] if result_summary else None,
                error_message=error_message,
            )

    # ── Find tool ────────────────────────────────────────────────────────────
    tool_fn = next((t for t in tools if t.name == tool_name), None)

    if tool_fn is None:
        error_response = {
            "success": False,
            "error": f"Herramienta '{tool_name}' no encontrada",
            "error_type": "tool_not_found",
        }
        return _json.dumps(error_response, ensure_ascii=False)

    # ── Parameter validation ──────────────────────────────────────────────────
    validator = get_tool_validator()

    validation_state: dict[str, Any] = {}
    if config is not None:
        configurable = config.get("configurable") if isinstance(config, dict) else None
        current_state = configurable.get("state") if isinstance(configurable, dict) else None
        if current_state:
            validation_state.update(current_state)
            mode_context = current_state.get("mode_context", {})
            if mode_context:
                validation_state.update(mode_context)

    is_valid, errors, failed_layer = await validator.validate(
        tool=tool_fn,
        params=tool_args,
        state=validation_state,
    )

    if not is_valid:
        _log.warning(
            "tool_parameter_validation_failed",
            tool=tool_name,
            errors=errors,
            validation_layer=failed_layer,
            provided_params=list(tool_args.keys()),
        )

        required_params = _get_required_params(tool_fn)
        suggestion = _generate_fix_suggestion(tool_fn, errors)

        error_response = structured_validation_error(
            tool_name=tool_name,
            validation_errors=errors,
            validation_layer=failed_layer,
            provided_params=list(tool_args.keys()),
            required_params=required_params,
            suggestion=suggestion,
        )

        validation_error_str = _json.dumps(error_response, ensure_ascii=False)

        # Log validation failure — always result_type="error"
        await _log_tool_call_fn(
            conversation_id=conversation_id,
            tool_name=tool_name,
            parameters=tool_args,
            result_summary=validation_error_str[:500],
            execution_time_ms=0,
            iteration=iteration,
            result_type="error",
            error_message=error_response.get(
                "validation_errors", ["parameter_validation"]
            )[0]
            if isinstance(error_response.get("validation_errors"), list)
            else "parameter_validation",
        )

        return validation_error_str

    # ── Dedup guard ───────────────────────────────────────────────────────────
    _dedup_active = dedup_cache is not None and tool_name not in TOOL_DEDUP_EXCLUDED
    _dedup_key: str = ""

    if _dedup_active:
        # Use tool_call_id if provided, otherwise fall back to (name, args) hash
        if tool_call_id:
            _dedup_key = f"id:{tool_call_id}"
        else:
            _dedup_key = (
                f"{tool_name}:{_json.dumps(tool_args, sort_keys=True, default=str)}"
            )

        if _dedup_key in dedup_cache:  # type: ignore[operator]
            _log.debug(
                "tool_call_dedup_hit",
                tool=tool_name,
                conversation_id=conversation_id,
                iteration=iteration,
            )
            return dedup_cache[_dedup_key]  # type: ignore[index]

    # ── Execute ───────────────────────────────────────────────────────────────
    start = _time.time()
    result = await _execute_tool_raw(tool_name, tool_args, tools, config=config)
    elapsed_ms = int((_time.time() - start) * 1000)

    # Store in dedup cache
    if _dedup_active and _dedup_key:
        dedup_cache[_dedup_key] = result  # type: ignore[index]

    # ── Classify and log ──────────────────────────────────────────────────────
    result_type, error_message = _classify_tool_result(result)

    await _log_tool_call_fn(
        conversation_id=conversation_id,
        tool_name=tool_name,
        parameters=tool_args,
        result_summary=result[:500] if isinstance(result, str) else str(result)[:500],
        execution_time_ms=elapsed_ms,
        iteration=iteration,
        result_type=result_type,
        error_message=error_message,
    )

    return result
