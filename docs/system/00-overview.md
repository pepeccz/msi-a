---
titulo: Vision general del sistema MSI-a
ambito: meta
ultima_verificacion_commit:
ultima_verificacion_fecha:
---

# Vision general del sistema MSI-a

## Qué es esto

Este directorio — `docs/system/` — es **la fuente de verdad viva** de lo que hace el sistema MSI-a hoy, escrita en lenguaje de negocio. No es documentación histórica, no es una guía de estilo de código: es el espejo actual del comportamiento del producto.

Si el documento dice que el bot hace X, el código hace X. Si el código hace Y pero el documento sigue diciendo X, **el documento tiene prioridad** y el código debe actualizarse.

## Qué NO es

- **No es** `docs/decisions/` → eso guarda *por qué* tomamos decisiones arquitectónicas (ADRs, inmutable, histórico).
- **No es** `docs/coding-standards/` → eso guarda *cómo* se escribe código en este proyecto (guías técnicas).
- **No es** un manual de usuario.
- **No es** un plan de producto futuro.

## Para quién

- **Dueño del producto** (no-programador): lee estos archivos para entender qué hace su sistema. Edita estos archivos cuando quiere cambiar comportamiento.
- **Arquitecto-AI**: edita estos archivos traduciendo peticiones de negocio a spec concreto.
- **Ingeniero-AI**: lee estos archivos como briefing antes de tocar cualquier código. NUNCA los edita (excepto el campo `ultima_verificacion_*` tras archivar un cambio).

## Sistema dual de agentes

Los archivos de `docs/system/` son el **contrato** entre dos roles de IA:

```
┌─────────────────┐         docs/system/**          ┌─────────────────┐
│                 │ ─────────────────────────────→  │                 │
│  Arquitecto-AI  │     (spec commits, rebounds)    │  Ingeniero-AI   │
│                 │ ←─────────────────────────────  │                 │
│  escribe docs   │         _rebounds/              │  escribe código │
└─────────────────┘                                 └─────────────────┘
       │                                                       │
       │              Owner (pepe)                             │
       ▼                                                       ▼
  Conversa con                                          Recibe órdenes
  Arquitecto en                                         del owner
  lenguaje CEO                                         "implementa X"
```

- **Arquitecto** conversa con el owner, traduce deseo de negocio a spec actualizado, commitea en `docs/system/**`. No toca código.
- **Ingeniero** lee el diff del spec, implementa el cambio en código/tests/infra, commitea. No toca specs (excepto frontmatter `ultima_verificacion_*`).
- Canal único de comunicación entre ambos: commits de spec + carpeta `_rebounds/`.

Ver `99-protocolo-cambios.md` para el protocolo completo.

## Mapa del sistema (alto nivel)

MSI-a es un sistema de atención al cliente por WhatsApp para **MSI Automotive** (homologación de vehículos). Componentes:

| Componente | Qué hace | Documentado en |
|------------|----------|----------------|
| **Core (entidades)** | Cliente, Expediente, Catálogo, Tarifa, Adjuntos | `core/` |
| **Agente conversacional (LA JOYA)** | Procesa conversaciones WhatsApp | `agente/` |
| **Módulos** | Facturación, RAG regulatorio | `modulos/` |
| **Infraestructura** | Canal WhatsApp, LLM router, Docker, deploy | `infra/` |
| **Admin panel** | UI de operadores | `ui/admin-panel/` |

**Estado actual**: auditoría completa de msi-a — PRE_EXPEDIENTE + EXPEDIENTE + ESCALATION + API + admin-panel + reglas de negocio + infraestructura + RAG. Los specs de `docs/system/` son la foto completa del sistema a fecha de la última verificación indicada en cada frontmatter.

## Modos del agente (resumen)

El agente tiene 2 modos activos + 1 modo terminal:

| Modo | Qué hace | Tráfico |
|------|----------|---------|
| **PRE_EXPEDIENTE** | Educa, orienta, presupuesta, muestra ejemplos de fotos | ~90% |
| **EXPEDIENTE** | Recolecta datos formales del caso (documentos, vehículo, taller) | ~10% |
| **ESCALATION** | Handoff a operador humano (terminal) | variable |

Detalle en `agente/modos/catalogo.md`.

## Cómo se usa este directorio

### Lectura (todo el mundo)
Abrir cualquier `.md`. Primera sección (`Resumen`) es el elevator pitch. Después vienen los escenarios CUANDO/ENTONCES que describen el comportamiento real.

### Edición (solo Arquitecto-AI + owner)
1. Owner pide un cambio en lenguaje libre.
2. Arquitecto-AI propone el diff al MD afectado.
3. Owner aprueba o pide ajustes.
4. Arquitecto-AI commitea el cambio en `docs/system/**`.
5. Owner (o automatismo futuro) llama al Ingeniero-AI.
6. Ingeniero-AI lee el diff, implementa, verifica, archiva.
7. Ingeniero-AI actualiza `ultima_verificacion_commit` y `ultima_verificacion_fecha` del spec afectado.

### Cuando un archivo te parece viejo
Si `ultima_verificacion_fecha` es de hace >3 meses o vacío, **trátalo como sospechoso**. Abrí un issue o pedile al Arquitecto-AI una revisión.

## Archivos en este directorio

```
docs/system/
├── 00-overview.md                              ← estás acá
├── 00-capacidades.md                           ← qué podemos / no podemos construir hoy
├── 99-protocolo-cambios.md                     ← cómo trabajamos Arquitecto ↔ Ingeniero ↔ Owner
│
├── core/                                       ← entidades del dominio
│   ├── clientes/
│   │   ├── definicion.md
│   │   └── escenarios.md
│   ├── conversaciones/
│   │   └── definicion.md
│   ├── expedientes/
│   │   └── ciclo-de-vida.md
│   ├── presupuestos/
│   │   └── draft-quote.md
│   ├── catalogo/
│   │   └── definicion.md
│   ├── tarifas/
│   │   └── calculo.md
│   ├── documentacion-requerida/
│   │   └── sistema-dual.md
│   └── adjuntos/
│       └── polimorfismo.md
│
├── agente/                                     ← agente conversacional (LA JOYA)
│   ├── modos/
│   │   └── catalogo.md                        ← los 3 modos (PRE / EXPEDIENTE / ESCALATION)
│   ├── flujos/
│   │   ├── pre-expediente/flujo.md
│   │   ├── expediente/flujo.md
│   │   └── escalado/flujo.md
│   ├── herramientas/
│   │   ├── pre-expediente.md
│   │   └── expediente.md
│   ├── prompts/
│   │   ├── pre-expediente.md
│   │   └── expediente.md
│   ├── router/
│   │   └── intenciones.md                     ← clasificador híbrido (11 intents)
│   ├── estado/
│   │   └── conversacional.md                  ← ConversationState + checkpointer + drafts
│   └── runtime/
│       └── servicios-auxiliares.md            ← EntityExtractionService, DigressionManager
│
├── modulos/                                    ← funcionalidades de producto acotadas
│   ├── facturacion/
│   │   └── flujo.md                           ← ciclo de vida de factura, Stripe SEPA, PDF
│   └── rag-regulatorio/
│       └── pipeline.md                        ← estado parcial, arquitectura esperada
│
├── infra/                                      ← cómo corre el sistema
│   ├── canal-whatsapp/
│   │   ├── webhook.md                         ← flujo WhatsApp ↔ Chatwoot ↔ agent
│   │   └── respuestas-salientes.md            ← handoff mecánico a operador humano
│   ├── auth-rbac/
│   │   └── jwt-roles.md                       ← JWT, roles, guards
│   ├── llm-router/
│   │   └── hibrido.md                         ← routing 2-tier Ollama + OpenRouter
│   ├── persistencia/
│   │   └── servicios-y-deploy.md              ← 6 servicios Docker + SSH deploy
│   ├── deploy/
│   │   └── procedimiento.md
│   ├── workers/
│   │   └── workers.md                         ← 4 workers background
│   ├── observabilidad/
│   │   └── telemetria.md                      ← turn telemetry, token tracking, validación
│   └── seguridad-adjuntos/
│       └── validacion.md
│
├── ui/                                         ← interfaces de usuario
│   └── admin-panel/
│       ├── conversaciones.md                  ← lista, detalle, escalaciones, attachments
│       ├── catalogo.md                        ← categorías, tiers, elementos, variantes, warnings
│       ├── usuarios.md                        ← CRUD usuarios, permisos, auditoría
│       ├── sistema.md                         ← monitoring, tokens, LLM metrics, validación
│       └── billing.md                         ← historial facturas, descarga PDF
│
├── _rebounds/                                  ← canal Ingeniero → Arquitecto
└── _demo/                                      ← prototipo inicial + ciclo simulado + morning review
```
