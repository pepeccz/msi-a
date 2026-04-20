"""
MSI-a — Mode Tool Loop Factory (AD-1).

Provides ``build_mode_tool_loop(config: ModeLoopConfig)`` — a factory that
returns a compiled LangGraph StateGraph subgraph implementing the standard
LLM + tool-call loop pattern.

Subgraph topology:
    llm_node → tools_or_end → custom_tool_node → post_tool_node → llm_node

Design decisions:
- AD-1: Custom tool_node (NOT langgraph.prebuilt.ToolNode) — needs validation,
  dedup guard, logging via tool_executor.execute_and_log_tool, and _state_update
  extraction. The prebuilt ToolNode doesn't support these.
- AD-2: Tools access state via RunnableConfig.configurable["state"] — no ContextVar.
- AD-3: Dedicated ToolLoopState TypedDict (messages add reducer, etc.).
- AD-5: Error handling — exceptions become ToolMessages so LLM can recover.

Usage::

    config = ModeLoopConfig(
        mode_name="PRE_EXPEDIENTE_MODE",
        get_tools=lambda ctx: [listar_categorias, listar_elementos, ...],
        get_system_prompt=lambda state: assemble_system_prompt("PRE_EXPEDIENTE_MODE", ...),
        post_tool_hook=None,
        max_iterations=8,
    )
    subgraph = build_mode_tool_loop(config)
    result = await subgraph.ainvoke(initial_state, config=runnable_config)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable, NamedTuple

import structlog
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage

from langgraph.graph import StateGraph, START, END

from agent.modes.tool_loop_state import ToolLoopState

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# ToolLoopResult NamedTuple
# ---------------------------------------------------------------------------


class ToolLoopResult(NamedTuple):
    """
    Return type for build_mode_tool_loop().

    Attributes:
        graph: The compiled LangGraph StateGraph subgraph ready for ainvoke().
        recursion_limit: The recursion limit that MUST be passed as
            ``config={"recursion_limit": loop_result.recursion_limit}``
            at every ainvoke() call so LangGraph actually enforces it.
    """

    graph: Any
    recursion_limit: int


# ---------------------------------------------------------------------------
# ModeLoopConfig dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModeLoopConfig:
    """
    Configuration for build_mode_tool_loop().

    Attributes:
        mode_name:
            The mode identifier (e.g. ``"PRE_EXPEDIENTE_MODE"``). Used in
            structured logging to tag every loop event.

        get_tools:
            Callable ``(mode_context: dict) -> list`` that returns the list
            of LangChain tools available for this mode/turn. Called once per
            graph invocation with the current _mode_context.

        get_system_prompt:
            Callable ``(state: dict) -> str`` that assembles the system prompt
            for llm_node. Receives the full ToolLoopState dict so it can read
            _mode_context, _conversation_id, etc.

        post_tool_hook:
            Optional async callable ``(tool_name, result_dict, state) -> dict``
            invoked by post_tool_node after each tool turn. Should return
            additional state updates to merge into pending_state_updates.
            None means no post-tool domain logic (suitable for CONSULTA).

        max_iterations:
            Maximum LLM invocations before the recursion_limit guard fires.
            Defaults to 10. The graph is compiled with ``recursion_limit =
            max_iterations * 3 + 5`` to accommodate the 3-node triple per
            iteration (llm_node + custom_tool_node + post_tool_node).

        max_tokens:
            Maximum tokens for the LLM response. Defaults to 1500.

        _llm_override:
            Internal — for testing only. When set, the factory uses this LLM
            instead of building one from Settings. Not part of the public API.
    """

    mode_name: str
    get_tools: Callable[[dict], list]
    get_system_prompt: Callable[[dict], str]
    post_tool_hook: Callable[[str, dict, dict], Awaitable[dict]] | None
    max_iterations: int = 10
    max_tokens: int = 1500
    get_tool_choice: Callable[[dict], str | None] | None = None
    _llm_override: Any = field(default=None, compare=False, hash=False)


# ---------------------------------------------------------------------------
# Standalone conditional edge function (importable for unit tests)
# ---------------------------------------------------------------------------


def tools_or_end(state: dict) -> str:
    """
    Conditional edge: route to 'custom_tool_node' if the last AIMessage has
    tool_calls, or to END otherwise.

    Routes to END when ANY of these transition signals are present:
    - ``_transition_to`` in pending_state_updates (ADR-005 canonical key, written by
      tools via ``_state_update`` → ``post_tool_node`` → ``pending_state_updates``).
    - ``_transition_to`` in _mode_context (already merged on a previous iteration).
    - ``pending_mode_transition`` in either location (legacy backward-compat key).

    This check is evaluated BEFORE inspecting tool_calls, ensuring that a transition
    signal always exits the loop even if the subsequent LLM iteration emits tool_calls
    (e.g., with tool_choice="required").

    Uses duck-typing instead of isinstance() to avoid class identity issues
    when langchain_core.messages is reloaded in test environments that
    manipulate sys.modules between test files.

    Args:
        state: Current ToolLoopState (or compatible dict).

    Returns:
        "custom_tool_node" or END.
    """
    messages = state.get("messages", [])
    mode_context = dict(state.get("_mode_context") or {})

    # Merge pending mode_context updates so transition signals from
    # post_tool_hook are visible (same pattern as llm_node).
    pending = state.get("pending_state_updates") or {}
    pending_mc = pending.get("mode_context")
    if isinstance(pending_mc, dict):
        mode_context.update(pending_mc)

    # Check for a pending mode transition → exit cleanly.
    # ADR-005: canonical channel is _transition_to (written by tools via _state_update).
    #
    # post_tool_node stores tool _state_update keys at the TOP LEVEL of
    # pending_state_updates (e.g. pending_state_updates["_transition_to"]).
    # tools_or_end must check both:
    #   1. mode_context (already merged from _mode_context + pending_state_updates.mode_context)
    #   2. pending_state_updates top-level (where _state_update keys land directly)
    #
    # Legacy: pending_mode_transition (kept for backward compat — bridges at
    # expediente_state.py:362-370 and pre_expediente_mode.py:597-612 still use it).
    # Either key alone is sufficient to exit; order reflects canonical-first precedence.
    transition = (
        mode_context.get("_transition_to")
        or pending.get("_transition_to")
        or mode_context.get("pending_mode_transition")
        or pending.get("pending_mode_transition")
    )
    if transition:
        if mode_context.get("_transition_to") or pending.get("_transition_to"):
            key_used = "_transition_to"
        else:
            key_used = "pending_mode_transition"
        logger.info(
            "tools_or_end_transition_detected",
            transition=transition,
            key=key_used,
        )
        return END

    # Must have messages
    if not messages:
        return END

    last_msg = messages[-1]

    # Duck-typing check: AIMessage or AIMessageChunk (both carry tool_calls)
    # We do NOT use isinstance() because langchain_core.messages may have been
    # reimported (creating a new class object) in environments that restore
    # sys.modules between test files (e.g. conftest pytest_collectstart).
    if type(last_msg).__name__ not in ("AIMessage", "AIMessageChunk"):
        return END

    tool_calls = getattr(last_msg, "tool_calls", None) or []
    if tool_calls:
        return "custom_tool_node"

    return END


# ---------------------------------------------------------------------------
# Parallel pending_variants merge
# ---------------------------------------------------------------------------


def _merge_pending_variants(
    existing: list[dict], incoming: list[dict]
) -> list[dict]:
    """
    Merge two pending_variants lists from parallel tool calls.

    Each ``seleccionar_variante_por_respuesta`` call resolves ONE entry but
    returns the FULL list (with stale snapshots of the others). A naive
    last-write-wins would undo the first tool's resolution.

    Strategy: index both lists by ``codigo_base``. For each entry, keep the
    version with higher ``cantidad_resuelta`` (i.e. more progress).
    """
    if not existing:
        return incoming
    if not incoming:
        return existing

    # Build lookup by codigo_base from existing (first tool's result)
    by_code: dict[str, dict] = {}
    for entry in existing:
        code = entry.get("codigo_base", entry.get("pending_id", ""))
        by_code[code] = entry

    # Merge: for each incoming entry, pick the more-resolved version
    merged: list[dict] = []
    seen: set[str] = set()
    for entry in incoming:
        code = entry.get("codigo_base", entry.get("pending_id", ""))
        seen.add(code)
        prev = by_code.get(code)
        if prev is not None:
            prev_resolved = prev.get("cantidad_resuelta", 0)
            curr_resolved = entry.get("cantidad_resuelta", 0)
            merged.append(prev if prev_resolved > curr_resolved else entry)
        else:
            merged.append(entry)

    # Add any entries from existing that weren't in incoming
    for code, entry in by_code.items():
        if code not in seen:
            merged.append(entry)

    return merged


# ---------------------------------------------------------------------------
# post_tool_node factory (importable for unit tests — see make_post_tool_node)
# ---------------------------------------------------------------------------


def make_post_tool_node(
    post_tool_hook: Callable[[str, dict, dict], Awaitable[dict]] | None,
) -> Callable[[dict], Awaitable[dict]]:
    """
    Create a post_tool_node function bound to a specific post_tool_hook.

    This is a factory so each mode can have its own domain logic while
    sharing the same _state_update extraction / merge code.

    Args:
        post_tool_hook: Optional async callback for domain-specific post-tool
                        processing. See ModeLoopConfig.post_tool_hook.

    Returns:
        An async node function ``post_tool_node(state) -> dict``.
    """

    async def post_tool_node(state: dict) -> dict:
        """
        Apply _state_update dicts from ToolMessages to pending_state_updates.

        Reads ToolMessages from the CURRENT TURN (those that follow the last
        AIMessage with tool_calls), extracts their _state_update payloads,
        merges them in call order (last-write-wins on conflicts), and writes
        the merged result to pending_state_updates.

        Also invokes the mode-specific post_tool_hook if provided.
        """
        messages = state.get("messages", [])
        current_pending = dict(state.get("pending_state_updates") or {})

        # ── Find the last AIMessage with tool_calls ───────────────────────
        # Use duck-typing instead of isinstance to avoid class identity issues
        # when langchain_core.messages is reloaded in test environments.
        last_ai_idx = -1
        for i in range(len(messages) - 1, -1, -1):
            msg = messages[i]
            if type(msg).__name__ in ("AIMessage", "AIMessageChunk") and getattr(
                msg, "tool_calls", None
            ):
                last_ai_idx = i
                break

        if last_ai_idx == -1:
            # No AIMessage with tool_calls — nothing to process
            return {"pending_state_updates": current_pending}

        # ── Extract ToolMessages that follow the AIMessage ────────────────
        turn_tool_messages = [
            m for m in messages[last_ai_idx + 1 :] if type(m).__name__ == "ToolMessage"
        ]

        if not turn_tool_messages:
            return {"pending_state_updates": current_pending}

        # ── Extract and merge _state_update from each ToolMessage ─────────
        merged_updates: dict[str, Any] = {}
        for tm in turn_tool_messages:
            content = tm.content
            if isinstance(content, str):
                try:
                    result_dict = json.loads(content)
                except (json.JSONDecodeError, TypeError):
                    result_dict = {}
            elif isinstance(content, dict):
                result_dict = content
            else:
                result_dict = {}

            state_update = result_dict.get("_state_update")
            if not isinstance(state_update, dict):
                continue

            # Check for key conflicts (warn on conflict)
            for key, value in state_update.items():
                if key in merged_updates:
                    if key == "pending_variants":
                        # Parallel seleccionar_variante calls each resolve ONE
                        # element but return the FULL list with stale snapshots
                        # of the others. Merge by taking the most-resolved
                        # status for each entry (matched by codigo_base).
                        value = _merge_pending_variants(
                            merged_updates[key], value
                        )
                    else:
                        logger.warning(
                            "post_tool_node_state_update_conflict",
                            conflicting_key=key,
                            existing_value=merged_updates[key],
                            new_value=value,
                            hint="Last-write-wins — second tool's value applied",
                        )
                merged_updates[key] = value

        # Invoke post_tool_hook if provided
        if post_tool_hook is not None and merged_updates:
            try:
                # Pass the first ToolMessage's tool_name and result_dict for context
                for tm in turn_tool_messages:
                    content = tm.content
                    if isinstance(content, str):
                        try:
                            result_dict = json.loads(content)
                        except (json.JSONDecodeError, TypeError):
                            result_dict = {}
                    elif isinstance(content, dict):
                        result_dict = content
                    else:
                        result_dict = {}

                    # Get tool name from the corresponding AIMessage tool_calls
                    ai_msg = messages[last_ai_idx]
                    tool_name = "unknown"
                    for tc in getattr(ai_msg, "tool_calls", None) or []:
                        if tc.get("id") == getattr(tm, "tool_call_id", None):
                            tool_name = tc.get("name", "unknown")
                            break

                    hook_state = {
                        **state,
                        "pending_state_updates": {**current_pending, **merged_updates},
                    }
                    hook_result = await post_tool_hook(
                        tool_name, result_dict, hook_state
                    )
                    if isinstance(hook_result, dict):
                        merged_updates.update(hook_result)
            except Exception as hook_exc:
                logger.warning(
                    "post_tool_node_hook_error",
                    error=str(hook_exc),
                    mode=state.get("_mode_name", "unknown"),
                )

        # Bubble up shared_context sub-key from _state_update to top-level
        # so the parent graph's merge_dicts reducer persists it correctly.
        if "shared_context" in merged_updates:
            sc_update = merged_updates.pop("shared_context")
            if isinstance(sc_update, dict):
                existing_sc = current_pending.get("shared_context") or {}
                merged_updates["shared_context"] = {**existing_sc, **sc_update}

        # Merge with existing pending_state_updates
        final_updates = {**current_pending, **merged_updates}

        return {"pending_state_updates": final_updates}

    return post_tool_node


# ---------------------------------------------------------------------------
# Main factory
# ---------------------------------------------------------------------------


def build_mode_tool_loop(config: ModeLoopConfig) -> ToolLoopResult:
    """
    Build and compile a ToolLoopState subgraph for a single mode turn.

    The subgraph implements the standard LLM + tool-call loop:

        START → llm_node → tools_or_end → custom_tool_node → post_tool_node → llm_node
                                        ↘ END

    Args:
        config: ModeLoopConfig with mode-specific settings.

    Returns:
        ToolLoopResult with:
        - graph: compiled LangGraph StateGraph
        - recursion_limit: must be passed at ainvoke() time as
          ``config={"recursion_limit": loop_result.recursion_limit}``
    """

    # ── Get or build the LLM ──────────────────────────────────────────────
    def _get_llm(tools: list, tool_choice: str | None = None) -> Any:
        """Return a configured LLM with tools bound."""
        if config._llm_override is not None:
            llm = config._llm_override
        else:
            from shared.config import get_settings
            from langchain_openai import ChatOpenAI

            settings = get_settings()
            llm = ChatOpenAI(
                model=settings.LLM_MODEL,
                openai_api_base="https://openrouter.ai/api/v1",
                openai_api_key=settings.OPENROUTER_API_KEY,
                max_tokens=config.max_tokens,
                temperature=0.1,
            )

        if tools:
            bind_kwargs: dict[str, Any] = {}
            if tool_choice is not None:
                bind_kwargs["tool_choice"] = tool_choice
            return llm.bind_tools(tools, **bind_kwargs)
        return llm

    # ── Node: llm_node ─────────────────────────────────────────────────────
    async def llm_node(state: ToolLoopState) -> dict:
        """
        Invoke the LLM with [SystemMessage] + conversation history.

        Reads _mode_context from state to assemble the system prompt.
        Merges pending mode_context updates from post_tool_hook so that
        tool selection and prompts reflect resolved state (e.g. variants).
        Returns {"messages": [ai_message]} — the add reducer appends it.
        """
        # Merge pending mode_context updates into _mode_context so that
        # tool filtering and system prompt see resolved state changes
        # (variant resolution, tariff calculation, etc.) from prior
        # iterations within this tool loop turn.
        mode_context = dict(state.get("_mode_context") or {})
        pending = state.get("pending_state_updates") or {}
        pending_mc = pending.get("mode_context")
        if isinstance(pending_mc, dict):
            mode_context.update(pending_mc)

        tools = config.get_tools(mode_context)
        tool_choice = (
            config.get_tool_choice(mode_context)
            if config.get_tool_choice is not None
            else None
        )
        llm = _get_llm(tools, tool_choice=tool_choice)

        # Build message list: system prompt + history
        # Pass updated mode_context so system prompt sees resolved state
        prompt_state = dict(state)
        prompt_state["_mode_context"] = mode_context
        system_prompt = config.get_system_prompt(prompt_state)
        messages = [SystemMessage(content=system_prompt)] + list(
            state.get("messages", [])
        )

        logger.debug(
            "llm_node_invoking",
            mode=config.mode_name,
            message_count=len(messages),
            conversation_id=state.get("_conversation_id", "unknown"),
        )

        try:
            response = await llm.ainvoke(messages)
        except Exception as exc:
            logger.error(
                "llm_node_error",
                mode=config.mode_name,
                error=str(exc),
                conversation_id=state.get("_conversation_id", "unknown"),
            )
            # Return error AIMessage so tools_or_end routes to END
            error_response = AIMessage(
                content=(
                    "Lo siento, he tenido un problema técnico. "
                    "Por favor, inténtalo de nuevo en un momento."
                )
            )
            return {
                "messages": [error_response],
                "ai_response": error_response.content,
                "exit_reason": "error",
                "_mode_context": mode_context,
            }

        # Propagate updated _mode_context for subsequent iterations.
        # _mode_context has no reducer (plain overwrite), which is correct:
        # each llm_node call computes the latest merged view.
        base_result: dict[str, Any] = {"_mode_context": mode_context}

        # If no tool calls, this is the final response
        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            return {
                **base_result,
                "messages": [response],
                "ai_response": response.content or "",
                "exit_reason": "response",
            }

        return {**base_result, "messages": [response]}

    # ── Node: custom_tool_node ─────────────────────────────────────────────
    async def custom_tool_node(state: ToolLoopState) -> dict:
        """
        Execute tool calls from the last AIMessage.

        Uses execute_and_log_tool (from tool_executor) for:
        - Parameter validation
        - Dedup guard
        - Timing and structured logging
        - Error capture (returns ToolMessage, does not raise)

        Appends ToolMessages to state["messages"] via add reducer.
        """
        messages = state.get("messages", [])
        mode_context = dict(state.get("_mode_context") or {})
        conversation_id = state.get("_conversation_id", "unknown")

        # Merge pending mode_context updates so tool filtering and
        # tool_state see resolved state (same pattern as llm_node).
        pending = state.get("pending_state_updates") or {}
        pending_mc = pending.get("mode_context")
        if isinstance(pending_mc, dict):
            mode_context.update(pending_mc)

        # Get the last AIMessage with tool_calls
        # Use duck-typing to avoid class identity issues in test environments.
        last_ai = None
        for msg in reversed(messages):
            if type(msg).__name__ in ("AIMessage", "AIMessageChunk") and getattr(
                msg, "tool_calls", None
            ):
                last_ai = msg
                break

        if last_ai is None:
            return {"messages": []}

        tools = config.get_tools(mode_context)
        tool_messages: list[ToolMessage] = []
        dedup_cache: dict[str, str] = {}

        # Build runnable config with state for tool access (AD-2)
        # ToolLoopState is a separate TypedDict that doesn't carry
        # ConversationState fields like client_type. Forward them from
        # mode_context where they were injected by the mode node.
        tool_state = {
            **(dict(state)),
            "mode_context": mode_context,
            "conversation_id": conversation_id,
            "client_type": mode_context.get("_client_type", "particular"),
        }

        # Derive current_mode from _mode_name so expediente/pre_expediente tools
        # can read state.get("current_mode") reliably.
        # IMPORTANT: Check PRE_EXPEDIENTE before EXPEDIENTE — "EXPEDIENTE" is a
        # substring of "PRE_EXPEDIENTE" and would match incorrectly.
        mode_name = state.get("_mode_name", "")
        if "PRE_EXPEDIENTE" in mode_name or "PRESUPUESTO" in mode_name or "CONSULTA" in mode_name:
            tool_state["current_mode"] = "PRE_EXPEDIENTE_MODE"
        elif "EXPEDIENTE" in mode_name:
            tool_state["current_mode"] = "EXPEDIENTE_MODE"

        from agent.modes.tool_executor import execute_and_log_tool

        # Build RunnableConfig so tools can access state via get_tool_state(config)
        tool_config = {"configurable": {"state": tool_state}}

        for i, tool_call in enumerate(last_ai.tool_calls or []):
            tc_name: str = tool_call.get("name", "")
            tc_args: dict = tool_call.get("args", {})
            tc_id: str = tool_call.get("id", f"call_{i}")

            logger.info(
                "custom_tool_node_executing",
                tool=tc_name,
                mode=config.mode_name,
                conversation_id=conversation_id,
            )

            raw_result = await execute_and_log_tool(
                conversation_id=conversation_id,
                tool_name=tc_name,
                tool_args=tc_args,
                tools=tools,
                tool_call_id=tc_id,
                iteration=i + 1,
                dedup_cache=dedup_cache,
                config=tool_config,
            )

            tool_messages.append(
                ToolMessage(
                    tool_call_id=tc_id,
                    content=raw_result,
                )
            )

        return {
            "messages": tool_messages,
            "tools_called": [tc.get("name", "") for tc in (last_ai.tool_calls or [])],
            "tool_results": [_parse_tool_result(tm.content) for tm in tool_messages],
        }

    # ── Node: post_tool_node ───────────────────────────────────────────────
    _post_tool_node = make_post_tool_node(config.post_tool_hook)

    # ── Build subgraph ─────────────────────────────────────────────────────
    builder = StateGraph(ToolLoopState)

    builder.add_node("llm_node", llm_node)
    builder.add_node("custom_tool_node", custom_tool_node)
    builder.add_node("post_tool_node", _post_tool_node)

    builder.add_edge(START, "llm_node")
    builder.add_conditional_edges(
        "llm_node",
        tools_or_end,
        ["custom_tool_node", END],
    )
    builder.add_edge("custom_tool_node", "post_tool_node")
    builder.add_edge("post_tool_node", "llm_node")

    # recursion_limit = max_iterations * 3 (llm + tool + post) + buffer
    recursion_limit = config.max_iterations * 3 + 5

    compiled = builder.compile()

    return ToolLoopResult(graph=compiled, recursion_limit=recursion_limit)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _parse_tool_result(raw: Any) -> dict:
    """
    Coerce a raw tool result string to a dict.

    ``tool_executor.execute_and_log_tool`` serialises results with
    ``json.dumps``; this helper is the inverse, tolerating non-JSON
    inputs by wrapping them in ``{"_raw": ...}``.
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
