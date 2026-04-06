"""
Unit tests for agent/tools/schemas.py

Verify that every Pydantic schema:
1. Instantiates correctly with valid data.
2. Rejects clearly invalid input with a ValidationError.

These tests are pure unit tests — no database, no Redis, no LLM.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent.tools.schemas import (
    ActualizarDatosExpedienteInput,
    ActualizarDatosTallerInput,
    CalcularTarifaConElementosInput,
    CancelarExpedienteInput,
    CompletarElementoActualInput,
    ConfirmarDocumentacionBaseInput,
    ConfirmarFotosElementoInput,
    ConfirmarPresupuestoInput,
    ConsultaDuranteExpedienteInput,
    EditarExpedienteInput,
    EnviarImagenesEjemploInput,
    EscalarAHumanoInput,
    FinalizarExpedienteInput,
    GuardarDatosElementoInput,
    IdentificarTipoVehiculoInput,
    IdentificarYResolverElementosInput,
    IniciarExpedienteInput,
    ListarCategoriasInput,
    ListarElementosInput,
    ListarTarifasInput,
    ObtenerCamposElementoInput,
    ObtenerDocumentacionElementoInput,
    ObtenerEstadoExpedienteInput,
    ObtenerProgresoElementosInput,
    ObtenerServiciosAdicionalesInput,
    ReenviarImagenesElementoInput,
    SeleccionarVariantePorRespuestaInput,
)


# ---------------------------------------------------------------------------
# tarifa_tools
# ---------------------------------------------------------------------------


class TestListarCategoriasInput:
    def test_empty_instantiation(self):
        """Schema has no required fields — must instantiate with no args."""
        schema = ListarCategoriasInput()
        assert schema is not None

    def test_no_extra_fields_required(self):
        """Must not raise even when no args provided."""
        schema = ListarCategoriasInput()
        # The model has no fields; just verify it is the right type.
        assert isinstance(schema, ListarCategoriasInput)


class TestListarTarifasInput:
    def test_valid(self):
        schema = ListarTarifasInput(categoria_vehiculo="motos", tipo_cliente="particular")
        assert schema.categoria_vehiculo == "motos"
        assert schema.tipo_cliente == "particular"

    def test_default_tipo_cliente(self):
        schema = ListarTarifasInput(categoria_vehiculo="aseicars")
        assert schema.tipo_cliente == "particular"

    def test_missing_required_field(self):
        with pytest.raises(ValidationError):
            ListarTarifasInput()  # categoria_vehiculo is required


class TestObtenerServiciosAdicionalesInput:
    def test_empty_instantiation(self):
        schema = ObtenerServiciosAdicionalesInput()
        assert schema.categoria_vehiculo == ""

    def test_with_category(self):
        schema = ObtenerServiciosAdicionalesInput(categoria_vehiculo="motos")
        assert schema.categoria_vehiculo == "motos"


# ---------------------------------------------------------------------------
# vehicle_tools
# ---------------------------------------------------------------------------


class TestIdentificarTipoVehiculoInput:
    def test_valid(self):
        schema = IdentificarTipoVehiculoInput(marca="Honda", modelo="CBF600")
        assert schema.marca == "Honda"
        assert schema.modelo == "CBF600"

    def test_missing_marca(self):
        with pytest.raises(ValidationError):
            IdentificarTipoVehiculoInput(modelo="CBF600")

    def test_missing_modelo(self):
        with pytest.raises(ValidationError):
            IdentificarTipoVehiculoInput(marca="Honda")


# ---------------------------------------------------------------------------
# image_tools
# ---------------------------------------------------------------------------


class TestEnviarImagenesEjemploInput:
    def test_default_tipo(self):
        schema = EnviarImagenesEjemploInput()
        assert schema.tipo == "presupuesto"
        assert schema.codigo_elemento is None
        assert schema.categoria is None
        assert schema.follow_up_message is None

    def test_tipo_elemento(self):
        schema = EnviarImagenesEjemploInput(
            tipo="elemento",
            codigo_elemento="ESCAPE",
            categoria="motos-part",
        )
        assert schema.tipo == "elemento"
        assert schema.codigo_elemento == "ESCAPE"
        assert schema.categoria == "motos-part"

    def test_invalid_tipo(self):
        with pytest.raises(ValidationError):
            EnviarImagenesEjemploInput(tipo="desconocido")

    def test_documentacion_base(self):
        schema = EnviarImagenesEjemploInput(
            tipo="documentacion_base",
            categoria="aseicars-prof",
            follow_up_message="¿Quieres abrir un expediente?",
        )
        assert schema.tipo == "documentacion_base"
        assert schema.follow_up_message == "¿Quieres abrir un expediente?"


# ---------------------------------------------------------------------------
# transition_tools
# ---------------------------------------------------------------------------


class TestConfirmarPresupuestoInput:
    def test_empty_instantiation(self):
        schema = ConfirmarPresupuestoInput()
        assert schema is not None


# ---------------------------------------------------------------------------
# element_tools
# ---------------------------------------------------------------------------


class TestListarElementosInput:
    def test_valid(self):
        schema = ListarElementosInput(categoria_vehiculo="motos-part")
        assert schema.categoria_vehiculo == "motos-part"

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            ListarElementosInput()


class TestSeleccionarVariantePorRespuestaInput:
    def test_valid(self):
        schema = SeleccionarVariantePorRespuestaInput(
            categoria_vehiculo="motos-part",
            codigo_elemento_base="SUSPENSION",
            respuesta_usuario="delantera",
        )
        assert schema.categoria_vehiculo == "motos-part"
        assert schema.codigo_elemento_base == "SUSPENSION"
        assert schema.respuesta_usuario == "delantera"

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            SeleccionarVariantePorRespuestaInput(categoria_vehiculo="motos-part")


class TestCalcularTarifaConElementosInput:
    def test_valid(self):
        schema = CalcularTarifaConElementosInput(
            categoria_vehiculo="motos-part",
            codigos_elementos=["ESCAPE", "MANILLAR"],
        )
        assert schema.codigos_elementos == ["ESCAPE", "MANILLAR"]
        assert schema.skip_validation is False

    def test_skip_validation_true(self):
        schema = CalcularTarifaConElementosInput(
            categoria_vehiculo="motos-part",
            codigos_elementos=["ESCAPE"],
            skip_validation=True,
        )
        assert schema.skip_validation is True

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            CalcularTarifaConElementosInput(categoria_vehiculo="motos-part")


class TestObtenerDocumentacionElementoInput:
    def test_valid(self):
        schema = ObtenerDocumentacionElementoInput(
            categoria_vehiculo="motos-part",
            codigo_elemento="ESCAPE",
        )
        assert schema.codigo_elemento == "ESCAPE"

    def test_missing_codigo(self):
        with pytest.raises(ValidationError):
            ObtenerDocumentacionElementoInput(categoria_vehiculo="motos-part")


class TestIdentificarYResolverElementosInput:
    def test_valid(self):
        schema = IdentificarYResolverElementosInput(
            categoria_vehiculo="motos-part",
            descripcion="quiero homologar el escape",
        )
        assert schema.descripcion == "quiero homologar el escape"

    def test_missing_descripcion(self):
        with pytest.raises(ValidationError):
            IdentificarYResolverElementosInput(categoria_vehiculo="motos-part")


# ---------------------------------------------------------------------------
# case_tools
# ---------------------------------------------------------------------------


class TestIniciarExpedienteInput:
    def test_valid_minimal(self):
        schema = IniciarExpedienteInput(
            categoria_vehiculo="motos-part",
            codigos_elementos=["ESCAPE"],
        )
        assert schema.tarifa_calculada is None
        assert schema.tier_id is None

    def test_valid_full(self):
        schema = IniciarExpedienteInput(
            categoria_vehiculo="motos-part",
            codigos_elementos=["ESCAPE", "ALUMBRADO"],
            tarifa_calculada=410.0,
            tier_id="00000000-0000-0000-0000-000000000001",
        )
        assert schema.tarifa_calculada == 410.0

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            IniciarExpedienteInput(categoria_vehiculo="motos-part")


class TestActualizarDatosExpedienteInput:
    def test_valid_personal_data(self):
        schema = ActualizarDatosExpedienteInput(
            datos_personales={
                "nombre": "Juan",
                "apellidos": "García López",
                "dni_cif": "12345678A",
                "email": "juan@example.com",
                "domicilio_calle": "Calle Mayor 1",
                "domicilio_localidad": "Madrid",
                "domicilio_provincia": "Madrid",
                "domicilio_cp": "28001",
                "itv_nombre": "ITV Norte",
            }
        )
        assert schema.datos_personales is not None
        assert schema.datos_vehiculo is None

    def test_valid_vehicle_data(self):
        schema = ActualizarDatosExpedienteInput(
            datos_vehiculo={
                "marca": "Honda",
                "modelo": "CBF600",
                "anio": "2018",
                "matricula": "1234ABC",
            }
        )
        assert schema.datos_vehiculo is not None

    def test_both_none_allowed(self):
        """Schema itself allows both None — validation happens inside the tool."""
        schema = ActualizarDatosExpedienteInput()
        assert schema.datos_personales is None
        assert schema.datos_vehiculo is None


class TestActualizarDatosTallerInput:
    def test_defaults(self):
        schema = ActualizarDatosTallerInput()
        assert schema.taller_propio is None
        assert schema.datos_taller is None

    def test_taller_propio_false(self):
        schema = ActualizarDatosTallerInput(taller_propio=False)
        assert schema.taller_propio is False

    def test_taller_con_datos(self):
        schema = ActualizarDatosTallerInput(
            taller_propio=True,
            datos_taller={
                "nombre": "Taller García",
                "responsable": "Luis",
                "domicilio": "Calle 1",
                "provincia": "Madrid",
                "ciudad": "Alcobendas",
                "telefono": "912345678",
                "registro_industrial": "TAL-001",
                "actividad": "motos",
            },
        )
        assert schema.taller_propio is True
        assert schema.datos_taller is not None


class TestEditarExpedienteInput:
    def test_valid(self):
        schema = EditarExpedienteInput(seccion="personal")
        assert schema.seccion == "personal"

    def test_missing_seccion(self):
        with pytest.raises(ValidationError):
            EditarExpedienteInput()


class TestFinalizarExpedienteInput:
    def test_empty_instantiation(self):
        schema = FinalizarExpedienteInput()
        assert schema is not None


class TestCancelarExpedienteInput:
    def test_default_motivo(self):
        schema = CancelarExpedienteInput()
        assert schema.motivo == "Cancelado por el usuario"

    def test_custom_motivo(self):
        schema = CancelarExpedienteInput(motivo="El usuario no quiere continuar")
        assert schema.motivo == "El usuario no quiere continuar"


class TestObtenerEstadoExpedienteInput:
    def test_empty_instantiation(self):
        schema = ObtenerEstadoExpedienteInput()
        assert schema is not None


class TestConsultaDuranteExpedienteInput:
    def test_defaults(self):
        schema = ConsultaDuranteExpedienteInput()
        assert schema.consulta is None
        assert schema.accion == "responder"

    def test_with_consulta(self):
        schema = ConsultaDuranteExpedienteInput(
            consulta="¿Qué documentos necesito?",
            accion="responder",
        )
        assert schema.consulta == "¿Qué documentos necesito?"

    def test_cancelar_accion(self):
        schema = ConsultaDuranteExpedienteInput(accion="cancelar")
        assert schema.accion == "cancelar"


# ---------------------------------------------------------------------------
# element_data_tools
# ---------------------------------------------------------------------------


class TestObtenerCamposElementoInput:
    def test_default_none(self):
        schema = ObtenerCamposElementoInput()
        assert schema.element_code is None

    def test_with_code(self):
        schema = ObtenerCamposElementoInput(element_code="ESCAPE")
        assert schema.element_code == "ESCAPE"


class TestGuardarDatosElementoInput:
    def test_valid(self):
        schema = GuardarDatosElementoInput(
            datos={"altura_mm": "1230", "material": "acero inox"}
        )
        assert schema.datos["altura_mm"] == "1230"
        assert schema.element_code is None

    def test_with_element_code(self):
        schema = GuardarDatosElementoInput(
            datos={"marca": "VICTRON"},
            element_code="PLACA_SOLAR",
        )
        assert schema.element_code == "PLACA_SOLAR"

    def test_empty_datos_allowed(self):
        """Empty dict is technically valid at schema level."""
        schema = GuardarDatosElementoInput(datos={})
        assert schema.datos == {}

    def test_missing_datos(self):
        with pytest.raises(ValidationError):
            GuardarDatosElementoInput()


class TestConfirmarFotosElementoInput:
    def test_empty_instantiation(self):
        schema = ConfirmarFotosElementoInput()
        assert schema is not None


class TestCompletarElementoActualInput:
    def test_empty_instantiation(self):
        schema = CompletarElementoActualInput()
        assert schema is not None


class TestObtenerProgresoElementosInput:
    def test_empty_instantiation(self):
        schema = ObtenerProgresoElementosInput()
        assert schema is not None


class TestConfirmarDocumentacionBaseInput:
    def test_default_none(self):
        schema = ConfirmarDocumentacionBaseInput()
        assert schema.usuario_confirma is None

    def test_true(self):
        schema = ConfirmarDocumentacionBaseInput(usuario_confirma=True)
        assert schema.usuario_confirma is True


class TestReenviarImagenesElementoInput:
    def test_default_none(self):
        schema = ReenviarImagenesElementoInput()
        assert schema.element_code is None

    def test_with_code(self):
        schema = ReenviarImagenesElementoInput(element_code="SUBCHASIS")
        assert schema.element_code == "SUBCHASIS"


# ---------------------------------------------------------------------------
# shared_tools (re-export)
# ---------------------------------------------------------------------------


class TestEscalarAHumanoInput:
    def test_valid_minimal(self):
        schema = EscalarAHumanoInput(motivo="El usuario quiere hablar con una persona")
        assert schema.motivo != ""
        assert schema.es_error_tecnico is False
        assert schema.contexto == ""

    def test_all_fields(self):
        schema = EscalarAHumanoInput(
            motivo="Error recurrente",
            es_error_tecnico=True,
            contexto="El usuario lleva 3 turnos con el mismo error.",
        )
        assert schema.es_error_tecnico is True
        assert "Error" in schema.contexto

    def test_missing_motivo(self):
        with pytest.raises(ValidationError):
            EscalarAHumanoInput()
