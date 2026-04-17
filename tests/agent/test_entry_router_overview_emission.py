"""
T3a + T3b + T3c — entry_router overview emission, expediente_init intro message,
and build_new_expediente_case_instructions simplification.

Verifies:
- T3a: entry_router emits AIMessage when expediente_intro_sent=False and
       expediente_intro_message is present; tombstones in same Command.update.
- T3a (idempotency): second entry with expediente_intro_sent=True does NOT emit.
- T3b: _initialize_new_case (via expediente_init) populates expediente_intro_message
       and expediente_intro_sent=False in state output.
- T3c: build_new_expediente_case_instructions has a single code path (intro_already_sent
       branch removed); always returns valid LLM instructions.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers — minimal ExpedienteState-shaped dicts
# ---------------------------------------------------------------------------

def _make_state(
    *,
    case_id: str | None = "case-123",
    expediente_sub_mode: str = "collect_element_data",
    expediente_intro_message: str | None = None,
    expediente_intro_sent: bool = False,
    messages: list[Any] | None = None,
    conversation_id: str = "conv-test",
    user_message: str = "hola",
) -> dict[str, Any]:
    state: dict[str, Any] = {
        "conversation_id": conversation_id,
        "user_message": user_message,
        "expediente_sub_mode": expediente_sub_mode,
        "expediente_intro_sent": expediente_intro_sent,
        "messages": messages if messages is not None else [],
    }
    if case_id is not None:
        state["case_id"] = case_id
    if expediente_intro_message is not None:
        state["expediente_intro_message"] = expediente_intro_message
    return state


# ---------------------------------------------------------------------------
# T3a — entry_router emits AIMessage on resumed expediente path
# (case_id present, so no initialization)
# ---------------------------------------------------------------------------


class TestEntryRouterOverviewEmission:
    """T3a: entry_router emits intro AIMessage and tombstones atomically."""

    @pytest.mark.asyncio
    async def test_emits_ai_message_when_intro_not_sent(self):
        """
        When expediente_intro_message is set and expediente_intro_sent=False,
        entry_router must include an AIMessage in the Command update's messages
        and set expediente_intro_sent=True with expediente_intro_message=None.
        """
        from agent.modes.expediente_nodes import entry_router

        intro_text = "He abierto tu expediente. Tiene 6 fases."
        state = _make_state(
            case_id="case-abc",
            expediente_intro_message=intro_text,
            expediente_intro_sent=False,
        )

        # Patch DB guard so it doesn't make real DB calls
        with patch(
            "agent.modes.expediente_nodes.get_async_session",
        ) as mock_session_ctx:
            # Simulate DB returning a non-terminal case
            mock_session = AsyncMock()
            mock_case = MagicMock()
            mock_case.status = "collecting"
            mock_scalars = MagicMock()
            mock_scalars.first.return_value = mock_case
            mock_session.scalars = AsyncMock(return_value=mock_scalars)
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            cmd = await entry_router(state)

        update = cmd.update or {}
        # Messages list must contain exactly one AIMessage with the intro text
        emitted_messages = update.get("messages", [])
        assert len(emitted_messages) == 1, (
            f"Expected 1 AIMessage in update, got {len(emitted_messages)}: {emitted_messages}"
        )
        msg = emitted_messages[0]
        assert type(msg).__name__ == "AIMessage", f"Expected AIMessage, got {type(msg)}"
        assert msg.content == intro_text, (
            f"AIMessage content mismatch. Expected: {intro_text!r}, got: {msg.content!r}"
        )

        # Tombstones: flag set True, message cleared
        assert update.get("expediente_intro_sent") is True, (
            "expediente_intro_sent must be True after emission"
        )
        assert update.get("expediente_intro_message") is None, (
            "expediente_intro_message must be tombstoned to None after emission"
        )

    @pytest.mark.asyncio
    async def test_no_emission_when_already_sent(self):
        """
        When expediente_intro_sent=True, entry_router must NOT emit an AIMessage
        even if expediente_intro_message is still populated (idempotent guard).
        """
        from agent.modes.expediente_nodes import entry_router

        state = _make_state(
            case_id="case-abc",
            expediente_intro_message="He abierto tu expediente.",
            expediente_intro_sent=True,
        )

        with patch(
            "agent.modes.expediente_nodes.get_async_session",
        ) as mock_session_ctx:
            mock_session = AsyncMock()
            mock_case = MagicMock()
            mock_case.status = "collecting"
            mock_scalars = MagicMock()
            mock_scalars.first.return_value = mock_case
            mock_session.scalars = AsyncMock(return_value=mock_scalars)
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            cmd = await entry_router(state)

        update = cmd.update or {}
        emitted_messages = update.get("messages", [])
        assert emitted_messages == [], (
            f"No AIMessage should be emitted when intro already sent, got: {emitted_messages}"
        )

    @pytest.mark.asyncio
    async def test_no_emission_when_intro_message_absent(self):
        """
        When expediente_intro_message is None (not set), no emission even if
        expediente_intro_sent=False.
        """
        from agent.modes.expediente_nodes import entry_router

        state = _make_state(
            case_id="case-abc",
            expediente_intro_message=None,
            expediente_intro_sent=False,
        )

        with patch(
            "agent.modes.expediente_nodes.get_async_session",
        ) as mock_session_ctx:
            mock_session = AsyncMock()
            mock_case = MagicMock()
            mock_case.status = "collecting"
            mock_scalars = MagicMock()
            mock_scalars.first.return_value = mock_case
            mock_session.scalars = AsyncMock(return_value=mock_scalars)
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            cmd = await entry_router(state)

        update = cmd.update or {}
        assert update.get("messages", []) == [], (
            "No emission expected when expediente_intro_message is absent"
        )

    @pytest.mark.asyncio
    async def test_double_entry_race_emits_only_once(self):
        """
        Calling entry_router twice with same state (intro not sent) — first call
        emits; second call (with intro_sent=True from first call's update applied)
        does NOT emit. Simulates idempotent tombstone.
        """
        from agent.modes.expediente_nodes import entry_router

        intro_text = "He abierto tu expediente."
        state_first = _make_state(
            case_id="case-abc",
            expediente_intro_message=intro_text,
            expediente_intro_sent=False,
        )

        db_patch = patch("agent.modes.expediente_nodes.get_async_session")

        def _make_db_mock():
            mock_session_ctx = db_patch.start()
            mock_session = AsyncMock()
            mock_case = MagicMock()
            mock_case.status = "collecting"
            mock_scalars = MagicMock()
            mock_scalars.first.return_value = mock_case
            mock_session.scalars = AsyncMock(return_value=mock_scalars)
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            return mock_session_ctx

        with db_patch as mock_session_ctx:
            mock_session = AsyncMock()
            mock_case = MagicMock()
            mock_case.status = "collecting"
            mock_scalars = MagicMock()
            mock_scalars.first.return_value = mock_case
            mock_session.scalars = AsyncMock(return_value=mock_scalars)
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            cmd1 = await entry_router(state_first)

        # First call: should emit
        update1 = cmd1.update or {}
        assert len(update1.get("messages", [])) == 1, "First entry must emit AIMessage"

        # Apply the first call's tombstone to build state for second call
        state_second = dict(state_first)
        state_second["expediente_intro_sent"] = True
        state_second["expediente_intro_message"] = None

        with db_patch as mock_session_ctx:
            mock_session = AsyncMock()
            mock_case = MagicMock()
            mock_case.status = "collecting"
            mock_scalars = MagicMock()
            mock_scalars.first.return_value = mock_case
            mock_session.scalars = AsyncMock(return_value=mock_scalars)
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            cmd2 = await entry_router(state_second)

        update2 = cmd2.update or {}
        assert update2.get("messages", []) == [], (
            "Second entry (intro already sent) must NOT emit again"
        )


# ---------------------------------------------------------------------------
# T3a (init path) — entry_router emits on the init path (case_id absent)
# ---------------------------------------------------------------------------


class TestEntryRouterOverviewEmissionInitPath:
    """T3a: emission also works on the init path (auto-create flow)."""

    @pytest.mark.asyncio
    async def test_emits_ai_message_on_init_path(self):
        """
        When case_id is absent, entry_router calls initialize_expediente.
        If the returned init_updates contain expediente_intro_message and
        expediente_intro_sent=False, the router must emit the AIMessage.
        """
        from agent.modes.expediente_nodes import entry_router

        intro_text = "He abierto tu expediente de homologación. Tiene 6 fases."
        # State without case_id — triggers init path
        state = _make_state(
            case_id=None,
            expediente_intro_message=None,
            expediente_intro_sent=False,
            user_message="abreme el expediente",
        )

        fake_init_updates = {
            "case_id": "case-new-123",
            "expediente_sub_mode": "collect_element_data",
            "expediente_intro_message": intro_text,
            "expediente_intro_sent": False,
        }

        with patch(
            "agent.modes.expediente_nodes.initialize_expediente",
            new=AsyncMock(return_value=fake_init_updates),
        ):
            cmd = await entry_router(state)

        update = cmd.update or {}
        emitted_messages = update.get("messages", [])
        assert len(emitted_messages) == 1, (
            f"Expected 1 AIMessage on init path, got {len(emitted_messages)}: {emitted_messages}"
        )
        assert type(emitted_messages[0]).__name__ == "AIMessage"
        assert emitted_messages[0].content == intro_text

        # Tombstones applied atomically with init
        assert update.get("expediente_intro_sent") is True
        assert update.get("expediente_intro_message") is None


# ---------------------------------------------------------------------------
# T3b — expediente_init._initialize_new_case populates intro fields
# ---------------------------------------------------------------------------


class TestInitializeNewCaseIntroMessage:
    """T3b: _initialize_new_case output carries expediente_intro_message."""

    def test_build_expediente_opening_overview_not_empty(self):
        """
        build_expediente_opening_overview() must return a non-empty string
        that mentions the overview concept.
        """
        from agent.services.expediente_onboarding import build_expediente_opening_overview

        overview = build_expediente_opening_overview()
        assert isinstance(overview, str) and len(overview) > 20, (
            "build_expediente_opening_overview must return a non-empty string"
        )
        # Should mention expediente and phases (6 fases)
        assert "expediente" in overview.lower() or "fase" in overview.lower(), (
            f"Overview should mention expediente or fases, got: {overview!r}"
        )

    @pytest.mark.asyncio
    async def test_auto_create_flow_populates_expediente_intro_message(self):
        """
        The _initialize_new_case code path must populate
        expediente_intro_message in the returned state updates.

        _initialize_new_case imports helpers from agent.modes.expediente_mode
        internally, so we patch them at their source module.
        """
        from agent.services.expediente_onboarding import build_expediente_opening_overview

        expected_message = build_expediente_opening_overview()

        mock_case = MagicMock()
        mock_case.id = "test-case-id"

        # Patch functions where they're defined (imported with 'from X import Y')
        with (
            patch(
                "agent.modes.expediente_mode._load_base_doc_descriptions",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "agent.modes.expediente_mode._resolve_element_display_names",
                new=AsyncMock(return_value={"elem-1": "Elemento 1"}),
            ),
            patch(
                "agent.modes.expediente_mode._build_element_photo_instructions",
                return_value="",
            ),
            patch(
                "agent.services.case_service._load_user_data_for_case",
                new=AsyncMock(return_value={}),
            ),
            patch(
                "agent.services.case_image_batch_service.get_case_image_batch_service",
            ) as mock_batch_svc,
            patch(
                "agent.services.tarifa_service.get_tarifa_service",
                side_effect=Exception("not needed"),
            ),
        ):
            mock_batch_svc.return_value.open_for_scope = AsyncMock()

            from agent.services.expediente_init import _initialize_new_case

            result = await _initialize_new_case(
                case=mock_case,
                state={
                    "conversation_id": "conv-test",
                    "categoria_slug": "turismo",
                    "element_codes": ["elem-1"],
                    "tarifa_calculada": None,
                },
                categoria_slug="turismo",
                category_id="cat-123",
                element_codes=["elem-1"],
                confirmed_display_names={"elem-1": "Elemento 1"},
                tarifa_amount=None,
                tier_id=None,
                user_id_safe_str=None,
            )

        assert "expediente_intro_message" in result, (
            f"_initialize_new_case must return expediente_intro_message. "
            f"Got keys: {list(result.keys())}"
        )
        assert result["expediente_intro_message"] == expected_message, (
            f"expediente_intro_message must equal build_expediente_opening_overview(). "
            f"Got: {result['expediente_intro_message']!r}"
        )
        assert result.get("expediente_intro_sent") is False, (
            f"expediente_intro_sent must be False after init. Got: {result.get('expediente_intro_sent')}"
        )

    @pytest.mark.asyncio
    async def test_initialize_new_case_intro_sent_is_false(self):
        """
        Triangulation: expediente_intro_sent=False is set explicitly regardless
        of any other params. The flag must default to False (not True, not None).
        """
        mock_case = MagicMock()
        mock_case.id = "test-case-002"

        with (
            patch(
                "agent.modes.expediente_mode._load_base_doc_descriptions",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "agent.modes.expediente_mode._resolve_element_display_names",
                new=AsyncMock(return_value={"elem-2": "Elemento 2"}),
            ),
            patch(
                "agent.modes.expediente_mode._build_element_photo_instructions",
                return_value="",
            ),
            patch(
                "agent.services.case_service._load_user_data_for_case",
                new=AsyncMock(return_value={}),
            ),
            patch(
                "agent.services.case_image_batch_service.get_case_image_batch_service",
            ) as mock_batch_svc,
            patch(
                "agent.services.tarifa_service.get_tarifa_service",
                side_effect=Exception("skip"),
            ),
        ):
            mock_batch_svc.return_value.open_for_scope = AsyncMock()

            from agent.services.expediente_init import _initialize_new_case

            result = await _initialize_new_case(
                case=mock_case,
                state={
                    "conversation_id": "conv-002",
                    "categoria_slug": "furgoneta",
                    "element_codes": ["elem-2"],
                },
                categoria_slug="furgoneta",
                category_id="cat-456",
                element_codes=["elem-2"],
                confirmed_display_names={"elem-2": "Elemento 2"},
                tarifa_amount=150.0,
                tier_id="tier-1",
                user_id_safe_str=None,
            )

        assert result.get("expediente_intro_sent") is False, (
            f"expediente_intro_sent must be explicitly False, got: {result.get('expediente_intro_sent')!r}"
        )


# ---------------------------------------------------------------------------
# T3c — build_new_expediente_case_instructions single code path
# ---------------------------------------------------------------------------


class TestBuildNewExpedienteCaseInstructions:
    """
    T3c: After simplification, build_new_expediente_case_instructions always
    behaves as intro_already_sent=True (subgraph owns delivery).

    The intro_already_sent parameter is REMOVED. The function must:
    - No longer accept intro_already_sent keyword arg
    - Always instruct the LLM to start directly with phase 1 content
    - Return a non-empty string with required structural elements
    - NOT include the 6-phase overview inline (subgraph emits it)
    """

    def test_returns_nonempty_string(self):
        """The function must return a non-empty string."""
        from agent.services.expediente_onboarding import build_new_expediente_case_instructions

        result = build_new_expediente_case_instructions(
            first_element_display="Elemento A",
            total_elements=3,
        )
        assert isinstance(result, str) and len(result) > 50, (
            f"build_new_expediente_case_instructions must return a non-empty string, got: {result!r}"
        )

    def test_contains_element_name_in_instructions(self):
        """Instructions must reference the first element display name."""
        from agent.services.expediente_onboarding import build_new_expediente_case_instructions

        result = build_new_expediente_case_instructions(
            first_element_display="Luneta trasera",
            total_elements=2,
        )
        assert "Luneta trasera" in result, (
            f"Instructions must reference the first element. Got: {result!r}"
        )

    def test_does_not_accept_intro_already_sent_kwarg(self):
        """
        After T3c simplification, intro_already_sent is removed.
        Calling with intro_already_sent=False must raise TypeError.
        """
        import inspect
        from agent.services.expediente_onboarding import build_new_expediente_case_instructions

        sig = inspect.signature(build_new_expediente_case_instructions)
        assert "intro_already_sent" not in sig.parameters, (
            "intro_already_sent parameter must be removed from "
            "build_new_expediente_case_instructions after T3c simplification."
        )

    def test_triangulation_different_elements(self):
        """
        Triangulation: output changes with different element display name.
        Confirms production code runs and uses the input.
        """
        from agent.services.expediente_onboarding import build_new_expediente_case_instructions

        result_a = build_new_expediente_case_instructions(
            first_element_display="Parabrisas delantero",
            total_elements=1,
        )
        result_b = build_new_expediente_case_instructions(
            first_element_display="Luneta trasera",
            total_elements=5,
        )
        assert "Parabrisas delantero" in result_a
        assert "Luneta trasera" in result_b
        assert result_a != result_b, "Different inputs must produce different instructions"
