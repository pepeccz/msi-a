# Borrador: Evaluación de Impacto en Protección de Datos (EIPD)

> **Documento**: Art. 35 RGPD — Evaluación de Impacto en Protección de Datos
> **Redactado por**: Zanovix (agencia de desarrollo — parte técnica)
> **Fecha**: 2026-02-19
> **Estado**: BORRADOR — Pendiente de validación por abogado RGPD y firma MSI Automotive

---

## Parte 1: Información General

### 1.1 Identificación del tratamiento

| Campo | Valor |
|-------|-------|
| **Nombre del tratamiento** | Atención al cliente por WhatsApp con IA agéntica (MSI-a) |
| **Responsable del tratamiento** | MSI Automotive S.L. |
| **Encargado principal** | Zanovix (desarrollo y operación) |
| **DPO** | [Completar si existe] |
| **Fecha de inicio del tratamiento** | [Completar] |
| **Fecha de la EIPD** | 2026-02-19 |
| **Próxima revisión** | 2027-02-19 (anual o ante cambios significativos) |

### 1.2 Equipo responsable de la EIPD

| Rol | Nombre | Responsabilidad |
|-----|--------|----------------|
| Responsable del tratamiento | MSI Automotive S.L. | Aprobación y firma |
| Redacción técnica | Zanovix | Análisis técnico completo |
| Validación jurídica | [Abogado RGPD - pendiente] | Validación legal |
| DPO | [Si aplica] | Supervisión |

---

## Parte 2: Descripción del Tratamiento

### 2.1 Naturaleza del tratamiento

MSI-a es un **sistema de IA agéntica** que atiende a clientes de MSI Automotive a través de WhatsApp. El sistema:

- Recibe mensajes de texto e imágenes de los usuarios
- Procesa el contenido mediante modelos de lenguaje (LLM)
- Accede a bases de datos de tarifas y elementos de homologación
- Genera respuestas automatizadas
- Puede recopilar datos personales para expedientes
- Escala a agentes humanos cuando es necesario

### 2.2 Arquitectura y flujo de datos

```
Usuario WhatsApp
      │
      ▼
Meta / WhatsApp Business API
      │
      ▼
Chatwoot (Webhook)
      │
      ▼
MSI-a API (FastAPI)
      │
      ▼
Redis Streams (cola de mensajes)
      │
      ▼
MSI-a Agent (LangGraph)
      │
      ├──► Hybrid LLM Router
      │         │
      │         ├── Tier 1: qwen2.5:3b (Ollama local — sin salida de datos)
      │         ├── Tier 2: llama3:8b (Ollama local — sin salida de datos)
      │         └── Tier 3: deepseek-chat (OpenRouter cloud ⚠️)
      │
      ├──► PostgreSQL (datos persistentes)
      ├──► Redis (caché, checkpoints conversación)
      └──► Qdrant (documentos normativos — sin datos personales)
            │
            ▼
      MSI-a API → Chatwoot → Usuario WhatsApp
```

**Punto crítico**: Solo el Tier 3 (deepseek-chat via OpenRouter) envía datos fuera de la infraestructura propia. Los Tier 1 y 2 procesan localmente.

### 2.3 Categorías de datos tratados

| Categoría | Dato | ¿Necesario? | ¿Llega a cloud? |
|-----------|------|-------------|-----------------|
| Identificativo | Nombre | Sí — personalización | Sí (nombre de pila) |
| Identificativo | Apellidos | Expediente | Solo en EXPEDIENTE |
| Identificativo | Teléfono | Identificación usuario | No (sanitizado en logs) |
| Identificativo | NIF/CIF | Expediente | ⚠️ Riesgo — anonimizar |
| Contacto | Email | Expediente | ⚠️ Riesgo — anonimizar |
| Contacto | Dirección | Expediente | ⚠️ Riesgo — anonimizar |
| Vehículo | Marca/modelo | Presupuesto | Sí (no personal) |
| Vehículo | Matrícula | Expediente | ⚠️ Riesgo — anonimizar |
| Vehículo | Bastidor | Expediente | ⚠️ Riesgo — anonimizar |
| Comunicación | Mensajes conversación | Contexto IA | Parcialmente |

### 2.4 Propósitos del tratamiento

1. **Atención de consultas**: Responder preguntas sobre homologación de vehículos
2. **Elaboración de presupuestos**: Calcular costes orientativos de homologación
3. **Gestión de expedientes**: Recopilar datos para iniciar expedientes
4. **Mejora del sistema**: Métricas de uso (sin identificación de usuarios)

### 2.5 Encargados y destinatarios

| Destinatario | Rol | País | Datos que recibe |
|--------------|-----|------|------------------|
| Zanovix | Encargado | España | Todos (acceso técnico) |
| Chatwoot | Encargado | [Completar] | Mensajes + contactos |
| OpenRouter/DeepSeek | Encargado | EE.UU./China | Prompts conversación |
| [Hosting] | Encargado | [Completar] | Todos (infraestructura) |

---

## Parte 3: Evaluación de Necesidad y Proporcionalidad

### 3.1 ¿Es necesario el tratamiento?

| Criterio | Evaluación |
|----------|------------|
| **Finalidad legítima** | ✅ Sí. Atención al cliente para servicios de homologación es actividad legítima |
| **Base jurídica** | ✅ Ejecución de contrato (Art. 6.1.b) y medidas precontractuales |
| **Adecuación** | ✅ El sistema es adecuado para la finalidad |
| **Necesidad** | ✅ Los datos tratados son necesarios para la finalidad |
| **Proporcionalidad** | ✅ No se tratan más datos de los estrictamente necesarios |

### 3.2 Minimización de datos

| Dato | ¿Estrictamente necesario? | Mitigación si excesivo |
|------|--------------------------|----------------------|
| Nombre | ✅ Sí — personalización conversacional | — |
| Teléfono | ✅ Sí — identificación del usuario | No se usa en conversación IA |
| Email | ⚠️ Solo en EXPEDIENTE | Recoger solo en modo EXPEDIENTE |
| NIF/CIF | ⚠️ Solo en EXPEDIENTE | Recoger solo en modo EXPEDIENTE |
| Dirección | ⚠️ Solo en EXPEDIENTE | Recoger solo en modo EXPEDIENTE |
| Matrícula | ⚠️ Solo en EXPEDIENTE | Recoger solo en modo EXPEDIENTE |
| Historial mensajes completo | ⚠️ Riesgo retención excesiva | Limitar a últimos N mensajes (P1-02) |

### 3.3 Calidad de los datos

- El sistema recoge datos directamente del interesado → alta calidad
- No enriquece perfiles con fuentes externas
- No realiza inferencias sobre categorías especiales de datos
- Logs sanitizados (teléfono anonimizado)

---

## Parte 4: Evaluación de Riesgos

### 4.1 Metodología

Metodología basada en:
- AEPD: "Orientaciones sobre IA Agéntica y Protección de Datos" (febrero 2026)
- ENISA: "Data Protection Engineering"
- ISO/IEC 29134:2017

Escala de impacto: 1 (insignificante) — 4 (máximo)
Escala de probabilidad: 1 (muy improbable) — 4 (muy probable)
Riesgo = Impacto × Probabilidad

### 4.2 Inventario de riesgos identificados

| ID | Riesgo | Impacto | Prob. | Riesgo bruto | Medidas existentes | Riesgo residual |
|----|--------|---------|-------|-------------|-------------------|-----------------|
| R01 | Acceso no autorizado a conversaciones de usuarios | 3 | 2 | 6 | Auth JWT+RBAC, cifrado TLS | **Medio (4)** |
| R02 | Fuga de datos personales a OpenRouter/DeepSeek | 3 | 3 | 9 | Hybrid LLM (Tier 3 solo para conversaciones), plan anonimización | **Medio (6)** |
| R03 | Inyección de prompts — acceso a datos de otros usuarios | 4 | 2 | 8 | Prompts seguridad, validación input, compartimentación | **Medio (4)** |
| R04 | Retención excesiva de datos (conversaciones sin purgar) | 3 | 4 | 12 | Config retención (no implementada aún) | **Alto (9)** |
| R05 | Envenenamiento de memoria RAG con datos personales | 2 | 2 | 4 | Solo documentos normativos en RAG, sin datos usuarios | **Bajo (2)** |
| R06 | Exfiltración shadow-leak por consultas fragmentadas | 3 | 2 | 6 | Prompts seguridad | **Medio (4)** |
| R07 | Transferencia internacional sin garantías (DeepSeek/China) | 4 | 3 | 12 | Plan TIA + SCCs | **Alto (8)** |
| R08 | Vulneración de derechos por falta de mecanismo supresión | 4 | 4 | 16 | No existe aún — CRÍTICO | **Crítico (12)** |
| R09 | Falta de transparencia al usuario (no informado de IA) | 3 | 3 | 9 | Prompt identidad (no hardcodeado) | **Medio (6)** |
| R10 | Decisión automatizada con efecto significativo | 3 | 2 | 6 | Presupuestos orientativos, escalado disponible | **Bajo (3)** |
| R11 | Perfilado de usuarios mediante logs acumulados | 3 | 3 | 9 | Logs sanitizados parcialmente | **Medio (6)** |
| R12 | Acceso a datos de terceros en fotos de documentos | 3 | 3 | 9 | Validación imagen multi-capa | **Medio (4)** |
| R13 | Fallo del sistema sin plan de contingencia documentado | 3 | 2 | 6 | Escalado a humano, Docker restart | **Bajo (3)** |
| R14 | Sesgo de automatización del agente humano supervisor | 2 | 3 | 6 | N/A — riesgo organizativo | **Medio (4)** |
| R15 | Brecha de seguridad sin notificación en plazo (72h) | 4 | 2 | 8 | Sin procedimiento documentado aún | **Alto (6)** |

### 4.3 Riesgos críticos y altos — Detalle

#### R04 — Retención excesiva de datos ⚠️ ALTO

**Descripción**: Las conversaciones y mensajes en PostgreSQL no tienen política de purga activa implementada. Los datos se acumulan indefinidamente.

**Impacto potencial**: Conservación de datos más allá del plazo necesario. Infracción Art. 5.1.e RGPD (limitación del plazo de conservación).

**Medidas propuestas**:
- QW-03 del plan: Job de purga con retención configurable (180 días mensajes)
- Retención automática con scripts de mantenimiento

**Responsable implementación**: Zanovix (backend-dev)
**Plazo**: Sprint 1 (Semana 1-2)

---

#### R07 — Transferencia internacional sin garantías ⚠️ ALTO

**Descripción**: DeepSeek (via OpenRouter) puede procesar datos en China. China no tiene decisión de adecuación de la Comisión Europea.

**Impacto potencial**: Infracción Art. 46 RGPD. Datos de ciudadanos europeos expuestos a jurisdicción china sin garantías equivalentes.

**Medidas propuestas**:
- P0-08 del plan: TIA + SCCs con OpenRouter
- P1-03 del plan: Anonimización de PII antes del envío a Tier 3
- Alternativa: Cambiar a proveedor con servidores en UE

**Responsable**: Zanovix (técnico) + abogado RGPD (SCCs) + MSI Automotive (decisión)
**Plazo**: Sprint 2-3

---

#### R08 — Sin mecanismo de supresión ⚠️ CRÍTICO

**Descripción**: No existe ningún mecanismo técnico para borrar TODOS los datos de un usuario (PostgreSQL + Redis + Chatwoot + archivos). Imposible atender el Art. 17 RGPD en la práctica.

**Impacto potencial**: Infracción directa del derecho de supresión. Sanción AEPD hasta 20M€. Daño reputacional.

**Medidas propuestas**:
- P0-04 del plan: Servicio de supresión cascada en todos los sistemas
- P0-05 del plan: Panel de gestión de derechos en admin

**Responsable implementación**: Zanovix (backend-dev)
**Plazo**: Sprint 2-3 (prioritario)

---

#### R09 — Falta de identificación como IA ⚠️ MEDIO-ALTO

**Descripción**: La identificación del agente como sistema de IA solo existe en el prompt del LLM. Si el LLM falla o ignora la instrucción, el usuario no sabe que habla con una IA. Infringe Art. 50 AI Act (Reglamento (UE) 2024/1689).

**Medidas propuestas**:
- QW-01 del plan: Identificación hardcodeada a nivel de código
- P0-02 del plan: Mensaje RGPD en primera interacción

**Responsable implementación**: Zanovix (agent-dev)
**Plazo**: Sprint 1 (inmediato)

---

### 4.4 Matriz de riesgo

```
        IMPACTO
         4 |     | R07 |     | R08 |
         3 | R13 | R01 | R06 | R04 |
    P    2 | R05 | R10 | R14 | R15 |
    R    1 |     | R02 |R09,11|R03,12|
    O    --+-----+-----+-----+-----+
    B       1     2     3     4
    A      MUY   BAJA  MEDIA ALTA
    B    IMPROBABLE
    .
```

---

## Parte 5: Medidas para Mitigar los Riesgos

### 5.1 Medidas ya implementadas ✅

| Medida | Riesgos mitigados |
|--------|------------------|
| Autenticación JWT + RBAC | R01 |
| Cifrado TLS en comunicaciones | R01 |
| Sanitización de logs (sanitize_phone) | R11 |
| Sistema de escalado a humano (escalar_a_humano) | R10, R13 |
| Validación multi-capa de imágenes (SSRF, magic numbers) | R12 |
| Prompts de seguridad (01_security.md) | R03, R06, R09 |
| Hybrid LLM (prioridad Ollama local) | R02, R07 |
| Sandboxing Docker | R01 |
| Whitelist de herramientas por modo | R03 |
| Tool logging persistente | R01, R11 |

### 5.2 Medidas planificadas (del plan de compliance)

| ID Plan | Medida | Riesgos mitigados | Prioridad | Plazo |
|---------|--------|-------------------|-----------|-------|
| QW-01 | Identificación IA hardcodeada | R09 | P0 | Sprint 1 |
| QW-02 | Disclaimer en presupuestos | R10 | P0 | Sprint 1 |
| QW-03 | Job de purga automática | R04 | P0 | Sprint 1 |
| QW-04 | Input sanitization código | R03 | P0 | Sprint 1 |
| P0-02 | Mensaje RGPD primera interacción | R09 | P0 | Sprint 3 |
| P0-04 | Servicio supresión completa | R08 | P0 | Sprint 2-3 |
| P0-08 | TIA + SCCs OpenRouter | R07 | P0 | Sprint 2-3 |
| P1-01 | Compartimentación contexto LLM | R02, R03 | P1 | Sprint 3-4 |
| P1-03 | Anonimización PII cloud | R02, R07 | P1 | Sprint 4 |
| P1-04 | Circuit breaker | R13 | P1 | Sprint 4 |
| P1-08 | Audit trail enriquecido | R01, R11 | P1 | Sprint 5 |
| P2-06 | Procedimiento brechas | R15 | P2 | Sprint 6+ |

### 5.3 Riesgos residuales aceptables

Tras la implementación de todas las medidas planificadas, los riesgos residuales estimados son:

| Riesgo | Nivel residual esperado | ¿Aceptable? |
|--------|------------------------|-------------|
| R01 | Bajo (2) | ✅ Sí |
| R02 | Bajo (2) | ✅ Sí (con anonimización P1-03) |
| R03 | Bajo (2) | ✅ Sí |
| R04 | Bajo (2) | ✅ Sí (con purga QW-03) |
| R07 | Medio (4) | ⚠️ Aceptable con SCCs + anonimización |
| R08 | Bajo (2) | ✅ Sí (con P0-04) |
| R09 | Bajo (1) | ✅ Sí (con QW-01 + P0-02) |
| R15 | Bajo (2) | ✅ Sí (con P2-06) |

> **Nota**: El riesgo R07 (transferencia internacional) se considera aceptable con las medidas propuestas, pero se recomienda evaluarlo periódicamente ante cambios en la situación jurídica de China.

---

## Parte 6: Consulta Previa a la AEPD

### 6.1 Evaluación de necesidad de consulta previa (Art. 36 RGPD)

La consulta previa es obligatoria cuando el riesgo residual es **alto** a pesar de las medidas adoptadas.

**Resultado**: Tras la implementación de las medidas del plan de compliance, ningún riesgo permanece en nivel "alto" o "crítico". **No se considera necesaria la consulta previa.**

**Condición**: Esta conclusión es válida siempre que se implementen las medidas de los Sprints 1-3 antes del despliegue en producción con el nuevo tratamiento.

> **⚠️ Para validación del abogado RGPD**: Revisar si esta conclusión es correcta, especialmente respecto a R07 (transferencia a China sin decisión de adecuación).

---

## Parte 7: Plan de Acción

### 7.1 Acciones prioritarias (antes de 30 días)

| Acción | Responsable | Plazo | Estado |
|--------|-------------|-------|--------|
| QW-01: Hardcodear identificación como IA | Zanovix | 7 días | ⏳ Pendiente |
| QW-02: Disclaimer en presupuestos | Zanovix | 7 días | ⏳ Pendiente |
| QW-03: Job de purga de datos | Zanovix | 14 días | ⏳ Pendiente |
| P0-04: Servicio supresión completa | Zanovix | 30 días | ⏳ Pendiente |
| P0-07: Contratos Art. 28 con encargados | Zanovix + MSI Automotive | 30 días | ⏳ Pendiente |
| P0-08: TIA + SCCs OpenRouter | Zanovix + abogado | 30 días | ⏳ Pendiente |

### 7.2 Acciones importantes (30-90 días)

| Acción | Responsable | Plazo |
|--------|-------------|-------|
| P0-02: Mensaje RGPD primera interacción | Zanovix | 45 días |
| P1-01: Compartimentación contexto LLM | Zanovix | 60 días |
| P1-03: Anonimización PII cloud | Zanovix | 75 días |
| P1-04: Circuit breaker | Zanovix | 75 días |

### 7.3 Acciones de madurez (90-180 días)

| Acción | Responsable | Plazo |
|--------|-------------|-------|
| P1-08: Audit trail enriquecido | Zanovix | 90 días |
| P2-06: Procedimiento brechas | Zanovix + MSI | 120 días |
| P1-09: Golden testing compliance | Zanovix | 90 días |

---

## Parte 8: Seguimiento y Revisión

### 8.1 Política de revisión

Esta EIPD debe revisarse:

- **Anualmente** como mínimo
- Ante cualquier **cambio significativo** en el tratamiento:
  - Nuevas categorías de datos
  - Nuevos encargados o subencargados
  - Cambio de proveedor LLM
  - Cambio de infraestructura
  - Nuevas funcionalidades del agente
  - Cambios normativos relevantes

### 8.2 Seguimiento de la implementación de medidas

| Reunión | Frecuencia | Participantes |
|---------|------------|---------------|
| Revisión de medidas en curso | Mensual | Zanovix + MSI Automotive |
| Revisión de riesgos | Trimestral | Zanovix + DPO |
| Revisión completa EIPD | Anual | Zanovix + MSI Automotive + abogado |

---

## Parte 9: Conclusión y Aprobación

### 9.1 Conclusión

El tratamiento de datos personales realizado por MSI-a **puede llevarse a cabo** con las medidas de seguridad existentes y las planificadas, siempre que:

1. Se implementen las medidas P0 del plan de compliance en los plazos indicados
2. Se firmen los contratos Art. 28 con todos los encargados
3. Se complete la TIA para las transferencias internacionales
4. Se implemente el aviso al usuario en primera interacción

**Riesgo residual global tras implementación**: MEDIO-BAJO — Aceptable

### 9.2 Firmas de aprobación

| Rol | Nombre | Fecha | Firma |
|-----|--------|-------|-------|
| Responsable del tratamiento (MSI Automotive) | | | |
| DPO / Asesor de protección de datos | | | |
| Validación jurídica (abogado RGPD) | | | |

---

## Apéndice A: Artículos RGPD aplicables

| Artículo | Contenido | Relevancia |
|----------|-----------|------------|
| Art. 5 | Principios del tratamiento | Todos los principios aplicables |
| Art. 6 | Licitud del tratamiento | Bases jurídicas |
| Art. 13 | Información al interesado | Deber de informar |
| Art. 17 | Derecho de supresión | Mecanismo técnico requerido |
| Art. 22 | Decisiones automatizadas | Evaluar si aplica |
| Art. 25 | Privacidad por diseño | Principio rector |
| Art. 28 | Encargado del tratamiento | Contratos con encargados |
| Art. 30 | Registro de actividades | RAT obligatorio |
| Art. 32 | Seguridad del tratamiento | Medidas técnicas |
| Art. 33-34 | Notificación de brechas | Procedimiento 72h |
| Art. 35 | EIPD | Este documento |
| Art. 46 | Transferencias internacionales | SCCs para China |

## Apéndice B: Documentos relacionados

| Documento | Ubicación |
|-----------|-----------|
| Política de privacidad | docs/legal/borrador-politica-privacidad.md |
| RAT | docs/legal/borrador-rat.md |
| Contrato encargado Zanovix | docs/legal/borrador-contrato-encargado-zanovix.md |
| Roles de tratamiento | docs/legal/borrador-roles-tratamiento.md |
| TIA OpenRouter | docs/legal/borrador-tia-openrouter.md |
| Análisis Art. 22 | docs/legal/borrador-analisis-art22.md |
| Plan de compliance | docs/plans/active/aepd-ia-agentica-compliance.md |
| ADR-009 | docs/decisions/009-aepd-ia-agentica-compliance.md |

## Apéndice C: Referencias normativas

- RGPD: Reglamento (UE) 2016/679
- LOPDGDD: Ley Orgánica 3/2018
- AI Act: Reglamento (UE) 2024/1689 (Art. 50 — identificación como IA)
- AEPD: "Orientaciones sobre IA Agéntica y Protección de Datos" (febrero 2026)
- AEPD: Guía sobre evaluaciones de impacto en protección de datos
- ENISA: "Guidelines on Assessing Personal Data Breaches"
- ISO/IEC 29134:2017: Privacy impact assessment — Guidelines

---

**Notas del abogado RGPD**:
> [Espacio reservado para observaciones del abogado]

**Fecha de aprobación**: _______________
