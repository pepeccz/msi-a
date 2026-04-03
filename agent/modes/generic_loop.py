"""
MSI-a — Generic LLM Loop (Phase 2 refactor).

Provides a single ``generic_llm_loop()`` function that replaces the
inline tool-calling loops duplicated across presupuesto_mode, consulta_mode,
and expediente's loop_engine.

Key design decisions:
- Pure function signature: LLM is injected → easy to test without real API.
- ContextVar state is set before each iteration so tools can access
  conversation context (same pattern as all existing modes).
- _internal_flags from tool results are applied to context_updates, which
  the caller merges into mode_context after the loop completes.
- on_tool_result callback allows callers to react to tool results
  (e.g. presupuesto_mode needs to extract pending_images, inject S4 price).

Feature flag: USE_GENERIC_LOOP (shared/config.py) — disabled by default.
Enable to activate this loop in modes (T2.2 wires up the flag).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import structlog

from agent.state.helpers import set_current_state

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class GenericLoopResult:
    """
    Result returned by ``generic_llm_loop()``.

    Attributes:
        ai_response:     Final text response from the LLM (empty string if
                         the loop exited due to max_iterations without a plain
                         text turn).
        tools_called:    Set of tool names that were called at least once.
        tool_results:    List of raw result dicts from all tool executions
                         (in call order).
        context_updates: Accumulated state updates collected from tool results.
                         Contains _internal_flags values merged from every tool
                         that returned them.
        exit_reason:     Why the loop stopped:
                         - "response"       → LLM produced a plain text turn.
                         - "max_iterations" → hit the iteration cap.
                         - "error"          → unexpected exception.
    """

    ai_response: str = ""
    tools_called: set[str] = field(default_factory=set)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    context_updates: dict[str, Any] = field(default_factory=dict)
    exit_reason: str = "response"  # "response" | "max_iterations" | "error"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_result(raw: Any, tool_name: str) -> dict[str, Any]:
    """
    Coerce a raw tool result (str or dict) into a dict.

    ``tool.ainvoke()`` can return either a dict or a JSON string depending
    on how the tool is implemented.  This function normalises both shapes
    so callers always work with a dict.
    """
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {"_raw": parsed}
        except (json.JSONDecodeError, TypeError):
            return {"success": False, "error": raw, "_raw": raw}
    return {"success": False, "error": f"unexpected type: {type(raw).__name__}"}


def _apply_internal_flags(
    context_updates: dict[str, Any],
    result_dict: dict[str, Any],
) -> None:
    """
    Merge ``result_dict["_internal_flags"]`` into *context_updates* in-place.

    Separates the ``_transition_to`` signal from plain context flags:
    - ``_transition_to`` is preserved as-is so callers can trigger mode transitions.
    - All other flags are merged directly into *context_updates*.
    """
    flags = result_dict.get("_internal_flags")
    if not flags or not isinstance(flags, dict):
        return

    # Copy so we don't mutate the original dict
    flags = dict(flags)

    # Preserve transition signal as a top-level key
    transition_to = flags.pop("_transition_to", None)
    if transition_to is not None:
        context_updates["_transition_to"] = transition_to

    # Merge remaining flags
    context_updates.update(flags)


async def _execute_tool(
    tool_name: str,
    tool_args: dict[str, Any],
    tools: list,
) -> str:
    """
    Execute a tool by name from *tools* and return its JSON-encoded result string.

    Returns a JSON error string if the tool is not found or raises.
    This replicates the minimal logic of ``BaseModeNode._execute_tool`` as a
    standalone function — no class required.
    """
    tool_fn = next((t for t in tools if t.name == tool_name), None)

    if tool_fn is None:
        return json.dumps(
            {"success": False, "error": f"Tool '{tool_name}' not found"},
            ensure_ascii=False,
        )

    try:
        raw = await tool_fn.ainvoke(tool_args)
        if isinstance(raw, dict):
            return json.dumps(raw, ensure_ascii=False)
        return str(raw)
    except Exception as exc:
        logger.error("generic_loop_tool_error", tool=tool_name, error=str(exc))
        return json.dumps(
            {"success": False, "error": str(exc)},
            ensure_ascii=False,
        )


def _ai_message_to_dict(response: Any) -> dict[str, Any]:
    """
    Convert an LLM AIMessage to a plain dict for the messages list.

    Mirrors ``BaseModeNode._ai_message_to_dict``.
    """
    msg: dict[str, Any] = {
        "role": "assistant",
        "content": response.content or "",
    }
    if hasattr(response, "tool_calls") and response.tool_calls:
        msg["tool_calls"] = [
            {
                "id": tc["id"],
                "name": tc["name"],
                "args": tc["args"],
            }
            for tc in response.tool_calls
        ]
    return msg


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def generic_llm_loop(
    *,
    system_prompt: str,
    messages: list[dict],
    tools: list,
    max_iterations: int = 12,
    conversation_id: str,
    mode_name: str,
    state: dict,
    llm: Any,
    on_tool_result: Callable[..., Awaitable[dict[str, Any] | None]] | None = None,
    pre_call_tools: list[tuple[str, dict]] | None = None,
) -> GenericLoopResult:
    """
    Generic LLM tool-calling loop shared across all modes.

    Runs the LLM in a loop, executing tool calls until the model produces a
    plain text response or the iteration cap is reached.

    Args:
        system_prompt:   System prompt string (already assembled by the caller).
        messages:        Formatted conversation history (list of role/content dicts).
        tools:           List of LangChain tool instances available this turn.
        max_iterations:  Maximum number of LLM invocations before forcing exit.
                         Defaults to 12 (conservative safety cap).
        conversation_id: Used for ContextVar state and logging.
        mode_name:       Mode name for structured logging.
        state:           Current ConversationState dict.  Set into ContextVar
                         before each iteration so tools can access it.
        llm:             Bound LLM instance (already has tools bound if needed).
                         Injected so tests can pass a mock without real API keys.
        on_tool_result:  Optional async callback invoked after each tool execution.
                         Signature:
                             ``async (tool_name, result_dict, tool_args, context_updates)
                               -> dict | None``.
                         The callback receives the CURRENT context_updates accumulator
                         (not a snapshot), so it can read flags applied by earlier tools.

                         The callback MAY return a dict with any of these optional keys:

                         ``inject_messages`` (list[dict]) — messages to append to
                             ``llm_messages`` before the next LLM invocation.  Used to
                             update the LLM's world-view after a state change (e.g. all
                             variants resolved).  Each entry is a plain dict with at
                             least ``role`` and ``content`` keys.

                         ``rebind_tools`` (list) — if provided, the current LLM
                             binding is replaced with a new one using these tools.
                             Allows switching from a restricted toolset (e.g. only
                             ``seleccionar_variante``) to the full toolset once the
                             condition that triggered the restriction is resolved.

                         ``rebind_tool_choice`` (str | None) — ``tool_choice`` value
                             to use when rebinding.  Defaults to ``None`` (auto) if
                             ``rebind_tools`` is provided but this key is absent.

        pre_call_tools:  Optional list of ``(tool_name, tool_args)`` pairs to execute
                         BEFORE the LLM loop starts.  Results are appended to the message
                         list as ToolMessages so the LLM sees them on the first call.
                         Used by expediente review_summary pre-call pattern.

    Returns:
        ``GenericLoopResult`` with ai_response, tools_called, tool_results,
        context_updates, and exit_reason.
    """
    result = GenericLoopResult()

    # ── Build initial message list ───────────────────────────────────────────
    llm_messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        *messages,
    ]

    # ── Pre-call tools (optional) ────────────────────────────────────────────
    if pre_call_tools:
        for pre_tool_name, pre_tool_args in pre_call_tools:
            raw_pre = await _execute_tool(pre_tool_name, pre_tool_args, tools)
            # Use a synthetic tool_call_id for pre-call results
            llm_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": f"pre_call_{pre_tool_name}",
                    "content": raw_pre,
                }
            )

    # ── Main loop ────────────────────────────────────────────────────────────
    for iteration in range(max_iterations):
        # Set ContextVar so tools can access conversation state.
        # T2.5: A single set_current_state() is sufficient — image_tools now
        # uses the shared ContextVar from agent.state.helpers (REQ-P2-2).
        full_state = dict(state)
        full_state["conversation_id"] = conversation_id
        set_current_state(full_state)

        # Invoke LLM
        try:
            response = await llm.ainvoke(llm_messages)
        except Exception as exc:
            logger.error(
                "generic_loop_llm_error",
                iteration=iteration,
                mode=mode_name,
                error=str(exc),
            )
            result.exit_reason = "error"
            result.ai_response = (
                "Lo siento, he tenido un problema procesando tu mensaje. "
                "Por favor, inténtalo de nuevo."
            )
            return result

        # Check for tool calls
        tool_calls = getattr(response, "tool_calls", None)

        if not tool_calls:
            # Plain text response — loop exits normally
            result.ai_response = response.content or ""
            result.exit_reason = "response"
            return result

        # Append the assistant's tool-call turn to the message list
        llm_messages.append(_ai_message_to_dict(response))

        # Execute each tool call in this LLM response
        for tool_call in tool_calls:
            tc_name: str = tool_call["name"]
            tc_args: dict = tool_call["args"]
            tc_id: str = tool_call["id"]

            result.tools_called.add(tc_name)

            logger.info(
                "generic_loop_tool_call",
                tool=tc_name,
                iteration=iteration + 1,
                mode=mode_name,
                conversation_id=conversation_id,
            )

            # Execute the tool (with logging via standalone executor)
            from agent.modes.tool_executor import execute_and_log_tool

            raw_result = await execute_and_log_tool(
                conversation_id=conversation_id,
                tool_name=tc_name,
                tool_args=tc_args,
                tools=tools,
                tool_call_id=tc_id,
                iteration=iteration + 1,
                dedup_cache=None,  # generic_loop manages its own dedup via tool_call_id
            )
            result_dict = _parse_result(raw_result, tc_name)
            result.tool_results.append(result_dict)

            # Apply _internal_flags to context_updates
            _apply_internal_flags(result.context_updates, result_dict)

            # Append ToolMessage with correct protocol (role="tool" + tool_call_id)
            llm_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": raw_result,
                }
            )

            # Fire on_tool_result callback if provided
            if on_tool_result is not None:
                try:
                    cb_result = await on_tool_result(
                        tc_name, result_dict, tc_args, result.context_updates
                    )

                    # Handle optional hook response
                    if isinstance(cb_result, dict):
                        # 1. inject_messages — append state-update messages so the
                        #    LLM sees the current world-view on the next invocation.
                        inject_msgs = cb_result.get("inject_messages")
                        if inject_msgs and isinstance(inject_msgs, list):
                            llm_messages.extend(inject_msgs)
                            logger.info(
                                "generic_loop_messages_injected",
                                tool=tc_name,
                                count=len(inject_msgs),
                                mode=mode_name,
                                conversation_id=conversation_id,
                            )

                        # 2. rebind_tools — replace the LLM binding with a new
                        #    toolset (and optionally a different tool_choice).
                        rebind_tools = cb_result.get("rebind_tools")
                        if rebind_tools is not None and isinstance(rebind_tools, list):
                            rebind_tc = cb_result.get("rebind_tool_choice")
                            # llm must support .bind_tools() — standard for
                            # ChatOpenAI / ChatAnthropic / compatible wrappers.
                            try:
                                bind_kwargs: dict[str, Any] = {}
                                if rebind_tc is not None:
                                    bind_kwargs["tool_choice"] = rebind_tc
                                llm = llm.bind_tools(rebind_tools, **bind_kwargs)
                                # Update the tools list so _execute_tool resolves
                                # newly-bound tools by name in subsequent iterations.
                                tools = rebind_tools
                                logger.info(
                                    "generic_loop_tools_rebound",
                                    tool=tc_name,
                                    new_tool_count=len(rebind_tools),
                                    tool_choice=rebind_tc,
                                    mode=mode_name,
                                    conversation_id=conversation_id,
                                )
                            except Exception as bind_exc:
                                logger.warning(
                                    "generic_loop_rebind_error",
                                    tool=tc_name,
                                    error=str(bind_exc),
                                )

                except Exception as cb_exc:
                    logger.warning(
                        "generic_loop_callback_error",
                        tool=tc_name,
                        error=str(cb_exc),
                    )

        # Update ContextVar with latest context_updates after all tools in this iteration
        updated_state = {**full_state, **result.context_updates}
        set_current_state(updated_state)

    # Loop exhausted without a plain-text response
    result.exit_reason = "max_iterations"
    logger.warning(
        "generic_loop_max_iterations",
        mode=mode_name,
        conversation_id=conversation_id,
        max_iterations=max_iterations,
        tools_called=list(result.tools_called),
    )
    return result
