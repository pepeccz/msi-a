"""
Unit tests for expediente_mode.py _auto_create_case() — expediente-transition-ux BUG-2.

BUG-2: _auto_create_case() was setting expediente_intro_sent=True, which blocked
the safety-net in _process_message from prepending the 6-step overview. At the same
time, intro_already_sent=False was passed to build_new_expediente_case_instructions(),
causing the full overview text to be embedded in case_instructions — making the LLM
the solo delivery mechanism for the intro.

Fix:
  - intro_already_sent=True  → case_instructions contains 'automáticamente' variant
    (tells LLM that Python will send the overview; do NOT embed it)
  - expediente_intro_sent=False → safety-net fires on first COLLECT_ELEMENT_DATA turn
    and deterministically prepends build_expediente_opening_overview() to ai_response

Scenarios:
  1. _auto_create_case() result dict has expediente_intro_sent == False
  2. case_instructions does NOT embed the full overview text (COMUNICA directive absent)
  3. case_instructions contains 'automáticamente' (auto-send variant from intro_already_sent=True)

Architecture note:
  _auto_create_case is a private async method on ExpedienteModeNode that makes DB calls.
  We test it by mocking all heavy dependencies (DB session, get_or_create_active_case, etc.)
  and calling it directly on an instantiated node.
"""

from __future__ import annotations

import types
import sys
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Stub phonenumbers before importing agent modules
sys.modules.setdefault("phonenumbers", types.ModuleType("phonenumbers"))


def _make_minimal_context(case_id: str | None = None) -> dict[str, Any]:
    """Build a minimal mode_context for auto-create path."""
    return {
        "categoria_slug": "motos-part",
        "element_codes": ["ESCAPE"],
        "elementos_confirmados": [{"code": "ESCAPE", "name": "Escape", "price": 350.0}],
        "tarifa_calculada": {
            "datos": {
                "price": 350.0,
                "tier_id": str(uuid.uuid4()),
            }
        },
        "precio_comunicado": True,
        "expediente_intro_sent": True,  # Old stale value (should be overwritten)
        "case_id": case_id,
    }


def _make_mock_case(case_id: str) -> MagicMock:
    """Build a minimal mock Case ORM row."""
    mock = MagicMock()
    mock.id = uuid.UUID(case_id)
    return mock


class TestAutoCreateCaseBUG2:
    """BUG-2 — _auto_create_case() must return expediente_intro_sent=False."""

    @pytest.mark.asyncio
    async def test_expediente_intro_sent_is_false_in_result(self):
        """
        GIVEN _auto_create_case() runs successfully (auto-create path)
        THEN the returned context dict must have expediente_intro_sent == False
        """
        from agent.modes.expediente_mode import ExpedienteModeNode

        node = ExpedienteModeNode()
        case_id = str(uuid.uuid4())
        category_id = str(uuid.uuid4())

        current_context = _make_minimal_context()
        mock_case = _make_mock_case(case_id)

        # Mock DB session
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        # Mock execute result for DB queries (category_id lookup, element_data)
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = AsyncMock(
            return_value=MagicMock(id=uuid.UUID(category_id))
        )
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()

        with (
            patch(
                "agent.modes.expediente_mode.get_async_session",
                return_value=mock_session,
            ),
            patch(
                "agent.modes.expediente_mode.get_or_create_active_case",
                new_callable=AsyncMock,
                return_value=(mock_case, True),  # (case, created=True)
            ),
            patch(
                "agent.tools.case_tools._get_category_id_by_slug",
                new_callable=AsyncMock,
                return_value=category_id,
            ),
            patch(
                "agent.modes.expediente_mode._resolve_element_display_names",
                new_callable=AsyncMock,
                return_value={"ESCAPE": "Escape"},
            ),
            patch(
                "agent.modes.expediente_mode._build_element_photo_instructions",
                return_value="",
            ),
            patch(
                "agent.tools.case_tools._load_user_data_for_case",
                new_callable=AsyncMock,
                return_value={},
            ),
            patch(
                "agent.services.tarifa_service.get_tarifa_service",
                return_value=MagicMock(
                    get_category_data=AsyncMock(return_value={"base_documentation": []})
                ),
            ),
            patch(
                "agent.tools.case_tools.initialize_element_data_status",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "agent.services.case_image_batch_service.get_case_image_batch_service",
                return_value=MagicMock(open_for_scope=AsyncMock(return_value=None)),
            ),
        ):
            result = await node._auto_create_case(
                conversation_id="101",
                current_context=current_context,
                state={"user_id": str(uuid.uuid4()), "conversation_id": "101"},
            )

        assert result.get("expediente_intro_sent") is False, (
            f"Expected expediente_intro_sent=False (safety-net must fire), "
            f"got: {result.get('expediente_intro_sent')!r}"
        )

    @pytest.mark.asyncio
    async def test_case_instructions_do_not_embed_full_overview(self):
        """
        GIVEN _auto_create_case() runs with intro_already_sent=True (the fix)
        THEN case_instructions MUST NOT contain the full 'COMUNICA al usuario' directive
        (which would embed the entire overview and make the LLM responsible for delivery)
        """
        from agent.modes.expediente_mode import ExpedienteModeNode

        node = ExpedienteModeNode()
        case_id = str(uuid.uuid4())
        category_id = str(uuid.uuid4())
        current_context = _make_minimal_context()
        mock_case = _make_mock_case(case_id)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = AsyncMock(
            return_value=MagicMock(id=uuid.UUID(category_id))
        )
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()

        with (
            patch(
                "agent.modes.expediente_mode.get_async_session",
                return_value=mock_session,
            ),
            patch(
                "agent.modes.expediente_mode.get_or_create_active_case",
                new_callable=AsyncMock,
                return_value=(mock_case, True),
            ),
            patch(
                "agent.tools.case_tools._get_category_id_by_slug",
                new_callable=AsyncMock,
                return_value=category_id,
            ),
            patch(
                "agent.modes.expediente_mode._resolve_element_display_names",
                new_callable=AsyncMock,
                return_value={"ESCAPE": "Escape"},
            ),
            patch(
                "agent.modes.expediente_mode._build_element_photo_instructions",
                return_value="",
            ),
            patch(
                "agent.tools.case_tools._load_user_data_for_case",
                new_callable=AsyncMock,
                return_value={},
            ),
            patch(
                "agent.services.tarifa_service.get_tarifa_service",
                return_value=MagicMock(
                    get_category_data=AsyncMock(return_value={"base_documentation": []})
                ),
            ),
            patch(
                "agent.tools.case_tools.initialize_element_data_status",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "agent.services.case_image_batch_service.get_case_image_batch_service",
                return_value=MagicMock(open_for_scope=AsyncMock(return_value=None)),
            ),
        ):
            result = await node._auto_create_case(
                conversation_id="101",
                current_context=current_context,
                state={"user_id": str(uuid.uuid4()), "conversation_id": "101"},
            )

        case_instructions = result.get("case_instructions", "")
        assert (
            "COMUNICA al usuario exactamente este mensaje" not in case_instructions
        ), (
            "case_instructions must NOT embed the full overview (intro_already_sent=True path). "
            f"Got:\n{case_instructions[:300]}"
        )
        assert "automáticamente" in case_instructions.lower(), (
            "case_instructions should indicate that the system sends overview automatically. "
            f"Got:\n{case_instructions[:300]}"
        )
