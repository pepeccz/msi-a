---
titulo: Expediente (Case) — ciclo de vida, estados, persistencia
ambito: core
ultima_verificacion_commit:
ultima_verificacion_fecha:
---

# Expediente (Case) — ciclo de vida, estados, persistencia

## Resumen

Un **Case** (Expediente) es el registro formal de solicitud de homologación que se crea cuando el cliente confirma el presupuesto. Representa el compromiso del cliente de avanzar con el trámite y contiene todos los datos recolectados durante el flujo EXPEDIENTE: fotos y datos técnicos de cada elemento, documentación base, datos personales del titular, datos del vehículo y datos del taller.

El Case tiene un ciclo de vida de dos estados principales: `collecting` (recolección activa) y `pending_review` (enviado a revisión humana). La persistencia es dual: PostgreSQL guarda el Case y sus sub-tablas como fuente de verdad definitiva; Redis guarda el checkpoint del agente con TTL de 7 días para permitir retomar la conversación sin perder progreso.

## Escenarios

### Escenario 1 — Creación del Case al confirmar presupuesto
CUANDO el cliente confirma el presupuesto en PRE_EXPEDIENTE
ENTONCES la herramienta `confirmar_presupuesto` retorna `_transition_to: EXPEDIENTE_MODE`, se crea un `Case` en PostgreSQL con `status=collecting`, se heredan de PRE_EXPEDIENTE los datos de elementos confirmados, categoría y tarifa calculada. El `Case.id` queda vinculado a la `ConversationHistory` del cliente.

### Escenario 2 — Recolección secuencial por los 6 sub-modos
CUANDO el Case está en `status=collecting`
ENTONCES el agente en modo EXPEDIENTE guía al cliente por 6 sub-modos secuenciales: (1) fotos y datos de cada elemento, (2) documentación base, (3) datos personales, (4) datos del vehículo, (5) datos del taller (opcional si `taller_propio=False`), (6) revisión final. Cada sub-modo se completa antes de avanzar al siguiente. El Case en PostgreSQL va acumulando los datos en sus sub-tablas (`CaseElementData`, `CasePersonalData`, `CaseVehicleData`, `CaseWorkshopData`).

### Escenario 3 — Fuente de verdad en BD, no en estado del agente
CUANDO el agente necesita finalizar el expediente y validar que todos los datos están completos
ENTONCES `finalizar_expediente` lee el `Case` desde PostgreSQL con `selectinload` de todas sus relaciones. No confía en `mode_context` (efímero). Los campos `element_codes`, `categoria_slug`, `taller_propio`, `tariff_amount` se leen de la fila `Case` en DB.

### Escenario 4 — Rehidratación tras timeout de Redis (< 7 días)
CUANDO el cliente abandona el flujo y vuelve antes de que expire el checkpoint Redis (TTL 7 días)
ENTONCES el checkpoint se carga automáticamente, se rehidrata `mode_context` con todos los datos previos, y se continúa en el sub-modo y elemento donde se dejó. El cliente ve un mensaje de bienvenida y el agente retoma donde se quedó.

### Escenario 5 — Rehidratación tras expiración de Redis (> 7 días)
CUANDO el checkpoint Redis expiró pero el `Case` sigue en PostgreSQL con `status=collecting`
ENTONCES `preprocess_node` detecta la sesión huérfana, inyecta `pending_recovery_case` en `mode_context`, y `initialize_expediente()` rehidrata el contexto desde DB. El cliente recibe un mensaje de bienvenida cálido y el agente retoma el sub-modo correspondiente.

### Escenario 6 — Finalización y transición a pending_review
CUANDO el cliente confirma el resumen en el sub-modo REVIEW_SUMMARY
ENTONCES `finalizar_expediente` valida precondiciones en DB (elements + personal + vehicle + base_docs presentes), genera el manifiesto del expediente, persiste `Case.status=pending_review`, y retorna `_transition_to: PRE_EXPEDIENTE_MODE`. El operador en el panel ve el caso en la cola de revisión.

### Escenario 7 — Cancelación o escalación
CUANDO el cliente quiere cancelar o acumula errores repetidos en la recolección
ENTONCES las herramientas `cancelar_expediente` o `escalar_a_humano` actualizan el `Case` a un estado terminal (`cancelled` o `escalated`). El flujo EXPEDIENTE no permite jumps a PRE_EXPEDIENTE sin confirmación explícita.

## Reglas duras

1. **6 sub-modos con orden inviolable**: COLLECT_ELEMENT_DATA → COLLECT_BASE_DOCS → (PERSONAL / VEHICLE / WORKSHOP en orden flexible, todos antes de REVIEW) → REVIEW_SUMMARY. No hay atajos.
2. **Fuente de verdad = PostgreSQL**: `finalizar_expediente` lee SOLO de DB, nunca de `mode_context`. Esto es ADR-010 y regla inquebrantable del sistema.
3. **Checkpoint Redis TTL = 7 días en EXPEDIENTE**: `ModeAwareTTLSaver` aplica TTL=10080 minutos al detectar `current_mode=EXPEDIENTE_MODE`. No configurable por conversación individual.
4. **Transiciones vía `_state_update._transition_to`**: las herramientas del expediente declaran cambios de estado y modo a través del dict `_state_update`. No se muta el estado directamente.
5. **Un Case por conversación activa**: no pueden coexistir dos Cases con `status=collecting` para el mismo `conversation_id`. Si hay uno existente, se rehidrata; no se crea uno nuevo.
6. **Tombstone para keys efímeras**: cuando una herramienta necesita limpiar una key de `mode_context` (ej. `pending_recovery_case` tras consumirlo), la asigna a `None`. El reducer `merge_dicts` la elimina. Sin el `None`, el checkpoint anterior la resucita (ADR-010).

## Mapeo al código

- `database/models.py` — modelo `Case` (id UUID, conversation_id FK, user_id FK, status ENUM, category_id FK, tariff_amount, element_codes JSONB), `CaseElementData`, `CasePersonalData`, `CaseVehicleData`, `CaseWorkshopData`.
- `agent/tools/case_tools.py:61-100` — herramientas `iniciar_expediente`, `finalizar_expediente`, `cancelar_expediente`, `editar_expediente`, herramientas de datos personales/vehículo/taller.
- `agent/services/case_service.py` — lógica de transiciones de estado del Case y finalización.
- `agent/state/checkpointer.py:64-142` — `ModeAwareTTLSaver` (TTL 7 días para EXPEDIENTE_MODE).
- `agent/modes/expediente_mode.py:87-943` — coordinador del modo EXPEDIENTE.
- `agent/modes/expediente_nodes.py:208-523` — `entry_router` del subgrafo, reconciliación de phase en T-5.

## Fuera de alcance

- Flujo detallado de cada sub-modo (→ `../../agente/flujos/expediente/flujo.md` — no existe aún, Ola 2).
- Recolección de adjuntos polimórficos (→ `../adjuntos/polimorfismo.md`).
- Presupuesto pre-confirmación (→ `../presupuestos/draft-quote.md`).
- Panel de revisión del operador (→ `../../admin-panel/casos/revision.md` — no existe aún).
