"""
Tests for the per-turn tool-call dedup guard in base_mode.py.

The guard prevents the same (tool_name, args) pair from executing more than once
within a single _process_message() / _run_llm_loop() turn.

Scenarios covered:
  1. Same tool + same args → second call returns cached result, tool executes only once
  2. Same tool + different args → both execute (no false dedup)
  3. Excluded tool + same args → both execute (TOOL_DEDUP_EXCLUDED bypass)
  4. dedup_cache parameter controls guard activation (None = inactive, {} = active)
  5. No class-level _tool_dedup_cache attribute exists on BaseModeNode
"""

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agent.modes.base_mode import BaseModeNode, TOOL_DEDUP_EXCLUDED


# ==============================================================================
# Test helpers
# ==============================================================================


class DedupTestModeNode(BaseModeNode):
    """Minimal concrete BaseModeNode for dedup guard testing."""

    def __init__(self) -> None:
        super().__init__("DEDUP_TEST_MODE")

    async def _process_message(self, message: str, state: dict) -> dict:  # type: ignore[override]
        return {"ai_response": "test"}

    def get_tools(self) -> list:
        return []


def _make_tool(name: str, return_value: dict) -> MagicMock:
    """Create a minimal mock LangChain tool."""
    tool = MagicMock()
    tool.name = name
    tool.args_schema = None  # Skip Pydantic validation layer
    tool.ainvoke = AsyncMock(return_value=return_value)
    return tool


def _make_state(conversation_id: str = "test-conv-001") -> dict:
    return {"conversation_id": conversation_id, "mode_context": {}}


# ==============================================================================
# 0. No class-level attribute — guard is parameter-based
# ==============================================================================


class TestNoClassLevelDedupAttribute:
    """_tool_dedup_cache must NOT exist as a class attribute on BaseModeNode."""

    def test_no_class_level_dedup_attribute(self) -> None:
        """BaseModeNode must not have _tool_dedup_cache as a class attribute."""
        assert "_tool_dedup_cache" not in BaseModeNode.__dict__, (
            "_tool_dedup_cache must be removed from the class body — "
            "it caused a race condition when singleton nodes served concurrent conversations"
        )
        assert "_tool_dedup_cache" not in getattr(BaseModeNode, "__annotations__", {}), (
            "_tool_dedup_cache must not appear in class annotations either"
        )


# ==============================================================================
# 1. Same tool + same args → cached on second call, only one execution
# ==============================================================================


class TestDedupHit:
    """Second call with identical args returns cached result without re-executing."""

    @pytest.mark.asyncio
    async def test_second_identical_call_returns_cached_result(self) -> None:
        mode = DedupTestModeNode()
        tool_result = {"success": True, "precio": 410}
        mock_tool = _make_tool("calcular_tarifa_con_elementos", tool_result)
        tools = [mock_tool]
        args = {
            "elementos": ["ESCAPE"],
            "categoria": "motos-part",
            "skip_validation": True,
        }

        # Pass dedup_cache as parameter (as generic_llm_loop would)
        dedup_cache: dict[str, str] = {}

        with patch("agent.state.helpers.get_current_state", return_value=_make_state()):
            result1 = await mode._execute_and_log_tool(
                conversation_id="test-conv-001",
                tool_name="calcular_tarifa_con_elementos",
                tool_args=args,
                tools=tools,
                iteration=1,
                dedup_cache=dedup_cache,
            )
            result2 = await mode._execute_and_log_tool(
                conversation_id="test-conv-001",
                tool_name="calcular_tarifa_con_elementos",
                tool_args=args,
                tools=tools,
                iteration=2,
                dedup_cache=dedup_cache,
            )

        # Tool executed only once
        assert mock_tool.ainvoke.call_count == 1

        # Both results are identical (second is the cached string)
        assert result1 == result2

        # Result contains the expected data
        result_dict = json.loads(result1)
        assert result_dict["success"] is True
        assert result_dict["precio"] == 410

    @pytest.mark.asyncio
    async def test_dedup_hit_is_logged(self) -> None:
        mode = DedupTestModeNode()
        mock_tool = _make_tool("calcular_tarifa_con_elementos", {"success": True})
        tools = [mock_tool]
        args = {"categoria": "motos-part"}

        dedup_cache: dict[str, str] = {}

        with patch("agent.state.helpers.get_current_state", return_value=_make_state()):
            with patch.object(mode, "_logger") as mock_logger:
                await mode._execute_and_log_tool(
                    conversation_id="test-conv-001",
                    tool_name="calcular_tarifa_con_elementos",
                    tool_args=args,
                    tools=tools,
                    iteration=1,
                    dedup_cache=dedup_cache,
                )
                await mode._execute_and_log_tool(
                    conversation_id="test-conv-001",
                    tool_name="calcular_tarifa_con_elementos",
                    tool_args=args,
                    tools=tools,
                    iteration=2,
                    dedup_cache=dedup_cache,
                )

        # "tool_call_dedup_hit" should have been logged once (for the second call)
        info_calls = [str(call) for call in mock_logger.info.call_args_list]
        assert any("tool_call_dedup_hit" in c for c in info_calls)


# ==============================================================================
# 2. Same tool + different args → both execute
# ==============================================================================


class TestDedupMiss:
    """Different args must NOT be deduplicated — both calls execute."""

    @pytest.mark.asyncio
    async def test_different_args_both_execute(self) -> None:
        mode = DedupTestModeNode()
        mock_tool = _make_tool("actualizar_datos_expediente", {"success": True})
        tools = [mock_tool]
        args1 = {"datos_personales": {"nombre": "María"}}
        args2 = {"datos_personales": {"nombre": "María", "email": "m@x.com"}}

        dedup_cache: dict[str, str] = {}

        with patch("agent.state.helpers.get_current_state", return_value=_make_state()):
            await mode._execute_and_log_tool(
                conversation_id="test-conv-001",
                tool_name="actualizar_datos_expediente",
                tool_args=args1,
                tools=tools,
                iteration=1,
                dedup_cache=dedup_cache,
            )
            await mode._execute_and_log_tool(
                conversation_id="test-conv-001",
                tool_name="actualizar_datos_expediente",
                tool_args=args2,
                tools=tools,
                iteration=2,
                dedup_cache=dedup_cache,
            )

        # Both executions should have happened
        assert mock_tool.ainvoke.call_count == 2

    @pytest.mark.asyncio
    async def test_guard_inactive_when_cache_is_none(self) -> None:
        """When dedup_cache=None, the guard is inactive — tools always execute."""
        mode = DedupTestModeNode()
        mock_tool = _make_tool("calcular_tarifa_con_elementos", {"success": True})
        tools = [mock_tool]
        args = {"categoria": "motos-part"}

        with patch("agent.state.helpers.get_current_state", return_value=_make_state()):
            await mode._execute_and_log_tool(
                conversation_id="test-conv-001",
                tool_name="calcular_tarifa_con_elementos",
                tool_args=args,
                tools=tools,
                iteration=1,
                dedup_cache=None,  # Guard inactive
            )
            await mode._execute_and_log_tool(
                conversation_id="test-conv-001",
                tool_name="calcular_tarifa_con_elementos",
                tool_args=args,
                tools=tools,
                iteration=2,
                dedup_cache=None,  # Guard inactive
            )

        # Both calls go through because guard was inactive
        assert mock_tool.ainvoke.call_count == 2


# ==============================================================================
# 3. Excluded tools bypass the guard entirely
# ==============================================================================


class TestDedupExcluded:
    """Tools in TOOL_DEDUP_EXCLUDED always execute, even with identical args."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("excluded_tool", sorted(TOOL_DEDUP_EXCLUDED))
    async def test_excluded_tool_always_executes(self, excluded_tool: str) -> None:
        mode = DedupTestModeNode()
        mock_tool = _make_tool(excluded_tool, {"success": True})
        tools = [mock_tool]
        args = {"motivo": "cliente insiste"}

        dedup_cache: dict[str, str] = {}

        with patch("agent.state.helpers.get_current_state", return_value=_make_state()):
            await mode._execute_and_log_tool(
                conversation_id="test-conv-001",
                tool_name=excluded_tool,
                tool_args=args,
                tools=tools,
                iteration=1,
                dedup_cache=dedup_cache,
            )
            await mode._execute_and_log_tool(
                conversation_id="test-conv-001",
                tool_name=excluded_tool,
                tool_args=args,
                tools=tools,
                iteration=2,
                dedup_cache=dedup_cache,
            )

        # Both calls must have executed (excluded from dedup)
        assert mock_tool.ainvoke.call_count == 2, (
            f"Excluded tool '{excluded_tool}' was incorrectly deduplicated"
        )

    def test_excluded_set_contains_expected_tools(self) -> None:
        """Verify the exclusion set has the four documented tools."""
        expected = {
            "escalar_a_humano",
            "enviar_imagenes_ejemplo",
            "iniciar_expediente",
            "finalizar_expediente",
        }
        assert TOOL_DEDUP_EXCLUDED == expected


# ==============================================================================
# 4. Dedup cache is parameter-based, not instance state
# ==============================================================================


class TestDedupParameterBased:
    """dedup_cache is passed as a parameter, not stored on the instance."""

    def test_new_instance_has_no_dedup_cache_attribute(self) -> None:
        mode = DedupTestModeNode()
        assert not hasattr(mode, "_tool_dedup_cache"), (
            "Instances must not have _tool_dedup_cache — it was removed to fix a "
            "race condition in concurrent conversations sharing singleton mode nodes"
        )

    @pytest.mark.asyncio
    async def test_independent_caches_do_not_interfere(self) -> None:
        """Two separate dedup caches (simulating two conversations) don't interfere."""
        mode = DedupTestModeNode()
        mock_tool = _make_tool("calcular_tarifa_con_elementos", {"success": True})
        tools = [mock_tool]
        args = {"categoria": "motos-part"}

        cache_conv_a: dict[str, str] = {}
        cache_conv_b: dict[str, str] = {}

        with patch("agent.state.helpers.get_current_state", return_value=_make_state()):
            # Conversation A: first call populates cache_conv_a
            await mode._execute_and_log_tool(
                conversation_id="conv-a",
                tool_name="calcular_tarifa_con_elementos",
                tool_args=args,
                tools=tools,
                iteration=1,
                dedup_cache=cache_conv_a,
            )
            # Conversation B: uses separate cache — tool must execute again
            await mode._execute_and_log_tool(
                conversation_id="conv-b",
                tool_name="calcular_tarifa_con_elementos",
                tool_args=args,
                tools=tools,
                iteration=1,
                dedup_cache=cache_conv_b,
            )

        # Both conversations got their own execution — no cross-conversation dedup
        assert mock_tool.ainvoke.call_count == 2

    @pytest.mark.asyncio
    async def test_presupuesto_mode_has_no_dedup_cache_attribute(self) -> None:
        """PresupuestoModeNode instances must not have _tool_dedup_cache."""
        from agent.modes.presupuesto_mode import PresupuestoModeNode

        mode = PresupuestoModeNode()
        assert not hasattr(mode, "_tool_dedup_cache")

    @pytest.mark.asyncio
    async def test_consulta_mode_has_no_dedup_cache_attribute(self) -> None:
        """ConsultaModeNode instances must not have _tool_dedup_cache."""
        from agent.modes.consulta_mode import ConsultaModeNode

        mode = ConsultaModeNode()
        assert not hasattr(mode, "_tool_dedup_cache")

    @pytest.mark.asyncio
    async def test_expediente_mode_has_no_dedup_cache_attribute(self) -> None:
        """ExpedienteModeNode instances must not have _tool_dedup_cache."""
        from agent.modes.expediente_mode import ExpedienteModeNode

        mode = ExpedienteModeNode()
        assert not hasattr(mode, "_tool_dedup_cache")
