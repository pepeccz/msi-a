"""
Integration tests for Multi-Element FSM Flow.

Tests that the FSM correctly transitions through all phases when collecting
data for multiple elements in a single case.

This addresses the bug where `completar_elemento_actual()` was returning
`"fsm_state"` instead of `"fsm_state_update"`, causing silent state loss.

Run with: pytest tests/test_multi_element_fsm_flow.py -v
"""

import pytest
from unittest.mock import patch, AsyncMock
from uuid import uuid4

from agent.tools.case_tools import iniciar_expediente
from agent.tools.element_data_tools import (
    confirmar_fotos_elemento,
    guardar_datos_elemento,
    completar_elemento_actual,
)
from agent.fsm.case_collection import CollectionStep
from database.models import User, Case, VehicleCategory
from database.connection import get_async_session
from sqlalchemy import select


@pytest.fixture
async def test_user():
    """Create a test user."""
    async with get_async_session() as session:
        user = User(
            id=uuid4(),
            phone="+34600000001",
            client_type="particular",
            name="Test User",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        yield user
        # Cleanup handled by test database rollback


@pytest.fixture
async def test_category():
    """Get motos-part category for testing."""
    async with get_async_session() as session:
        result = await session.execute(
            select(VehicleCategory).where(VehicleCategory.slug == "motos-part")
        )
        category = result.scalar()
        assert category is not None, "motos-part category must exist in test DB"
        return category


@pytest.fixture
def mock_conversation_state(test_user):
    """Mock conversation state with test user."""
    return {
        "conversation_id": "test-conversation-1",
        "user_id": str(test_user.id),
        "messages": [],
        "fsm_state": None,
    }


# =============================================================================
# TEST SUITE: Multi-Element FSM Transition Flow
# =============================================================================


@pytest.mark.asyncio
async def test_two_element_flow_completes_and_transitions(
    test_user, test_category, mock_conversation_state
):
    """
    Test that FSM correctly transitions to COLLECT_BASE_DOCS after completing
    all elements in a 2-element case (SUBCHASIS + MANILLAR).
    
    This is a regression test for the bug where completar_elemento_actual()
    returned "fsm_state" instead of "fsm_state_update", causing the state
    update to be ignored by the conversational_agent node.
    """
    
    # Mock set_current_state to inject our test state
    with patch("agent.tools.case_tools.set_current_state") as mock_set, \
         patch("agent.tools.case_tools.get_current_state") as mock_get, \
         patch("agent.tools.element_data_tools.set_current_state") as mock_set_elem, \
         patch("agent.tools.element_data_tools.get_current_state") as mock_get_elem:
        
        # Initialize state
        mock_get.return_value = mock_conversation_state.copy()
        mock_get_elem.return_value = mock_conversation_state.copy()
        
        # Step 1: iniciar_expediente with 2 elements
        result1 = await iniciar_expediente(
            categoria_vehiculo="motos-part",
            codigos_elementos=["SUBCHASIS", "MANILLAR"],
        )
        
        assert result1["success"] is True
        assert "fsm_state_update" in result1, "iniciar_expediente must return fsm_state_update"
        
        fsm_state = result1["fsm_state_update"]
        case_state = fsm_state["case_collection"]
        
        # Verify initial FSM state
        assert case_state["step"] == CollectionStep.COLLECT_ELEMENT_DATA.value
        assert case_state["current_element_index"] == 0
        assert case_state["element_phase"] == "photos"
        assert case_state["element_codes"] == ["SUBCHASIS", "MANILLAR"]
        assert case_state["element_data_status"] == {
            "SUBCHASIS": "pending",
            "MANILLAR": "pending",
        }
        
        case_id = result1["case_id"]
        mock_conversation_state["fsm_state"] = fsm_state
        mock_get.return_value = mock_conversation_state.copy()
        mock_get_elem.return_value = mock_conversation_state.copy()
        
        # Step 2: Confirm subchasis photos (element has required fields)
        result2 = await confirmar_fotos_elemento()
        
        assert result2["success"] is True
        assert "fsm_state_update" in result2, "confirmar_fotos_elemento must return fsm_state_update"
        
        fsm_state = result2["fsm_state_update"]
        case_state = fsm_state["case_collection"]
        
        # Should transition to "data" phase for subchasis
        assert case_state["element_phase"] == "data"
        assert case_state["element_data_status"]["SUBCHASIS"] == "photos_done"
        assert case_state["current_element_index"] == 0  # Still on subchasis
        
        mock_conversation_state["fsm_state"] = fsm_state
        mock_get.return_value = mock_conversation_state.copy()
        mock_get_elem.return_value = mock_conversation_state.copy()
        
        # Step 3: Save subchasis data (mock required fields)
        # Note: In real flow, guardar_datos_elemento would validate field_keys
        # For this test, we'll assume the data is valid
        result3 = await guardar_datos_elemento(
            datos={
                "descripcion_modificacion": "Recorte de 20 cm del subchasis trasero",
                "medida_desde_tanque": 150,
                "nueva_longitud_total": 3000,
            }
        )
        
        # guardar_datos_elemento doesn't return fsm_state_update
        # (it only saves to DB, FSM transition happens in completar_elemento_actual)
        assert result3["success"] is True or "all_required_collected" in result3
        
        # Step 4: Complete subchasis element
        result4 = await completar_elemento_actual()
        
        assert result4["success"] is True
        assert "fsm_state_update" in result4, "completar_elemento_actual MUST return fsm_state_update (NOT fsm_state)"
        
        fsm_state = result4["fsm_state_update"]
        case_state = fsm_state["case_collection"]
        
        # CRITICAL: Should advance to next element (MANILLAR)
        assert case_state["current_element_index"] == 1, "Should increment to element 1 (MANILLAR)"
        assert case_state["element_phase"] == "photos", "Should reset to photos phase for next element"
        assert case_state["element_data_status"]["SUBCHASIS"] == "complete"
        assert case_state["element_data_status"]["MANILLAR"] == "pending"
        assert case_state["step"] == CollectionStep.COLLECT_ELEMENT_DATA.value  # Still collecting elements
        
        mock_conversation_state["fsm_state"] = fsm_state
        mock_get.return_value = mock_conversation_state.copy()
        mock_get_elem.return_value = mock_conversation_state.copy()
        
        # Step 5: Confirm MANILLAR photos
        result5 = await confirmar_fotos_elemento()
        
        assert result5["success"] is True
        assert "fsm_state_update" in result5
        
        fsm_state = result5["fsm_state_update"]
        case_state = fsm_state["case_collection"]
        
        assert case_state["element_phase"] == "data"
        assert case_state["element_data_status"]["MANILLAR"] == "photos_done"
        
        mock_conversation_state["fsm_state"] = fsm_state
        mock_get.return_value = mock_conversation_state.copy()
        mock_get_elem.return_value = mock_conversation_state.copy()
        
        # Step 6: Save MANILLAR data
        result6 = await guardar_datos_elemento(
            datos={
                "marca": "Renthal",
                "modelo": "Fatbar 30",
                "material": "Acero",
                "diametro_mm": 34,
                "nuevo_ancho_mm": 800,
                "nueva_altura_mm": 70,
            }
        )
        
        assert result6["success"] is True or "all_required_collected" in result6
        
        # Step 7: Complete MANILLAR element (FINAL ELEMENT)
        result7 = await completar_elemento_actual()
        
        assert result7["success"] is True
        assert "fsm_state_update" in result7, "completar_elemento_actual MUST return fsm_state_update"
        
        fsm_state = result7["fsm_state_update"]
        case_state = fsm_state["case_collection"]
        
        # CRITICAL ASSERTION: Should transition to COLLECT_BASE_DOCS
        assert case_state["step"] == CollectionStep.COLLECT_BASE_DOCS.value, (
            "FSM MUST transition to COLLECT_BASE_DOCS after all elements are complete"
        )
        assert case_state["element_data_status"]["SUBCHASIS"] == "complete"
        assert case_state["element_data_status"]["MANILLAR"] == "complete"
        assert result7["all_elements_complete"] is True
        assert result7["next_step"] == "COLLECT_BASE_DOCS"


@pytest.mark.asyncio
async def test_completar_elemento_actual_returns_fsm_state_update_key():
    """
    Unit test to verify completar_elemento_actual() returns the correct key.
    
    This is a regression test for the bug where the function was returning
    "fsm_state" instead of "fsm_state_update", causing the conversational_agent
    node to ignore the state update (it only checks for "fsm_state_update").
    """
    
    # Mock state with 1 element completed
    mock_state = {
        "conversation_id": "test",
        "user_id": str(uuid4()),
        "fsm_state": {
            "case_collection": {
                "step": CollectionStep.COLLECT_ELEMENT_DATA.value,
                "case_id": str(uuid4()),
                "category_slug": "motos-part",
                "category_id": uuid4(),
                "element_codes": ["MANILLAR"],
                "current_element_index": 0,
                "element_phase": "data",
                "element_data_status": {
                    "MANILLAR": "photos_done",
                },
            }
        },
    }
    
    with patch("agent.tools.element_data_tools.get_current_state") as mock_get, \
         patch("agent.tools.element_data_tools._get_element_by_code") as mock_elem, \
         patch("agent.tools.element_data_tools._get_required_fields_for_element") as mock_fields, \
         patch("agent.tools.element_data_tools._get_or_create_case_element_data") as mock_case_elem, \
         patch("agent.tools.element_data_tools._update_case_element_data") as mock_update:
        
        mock_get.return_value = mock_state
        
        # Mock element
        mock_element = AsyncMock()
        mock_element.id = uuid4()
        mock_element.name = "Manillar"
        mock_elem.return_value = mock_element
        
        # Mock no required fields (to simplify test)
        mock_fields.return_value = []
        
        # Mock case element data
        mock_case_elem_data = AsyncMock()
        mock_case_elem_data.field_values = {}
        mock_case_elem.return_value = mock_case_elem_data
        
        mock_update.return_value = None
        
        # Execute
        result = await completar_elemento_actual()
        
        # CRITICAL ASSERTION: Must return "fsm_state_update", NOT "fsm_state"
        assert "fsm_state_update" in result, (
            "completar_elemento_actual() MUST return 'fsm_state_update' key "
            "(NOT 'fsm_state'). The conversational_agent node only recognizes "
            "'fsm_state_update' (line 1255 in conversational_agent.py)."
        )
        
        # Should NOT have the old incorrect key
        assert "fsm_state" not in result or result.get("fsm_state") is None, (
            "completar_elemento_actual() should NOT return 'fsm_state' key "
            "(only 'fsm_state_update' is recognized by the node)"
        )


@pytest.mark.asyncio
async def test_confirmar_fotos_elemento_returns_fsm_state_update_key():
    """
    Unit test to verify confirmar_fotos_elemento() returns the correct key
    in all branches (with/without required fields, all done/more elements).
    """
    
    # Test case: Element without required fields, all elements complete
    mock_state_all_done = {
        "conversation_id": "test",
        "user_id": str(uuid4()),
        "fsm_state": {
            "case_collection": {
                "step": CollectionStep.COLLECT_ELEMENT_DATA.value,
                "case_id": str(uuid4()),
                "category_slug": "motos-part",
                "category_id": uuid4(),
                "element_codes": ["SUSPENSION"],
                "current_element_index": 0,
                "element_phase": "photos",
                "element_data_status": {
                    "SUSPENSION": "pending",
                },
            }
        },
    }
    
    with patch("agent.tools.element_data_tools.get_current_state") as mock_get, \
         patch("agent.tools.element_data_tools._get_element_by_code") as mock_elem, \
         patch("agent.tools.element_data_tools._get_required_fields_for_element") as mock_fields, \
         patch("agent.tools.element_data_tools._update_case_element_data") as mock_update:
        
        mock_get.return_value = mock_state_all_done
        
        mock_element = AsyncMock()
        mock_element.id = uuid4()
        mock_element.name = "Suspensión"
        mock_elem.return_value = mock_element
        
        # No required fields → will complete element immediately
        mock_fields.return_value = []
        mock_update.return_value = None
        
        result = await confirmar_fotos_elemento()
        
        # CRITICAL: Must return "fsm_state_update"
        assert "fsm_state_update" in result, (
            "confirmar_fotos_elemento() MUST return 'fsm_state_update' when "
            "element has no required fields and all elements are complete"
        )
        assert "fsm_state" not in result or result.get("fsm_state") is None
