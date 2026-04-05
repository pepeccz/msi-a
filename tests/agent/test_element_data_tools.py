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

from agent.utils.expediente_types import CollectionStep


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
        
        with patch("agent.tools.element_data_tools.get_current_state", return_value=mock_state_in_collect_element_data):
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
        
        with patch("agent.tools.element_data_tools.get_current_state", return_value=wrong_step_state):
            result = await obtener_campos_elemento.ainvoke({})
            
            assert result["success"] is False
            assert "COLLECT_ELEMENT_DATA" in result["error"]

    @pytest.mark.asyncio
    async def test_fails_with_no_state(self):
        """Should fail if no conversation state."""
        from agent.tools.element_data_tools import obtener_campos_elemento
        
        with patch("agent.tools.element_data_tools.get_current_state", return_value=None):
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
        
        case_state = mock_state_photos_phase["fsm_state"]["case_collection"]
        with patch("agent.tools.element_data_tools.get_current_state", return_value=mock_state_photos_phase):
            with patch("agent.tools.element_data_tools.get_case_fsm_state", return_value=case_state):
                with patch("agent.tools.element_data_tools.get_current_step", return_value=CollectionStep.COLLECT_ELEMENT_DATA):
                    with patch("agent.tools.element_data_tools.get_current_element_code", return_value="SUBCHASIS"):
                        with patch("agent.tools.element_data_tools.get_element_phase", return_value="photos"):
                            with patch("agent.tools.element_data_tools._get_element_image_count", new_callable=AsyncMock, return_value=1):
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
        
        case_state = mock_state_photos_phase["fsm_state"]["case_collection"]
        with patch("agent.tools.element_data_tools.get_current_state", return_value=mock_state_photos_phase):
            with patch("agent.tools.element_data_tools.get_case_fsm_state", return_value=case_state):
                with patch("agent.tools.element_data_tools.get_current_step", return_value=CollectionStep.COLLECT_ELEMENT_DATA):
                    with patch("agent.tools.element_data_tools.get_current_element_code", return_value="SUBCHASIS"):
                        with patch("agent.tools.element_data_tools.get_element_phase", return_value="photos"):
                            with patch("agent.tools.element_data_tools._get_element_image_count", new_callable=AsyncMock, return_value=1):
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
        
        case_state = state_data_phase["fsm_state"]["case_collection"]
        with patch("agent.tools.element_data_tools.get_current_state", return_value=state_data_phase):
            with patch("agent.tools.element_data_tools.get_case_fsm_state", return_value=case_state):
                with patch("agent.tools.element_data_tools.get_current_step", return_value=CollectionStep.COLLECT_ELEMENT_DATA):
                    with patch("agent.tools.element_data_tools.get_current_element_code", return_value="SUBCHASIS"):
                        with patch("agent.tools.element_data_tools.get_element_phase", return_value="data"):
                            with patch("agent.tools.element_data_tools.is_current_element_photos_done", return_value=False):
                                result = await confirmar_fotos_elemento.ainvoke({})
                                
                                assert result["success"] is False
                                assert "data" in result["error"]

    @pytest.mark.asyncio
    async def test_insists_when_no_photos_but_user_confirms(self, mock_state_photos_phase):
        """Should return needs_photos=True and NOT escalate when user confirms but 0 images exist.

        Two-phase poll: both asyncio.sleep calls are made (phase-1 and phase-2 retry)
        because image count stays 0 throughout. Image count is checked 3 times total:
        1. Initial check (before any wait)
        2. After phase-1 wait
        3. After phase-2 retry wait
        """
        from agent.tools.element_data_tools import confirmar_fotos_elemento

        case_state = mock_state_photos_phase["fsm_state"]["case_collection"]
        with patch("agent.tools.element_data_tools.get_current_state", return_value=mock_state_photos_phase):
            with patch("agent.tools.element_data_tools.get_case_fsm_state", return_value=case_state):
                with patch("agent.tools.element_data_tools.get_current_step", return_value=CollectionStep.COLLECT_ELEMENT_DATA):
                    with patch(
                        "agent.tools.element_data_tools._get_element_image_count",
                        new_callable=AsyncMock,
                        return_value=0,
                    ) as mock_image_count:
                        with patch(
                            "agent.tools.element_data_tools.asyncio.sleep",
                            new_callable=AsyncMock,
                        ) as mock_sleep:
                            with patch(
                                "agent.tools.element_data_tools._escalate_image_receipt_issue",
                                new_callable=AsyncMock,
                            ) as mock_escalate:
                                result = await confirmar_fotos_elemento.ainvoke(
                                    {"usuario_confirma": True}
                                )

                                assert result["success"] is False
                                assert result["needs_photos"] is True
                                # Two-phase poll: sleep is called twice (phase-1 + phase-2 retry)
                                assert mock_sleep.await_count == 2
                                mock_escalate.assert_not_called()
                                # Image count checked 3 times: initial + after phase-1 + after phase-2
                                assert mock_image_count.await_count == 3

    @pytest.mark.asyncio
    async def test_does_not_advance_phase_when_no_photos(self, mock_state_photos_phase):
        """Should NOT include element_phase in result when no photos exist after wait."""
        from agent.tools.element_data_tools import confirmar_fotos_elemento

        case_state = mock_state_photos_phase["fsm_state"]["case_collection"]
        with patch("agent.tools.element_data_tools.get_current_state", return_value=mock_state_photos_phase):
            with patch("agent.tools.element_data_tools.get_case_fsm_state", return_value=case_state):
                with patch("agent.tools.element_data_tools.get_current_step", return_value=CollectionStep.COLLECT_ELEMENT_DATA):
                    with patch(
                        "agent.tools.element_data_tools._get_element_image_count",
                        new_callable=AsyncMock,
                        return_value=0,
                    ):
                        with patch(
                            "agent.tools.element_data_tools.asyncio.sleep",
                            new_callable=AsyncMock,
                        ):
                            result = await confirmar_fotos_elemento.ainvoke(
                                {"usuario_confirma": True}
                            )

                            assert "element_phase" not in result

    @pytest.mark.asyncio
    async def test_advances_normally_when_photos_exist(self, mock_state_photos_phase):
        """Should return success=True and not set needs_photos when photos are present."""
        from agent.tools.element_data_tools import confirmar_fotos_elemento

        mock_element = MagicMock()
        mock_element.id = uuid.uuid4()
        mock_element.name = "Subchasis"

        mock_fields = [MagicMock(field_key="test", is_required=True)]
        mock_fields[0].field_label = "Test Field"
        mock_fields[0].field_type = "text"
        mock_fields[0].example_value = None
        mock_fields[0].llm_instruction = None

        case_state = mock_state_photos_phase["fsm_state"]["case_collection"]
        with patch("agent.tools.element_data_tools.get_current_state", return_value=mock_state_photos_phase):
            with patch("agent.tools.element_data_tools.get_case_fsm_state", return_value=case_state):
                with patch("agent.tools.element_data_tools.get_current_step", return_value=CollectionStep.COLLECT_ELEMENT_DATA):
                    with patch(
                        "agent.tools.element_data_tools._get_element_image_count",
                        new_callable=AsyncMock,
                        return_value=2,
                    ):
                        with patch(
                            "agent.tools.element_data_tools.asyncio.sleep",
                            new_callable=AsyncMock,
                        ) as mock_sleep:
                            with patch(
                                "agent.tools.element_data_tools._get_element_by_code",
                                return_value=mock_element,
                            ):
                                with patch(
                                    "agent.tools.element_data_tools._get_required_fields_for_element",
                                    return_value=mock_fields,
                                ):
                                    with patch("agent.tools.element_data_tools._update_case_element_data"):
                                        result = await confirmar_fotos_elemento.ainvoke({})

                                        assert result["success"] is True
                                        assert result.get("needs_photos") is not True
                                        # Sleep should NOT be called when images exist
                                        mock_sleep.assert_not_awaited()


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
        
        with patch("agent.tools.element_data_tools.get_current_state", return_value=mock_state_data_phase):
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
        
        with patch("agent.tools.element_data_tools.get_current_state", return_value=state_photos_phase):
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
        
        with patch("agent.tools.element_data_tools.get_current_state", return_value=mock_state_collect_base_docs):
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
        
        with patch("agent.tools.element_data_tools.get_current_state", return_value=wrong_step_state):
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


# =============================================================================
# TASK-4.4: Unit tests for fuzzy field mapping (R3)
# =============================================================================


class TestLcpLength:
    """Tests for the _lcp_length() helper function."""

    def test_lcp_length_basic_common_prefix(self):
        """
        _lcp_length("placa_solar", "placa_solar_potencia") must return 11
        (the length of the shared prefix "placa_solar").
        """
        from agent.tools.element_data_tools import _lcp_length

        result = _lcp_length("placa_solar", "placa_solar_potencia")
        assert result == 11, f"Expected 11, got {result}"

    def test_lcp_length_no_common_prefix(self):
        """
        Strings with no common prefix must return 0.
        """
        from agent.tools.element_data_tools import _lcp_length

        result = _lcp_length("marca", "ubicacion")
        assert result == 0, f"Expected 0, got {result}"

    def test_lcp_length_identical_strings(self):
        """
        Identical strings must return len(string).
        """
        from agent.tools.element_data_tools import _lcp_length

        s = "descripcion_modificacion"
        result = _lcp_length(s, s)
        assert result == len(s), f"Expected {len(s)}, got {result}"

    def test_lcp_length_empty_strings(self):
        """
        Empty strings must return 0.
        """
        from agent.tools.element_data_tools import _lcp_length

        assert _lcp_length("", "") == 0
        assert _lcp_length("abc", "") == 0
        assert _lcp_length("", "abc") == 0


class TestFuzzyFieldMappingBehavior:
    """
    Tests for the fuzzy-matching branch in guardar_datos_elemento (R3).

    Verifies:
    - Shadow log fires on ambiguous matches regardless of strict_mode
    - Soft mode (flag=False) uses LCP winner
    - Strict mode (flag=True) returns status="ambiguous"
    """

    @pytest.fixture
    def mock_state_data_phase(self):
        """Mock state in COLLECT_ELEMENT_DATA, data phase.

        Includes both legacy fsm_state AND mode_context/current_mode so that
        _get_mode_context() in element_data_tools reconstructs the correct
        CollectionStep (COLLECT_ELEMENT_DATA) when it calls get_current_state().
        """
        _case_id = str(uuid.uuid4())
        _category_id = str(uuid.uuid4())
        return {
            "current_mode": "EXPEDIENTE_MODE",
            "mode_context": {
                "expediente_sub_mode": "collect_element_data",
                "case_id": _case_id,
                "category_id": _category_id,
                "element_codes": ["PLACA_SOLAR"],
                "current_element_index": 0,
                "element_phase": "data",
                "element_data_status": {"PLACA_SOLAR": "photos_done"},
            },
            "fsm_state": {
                "case_collection": {
                    "step": "collect_element_data",
                    "case_id": _case_id,
                    "category_id": _category_id,
                    "element_codes": ["PLACA_SOLAR"],
                    "current_element_index": 0,
                    "element_phase": "data",
                    "element_data_status": {"PLACA_SOLAR": "photos_done"},
                }
            },
        }

    @pytest.fixture
    def mock_ambiguous_fields(self):
        """
        Two fields that both match the substring 'placa' — triggers ambiguous path.
        field_keys: placa_solar_potencia_w, placa_solar_marca
        input: "placa" → matches both.
        """
        field1 = MagicMock()
        field1.field_key = "placa_solar_potencia_w"
        field1.field_label = "Potencia de la placa (W)"
        field1.field_type = "number"
        field1.is_required = True
        field1.options = None
        field1.example_value = "200"
        field1.llm_instruction = "Indica la potencia"
        field1.validation_rules = None
        field1.condition_field_id = None

        field2 = MagicMock()
        field2.field_key = "placa_solar_marca"
        field2.field_label = "Marca de la placa"
        field2.field_type = "text"
        field2.is_required = False
        field2.options = None
        field2.example_value = None
        field2.llm_instruction = None
        field2.validation_rules = None
        field2.condition_field_id = None

        return [field1, field2]

    @pytest.mark.asyncio
    async def test_ambiguous_shadow_log_fires(
        self, mock_state_data_phase, mock_ambiguous_fields
    ):
        """
        When candidates > 1 exist, logger.warning must be called with
        event key 'expediente_field_mapping_ambiguous' regardless of strict_mode flag.
        """
        from agent.tools.element_data_tools import guardar_datos_elemento

        mock_element = MagicMock()
        mock_element.id = uuid.uuid4()
        mock_element.name = "Placa solar"

        mock_case_element = MagicMock()
        mock_case_element.field_values = {}

        # Soft mode (default) — flag=False
        mock_settings = MagicMock()
        mock_settings.EXPEDIENTE_STRICT_FIELD_MAPPING = False

        with patch(
            "agent.tools.element_data_tools.get_current_state",
            return_value=mock_state_data_phase,
        ):
            with patch(
                "agent.tools.element_data_tools._get_element_by_code",
                return_value=mock_element,
            ):
                with patch(
                    "agent.tools.element_data_tools._get_required_fields_for_element",
                    return_value=mock_ambiguous_fields,
                ):
                    with patch(
                        "agent.tools.element_data_tools._get_or_create_case_element_data",
                        return_value=mock_case_element,
                    ):
                        with patch(
                            "agent.tools.element_data_tools._update_case_element_data",
                        ):
                            with patch(
                                "agent.tools.element_data_tools.get_settings",
                                return_value=mock_settings,
                            ):
                                with patch(
                                    "agent.tools.element_data_tools.logger"
                                ) as mock_logger:
                                    # "placa" is a substring of both field keys
                                    await guardar_datos_elemento.ainvoke(
                                        {"datos": {"placa": "200"}}
                                    )

                                    # Shadow log must fire
                                    warning_calls = [
                                        str(call)
                                        for call in mock_logger.warning.call_args_list
                                    ]
                                    assert any(
                                        "expediente_field_mapping_ambiguous" in c
                                        for c in warning_calls
                                    ), (
                                        f"Expected 'expediente_field_mapping_ambiguous' warning. "
                                        f"Actual warning calls: {warning_calls}"
                                    )

    @pytest.mark.asyncio
    async def test_soft_mode_uses_lcp_winner_when_ambiguous(
        self, mock_state_data_phase, mock_ambiguous_fields
    ):
        """
        When EXPEDIENTE_STRICT_FIELD_MAPPING=False and candidates > 1,
        the tool must select the LCP winner and save successfully
        (not return ambiguous/failure).

        Input "placa_solar_p" is a longer prefix of "placa_solar_potencia_w"
        than "placa_solar_marca", so potencia wins.
        """
        from agent.tools.element_data_tools import guardar_datos_elemento

        mock_element = MagicMock()
        mock_element.id = uuid.uuid4()
        mock_element.name = "Placa solar"

        mock_case_element = MagicMock()
        mock_case_element.field_values = {}

        mock_settings = MagicMock()
        mock_settings.EXPEDIENTE_STRICT_FIELD_MAPPING = False

        with patch(
            "agent.tools.element_data_tools.get_current_state",
            return_value=mock_state_data_phase,
        ):
            with patch(
                "agent.tools.element_data_tools._get_element_by_code",
                return_value=mock_element,
            ):
                with patch(
                    "agent.tools.element_data_tools._get_required_fields_for_element",
                    return_value=mock_ambiguous_fields,
                ):
                    with patch(
                        "agent.tools.element_data_tools._get_or_create_case_element_data",
                        return_value=mock_case_element,
                    ):
                        with patch(
                            "agent.tools.element_data_tools._update_case_element_data"
                        ):
                            with patch(
                                "agent.tools.element_data_tools.get_settings",
                                return_value=mock_settings,
                            ):
                                # "placa_solar_p" is a longer common prefix with
                                # "placa_solar_potencia_w" than with "placa_solar_marca"
                                result = await guardar_datos_elemento.ainvoke(
                                    {"datos": {"placa_solar_p": 200}}
                                )

                                # In soft mode, LCP winner is selected → saved
                                # The result must NOT have status="ambiguous" for this field
                                ambiguous_results = [
                                    r
                                    for r in result.get("results", [])
                                    if r.get("status") == "ambiguous"
                                ]
                                assert len(ambiguous_results) == 0, (
                                    f"Soft mode should not return ambiguous, got: {result}"
                                )

    @pytest.mark.asyncio
    async def test_strict_mode_returns_ambiguous_when_candidates_gt_1(
        self, mock_state_data_phase, mock_ambiguous_fields
    ):
        """
        When EXPEDIENTE_STRICT_FIELD_MAPPING=True and candidates > 1,
        the tool MUST return status='ambiguous' and success=False.
        """
        from agent.tools.element_data_tools import guardar_datos_elemento

        mock_element = MagicMock()
        mock_element.id = uuid.uuid4()
        mock_element.name = "Placa solar"

        mock_case_element = MagicMock()
        mock_case_element.field_values = {}

        mock_settings = MagicMock()
        mock_settings.EXPEDIENTE_STRICT_FIELD_MAPPING = True

        with patch(
            "agent.tools.element_data_tools.get_current_state",
            return_value=mock_state_data_phase,
        ):
            with patch(
                "agent.tools.element_data_tools._get_element_by_code",
                return_value=mock_element,
            ):
                with patch(
                    "agent.tools.element_data_tools._get_required_fields_for_element",
                    return_value=mock_ambiguous_fields,
                ):
                    with patch(
                        "agent.tools.element_data_tools._get_or_create_case_element_data",
                        return_value=mock_case_element,
                    ):
                        with patch(
                            "agent.tools.element_data_tools._update_case_element_data"
                        ):
                            with patch(
                                "agent.tools.element_data_tools.get_settings",
                                return_value=mock_settings,
                            ):
                                # "placa" matches both fields — triggers ambiguous path
                                result = await guardar_datos_elemento.ainvoke(
                                    {"datos": {"placa": 200}}
                                )

                                # In strict mode: must return ambiguous result
                                ambiguous_results = [
                                    r
                                    for r in result.get("results", [])
                                    if r.get("status") == "ambiguous"
                                ]
                                assert len(ambiguous_results) >= 1, (
                                    f"Expected ambiguous result in strict mode. Got: {result}"
                                )
                                # Overall success must be False
                                assert result["success"] is False, (
                                    f"Expected success=False in strict mode. Got: {result}"
                                )


class TestGuardarDatosFieldNotFound:
    """Tests for guardar_datos_elemento field-not-found with valid alternatives."""

    @pytest.fixture
    def mock_state_data_phase(self):
        _case_id = str(uuid.uuid4())
        _category_id = str(uuid.uuid4())
        return {
            "current_mode": "EXPEDIENTE_MODE",
            "mode_context": {
                "expediente_sub_mode": "collect_element_data",
                "case_id": _case_id,
                "category_id": _category_id,
                "element_codes": ["PLACA_SOLAR"],
                "current_element_index": 0,
                "element_phase": "data",
                "element_data_status": {"PLACA_SOLAR": "photos_done"},
            },
            "fsm_state": {
                "case_collection": {
                    "step": "collect_element_data",
                    "case_id": _case_id,
                    "category_id": _category_id,
                    "element_codes": ["PLACA_SOLAR"],
                    "current_element_index": 0,
                    "element_phase": "data",
                    "element_data_status": {"PLACA_SOLAR": "photos_done"},
                }
            },
        }

    @pytest.fixture
    def mock_element(self):
        el = MagicMock()
        el.id = uuid.uuid4()
        el.name = "Placa Solar"
        el.code = "PLACA_SOLAR"
        return el

    @pytest.fixture
    def mock_fields(self):
        f1 = MagicMock()
        f1.field_key = "marca_placa"
        f1.field_label = "Marca placa"
        f1.field_type = "text"
        f1.is_required = True
        f1.validation_rules = None
        f1.condition_field_id = None

        f2 = MagicMock()
        f2.field_key = "potencia_wp"
        f2.field_label = "Potencia Wp"
        f2.field_type = "number"
        f2.is_required = True
        f2.validation_rules = None
        f2.condition_field_id = None

        return [f1, f2]

    @pytest.mark.asyncio
    async def test_ignored_field_includes_valid_keys(
        self, mock_state_data_phase, mock_element, mock_fields
    ):
        """Ignored field entry MUST include valid_field_keys list."""
        from agent.tools.element_data_tools import guardar_datos_elemento

        mock_case_element = MagicMock()
        mock_case_element.field_values = {}

        with patch("agent.tools.element_data_tools.get_current_state", return_value=mock_state_data_phase):
            with patch("agent.tools.element_data_tools._get_element_by_code", return_value=mock_element):
                with patch("agent.tools.element_data_tools._get_required_fields_for_element", return_value=mock_fields):
                    with patch("agent.tools.element_data_tools._get_or_create_case_element_data", return_value=mock_case_element):
                        result = await guardar_datos_elemento.ainvoke(
                            {"datos": {"campo_inventado": "valor"}}
                        )

                        ignored = [r for r in result.get("results", []) if r["status"] == "ignored"]
                        assert len(ignored) == 1
                        assert "valid_field_keys" in ignored[0]
                        assert ignored[0]["valid_field_keys"] == ["marca_placa", "potencia_wp"]

    @pytest.mark.asyncio
    async def test_ignored_field_message_lists_alternatives(
        self, mock_state_data_phase, mock_element, mock_fields
    ):
        """Ignored field message MUST contain all valid field_key names."""
        from agent.tools.element_data_tools import guardar_datos_elemento

        mock_case_element = MagicMock()
        mock_case_element.field_values = {}

        with patch("agent.tools.element_data_tools.get_current_state", return_value=mock_state_data_phase):
            with patch("agent.tools.element_data_tools._get_element_by_code", return_value=mock_element):
                with patch("agent.tools.element_data_tools._get_required_fields_for_element", return_value=mock_fields):
                    with patch("agent.tools.element_data_tools._get_or_create_case_element_data", return_value=mock_case_element):
                        result = await guardar_datos_elemento.ainvoke(
                            {"datos": {"campo_inventado": "valor"}}
                        )

                        ignored = [r for r in result.get("results", []) if r["status"] == "ignored"]
                        assert "marca_placa" in ignored[0]["message"]
                        assert "potencia_wp" in ignored[0]["message"]


class TestGuardarDatosEmptyDatos:
    """Tests for guardar_datos_elemento with empty datos dict."""

    @pytest.fixture
    def mock_state_data_phase(self):
        _case_id = str(uuid.uuid4())
        _category_id = str(uuid.uuid4())
        return {
            "current_mode": "EXPEDIENTE_MODE",
            "mode_context": {
                "expediente_sub_mode": "collect_element_data",
                "case_id": _case_id,
                "category_id": _category_id,
                "element_codes": ["PLACA_SOLAR"],
                "current_element_index": 0,
                "element_phase": "data",
                "element_data_status": {"PLACA_SOLAR": "photos_done"},
            },
            "fsm_state": {
                "case_collection": {
                    "step": "collect_element_data",
                    "case_id": _case_id,
                    "category_id": _category_id,
                    "element_codes": ["PLACA_SOLAR"],
                    "current_element_index": 0,
                    "element_phase": "data",
                    "element_data_status": {"PLACA_SOLAR": "photos_done"},
                }
            },
        }

    @pytest.fixture
    def mock_element(self):
        el = MagicMock()
        el.id = uuid.uuid4()
        el.name = "Placa Solar"
        el.code = "PLACA_SOLAR"
        return el

    def _make_field(self, key, label, ftype="text", condition_field_id=None):
        f = MagicMock()
        f.field_key = key
        f.field_label = label
        f.field_type = ftype
        f.is_required = True
        f.validation_rules = None
        f.condition_field_id = condition_field_id
        return f

    @pytest.mark.asyncio
    async def test_empty_dict_returns_pending_fields(
        self, mock_state_data_phase, mock_element
    ):
        """Empty datos MUST return pending_fields with field info."""
        from agent.tools.element_data_tools import guardar_datos_elemento

        fields = [
            self._make_field("marca_placa", "Marca placa", "text"),
            self._make_field("potencia_wp", "Potencia Wp", "number"),
            self._make_field("tipo_celda", "Tipo celda", "select"),
        ]
        mock_case_element = MagicMock()
        mock_case_element.field_values = {}

        with patch("agent.tools.element_data_tools.get_current_state", return_value=mock_state_data_phase):
            with patch("agent.tools.element_data_tools._get_element_by_code", return_value=mock_element):
                with patch("agent.tools.element_data_tools._get_required_fields_for_element", return_value=fields):
                    with patch("agent.tools.element_data_tools._get_or_create_case_element_data", return_value=mock_case_element):
                        with patch("agent.tools.element_data_tools._evaluate_field_condition", return_value=True):
                            result = await guardar_datos_elemento.ainvoke(
                                {"datos": {}}
                            )

                            assert result["success"] is False
                            assert len(result["pending_fields"]) == 3
                            assert result["pending_fields"][0]["field_key"] == "marca_placa"
                            assert result["pending_fields"][1]["field_type"] == "number"

    @pytest.mark.asyncio
    async def test_empty_dict_excludes_collected(
        self, mock_state_data_phase, mock_element
    ):
        """Pending fields MUST exclude already-collected fields."""
        from agent.tools.element_data_tools import guardar_datos_elemento

        fields = [
            self._make_field("marca_placa", "Marca placa", "text"),
            self._make_field("potencia_wp", "Potencia Wp", "number"),
            self._make_field("tipo_celda", "Tipo celda", "select"),
        ]
        mock_case_element = MagicMock()
        mock_case_element.field_values = {"marca_placa": "SOLARFAM"}

        with patch("agent.tools.element_data_tools.get_current_state", return_value=mock_state_data_phase):
            with patch("agent.tools.element_data_tools._get_element_by_code", return_value=mock_element):
                with patch("agent.tools.element_data_tools._get_required_fields_for_element", return_value=fields):
                    with patch("agent.tools.element_data_tools._get_or_create_case_element_data", return_value=mock_case_element):
                        with patch("agent.tools.element_data_tools._evaluate_field_condition", return_value=True):
                            result = await guardar_datos_elemento.ainvoke(
                                {"datos": {}}
                            )

                            assert result["success"] is False
                            assert len(result["pending_fields"]) == 2
                            keys = [f["field_key"] for f in result["pending_fields"]]
                            assert "marca_placa" not in keys

    @pytest.mark.asyncio
    async def test_empty_dict_excludes_unmet_conditionals(
        self, mock_state_data_phase, mock_element
    ):
        """Pending fields MUST exclude conditional fields with unmet conditions."""
        from agent.tools.element_data_tools import guardar_datos_elemento

        fields = [
            self._make_field("marca_placa", "Marca placa", "text"),
            self._make_field("potencia_wp", "Potencia Wp", "number"),
            self._make_field("tipo_celda", "Tipo celda", "select", condition_field_id="some-uuid"),
        ]
        mock_case_element = MagicMock()
        mock_case_element.field_values = {}

        def condition_side_effect(field, current_values, all_fields):
            # tipo_celda condition not met
            return field.field_key != "tipo_celda"

        with patch("agent.tools.element_data_tools.get_current_state", return_value=mock_state_data_phase):
            with patch("agent.tools.element_data_tools._get_element_by_code", return_value=mock_element):
                with patch("agent.tools.element_data_tools._get_required_fields_for_element", return_value=fields):
                    with patch("agent.tools.element_data_tools._get_or_create_case_element_data", return_value=mock_case_element):
                        with patch("agent.tools.element_data_tools._evaluate_field_condition", side_effect=condition_side_effect):
                            result = await guardar_datos_elemento.ainvoke(
                                {"datos": {}}
                            )

                            assert result["success"] is False
                            assert len(result["pending_fields"]) == 2
                            keys = [f["field_key"] for f in result["pending_fields"]]
                            assert "tipo_celda" not in keys

    @pytest.mark.asyncio
    async def test_empty_dict_example_max_three(
        self, mock_state_data_phase, mock_element
    ):
        """Example dict MUST have at most 3 entries."""
        from agent.tools.element_data_tools import guardar_datos_elemento

        fields = [
            self._make_field("f1", "Field 1", "text"),
            self._make_field("f2", "Field 2", "number"),
            self._make_field("f3", "Field 3", "select"),
            self._make_field("f4", "Field 4", "text"),
            self._make_field("f5", "Field 5", "boolean"),
        ]
        mock_case_element = MagicMock()
        mock_case_element.field_values = {}

        with patch("agent.tools.element_data_tools.get_current_state", return_value=mock_state_data_phase):
            with patch("agent.tools.element_data_tools._get_element_by_code", return_value=mock_element):
                with patch("agent.tools.element_data_tools._get_required_fields_for_element", return_value=fields):
                    with patch("agent.tools.element_data_tools._get_or_create_case_element_data", return_value=mock_case_element):
                        with patch("agent.tools.element_data_tools._evaluate_field_condition", return_value=True):
                            result = await guardar_datos_elemento.ainvoke(
                                {"datos": {}}
                            )

                            assert len(result["example"]) <= 3


class TestGuardarDatosPhaseValidation:
    """Tests for guardar_datos_elemento phase validation with field hints."""

    @pytest.fixture
    def mock_state_photos_phase(self):
        _case_id = str(uuid.uuid4())
        _category_id = str(uuid.uuid4())
        return {
            "current_mode": "EXPEDIENTE_MODE",
            "mode_context": {
                "expediente_sub_mode": "collect_element_data",
                "case_id": _case_id,
                "category_id": _category_id,
                "element_codes": ["PLACA_SOLAR"],
                "current_element_index": 0,
                "element_phase": "photos",
                "element_data_status": {"PLACA_SOLAR": "pending"},
            },
            "fsm_state": {
                "case_collection": {
                    "step": "collect_element_data",
                    "case_id": _case_id,
                    "category_id": _category_id,
                    "element_codes": ["PLACA_SOLAR"],
                    "current_element_index": 0,
                    "element_phase": "photos",
                    "element_data_status": {"PLACA_SOLAR": "pending"},
                }
            },
        }

    @pytest.mark.asyncio
    async def test_wrong_phase_returns_field_hints(self, mock_state_photos_phase):
        """Phase error MUST include field_key hints when element is resolvable."""
        from agent.tools.element_data_tools import guardar_datos_elemento

        mock_element = MagicMock()
        mock_element.id = uuid.uuid4()

        f1 = MagicMock()
        f1.field_key = "marca_placa"
        f1.field_label = "Marca placa"
        f2 = MagicMock()
        f2.field_key = "potencia_wp"
        f2.field_label = "Potencia Wp"

        with patch("agent.tools.element_data_tools.get_current_state", return_value=mock_state_photos_phase):
            with patch("agent.tools.element_data_tools._get_element_by_code", return_value=mock_element) as mock_get_el:
                with patch("agent.tools.element_data_tools._get_required_fields_for_element", return_value=[f1, f2]):
                    result = await guardar_datos_elemento.ainvoke(
                        {"datos": {"marca_placa": "SOLARFAM"}}
                    )

                    assert result["success"] is False
                    assert "photos" in result["error"]
                    assert "marca_placa (Marca placa)" in result["error"]
                    assert "potencia_wp (Potencia Wp)" in result["error"]
                    assert result.get("guidance") == "confirmar_fotos_primero"

    @pytest.mark.asyncio
    async def test_wrong_phase_no_element_still_returns_error(self, mock_state_photos_phase):
        """Phase error without resolvable element MUST return base error, no crash."""
        from agent.tools.element_data_tools import guardar_datos_elemento

        with patch("agent.tools.element_data_tools.get_current_state", return_value=mock_state_photos_phase):
            with patch("agent.tools.element_data_tools._get_element_by_code", return_value=None):
                result = await guardar_datos_elemento.ainvoke(
                    {"datos": {"test": "value"}}
                )

                assert result["success"] is False
                assert "photos" in result["error"]
                # No field hints, but no crash either
                assert "Campos que necesitarás después" not in result["error"]

    @pytest.mark.asyncio
    async def test_wrong_phase_db_error_graceful(self, mock_state_photos_phase):
        """DB error during hint fetch MUST not crash; return base error."""
        from agent.tools.element_data_tools import guardar_datos_elemento

        with patch("agent.tools.element_data_tools.get_current_state", return_value=mock_state_photos_phase):
            with patch("agent.tools.element_data_tools._get_element_by_code", side_effect=Exception("DB down")):
                result = await guardar_datos_elemento.ainvoke(
                    {"datos": {"test": "value"}}
                )

                assert result["success"] is False
                assert "photos" in result["error"]
