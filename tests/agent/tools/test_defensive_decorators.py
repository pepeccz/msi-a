"""
Test Phase 4: Defensive Tool Decorators Application

Tests that defensive decorators are correctly applied to high-risk tools:
- actualizar_datos_expediente: email, phone, DNI validation
- iniciar_expediente: state completeness validation

These tests verify the decorators PREVENT invalid data from reaching the database.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import agent.tools.case_tools as case_tools_module

# Access the underlying functions from LangChain @tool decorator
# The @tool decorator wraps the function in a StructuredTool, so we need .coroutine
actualizar_datos_expediente_func = case_tools_module.actualizar_datos_expediente.coroutine
iniciar_expediente_func = case_tools_module.iniciar_expediente.coroutine


class TestActualizarDatosExpediente:
    """Test defensive decorators on actualizar_datos_expediente."""
    
    @pytest.mark.asyncio
    async def test_invalid_email_rejected(self):
        """Email validation blocks invalid formats."""
        datos_personales = {
            "nombre": "Juan",
            "apellidos": "García",
            "dni_cif": "12345678Z",
            "email": "invalid-email",  # INVALID
            "domicilio_calle": "Calle Mayor 1",
            "domicilio_localidad": "Madrid",
            "domicilio_provincia": "Madrid",
            "domicilio_cp": "28001",
            "itv_nombre": "ITV Madrid",
        }
        
        with patch("agent.tools.case_tools.get_current_state") as mock_state:
            mock_state.return_value = {
                "fsm_state": {"case_id": "test-case-id"},
                "conversation_id": "test-conv",
            }
            
            result = await actualizar_datos_expediente_func(datos_personales=datos_personales)
        
        assert result["success"] is False
        assert "email inválido" in result["message"].lower()
        assert result["error_code"] == "INVALID_EMAIL"
    
    @pytest.mark.asyncio
    async def test_invalid_phone_rejected(self):
        """Phone validation blocks invalid formats."""
        datos_personales = {
            "nombre": "Juan",
            "apellidos": "García",
            "dni_cif": "12345678Z",
            "email": "juan@example.com",
            "telefono": "123",  # INVALID (too short)
            "domicilio_calle": "Calle Mayor 1",
            "domicilio_localidad": "Madrid",
            "domicilio_provincia": "Madrid",
            "domicilio_cp": "28001",
            "itv_nombre": "ITV Madrid",
        }
        
        with patch("agent.tools.case_tools.get_current_state") as mock_state:
            mock_state.return_value = {
                "fsm_state": {"case_id": "test-case-id"},
                "conversation_id": "test-conv",
            }
            
            result = await actualizar_datos_expediente_func(datos_personales=datos_personales)
        
        assert result["success"] is False
        assert "teléfono inválido" in result["message"].lower()
        assert result["error_code"] == "INVALID_PHONE"
    
    @pytest.mark.asyncio
    async def test_invalid_dni_rejected(self):
        """DNI validation blocks invalid formats (wrong check letter)."""
        datos_personales = {
            "nombre": "Juan",
            "apellidos": "García",
            "dni_cif": "12345678A",  # INVALID (check letter should be Z)
            "email": "juan@example.com",
            "domicilio_calle": "Calle Mayor 1",
            "domicilio_localidad": "Madrid",
            "domicilio_provincia": "Madrid",
            "domicilio_cp": "28001",
            "itv_nombre": "ITV Madrid",
        }
        
        with patch("agent.tools.case_tools.get_current_state") as mock_state:
            mock_state.return_value = {
                "fsm_state": {"case_id": "test-case-id"},
                "conversation_id": "test-conv",
            }
            
            result = await actualizar_datos_expediente_func(datos_personales=datos_personales)
        
        assert result["success"] is False
        assert "dni" in result["message"].lower() or "nie" in result["message"].lower()
        assert result["error_code"] == "INVALID_DNI"
    
    @pytest.mark.asyncio
    async def test_valid_data_passes_decorators(self):
        """Valid data passes all decorators and proceeds to implementation."""
        datos_personales = {
            "nombre": "Juan",
            "apellidos": "García",
            "dni_cif": "12345678Z",  # VALID
            "email": "juan@example.com",  # VALID
            "telefono": "612345678",  # VALID
            "domicilio_calle": "Calle Mayor 1",
            "domicilio_localidad": "Madrid",
            "domicilio_provincia": "Madrid",
            "domicilio_cp": "28001",
            "itv_nombre": "ITV Madrid",
        }
        
        # Mock the entire implementation to avoid DB calls
        with patch("agent.tools.case_tools.get_current_state") as mock_state, \
             patch("agent.tools.case_tools.get_case_fsm_state") as mock_case_state, \
             patch("agent.tools.case_tools.get_current_step") as mock_step, \
             patch("agent.tools.case_tools.get_async_session"):
            
            from agent.utils.fsm_compat import CollectionStep
            
            mock_state.return_value = {
                "fsm_state": {"case_id": "test-case-id"},
                "conversation_id": "test-conv",
            }
            mock_case_state.return_value = {"case_id": "test-case-id"}
            mock_step.return_value = CollectionStep.COLLECT_PERSONAL
            
            result = await actualizar_datos_expediente_func(datos_personales=datos_personales)
        
        # Should NOT fail validation
        # (may fail on actual implementation due to missing mocks, but validation passed)
        # Check that error is NOT validation-related
        if not result.get("success"):
            assert result.get("error_code") not in ["INVALID_EMAIL", "INVALID_PHONE", "INVALID_DNI"]


class TestIniciarExpediente:
    """Test defensive decorators on iniciar_expediente."""
    
    @pytest.mark.asyncio
    async def test_missing_categoria_slug_rejected(self):
        """State completeness validation blocks missing categoria_slug."""
        with patch("agent.tools.case_tools.get_current_state") as mock_state:
            mock_state.return_value = {
                # Missing "categoria_slug"
                "user_id": "test-user-id",
                "conversation_id": "test-conv",
            }
            
            result = await iniciar_expediente_func(
                categoria_vehiculo="motos-part",
                codigos_elementos=["ESCAPE"],
            )
        
        assert result["success"] is False
        assert "estado incompleto" in result["message"].lower()
        assert result["error_code"] == "INCOMPLETE_STATE"
        assert "categoria_slug" in result["context"]["missing_fields"]
    
    @pytest.mark.asyncio
    async def test_missing_user_id_rejected(self):
        """State completeness validation blocks missing user_id."""
        with patch("agent.tools.case_tools.get_current_state") as mock_state:
            mock_state.return_value = {
                "categoria_slug": "motos-part",
                # Missing "user_id"
                "conversation_id": "test-conv",
            }
            
            result = await iniciar_expediente_func(
                categoria_vehiculo="motos-part",
                codigos_elementos=["ESCAPE"],
            )
        
        assert result["success"] is False
        assert "estado incompleto" in result["message"].lower()
        assert result["error_code"] == "INCOMPLETE_STATE"
        assert "user_id" in result["context"]["missing_fields"]
    
    @pytest.mark.asyncio
    async def test_complete_state_passes_decorator(self):
        """Complete state passes validation and proceeds to implementation."""
        with patch("agent.tools.case_tools.get_current_state") as mock_state, \
             patch("agent.tools.case_tools.get_case_fsm_state") as mock_case_state, \
             patch("agent.tools.case_tools.get_current_step") as mock_step, \
             patch("agent.tools.case_tools._get_active_case_for_conversation") as mock_active_case, \
             patch("agent.tools.case_tools._get_category_id_by_slug") as mock_cat_id, \
             patch("agent.tools.case_tools._validate_element_codes_for_category") as mock_validate:
            
            from agent.utils.fsm_compat import CollectionStep
            
            # Complete state (has both required fields)
            mock_state.return_value = {
                "categoria_slug": "motos-part",
                "user_id": "test-user-id",
                "conversation_id": "test-conv",
                "fsm_state": {"step": "IDLE"},
            }
            mock_case_state.return_value = {}
            mock_step.return_value = CollectionStep.IDLE
            mock_active_case.return_value = None  # No active case
            mock_cat_id.return_value = "cat-uuid"
            mock_validate.return_value = (True, [], [], ["ESCAPE"], [])
            
            result = await iniciar_expediente_func(
                categoria_vehiculo="motos-part",
                codigos_elementos=["ESCAPE"],
                tarifa_calculada=350.0,
                tier_id="tier-uuid",
            )
        
        # Should NOT fail state validation
        # (may fail on actual implementation due to missing mocks, but validation passed)
        # Check that error is NOT validation-related
        if not result.get("success"):
            assert result.get("error_code") != "INCOMPLETE_STATE"


class TestPhase4Coverage:
    """Meta-tests to verify Phase 4 is fully implemented."""
    
    def test_actualizar_datos_has_defensive_checks(self):
        """Verify actualizar_datos_expediente has defensive validation code."""
        import inspect
        
        source = inspect.getsource(actualizar_datos_expediente_func)
        
        # Check for email validation
        assert "validate_email" in source
        assert "INVALID_EMAIL" in source
        
        # Check for phone validation
        assert "validate_phone" in source
        assert "INVALID_PHONE" in source
        
        # Check for DNI validation
        assert "validate_dni" in source
        assert "INVALID_DNI" in source
    
    def test_iniciar_expediente_has_defensive_checks(self):
        """Verify iniciar_expediente has defensive validation code."""
        import inspect
        
        source = inspect.getsource(iniciar_expediente_func)
        
        # Check for state completeness validation
        assert "check_state_completeness" in source
        assert "INCOMPLETE_STATE" in source
        assert "required_state" in source or "missing" in source
