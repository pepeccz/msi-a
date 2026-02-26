# Plan: Compliance AEPD — Orientaciones IA Agéntica y Protección de Datos

> **Status**: 🟡 Proposed  
> **Created**: 2026-02-19  
> **Updated**: 2026-02-19  
> **Priority**: 🔴 High  
> **Referencia normativa**: AEPD, "Orientaciones sobre IA Agéntica y Protección de Datos" (febrero 2026)  
> **ADR asociado**: `docs/decisions/009-aepd-ia-agentica-compliance.md`

---

## Resumen Ejecutivo

MSI-a, como sistema de IA agéntica que trata datos personales (teléfono, nombre, NIF/CIF, email, domicilio, datos de vehículos) por WhatsApp, debe cumplir con las Orientaciones de la AEPD sobre IA Agéntica y Protección de Datos (febrero 2026). El análisis de compliance reveló que **solo se cumplen 15 de 62 requisitos** identificados. Este plan define **45 acciones concretas** organizadas en 3 fases (P0, P1, P2) para alcanzar conformidad total.

### Modelo de responsabilidad

| Quién | Responsabilidad |
|-------|----------------|
| **MSI Automotive** | Responsable del tratamiento (Art. 24 RGPD). Aprueba, firma y responde ante la AEPD. |
| **Zanovix (agencia)** | Encargado del tratamiento. Redacta TODOS los borradores legales (tiene el conocimiento técnico). Ejecuta el desarrollo. |
| **Abogado RGPD** ⚖️ | Valida jurídica de los documentos críticos (EIPD, contratos Art. 28, bases legitimadoras). |

### Esfuerzo estimado

| Tipo | Esfuerzo | Responsable |
|------|----------|-------------|
| Desarrollo código | **33-43 días** | Zanovix (agent-dev, backend-dev, etc.) |
| Redacción borradores legales | **11-17 días** | Zanovix |
| Revisión MSI + validación abogado | **Variable** | MSI Automotive + abogado RGPD |

> **CLAVE**: Zanovix tiene TODO el contexto técnico del análisis de compliance recién realizado. Esto reduce drásticamente el tiempo de preparación de documentos legales vs. empezar desde cero con un consultor externo.

---

## Problema

### Contexto

La AEPD publicó en febrero 2026 orientaciones específicas sobre sistemas de IA agéntica que tratan datos personales. MSI-a encaja plenamente en la definición de "sistema de IA agéntica" de la AEPD:
- Toma decisiones autónomas (modo PRESUPUESTO, EVALUACION_GATEWAY)
- Accede a datos personales almacenados (User, Case, ConversationHistory)
- Interactúa con servicios de terceros (Chatwoot, OpenRouter, Qdrant)
- Opera con supervisión humana limitada (solo escalado bajo demanda)

### Pain Points

- **Riesgo sancionador real**: La AEPD puede imponer sanciones de hasta 20M€ o 4% facturación global
- **Sin capa de información RGPD**: Los usuarios nunca son informados de sus derechos
- **Sin derecho de supresión técnicamente implementado**: No existe mecanismo para borrar datos de un usuario en todos los sistemas
- **Sin EIPD**: Obligatoria para tratamientos de alto riesgo con IA
- **Transferencias internacionales sin documentar**: DeepSeek (OpenRouter) puede procesar en terceros países
- **Sin contratos Art. 28 RGPD documentados**: Chatwoot, OpenRouter sin rol definido

### Requisitos de Negocio

- Cumplir con RGPD y las orientaciones AEPD sobre IA agéntica
- Minimizar riesgo sancionador
- Mantener la funcionalidad y experiencia de usuario del agente
- Implementar sin downtime significativo

---

## Estado Actual de Compliance

| Categoría | Cumple | Parcial | No cumple | Total |
|-----------|--------|---------|-----------|-------|
| Principios tratamiento | 3 | 4 | 5 | 12 |
| Derechos interesados | 1 | 2 | 7 | 10 |
| Seguridad técnica | 6 | 4 | 3 | 13 |
| Gobernanza y documentación | 2 | 3 | 8 | 13 |
| Transparencia IA | 3 | 3 | 8 | 14 |
| **TOTAL** | **15** | **16** | **31** | **62** |

### Lo que ya cumple bien MSI-a

- ✅ Supervisión humana y escalado (`escalar_a_humano`, modo ESCALATION)
- ✅ Minimización en acceso a datos (tools solo acceden a tarifas/elementos/categorías)
- ✅ Seguridad de imagen multi-capa (SSRF, magic numbers, decompression bombs)
- ✅ Sanitización de datos personales en logs (`sanitize_phone()`)
- ✅ Hybrid LLM con prioridad local (Tier 1-2 Ollama, solo Tier 3 cloud)
- ✅ Trazabilidad y auditoría (tool_call_logs, token_usage, llm_usage_metrics)
- ✅ Sandboxing Docker
- ✅ Whitelist de herramientas por modo
- ✅ Sistema de prompts estructurado con guardrails (01_security.md)

---

## Servicios Afectados

- [x] **Agent** (`agent/`) — Mensaje de bienvenida, disclaimer, identificación IA hardcodeada
- [x] **API** (`api/`) — Endpoints RGPD (supresión, exportación, retención), privacy info
- [x] **Admin Panel** (`admin-panel/`) — Panel de gestión RGPD, consentimiento, auditoría
- [x] **Database** (`database/`) — Modelo ConsentLog, DataDeletionRequest, policies RGPD
- [x] **Shared** (`shared/`) — Config nuevas variables, utilities de anonimización

---

## Leyenda

| Símbolo | Significado |
|---------|-------------|
| 🔧 | Cambio de CÓDIGO (responsabilidad desarrollo) |
| 📋 | Cambio DOCUMENTAL/LEGAL — **Zanovix (agencia) redacta borrador**, MSI Automotive revisa y aprueba |
| 🔧📋 | Mixto: código implementa + contenido legal redactado por Zanovix |
| ⚖️ | Requiere REVISIÓN JURÍDICA externa obligatoria (abogado RGPD) |
| S/M/L/XL | Complejidad: Small (<0.5d) / Medium (0.5-1d) / Large (1-3d) / XL (3-5d) |

### Modelo de responsabilidad legal

> **Responsable del tratamiento**: MSI Automotive S.L. (siempre — Art. 24 RGPD)  
> **Encargado del tratamiento / Agencia de desarrollo**: Zanovix  
> **Modelo de trabajo**: Zanovix redacta TODOS los borradores legales y técnicos. MSI Automotive revisa, aprueba y firma. Un abogado RGPD valida los documentos marcados con ⚖️.
>
> **Zanovix aporta**:
> - Borradores de textos legales basados en plantillas estándar RGPD
> - Ejecución de la parte técnica de la EIPD (inventario datos, flujos, análisis riesgos)
> - Preparación del RAT con datos técnicos del sistema
> - Propuesta de contratos Art. 28 (incluido el suyo propio como encargado)
> - Documentación de transferencias internacionales (parte técnica)
>
> **MSI Automotive decide y firma**:
> - Aprobación de bases legitimadoras
> - Firma de contratos Art. 28
> - Firma de la EIPD
> - Aprobación final de textos legales
> - Decisión sobre consulta previa a AEPD
>
> **Abogado RGPD externo valida**:
> - Bases legitimadoras elegidas
> - Contratos Art. 28 antes de firma
> - EIPD antes de firma (requisitos formales)
> - Análisis Art. 22 (decisiones automatizadas)
> - Procedimiento de brechas

---

# FASE 0: Quick Wins (Implementar inmediatamente, sin riesgo)

> **Esfuerzo estimado**: 3-4 días  
> **Riesgo**: Ninguno — son mejoras aditivas que no afectan funcionalidad existente

---

### QW-01: 🔧 Hardcodear identificación como IA en código (no solo en prompt)

**Descripción**: Actualmente la identificación como IA depende del prompt (`02_identity.md`). Si el LLM falla o ignora la instrucción, no hay fallback. Insertar un prefijo hardcodeado a nivel de código en la primera respuesta de cada conversación.

**Agente**: agent-dev  
**Complejidad**: S  
**Archivos**:
- `agent/modes/consulta_mode.py` — Inyectar prefijo en primera interacción
- `agent/modes/presupuesto_mode.py` — Idem
- `agent/state/conversation_state.py` — Añadir flag `ia_disclosure_sent: bool`

**Criterios de aceptación**:
- [ ] La primera respuesta del agente en TODA conversación nueva comienza con texto que incluye "asistente con inteligencia artificial" o "asistente con IA"
- [ ] Este texto se inyecta a nivel de código Python, no depende del LLM
- [ ] Flag `ia_disclosure_sent` se persiste en state y evita repetir en mensajes siguientes
- [ ] Tests unitarios verifican la inyección

**Dependencias**: Ninguna

---

### QW-02: 🔧 Añadir disclaimer orientativo a presupuestos

**Descripción**: Los presupuestos calculados por el agente no indican que son orientativos y no vinculantes. Añadir coletilla automática al resultado de `calcular_tarifa_con_elementos`.

**Agente**: agent-dev  
**Complejidad**: S  
**Archivos**:
- `agent/tools/tarifa_tools.py` — Añadir disclaimer al campo `message` del resultado
- `agent/prompts/core/07_pricing_rules.md` — Reforzar instrucción de mencionar carácter orientativo

**Criterios de aceptación**:
- [ ] Todo presupuesto incluye texto tipo: "*Este presupuesto es orientativo y no vinculante. El precio final puede variar tras revisión del expediente.*"
- [ ] El disclaimer se inserta en el `message` del tool return (no depende del LLM)
- [ ] Tests verifican presencia del disclaimer en resultado de herramienta

**Dependencias**: Ninguna

---

### QW-03: 🔧 Implementar job de purga de métricas LLM

**Descripción**: `LLM_METRICS_RETENTION_DAYS=90` está configurado en `shared/config.py` pero no hay job que ejecute la purga. Crear un endpoint de administración y un script de mantenimiento.

**Agente**: backend-dev  
**Complejidad**: M  
**Archivos**:
- `api/routes/system.py` — Nuevo endpoint `POST /api/system/maintenance/purge-old-data`
- `scripts/purge_old_data.py` — Script de purga ejecutable por cron/manual
- `shared/config.py` — Nuevas variables: `CONVERSATION_RETENTION_DAYS`, `TOOL_LOG_RETENTION_DAYS`

**Tablas a purgar** (con retención configurable):
| Tabla | Retención por defecto | Datos sensibles |
|-------|-----------------------|-----------------|
| `llm_usage_metrics` | 90 días | No (solo métricas) |
| `tool_call_logs` | 90 días | Sí (parámetros pueden contener datos personales) |
| `token_usage` | 365 días | No (solo contadores mensuales) |
| `conversation_messages` | 180 días | Sí (contenido de mensajes) |
| `container_error_logs` | 30 días (resueltos) | No |
| `admin_access_log` | 365 días | Sí (IPs) |

**Criterios de aceptación**:
- [ ] Endpoint protegido con `require_role("admin")`
- [ ] Script ejecutable: `python -m scripts.purge_old_data --dry-run`
- [ ] Modo dry-run muestra qué se borraría sin borrar
- [ ] Cada tabla respeta su período de retención configurado
- [ ] Log estructurado de cada purga (registros eliminados por tabla)
- [ ] Tests unitarios con datos de test

**Dependencias**: Ninguna

---

### QW-04: 🔧 Añadir input sanitization guardrails a nivel de código

**Descripción**: Actualmente la protección contra prompt injection depende exclusivamente de `01_security.md` (prompt). Añadir una capa de detección a nivel de código antes de enviar al LLM.

**Agente**: agent-dev  
**Complejidad**: M  
**Archivos**:
- `agent/utils/input_sanitizer.py` — Nuevo módulo de sanitización
- `agent/graph/conversation_graph.py` — Integrar en nodo `preprocess`
- `agent/state/conversation_state.py` — Añadir flag `input_flagged: bool`

**Patrones a detectar** (regex, no LLM):
- Intentos de extracción de prompt (`"ignora.*instrucciones"`, `"actúa como"`, `"eres ahora"`)
- Ofuscación (`base64`, `hexadecimal`, unicode invisible)
- Inyección de roles (`"system:"`, `"<|im_start|>"`)

**Comportamiento al detectar**:
- Flag el input como sospechoso (`input_flagged=True`)
- Añadir instrucción de refuerzo al system prompt
- Log el intento (`logger.warning("prompt_injection_attempt", ...)`)
- NO bloquear el mensaje (evitar falsos positivos que impidan uso legítimo)

**Criterios de aceptación**:
- [ ] Módulo detecta al menos 10 patrones comunes de prompt injection
- [ ] Input flaggeado se registra en logs
- [ ] No genera falsos positivos con mensajes normales de homologación
- [ ] Tests parametrizados con vectores de ataque conocidos
- [ ] No aumenta latencia más de 5ms por mensaje

**Dependencias**: Ninguna

---

### QW-05: 🔧 Endpoint de exportación de datos del usuario (Art. 20 RGPD — Portabilidad)

**Descripción**: Crear endpoint que exporte todos los datos de un usuario en formato estructurado (JSON). Esto también es prerequisito para el derecho de supresión (saber qué borrar).

**Agente**: backend-dev  
**Complejidad**: M  
**Archivos**:
- `api/routes/admin.py` — Nuevo endpoint `GET /api/admin/users/{user_id}/export`
- `api/services/gdpr_service.py` — Nuevo servicio con lógica de recopilación de datos

**Datos a exportar por usuario**:
```json
{
  "user": { "phone", "first_name", "last_name", "email", "nif_cif", "domicilio_*", "metadata" },
  "conversations": [{ "messages": [...], "summary", "created_at" }],
  "cases": [{ "vehicle_data", "element_data", "images", "status" }],
  "tool_logs": [{ "tool_name", "parameters", "result", "timestamp" }],
  "escalations": [{ "reason", "status", "timestamp" }]
}
```

**Criterios de aceptación**:
- [ ] Endpoint protegido con `require_role("admin")`
- [ ] Retorna JSON completo con todos los datos del usuario
- [ ] Incluye datos de todas las tablas con FK a `user_id`
- [ ] No incluye datos internos del sistema (IDs de Chatwoot, hashes, etc.)
- [ ] Tests verifican exportación completa

**Dependencias**: Ninguna

---

# FASE 1 (P0): Acciones Urgentes — Riesgos Legales Inmediatos

> **Esfuerzo estimado**: 15-20 días  
> **Plazo recomendado**: 4-6 semanas desde aprobación  
> **Riesgo de no hacerlo**: Sanción AEPD, reclamación de interesado

---

## 1.1 Capa de Información RGPD al Usuario

### P0-01: 📋⚖️ Redactar textos legales de primera interacción

**Descripción**: Zanovix redacta los borradores de todos los textos legales necesarios. MSI Automotive revisa y aprueba. Un abogado RGPD valida antes de puesta en producción.

**Responsable redacción**: Zanovix (agencia)  
**Aprueba**: MSI Automotive  
**Valida**: Abogado RGPD externo ⚖️  
**Complejidad**: L  

**Entregables que redacta Zanovix**:

1. **Mensaje de primera interacción** (capa 1, breve, WhatsApp):
   - Plantilla en `docs/legal/borrador-aviso-primera-interaccion.md`
   - Identificación del responsable: "MSI Automotive S.L."
   - Finalidad: "Gestión de presupuestos y expedientes de homologación"
   - Base legitimadora propuesta: "Ejecución de un contrato o medidas precontractuales (Art. 6.1.b RGPD)"
   - Enlace a política completa: URL a web de MSI Automotive
   - Mención de derechos: "Puedes ejercer tus derechos ARCO+ escribiendo a [email]"

2. **Política de privacidad completa** (capa 2, web):
   - Plantilla en `docs/legal/borrador-politica-privacidad.md`
   - Responsable, DPO (si aplica), finalidades, bases legitimadoras
   - Destinatarios (Chatwoot, OpenRouter, etc.)
   - Transferencias internacionales
   - Plazos de conservación
   - Derechos y cómo ejercerlos
   - Derecho a reclamar ante la AEPD

3. **Texto de consentimiento** (si se opta por consentimiento como base adicional):
   - Plantilla en `docs/legal/borrador-consentimiento.md`
   - Consentimiento para tratamiento por IA
   - Consentimiento para transferencia internacional a OpenRouter

4. **Contrato de encargado de tratamiento Zanovix ↔ MSI Automotive**:
   - Plantilla en `docs/legal/borrador-contrato-encargado-zanovix.md`
   - Basado en modelo estándar Art. 28 RGPD de la AEPD

**Criterios de aceptación**:
- [ ] Borradores redactados por Zanovix en `docs/legal/`
- [ ] Revisados por MSI Automotive (feedback incorporado)
- [ ] Validados por abogado RGPD ⚖️
- [ ] Aprobados y firmados por MSI Automotive
- [ ] URL de política de privacidad operativa
- [ ] Email de ejercicio de derechos definido
- [ ] Textos adaptados a formato WhatsApp (longitud razonable)

**Dependencias**: Bloquea P0-02

---

### P0-02: 🔧📋 Implementar mensaje RGPD en primera interacción

**Descripción**: Cuando un usuario escribe por primera vez (no hay `ConversationHistory` previa), el agente debe enviar un mensaje informativo RGPD antes de la respuesta normal. Este mensaje se envía UNA sola vez por usuario.

**Agente**: agent-dev + backend-dev  
**Complejidad**: L  
**Archivos**:
- `database/models.py` — Añadir campo `privacy_notice_sent_at: DateTime | None` en `User`
- `database/alembic/versions/035_add_privacy_fields.py` — Migration
- `agent/modes/consulta_mode.py` — Inyectar mensaje RGPD si `privacy_notice_sent_at` es None
- `agent/modes/presupuesto_mode.py` — Idem
- `agent/services/privacy_service.py` — Nuevo servicio: comprobar/registrar envío de aviso
- `shared/config.py` — Nueva variable: `PRIVACY_NOTICE_TEXT`, `PRIVACY_POLICY_URL`

**Flujo**:
```
1. Usuario escribe primer mensaje
2. Agent consulta User.privacy_notice_sent_at
3. Si es None:
   a. Envía mensaje RGPD (configurado en PRIVACY_NOTICE_TEXT o SystemSetting)
   b. Actualiza User.privacy_notice_sent_at = now()
   c. Continúa con respuesta normal del agente
4. Si ya fue enviado: continúa normal
```

**Criterios de aceptación**:
- [ ] Todo usuario nuevo recibe el mensaje RGPD en su primera interacción
- [ ] El mensaje se envía como mensaje separado ANTES de la respuesta del agente
- [ ] El texto es configurable desde `system_settings` o `.env`
- [ ] Incluye enlace a política de privacidad
- [ ] Se registra timestamp de envío en `User.privacy_notice_sent_at`
- [ ] No se repite en conversaciones posteriores del mismo usuario
- [ ] Tests unitarios y de integración

**Dependencias**: P0-01 (textos legales)

---

### P0-03: 🔧 Implementar página de política de privacidad en admin panel

**Descripción**: Crear una página pública (sin auth) que muestre la política de privacidad. El enlace en el mensaje RGPD del agente debe apuntar aquí o a la web de MSI Automotive.

**Agente**: frontend-dev + backend-dev  
**Complejidad**: M  
**Archivos**:
- `admin-panel/src/app/privacy/page.tsx` — Página pública (Server Component)
- `api/routes/system.py` — Endpoint `GET /api/public/privacy-policy` (sin auth)
- `database/models.py` — Usar `SystemSetting` con key `privacy_policy_html`

**Criterios de aceptación**:
- [ ] Página accesible sin autenticación en `/privacy`
- [ ] Contenido editable desde admin panel (via SystemSetting)
- [ ] Renderiza HTML/Markdown correctamente
- [ ] Responsive (funciona desde WhatsApp Web link preview)

**Dependencias**: P0-01 (textos legales)

---

## 1.2 Derecho de Supresión (Art. 17 RGPD)

### P0-04: 🔧 Implementar servicio de supresión completa de datos de usuario

**Descripción**: Crear un servicio que borre TODOS los datos de un usuario en TODOS los sistemas. Este es el gap más técnicamente complejo.

**Agente**: backend-dev  
**Complejidad**: XL  
**Archivos**:
- `api/services/gdpr_service.py` — Ampliar con método `delete_user_data(user_id)`
- `api/routes/admin.py` — Nuevo endpoint `DELETE /api/admin/users/{user_id}/gdpr-delete`
- `database/models.py` — Nuevo modelo `DataDeletionRequest`
- `database/alembic/versions/036_data_deletion_requests.py` — Migration

**Sistemas a purgar** (en orden):
```
1. Redis
   - Checkpoints de conversación (agent:checkpoint:*)
   - Cache de tarifas (tariffs:*)
   - Batches de mensajes (agent:batch:*)
   
2. PostgreSQL (cascading delete o anonimización)
   - conversation_messages → DELETE WHERE conversation_id IN (user conversations)
   - conversation_history → DELETE WHERE user_id = X
   - case_element_data → DELETE WHERE case_id IN (user cases)
   - case_images → DELETE archivos físicos + registros WHERE case_id IN (user cases)
   - cases → DELETE WHERE user_id = X
   - tool_call_logs → ANONYMIZE WHERE conversation_id IN (user conversations)
   - escalations → ANONYMIZE WHERE conversation_id IN (user conversations)
   - users → DELETE WHERE id = X

3. Chatwoot
   - Borrar contacto via API: DELETE /api/v1/accounts/{id}/contacts/{contact_id}
   - O anonimizar si borrado no es posible

4. Qdrant (si aplica)
   - No debería tener datos personales (solo chunks de documentos normativos)
   - Verificar que RAGQuery no contenga datos personales en query text

5. Archivos físicos
   - Borrar imágenes de uploads/ asociadas a cases del usuario
```

**Modelo DataDeletionRequest**:
```python
class DataDeletionRequest(Base):
    __tablename__ = "data_deletion_requests"
    
    id: UUID (PK)
    user_id: UUID (FK users.id, SET NULL)
    user_phone: str  # Guardado por si user ya fue borrado
    requested_at: DateTime
    completed_at: DateTime | None
    status: str  # pending, in_progress, completed, failed, partially_completed
    deletion_log: JSONB  # {"redis": "ok", "postgres": "ok", "chatwoot": "failed", ...}
    requested_by: UUID (FK admin_users.id)
    notes: str | None
```

**Criterios de aceptación**:
- [ ] Endpoint protegido con `require_role("admin")`
- [ ] Requiere confirmación (parámetro `confirm=true`)
- [ ] Ejecuta borrado en TODOS los sistemas listados
- [ ] Registra resultado por sistema en `deletion_log` (JSONB)
- [ ] Si un sistema falla, continúa con los demás y marca `partially_completed`
- [ ] Borra archivos físicos de `uploads/`
- [ ] Intenta borrar/anonimizar contacto en Chatwoot
- [ ] Log de auditoría completo (`AuditLog`)
- [ ] Tests con mocks de cada sistema
- [ ] El endpoint retorna el `DataDeletionRequest` con estado

**Dependencias**: QW-05 (exportación, para saber qué borrar)

---

### P0-05: 🔧 Panel de gestión de solicitudes RGPD en admin

**Descripción**: Crear sección en el admin panel para gestionar solicitudes de derechos RGPD (supresión, acceso, portabilidad).

**Agente**: frontend-dev  
**Complejidad**: L  
**Archivos**:
- `admin-panel/src/app/(dashboard)/gdpr/page.tsx` — Página principal
- `admin-panel/src/app/(dashboard)/gdpr/components/` — Componentes
- `admin-panel/src/lib/types.ts` — Tipos DataDeletionRequest
- `admin-panel/src/lib/api.ts` — Métodos API para GDPR

**Funcionalidades**:
- Lista de solicitudes de supresión (con estado)
- Botón "Exportar datos" por usuario (llama a QW-05)
- Botón "Eliminar datos" por usuario (llama a P0-04, con AlertDialog de confirmación)
- Vista de log de eliminación (qué sistemas completaron, cuáles fallaron)
- Buscar usuario por teléfono para iniciar solicitud

**Criterios de aceptación**:
- [ ] Página accesible desde sidebar del admin panel
- [ ] AlertDialog con doble confirmación para eliminación
- [ ] Muestra estado de cada solicitud
- [ ] Permite reintentar sistemas fallidos
- [ ] Toast de feedback en cada acción

**Dependencias**: P0-04 (endpoint de supresión)

---

## 1.3 Documentación Legal y Organizativa

### P0-06: 📋⚖️ Realizar EIPD (Evaluación de Impacto en Protección de Datos)

**Descripción**: El RGPD (Art. 35) obliga a realizar una EIPD cuando el tratamiento implica uso de nuevas tecnologías y puede suponer alto riesgo. Un sistema de IA agéntica que trata datos personales por WhatsApp cumple AMBOS criterios.

**Responsable redacción**: Zanovix (parte técnica completa + borrador parte legal)  
**Aprueba y firma**: MSI Automotive  
**Valida**: Abogado RGPD externo ⚖️  
**Complejidad**: XL  
**Entregable**: Documento EIPD en `docs/legal/borrador-eipd.md` siguiendo metodología AEPD

**Contenido mínimo de la EIPD**:
1. Descripción del tratamiento (flujo de datos MSI-a) — **Zanovix redacta**
2. Evaluación de necesidad y proporcionalidad — **Zanovix propone, abogado valida** ⚖️
3. Evaluación de riesgos para derechos y libertades — **Zanovix ejecuta** (ya tenemos el análisis de compliance)
4. Medidas para mitigar riesgos (las que ya existen + las de este plan) — **Zanovix redacta**
5. Consulta previa a la AEPD si el riesgo residual es alto — **MSI Automotive decide con abogado** ⚖️

**Aportación técnica de Zanovix** (el grueso del trabajo):
- Diagrama de flujo de datos completo (WhatsApp → Chatwoot → Agent → DB → Chatwoot → WhatsApp)
- Inventario de datos personales tratados por tabla (ya identificado en análisis)
- Descripción de medidas de seguridad existentes (security whitepaper)
- Descripción del Hybrid LLM y qué datos llegan a cada tier
- Análisis de riesgos técnicos (basado en el análisis AEPD ya realizado: 62 requisitos, 31 amenazas)
- Propuesta de medidas de mitigación (este plan)

**Criterios de aceptación**:
- [ ] EIPD borrador redactada por Zanovix en `docs/legal/borrador-eipd.md`
- [ ] Validada por abogado RGPD ⚖️
- [ ] Firmada por responsable del tratamiento (MSI Automotive)
- [ ] Incluye plan de acción para riesgos identificados
- [ ] Referencia las medidas técnicas implementadas

**Dependencias**: Ninguna (puede hacerse en paralelo con desarrollo)

---

### P0-07: 📋⚖️ Documentar y formalizar roles de tratamiento

**Descripción**: Definir formalmente el rol de cada tercero bajo RGPD y preparar los contratos correspondientes.

**Responsable redacción**: Zanovix (análisis técnico + borradores de contratos)  
**Aprueba y firma**: MSI Automotive  
**Valida**: Abogado RGPD externo ⚖️  
**Complejidad**: L

**Roles a determinar** (propuesta de Zanovix):

| Tercero | Rol probable | Contrato necesario | Quién prepara borrador |
|---------|-------------|-------------------|----------------------|
| **Zanovix** (agencia desarrollo) | Encargado del tratamiento | Contrato Art. 28 RGPD | Zanovix |
| **Chatwoot** (self-hosted o cloud) | Encargado del tratamiento | Contrato Art. 28 RGPD | Zanovix |
| **OpenRouter** | Encargado del tratamiento (subencargado: DeepSeek) | Contrato Art. 28 RGPD + cláusulas transferencia | Zanovix |
| **Hetzner/OVH** (hosting) | Encargado del tratamiento | Contrato Art. 28 RGPD | Zanovix |
| **WhatsApp/Meta** | Responsable independiente | Verificar Terms of Service | Zanovix analiza |

**Entregables de Zanovix**:
- [ ] Documento de determinación de roles en `docs/legal/borrador-roles-tratamiento.md`
- [ ] Borrador contrato Art. 28 Zanovix ↔ MSI Automotive en `docs/legal/borrador-contrato-encargado-zanovix.md`
- [ ] Borrador contratos Art. 28 con Chatwoot, OpenRouter, hosting en `docs/legal/`
- [ ] Cadena de subencargados documentada
- [ ] Análisis de Terms of Service de OpenRouter y Chatwoot

**Validación obligatoria** ⚖️:
- [ ] Abogado RGPD valida roles propuestos
- [ ] Abogado RGPD revisa contratos Art. 28 antes de firma
- [ ] MSI Automotive firma todos los contratos

**Dependencias**: Ninguna

---

### P0-08: 📋⚖️ Documentar transferencias internacionales

**Descripción**: DeepSeek (via OpenRouter) procesa datos en China. Requiere documentar bajo Cap. V RGPD.

**Responsable investigación y redacción**: Zanovix  
**Aprueba**: MSI Automotive  
**Valida**: Abogado RGPD externo ⚖️  
**Complejidad**: L  
**Estado**: 🟡 Parcialmente resuelto — decisión tomada, acciones contractuales pendientes

**Decisión de MSI Automotive (Febrero 2026)**:  
Evaluadas las alternativas (Mistral AI, Nebius NL como host alternativo, pseudonimización), MSI Automotive ha decidido **mantener DeepSeek V3 via OpenRouter** asumiendo el riesgo residual bajo **Art. 49.1.b RGPD**. Decisión documentada en `docs/legal/borrador-tia-openrouter.md` v1.1.

**Entregables de Zanovix**:
- [x] Investigación de ubicación de procesamiento de OpenRouter/DeepSeek
- [x] Borrador TIA en `docs/legal/borrador-tia-openrouter.md`
- [x] Alternativas evaluadas (Nebius NL, Mistral AI, pseudonimización)
- [ ] Verificar adherencia de OpenRouter al DPF (dataprivacyframework.gov)
- [ ] Borrador SCCs Módulo 3 con OpenRouter → ya en `docs/legal/borrador-contrato-encargado-openrouter.md`

**Validación obligatoria pendiente** ⚖️:
- [ ] Abogado RGPD valida base Art. 49.1.b y TIA v1.1
- [ ] Confirmar con OpenRouter términos de no-entrenamiento
- [ ] SCCs Módulo 3 firmadas con OpenRouter

**Dependencias**: P0-07 (definición de roles)

---

### P0-09: 📋 Crear RAT (Registro de Actividades de Tratamiento)

**Descripción**: El Art. 30 RGPD obliga a mantener un registro de actividades de tratamiento. Zanovix prepara el borrador completo con toda la información técnica (que ya conoce mejor que nadie).

**Responsable redacción**: Zanovix  
**Aprueba**: MSI Automotive  
**Complejidad**: M

**Entregable**: `docs/legal/borrador-rat.md`

**Contenido mínimo** (Zanovix redacta todo esto):
```
Actividad: Atención al cliente por WhatsApp con IA agéntica (MSI-a)
Responsable: MSI Automotive S.L., [dirección], [CIF]  ← MSI completa
DPO: [si aplica]  ← MSI completa
Finalidad: Gestión de consultas, presupuestos y expedientes de homologación
Categorías de interesados: Clientes y potenciales clientes
Categorías de datos: Nombre, teléfono, email, NIF/CIF, domicilio, datos vehículo, matrícula, bastidor
Destinatarios: 
  - Zanovix (encargado — desarrollo y mantenimiento)
  - Chatwoot (encargado — mensajería)
  - OpenRouter (encargado — procesamiento LLM cloud)
  - [hosting provider] (encargado — infraestructura)
Transferencias internacionales: [según P0-08]
Plazos de supresión: 
  - Datos de usuario: hasta ejercicio derecho supresión
  - Mensajes conversación: 180 días
  - Métricas LLM: 90 días
  - Tool logs: 90 días
Medidas de seguridad: [referencia a security whitepaper P2-03]
```

**Criterios de aceptación**:
- [ ] Borrador completo en `docs/legal/borrador-rat.md`
- [ ] Solo quedan campos `[MSI completa]` para que rellene MSI Automotive
- [ ] MSI Automotive revisa, completa campos pendientes y aprueba

**Dependencias**: P0-07, P0-08

---

## 1.4 Evaluación Art. 22 RGPD (Decisiones Automatizadas)

### P0-10: 📋⚖️ Evaluar si MSI-a toma "decisiones automatizadas" bajo Art. 22 RGPD

**Descripción**: El Art. 22 RGPD da derecho a no ser objeto de decisiones basadas únicamente en tratamiento automatizado que produzcan efectos jurídicos o similares. Zanovix prepara el análisis técnico y el abogado valida la conclusión jurídica.

**Responsable análisis técnico**: Zanovix  
**Valida conclusión jurídica**: Abogado RGPD externo ⚖️  
**Complejidad**: M

**Análisis preliminar de Zanovix** (ya realizado):
- **Presupuestos**: Son orientativos → probablemente NO es decisión con efecto jurídico (si se implementa QW-02)
- **Evaluación Gateway (aceptar/rechazar)**: ¿Tiene efecto significativo? El usuario puede pedir hablar con humano → probablemente NO
- **Expediente**: Recopila datos → el humano decide → NO es automatizada
- **Escalado**: Beneficia al usuario → NO es Art. 22

**Si se determina que SÍ aplica Art. 22**:
- Implementar derecho a intervención humana (ya existe via `escalar_a_humano`)
- Informar al usuario del uso de IA en la toma de decisiones (ya cubierto por QW-01)
- Permitir impugnar la decisión

**Entregables**:
- [ ] Borrador de análisis Art. 22 por Zanovix en `docs/legal/borrador-analisis-art22.md`
- [ ] Validación jurídica por abogado RGPD ⚖️
- [ ] Si procede: aviso adicional al usuario cuando se toman decisiones automatizadas

**Dependencias**: P0-06 (EIPD incluye este análisis)

---

# FASE 2 (P1): Acciones Importantes — Mejora de Compliance

> **Esfuerzo estimado**: 12-15 días  
> **Plazo recomendado**: 8-12 semanas desde aprobación  
> **Riesgo de no hacerlo**: Debilidad ante auditoría, mejora de postura de seguridad

---

## 2.1 Compartimentación y Minimización de Datos en LLM

### P1-01: 🔧 Política formal de datos en contexto LLM

**Descripción**: Definir y implementar qué datos personales se incluyen en el contexto enviado al LLM y cuáles se excluyen/anonimizan.

**Agente**: agent-dev  
**Complejidad**: L  
**Archivos**:
- `agent/services/context_sanitizer.py` — Nuevo servicio de sanitización de contexto
- `agent/modes/base_mode.py` — Integrar sanitización antes de llamada LLM
- `agent/prompts/loader.py` — Filtrar datos sensibles del mode_context

**Reglas de compartimentación**:
| Dato | ¿Incluir en contexto LLM? | Justificación |
|------|---------------------------|---------------|
| Nombre del usuario | ✅ Sí (primer nombre) | Personalización necesaria |
| Teléfono | ❌ No | No necesario para conversación |
| Email | ❌ No | No necesario para conversación |
| NIF/CIF | ❌ No | No necesario para conversación |
| Domicilio | ❌ No | No necesario para conversación |
| Datos vehículo (marca, modelo) | ✅ Sí | Necesario para presupuesto |
| Matrícula | ⚠️ Solo en modo EXPEDIENTE | No necesario en consulta/presupuesto |
| Bastidor | ⚠️ Solo en modo EXPEDIENTE | Idem |
| Historial mensajes | ✅ Sí (últimos N) | Contexto conversacional |

**Criterios de aceptación**:
- [ ] Datos personales no necesarios se excluyen del contexto LLM
- [ ] Sanitización se aplica antes de TODA llamada al LLM
- [ ] El agente sigue funcionando correctamente tras la sanitización
- [ ] Log de qué campos se sanitizaron por llamada
- [ ] Tests de regresión para conversaciones normales

**Dependencias**: Ninguna

---

### P1-02: 🔧 Limitar ventana de historial en contexto LLM

**Descripción**: Actualmente se envía el historial completo de la conversación al LLM. Limitar a los últimos N mensajes para minimizar datos personales en tránsito.

**Agente**: agent-dev  
**Complejidad**: M  
**Archivos**:
- `agent/state/helpers.py` — Modificar `format_messages()` para truncar historial
- `shared/config.py` — Nueva variable: `LLM_CONTEXT_WINDOW_MESSAGES=20`

**Criterios de aceptación**:
- [ ] Historial limitado a N mensajes configurables
- [ ] Se preserva siempre el primer mensaje (contexto inicial)
- [ ] Se preserva el system prompt completo (no se trunca)
- [ ] No afecta calidad de respuesta para conversaciones normales (<20 mensajes)
- [ ] Tests de regresión

**Dependencias**: Ninguna

---

### P1-03: 🔧 Anonimizar datos personales antes de enviar a cloud (Tier 3)

**Descripción**: Cuando el LLM Router envía datos a OpenRouter (Tier 3, cloud), anonimizar datos personales detectados en el contenido del mensaje.

**Agente**: agent-dev  
**Complejidad**: L  
**Archivos**:
- `shared/llm_router.py` — Integrar anonimización pre-envío para Tier 3
- `agent/services/context_sanitizer.py` — Añadir función de anonimización de PII en texto libre

**Patrones a anonimizar** (regex):
- Teléfonos españoles: `+34XXXXXXXXX` → `[TELÉFONO]`
- NIFs: `XXXXXXXL` → `[NIF]`
- Emails: `user@domain.com` → `[EMAIL]`
- Matrículas: `XXXXAAA` → `[MATRÍCULA]`

**Criterios de aceptación**:
- [ ] Anonimización activa solo para Tier 3 (cloud)
- [ ] Tier 1 y Tier 2 (local) no se anonimizan (ya son locales)
- [ ] Patrones de PII detectados y reemplazados antes de envío
- [ ] La respuesta del LLM se desanonimiza si es necesario (o se acepta que use placeholders)
- [ ] Tests parametrizados con distintos tipos de PII

**Dependencias**: P1-01

---

### P1-04: 🔧 Circuit breaker global para comportamiento anómalo

**Descripción**: Implementar detección de patrones anómalos que puedan indicar un fallo del agente (bucles, respuestas repetitivas, consumo excesivo de tokens).

**Agente**: agent-dev + backend-dev  
**Complejidad**: L  
**Archivos**:
- `agent/services/anomaly_detector.py` — Nuevo servicio de detección
- `agent/modes/base_mode.py` — Integrar checks en cada iteración del tool loop
- `shared/config.py` — Umbrales configurables

**Patrones a detectar**:
| Patrón | Umbral | Acción |
|--------|--------|--------|
| Tool loop infinito | >10 iteraciones | Forzar respuesta + escalado |
| Tokens excesivos por turno | >4000 tokens output | Log warning + truncar |
| Misma respuesta repetida | 3 veces consecutivas | Escalado automático |
| Error rate alto | >50% errores en 5 min | Pausa + alerta admin |
| Conversación excesivamente larga | >100 mensajes | Sugerir escalado |

**Criterios de aceptación**:
- [ ] Al menos 3 patrones anómalos detectados
- [ ] Acción automática por patrón (escalado, log, pausa)
- [ ] Umbrales configurables via `.env` o `system_settings`
- [ ] No genera falsos positivos en uso normal
- [ ] Log de anomalías detectadas

**Dependencias**: Ninguna

---

### P1-05: 🔧 Modelo de consentimiento granular

**Descripción**: Crear infraestructura para registrar consentimientos específicos del usuario (aunque la base legitimadora principal sea contractual).

**Agente**: database-dev + backend-dev  
**Complejidad**: L  
**Archivos**:
- `database/models.py` — Nuevo modelo `ConsentRecord`
- `database/alembic/versions/037_consent_records.py` — Migration
- `api/routes/admin.py` — Endpoints CRUD para consentimientos
- `api/services/gdpr_service.py` — Lógica de gestión de consentimiento

**Modelo ConsentRecord**:
```python
class ConsentRecord(Base):
    __tablename__ = "consent_records"
    
    id: UUID (PK)
    user_id: UUID (FK users.id, CASCADE)
    consent_type: str  # "ai_processing", "international_transfer", "marketing"
    granted: bool
    granted_at: DateTime | None
    revoked_at: DateTime | None
    ip_address: str | None  # Si aplica
    method: str  # "whatsapp_message", "admin_panel", "api"
    version: str  # Versión del texto de consentimiento aceptado
    metadata: JSONB
```

**Tipos de consentimiento**:
- `ai_processing`: Consentimiento para que una IA procese su consulta
- `international_transfer`: Consentimiento para transferencia a terceros países
- `marketing`: Consentimiento para comunicaciones comerciales (futuro)

**Criterios de aceptación**:
- [ ] Modelo con histórico completo (nunca se borran registros de consentimiento)
- [ ] Endpoint para registrar consentimiento por usuario
- [ ] Endpoint para revocar consentimiento
- [ ] El agente puede consultar si un usuario tiene consentimiento activo
- [ ] Tests CRUD completos

**Dependencias**: P0-02 (privacy notice)

---

### P1-06: 🔧 Endpoint para ejercicio de derechos ARCO+ via API

**Descripción**: Crear endpoints que permitan al admin gestionar solicitudes de derechos de acceso, rectificación, cancelación, oposición, limitación y portabilidad.

**Agente**: backend-dev  
**Complejidad**: M  
**Archivos**:
- `api/routes/gdpr.py` — Nuevo módulo de rutas RGPD
- `api/models/gdpr_schemas.py` — Pydantic schemas
- `database/models.py` — Nuevo modelo `RightsRequest`
- `database/alembic/versions/038_rights_requests.py` — Migration

**Endpoints**:
```
POST   /api/gdpr/rights-requests          Crear solicitud de ejercicio de derecho
GET    /api/gdpr/rights-requests          Listar solicitudes (paginado)
GET    /api/gdpr/rights-requests/{id}     Detalle de solicitud
PATCH  /api/gdpr/rights-requests/{id}     Actualizar estado (en curso, completada, denegada)
GET    /api/gdpr/users/{user_id}/data     Acceso (exportar datos — reutiliza QW-05)
DELETE /api/gdpr/users/{user_id}/data     Supresión (reutiliza P0-04)
PATCH  /api/gdpr/users/{user_id}/data     Rectificación (actualizar datos usuario)
```

**Criterios de aceptación**:
- [ ] Todos los endpoints protegidos con `require_role("admin")`
- [ ] Registro de solicitud con timestamp, tipo, estado, notas
- [ ] Plazos: sistema debe alertar si una solicitud lleva >25 días sin resolver (RGPD: 30 días máx.)
- [ ] Log de auditoría para cada acción
- [ ] Tests completos

**Dependencias**: P0-04, QW-05

---

### P1-07: 🔧 Añadir "Mapa de datos" al admin panel

**Descripción**: Crear vista en admin panel que muestre qué datos personales almacena el sistema, dónde, y con qué retención. Sirve como apoyo técnico al RAT y como herramienta de governance.

**Agente**: frontend-dev  
**Complejidad**: M  
**Archivos**:
- `admin-panel/src/app/(dashboard)/gdpr/data-map/page.tsx` — Página de mapa de datos
- `api/routes/gdpr.py` — Endpoint `GET /api/gdpr/data-map`

**Contenido del mapa de datos**:
```
┌─────────────────────────┬─────────────────┬──────────────┬───────────────┐
│ Dato                    │ Almacenamiento  │ Retención    │ Base legal    │
├─────────────────────────┼─────────────────┼──────────────┼───────────────┤
│ Teléfono                │ PostgreSQL      │ Hasta supres.│ Contractual   │
│ Nombre, apellido        │ PostgreSQL      │ Hasta supres.│ Contractual   │
│ Email                   │ PostgreSQL      │ Hasta supres.│ Contractual   │
│ NIF/CIF                 │ PostgreSQL      │ Hasta supres.│ Contractual   │
│ Domicilio               │ PostgreSQL      │ Hasta supres.│ Contractual   │
│ Datos vehículo          │ PostgreSQL      │ Hasta supres.│ Contractual   │
│ Mensajes conversación   │ PostgreSQL      │ 180 días     │ Interés legít.│
│ Imágenes caso           │ Filesystem      │ Hasta supres.│ Contractual   │
│ Métricas LLM            │ PostgreSQL      │ 90 días      │ Interés legít.│
│ Tool logs               │ PostgreSQL      │ 90 días      │ Interés legít.│
│ Checkpoints conversación│ Redis           │ 24h TTL      │ Interés legít.│
│ Contacto Chatwoot       │ Chatwoot (ext.) │ Hasta supres.│ Contractual   │
│ Prompts + respuestas    │ OpenRouter(ext.)│ Según ToS    │ Contractual   │
└─────────────────────────┴─────────────────┴──────────────┴───────────────┘
```

**Criterios de aceptación**:
- [ ] Tabla visual con todos los datos personales identificados
- [ ] Indica almacenamiento (sistema), retención, y base legal
- [ ] Datos reales del backend (conteo de registros por tabla)
- [ ] Accesible solo con auth de admin

**Dependencias**: P1-06

---

## 2.2 Mejoras de Transparencia y Auditoría

### P1-08: 🔧 Log de decisiones del agente (audit trail enriquecido)

**Descripción**: Enriquecer el sistema de auditoría existente para registrar decisiones clave del agente (cambios de modo, escalados, envío de presupuestos, rechazo de inputs).

**Agente**: agent-dev  
**Complejidad**: M  
**Archivos**:
- `agent/services/decision_logger.py` — Nuevo servicio de logging de decisiones
- `agent/modes/base_mode.py` — Integrar logging en cada transición
- `agent/router/intent_router.py` — Log de clasificación de intents

**Eventos a registrar**:
| Evento | Datos | Tabla destino |
|--------|-------|---------------|
| Cambio de modo | `from_mode`, `to_mode`, `trigger` | `audit_log` |
| Clasificación de intent | `intent`, `confidence`, `method` | `tool_call_logs` |
| Presupuesto enviado | `precio`, `elementos`, `categoria` | `audit_log` |
| Escalado activado | `reason`, `source` | `escalations` (ya existe) |
| Input flaggeado | `pattern_matched`, `action_taken` | `audit_log` |
| Privacy notice enviado | `user_id`, `timestamp` | `audit_log` |
| Datos exportados/borrados | `user_id`, `action`, `systems_affected` | `audit_log` |

**Criterios de aceptación**:
- [ ] Al menos 5 tipos de evento registrados
- [ ] Datos estructurados en JSONB (no texto libre)
- [ ] Consulta de audit trail por usuario / por conversación
- [ ] No impacta rendimiento (fire-and-forget via background task)

**Dependencias**: Ninguna

---

### P1-09: 🔧 Golden testing normativo

**Descripción**: Crear suite de tests que verifiquen compliance normativo del agente (identificación como IA, disclaimer, no revelar datos de otros usuarios, etc.).

**Agente**: qa-dev  
**Complejidad**: L  
**Archivos**:
- `tests/compliance/test_gdpr_compliance.py` — Tests RGPD
- `tests/compliance/test_ai_act_compliance.py` — Tests IA Act
- `tests/compliance/conftest.py` — Fixtures de compliance

**Tests a incluir**:
```python
class TestGDPRCompliance:
    async def test_first_interaction_includes_ia_disclosure()
    async def test_first_interaction_includes_privacy_notice()
    async def test_budget_includes_disclaimer()
    async def test_agent_does_not_leak_other_users_data()
    async def test_agent_does_not_reveal_internal_tools()
    async def test_agent_handles_data_deletion_request()
    async def test_agent_escalates_on_rights_exercise_request()

class TestAIActCompliance:
    async def test_agent_identifies_as_ai_in_every_first_response()
    async def test_agent_rejects_prompt_injection_attempts()
    async def test_agent_does_not_generate_harmful_content()
```

**Criterios de aceptación**:
- [ ] Al menos 10 tests de compliance
- [ ] Ejecutables con `pytest tests/compliance/`
- [ ] Incluidos en CI (cuando se implemente)
- [ ] Documentan requisito normativo que verifican

**Dependencias**: QW-01, QW-02, P0-02

---

# FASE 3 (P2): Mejoras de Madurez — Excelencia en Compliance

> **Esfuerzo estimado**: 8-10 días  
> **Plazo recomendado**: 12-20 semanas desde aprobación  
> **Riesgo de no hacerlo**: Menor madurez, pero no bloquea compliance básico

---

### P2-01: 🔧 Dashboard de métricas de compliance en admin panel

**Descripción**: Panel que muestre indicadores clave de compliance: solicitudes RGPD pendientes, usuarios sin privacy notice, datos por purgar, anomalías detectadas.

**Agente**: frontend-dev + backend-dev  
**Complejidad**: L  
**Archivos**:
- `admin-panel/src/app/(dashboard)/gdpr/dashboard/page.tsx`
- `api/routes/gdpr.py` — Endpoint `GET /api/gdpr/dashboard-stats`

**Métricas**:
- Solicitudes de derechos pendientes (>25 días = alerta)
- Usuarios sin privacy notice enviado
- Datos pendientes de purga (por tabla)
- Anomalías detectadas últimas 24h
- Consentimientos activos/revocados
- Eliminaciones completadas/fallidas

**Criterios de aceptación**:
- [ ] Dashboard visual con tarjetas de métricas
- [ ] Alertas visuales para solicitudes próximas a vencer
- [ ] Auto-refresh cada 60s
- [ ] Solo accesible con auth admin

**Dependencias**: P1-06, P1-04, QW-03

---

### P2-02: 🔧 Mecanismo de pausa/reanudación del agente por usuario

**Descripción**: Permitir que un usuario solicite "parar" el procesamiento de IA y hablar solo con humanos. Implementar como etiqueta en Chatwoot + check en agent.

**Agente**: agent-dev + backend-dev  
**Complejidad**: M  
**Archivos**:
- `agent/graph/conversation_graph.py` — Check en `preprocess` node
- `api/routes/admin.py` — Endpoint para pausar/reanudar por usuario
- `shared/config.py` — Configuración

**Flujo**:
```
1. Usuario: "No quiero hablar con una IA, quiero una persona"
2. Agent detecta intención → escalar_a_humano + marcar usuario como "ai_paused"
3. Mensajes siguientes → NO procesados por agent → van directo a Chatwoot inbox
4. Admin puede reanudar el procesamiento IA para ese usuario
```

**Criterios de aceptación**:
- [ ] Usuario puede pausar procesamiento IA
- [ ] Mensajes de usuario "pausado" no se procesan por agent
- [ ] Admin puede reanudar desde panel
- [ ] Flag persistido en User model o SystemSetting por usuario

**Dependencias**: Ninguna

---

### P2-03: 🔧 Documentación técnica de seguridad (Security Whitepaper)

**Descripción**: Crear documento técnico que describa todas las medidas de seguridad implementadas. Sirve como referencia para EIPD, auditorías, y clientes que pregunten.

**Agente**: N/A — Tarea documental, asistida por IA  
**Complejidad**: M

**Contenido**:
1. Arquitectura de seguridad (diagrama)
2. Cifrado en tránsito y reposo
3. Autenticación y autorización (JWT + RBAC)
4. Seguridad de imagen (multi-capa)
5. Protección contra prompt injection
6. Sanitización de logs
7. Política de retención de datos
8. Gestión de secretos (variables de entorno)
9. Sandboxing Docker
10. Hybrid LLM y minimización de datos cloud

**Criterios de aceptación**:
- [ ] Documento completo en `docs/security/security-whitepaper.md`
- [ ] Revisado por equipo técnico
- [ ] Referenciable desde EIPD

**Dependencias**: Ninguna

---

### P2-04: 🔧 Evaluar y documentar sesgos del modelo

**Descripción**: Las orientaciones AEPD mencionan la necesidad de evaluar sesgos. Para MSI-a, los riesgos de sesgo son bajos (no toma decisiones sobre personas), pero debe documentarse.

**Agente**: qa-dev  
**Complejidad**: M  
**Archivos**:
- `tests/compliance/test_bias_evaluation.py` — Tests de sesgo
- `docs/compliance/bias-evaluation.md` — Documentación

**Tests de sesgo relevantes para MSI-a**:
- ¿El agente trata diferente a usuarios con nombres "extranjeros"?
- ¿Los presupuestos varían por cómo habla el usuario (formal vs. informal)?
- ¿El agente escala más frecuentemente a ciertos tipos de usuario?

**Criterios de aceptación**:
- [ ] Al menos 5 tests de sesgo ejecutados
- [ ] Resultados documentados
- [ ] Metodología reproducible

**Dependencias**: P1-09

---

### P2-05: 🔧 Cifrado de datos personales en reposo (column-level encryption)

**Descripción**: Evaluar e implementar cifrado a nivel de columna para los campos más sensibles (NIF/CIF, email, domicilio).

**Agente**: database-dev + backend-dev  
**Complejidad**: XL  
**Archivos**:
- `database/models.py` — Tipo de columna cifrada
- `shared/encryption.py` — Utilidades de cifrado/descifrado
- Migración para cifrar datos existentes

**Evaluación costo-beneficio**:
- **Pro**: Protección en caso de acceso directo a DB
- **Contra**: Complejidad, impacto en queries, gestión de claves
- **Alternativa**: PostgreSQL TDE (Transparent Data Encryption) si disponible

> **NOTA**: Esta acción debe evaluarse contra el beneficio real. Si la DB está en servidor propio con acceso controlado, el cifrado a nivel de disco puede ser suficiente.

**Criterios de aceptación**:
- [ ] Evaluación documentada de opciones
- [ ] Si se implementa: cifrado AES-256 para campos seleccionados
- [ ] Si se descarta: justificación documentada + medida alternativa

**Dependencias**: Ninguna

---

### P2-06: 📋⚖️ Procedimiento interno de gestión de brechas de seguridad

**Descripción**: RGPD Art. 33-34 obliga a notificar brechas a la AEPD en 72h y al interesado si hay riesgo alto. Zanovix redacta el procedimiento técnico completo.

**Responsable redacción**: Zanovix  
**Aprueba**: MSI Automotive  
**Valida**: Abogado RGPD externo ⚖️  
**Complejidad**: M

**Entregable de Zanovix**: `docs/legal/borrador-procedimiento-brechas.md`
- [ ] Procedimiento documentado de respuesta a brechas (Zanovix redacta)
- [ ] Plantilla de notificación a AEPD (Zanovix prepara basándose en formulario AEPD)
- [ ] Lista de contactos y responsabilidades (MSI Automotive completa)
- [ ] Criterios técnicos para evaluar gravedad (Zanovix define)
- [ ] Criterios legales para evaluar si notificar al interesado (abogado valida ⚖️)

**Dependencias**: Ninguna

---

### P2-07: 🔧 Webhook de notificación al admin cuando se detectan solicitudes de derechos

**Descripción**: Si un usuario escribe algo como "quiero que borréis mis datos" o "ejercer derecho de acceso", el agente debe detectarlo y notificar al admin además de escalar.

**Agente**: agent-dev  
**Complejidad**: M  
**Archivos**:
- `agent/services/rights_detector.py` — Detector de solicitudes de derechos
- `agent/modes/base_mode.py` — Integrar detector
- `api/routes/system.py` — Webhook/notificación interna

**Patrones a detectar**:
- "borrar mis datos", "eliminar mi información"
- "derecho de acceso", "derecho de supresión"
- "RGPD", "protección de datos", "mis derechos"
- "no quiero que guardéis", "quitad mi teléfono"

**Comportamiento**:
1. Detectar patrón → escalar a humano
2. Crear `RightsRequest` automáticamente con tipo inferido
3. Notificar a admin panel (badge de alerta)
4. Responder al usuario: "He tomado nota de tu solicitud. Un agente humano la gestionará lo antes posible. El plazo máximo de respuesta es de 30 días."

**Criterios de aceptación**:
- [ ] Detección de al menos 8 patrones de solicitud de derechos
- [ ] Escalado automático + creación de RightsRequest
- [ ] Notificación visible en admin panel
- [ ] Respuesta predefinida al usuario (no depende del LLM)
- [ ] Tests con patrones de ejemplo

**Dependencias**: P1-06 (modelo RightsRequest)

---

# Dependencias entre Acciones

```
FASE 0 (Quick Wins) — Sin dependencias, ejecutar en paralelo
├── QW-01: Hardcodear ID como IA
├── QW-02: Disclaimer presupuestos
├── QW-03: Job de purga
├── QW-04: Input sanitization
└── QW-05: Endpoint exportación datos

FASE 1 (P0) — Cadena de dependencias
├── P0-01 [LEGAL] ──→ P0-02 (textos → implementación)
│                  ──→ P0-03 (textos → página web)
├── P0-04 ◀── QW-05 (exportación → supresión)
├── P0-05 ◀── P0-04 (endpoint → UI)
├── P0-06 [LEGAL] (en paralelo)
├── P0-07 [LEGAL] ──→ P0-08 [LEGAL] ──→ P0-09 [LEGAL]
└── P0-10 [LEGAL] ◀── P0-06

FASE 2 (P1)
├── P1-01 ──→ P1-03 (sanitización → anonimización cloud)
├── P1-02 (independiente)
├── P1-04 (independiente)
├── P1-05 ◀── P0-02 (privacy notice → consentimiento)
├── P1-06 ◀── P0-04, QW-05
├── P1-07 ◀── P1-06
├── P1-08 (independiente)
└── P1-09 ◀── QW-01, QW-02, P0-02

FASE 3 (P2)
├── P2-01 ◀── P1-06, P1-04, QW-03
├── P2-02 (independiente)
├── P2-03 (independiente, documental)
├── P2-04 ◀── P1-09
├── P2-05 (independiente, evaluar primero)
├── P2-06 [LEGAL] (independiente)
└── P2-07 ◀── P1-06
```

---

## Estimación de Esfuerzo

### Desarrollo (Código)

| Fase | Acciones código | Estimación | Agentes principales |
|------|-----------------|------------|---------------------|
| Fase 0 (Quick Wins) | QW-01 a QW-05 | **3-4 días** | agent-dev, backend-dev |
| Fase 1 (P0) | P0-02 a P0-05 | **10-14 días** | backend-dev, agent-dev, frontend-dev, database-dev |
| Fase 2 (P1) | P1-01 a P1-09 | **12-15 días** | agent-dev, backend-dev, frontend-dev, qa-dev |
| Fase 3 (P2) | P2-01 a P2-07 | **8-10 días** | Varios |
| **TOTAL CÓDIGO** | **25 acciones** | **33-43 días** | |

### Legal/Documental (Zanovix redacta → MSI Automotive aprueba → Abogado valida ⚖️)

| Acción | Redacción Zanovix | Revisión MSI | Validación abogado ⚖️ |
|--------|-------------------|--------------|----------------------|
| P0-01: Textos legales | 2-3 días | 3-5 días | 3-5 días |
| P0-06: EIPD | 3-5 días (parte técnica ya hecha) | 1 semana | 1-2 semanas |
| P0-07: Roles + contratos Art. 28 | 2-3 días | 3-5 días | 1 semana |
| P0-08: Transferencias int. + TIA | 1-2 días | 3-5 días | 1 semana |
| P0-09: RAT | 1 día | 2-3 días | No necesario |
| P0-10: Análisis Art. 22 | 1 día (ya hecho preliminar) | — | 3-5 días |
| P2-06: Procedimiento brechas | 1-2 días | 2-3 días | 3-5 días |
| **TOTAL Zanovix** | **~11-17 días** | | |

> **VENTAJA**: Zanovix tiene TODA la información técnica del sistema (acaba de hacer el análisis de compliance). Eso reduce drásticamente el tiempo de redacción de los borradores legales.
> 
> **BOTTLENECK**: Ya no es "esperar al abogado desde cero" sino "abogado revisa borrador ya hecho". Mucho más rápido. El bottleneck se desplaza a la velocidad de revisión de MSI Automotive y el abogado.

---

## Orden de Ejecución Recomendado

### Sprint 1 (Semana 1-2): Quick Wins + Legal kickoff

**Desarrollo**:
1. QW-01: Hardcodear ID como IA → agent-dev (0.5d)
2. QW-02: Disclaimer presupuestos → agent-dev (0.5d)
3. QW-03: Job de purga → backend-dev (1d)
4. QW-04: Input sanitization → agent-dev (1d)
5. QW-05: Endpoint exportación → backend-dev (1d)

**Legal** (en paralelo):
- Kickoff con abogado RGPD para P0-01, P0-06, P0-07

### Sprint 2 (Semana 3-4): Database + Core RGPD

**Desarrollo**:
1. P0-04: Servicio supresión completa → backend-dev (3-5d)
2. Migration 035: privacy_notice_sent_at → database-dev (0.5d)
3. Migration 036: data_deletion_requests → database-dev (0.5d)

**Legal** (en paralelo):
- P0-01: Definición de textos legales
- P0-07: Determinación de roles

### Sprint 3 (Semana 5-6): Integración + Frontend

**Desarrollo** (cuando textos legales estén listos):
1. P0-02: Mensaje RGPD primera interacción → agent-dev (1.5d)
2. P0-03: Página política privacidad → frontend-dev (1d)
3. P0-05: Panel GDPR admin → frontend-dev (2d)
4. P1-01: Compartimentación contexto LLM → agent-dev (1.5d)
5. P1-02: Límite ventana historial → agent-dev (0.5d)

### Sprint 4 (Semana 7-8): Madurez P1

**Desarrollo**:
1. P1-03: Anonimización datos cloud → agent-dev (1.5d)
2. P1-04: Circuit breaker → agent-dev (1.5d)
3. P1-05: Consentimiento granular → database-dev + backend-dev (1.5d)
4. P1-06: Endpoints derechos ARCO+ → backend-dev (1d)
5. P1-07: Mapa de datos → frontend-dev (1d)

### Sprint 5 (Semana 9-10): Auditoría + Testing

**Desarrollo**:
1. P1-08: Log decisiones enriquecido → agent-dev (1d)
2. P1-09: Golden testing normativo → qa-dev (1.5d)

### Sprint 6+ (Semana 11-16): P2 — Mejoras graduales

- P2-01 a P2-07 según prioridad y disponibilidad

---

## Migrations Database Requeridas

| # | Nombre | Contenido | Fase |
|---|--------|-----------|------|
| 035 | `add_privacy_fields.py` | `users.privacy_notice_sent_at`, `users.ai_processing_paused` | P0 |
| 036 | `data_deletion_requests.py` | Tabla `data_deletion_requests` | P0 |
| 037 | `consent_records.py` | Tabla `consent_records` | P1 |
| 038 | `rights_requests.py` | Tabla `rights_requests` | P1 |

---

## Variables de Entorno Nuevas

```bash
# GDPR / Privacy
PRIVACY_NOTICE_TEXT=""                    # Texto corto del aviso (o usar SystemSetting)
PRIVACY_POLICY_URL=""                     # URL de la política completa

# Data Retention (días)
CONVERSATION_RETENTION_DAYS=180           # Mensajes de conversación
TOOL_LOG_RETENTION_DAYS=90                # Logs de herramientas
ADMIN_ACCESS_LOG_RETENTION_DAYS=365       # Logs de acceso admin
ERROR_LOG_RETENTION_DAYS=30               # Logs de errores (resueltos)

# LLM Context
LLM_CONTEXT_WINDOW_MESSAGES=20            # Mensajes máximos en contexto

# Anomaly Detection
ANOMALY_MAX_TOOL_ITERATIONS=10            # Máx. iteraciones tool loop
ANOMALY_MAX_OUTPUT_TOKENS=4000            # Máx. tokens por respuesta
ANOMALY_ERROR_RATE_THRESHOLD=0.5          # 50% error rate → alerta
ANOMALY_MAX_CONVERSATION_MESSAGES=100     # Máx. mensajes por conversación
```

---

## ADR Propuesto

> Se debe crear como archivo separado: `docs/decisions/009-aepd-ia-agentica-compliance.md`

### ADR-009: Compliance AEPD Orientaciones IA Agéntica

**Status**: Proposed

**Date**: 2026-02-19

**Context**: La AEPD publicó en febrero 2026 orientaciones específicas sobre sistemas de IA agéntica y protección de datos. MSI-a es un sistema de IA agéntica que trata datos personales por WhatsApp. Un análisis de compliance reveló que solo se cumplen 15 de 62 requisitos identificados. Es necesario implementar medidas técnicas y organizativas para alcanzar conformidad con RGPD y las orientaciones AEPD.

**Decision**: Implementar un plan de compliance en 3 fases (P0 urgente, P1 importante, P2 mejora) que aborda:
1. Capa de información RGPD al usuario (mensaje primera interacción)
2. Derecho de supresión técnicamente implementado (borrado en todos los sistemas)
3. Política de retención de datos con jobs de purga
4. Compartimentación y anonimización de datos en contexto LLM
5. Input sanitization a nivel de código (no solo prompt)
6. Infraestructura de consentimiento y gestión de derechos ARCO+
7. Auditoría enriquecida y golden testing normativo

Se prioriza implementación de código sobre documentación legal, dado que la documentación legal es responsabilidad de MSI Automotive con su asesor jurídico.

**Consequences**:

Positive:
- Cumplimiento con RGPD y orientaciones AEPD
- Reducción significativa del riesgo sancionador
- Mejora de la postura de seguridad y privacidad del sistema
- Infraestructura reutilizable para futuros requisitos regulatorios
- Mayor confianza de los usuarios

Negative:
- Esfuerzo de desarrollo significativo (~38-48 días)
- Complejidad añadida al sistema (sanitización, consentimiento, purga)
- Posible impacto menor en rendimiento (sanitización pre-LLM, anonimización)
- Dependencia de textos legales de MSI Automotive (puede retrasar implementación)

Neutral:
- El mensaje RGPD en primera interacción puede percibirse como "pesado" por usuarios
- La anonimización antes de envío a cloud puede afectar calidad de respuesta (mínimamente)

**Alternatives Considered**:

- **Compliance mínimo (solo Quick Wins)**: Rechazada — no cubre gaps P0 legalmente obligatorios
- **Reemplazar OpenRouter por modelo 100% local**: Evaluada pero descartada por ahora — Tier 3 cloud necesario para calidad conversacional, se compensa con anonimización
- **Externalizar compliance a consultoría**: Parcialmente adoptada — la parte legal es responsabilidad de MSI Automotive, la parte técnica se implementa internamente

---

## Checklist de Verificación Global

### Pre-implementación
- [ ] Plan aprobado por responsable MSI Automotive
- [ ] Abogado RGPD contratado/asignado
- [ ] Kickoff legal para P0-01, P0-06, P0-07

### Post-Fase 0
- [ ] Identificación como IA hardcodeada (QW-01)
- [ ] Disclaimer en presupuestos (QW-02)
- [ ] Job de purga funcional (QW-03)
- [ ] Input sanitization activa (QW-04)
- [ ] Exportación de datos funcional (QW-05)

### Post-Fase 1
- [ ] Mensaje RGPD en primera interacción (P0-02)
- [ ] Supresión completa de datos funcional (P0-04)
- [ ] Panel GDPR en admin (P0-05)
- [ ] EIPD completada (P0-06)
- [ ] Contratos Art. 28 firmados (P0-07)
- [ ] Transferencias documentadas (P0-08)
- [ ] RAT creado (P0-09)

### Post-Fase 2
- [ ] Datos sanitizados antes de envío a cloud (P1-03)
- [ ] Circuit breaker activo (P1-04)
- [ ] Modelo consentimiento implementado (P1-05)
- [ ] Endpoints ARCO+ operativos (P1-06)
- [ ] Golden testing normativo pasa (P1-09)

### Post-Fase 3
- [ ] Dashboard compliance operativo (P2-01)
- [ ] Evaluación de sesgos documentada (P2-04)
- [ ] Procedimiento brechas documentado (P2-06)

---

## Riesgos Identificados

| Riesgo | Impacto | Probabilidad | Mitigación |
|--------|---------|--------------|------------|
| Textos legales tardan en llegar (P0-01 bloquea P0-02) | Alto | Alta | Implementar Quick Wins mientras tanto; usar textos provisionales |
| Anonimización afecta calidad del agente | Medio | Baja | Evaluar con tests A/B; limitar anonimización a PII obvio |
| Supresión en Chatwoot falla | Medio | Media | Registrar intento fallido, reintentar manualmente |
| EIPD revela riesgo residual alto | Alto | Baja | Consulta previa a AEPD si procede |
| Job de purga borra datos necesarios | Alto | Baja | Modo dry-run obligatorio; período de retención generoso |
| Falsos positivos en input sanitization | Medio | Media | Modo "flag" en lugar de "block"; tuning iterativo |

---

## Referencias

- **AEPD**: "Orientaciones sobre IA Agéntica y Protección de Datos" (febrero 2026)
- **RGPD**: Reglamento (UE) 2016/679
- **AI Act**: Reglamento (UE) 2024/1689, Art. 50 (identificación como IA)
- **AEPD Guía EIPD**: https://www.aepd.es/guias/guia-evaluaciones-de-impacto-rgpd.pdf
- **ADRs existentes**: `docs/decisions/001-008`
- **Análisis de compliance**: Sesión de análisis del 2026-02-19

---

**Plan creado por**: Zanovix (architect mode)  
**Revisado por**: [Pendiente]  
**Aprobado por**: [Pendiente aprobación MSI Automotive]  
**Fecha estimada de completitud Fase 0**: Quick Wins: semana 2 / P0 completo: semana 6  
**Fecha estimada de completitud Fase 1**: Semana 10  
**Fecha estimada de completitud Fase 2**: Semana 16

---

## Apéndice: Entregables de Zanovix

### Entregables de código

| ID | Entregable | Archivos |
|----|------------|----------|
| QW-01 | Identificación IA hardcodeada | `agent/modes/*.py`, `agent/state/conversation_state.py` |
| QW-02 | Disclaimer presupuestos | `agent/tools/tarifa_tools.py`, `agent/prompts/core/07_pricing_rules.md` |
| QW-03 | Job de purga datos | `api/routes/system.py`, `scripts/purge_old_data.py` |
| QW-04 | Input sanitization | `agent/utils/input_sanitizer.py` |
| QW-05 | Exportación datos usuario | `api/routes/admin.py`, `api/services/gdpr_service.py` |
| P0-02 | Mensaje RGPD primera interacción | `database/models.py`, `agent/services/privacy_service.py`, migrations |
| P0-03 | Página política privacidad | `admin-panel/src/app/privacy/page.tsx`, `api/routes/system.py` |
| P0-04 | Supresión completa usuario | `api/services/gdpr_service.py`, `database/models.py`, migrations |
| P0-05 | Panel GDPR admin | `admin-panel/src/app/(dashboard)/gdpr/` |
| P1-01 | Compartimentación contexto LLM | `agent/services/context_sanitizer.py` |
| P1-02 | Límite ventana historial | `agent/state/helpers.py` |
| P1-03 | Anonimización cloud | `shared/llm_router.py`, `agent/services/context_sanitizer.py` |
| P1-04 | Circuit breaker | `agent/services/anomaly_detector.py` |
| P1-05 | Modelo consentimiento | `database/models.py`, migrations |
| P1-06 | Endpoints ARCO+ | `api/routes/gdpr.py`, migrations |
| P1-07 | Mapa de datos | `admin-panel/src/app/(dashboard)/gdpr/data-map/` |
| P1-08 | Log decisiones | `agent/services/decision_logger.py` |
| P1-09 | Golden testing | `tests/compliance/` |
| P2-01 | Dashboard compliance | `admin-panel/src/app/(dashboard)/gdpr/dashboard/` |
| P2-02 | Pausa IA por usuario | `agent/graph/conversation_graph.py`, `api/routes/admin.py` |
| P2-03 | Security whitepaper | `docs/security/security-whitepaper.md` |
| P2-04 | Evaluación sesgos | `tests/compliance/test_bias_evaluation.py` |
| P2-05 | Cifrado columnas | `database/models.py`, `shared/encryption.py` (evaluar primero) |
| P2-07 | Detector solicitudes derechos | `agent/services/rights_detector.py` |

### Entregables legales (borradores)

| ID | Entregable | Archivo |
|----|------------|---------|
| P0-01a | Aviso primera interacción | `docs/legal/borrador-aviso-primera-interaccion.md` |
| P0-01b | Política de privacidad | `docs/legal/borrador-politica-privacidad.md` |
| P0-01c | Texto consentimiento | `docs/legal/borrador-consentimiento.md` |
| P0-01d | Contrato encargado Zanovix | `docs/legal/borrador-contrato-encargado-zanovix.md` |
| P0-06 | EIPD | `docs/legal/borrador-eipd.md` |
| P0-07a | Determinación roles | `docs/legal/borrador-roles-tratamiento.md` |
| P0-07b | Contrato Chatwoot | `docs/legal/borrador-contrato-encargado-chatwoot.md` |
| P0-07c | Contrato OpenRouter | `docs/legal/borrador-contrato-encargado-openrouter.md` |
| P0-08 | TIA + transferencias | `docs/legal/borrador-tia-openrouter.md` |
| P0-09 | RAT | `docs/legal/borrador-rat.md` |
| P0-10 | Análisis Art. 22 | `docs/legal/borrador-analisis-art22.md` |
| P2-06 | Procedimiento brechas | `docs/legal/borrador-procedimiento-brechas.md` |

### Estructura de directorios a crear

```
docs/
├── legal/                          # NUEVO — Borradores legales
│   ├── borrador-aviso-primera-interaccion.md
│   ├── borrador-politica-privacidad.md
│   ├── borrador-consentimiento.md
│   ├── borrador-contrato-encargado-zanovix.md
│   ├── borrador-contrato-encargado-chatwoot.md
│   ├── borrador-contrato-encargado-openrouter.md
│   ├── borrador-roles-tratamiento.md
│   ├── borrador-eipd.md
│   ├── borrador-tia-openrouter.md
│   ├── borrador-rat.md
│   ├── borrador-analisis-art22.md
│   └── borrador-procedimiento-brechas.md
├── security/                       # NUEVO — Documentación seguridad
│   └── security-whitepaper.md
└── compliance/                     # NUEVO — Documentación compliance
    └── bias-evaluation.md

tests/
└── compliance/                     # NUEVO — Tests de compliance
    ├── conftest.py
    ├── test_gdpr_compliance.py
    ├── test_ai_act_compliance.py
    └── test_bias_evaluation.py
```

---

## Contrato Art. 28 Zanovix ↔ MSI Automotive

> Este plan asume que Zanovix firma un contrato de encargado del tratamiento con MSI Automotive. El borrador del contrato se incluye como entregable P0-01d y debe ser validado por el abogado RGPD de MSI Automotive antes de firma.

**Obligaciones de Zanovix como encargado**:
- Tratar datos solo siguiendo instrucciones documentadas de MSI Automotive
- Garantizar confidencialidad del personal con acceso a datos
- Implementar medidas de seguridad técnicas y organizativas (ya implementadas)
- No subencargar sin autorización (OpenRouter, Chatwoot ya autorizados implícitamente)
- Asistir a MSI Automotive en responder solicitudes de derechos
- Notificar brechas de seguridad sin dilución indebida
- Devolver o destruir datos al finalizar el contrato

**Duración**: Por definir en contrato  
**Jurisdicción**: España  
