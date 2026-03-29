"""
Unit tests for p0-state-integrity-fixes Fix 2:
finalizar_expediente() reads from DB Case columns, not stale case_fsm_state.

Root cause: Lines that build the Chatwoot private note read element_codes,
category_slug, taller_propio, and tariff_amount from case_fsm_state (a
ContextVar snapshot potentially stale at finalization time). These values are
authoritative columns on the Case row itself. Additionally, the original
session.get(Case, ...) did not eager-load Case.category, so accessing
case.category.slug would lazy-load and fail in async.

Fix:
- Change 2a: Use select(...).options(selectinload(Case.category)) instead of
  session.get(Case, ...) to eager-load the category relationship.
- Change 2b: Read element_codes, category_slug, taller_propio, tariff_amount
  from case.* (DB row), not case_fsm_state.get(...).

Spec scenarios:
- F2-S1 (stale context, note built from DB): When mode_context has empty/wrong
  element_codes, taller_propio=None, tariff_amount=None, and category_slug
  "wrong-slug", the Chatwoot note must reflect the authoritative DB values.
- F2-S2 (happy path, MSI certificate supplement): taller_propio=False triggers
  the 85€ supplement in the price display (from DB column, not stale context).
- F2-S3 (happy path, taller propio=True): taller_propio=True shows simple price.
- F2-S4 (case not found): Non-existent case_id returns early with error, not
  AttributeError.
"""

from __future__ import annotations

import sys
import types
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub optional dependencies not installed in the local test environment.
# Must be done BEFORE importing agent.tools.case_tools (which transitively
# imports vehicle_tools → langchain_openai and other optional deps).
# ---------------------------------------------------------------------------

# structlog stub
if "structlog" not in sys.modules:
    _structlog = types.ModuleType("structlog")
    _structlog.get_logger = lambda *a, **kw: MagicMock()  # type: ignore[attr-defined]
    sys.modules["structlog"] = _structlog

# langchain_openai stub (not installed locally; only needed at import time for vehicle_tools)
if "langchain_openai" not in sys.modules:
    _lco = types.ModuleType("langchain_openai")
    _lco.ChatOpenAI = MagicMock()  # type: ignore[attr-defined]
    sys.modules["langchain_openai"] = _lco

# langgraph.checkpoint.redis stub (not installed locally)
for _mod_name in ("langgraph.checkpoint.redis", "langgraph.checkpoint.redis.aio"):
    if _mod_name not in sys.modules:
        _stub = types.ModuleType(_mod_name)
        _stub.AsyncRedisSaver = MagicMock()  # type: ignore[attr-defined]
        sys.modules[_mod_name] = _stub

# ---------------------------------------------------------------------------
# Now safe to import agent code
# ---------------------------------------------------------------------------

import agent.tools.case_tools as case_tools_module

# Access the underlying coroutine from the LangChain @tool wrapper
finalizar_expediente_func = case_tools_module.finalizar_expediente.coroutine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_case_id() -> str:
    return str(uuid.uuid4())


def _build_mock_case(
    *,
    case_id: str | None = None,
    element_codes: list[str] | None = None,
    taller_propio: bool | None = None,
    tariff_amount: Decimal | None = None,
    category_slug: str | None = None,
    status: str = "active",
) -> MagicMock:
    """Return a mock Case with the given DB column values."""
    mock_case = MagicMock()
    mock_case.id = uuid.UUID(case_id) if case_id else uuid.uuid4()
    mock_case.element_codes = element_codes if element_codes is not None else []
    mock_case.taller_propio = taller_propio
    mock_case.tariff_amount = tariff_amount
    mock_case.status = status
    mock_case.metadata_ = {}

    # Build the category relationship mock
    if category_slug is not None:
        mock_case.category = MagicMock()
        mock_case.category.slug = category_slug
    else:
        mock_case.category = None

    return mock_case


def _build_session_mock(case: MagicMock | None = None) -> AsyncMock:
    """
    Build a minimal async session mock.
    session.execute returns a result whose scalar_one_or_none() returns `case`.
    """
    mock_result = MagicMock()
    mock_result.scalar_one_or_none = MagicMock(return_value=case)

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()
    return mock_session


# ---------------------------------------------------------------------------
# F2-S1 — Stale context: note built from DB columns, ignores fsm_state values
# ---------------------------------------------------------------------------


class TestFinalizarExpedienteUsesDBNotModeContext:
    """
    F2-S1: When mode_context/case_fsm_state is stale (wrong/missing values),
    the Chatwoot note must be built from the authoritative DB Case row.
    """

    @pytest.mark.asyncio
    async def test_note_built_from_db_not_stale_mode_context(self):
        """
        Given:  DB Case has element_codes=["ESCAPE","MANILLAR"],
                taller_propio=True, tariff_amount=450.00, category.slug="motos-part"
                case_fsm_state (mode_context) has stale empty/wrong values
        When:   finalizar_expediente() is called
        Then:   The Chatwoot private note contains "ESCAPE, MANILLAR" (from DB)
                and "motos-part" (from DB), not the stale values
                and the price is "450.00€ + IVA" (taller_propio=True)
        """
        case_id = _make_case_id()

        db_case = _build_mock_case(
            case_id=case_id,
            element_codes=["ESCAPE", "MANILLAR"],
            taller_propio=True,
            tariff_amount=Decimal("450.00"),
            category_slug="motos-part",
            status="active",
        )

        # Stale mode_context — wrong values for all 4 fields
        stale_context = {
            "element_codes": [],  # stale: empty
            "taller_propio": None,  # stale: not set
            "tariff_amount": None,  # stale: not set
            "category_slug": "wrong-slug",  # stale: wrong slug
        }

        mock_session = _build_session_mock(case=db_case)

        captured_note = {}

        async def _mock_add_private_note(conversation_id, note):
            captured_note["content"] = note

        mock_chatwoot = AsyncMock()
        mock_chatwoot.add_private_note = _mock_add_private_note
        mock_chatwoot.add_labels = AsyncMock()

        from agent.utils.expediente_types import CollectionStep

        with (
            patch(
                "agent.tools.case_tools._get_mode_context",
                return_value=stale_context,
            ),
            patch(
                "agent.tools.case_tools.get_current_state",
                return_value={
                    "conversation_id": "42",
                    "user_id": str(uuid.uuid4()),
                    "mode_context": stale_context,
                    "current_mode": "EXPEDIENTE_MODE",
                    "fsm_state": {},
                },
            ),
            patch(
                "agent.tools.case_tools._get_case_id_with_fallback",
                return_value=case_id,
            ),
            patch(
                "agent.tools.case_tools._get_current_step_from_context",
                return_value=CollectionStep.REVIEW_SUMMARY,
            ),
            patch(
                "agent.tools.case_tools.get_async_session",
                return_value=mock_session,
            ),
            patch(
                "agent.tools.case_tools._reset_fsm",
                return_value={},
            ),
            # ChatwootClient is imported inside the function body via
            # `from shared.chatwoot_client import ChatwootClient`, so we patch
            # the source module rather than case_tools.
            patch(
                "shared.chatwoot_client.ChatwootClient",
                return_value=mock_chatwoot,
            ),
        ):
            result = await finalizar_expediente_func()

        assert result.get("success") is True, f"Expected success. Got: {result}"

        note = captured_note.get("content", "")
        # DB element_codes — not stale empty list
        assert "ESCAPE" in note, (
            f"Expected 'ESCAPE' in note (from DB element_codes). Note:\n{note}"
        )
        assert "MANILLAR" in note, (
            f"Expected 'MANILLAR' in note (from DB element_codes). Note:\n{note}"
        )
        # DB category slug — not stale "wrong-slug"
        assert "motos-part" in note, (
            f"Expected 'motos-part' in note (from DB category.slug). Note:\n{note}"
        )
        assert "wrong-slug" not in note, (
            f"'wrong-slug' must NOT appear in note. Note:\n{note}"
        )
        # DB tariff_amount — taller_propio=True → simple price
        assert "450.00" in note, (
            f"Expected '450.00' from DB tariff_amount. Note:\n{note}"
        )


# ---------------------------------------------------------------------------
# F2-S2 — taller_propio=False from DB: MSI certificate supplement (+85€)
# ---------------------------------------------------------------------------


class TestFinalizarExpedienteCertificadoSupplement:
    """
    F2-S2: When DB Case has taller_propio=False, the price display must include
    the 85€ certificate supplement (read from DB, not stale context).
    """

    @pytest.mark.asyncio
    async def test_certificado_supplement_when_taller_propio_false_in_db(self):
        """
        Given:  DB Case has taller_propio=False, tariff_amount=410.00
                case_fsm_state has taller_propio=None (stale)
        When:   finalizar_expediente() is called
        Then:   Note price shows "85€ (certificado MSI)" supplement
                Total is 410 + 85 = 495
        """
        case_id = _make_case_id()

        db_case = _build_mock_case(
            case_id=case_id,
            element_codes=["ESCAPE"],
            taller_propio=False,  # MSI certificate required
            tariff_amount=Decimal("410.00"),
            category_slug="motos-part",
            status="active",
        )

        # Stale: taller_propio not set in mode_context
        stale_context = {
            "taller_propio": None,
            "tariff_amount": None,
            "element_codes": [],
            "category_slug": "N/A",
        }

        mock_session = _build_session_mock(case=db_case)

        captured_note = {}

        async def _mock_add_private_note(conversation_id, note):
            captured_note["content"] = note

        mock_chatwoot = AsyncMock()
        mock_chatwoot.add_private_note = _mock_add_private_note
        mock_chatwoot.add_labels = AsyncMock()

        from agent.utils.expediente_types import CollectionStep

        with (
            patch(
                "agent.tools.case_tools._get_mode_context",
                return_value=stale_context,
            ),
            patch(
                "agent.tools.case_tools.get_current_state",
                return_value={
                    "conversation_id": "42",
                    "user_id": str(uuid.uuid4()),
                    "mode_context": stale_context,
                    "current_mode": "EXPEDIENTE_MODE",
                    "fsm_state": {},
                },
            ),
            patch(
                "agent.tools.case_tools._get_case_id_with_fallback",
                return_value=case_id,
            ),
            patch(
                "agent.tools.case_tools._get_current_step_from_context",
                return_value=CollectionStep.REVIEW_SUMMARY,
            ),
            patch(
                "agent.tools.case_tools.get_async_session",
                return_value=mock_session,
            ),
            patch(
                "agent.tools.case_tools._reset_fsm",
                return_value={},
            ),
            # ChatwootClient is imported inside the function body via
            # `from shared.chatwoot_client import ChatwootClient`, so we patch
            # the source module rather than case_tools.
            patch(
                "shared.chatwoot_client.ChatwootClient",
                return_value=mock_chatwoot,
            ),
        ):
            result = await finalizar_expediente_func()

        assert result.get("success") is True, f"Expected success. Got: {result}"

        note = captured_note.get("content", "")
        # taller_propio=False (from DB) must trigger the certificate supplement
        assert "certificado MSI" in note or "85" in note, (
            f"Expected certificate supplement in note (taller_propio=False from DB). "
            f"Note:\n{note}"
        )
        # tariff_amount=410 from DB
        assert "410" in note, f"Expected '410' from DB tariff_amount. Note:\n{note}"


# ---------------------------------------------------------------------------
# F2-S4 — Case not found: early return with error (no AttributeError)
# ---------------------------------------------------------------------------


class TestFinalizarExpedienteCaseNotFound:
    """
    F2-S4: When the Case row doesn't exist in DB, the function must return
    a tool_error_response early without raising AttributeError on case.element_codes.
    """

    @pytest.mark.asyncio
    async def test_case_not_found_returns_error_not_exception(self):
        """
        Given:  DB has no Case with case_id (scalar_one_or_none returns None)
        When:   finalizar_expediente() is called
        Then:   Returns a dict with success=False (not raises AttributeError)
        """
        case_id = _make_case_id()

        # session returns None for the case
        mock_session = _build_session_mock(case=None)

        from agent.utils.expediente_types import CollectionStep

        with (
            patch(
                "agent.tools.case_tools._get_mode_context",
                return_value={},
            ),
            patch(
                "agent.tools.case_tools.get_current_state",
                return_value={
                    "conversation_id": "42",
                    "user_id": str(uuid.uuid4()),
                    "mode_context": {},
                    "current_mode": "EXPEDIENTE_MODE",
                    "fsm_state": {},
                },
            ),
            patch(
                "agent.tools.case_tools._get_case_id_with_fallback",
                return_value=case_id,
            ),
            patch(
                "agent.tools.case_tools._get_current_step_from_context",
                return_value=CollectionStep.REVIEW_SUMMARY,
            ),
            patch(
                "agent.tools.case_tools.get_async_session",
                return_value=mock_session,
            ),
        ):
            result = await finalizar_expediente_func()

        # Must not raise; must return an error dict
        assert result.get("success") is False, (
            f"Expected success=False for non-existent case. Got: {result}"
        )
        assert (
            result.get("error_code") == "CASE_NOT_FOUND"
            or "not found" in str(result.get("message", "")).lower()
            or "error" in str(result).lower()
        ), f"Expected error response for missing case. Got: {result}"
