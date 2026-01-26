"""
Tests for case tools validation - specifically element code validation.

These tests verify that iniciar_expediente() properly validates element codes
and rejects hallucinated/invalid codes from the LLM.
"""

import pytest
import uuid
from unittest.mock import AsyncMock, patch, MagicMock

from agent.tools.case_tools import (
    _validate_element_codes_for_category,
    iniciar_expediente,
)


class TestValidateElementCodesForCategory:
    """Test the element code validation helper function."""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        return session

    async def test_all_codes_valid(self, mock_db_session):
        """All provided codes exist in the category."""
        # Setup mock to return valid codes
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("ESCAPE",),
            ("BOLA_REMOLQUE",),
            ("ALUMBRADO",),
        ]
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        with patch(
            "agent.tools.case_tools.get_async_session",
            return_value=mock_db_session,
        ):
            category_id = str(uuid.uuid4())
            is_valid, invalid, valid = await _validate_element_codes_for_category(
                category_id,
                ["ESCAPE", "BOLA_REMOLQUE"],
            )

            assert is_valid is True
            assert invalid == []
            assert "ESCAPE" in valid
            assert "BOLA_REMOLQUE" in valid

    async def test_some_codes_invalid(self, mock_db_session):
        """Some provided codes don't exist - should return invalid list."""
        # Setup mock to return valid codes
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("ESCAPE",),
            ("BOLA_REMOLQUE",),
            ("ALUMBRADO",),
        ]
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        with patch(
            "agent.tools.case_tools.get_async_session",
            return_value=mock_db_session,
        ):
            category_id = str(uuid.uuid4())
            is_valid, invalid, valid = await _validate_element_codes_for_category(
                category_id,
                ["ESCAPE", "TOLDO_LATERAL", "INVENTED_CODE"],  # 2 invalid codes
            )

            assert is_valid is False
            assert "TOLDO_LATERAL" in invalid
            assert "INVENTED_CODE" in invalid
            assert len(invalid) == 2

    async def test_all_codes_invalid(self, mock_db_session):
        """All provided codes are invalid."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("ESCAPE",),
            ("BOLA_REMOLQUE",),
        ]
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        with patch(
            "agent.tools.case_tools.get_async_session",
            return_value=mock_db_session,
        ):
            category_id = str(uuid.uuid4())
            is_valid, invalid, valid = await _validate_element_codes_for_category(
                category_id,
                ["FAKE_CODE_1", "FAKE_CODE_2"],
            )

            assert is_valid is False
            assert len(invalid) == 2
            assert "FAKE_CODE_1" in invalid
            assert "FAKE_CODE_2" in invalid

    async def test_empty_codes_list(self, mock_db_session):
        """Empty codes list should be valid (edge case)."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [("ESCAPE",)]
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        with patch(
            "agent.tools.case_tools.get_async_session",
            return_value=mock_db_session,
        ):
            category_id = str(uuid.uuid4())
            is_valid, invalid, valid = await _validate_element_codes_for_category(
                category_id,
                [],
            )

            assert is_valid is True
            assert invalid == []


class TestIniciarExpedienteValidation:
    """Test iniciar_expediente() rejects invalid element codes."""

    @pytest.fixture
    def mock_state(self):
        """Mock conversation state."""
        return {
            "conversation_id": "test-conv-123",
            "user_id": str(uuid.uuid4()),
            "fsm_state": None,
        }

    async def test_rejects_invalid_element_codes(self, mock_state):
        """iniciar_expediente should reject hallucinated element codes."""
        category_id = str(uuid.uuid4())

        # Mock all required functions
        with patch(
            "agent.tools.case_tools.get_current_state",
            return_value=mock_state,
        ), patch(
            "agent.tools.case_tools._get_active_case_for_conversation",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "agent.tools.case_tools._get_category_id_by_slug",
            new_callable=AsyncMock,
            return_value=category_id,
        ), patch(
            "agent.tools.case_tools._validate_element_codes_for_category",
            new_callable=AsyncMock,
            return_value=(False, ["INVENTED_CODE"], ["ESCAPE", "BOLA_REMOLQUE"]),
        ):
            # Call the tool with an invalid code
            result = await iniciar_expediente.coroutine(
                categoria_vehiculo="aseicars-prof",
                codigos_elementos=["INVENTED_CODE"],
                tarifa_calculada=59.0,
            )

            # Should fail
            assert result["success"] is False
            assert "INVENTED_CODE" in result["error"]
            assert "message" in result  # Should have guidance
            assert "QUÉ HACER" in result["message"]
            assert "identificar_y_resolver_elementos" in result["message"]

    async def test_accepts_valid_element_codes(self, mock_state):
        """iniciar_expediente should accept valid element codes."""
        category_id = str(uuid.uuid4())
        case_id = str(uuid.uuid4())

        # Mock database session for case creation
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        with patch(
            "agent.tools.case_tools.get_current_state",
            return_value=mock_state,
        ), patch(
            "agent.tools.case_tools._get_active_case_for_conversation",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "agent.tools.case_tools._get_category_id_by_slug",
            new_callable=AsyncMock,
            return_value=category_id,
        ), patch(
            "agent.tools.case_tools._validate_element_codes_for_category",
            new_callable=AsyncMock,
            return_value=(True, [], ["ESCAPE", "BOLA_REMOLQUE"]),
        ), patch(
            "agent.tools.case_tools.get_async_session",
            return_value=mock_session,
        ):
            result = await iniciar_expediente.coroutine(
                categoria_vehiculo="aseicars-prof",
                codigos_elementos=["ESCAPE"],
                tarifa_calculada=59.0,
            )

            # Should succeed
            assert result["success"] is True
            assert "case_id" in result
            assert result["next_step"] == "collect_images"


class TestElementCodeValidationEdgeCases:
    """Test edge cases in element code validation."""

    async def test_case_sensitive_validation(self):
        """Element codes should be case-sensitive."""
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [("ESCAPE",)]  # Uppercase
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch(
            "agent.tools.case_tools.get_async_session",
            return_value=mock_session,
        ):
            category_id = str(uuid.uuid4())
            
            # Lowercase should fail
            is_valid, invalid, _ = await _validate_element_codes_for_category(
                category_id,
                ["escape"],  # lowercase
            )
            assert is_valid is False
            assert "escape" in invalid

    async def test_duplicate_codes_handled(self):
        """Duplicate codes in input should be handled correctly."""
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [("ESCAPE",), ("BOLA_REMOLQUE",)]
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch(
            "agent.tools.case_tools.get_async_session",
            return_value=mock_session,
        ):
            category_id = str(uuid.uuid4())
            
            # Duplicates should be valid (set operation handles them)
            is_valid, invalid, _ = await _validate_element_codes_for_category(
                category_id,
                ["ESCAPE", "ESCAPE", "ESCAPE"],
            )
            assert is_valid is True
            assert invalid == []
