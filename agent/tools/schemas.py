"""
MSI-a — Tool input schemas (Pydantic BaseModel).

Single source of truth for all tool argument validation.  Every @tool
function that requires explicit input schema references its model here
instead of defining it inline or in the tool module.

Existing inline schemas (EscalarAHumanoInput in shared_tools.py,
GuardarDatosElementoInput in element_data_tools.py) are re-exported from
here so consumers can import from a single location.  The originals remain
in place for backward compatibility — the next refactor wave will remove
the duplicates and point @tool() at these.

Usage:
    from agent.tools.schemas import IdentificarElementosInput
    @tool(args_schema=IdentificarElementosInput)
    async def identificar_y_resolver_elementos(...): ...
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# tarifa_tools
# ---------------------------------------------------------------------------


class ListarCategoriasInput(BaseModel):
    """Input schema para listar_categorias (sin parámetros requeridos).

    The tool reads client_type from state — no user-supplied args needed.
    Schema is provided for uniformity and future extension.
    """


class ListarTarifasInput(BaseModel):
    """Input schema para listar_tarifas."""

    categoria_vehiculo: str = Field(
        description=(
            "Slug de la categoría del vehículo. "
            "Ejemplos: 'aseicars' para autocaravanas, 'motos' para motocicletas."
        ),
    )
    tipo_cliente: str = Field(
        default="particular",
        description="Tipo de cliente: 'particular' o 'professional'.",
    )


class ObtenerServiciosAdicionalesInput(BaseModel):
    """Input schema para obtener_servicios_adicionales."""

    categoria_vehiculo: str = Field(
        default="",
        description=(
            "Categoría opcional para filtrar servicios. "
            "Si se omite se devuelven todos los servicios adicionales disponibles."
        ),
    )


# ---------------------------------------------------------------------------
# vehicle_tools
# ---------------------------------------------------------------------------


class IdentificarTipoVehiculoInput(BaseModel):
    """Input schema para identificar_tipo_vehiculo."""

    marca: str = Field(
        description=(
            "Marca del vehículo tal como la menciona el usuario. "
            "Ejemplos: 'Honda', 'Mercedes', 'Hymer', 'Yamaha'."
        ),
    )
    modelo: str = Field(
        description=(
            "Modelo del vehículo tal como lo menciona el usuario. "
            "Ejemplos: 'CBF600', 'Sprinter', 'B-Klasse', 'MT-07'."
        ),
    )


# ---------------------------------------------------------------------------
# image_tools
# ---------------------------------------------------------------------------


class EnviarImagenesEjemploInput(BaseModel):
    """Input schema para enviar_imagenes_ejemplo."""

    tipo: Literal["presupuesto", "elemento", "documentacion_base"] = Field(
        default="presupuesto",
        description=(
            "Tipo de imágenes a enviar: "
            "'presupuesto' = todas las imágenes del presupuesto activo; "
            "'elemento' = imágenes de un elemento concreto (requiere codigo_elemento); "
            "'documentacion_base' = documentos obligatorios del vehículo (ficha técnica, permiso…)."
        ),
    )
    codigo_elemento: str | None = Field(
        default=None,
        description=(
            "Código del elemento. Obligatorio cuando tipo='elemento'. "
            "Ejemplo: 'ESCAPE', 'SUBCHASIS'."
        ),
    )
    categoria: str | None = Field(
        default=None,
        description=(
            "Slug de la categoría. Obligatorio cuando tipo='elemento' o 'documentacion_base'. "
            "Ejemplo: 'motos-part', 'aseicars-prof'."
        ),
    )
    follow_up_message: str | None = Field(
        default=None,
        description=(
            "Mensaje de texto que se envía DESPUÉS de las imágenes. "
            "Útil para preguntar si el usuario quiere abrir un expediente."
        ),
    )


# ---------------------------------------------------------------------------
# transition_tools
# ---------------------------------------------------------------------------


class ConfirmarPresupuestoInput(BaseModel):
    """Input schema para confirmar_presupuesto (sin parámetros requeridos).

    The tool reads all required data from state (mode_context).
    """


# ---------------------------------------------------------------------------
# element_tools
# ---------------------------------------------------------------------------


class ListarElementosInput(BaseModel):
    """Input schema para listar_elementos."""

    categoria_vehiculo: str = Field(
        description=(
            "Slug completo de la categoría del vehículo. "
            "Ejemplos: 'motos-part' (particulares), 'aseicars-prof' (profesionales)."
        ),
    )


class SeleccionarVariantePorRespuestaInput(BaseModel):
    """Input schema para seleccionar_variante_por_respuesta."""

    categoria_vehiculo: str = Field(
        description="Slug completo de la categoría (ej: 'motos-part', 'aseicars-prof').",
    )
    codigo_elemento_base: str = Field(
        description=(
            "Código del elemento base que tiene variantes. "
            "Ejemplo: 'BOLA_REMOLQUE', 'SUSPENSION'."
        ),
    )
    respuesta_usuario: str = Field(
        description=(
            "Texto literal con la respuesta del usuario sobre qué variante quiere. "
            "Ejemplos: 'delantera', 'ambos', '2 delanteras y 1 trasera', 'sí, aumenta MMR'."
        ),
    )


class CalcularTarifaConElementosInput(BaseModel):
    """Input schema para calcular_tarifa_con_elementos."""

    categoria_vehiculo: str = Field(
        description="Slug completo de la categoría (ej: 'motos-part', 'aseicars-prof').",
    )
    codigos_elementos: list[str] = Field(
        description=(
            "Lista de códigos EXACTOS de los elementos a homologar, "
            "tal como los devolvió identificar_y_resolver_elementos(). "
            "Ejemplo: ['ESCAPE', 'MANILLAR']."
        ),
    )
    skip_validation: bool = Field(
        default=False,
        description=(
            "Si True, omite la validación previa de códigos. "
            "Usar cuando ya se validó con identificar_y_resolver_elementos()."
        ),
    )


class ObtenerDocumentacionElementoInput(BaseModel):
    """Input schema para obtener_documentacion_elemento."""

    categoria_vehiculo: str = Field(
        description="Slug completo de la categoría (ej: 'motos-part', 'aseicars-prof').",
    )
    codigo_elemento: str = Field(
        description=(
            "Código del elemento del que se quiere documentación. "
            "Ejemplo: 'ESCAPE', 'ESC_MEC'."
        ),
    )


class IdentificarYResolverElementosInput(BaseModel):
    """Input schema para identificar_y_resolver_elementos."""

    categoria_vehiculo: str = Field(
        description=(
            "Slug completo de la categoría según el tipo de cliente. "
            "Particulares → sufijo '-part' (ej: 'motos-part'). "
            "Profesionales → sufijo '-prof' (ej: 'aseicars-prof')."
        ),
    )
    descripcion: str = Field(
        description=(
            "Descripción libre del usuario con los elementos que quiere homologar. "
            "Ejemplo: 'quiero homologar el escape y el manillar'."
        ),
    )


# ---------------------------------------------------------------------------
# case_tools
# ---------------------------------------------------------------------------


class IniciarExpedienteInput(BaseModel):
    """Input schema para iniciar_expediente."""

    categoria_vehiculo: str = Field(
        description=(
            "Slug de la categoría del vehículo (ej: 'motos-part', 'aseicars-prof'). "
            "Debe coincidir con la categoría del presupuesto calculado."
        ),
    )
    codigos_elementos: list[str] = Field(
        description=(
            "Lista de códigos de los elementos a homologar. "
            "Ejemplo: ['ESCAPE', 'ALUMBRADO']."
        ),
    )
    tarifa_calculada: float | None = Field(
        default=None,
        description="Precio calculado sin IVA. Extraer de mode_context['tarifa_calculada'].",
    )
    tier_id: str | None = Field(
        default=None,
        description="UUID del tier de tarifa. Extraer de mode_context['tarifa_calculada'].",
    )


class ActualizarDatosPersonalesInput(BaseModel):
    """Input schema para actualizar_datos_personales.

    Explicit fields so LLM models generate proper tool call args
    (dict[str, str] with additionalProperties-only schema caused empty args
    on DeepSeek). The tool function repackages these into a dict for the service.
    """

    nombre: str = Field(description="Nombre de pila (ej: Pepe)")
    apellidos: str = Field(description="Apellidos (ej: Cabeza Cruz)")
    dni_cif: str = Field(description="DNI, NIE o CIF (ej: 77429548W)")
    email: str = Field(description="Email de contacto (ej: pepe@email.com)")
    domicilio_calle: str = Field(description="Calle y numero (ej: Urb. Haza del Algarrobo 50)")
    domicilio_localidad: str = Field(description="Localidad (ej: Mijas)")
    domicilio_provincia: str = Field(description="Provincia (ej: Malaga)")
    domicilio_cp: str = Field(description="Codigo postal de 5 digitos (ej: 29650)")
    itv_nombre: str = Field(description="Nombre de la estacion ITV (ej: ITV Guadalhorce)")


class ActualizarDatosVehiculoInput(BaseModel):
    """Input schema para actualizar_datos_vehiculo.

    Explicit fields so LLM models generate proper tool call args
    (dict[str, str] with additionalProperties-only schema caused empty args
    on DeepSeek). The tool function repackages these into a dict for the service.
    """

    marca: str = Field(description="Marca del vehiculo (ej: Fiat)")
    modelo: str = Field(description="Modelo del vehiculo (ej: Ducato)")
    anio: str = Field(description="Ano de primera matriculacion (ej: 2001)")
    matricula: str = Field(description="Matricula espanola (ej: 6384BRN)")
    bastidor: str | None = Field(default=None, description="Numero de bastidor/VIN, 17 caracteres (ej: WVWZZZ3CZWE123456)")


class ActualizarDatosTallerInput(BaseModel):
    """Input schema para actualizar_datos_taller.

    Explicit fields so LLM models generate proper tool call args.
    taller_propio is always required. Workshop fields are optional
    (only needed when taller_propio=True). The tool function repackages
    workshop fields into a dict for the service.
    """

    taller_propio: bool = Field(
        description=(
            "False = MSI gestiona el certificado (coste adicional). "
            "True = el cliente aporta su propio taller registrado."
        ),
    )
    taller_nombre: str | None = Field(default=None, description="Nombre del taller (ej: Taller Garcia)")
    taller_responsable: str | None = Field(default=None, description="Responsable del taller (ej: Luis Martinez)")
    taller_domicilio: str | None = Field(default=None, description="Direccion del taller (ej: C/ Industrial 10)")
    taller_provincia: str | None = Field(default=None, description="Provincia del taller (ej: Madrid)")
    taller_ciudad: str | None = Field(default=None, description="Ciudad del taller (ej: Alcobendas)")
    taller_telefono: str | None = Field(default=None, description="Telefono del taller (ej: 912345678)")
    taller_registro_industrial: str | None = Field(default=None, description="Numero de registro industrial (ej: TAL-12345)")
    taller_actividad: str | None = Field(default=None, description="Actividad del taller (ej: reparacion de motocicletas)")


class EditarExpedienteInput(BaseModel):
    """Input schema para editar_expediente."""

    seccion: str = Field(
        description=(
            "Sección del expediente a editar. Valores válidos: "
            "'personal' (datos personales), 'vehiculo' (datos del vehículo), "
            "'taller' (datos del taller), 'documentacion' o 'docs' (documentación base)."
        ),
    )


class CancelarExpedienteInput(BaseModel):
    """Input schema para cancelar_expediente."""

    motivo: str = Field(
        default="Cancelado por el usuario",
        description="Razón de la cancelación del expediente.",
    )


class FinalizarExpedienteInput(BaseModel):
    """Input schema para finalizar_expediente (sin parámetros requeridos)."""


class ObtenerEstadoExpedienteInput(BaseModel):
    """Input schema para obtener_estado_expediente (sin parámetros requeridos)."""


class ConsultaDuranteExpedienteInput(BaseModel):
    """Input schema para consulta_durante_expediente."""

    consulta: str | None = Field(
        default=None,
        description="Pregunta o solicitud del usuario (opcional).",
    )
    accion: str = Field(
        default="responder",
        description=(
            "Tipo de acción: "
            "'responder' = atender consulta sin perder el contexto del expediente; "
            "'cancelar' = cancelar el expediente; "
            "'pausar' = pausar para atender otra cosa; "
            "'reanudar' = continuar con el expediente."
        ),
    )


# ---------------------------------------------------------------------------
# element_data_tools
# ---------------------------------------------------------------------------


class ObtenerCamposElementoInput(BaseModel):
    """Input schema para obtener_campos_elemento."""

    element_code: str | None = Field(
        default=None,
        description=(
            "Código del elemento (opcional). "
            "Si no se especifica, se usa el elemento actual del expediente."
        ),
    )


class GuardarDatosElementoInput(BaseModel):
    """Input schema para guardar_datos_elemento.

    Re-exported here from element_data_tools for single-source-of-truth imports.
    The original definition in element_data_tools.py remains for backward compatibility.
    """

    datos: dict[str, Any] = Field(
        description=(
            "Diccionario con los valores de los campos técnicos del elemento. "
            "Las claves DEBEN ser los field_key exactos devueltos por obtener_campos_elemento(). "
            'Ejemplo: {"marca_placa": "SOLARFAM", "marca_regulador": "VICTRON", '
            '"modelo_regulador": "MPPT 100-30I"}'
        ),
    )
    element_code: str | None = Field(
        default=None,
        description="Código del elemento (opcional, usa el actual si no se especifica).",
    )


class ConfirmarFotosElementoInput(BaseModel):
    """Input schema para confirmar_fotos_elemento (sin parámetros requeridos)."""


class CompletarElementoActualInput(BaseModel):
    """Input schema para completar_elemento_actual (sin parámetros requeridos)."""


class ObtenerProgresoElementosInput(BaseModel):
    """Input schema para obtener_progreso_elementos (sin parámetros requeridos)."""


class ConfirmarDocumentacionBaseInput(BaseModel):
    """Input schema para confirmar_documentacion_base."""

    usuario_confirma: bool | None = Field(
        default=None,
        description=(
            "True si el usuario confirma que ha enviado toda la documentación base. "
            "None para verificar el estado actual sin confirmar."
        ),
    )


class ReenviarImagenesElementoInput(BaseModel):
    """Input schema para reenviar_imagenes_elemento."""

    element_code: str | None = Field(
        default=None,
        description=(
            "Código del elemento del que reenviar imágenes (opcional). "
            "Si no se especifica, se usa el elemento actual."
        ),
    )


# ---------------------------------------------------------------------------
# shared_tools (re-export for uniform imports)
# ---------------------------------------------------------------------------


class EscalarAHumanoInput(BaseModel):
    """Input schema para escalar_a_humano.

    Re-exported here from shared_tools for single-source-of-truth imports.
    The original definition in shared_tools.py remains for backward compatibility.
    """

    motivo: str = Field(
        description=(
            "Motivo de la escalación. Ejemplos: "
            "'El usuario quiere hablar con una persona', "
            "'Caso técnicamente complejo', "
            "'Error recurrente en el proceso'."
        ),
    )
    es_error_tecnico: bool = Field(
        default=False,
        description="True si la escalación es por un error técnico del sistema.",
    )
    contexto: str = Field(
        default="",
        description="Resumen breve del contexto de la conversación.",
    )
