# Catálogo de Herramientas — Source of Truth

> Este documento es la referencia para la reescritura del system prompt.
> Cada herramienta está documentada con sus parámetros reales, returns reales,
> efectos de estado y instrucciones embebidas que el LLM ve.
>
> **REVISA** que todo sea correcto antes de proceder a la Fase 2.

---

## Herramientas Universales (disponibles en todos los modos)

### escalar_a_humano
- **Modos**: Todos
- **Params**: `motivo: str` (req), `es_error_tecnico: bool = False`, `contexto: str = ""`
- **Returns (ok)**: `{success: true, message, escalation_triggered: true}`
- **Returns (error)**: `{success: false, message, escalation_triggered: false}`
- **Instrucción embebida**: Ninguna relevante
- **State effects**: Desactiva bot en Chatwoot, añade labels, asigna equipo
- **Precondiciones**: conversation_id debe existir

---

## PRE_EXPEDIENTE — Herramientas de Identificación y Presupuesto

### obtener_documentacion_elemento (LEGACY — no recomendar en prompt)
- **Modos**: PRE_EXPEDIENTE (registrada en tool_manager pero NO recomendada)
- **Params**: `categoria_vehiculo: str`, `codigo_elemento: str`
- **Returns**: Documentación texto-only (docs_requeridos + advertencias + base docs) SIN URLs de imagen
- **State effects**: Ninguno
- **Por qué es legacy**: `identificar_y_resolver_elementos` ya devuelve la misma documentación como parte de su respuesta. Esta tool es un lookup standalone para cuando el código del elemento ya es conocido, pero en la práctica el flujo siempre pasa por identificar primero.
- **Para el prompt rewrite**: NO incluir como herramienta recomendada. Si el usuario pregunta "¿qué documentación necesito?", usar `identificar_y_resolver_elementos`.

### identificar_y_resolver_elementos
- **Modos**: PRE_EXPEDIENTE (IDLE/COMPLETED en tool_manager)
- **Params**: `categoria_vehiculo: str`, `descripcion: str`
- **Returns (ok)**:
  ```json
  {
    "elementos_listos": [{"codigo": "SUBCHASIS", "nombre": "Subchasis", "cantidad": 1}],
    "elementos_con_variantes": [{"codigo_base": "...", "variantes": [...]}],
    "preguntas_variantes": [{"codigo_base": "...", "pregunta": "...", "opciones": [...]}],
    "terminos_no_reconocidos": ["..."],
    "categoria_slug": "motos-part",
    "documentacion": {
      "SUBCHASIS": {
        "docs_requeridos": ["Foto con medida desde el tanque", "..."],
        "advertencias": ["Posible pérdida de 2a plaza..."],
        "num_imagenes_ejemplo": 3
      }
    },
    "documentacion_base": ["Ficha técnica...", "Permiso circulación...", "..."],
    "instrucciones": "Si el usuario pidió PRECIO → llama calcular_tarifa... Si pidió DOCUMENTACIÓN → responde con el campo documentacion..."
  }
  ```
- **Instrucción embebida**: ⚠️ `"responde con el campo documentacion de este resultado (docs_requeridos, advertencias) Y el campo documentacion_base"` — esta instrucción NO distingue entre primera vez y agregar elemento. Es la causa principal de que el LLM repita documentación.
- **State effects**: Via `_state_update`: resetea `precio_comunicado=false`, `imagenes_enviadas=false`, `imagenes_enviadas_codigos=[]`. Añade elemento a `element_codes` (additive).
- **Precondiciones**: Categoría debe existir. Validación de slug con whitelist.

### seleccionar_variante_por_respuesta
- **Modos**: PRE_EXPEDIENTE
- **Params**: `categoria_vehiculo: str`, `codigo_elemento_base: str`, `respuesta_usuario: str`
- **Returns (ok — selección simple)**: `{selected_variant: "SUSPENSION_DEL", confidence: 0.95, name: "Delantera"}`
- **Returns (ok — multi-select)**: `{selected_variants: [...], mode: "multi_select", names: [...]}`
- **Returns (clarificación)**: `{needs_clarification: true, pregunta: "...", opciones: [...]}`
- **Instrucción embebida**: Ninguna relevante
- **State effects**: Indirectos via hook — actualiza `pending_variants`
- **Precondiciones**: Variantes deben existir para el elemento base

### calcular_tarifa_con_elementos
- **Modos**: PRE_EXPEDIENTE
- **Params**: `categoria_vehiculo: str`, `codigos_elementos: list[str]`, `skip_validation: bool = False`
- **Returns (ok)**:
  ```json
  {
    "success": true,
    "texto": "TARIFA RECOMENDADA: Proyecto Completo\nPrecio: 410.0 EUR...",
    "datos": {
      "price": 410.0,
      "precio_final": 410.0,
      "tier_name": "Proyecto Completo",
      "elementos_incluidos": ["SUBCHASIS"],
      "warnings": [{"message": "Posible pérdida de 2a plaza...", "severity": "warning"}]
    },
    "documentacion": {"elementos": [...], "documentacion_base": {...}},
    "imagenes_ejemplo": [...]
  }
  ```
- **Instrucción embebida**: `"Calcula el precio de homologación basándose en elementos específicos del catálogo"`
- **State effects**: Via post-tool hook: `price_authority_confirmed=true`, extrae warnings a `advertencias_comunicadas`. NO setea `precio_comunicado` — eso lo hace el mode node DESPUÉS de que el LLM genera respuesta.
- **Precondiciones**: Todos los element codes deben ser válidos

### enviar_imagenes_ejemplo
- **Modos**: Todos (PRE_EXPEDIENTE + EXPEDIENTE)
- **Params**: `tipo: "presupuesto" | "elemento" | "documentacion_base"`, `codigo_elemento: str | None`, `categoria: str | None`, `follow_up_message: str | None` (DEPRECATED)
- **Returns (ok)**: `{success: true, message: "OK: 5 imagenes encoladas...", data: {images_count: 5}}`
- **Returns (error)**: `{success: false, message: "...", valid_codes: [...]}`
- **Instrucción embebida**: `"NO uses follow_up_message — escribe el CTA directamente en tu ai_response"`
- **State effects**: Via `_state_update`: `imagenes_enviadas_codigos_pending=[codes]`. TIMING: `imagenes_enviadas_codigos` se popula en el PRÓXIMO turno después de delivery real.
- **Precondiciones**: Categoría o elemento deben existir

### listar_categorias
- **Modos**: PRE_EXPEDIENTE
- **Params**: Ninguno
- **Returns**: `{success: true, data: {categories: [{slug, name, description}]}}`
- **State effects**: Ninguno
- **Precondiciones**: Ninguna

### listar_elementos
- **Modos**: PRE_EXPEDIENTE
- **Params**: `categoria_vehiculo: str`
- **Returns**: `{elementos: "lista formateada"}`
- **State effects**: Ninguno
- **Precondiciones**: Categoría debe existir

### identificar_tipo_vehiculo
- **Modos**: PRE_EXPEDIENTE
- **Params**: `marca: str`, `modelo: str`
- **Returns**: `{success: true, data: {tipo, confianza, categoria_sugerida, pedir_confirmacion}}`
- **State effects**: Ninguno
- **Precondiciones**: Ninguna

---

## PRE_EXPEDIENTE → EXPEDIENTE — Herramientas de Transición

### confirmar_presupuesto
- **Modos**: PRE_EXPEDIENTE (transición a EXPEDIENTE)
- **Params**: Ninguno
- **Returns (ok)**: `{success: true, message: "El usuario ha confirmado el presupuesto.", resumen: {precio: 410.0, elementos: [...], categoria: "motos-part"}, _state_update: {_transition_to: "EXPEDIENTE_MODE"}}`
- **Returns (error)**: `{success: false, error: "..."}`
- **Instrucción embebida**: Ninguna
- **State effects**: Señaliza transición de modo a EXPEDIENTE_MODE. NO crea caso en BD (eso lo hace iniciar_expediente).
- **Precondiciones**: `precio_comunicado=true` y `tarifa_calculada` deben existir
- **Nota**: Gated dinámicamente en pre_expediente_mode.py — no aparece en tool_manager.py. Solo disponible cuando se cumplen las precondiciones.

### iniciar_expediente
- **Modos**: EXPEDIENTE (llamada automática tras confirmar_presupuesto)
- **Params**: `categoria_vehiculo: str`, `codigos_elementos: list[str]`, `tarifa_calculada: float | None`, `tier_id: str | None`
- **Returns (ok)**: `{success: true, case_id: "uuid", message: "...", _state_update: {case_collection: {step: "collect_element_data"}}}`
- **Returns (error)**: `{success: false, error: "..."}`
- **Instrucción embebida**: Ninguna relevante
- **State effects**: Crea caso (Case) en BD con status="collecting". Inicializa FSM en COLLECT_ELEMENT_DATA. Almacena categoría + element codes en mode_context.
- **Precondiciones**: `categoria_vehiculo` y `user_id` deben existir en state
- **Relación con confirmar_presupuesto**: Son herramientas SEPARADAS en secuencia. confirmar_presupuesto = señal de transición de modo. iniciar_expediente = creación real del caso en BD. El LLM llama ambas en turnos diferentes.

---

## EXPEDIENTE — Herramientas de Recolección de Elementos

### obtener_campos_elemento
- **Modos**: EXPEDIENTE_COLLECT_ELEMENT_DATA
- **Params**: `element_code: str | None` (usa actual si no se especifica)
- **Returns (ok)**:
  ```json
  {
    "success": true,
    "element_code": "SUBCHASIS",
    "element_name": "Subchasis",
    "phase": "photos" | "data",
    "photos_required": true,
    "photos_confirmed_count": 0,
    "fields": [
      {
        "field_key": "descripcion_modificacion",
        "field_label": "Descripción de la modificación",
        "field_type": "text",
        "is_required": true,
        "instruccion_usuario": "Guía: qué se hizo al subchasis",
        "example_value": "Recortado por la parte trasera"
      }
    ]
  }
  ```
- **State effects**: Ninguno
- **Precondiciones**: Elemento debe existir, caso activo

### confirmar_fotos_elemento
- **Modos**: EXPEDIENTE_COLLECT_ELEMENT_DATA
- **Params**: `usuario_confirma: bool | None`
- **Returns (ok)**: `{success: true, photos_confirmed: true, element_code: "...", element_phase: "data"}`
- **State effects**: Transiciona fase del elemento: photos → data
- **Precondiciones**: Caso activo, elemento en fase photos

### guardar_datos_elemento
- **Modos**: EXPEDIENTE_COLLECT_ELEMENT_DATA
- **Params**: `datos: dict[str, Any]` (req — keys deben ser field_key exactos), `element_code: str | None`
- **Returns (ok)**: `{success: true, results: [{field_key, status, value}], all_required_collected: bool, saved_count: int}`
- **Returns (error)**: `{success: false, error: "Missing required parameter: datos"}` o `{success: false, error: "CAMPOS INCORRECTOS: ..."}`
- **State effects**: Si `all_required_collected: true` → setea flag para completar elemento
- **Precondiciones**: Caso activo, field_keys deben coincidir con obtener_campos_elemento

### completar_elemento_actual
- **Modos**: EXPEDIENTE_COLLECT_ELEMENT_DATA
- **Params**: Ninguno
- **Returns (ok)**: `{success: true, element_code: "...", all_elements_complete: bool, next_step: "COLLECT_BASE_DOCS" | null, next_element_name: "..." | null}`
- **State effects**: Avanza índice de elemento. Si todos completos → auto-transición a COLLECT_BASE_DOCS
- **Precondiciones**: Todos los required fields deben estar recolectados

### obtener_progreso_elementos
- **Modos**: EXPEDIENTE_COLLECT_ELEMENT_DATA
- **Params**: Ninguno
- **Returns**: `{elements_total: 2, elements_completed: 1, current_element_code: "...", current_element_phase: "photos"}`
- **State effects**: Ninguno

### reenviar_imagenes_elemento
- **Modos**: EXPEDIENTE_COLLECT_ELEMENT_DATA
- **Params**: `element_code: str | None`
- **Returns**: `{success: true, element_code: "...", images_count: 3}`
- **State effects**: Encola imágenes para re-envío

---

## EXPEDIENTE — Documentación Base

### confirmar_documentacion_base
- **Modos**: EXPEDIENTE_COLLECT_BASE_DOCS
- **Params**: `usuario_confirma: bool | None`
- **Returns (ok)**: `{success: true, images_received: 4, base_docs_confirmed: true, next_step: "COLLECT_PERSONAL"}`
- **Returns (error/escalación)**: `{success: false, escalated: true, images_received: 1, message: "He registrado una incidencia..."}`
- **State effects**: Transiciona a COLLECT_PERSONAL. Si faltan imágenes + usuario confirma → escalación silenciosa.
- **Precondiciones**: Caso activo. **PDF bypass**: si hay un PDF (`mime_type=application/pdf`), satisface el mínimo (fix deployeado hoy).

---

## EXPEDIENTE — Datos Personales / Vehículo / Taller

### actualizar_datos_personales
- **Modos**: EXPEDIENTE_COLLECT_PERSONAL
- **Params**: `datos_personales: dict` con keys: `nombre, apellidos, email, dni_cif, domicilio_calle, domicilio_localidad, domicilio_provincia, domicilio_cp, itv_nombre`
- **Returns (ok)**: `{success: true, personal_data_complete: bool, missing_fields: [...]}`
- **State effects**: Transiciona a COLLECT_VEHICLE cuando completo
- **Precondiciones**: Caso activo. NO incluir teléfono (ya lo tenemos de WhatsApp)

### actualizar_datos_vehiculo
- **Modos**: EXPEDIENTE_COLLECT_VEHICLE
- **Params**: `datos_vehiculo: dict` con keys: `marca, modelo, anio, matricula, bastidor`
- **Returns (ok)**: `{success: true, vehicle_data_complete: bool, missing_fields: [...]}`
- **State effects**: Transiciona a COLLECT_WORKSHOP cuando completo
- **Precondiciones**: Caso activo

### actualizar_datos_taller
- **Modos**: EXPEDIENTE_COLLECT_WORKSHOP
- **Params**: `taller_propio: bool` (req), + si `taller_propio=true`: `taller_nombre, taller_responsable, taller_domicilio, taller_provincia, taller_ciudad, taller_telefono, taller_registro_industrial, taller_actividad`
- **Returns (ok)**: `{success: true, taller_propio: bool, taller_data_complete: bool}`
- **State effects**: Transiciona a REVIEW_SUMMARY cuando completo
- **Precondiciones**: Caso activo. Si `taller_propio=true`, todos los campos de taller son requeridos

---

## EXPEDIENTE — Revisión y Finalización

### obtener_estado_expediente
- **Modos**: Todos los EXPEDIENTE
- **Params**: Ninguno
- **Returns**: `{success: true, current_step, personal_data: {...}, vehicle_data: {...}, element_status: [...], tariff_amount, precio_total}`
- **State effects**: Ninguno
- **Precondiciones**: Ninguna (retorna gracefully si no hay caso)

### finalizar_expediente
- **Modos**: EXPEDIENTE_REVIEW_SUMMARY
- **Params**: Ninguno
- **Returns (ok)**: `{success: true, case_id, status: "pending_review"}`
- **Returns (error)**: `{success: false, error: "..."}`
- **State effects**: Crea escalación para revisión. Marca caso como completado.
- **Precondiciones**: Todas las secciones deben estar completas

### editar_expediente
- **Modos**: EXPEDIENTE_REVIEW_SUMMARY
- **Params**: `seccion: "personal" | "vehiculo" | "taller" | "documentacion"`
- **Returns**: `{success: true, next_step: "collect_personal" | "collect_vehicle" | ...}`
- **State effects**: Transiciona FSM de vuelta a la sección especificada

### cancelar_expediente
- **Modos**: Todos los EXPEDIENTE
- **Params**: `motivo: str = "Cancelado por el usuario"`
- **Returns**: `{success: true, case_id, status: "cancelled"}`
- **State effects**: Cancela caso, transiciona a PRE_EXPEDIENTE

### consulta_durante_expediente
- **Modos**: Todos los EXPEDIENTE
- **Params**: `consulta: str | None`, `accion: str = "responder"`
- **Returns**: `{success: true, respuesta_consulta, expediente_status}`
- **State effects**: Puede pausar/reanudar caso según `accion`

### reactivar_expediente_abandonado
- **Modos**: IDLE (recuperación)
- **Params**: `case_id: str` (UUID)
- **Returns**: `{success: true, case_id, element_codes, category_slug}`
- **State effects**: Reactiva caso abandonado
- **Precondiciones**: Caso debe existir y estar en status "abandoned"
