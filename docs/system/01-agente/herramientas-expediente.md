---
titulo: Herramientas disponibles en EXPEDIENTE
ambito: expediente
ultima_verificacion_commit:
ultima_verificacion_fecha:
---

# Herramientas disponibles en EXPEDIENTE

## Resumen

Las herramientas de EXPEDIENTE se dividen en **dos categorías**:

1. **Element Data Tools** (`agent/tools/element_data_tools.py`) — recolección de fotos y datos técnicos por elemento
2. **Case Tools** (`agent/tools/case_tools.py`) — gestión del expediente completo (personal, vehículo, taller, finalización)

Las herramientas usan un contrato estándar: reciben argumentos Pydantic, delegan toda lógica a servicios (`element_data_service`, `case_service`), retornan dicts con estructura `{success, data, error, _state_update}`, y NUNCA mutan estado directamente (los reducers lo hacen en `post_tool_node`).

## Escenarios

### 1. Flujo típico de 1 elemento (fotos → datos → completar)
- CUANDO entry_router despacha a `collect_element_data_node`
- ENTONCES:
  - Primer turno: LLM dice "te envío ejemplos", tool `enviar_imagenes_elemento` (pre-loop), usuario sube fotos
  - Segundo turno: usuario dice "listo", guardia `_guard_photo_completion_intent` llama `confirmar_fotos_elemento` (no-LLM), fase avanza "photos" → "data"
  - Tercer turno: LLM pide campos, tool `obtener_campos_elemento` devuelve `{field_key: {...}}`, usuario responde
  - Cuarto turno: LLM llama `guardar_datos_elemento` con `{datos: {field_key: value}}`, se valida y persiste. Si todos los campos resueltos, LLM llama `completar_elemento_actual`

### 2. Validación determinística de field_key
- CUANDO `guardar_datos_elemento(datos={mi_campo: "valor"})` se invoca
- ENTONCES `element_data_service.save_element_data()` revisa que "mi_campo" existe en el resultado previo de `obtener_campos_elemento()`. Si no existe → error `InvalidFieldKeyError`, no se persiste nada, el bot reformula.

### 3. Manejo de fotos incompletas
- CUANDO `confirmar_fotos_elemento` ejecuta y detecta 0 fotos en S3
- ENTONCES retorna `{success: false, photos_count: 0, action: RETRY}`, el bot NO avanza la fase, reformula pidiendo fotos, se incrementa retry_count.

### 4. Escalación en data collection tras 3 reintentos
- CUANDO un elemento ha fallado `guardar_datos_elemento` 3+ veces consecutivas
- ENTONCES el post_tool_hook detecta `consecutive_errors >= 3`, invoca automáticamente `escalar_a_humano(motivo="Error persistente en recolección de datos", es_error_tecnico=False)`, y transiciona a ESCALATION.

### 5. Transición a base_docs cuando elemento termina
- CUANDO `completar_elemento_actual` detecta `current_element_index >= len(element_codes)`
- ENTONCES retorna `{_context_updates: {expediente_sub_mode: collect_base_docs}}`, entry_router lee esto, despacha a `collect_base_docs_node`, y el flujo continúa.

### 6. Uso de tools desde distintos sub-modos
- CUANDO COLLECT_BASE_DOCS necesita `confirmar_documentacion_base`, COLLECT_PERSONAL necesita `actualizar_datos_personales`, etc.
- ENTONCES cada sub-modo tiene su propio `get_tools()` que retorna SOLO sus herramientas (sin element_data_tools, sin case_tools de otros tipos). Esto fuerza que el LLM use la herramienta correcta para el contexto.

## Reglas duras

1. **field_key es exacto o no entra**: `guardar_datos_elemento(datos={campo_inventado: val})` → error sin inducción. Mismatch entre `obtener_campos_elemento()` y lo que el usuario proporciona → reformulación, sin intentar "normalizar" o "adivinar".

2. **`finalizar_expediente` es el gatekeeper**: NUNCA se marca `case.status=pending_review` excepto dentro de `finalizar_expediente()`. Cualquier otra ruta que intente cambiar status → error. El DB schema la refuerza con checks.

3. **Las herramientas NO mutan `mode_context` directamente**: los updates retornan en `_state_update._context_updates`. El `post_tool_node` es el único lugar que aplica `merge_dicts`. Previene race conditions.

4. **Confirmar fotos es determinístico (no-LLM)**: `confirmar_fotos_elemento` se ejecuta vía `_guard_photo_completion_intent` en entry_router, NO como una llamada de tool del LLM. El LLM nunca invoca directamente esta herramienta.

5. **Enviar imágenes es idempotente por elemento**: hay un guard `_photos_confirmed_this_turn` (in-memory) que previene llamadas duplicadas a `enviar_imagenes_ejemplo` dentro del mismo turno.

6. **tariff_amount en finalizar debe venir de BD**: `finalizar_expediente` NO usa `mode_context["tariff_amount"]`; lo lee del `Case.tariff_amount` en PostgreSQL. Si no existe, falla validación.

7. **element_codes y categoria_slug son readonly una vez en BD**: una vez que `Case` se crea, estos campos son inmutables. Cualquier cambio posterior → error controlado.

8. **Reintento explícito tras error**: `guardar_datos_elemento` retorna `{retry_count, consecutive_errors, last_error_type}` para que el post_tool_hook pueda tomar decisiones de escalación.

## Catálogo de herramientas

### Element Data Tools (recolección de elementos)

| Herramienta | Archivo | Propósito | Cuándo se usa |
|-------------|---------|-----------|---------------|
| `obtener_campos_elemento` | `element_data_tools.py` | Devuelve la lista de campos técnicos requeridos para un elemento. **Phase-aware**: cuando `phase=="photos"` retorna `fields=[]` (lista vacía) — el LLM no puede pedir datos textuales antes de confirmar fotos. Cuando `phase=="data"` retorna los fields normales. | Inicio de fase "data" (LLM pregunta "¿qué necesito?") |
| `guardar_datos_elemento` | `element_data_tools.py` | Valida y persiste respuesta del usuario para 1+ campos | Usuario responde a pregunta técnica (turno iterativo) |
| `confirmar_fotos_elemento` | `element_data_tools.py` | Valida ≥1 foto en S3, transiciona a data, persiste en DB | Llamado por `_guard_photo_completion_intent` (no-LLM) |
| `completar_elemento_actual` | `element_data_tools.py` | Marca elemento como "completed", avanza índice, persiste | LLM lo invoca después de guardar último dato |
| `obtener_progreso_elementos` | `element_data_tools.py` | Devuelve `{completado, pendiente}` para mostrar al usuario | LLM para transparencia ("ya hemos recolectado X/Y elementos") |
| `reenviar_imagenes_elemento` | `element_data_tools.py:406` | Reenvía las imágenes de ejemplo del elemento actual (o de un elemento por código). Solo funciona cuando `expediente_sub_mode == COLLECT_ELEMENT_DATA`. Delega a `resend_element_images()` en `element_data_service.py`. **Sin efectos de estado**: no avanza ni retrocede fases; solo regenera el mensaje de imágenes. | Cliente dice "¿puedo ver las fotos de ejemplo de nuevo?" durante la recolección de un elemento |
| `consulta_durante_expediente` | `case_tools.py:319` | Maneja consultas y acciones del usuario dentro de EXPEDIENTE sin romper el flujo. Soporta 4 acciones via parámetro `accion`: `"responder"` (responder pregunta sin perder contexto), `"cancelar"` (delega a `cancelar_expediente`), `"pausar"` (suspende temporalmente), `"reanudar"` (retoma tras pausa). **Registrada en todos los sub-modos** de EXPEDIENTE (`_shared.py:912-1028`). Sin efectos de estado (excepto cuando `accion="cancelar"`, que llama internamente a `cancelar_expediente`). | Cliente hace una pregunta off-topic durante EXPEDIENTE, o pide pausar, o intenta salir |

### Case Tools (gestión del expediente)

| Herramienta | Archivo | Propósito | Cuándo se usa |
|-------------|---------|-----------|---------------|
| `iniciar_expediente` | `case_tools.py:61+` | Crea un Case en BD, inicializa CaseElementData rows | Entrada a EXPEDIENTE (llamado por `initialize_expediente`) |
| `actualizar_datos_personales` | `case_tools.py:~200+` | Valida y persiste personal_data, transiciona a vehicle | COLLECT_PERSONAL node |
| `actualizar_datos_vehiculo` | `case_tools.py:~280+` | Valida y persiste vehicle_data, transiciona a workshop/review | COLLECT_VEHICLE node |
| `actualizar_datos_taller` | `case_tools.py:~360+` | Valida y persiste taller_data (si `taller_propio=True`), transiciona a REVIEW | COLLECT_WORKSHOP node (o salta si `taller_propio=False`) |
| `confirmar_documentacion_base` | `case_tools.py:~120+` | Valida que se recibió base_docs (ficha, permiso, vistas), transiciona a PERSONAL | COLLECT_BASE_DOCS node |
| `finalizar_expediente` | `case_tools.py:~450+` | **GATEKEEPER**: valida precondiciones, genera manifiesto, persiste `status=pending_review` | REVIEW_SUMMARY node (confirmar final) |
| `cancelar_expediente` | `case_tools.py:~520+` | Marca `status=cancelled`, cleans up, transiciona a PRE_EXPEDIENTE | User cancela durante EXPEDIENTE |
| `editar_expediente` | `case_tools.py:~580+` | Vuelve a un sub-modo anterior para re-recolectar datos | User dice "quiero cambiar el [dato]" desde REVIEW |
| `obtener_estado_expediente` | `case_tools.py:~650+` | Devuelve estado del caso en texto legible | User pregunta "¿dónde está mi caso?" |
| `reactivar_expediente_abandonado` | `case_tools.py:462` | Reactiva un expediente con `status="abandoned"` para continuar la tramitación. Valida que el expediente existe, está en estado `abandoned`, y que no hay otro expediente activo para el mismo usuario. Devuelve `element_codes` y `category_slug` para retomar el flujo. | Entrada a session recovery: cuando `conversation_graph.py` detecta `pending_abandoned_case` en estado y el usuario confirma querer retomar (ver `agent/prompts/modes/session_recovery.md:65`). Se registra en `CASE_TOOLS` pero NO en sub-modos EXPEDIENTE estándar — se invoca desde el contexto de recuperación de sesión |

## Mapeo al código

### Servicios (lógica)
- `agent/services/element_data_service.py` — `save_element_data()`, `confirm_element_photos()`, `complete_current_element()`, `get_element_fields()`
- `agent/services/case_service.py` — `initialize_case()`, `update_personal_data()`, `update_vehicle_data()`, `update_workshop_data()`, `finalize_case()`

### Schemas (validación)
- `agent/tools/schemas.py` — `GuardarDatosElementoInput`, `ConfirmarFotosElementoInput`, `ActualizarDatosPersonalesInput`, `ReactivarExpedienteInput`, etc.

### Post-tool hooks (state merge)
- `agent/modes/post_tool_hooks.py` — `expediente_post_tool_hook` que aplica `_context_updates` al `mode_context`

## Fuera de alcance

- `agent/tools/element_tools.py` — identificación de elementos (exclusivo PRE_EXPEDIENTE)
- `agent/tools/image_tools.py` — envío de imágenes ejemplo (exclusivo PRE_EXPEDIENTE)
- `agent/tools/tarifa_tools.py` — cálculo de tarifas (exclusivo PRE_EXPEDIENTE)
- `api/**` — backend API (otro scope)
