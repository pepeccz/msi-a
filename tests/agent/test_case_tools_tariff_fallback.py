"""
Test for iniciar_expediente() tariff fallback mechanism.

Bug Fix (2026-02-07): Ensures that when the LLM forgets to pass
tarifa_calculada and tier_id parameters, the tool extracts them
from mode_context["tarifa_calculada"] as a defensive fallback.

This prevents cases from being created with NULL tariff values.
"""

import json
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.state.helpers import set_current_state
from agent.tools.case_tools import iniciar_expediente


@pytest.mark.asyncio
async def test_iniciar_expediente_fallback_extracts_tariff_from_state():
    """
    Test that iniciar_expediente extracts tariff from mode_context
    when LLM doesn't pass tarifa_calculada and tier_id parameters.
    
    Scenario:
    1. State has tarifa_calculada in mode_context (typical after price calculation)
    2. LLM calls iniciar_expediente WITHOUT passing tariff params
    3. Tool should extract tier_id and price from state fallback
    4. Case should be created with correct tariff values (NOT NULL)
    """
    
    # Setup: Mock state with tarifa_calculada in mode_context
    test_tier_id = str(uuid.uuid4())
    test_price = 410.0
    
    mock_state = {
        "conversation_id": "test-conv-123",
        "user_id": str(uuid.uuid4()),
        "fsm_state": {"current_step": "IDLE"},  # Allow expediente creation
        "mode_context": {
            "tarifa_calculada": json.dumps({  # Stored as JSON string (realistic)
                "texto": "TARIFA RECOMENDADA...",
                "datos": {
                    "tier_id": test_tier_id,
                    "price": test_price,
                    "element_codes": ["SUBCHASIS"]
                },
                "documentacion": {},
                "imagenes_ejemplo": []
            })
        }
    }
    
    set_current_state(mock_state)
    
    # Mock database operations
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    
    # Mock category lookup
    test_category_id = str(uuid.uuid4())
    
    with patch("agent.tools.case_tools.get_async_session", return_value=mock_session):
        with patch("agent.tools.case_tools._get_active_case_for_conversation", return_value=None):
            with patch("agent.tools.case_tools._get_category_id_by_slug", return_value=test_category_id):
                with patch("agent.tools.case_tools._validate_element_codes_for_category") as mock_validate:
                    # Mock validation as successful
                    mock_validate.return_value = (True, [], ["SUBCHASIS"], ["SUBCHASIS"], {})
                    
                    with patch("agent.tools.case_tools.get_tarifa_service") as mock_tarifa_service:
                        # Mock tariff service
                        mock_service = MagicMock()
                        mock_service.get_category_data = AsyncMock(return_value={
                            "base_documentation": []
                        })
                        mock_tarifa_service.return_value = mock_service
                        
                        with patch("agent.tools.case_tools.initialize_element_data_status", return_value={}):
                            # Call WITHOUT tariff params (simulate LLM forgetting)
                            result = await iniciar_expediente(
                                categoria_vehiculo="motos-part",
                                codigos_elementos=["SUBCHASIS"],
                                # NO tarifa_calculada
                                # NO tier_id
                            )
    
    # Verify: Result is successful
    assert result["success"] is True, f"Expected success, got: {result}"
    assert "case_id" in result, "Expected case_id in result"
    
    # Verify: Case was created with correct tariff values (extracted from fallback)
    # Check the Case() call arguments
    mock_session.add.assert_called_once()
    case_obj = mock_session.add.call_args[0][0]
    
    assert case_obj.tariff_tier_id == uuid.UUID(test_tier_id), \
        f"Expected tier_id {test_tier_id}, got {case_obj.tariff_tier_id}"
    
    assert case_obj.tariff_amount == Decimal(str(test_price)), \
        f"Expected price {test_price}, got {case_obj.tariff_amount}"
    
    assert case_obj.element_codes == ["SUBCHASIS"]
    assert case_obj.status == "collecting"


@pytest.mark.asyncio
async def test_iniciar_expediente_fallback_no_tariff_in_state():
    """
    Test that iniciar_expediente handles gracefully when:
    1. LLM doesn't pass tariff params
    2. State doesn't have tarifa_calculada either
    
    Expected: Case created with NULL tariff (logs warning)
    """
    
    # Setup: State WITHOUT tarifa_calculada
    mock_state = {
        "conversation_id": "test-conv-456",
        "user_id": str(uuid.uuid4()),
        "fsm_state": {"current_step": "IDLE"},
        "mode_context": {}  # No tarifa_calculada
    }
    
    set_current_state(mock_state)
    
    # Mock database operations
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    
    test_category_id = str(uuid.uuid4())
    
    with patch("agent.tools.case_tools.get_async_session", return_value=mock_session):
        with patch("agent.tools.case_tools._get_active_case_for_conversation", return_value=None):
            with patch("agent.tools.case_tools._get_category_id_by_slug", return_value=test_category_id):
                with patch("agent.tools.case_tools._validate_element_codes_for_category") as mock_validate:
                    mock_validate.return_value = (True, [], ["ESCAPE"], ["ESCAPE"], {})
                    
                    with patch("agent.tools.case_tools.get_tarifa_service") as mock_tarifa_service:
                        mock_service = MagicMock()
                        mock_service.get_category_data = AsyncMock(return_value={
                            "base_documentation": []
                        })
                        mock_tarifa_service.return_value = mock_service
                        
                        with patch("agent.tools.case_tools.initialize_element_data_status", return_value={}):
                            # Call WITHOUT tariff params AND no state data
                            result = await iniciar_expediente(
                                categoria_vehiculo="motos-part",
                                codigos_elementos=["ESCAPE"],
                            )
    
    # Verify: Still succeeds (doesn't crash)
    assert result["success"] is True
    
    # Verify: Case created with NULL tariff (fallback didn't find data)
    case_obj = mock_session.add.call_args[0][0]
    assert case_obj.tariff_tier_id is None, "Expected NULL tier_id when no fallback data"
    assert case_obj.tariff_amount is None, "Expected NULL tariff_amount when no fallback data"


@pytest.mark.asyncio
async def test_iniciar_expediente_llm_provides_tariff_no_fallback():
    """
    Test that when LLM DOES provide tariff params, the fallback is NOT used.
    
    Expected: Use LLM-provided values directly (no state extraction)
    """
    
    # Setup: State with DIFFERENT tariff values (to prove fallback not used)
    wrong_tier_id = str(uuid.uuid4())
    
    mock_state = {
        "conversation_id": "test-conv-789",
        "user_id": str(uuid.uuid4()),
        "fsm_state": {"current_step": "IDLE"},
        "mode_context": {
            "tarifa_calculada": json.dumps({
                "datos": {
                    "tier_id": wrong_tier_id,  # Different
                    "price": 999.0,            # Different
                }
            })
        }
    }
    
    set_current_state(mock_state)
    
    # Mock database
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    
    # LLM-provided values (correct ones)
    correct_tier_id = str(uuid.uuid4())
    correct_price = 410.0
    
    test_category_id = str(uuid.uuid4())
    
    with patch("agent.tools.case_tools.get_async_session", return_value=mock_session):
        with patch("agent.tools.case_tools._get_active_case_for_conversation", return_value=None):
            with patch("agent.tools.case_tools._get_category_id_by_slug", return_value=test_category_id):
                with patch("agent.tools.case_tools._validate_element_codes_for_category") as mock_validate:
                    mock_validate.return_value = (True, [], ["MANILLAR"], ["MANILLAR"], {})
                    
                    with patch("agent.tools.case_tools.get_tarifa_service") as mock_tarifa_service:
                        mock_service = MagicMock()
                        mock_service.get_category_data = AsyncMock(return_value={
                            "base_documentation": []
                        })
                        mock_tarifa_service.return_value = mock_service
                        
                        with patch("agent.tools.case_tools.initialize_element_data_status", return_value={}):
                            # Call WITH tariff params (LLM did its job)
                            result = await iniciar_expediente(
                                categoria_vehiculo="motos-part",
                                codigos_elementos=["MANILLAR"],
                                tarifa_calculada=correct_price,  # LLM-provided
                                tier_id=correct_tier_id,         # LLM-provided
                            )
    
    # Verify: Used LLM-provided values (NOT state fallback)
    case_obj = mock_session.add.call_args[0][0]
    
    assert case_obj.tariff_tier_id == uuid.UUID(correct_tier_id), \
        "Should use LLM-provided tier_id, not fallback"
    
    assert case_obj.tariff_amount == Decimal(str(correct_price)), \
        "Should use LLM-provided price, not fallback"


@pytest.mark.asyncio
async def test_iniciar_expediente_fallback_partial_llm_data():
    """
    Test fallback when LLM provides ONLY tier_id but NOT price (or vice versa).
    
    Expected: Fallback fills in the missing value from state.
    """
    
    # Setup: State with complete tariff data
    test_tier_id = str(uuid.uuid4())
    test_price = 520.0
    
    mock_state = {
        "conversation_id": "test-conv-partial",
        "user_id": str(uuid.uuid4()),
        "fsm_state": {"current_step": "IDLE"},
        "mode_context": {
            "tarifa_calculada": json.dumps({
                "datos": {
                    "tier_id": test_tier_id,
                    "price": test_price,
                }
            })
        }
    }
    
    set_current_state(mock_state)
    
    # Mock database
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    
    test_category_id = str(uuid.uuid4())
    
    with patch("agent.tools.case_tools.get_async_session", return_value=mock_session):
        with patch("agent.tools.case_tools._get_active_case_for_conversation", return_value=None):
            with patch("agent.tools.case_tools._get_category_id_by_slug", return_value=test_category_id):
                with patch("agent.tools.case_tools._validate_element_codes_for_category") as mock_validate:
                    mock_validate.return_value = (True, [], ["ASIDEROS"], ["ASIDEROS"], {})
                    
                    with patch("agent.tools.case_tools.get_tarifa_service") as mock_tarifa_service:
                        mock_service = MagicMock()
                        mock_service.get_category_data = AsyncMock(return_value={
                            "base_documentation": []
                        })
                        mock_tarifa_service.return_value = mock_service
                        
                        with patch("agent.tools.case_tools.initialize_element_data_status", return_value={}):
                            # Call with ONLY tier_id (no price)
                            result = await iniciar_expediente(
                                categoria_vehiculo="motos-part",
                                codigos_elementos=["ASIDEROS"],
                                tier_id=test_tier_id,  # Provided
                                # tarifa_calculada NOT provided → should fallback
                            )
    
    # Verify: tier_id from LLM, price from fallback
    case_obj = mock_session.add.call_args[0][0]
    
    assert case_obj.tariff_tier_id == uuid.UUID(test_tier_id), \
        "Should use LLM-provided tier_id"
    
    assert case_obj.tariff_amount == Decimal(str(test_price)), \
        "Should use fallback price from state"
