# ADR-009: Compliance AEPD Orientaciones IA Agéntica y Protección de Datos

## Status

Proposed

## Date

2026-02-19

## Context

La AEPD (Agencia Española de Protección de Datos) publicó en febrero 2026 orientaciones específicas sobre sistemas de IA agéntica y protección de datos personales. MSI-a es un sistema de IA agéntica que:

- Toma decisiones autónomas en conversaciones (modo PRESUPUESTO, EVALUACION_GATEWAY)
- Trata datos personales (teléfono, nombre, NIF/CIF, email, domicilio, datos de vehículos)
- Interactúa con servicios de terceros (Chatwoot, OpenRouter/DeepSeek, Qdrant)
- Opera con supervisión humana limitada (escalado solo bajo demanda)

Un análisis de compliance reveló que MSI-a cumple solo **15 de 62 requisitos** identificados (24%), con **31 requisitos no cumplidos** y **16 parcialmente cumplidos**.

Los gaps más críticos son:
1. Sin capa de información RGPD al usuario (Art. 13-14 RGPD)
2. Sin derecho de supresión implementado (Art. 17 RGPD)
3. Sin EIPD (Art. 35 RGPD)
4. Sin documentación de transferencias internacionales (Cap. V RGPD)
5. Sin contratos formales con encargados del tratamiento (Art. 28 RGPD)

## Decision

Implementar un plan de compliance en **3 fases priorizadas** (P0 urgente, P1 importante, P2 mejora).

### Modelo de responsabilidad adoptado:

| Rol | Quién | Responsabilidad |
|-----|-------|----------------|
| **Responsable del tratamiento** | MSI Automotive S.L. | Siempre (Art. 24 RGPD). Aprueba, firma, responde ante AEPD. |
| **Encargado del tratamiento** | Zanovix (agencia) | Desarrollo, mantenimiento, y **redacción de borradores legales** |
| **Validación jurídica** | Abogado RGPD externo | Valida EIPD, contratos Art. 28, bases legitimadoras |

**Decisión clave**: Zanovix (como agencia de desarrollo y encargado del tratamiento) se encarga de redactar **TODOS los borradores legales**. Esto se justifica porque:
- Zanovix tiene todo el contexto técnico del sistema (acaba de realizar el análisis de compliance)
- Conoce los flujos de datos, las tablas, las integraciones
- Puede preparar documentos técnicos completos que el abogado solo tiene que validar, no escribir desde cero
- Reduce tiempo y coste vs. consultoría RGPD externa que tendría que investigar el sistema

**Flujo de trabajo**:
1. Zanovix redacta borradores en `docs/legal/borrador-*.md`
2. MSI Automotive revisa y da feedback
3. Abogado RGPD valida jurídica de documentos críticos (⚖️)
4. MSI Automotive aprueba y firma

### Cambios técnicos principales:

1. **Mensaje RGPD en primera interacción**: Informar a usuarios sobre responsable, finalidad, derechos y enlace a política de privacidad. Implementado a nivel de código (no depende del LLM).

2. **Derecho de supresión completo**: Servicio que borra datos de un usuario en PostgreSQL, Redis, Chatwoot, y filesystem. Modelo `DataDeletionRequest` para auditoría.

3. **Jobs de retención/purga**: Implementar purga real de datos con los períodos ya configurados (`LLM_METRICS_RETENTION_DAYS`) y nuevos períodos para conversaciones, logs, etc.

4. **Compartimentación de datos en contexto LLM**: Política formal de qué datos personales se incluyen en el contexto enviado a cada tier del LLM. Anonimización de PII antes de envío a Tier 3 (cloud).

5. **Input sanitization a nivel de código**: Detección de prompt injection por regex antes de enviar al LLM, como complemento al prompt de seguridad.

6. **Infraestructura RGPD**: Modelos `ConsentRecord` y `RightsRequest`, endpoints ARCO+, panel de gestión en admin.

7. **Identificación como IA hardcodeada**: No depender del LLM para cumplir Art. 50 AI Act.

### Documentos legales que redacta Zanovix:

- `docs/legal/borrador-aviso-primera-interaccion.md`
- `docs/legal/borrador-politica-privacidad.md`
- `docs/legal/borrador-consentimiento.md`
- `docs/legal/borrador-contrato-encargado-zanovix.md`
- `docs/legal/borrador-contrato-encargado-chatwoot.md`
- `docs/legal/borrador-contrato-encargado-openrouter.md`
- `docs/legal/borrador-roles-tratamiento.md`
- `docs/legal/borrador-eipd.md`
- `docs/legal/borrador-tia-openrouter.md`
- `docs/legal/borrador-rat.md`
- `docs/legal/borrador-analisis-art22.md`
- `docs/legal/borrador-procedimiento-brechas.md`

### Plan detallado:

Ver `docs/plans/active/aepd-ia-agentica-compliance.md`

## Consequences

### Positive

- Cumplimiento con RGPD y orientaciones AEPD sobre IA agéntica
- Reducción significativa del riesgo sancionador (hasta 20M€ o 4% facturación)
- Mejora de la postura de seguridad y privacidad del sistema
- Infraestructura reutilizable para futuros requisitos regulatorios
- Mayor confianza de los usuarios en el sistema
- **Zanovix tiene todo el contexto técnico → borradores listos en días, no semanas**
- **Coste reducido vs. consultoría RGPD externa**
- **Contrato Art. 28 formaliza relación Zanovix ↔ MSI Automotive**

### Negative

- Esfuerzo de desarrollo significativo (~33-43 días distribuidos en 16 semanas)
- Esfuerzo adicional de redacción legal para Zanovix (~11-17 días)
- Complejidad añadida al sistema (sanitización, consentimiento, purga, modelos nuevos)
- 4 nuevas tablas en base de datos
- Posible impacto menor en rendimiento (sanitización pre-LLM ~5ms, anonimización)
- Zanovix pasa a ser formalmente **encargado del tratamiento** con obligaciones RGPD asociadas
- Mensaje RGPD en primera interacción puede percibirse como "pesado" por usuarios

### Neutral

- El análisis reveló que MSI-a ya cumple bien en seguridad técnica (imagen, logs, Docker) — estas áreas requieren poco trabajo adicional
- La anonimización antes de envío a cloud es selectiva (solo PII obvio: teléfonos, NIFs, emails, matrículas) — impacto mínimo en calidad conversacional
- Las orientaciones AEPD no son vinculantes legalmente, pero anticipan el criterio sancionador de la autoridad

## Alternatives Considered

### Alternative A: Compliance mínimo (solo Quick Wins)

Implementar solo las mejoras rápidas (identificación IA, disclaimer, purga) sin abordar gaps P0.

**Rechazada**: No cubre requisitos legalmente obligatorios (información al usuario, derecho de supresión). Riesgo sancionador intacto.

### Alternative B: Reemplazar OpenRouter por modelo 100% local

Eliminar Tier 3 (cloud) y usar solo Ollama para todo el procesamiento, eliminando transferencias internacionales.

**Evaluada pero descartada**: Tier 3 (deepseek-chat via OpenRouter) es necesario para calidad conversacional. Modelos locales (qwen2.5:3b, llama3:8b) no alcanzan la calidad necesaria para conversaciones complejas. Se compensa con anonimización pre-envío (P1-03).

### Alternative C: Contratar consultoría RGPD externa para todo lo legal

Externalizar toda la parte documental/legal a una consultoría RGPD.

**Rechazada**: 
- Mayor coste (consultoría tendría que investigar el sistema desde cero)
- Mayor tiempo (semana vs. días para borradores)
- Zanovix ya tiene todo el contexto técnico necesario
- Se mantiene en modelo híbrido: Zanovix redacta + abogado valida

### Alternative D: MSI Automotive hace todo lo legal internamente

**No viable**: MSI Automotive no tiene recursos técnicos para documentar flujos de datos, inventario de tablas, análisis técnico de riesgos.

## References

- AEPD: "Orientaciones sobre IA Agéntica y Protección de Datos" (febrero 2026)
- RGPD: Reglamento (UE) 2016/679
- AI Act: Reglamento (UE) 2024/1689, Art. 50
- Plan de implementación: `docs/plans/active/aepd-ia-agentica-compliance.md`
- AEPD Guía EIPD: https://www.aepd.es/guias/guia-evaluaciones-de-impacto-rgpd.pdf
- AEPD Modelos Art. 28: https://www.aepd.es/documentos/modelo-contratos-encargado-tratamiento.pdf
