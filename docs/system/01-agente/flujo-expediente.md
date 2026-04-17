---
titulo: Flujo EXPEDIENTE
ambito: expediente
ultima_verificacion_commit:
ultima_verificacion_fecha:
---

# Flujo EXPEDIENTE

## Resumen

`EXPEDIENTE` es un **modo compilado** (subgrafo LangGraph) con **6 sub-modos secuenciales** que recolectan los datos formales de un expediente de homologación después de que el cliente confirmó el presupuesto. A diferencia de PRE_EXPEDIENTE (conversacional, el usuario puede saltar pasos), EXPEDIENTE es un formulario guiado: cada sub-modo recolecta un conjunto específico de datos y solo transiciona al siguiente cuando esos datos están completos.

**Objetivo de negocio**: Recolectar y validar el 100% de los datos requeridos para enviar el caso a revisión humana, eliminando ciclos de ida y vuelta posteriores.

**Los 6 sub-modos secuenciales**:
1. **COLLECT_ELEMENT_DATA** — por cada elemento: fotos + datos técnicos específicos
2. **COLLECT_BASE_DOCS** — documentación base (ficha técnica, permiso, vistas)
3. **COLLECT_PERSONAL** — datos del titular (nombre, DNI, email, domicilio)
4. **COLLECT_VEHICLE** — datos del vehículo (marca, modelo, matrícula, bastidor)
5. **COLLECT_WORKSHOP** — datos del taller (si el cliente tiene taller propio)
6. **REVIEW_SUMMARY** — revisión final y envío a estado pendiente de revisión humana

El estado se preserva en Redis checkpointer + PostgreSQL (Case + CaseElementData): si el usuario abandona y vuelve, se rehidrata automáticamente el contexto sin perder progreso.

## Escenarios

### 1. Entrada a EXPEDIENTE desde PRE_EXPEDIENTE
- CUANDO el cliente confirma el presupuesto vía `confirmar_presupuesto` en PRE_EXPEDIENTE
- ENTONCES la herramienta retorna `_transition_to: EXPEDIENTE_MODE`, el router cambia de modo, se llama a `initialize_expediente()` que crea un Case en PostgreSQL, se construye el "overview" introductorio de 6 fases y se escribe en `pending_outbound_messages` (canal de reemplazo en `ConversationState`), `main.py` lo despacha vía Chatwoot **antes** del `ai_response`, limpia el canal, y entry_router despacha a `collect_element_data_node`. El flag atómico `expediente_intro_sent=True` + `expediente_intro_message=None` (tombstone) se preservan para evitar reenvíos.

### 2. Recolección de fotos del primer elemento
- CUANDO el usuario accede a EXPEDIENTE_MODE en el sub-modo `collect_element_data` para el primer elemento
- ENTONCES el bot emite instrucciones: *"Necesitamos fotos de [elemento]. Te muestro ejemplos"*, envía imágenes de ejemplo, espera que el usuario suba fotos, y acepta la confirmación "listo" vía la guardia determinística `_guard_photo_completion_intent`.

### 3. Guardia de confirmación de fotos (no-LLM)
- CUANDO el usuario está en fase "photos" y responde con intención de completar ("listo", "ya", "hechas", etc.)
- ENTONCES entry_router antes de entrar al LLM loop ejecuta `_guard_photo_completion_intent` directamente, que llama a `confirmar_fotos_elemento`, valida que hay al menos 1 foto en S3, y transiciona automáticamente a fase "data" sin involucrar al LLM. Esto previene que el LLM malinterprete "listo" como saludo.

### 4. Recolección de datos técnicos del elemento
- CUANDO el usuario está en fase "data" y responde a preguntas de campos (ej. "¿Cilindrada?", "¿Material?")
- ENTONCES `guardar_datos_elemento` valida que cada respuesta corresponda a un `field_key` exacto de `obtener_campos_elemento()`, persiste en DB, y marca el elemento "pending_data" → "completed" cuando todos los campos requeridos están rellenados.

### 5. Transición elemento → siguiente elemento
- CUANDO se completan todos los campos de un elemento
- ENTONCES `completar_elemento_actual` incrementa `current_element_index`, verifica si hay más elementos; si SÍ, reinicia el sub-modo al próximo elemento (fase "photos"); si NO, transiciona a `COLLECT_BASE_DOCS`.

### 6. Todos los elementos completados → entrada a base_docs
- CUANDO `completar_elemento_actual` detecta que `current_element_index >= len(element_codes)`
- ENTONCES entry_router auto-avanza de `COLLECT_ELEMENT_DATA` a `COLLECT_BASE_DOCS`, reinicia la sesión con el nuevo sub-modo y nuevas herramientas, y el bot pregunta por documentación base.

### 7. Confirmación de documentación base
- CUANDO el usuario envía los documentos base (ficha técnica, permiso, vistas) y confirma
- ENTONCES `confirmar_documentacion_base` valida que se recibieron archivos, persiste en `Case.base_docs_received`, y transiciona a `COLLECT_PERSONAL`.

### 8. Routing flexible (personal/vehicle/workshop sin dependencias entre sí)
- CUANDO base_docs está completado y se entra a personal/vehicle/workshop
- ENTONCES entry_router detecta intención del usuario (palabras clave: "matrícula" → vehicle, "nombre" → personal, "taller" → workshop), y si esa sección aún no está recolectada, despacha a ese nodo independientemente del orden (salvo que workshop se salta si `taller_propio=False`).

### 9. Datos completos → entrada a revisión
- CUANDO personal, vehicle y workshop están recolectados (o workshop skipped)
- ENTONCES `join_collections_node` despacha a `review_summary_node`, que emite el resumen de todo lo recolectado y pide confirmación final.

### 10. Confirmación y finalización
- CUANDO el usuario confirma el resumen en review_summary
- ENTONCES `finalizar_expediente` lee el Case desde DB (no desde `mode_context`), valida precondiciones (elements + personal + vehicle + base_docs), genera el manifiesto, persiste `Case.status=pending_review`, y retorna con `_transition_to: PRE_EXPEDIENTE_MODE` (conversación queda completada).

### 11. Recuperación de sesión tras timeout de Redis
- CUANDO el checkpoint Redis expira (TTL 7 días) pero el cliente vuelve y el Case sigue en BD con `status=collecting`
- ENTONCES preprocess_node detecta la sesión huérfana, inyecta `pending_recovery_case` en mode_context, entry_router llama a `initialize_expediente()` que rehidrata el contexto desde BD, se emite un mensaje de bienvenida cálido, y se continúa en el sub-modo + elemento donde se dejó.

### 12. Error de recolección y reintentos
- CUANDO `guardar_datos_elemento` falla validación (ej. field_key inválido, dato mal formado)
- ENTONCES retorna error con sugerencia, `retry_state.consecutive_errors` se incrementa, el bot reformula la pregunta, y tras 3 reintentos fallidos ofrece escalación a humano.

## Reglas duras

1. **6 sub-modos con orden inviolable**: COLLECT_ELEMENT_DATA → COLLECT_BASE_DOCS → (PERSONAL/VEHICLE/WORKSHOP en orden flexible pero TODOS antes de REVIEW) → REVIEW_SUMMARY. No hay atajos ni jumps entre niveles.

2. **Guardia de confirmación de fotos es determinística (no-LLM)**: cuando `element_phase=="photos"` y el usuario dice "listo" (o similar), entry_router dispara `_guard_photo_completion_intent` ANTES del LLM, sin intervención del agente. Previene que el LLM malinterprete "listo" como saludo o ignore la intención.

3. **finalizar_expediente lee SOLO de BD, NO de mode_context**: los campos `element_codes`, `categoria_slug`, `taller_propio`, `tariff_amount` deben leerse de la fila `Case` en PostgreSQL (con selectinload de relaciones), no de `mode_context`. `mode_context` es efímero; la BD es la fuente de verdad. (ADR-010.)

4. **Fase "photos" → "data" es atómica e irreversible**: una vez que `confirmar_fotos_elemento` retorna success, la fase NUNCA vuelve a "photos" para ese elemento. Si el usuario pide "más fotos", se rechaza ("ya confirmaste las fotos").

5. **field_key exacto o fallo**: en `guardar_datos_elemento(datos=...)`, cada clave en el dict `datos` debe coincidir EXACTAMENTE con un field_key retornado por `obtener_campos_elemento()`. Sin abreviaturas, sin normalización de acentos, sin conversión inteligente. Mismatch → error sin inferencia.

6. **Tombstone protocol para mode_context**: cuando una herramienta necesita limpiar una key (ej. `current_element_field_keys`), NO simplemente la deja vacía: la asigna a `None`, y luego el reducer `merge_dicts` lo interpreta como "eliminar". Sin el None, el checkpoint anterior resucita la clave. (ADR-010.)

7. **ExpedienteState NO usa merge_dicts**: a diferencia del parent `ConversationState`, el subgrafo usa plain overwrite para todas las keys (menos `messages` que usan `operator.add`). Esto elimina zombies; cada sub-modo comienza desde un clean slate.

8. **element_phase y current_element_index deben reconciliarse desde BD**: en entry_router (T-5), si `element_phase=="photos"` pero el DB muestra el elemento ya en `pending_data`, reconsolidar a `phase="data"` automáticamente. Previene "pedir fotos otra vez después de reconectar".

9. **Escalación SOLO desde sub-modos, nunca desde entry_router**: el único camino a ESCALATION es una herramienta que retorna `_transition_to: ESCALATION` (ej. `escalar_a_humano` cuando error recurrente). entry_router NO despacha directamente a escalación.

10. **No se permiten digresiones dentro de los sub-modos**: el router rechaza cambios de intent a otros modos mientras está en EXPEDIENTE. Mensaje "quiero cambiar de idea" → se mantiene en sub-modo actual y se ofrecen opciones de re-confirmación o escalación, nunca saltando a PRE_EXPEDIENTE automáticamente.

## Mapeo al código

### Modo principal y subgrafo
- `agent/modes/expediente_mode.py:87-943` — clase `ExpedienteModeNode` (coordinador, guards, helpers)
- `agent/modes/expediente_nodes.py:208-523` — `entry_router` (dispatcher del subgrafo)
- `agent/graph/expediente_subgraph.py` — compilación del subgrafo (build_mode_tool_loop + 7 nodes)

### 6 sub-modos handlers
- `agent/modes/submodos/collect_element_data.py:64-203` — ElementDataHandler
- `agent/modes/submodos/collect_base_docs.py` — BaseDocsHandler
- `agent/modes/submodos/collect_personal.py` — PersonalHandler
- `agent/modes/submodos/collect_vehicle.py` — VehicleHandler
- `agent/modes/submodos/collect_workshop.py` — WorkshopHandler
- `agent/modes/submodos/review_summary.py` — ReviewHandler

### Estado y límites
- `agent/modes/expediente_state.py:99-240` — `ExpedienteState` TypedDict (sin merge_dicts)
- `agent/modes/expediente_state.py:530-653` — funciones de mapeo parent↔subgrafo

### Herramientas de elemento
- `agent/tools/element_data_tools.py` — `confirmar_fotos_elemento`, `guardar_datos_elemento`, `completar_elemento_actual`, `obtener_campos_elemento`
- `agent/services/element_data_service.py` — lógica de validación y persistencia

### Herramientas de caso
- `agent/tools/case_tools.py:61-100` — `iniciar_expediente`, `actualizar_datos_personales`, `actualizar_datos_vehiculo`, `actualizar_datos_taller`, `confirmar_documentacion_base`, `finalizar_expediente`, `cancelar_expediente`, `editar_expediente`
- `agent/services/case_service.py` — lógica de transiciones y finalización

### Guards y reconciliación
- `agent/modes/expediente_mode.py:483-750` — `_guard_photo_completion_intent` + post-call state update
- `agent/services/expediente_guards.py` — `guard_photo_completion` (wrapper llamado por entry_router)
- `agent/modes/expediente_nodes.py:354-373` — reconciliación de phase en entry_router (T-5)

### Persistencia
- `database/models.py` — `Case`, `CaseElementData`, `CasePersonalData`, `CaseVehicleData`, `CaseWorkshopData`
- `agent/state/checkpointer.py:64-142` — `ModeAwareTTLSaver` (TTL 7d para EXPEDIENTE_MODE)

## Fuera de alcance

- `agent/modes/pre_expediente_mode.py` — modo PRE_EXPEDIENTE (otro scope)
- `agent/tools/element_tools.py` — identificación de elementos (exclusivo PRE_EXPEDIENTE)
- `agent/tools/image_tools.py:enviar_imagenes_ejemplo` — envío de imágenes en PRE (otro scope)
- `agent/tools/transition_tools.py:confirmar_presupuesto` — confirmación PRE→EXPEDIENTE (frontera, tocado solo vía ADR explícito)
- `api/**` — backend API (otro scope)
- `admin-panel/**` — UI admin (otro scope)
- `database/**` modelos sin cambios de schema (otro scope)
- `shared/**` — clientes compartidos (scope transversal)
