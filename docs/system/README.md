---
titulo: Mapa de docs/system/ — estructura agente-céntrica
ambito: meta
ultima_verificacion_commit:
ultima_verificacion_fecha:
---

# docs/system/ — mapa del vault

Este directorio es la **fuente de verdad viva** del sistema MSI-a en lenguaje de negocio. La estructura está organizada por **capacidad de negocio**, no por componente técnico del stack.

Principio rector: **dominio sobre stack**. El agente conversacional es la joya del producto — todo lo demás (API, panel, base de datos, colas) son soportes alrededor. La jerarquía de esta carpeta refleja esa realidad.

## Estructura objetivo

```
docs/system/
├── 00-overview.md                    ← visión general del sistema
├── 00-capacidades.md                 ← qué se puede / no se puede construir hoy
├── 99-protocolo-cambios.md           ← Arquitecto ↔ Ingeniero ↔ Owner
├── README.md                         ← estás acá
│
├── core/                             ← ENTIDADES DE NEGOCIO
│   ├── clientes/                     ← User WhatsApp: identidad, tipo, sync Chatwoot↔DB
│   ├── conversaciones/               ← ConversationHistory: unicidad, ciclo, vínculo DraftQuote
│   ├── expedientes/                  ← Case: 6 sub-modos, transiciones, persistencia PG+Redis
│   ├── catalogo/                     ← categorías, tiers, elementos, variantes, servicios, warnings
│   ├── tarifas/                      ← fórmula base + elementos + servicios + IVA
│   ├── presupuestos/                 ← DraftQuote: ciclo pre-confirmación, rehidratación
│   ├── adjuntos/                     ← imágenes vs PDFs (HOME CANÓNICO), MIME end-to-end
│   └── documentacion-requerida/      ← sistema dual de warnings (M2M)
│
├── agente/                           ← LA JOYA — dominio conversacional top-level
│   ├── modos/                        ← PRE_EXPEDIENTE, EXPEDIENTE, ESCALATION (+ COMPLETED)
│   ├── flujos/
│   │   ├── pre-expediente/           ← educación + pricing (DISCOVERY, PRICING, POST_PRICE)
│   │   ├── expediente/               ← recolección formal (subgrafo, 6 sub-modos)
│   │   └── escalado/                 ← handoff humano (flujo conversacional + técnico unificado)
│   ├── herramientas/                 ← catálogo de tools por modo
│   ├── prompts/                      ← mapa de prompts por fase/sub-modo
│   ├── estado/                       ← ConversationState, reducers, Redis checkpointer
│   ├── router/                       ← clasificador híbrido de intents (11 intents, 2-tier)
│   └── runtime/                      ← EntityExtraction, DigressionManager, LangGraph nodes
│
├── modulos/                          ← CASOS DE USO NO-AGENTE
│   ├── facturacion/                  ← Stripe SEPA mensual operador↔MSI (NO confundir con tarifas/)
│   └── rag-regulatorio/              ← pipeline parcialmente desmantelado
│
├── infra/                            ← PLOMERÍA TÉCNICA
│   ├── canal-whatsapp/               ← Chatwoot webhook, ventana 24h, templates, panic button
│   ├── llm-router/                   ← 2-tier Ollama + OpenRouter, TaskType, fallback
│   ├── persistencia/                 ← Redis Streams + checkpointer + Postgres + Alembic
│   ├── workers/                      ← image-batch, case-lifecycle, billing, doc_processor
│   ├── observabilidad/               ← turn telemetry, token tracking, validation metrics
│   ├── seguridad-adjuntos/           ← SSRF, validate_url, validate_image_full, pikepdf
│   ├── auth-rbac/                    ← JWT, require_role, operator/admin
│   └── deploy/                       ← docker-compose, SSH deploy, healthchecks, backups
│
├── ui/                               ← SUPERFICIES DE PRESENTACIÓN
│   └── admin-panel/                  ← partido por función
│       ├── conversaciones.md         ← visor, escalaciones, attachments polimórficos
│       ├── catalogo.md               ← categorías, tiers, elementos, warnings
│       ├── usuarios.md               ← gestión, roles, permisos
│       ├── sistema.md                ← tokens, métricas LLM, validación agent
│       └── billing.md                ← UX del panel de facturación
│
├── _rebounds/                        ← canal Ingeniero → Arquitecto (ambigüedad/imposibilidad)
└── _demo/                            ← prototipo inicial + ciclo simulado
```

## ¿Cómo encontrás X?

| Querés... | Mirá |
|---|---|
| Entender qué es un Expediente como entidad | `core/expedientes/ciclo-de-vida.md` |
| Saber cómo conversa el agente en pre-presupuesto | `agente/flujos/pre-expediente/flujo.md` |
| Cómo escala un caso a humano (flujo + técnica) | `agente/flujos/escalado/flujo.md` — único canon |
| Reglas de adjuntos polimórficos (PDF vs imagen) | `core/adjuntos/polimorfismo.md` — único home |
| Cómo se factura al operador (Stripe SEPA) | `modulos/facturacion/flujo.md` |
| Cómo se calcula el precio al cliente | `core/tarifas/calculo.md` |
| Cómo entra un mensaje de WhatsApp | `infra/canal-whatsapp/webhook.md` |
| Cómo se responde en ventana de 24h | `infra/canal-whatsapp/respuestas-salientes.md` |
| Qué hay en ConversationState | `agente/estado/conversacional.md` |
| Catálogo de tools del agente | `agente/herramientas/{pre-expediente,expediente}.md` |
| Qué tiene el panel de administración | `ui/admin-panel/*.md` |
| Cómo corre el sistema (Docker, deploy) | `infra/deploy/procedimiento.md` + `infra/persistencia/servicios-y-deploy.md` |

## Reglas del vault

1. **Un solo home por concepto.** Cada entidad de negocio tiene exactamente un archivo canónico. Otros specs pueden referenciarla con `../` relativo, pero nunca duplicar contenido.
2. **Plantilla obligatoria** en cada spec: frontmatter (`titulo`, `ambito`, `ultima_verificacion_commit`, `ultima_verificacion_fecha`) + secciones `## Resumen`, `## Escenarios`, `## Reglas duras`, `## Mapeo al código`, `## Fuera de alcance`.
3. **Secciones sin contenido genuino** → "N/A — <razón>", no se omiten.
4. **Arquitecto-AI** es el único que escribe acá (ver `99-protocolo-cambios.md`).
5. **Ingeniero-AI** solo lee (excepción: campos `ultima_verificacion_*` al archivar).

## Migración desde la estructura anterior

Este árbol reemplaza la organización previa por componente técnico (`01-agente/`, `02-api/`, `03-admin-panel/`, `04-reglas-negocio/`, `05-infraestructura/`, `06-rag/`). Para el mapeo archivo-a-archivo y razones del cambio, ver commit de merge `docs-system-agente-centrico-split` y los artifacts SDD en engram (`sdd/docs-system-agente-centrico-split/*`).
