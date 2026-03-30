"""
Unit tests for fallback-state-source — Phase 4 (Tasks 4.1–4.6).

Covers:
- 4.1  obtener_estado_expediente() returns data_source="db" when DB returns a valid Case row.
- 4.2  obtener_estado_expediente() returns data_source="fallback" when DB raises an exception.
- 4.3  obtener_estado_expediente() returns data_source="fallback" when case_id is None.
- 4.4  _handle_review() skips LLM loop and returns retry message on first fallback.
- 4.5  _handle_review() calls escalar_a_humano and tombstones counter on second fallback.
- 4.6  _handle_review() tombstones _review_fallback_count when data_source="db" and
       counter was previously set.

All tests are pure unit tests — no Redis, no full LangGraph stack, no live DB.

Usage (runs without Docker stack):
    pytest tests/unit/test_fallback_state_source.py -v
"""

from __future__ import annotations

import sys
import types
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub heavy optional dependencies so tests run without full Docker stack.
# ---------------------------------------------------------------------------

# structlog
if "structlog" not in sys.modules:
    _structlog = types.ModuleType("structlog")
    _structlog.get_logger = lambda *a, **kw: MagicMock()  # type: ignore[attr-defined]
    sys.modules["structlog"] = _structlog

# phonenumbers (used transitively by some imports)
sys.modules.setdefault("phonenumbers", types.ModuleType("phonenumbers"))

# langgraph.checkpoint.redis — not installed locally
for _redis_mod in ("langgraph.checkpoint.redis", "langgraph.checkpoint.redis.aio"):
    if _redis_mod not in sys.modules:
        _redis_stub = types.ModuleType(_redis_mod)
        _redis_stub.AsyncRedisSaver = MagicMock()  # type: ignore[attr-defined]
        sys.modules[_redis_mod] = _redis_stub


# ---------------------------------------------------------------------------
# Imports (after stubs)
# ---------------------------------------------------------------------------

import agent.tools.case_tools as case_tools_module

# Unwrap LangChain @tool so we can call the underlying async function directly.
obtener_estado_expediente_func = case_tools_module.obtener_estado_expediente.coroutine


# ===========================================================================
# Helpers
# ===========================================================================


def _make_case_id() -> str:
    return str(uuid.uuid4())


def _make_minimal_state(case_id: str | None = None) -> dict:
    """Return a minimal ConversationState-like dict."""
    return {
        "conversation_id": "test-conv-fallback-state-source",
        "user_id": str(uuid.uuid4()),
        "fsm_state": {},
        "mode_context": {"case_id": case_id} if case_id else {},
        "current_mode": "EXPEDIENTE_MODE",
    }


def _make_db_case_mock(case_id: str) -> MagicMock:
    """Return a minimal Case ORM mock that satisfies obtener_estado_expediente."""
    mock_case = MagicMock()
    mock_case.id = uuid.UUID(case_id)

    # Images: 0 photos (minimal)
    mock_case.images = []

    # Elements
    mock_case.element_codes = ["ESCAPE"]
    mock_case.element_data = []

    # Workshop
    mock_case.taller_propio = False
    mock_case.taller_nombre = "Taller MSI"

    # Tariff
    mock_case.tariff_amount = 410.0

    # Personal data completeness (via User relationship)
    mock_user = MagicMock()
    mock_user.first_name = "Ana"
    mock_user.last_name = "García"
    mock_user.email = "ana@example.com"
    mock_user.nif_cif = "12345678Z"
    mock_user.domicilio_calle = "Calle Real 42"
    mock_user.domicilio_localidad = "Sevilla"
    mock_user.domicilio_provincia = "Sevilla"
    mock_user.domicilio_cp = "41001"
    mock_case.user = mock_user
    mock_case.itv_nombre = "ITV Sevilla Norte"

    # Vehicle data completeness
    mock_case.vehicle_data = {
        "marca": "Honda",
        "modelo": "CBR600RR",
        "matricula": "1234BCD",
        "anio": "2019",
        "bastidor": "JH2PC37CXKM100001",
    }

    return mock_case


def _build_session_mock_returning(case_obj: MagicMock | None) -> AsyncMock:
    """Return a minimal async DB session mock that yields case_obj from scalar_one_or_none."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = case_obj

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.execute = AsyncMock(return_value=mock_result)
    return mock_session


def _build_session_mock_raising(exc: Exception) -> AsyncMock:
    """Return a DB session mock that raises exc when execute() is called."""
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.execute = AsyncMock(side_effect=exc)
    return mock_session


# ===========================================================================
# 4.1 — data_source: "db" when DB returns valid Case row
# ===========================================================================


class TestDataSourceDbPath:
    """
    Task 4.1: obtener_estado_expediente() must return data_source="db" when
    the DB session returns a non-None Case row.
    """

    @pytest.mark.asyncio
    async def test_db_path_returns_data_source_db(self) -> None:
        """
        Given: case_id is available AND DB session returns a valid Case row
        When:  obtener_estado_expediente() is called
        Then:  result["data_source"] == "db"
        """
        case_id = _make_case_id()
        mock_case = _make_db_case_mock(case_id)
        mock_session = _build_session_mock_returning(mock_case)

        # Stale FSM context (DB path overrides these)
        stale_context = MagicMock()
        stale_context.get = MagicMock(return_value=None)

        with (
            patch(
                "agent.tools.case_tools.get_current_state",
                return_value=_make_minimal_state(case_id),
            ),
            patch(
                "agent.tools.case_tools._is_collection_active",
                return_value=True,
            ),
            patch(
                "agent.tools.case_tools._get_mode_context",
                return_value=stale_context,
            ),
            patch(
                "agent.tools.case_tools._get_case_id_with_fallback",
                return_value=case_id,
            ),
            patch(
                "agent.tools.case_tools.get_async_session",
                return_value=mock_session,
            ),
        ):
            result = await obtener_estado_expediente_func()

        assert result.get("data_source") == "db", (
            f"Expected data_source='db' when DB returns a valid Case. Got: {result.get('data_source')!r}"
        )
        assert result.get("success") is True
        assert result.get("has_active_case") is True

    @pytest.mark.asyncio
    async def test_db_path_data_source_type_is_string(self) -> None:
        """data_source must be a plain string, not a truthy/falsy alias."""
        case_id = _make_case_id()
        mock_case = _make_db_case_mock(case_id)
        mock_session = _build_session_mock_returning(mock_case)

        stale_context = MagicMock()
        stale_context.get = MagicMock(return_value=None)

        with (
            patch(
                "agent.tools.case_tools.get_current_state",
                return_value=_make_minimal_state(case_id),
            ),
            patch("agent.tools.case_tools._is_collection_active", return_value=True),
            patch(
                "agent.tools.case_tools._get_mode_context", return_value=stale_context
            ),
            patch(
                "agent.tools.case_tools._get_case_id_with_fallback",
                return_value=case_id,
            ),
            patch(
                "agent.tools.case_tools.get_async_session", return_value=mock_session
            ),
        ):
            result = await obtener_estado_expediente_func()

        assert isinstance(result.get("data_source"), str)


# ===========================================================================
# 4.2 — data_source: "fallback" when DB raises exception
# ===========================================================================


class TestDataSourceDbException:
    """
    Task 4.2: obtener_estado_expediente() must return data_source="fallback" when
    the DB session raises an exception during execute().
    """

    @pytest.mark.asyncio
    async def test_db_exception_returns_data_source_fallback(self) -> None:
        """
        Given: case_id is available BUT DB session raises an exception
        When:  obtener_estado_expediente() is called
        Then:  result["data_source"] == "fallback"
               The tool does NOT propagate the exception
        """
        case_id = _make_case_id()
        mock_session = _build_session_mock_raising(
            ConnectionError("DB connection refused")
        )

        stale_context = MagicMock()
        stale_context.get = MagicMock(
            side_effect=lambda key, *args: args[0] if args else None
        )

        with (
            patch(
                "agent.tools.case_tools.get_current_state",
                return_value=_make_minimal_state(case_id),
            ),
            patch(
                "agent.tools.case_tools._is_collection_active",
                return_value=True,
            ),
            patch(
                "agent.tools.case_tools._get_mode_context",
                return_value=stale_context,
            ),
            patch(
                "agent.tools.case_tools._get_case_id_with_fallback",
                return_value=case_id,
            ),
            patch(
                "agent.tools.case_tools.get_async_session",
                return_value=mock_session,
            ),
        ):
            result = await obtener_estado_expediente_func()

        assert result.get("data_source") == "fallback", (
            f"Expected data_source='fallback' when DB raises. Got: {result.get('data_source')!r}"
        )
        assert result.get("success") is True, (
            "Tool must still return success=True even on DB failure (falls back gracefully)"
        )

    @pytest.mark.asyncio
    async def test_db_exception_tool_does_not_propagate(self) -> None:
        """Verifies the tool catches the DB exception and returns a dict (no raise)."""
        case_id = _make_case_id()
        mock_session = _build_session_mock_raising(RuntimeError("unexpected DB error"))

        stale_context = MagicMock()
        stale_context.get = MagicMock(
            side_effect=lambda key, *args: args[0] if args else None
        )

        try:
            with (
                patch(
                    "agent.tools.case_tools.get_current_state",
                    return_value=_make_minimal_state(case_id),
                ),
                patch(
                    "agent.tools.case_tools._is_collection_active", return_value=True
                ),
                patch(
                    "agent.tools.case_tools._get_mode_context",
                    return_value=stale_context,
                ),
                patch(
                    "agent.tools.case_tools._get_case_id_with_fallback",
                    return_value=case_id,
                ),
                patch(
                    "agent.tools.case_tools.get_async_session",
                    return_value=mock_session,
                ),
            ):
                result = await obtener_estado_expediente_func()
        except Exception as exc:
            pytest.fail(
                f"obtener_estado_expediente must not propagate DB exception. Got: {type(exc).__name__}: {exc}"
            )

        assert isinstance(result, dict), "Must return a dict even on DB failure"


# ===========================================================================
# 4.3 — data_source: "fallback" when case_id is None
# ===========================================================================


class TestDataSourceNoCaseId:
    """
    Task 4.3: obtener_estado_expediente() must return data_source="fallback" when
    case_id is None (DB path is skipped entirely — no case_id to query by).
    """

    @pytest.mark.asyncio
    async def test_no_case_id_returns_data_source_fallback(self) -> None:
        """
        Given: case_id is None in state (not yet persisted, or early tool call)
        When:  obtener_estado_expediente() is called
        Then:  result["data_source"] == "fallback"
               DB session is never called (no case_id to query)
        """
        stale_context = MagicMock()
        stale_context.get = MagicMock(
            side_effect=lambda key, *args: args[0] if args else None
        )

        with (
            patch(
                "agent.tools.case_tools.get_current_state",
                return_value=_make_minimal_state(case_id=None),
            ),
            patch(
                "agent.tools.case_tools._is_collection_active",
                return_value=True,
            ),
            patch(
                "agent.tools.case_tools._get_mode_context",
                return_value=stale_context,
            ),
            patch(
                "agent.tools.case_tools._get_case_id_with_fallback",
                return_value=None,  # No case_id
            ),
        ):
            result = await obtener_estado_expediente_func()

        assert result.get("data_source") == "fallback", (
            f"Expected data_source='fallback' when case_id is None. Got: {result.get('data_source')!r}"
        )

    @pytest.mark.asyncio
    async def test_no_case_id_does_not_call_db(self) -> None:
        """DB session must NOT be called when case_id is None."""
        stale_context = MagicMock()
        stale_context.get = MagicMock(
            side_effect=lambda key, *args: args[0] if args else None
        )

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(
                "agent.tools.case_tools.get_current_state",
                return_value=_make_minimal_state(case_id=None),
            ),
            patch("agent.tools.case_tools._is_collection_active", return_value=True),
            patch(
                "agent.tools.case_tools._get_mode_context", return_value=stale_context
            ),
            patch(
                "agent.tools.case_tools._get_case_id_with_fallback", return_value=None
            ),
            patch(
                "agent.tools.case_tools.get_async_session", return_value=mock_session
            ) as mock_get_session,
        ):
            await obtener_estado_expediente_func()

        # get_async_session should not have been entered when case_id is None
        mock_session.execute.assert_not_called()


# ===========================================================================
# 4.4 — _handle_review() blocks on fallback, returns retry message (count=0)
# ===========================================================================


class TestHandleReviewFirstFallback:
    """
    Task 4.4: _handle_review() must skip the LLM loop and return the retry message
    when data_source == "fallback" and _review_fallback_count is 0 (first failure).
    """

    @pytest.mark.asyncio
    async def test_first_fallback_returns_retry_message(self) -> None:
        """
        Given: obtener_estado_expediente() returns data_source="fallback"
               _review_fallback_count is absent (defaults to 0)
        When:  _handle_review() is called
        Then:  LLM loop is NOT entered
               ai_response contains retry wording
               mode_context["_review_fallback_count"] == 1
        """
        from agent.modes.expediente_mode import ExpedienteModeNode

        node = ExpedienteModeNode()

        state: dict = {
            "conversation_id": "test-review-first-fallback",
            "user_id": str(uuid.uuid4()),
            "current_mode": "EXPEDIENTE_MODE",
            "messages": [],
            "fsm_state": {},
            "mode_context": {
                "expediente_sub_mode": "review_summary",
                # _review_fallback_count intentionally absent
            },
        }
        mode_context: dict = dict(state["mode_context"])
        message = "Quiero confirmar el expediente"

        # obtener_estado_expediente returns fallback data
        fallback_result = {
            "success": True,
            "has_active_case": True,
            "data_source": "fallback",
            "precio_total": None,
        }

        run_llm_loop_mock = AsyncMock()

        with (
            patch(
                "agent.modes.expediente_mode.set_current_state",
            ),
            patch(
                "agent.modes.expediente_mode.set_current_state_for_image_tools",
            ),
            patch(
                "agent.tools.case_tools.obtener_estado_expediente.ainvoke",
                new_callable=AsyncMock,
                return_value=fallback_result,
            ),
            patch.object(
                node,
                "_run_llm_loop",
                run_llm_loop_mock,
            ),
        ):
            result = await node._handle_review(
                message=message,
                state=state,  # type: ignore[arg-type]
                mode_context=mode_context,
            )

        # LLM loop must NOT have been called
        run_llm_loop_mock.assert_not_called()

        # ai_response must be the retry message
        ai_response = result.get("ai_response", "")
        assert (
            "verificando" in ai_response.lower() or "expediente" in ai_response.lower()
        ), f"Retry message expected in ai_response. Got: {ai_response!r}"

        # Counter must have been incremented to 1
        returned_context = result.get("mode_context", {})
        assert returned_context.get("_review_fallback_count") == 1, (
            f"_review_fallback_count must be 1 after first fallback. Got: {returned_context.get('_review_fallback_count')!r}"
        )

        # review_blocked_reason must be set to "stale_data"
        assert returned_context.get("review_blocked_reason") == "stale_data", (
            f"review_blocked_reason must be 'stale_data' on fallback block. Got: {returned_context.get('review_blocked_reason')!r}"
        )

    @pytest.mark.asyncio
    async def test_first_fallback_does_not_escalate(self) -> None:
        """On the first fallback (count goes from 0→1), escalation must NOT be triggered."""
        from agent.modes.expediente_mode import ExpedienteModeNode

        node = ExpedienteModeNode()

        state: dict = {
            "conversation_id": "test-review-no-escalate",
            "user_id": str(uuid.uuid4()),
            "current_mode": "EXPEDIENTE_MODE",
            "messages": [],
            "fsm_state": {},
            "mode_context": {"expediente_sub_mode": "review_summary"},
        }
        mode_context = dict(state["mode_context"])

        fallback_result = {
            "success": True,
            "has_active_case": True,
            "data_source": "fallback",
        }
        escalar_mock = AsyncMock()

        with (
            patch("agent.modes.expediente_mode.set_current_state"),
            patch("agent.modes.expediente_mode.set_current_state_for_image_tools"),
            patch(
                "agent.tools.case_tools.obtener_estado_expediente.ainvoke",
                new_callable=AsyncMock,
                return_value=fallback_result,
            ),
            patch(
                "agent.modes.expediente_mode.ExpedienteModeNode._run_llm_loop",
                new_callable=AsyncMock,
            ),
            patch(
                "agent.tools.shared_tools.escalar_a_humano.ainvoke",
                escalar_mock,
            ),
        ):
            await node._handle_review(
                message="confirmar",
                state=state,  # type: ignore[arg-type]
                mode_context=mode_context,
            )

        escalar_mock.assert_not_called()


# ===========================================================================
# 4.5 — _handle_review() escalates on second fallback (count was 1)
# ===========================================================================


class TestHandleReviewSecondFallback:
    """
    Task 4.5: _handle_review() must call escalar_a_humano and tombstone the counter
    when _review_fallback_count == 1 (i.e., this is the second consecutive fallback,
    pushing count to 2 which satisfies count >= 2).
    """

    @pytest.mark.asyncio
    async def test_second_fallback_calls_escalar_a_humano(self) -> None:
        """
        Given: data_source="fallback" AND _review_fallback_count == 1
        When:  _handle_review() is called
        Then:  escalar_a_humano is called with es_error_tecnico=True
               LLM loop is NOT entered
               _review_fallback_count is tombstoned to None
        """
        from agent.modes.expediente_mode import ExpedienteModeNode

        node = ExpedienteModeNode()

        state: dict = {
            "conversation_id": "test-review-second-fallback",
            "user_id": str(uuid.uuid4()),
            "current_mode": "EXPEDIENTE_MODE",
            "messages": [],
            "fsm_state": {},
            "mode_context": {
                "expediente_sub_mode": "review_summary",
                "_review_fallback_count": 1,  # Second failure incoming
            },
        }
        mode_context = dict(state["mode_context"])

        fallback_result = {
            "success": True,
            "has_active_case": True,
            "data_source": "fallback",
        }
        escalar_mock = AsyncMock(return_value={"success": True})
        run_llm_loop_mock = AsyncMock()

        with (
            patch("agent.modes.expediente_mode.set_current_state"),
            patch("agent.modes.expediente_mode.set_current_state_for_image_tools"),
            patch(
                "agent.tools.case_tools.obtener_estado_expediente.ainvoke",
                new_callable=AsyncMock,
                return_value=fallback_result,
            ),
            patch.object(node, "_run_llm_loop", run_llm_loop_mock),
            patch(
                "agent.tools.shared_tools.escalar_a_humano.ainvoke",
                escalar_mock,
            ),
        ):
            result = await node._handle_review(
                message="confirmar",
                state=state,  # type: ignore[arg-type]
                mode_context=mode_context,
            )

        # escalar_a_humano must have been called
        escalar_mock.assert_called_once()
        call_kwargs = escalar_mock.call_args[0][
            0
        ]  # First positional arg is the input dict
        assert call_kwargs.get("es_error_tecnico") is True, (
            f"escalar_a_humano must be called with es_error_tecnico=True. Got: {call_kwargs}"
        )

        # LLM loop must NOT have been called
        run_llm_loop_mock.assert_not_called()

        # Counter must be tombstoned to None
        returned_context = result.get("mode_context", {})
        assert returned_context.get("_review_fallback_count") is None, (
            f"_review_fallback_count must be tombstoned to None after escalation. "
            f"Got: {returned_context.get('_review_fallback_count')!r}"
        )

        # review_blocked_reason must be set to "stale_data" even on escalation
        assert returned_context.get("review_blocked_reason") == "stale_data", (
            f"review_blocked_reason must be 'stale_data' on escalation fallback. Got: {returned_context.get('review_blocked_reason')!r}"
        )

    @pytest.mark.asyncio
    async def test_second_fallback_ai_response_mentions_agent(self) -> None:
        """Escalation response must mention that a human agent will assist."""
        from agent.modes.expediente_mode import ExpedienteModeNode

        node = ExpedienteModeNode()

        state: dict = {
            "conversation_id": "test-review-second-fallback-msg",
            "user_id": str(uuid.uuid4()),
            "current_mode": "EXPEDIENTE_MODE",
            "messages": [],
            "fsm_state": {},
            "mode_context": {
                "expediente_sub_mode": "review_summary",
                "_review_fallback_count": 1,
            },
        }
        mode_context = dict(state["mode_context"])

        fallback_result = {
            "success": True,
            "has_active_case": True,
            "data_source": "fallback",
        }

        with (
            patch("agent.modes.expediente_mode.set_current_state"),
            patch("agent.modes.expediente_mode.set_current_state_for_image_tools"),
            patch(
                "agent.tools.case_tools.obtener_estado_expediente.ainvoke",
                new_callable=AsyncMock,
                return_value=fallback_result,
            ),
            patch(
                "agent.modes.expediente_mode.ExpedienteModeNode._run_llm_loop",
                new_callable=AsyncMock,
            ),
            patch(
                "agent.tools.shared_tools.escalar_a_humano.ainvoke",
                AsyncMock(return_value={"success": True}),
            ),
        ):
            result = await node._handle_review(
                message="confirmar",
                state=state,  # type: ignore[arg-type]
                mode_context=mode_context,
            )

        ai_response = result.get("ai_response", "")
        # Should mention agent or MSI (escalation message)
        assert (
            "agente" in ai_response.lower()
            or "msi" in ai_response.lower()
            or "pasarte" in ai_response.lower()
        ), f"Escalation ai_response should mention human agent. Got: {ai_response!r}"

    @pytest.mark.asyncio
    async def test_second_fallback_warning_log_emitted(self) -> None:
        """review_fallback_escalated warning must be logged on second fallback."""
        from agent.modes.expediente_mode import ExpedienteModeNode

        node = ExpedienteModeNode()
        # Replace node's logger with a spy
        mock_logger = MagicMock()
        node._logger = mock_logger

        state: dict = {
            "conversation_id": "test-review-log",
            "user_id": str(uuid.uuid4()),
            "current_mode": "EXPEDIENTE_MODE",
            "messages": [],
            "fsm_state": {},
            "mode_context": {
                "expediente_sub_mode": "review_summary",
                "_review_fallback_count": 1,
            },
        }
        mode_context = dict(state["mode_context"])

        fallback_result = {
            "success": True,
            "has_active_case": True,
            "data_source": "fallback",
        }

        with (
            patch("agent.modes.expediente_mode.set_current_state"),
            patch("agent.modes.expediente_mode.set_current_state_for_image_tools"),
            patch(
                "agent.tools.case_tools.obtener_estado_expediente.ainvoke",
                new_callable=AsyncMock,
                return_value=fallback_result,
            ),
            patch(
                "agent.modes.expediente_mode.ExpedienteModeNode._run_llm_loop",
                new_callable=AsyncMock,
            ),
            patch(
                "agent.tools.shared_tools.escalar_a_humano.ainvoke",
                AsyncMock(return_value={"success": True}),
            ),
        ):
            await node._handle_review(
                message="confirmar",
                state=state,  # type: ignore[arg-type]
                mode_context=mode_context,
            )

        # Verify that warning("review_fallback_escalated", ...) was called
        warning_calls = [call for call in mock_logger.warning.call_args_list]
        escalated_calls = [
            c for c in warning_calls if c[0][0] == "review_fallback_escalated"
        ]
        assert escalated_calls, (
            "review_fallback_escalated warning must be logged on second fallback. "
            f"All warning calls: {[c[0][0] for c in warning_calls]}"
        )


# ===========================================================================
# 4.6 — _handle_review() tombstones counter when data_source="db" and count set
# ===========================================================================


class TestHandleReviewDbSuccessTombstone:
    """
    Task 4.6: When data_source="db" and _review_fallback_count was previously set,
    _handle_review() must tombstone _review_fallback_count to None before entering
    the LLM loop.
    """

    @pytest.mark.asyncio
    async def test_db_success_tombstones_review_fallback_count(self) -> None:
        """
        Given: data_source="db" AND _review_fallback_count=1 (prior failure)
        When:  _handle_review() is called
        Then:  _run_llm_loop IS called (normal path)
               mode_context["_review_fallback_count"] is None (tombstoned)
        """
        import json

        from agent.modes.expediente_mode import ExpedienteModeNode

        node = ExpedienteModeNode()

        state: dict = {
            "conversation_id": "test-review-db-tombstone",
            "user_id": str(uuid.uuid4()),
            "current_mode": "EXPEDIENTE_MODE",
            "messages": [],
            "fsm_state": {},
            "mode_context": {
                "expediente_sub_mode": "review_summary",
                "_review_fallback_count": 1,  # Was set from prior fallback
            },
        }
        mode_context = dict(state["mode_context"])

        # DB path: data_source="db"
        db_result = {
            "success": True,
            "has_active_case": True,
            "data_source": "db",
            "precio_total": 495.0,
        }

        # _run_llm_loop returns a typical result; we just need to inspect what
        # mode_context was passed to it.
        captured_mode_context: dict = {}

        async def _capture_llm_loop(**kwargs: object) -> dict:
            captured_mode_context.update(kwargs.get("mode_context", {}))  # type: ignore[arg-type]
            return {
                "ai_response": "Aquí tienes el resumen de tu expediente.",
                "mode_context": {},
            }

        with (
            patch("agent.modes.expediente_mode.set_current_state"),
            patch("agent.modes.expediente_mode.set_current_state_for_image_tools"),
            patch(
                "agent.tools.case_tools.obtener_estado_expediente.ainvoke",
                new_callable=AsyncMock,
                return_value=db_result,
            ),
            patch.object(node, "_run_llm_loop", side_effect=_capture_llm_loop),
        ):
            await node._handle_review(
                message="quiero confirmar",
                state=state,  # type: ignore[arg-type]
                mode_context=mode_context,
            )

        # _run_llm_loop must have been called (normal path)
        assert captured_mode_context is not None, "_run_llm_loop was not called"

        # The mode_context passed to _run_llm_loop must have _review_fallback_count=None
        assert "_review_fallback_count" in captured_mode_context, (
            "_review_fallback_count key must be in mode_context (tombstoned as None, not popped)"
        )
        assert captured_mode_context["_review_fallback_count"] is None, (
            f"_review_fallback_count must be tombstoned to None on DB success. "
            f"Got: {captured_mode_context['_review_fallback_count']!r}"
        )

    @pytest.mark.asyncio
    async def test_db_success_no_prior_counter_does_not_add_key(self) -> None:
        """
        When data_source="db" and _review_fallback_count was never set,
        _handle_review() must NOT add _review_fallback_count to mode_context.
        (The tombstone logic only fires when the key was previously set.)
        """
        import json

        from agent.modes.expediente_mode import ExpedienteModeNode

        node = ExpedienteModeNode()

        state: dict = {
            "conversation_id": "test-review-db-no-counter",
            "user_id": str(uuid.uuid4()),
            "current_mode": "EXPEDIENTE_MODE",
            "messages": [],
            "fsm_state": {},
            "mode_context": {
                "expediente_sub_mode": "review_summary",
                # _review_fallback_count intentionally absent
            },
        }
        mode_context = dict(state["mode_context"])

        db_result = {
            "success": True,
            "has_active_case": True,
            "data_source": "db",
            "precio_total": 495.0,
        }

        captured_mode_context: dict = {}

        async def _capture_llm_loop(**kwargs: object) -> dict:
            captured_mode_context.update(kwargs.get("mode_context", {}))  # type: ignore[arg-type]
            return {"ai_response": "Resumen del expediente.", "mode_context": {}}

        with (
            patch("agent.modes.expediente_mode.set_current_state"),
            patch("agent.modes.expediente_mode.set_current_state_for_image_tools"),
            patch(
                "agent.tools.case_tools.obtener_estado_expediente.ainvoke",
                new_callable=AsyncMock,
                return_value=db_result,
            ),
            patch.object(node, "_run_llm_loop", side_effect=_capture_llm_loop),
        ):
            await node._handle_review(
                message="confirmar",
                state=state,  # type: ignore[arg-type]
                mode_context=mode_context,
            )

        # _review_fallback_count should NOT be present when it was never set
        assert "_review_fallback_count" not in captured_mode_context, (
            "_review_fallback_count must NOT be injected into mode_context when it was never set. "
            f"Got mode_context keys: {list(captured_mode_context.keys())}"
        )

    @pytest.mark.asyncio
    async def test_db_success_runs_llm_loop(self) -> None:
        """On DB success, _run_llm_loop must always be called (normal path)."""
        import json

        from agent.modes.expediente_mode import ExpedienteModeNode

        node = ExpedienteModeNode()

        state: dict = {
            "conversation_id": "test-review-runs-loop",
            "user_id": str(uuid.uuid4()),
            "current_mode": "EXPEDIENTE_MODE",
            "messages": [],
            "fsm_state": {},
            "mode_context": {"expediente_sub_mode": "review_summary"},
        }
        mode_context = dict(state["mode_context"])

        db_result = {"success": True, "has_active_case": True, "data_source": "db"}
        run_llm_loop_mock = AsyncMock(
            return_value={"ai_response": "OK", "mode_context": {}}
        )

        with (
            patch("agent.modes.expediente_mode.set_current_state"),
            patch("agent.modes.expediente_mode.set_current_state_for_image_tools"),
            patch(
                "agent.tools.case_tools.obtener_estado_expediente.ainvoke",
                new_callable=AsyncMock,
                return_value=db_result,
            ),
            patch.object(node, "_run_llm_loop", run_llm_loop_mock),
        ):
            await node._handle_review(
                message="confirmar",
                state=state,  # type: ignore[arg-type]
                mode_context=mode_context,
            )

        run_llm_loop_mock.assert_called_once()


# ===========================================================================
# Backwards-compatibility contract
# ===========================================================================


class TestBackwardsCompatibility:
    """
    Ensure that callers treating an absent data_source as "db" are unaffected.
    Spec: Callers MUST treat an absent data_source as "db" (backwards-compatible .get() access).
    """

    def test_absent_data_source_treated_as_db_via_get(self) -> None:
        """
        Simulates the canonical caller pattern:
            result.get("data_source") == "fallback"
        When data_source is absent, .get() returns None → not equal to "fallback" → proceeds normally.
        """
        result_without_field: dict = {
            "success": True,
            "has_active_case": True,
            "precio_total": 495.0,
            # No "data_source" key
        }

        # The guard in _handle_review() uses:
        #   if pre_call_result.get("data_source") == "fallback":
        # When key is absent, .get() returns None → condition is False → normal path
        is_fallback = result_without_field.get("data_source") == "fallback"
        assert is_fallback is False, (
            "Absent data_source must NOT trigger the fallback guard. "
            "Callers using .get() treat absence as 'db' (backwards-compatible)."
        )
