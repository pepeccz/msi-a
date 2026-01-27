"""
Tests for element data collection tools.

These tests verify the behavior of tools used in the COLLECT_ELEMENT_DATA phase:
- obtener_campos_elemento
- guardar_datos_elemento
- confirmar_fotos_elemento
- completar_elemento_actual
- obtener_progreso_elementos
- confirmar_documentacion_base
- reenviar_imagenes_elemento
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import uuid

from agent.fsm.case_collection import CollectionStep


class TestObtenerCamposElemento:
    """Tests for obtener_campos_elemento tool."""

    @pytest.fixture
    def mock_state_in_collect_element_data(self):
        """Mock state in COLLECT_ELEMENT_DATA step, data phase."""
        return {
            "conversation_id": "test-conv-123",
            "fsm_state": {
                "case_collection": {
                    "step": CollectionStep.COLLECT_ELEMENT_DATA.value,
                    "case_id": str(uuid.uuid4()),
                    "category_id": str(uuid.uuid4()),
                    "element_codes": ["SUBCHASIS", "SUSP_TRAS"],
                    "current_element_index": 0,
                    "element_phase": "data",
                    "element_data_status": {"SUBCHASIS": "photos_done", "SUSP_TRAS": "pending"},
                }
            }
        }

    @pytest.fixture
    def mock_element(self):
        """Create a mock Element."""
        element = MagicMock()
        element.id = uuid.uuid4()
        element.name = "Subchasis"
        element.code = "SUBCHASIS"
        return element

    @pytest.fixture
    def mock_fields(self):
        """Create mock required fields."""
        field1 = MagicMock()
        field1.field_key = "descripcion_modificacion"
        field1.field_label = "En que consiste la modificacion"
        field1.field_type = "text"
        field1.is_required = True
        field1.options = None
        field1.example_value = "Acortado 50mm"
        field1.llm_instruction = "Pregunta que modificacion se realizo"
        field1.validation_rules = None
        field1.condition_field_id = None
        
        field2 = MagicMock()
        field2.field_key = "nueva_longitud_total"
        field2.field_label = "Nueva longitud total (mm)"
        field2.field_type = "number"
        field2.is_required = True
        field2.options = None
        field2.example_value = "2100"
        field2.llm_instruction = None
        field2.validation_rules = {"min": 100, "max": 5000}
        field2.condition_field_id = None
        
        return [field1, field2]

    @pytest.mark.asyncio
    async def test_returns_fields_from_database(
        self, mock_state_in_collect_element_data, mock_element, mock_fields
    ):
        """Should return actual fields from DB, not invented ones."""
        from agent.tools.element_data_tools import obtener_campos_elemento
        
        mock_case_element = MagicMock()
        mock_case_element.field_values = {}
        
        with patch("agent.state.helpers.get_current_state", return_value=mock_state_in_collect_element_data):
            with patch("agent.tools.element_data_tools._get_element_by_code", return_value=mock_element):
                with patch("agent.tools.element_data_tools._get_required_fields_for_element", return_value=mock_fields):
                    with patch("agent.tools.element_data_tools._get_or_create_case_element_data", return_value=mock_case_element):
                        result = await obtener_campos_elemento.ainvoke({})
                        
                        assert result["success"] is True
                        assert result["element_code"] == "SUBCHASIS"
                        assert len(result["fields"]) == 2
                        assert result["fields"][0]["field_key"] == "descripcion_modificacion"
                        assert result["fields"][1]["field_key"] == "nueva_longitud_total"

    @pytest.mark.asyncio
    async def test_fails_outside_collect_element_data(self):
        """Should fail if not in COLLECT_ELEMENT_DATA step."""
        from agent.tools.element_data_tools import obtener_campos_elemento
        
        wrong_step_state = {
            "fsm_state": {
                "case_collection": {
                    "step": CollectionStep.COLLECT_PERSONAL.value,
                    "case_id": str(uuid.uuid4()),
                }
            }
        }
        
        with patch("agent.state.helpers.get_current_state", return_value=wrong_step_state):
            result = await obtener_campos_elemento.ainvoke({})
            
            assert result["success"] is False
            assert "COLLECT_ELEMENT_DATA" in result["error"]

    @pytest.mark.asyncio
    async def test_fails_with_no_state(self):
        """Should fail if no conversation state."""
        from agent.tools.element_data_tools import obtener_campos_elemento
        
        with patch("agent.state.helpers.get_current_state", return_value=None):
            result = await obtener_campos_elemento.ainvoke({})
            
            assert result["success"] is False
            assert "estado" in result["error"].lower()


class TestConfirmarFotosElemento:
    """Tests for confirmar_fotos_elemento tool."""

    @pytest.fixture
    def mock_state_photos_phase(self):
        """Mock state in photos phase."""
        return {
            "fsm_state": {
                "case_collection": {
                    "step": CollectionStep.COLLECT_ELEMENT_DATA.value,
                    "case_id": str(uuid.uuid4()),
                    "category_id": str(uuid.uuid4()),
                    "element_codes": ["SUBCHASIS"],
                    "current_element_index": 0,
                    "element_phase": "photos",
                    "element_data_status": {"SUBCHASIS": "pending"},
                }
            }
        }

    @pytest.mark.asyncio
    async def test_transitions_to_data_phase_when_has_fields(self, mock_state_photos_phase):
        """Should transition to 'data' phase if element has required fields."""
        from agent.tools.element_data_tools import confirmar_fotos_elemento
        
        mock_element = MagicMock()
        mock_element.id = uuid.uuid4()
        mock_element.name = "Subchasis"
        
        mock_fields = [MagicMock(field_key="test", is_required=True)]
        mock_fields[0].field_label = "Test Field"
        mock_fields[0].field_type = "text"
        mock_fields[0].example_value = None
        mock_fields[0].llm_instruction = None
        
        with patch("agent.state.helpers.get_current_state", return_value=mock_state_photos_phase):
            with patch("agent.tools.element_data_tools._get_element_by_code", return_value=mock_element):
                with patch("agent.tools.element_data_tools._get_required_fields_for_element", return_value=mock_fields):
                    with patch("agent.tools.element_data_tools._update_case_element_data"):
                        result = await confirmar_fotos_elemento.ainvoke({})
                        
                        assert result["success"] is True
                        assert result["photos_confirmed"] is True
                        assert result["has_required_fields"] is True
                        assert result["next_phase"] == "data"

    @pytest.mark.asyncio
    async def test_completes_element_when_no_fields(self, mock_state_photos_phase):
        """Should mark element complete if no required fields."""
        from agent.tools.element_data_tools import confirmar_fotos_elemento
        
        mock_element = MagicMock()
        mock_element.id = uuid.uuid4()
        mock_element.name = "Subchasis"
        
        with patch("agent.state.helpers.get_current_state", return_value=mock_state_photos_phase):
            with patch("agent.tools.element_data_tools._get_element_by_code", return_value=mock_element):
                with patch("agent.tools.element_data_tools._get_required_fields_for_element", return_value=[]):
                    with patch("agent.tools.element_data_tools._update_case_element_data"):
                        result = await confirmar_fotos_elemento.ainvoke({})
                        
                        assert result["success"] is True
                        assert result["has_required_fields"] is False
                        assert result["element_complete"] is True

    @pytest.mark.asyncio
    async def test_fails_in_data_phase(self):
        """Should fail if already in data phase."""
        from agent.tools.element_data_tools import confirmar_fotos_elemento
        
        state_data_phase = {
            "fsm_state": {
                "case_collection": {
                    "step": CollectionStep.COLLECT_ELEMENT_DATA.value,
                    "case_id": str(uuid.uuid4()),
                    "category_id": str(uuid.uuid4()),
                    "element_codes": ["SUBCHASIS"],
                    "current_element_index": 0,
                    "element_phase": "data",  # Already in data phase
                    "element_data_status": {"SUBCHASIS": "photos_done"},
                }
            }
        }
        
        with patch("agent.state.helpers.get_current_state", return_value=state_data_phase):
            result = await confirmar_fotos_elemento.ainvoke({})
            
            assert result["success"] is False
            assert "data" in result["error"]


class TestGuardarDatosElemento:
    """Tests for guardar_datos_elemento tool."""

    @pytest.fixture
    def mock_state_data_phase(self):
        """Mock state in data phase."""
        return {
            "fsm_state": {
                "case_collection": {
                    "step": CollectionStep.COLLECT_ELEMENT_DATA.value,
                    "case_id": str(uuid.uuid4()),
                    "category_id": str(uuid.uuid4()),
                    "element_codes": ["SUBCHASIS"],
                    "current_element_index": 0,
                    "element_phase": "data",
                    "element_data_status": {"SUBCHASIS": "photos_done"},
                }
            }
        }

    @pytest.mark.asyncio
    async def test_saves_valid_data(self, mock_state_data_phase):
        """Should save valid field data."""
        from agent.tools.element_data_tools import guardar_datos_elemento
        
        mock_element = MagicMock()
        mock_element.id = uuid.uuid4()
        
        mock_field = MagicMock()
        mock_field.field_key = "descripcion_modificacion"
        mock_field.field_label = "Descripcion"
        mock_field.field_type = "text"
        mock_field.is_required = True
        mock_field.validation_rules = None
        mock_field.condition_field_id = None
        
        mock_case_element = MagicMock()
        mock_case_element.field_values = {}
        
        with patch("agent.state.helpers.get_current_state", return_value=mock_state_data_phase):
            with patch("agent.tools.element_data_tools._get_element_by_code", return_value=mock_element):
                with patch("agent.tools.element_data_tools._get_required_fields_for_element", return_value=[mock_field]):
                    with patch("agent.tools.element_data_tools._get_or_create_case_element_data", return_value=mock_case_element):
                        with patch("agent.tools.element_data_tools._update_case_element_data"):
                            result = await guardar_datos_elemento.ainvoke({
                                "datos": {"descripcion_modificacion": "Acortado 50mm"}
                            })
                            
                            assert result["success"] is True
                            assert result["saved_count"] == 1

    @pytest.mark.asyncio
    async def test_fails_in_photos_phase(self):
        """Should fail if in photos phase."""
        from agent.tools.element_data_tools import guardar_datos_elemento
        
        state_photos_phase = {
            "fsm_state": {
                "case_collection": {
                    "step": CollectionStep.COLLECT_ELEMENT_DATA.value,
                    "case_id": str(uuid.uuid4()),
                    "category_id": str(uuid.uuid4()),
                    "element_codes": ["SUBCHASIS"],
                    "current_element_index": 0,
                    "element_phase": "photos",  # Wrong phase
                    "element_data_status": {"SUBCHASIS": "pending"},
                }
            }
        }
        
        with patch("agent.state.helpers.get_current_state", return_value=state_photos_phase):
            result = await guardar_datos_elemento.ainvoke({
                "datos": {"test": "value"}
            })
            
            assert result["success"] is False
            assert "photos" in result["error"]


class TestConfirmarDocumentacionBase:
    """Tests for confirmar_documentacion_base tool."""

    @pytest.fixture
    def mock_state_collect_base_docs(self):
        """Mock state in COLLECT_BASE_DOCS step."""
        return {
            "fsm_state": {
                "case_collection": {
                    "step": CollectionStep.COLLECT_BASE_DOCS.value,
                    "case_id": str(uuid.uuid4()),
                    "base_docs_received": False,
                }
            }
        }

    @pytest.mark.asyncio
    async def test_transitions_to_collect_personal(self, mock_state_collect_base_docs):
        """Should transition to COLLECT_PERSONAL after confirming docs."""
        from agent.tools.element_data_tools import confirmar_documentacion_base
        
        with patch("agent.state.helpers.get_current_state", return_value=mock_state_collect_base_docs):
            result = await confirmar_documentacion_base.ainvoke({})
            
            assert result["success"] is True
            assert result["base_docs_confirmed"] is True
            assert result["next_step"] == "COLLECT_PERSONAL"

    @pytest.mark.asyncio
    async def test_fails_outside_collect_base_docs(self):
        """Should fail if not in COLLECT_BASE_DOCS step."""
        from agent.tools.element_data_tools import confirmar_documentacion_base
        
        wrong_step_state = {
            "fsm_state": {
                "case_collection": {
                    "step": CollectionStep.COLLECT_ELEMENT_DATA.value,
                }
            }
        }
        
        with patch("agent.state.helpers.get_current_state", return_value=wrong_step_state):
            result = await confirmar_documentacion_base.ainvoke({})
            
            assert result["success"] is False
            assert "COLLECT_BASE_DOCS" in result["error"]


class TestImageElementCodeTagging:
    """Tests for image element_code tagging in main.py."""

    @pytest.mark.asyncio
    async def test_save_images_accepts_element_code_parameter(self):
        """save_images_silently should accept element_code parameter."""
        from agent.main import save_images_silently
        import inspect
        
        sig = inspect.signature(save_images_silently)
        params = list(sig.parameters.keys())
        
        assert "element_code" in params, \
            "save_images_silently should have element_code parameter"

    @pytest.mark.asyncio
    async def test_save_images_with_element_code(self):
        """Images saved during COLLECT_ELEMENT_DATA should have element_code."""
        from agent.main import save_images_silently
        
        case_id = str(uuid.uuid4())
        element_code = "SUBCHASIS"
        
        mock_attachment = {"data_url": "https://example.com/image.jpg"}
        
        with patch("agent.main.get_chatwoot_image_service") as mock_service:
            with patch("agent.main.get_case_image_count", return_value=0):
                with patch("agent.main.get_async_session") as mock_session:
                    # Setup mocks
                    mock_download = {
                        "stored_filename": "test-uuid.jpg",
                        "mime_type": "image/jpeg",
                        "file_size": 1024,
                    }
                    mock_service.return_value.download_image = AsyncMock(return_value=mock_download)
                    
                    session_instance = AsyncMock()
                    mock_session.return_value.__aenter__ = AsyncMock(return_value=session_instance)
                    mock_session.return_value.__aexit__ = AsyncMock(return_value=None)
                    
                    saved, failed = await save_images_silently(
                        case_id=case_id,
                        conversation_id="123",
                        attachments=[mock_attachment],
                        user_phone="+34123456789",
                        element_code=element_code,
                    )
                    
                    assert saved == 1
                    assert failed == 0
                    
                    # Verify CaseImage was created with element_code
                    session_instance.add.assert_called_once()
                    added_image = session_instance.add.call_args[0][0]
                    assert added_image.element_code == element_code

    @pytest.mark.asyncio
    async def test_save_images_without_element_code(self):
        """Images from COLLECT_BASE_DOCS should have element_code=None."""
        from agent.main import save_images_silently
        
        case_id = str(uuid.uuid4())
        
        with patch("agent.main.get_chatwoot_image_service") as mock_service:
            with patch("agent.main.get_case_image_count", return_value=0):
                with patch("agent.main.get_async_session") as mock_session:
                    mock_download = {
                        "stored_filename": "doc-uuid.jpg",
                        "mime_type": "image/jpeg",
                    }
                    mock_service.return_value.download_image = AsyncMock(return_value=mock_download)
                    
                    session_instance = AsyncMock()
                    mock_session.return_value.__aenter__ = AsyncMock(return_value=session_instance)
                    mock_session.return_value.__aexit__ = AsyncMock(return_value=None)
                    
                    saved, failed = await save_images_silently(
                        case_id=case_id,
                        conversation_id="123",
                        attachments=[{"data_url": "https://example.com/doc.jpg"}],
                        user_phone="+34123456789",
                        element_code=None,  # Base docs have no element
                    )
                    
                    added_image = session_instance.add.call_args[0][0]
                    assert added_image.element_code is None
