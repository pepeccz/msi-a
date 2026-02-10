# MSI-a: Sistema de Atención al Cliente WhatsApp

Sistema de atención al cliente vía WhatsApp para **MSI Automotive**, empresa especializada en homologaciones de vehículos en España.

Construido con **LangGraph**, **FastAPI**, **Next.js** y **PostgreSQL** para proporcionar respuestas automáticas inteligentes a consultas sobre homologaciones.

---

## 🏗️ Arquitectura

### Servicios Docker (9 servicios)

| Servicio | Puerto | Propósito |
|----------|--------|-----------|
| **postgres** | 5432 | Base de datos PostgreSQL 15 |
| **redis** | 6379 | Redis Stack (Streams, cache, checkpoints) |
| **api** | 8000 | Backend FastAPI (~147 endpoints) |
| **agent** | — | Agente conversacional LangGraph (Mode-based v2.0) |
| **admin-panel** | 3000 | Panel de administración Next.js 16 |
| **ollama** | 11434 | Servidor LLM local (embeddings + generación) |
| **ollama-setup** | — | One-time model pull (qwen2.5:3b, llama3:8b, nomic-embed-text) |
| **qdrant** | 6333 | Base de datos vectorial para RAG |
| **document-processor** | — | Worker para procesamiento de PDFs |

**Integración Externa**: Chatwoot (WhatsApp messaging)

---

### Arquitectura del Agente (v2.0 - Mode-Based)

```
WhatsApp → Chatwoot → API Webhook → Redis Streams → Agent
                                                        ↓
                                              Intent Router
                                    (Keyword + LLM classification)
                                                        ↓
                                    ┌───────────────────┴────────────────────┐
                                    ↓                                        ↓
                            CONSULTA_MODE                            PRESUPUESTO_MODE
                         (Educational ~10%)                       (Pricing + Images ~90%)
                                                                            ↓
                                                                  EVALUACION_GATEWAY
                                                                      (Yes/No)
                                                                            ↓
                                                                  EXPEDIENTE_MODE
                                                                   (Case collection)
                                                                            ↓
                                                                   Escalation → Human
```

**Características v2.0**:
- ✅ Mode-based (no FSM lineal)
- ✅ Intent routing inteligente
- ✅ Digression handling (off-topic)
- ✅ Fallback & retry patterns
- ✅ Tool-driven state management

---

### Flujo de Mensajes

```
1. Cliente → WhatsApp
2. WhatsApp → Chatwoot
3. Chatwoot → Webhook (/api/chatwoot/webhook)
4. API → Redis Stream (incoming_messages)
5. Agent consume → LangGraph procesa → Genera respuesta
6. Agent → Chatwoot API → WhatsApp → Cliente
```

---

## 📁 Estructura del Proyecto

```
msi-a/
├── docker/                 # Dockerfiles y scripts
├── shared/                 # Módulos compartidos (11 archivos, 3,402 líneas)
│   ├── config.py           # Pydantic Settings (46+ env vars)
│   ├── redis_client.py     # Redis Streams client
│   ├── chatwoot_client.py  # Chatwoot API client
│   ├── llm_router.py       # Hybrid LLM router (3-tier)
│   └── ...
├── database/               # SQLAlchemy + Alembic
│   ├── models.py           # 32 modelos (3,224 líneas)
│   ├── connection.py       # Async PostgreSQL
│   ├── seeds/              # Data seeds (4,887 líneas)
│   └── alembic/            # 34 migrations (4,490 líneas)
├── uploads/                # Documentos subidos (PDFs, imágenes)
├── api/                    # Backend FastAPI
│   ├── main.py             # FastAPI app
│   ├── routes/             # 15 módulos (~147 endpoints)
│   ├── services/           # RAG, embeddings, document processor
│   ├── workers/            # Document processor worker
│   └── models/             # 51 Pydantic schemas
├── agent/                  # Agente LangGraph (Mode-based v2.0)
│   ├── graph/              # StateGraph definition
│   ├── router/             # Intent router, digression, transitions
│   ├── fallback/           # Retry policies
│   ├── modes/              # Mode nodes (CONSULTA, PRESUPUESTO, EXPEDIENTE, etc.)
│   ├── prompts/            # Dynamic prompts (core + mode-specific)
│   ├── tools/              # 26 LangChain tools
│   ├── services/           # Business logic (tarifas, elementos)
│   └── state/              # Conversation state + checkpointer
├── admin-panel/            # Next.js 16 Admin Panel
│   └── src/
│       ├── app/            # App Router (28 routes)
│       ├── components/     # 46 components (21 Radix UI + 25 feature)
│       ├── contexts/       # 3 React contexts
│       ├── hooks/          # 4 custom hooks
│       └── lib/            # API client (1,357 líneas) + types (1,397 líneas)
├── tests/                  # Test suite (342 tests, 89.2% coverage)
├── docs/                   # Documentación completa (ver docs/README.md)
│   ├── architecture/       # Arquitectura v2.0 (current) + legacy
│   ├── decisions/          # Architecture Decision Records (6 ADRs)
│   ├── coding-standards/   # Estándares de código (9 archivos)
│   ├── deployment/         # Historial de deployments
│   ├── bugs/               # Bug fixes documentados
│   ├── testing/            # Testing documentation
│   ├── plans/              # Implementation plans
│   └── sessions/           # Development session notes
└── skills/                 # AI agent skills (18 skills)
```

---

## 🚀 Inicio Rápido

### Requisitos

- Docker y Docker Compose
- Python 3.11+
- Node.js 20+
- Cuenta de Chatwoot configurada
- API Key de OpenRouter (o Ollama local)

### Configuración

1. **Clonar y configurar variables de entorno**:

```bash
git clone <repo-url>
cd msi-a
cp .env.example .env
```

2. **Editar `.env` con tus credenciales**:

```env
# OpenRouter (Cloud LLM - Tier 3)
OPENROUTER_API_KEY=tu_api_key
LLM_MODEL=deepseek/deepseek-chat

# Chatwoot (WhatsApp)
CHATWOOT_API_URL=https://app.chatwoot.com
CHATWOOT_API_TOKEN=tu_token
CHATWOOT_ACCOUNT_ID=tu_account_id
CHATWOOT_INBOX_ID=tu_inbox_id
CHATWOOT_WEBHOOK_TOKEN=token_secreto

# Admin Panel
ADMIN_JWT_SECRET=secreto_jwt_seguro  # Generar con: openssl rand -hex 32
ADMIN_PASSWORD_HASH=hash_bcrypt  # Generar con Python bcrypt
```

3. **Iniciar servicios**:

```bash
# Todos los servicios
docker-compose up -d

# Ver logs
docker-compose logs -f agent api

# Verificar estado
docker-compose ps
```

4. **Aplicar migraciones**:

```bash
docker-compose exec api alembic upgrade head
```

5. **Crear usuario admin** (opcional):

```bash
docker-compose exec api python database/seeds/create_admin_user.py
```

---

## 🌐 URLs de Acceso

| Servicio | URL | Documentación |
|----------|-----|---------------|
| **API REST** | http://localhost:8000 | http://localhost:8000/docs |
| **Admin Panel** | http://localhost:3000 | Login: admin/tu_password |
| **Ollama API** | http://localhost:11434 | http://localhost:11434/api/tags |
| **Qdrant Dashboard** | http://localhost:6333/dashboard | Vector DB |
| **Redis** | localhost:6379 | Requiere cliente |

---

## 🤖 Sistema de LLM Híbrido (3-Tier)

MSI-a usa un **sistema híbrido** para optimizar costos y latencia:

| Tier | Modelo | Uso | Costo | Latencia |
|------|--------|-----|-------|----------|
| **Tier 1 (Fast)** | Ollama: qwen2.5:3b | Clasificación, extracción | $0 | ~200ms |
| **Tier 2 (Capable)** | Ollama: llama3:8b | RAG simple, vehicle classification | $0 | ~1s |
| **Tier 3 (Cloud)** | OpenRouter: deepseek-chat | Conversación, RAG complejo | ~$0.27/1M tokens | ~2s |

**Configuración**:

```env
# Habilitar LLM híbrido
USE_HYBRID_LLM=true
LOCAL_FAST_MODEL=qwen2.5:3b         # Tier 1
LOCAL_CAPABLE_MODEL=llama3:8b        # Tier 2
LLM_MODEL=deepseek/deepseek-chat     # Tier 3

# Routing específico
USE_LOCAL_VEHICLE_CLASSIFICATION=true
USE_LOCAL_SECTION_MAPPING=true
USE_LOCAL_FOR_SIMPLE_RAG=true
```

**Ahorro de costos**: ~97% para RAG simple, ~70% overall.

---

## 📚 Sistema RAG (Retrieval-Augmented Generation)

### Pipeline de Documentos

```
Admin sube PDF → Redis Stream → Document Processor Worker
                                        ↓
                            Docling/PyMuPDF extraction
                                        ↓
                            Semantic chunking (1000 chars)
                                        ↓
                        Section mapping (Hybrid LLM: T1 + T3 fallback)
                                        ↓
                        Ollama embeddings (nomic-embed-text, 768-dim)
                                        ↓
                    Qdrant (vectors) + PostgreSQL (metadata)
```

### Pipeline de Consultas

```
User query → Query expansion → Hybrid search (Vector + Keyword)
                                        ↓
                            RRF merge + Keyword boosting
                                        ↓
                                BGE reranking (top 5)
                                        ↓
                        Query complexity classification
                                        ↓
                    ┌───────────────────┴────────────────────┐
                    ↓                                        ↓
            SIMPLE (T2: llama3:8b)              COMPLEX (T3: deepseek)
                    ↓                                        ↓
                        LLM answer + Citations
                                        ↓
                    Redis cache (24h embeddings, 1h queries)
```

**Configuración**:

```env
# Qdrant
QDRANT_URL=http://qdrant:6333
QDRANT_COLLECTION_NAME=regulatory_documents

# Embeddings
OLLAMA_BASE_URL=http://ollama:11434
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIMENSION=768

# RAG
RAG_TOP_K=10           # Top K chunks
RAG_RERANK_TOP_K=5     # Top K after reranking
RAG_CHUNK_SIZE=1000    # Chunk size (chars)
```

---

## 📋 Gestión de Expedientes (Cases)

### Flujo de Creación (Mode-Based)

```
User: "Quiero abrir expediente"
    ↓
EVALUACION_GATEWAY: "¿Estás seguro? (Sí/No)"
    ↓ (Si responde "sí")
EXPEDIENTE_MODE: Recolección secuencial
    ↓
1. collect_element_data    → Fotos + datos técnicos por elemento
2. collect_base_docs       → Ficha técnica, permiso circulación, fotos vehículo
3. collect_personal        → Nombre, DNI/CIF, email, domicilio, ITV
4. collect_vehicle         → Marca, modelo, matrícula, año, bastidor
5. collect_workshop        → Taller MSI o taller propio (+ datos si propio)
6. review_summary          → Resumen + confirmación
    ↓
Case created (pending_review) → Escalation → Human agent
```

### Estados del Expediente

| Estado | Descripción |
|--------|-------------|
| `collecting` | Recopilando datos |
| `pending_images` | Esperando imágenes |
| `pending_review` | Listo para revisión (escalado) |
| `in_progress` | En proceso de homologación |
| `resolved` | Completado |

---

## 🛠️ Desarrollo Local

### Sin Docker (desarrollo)

```bash
# 1. Base de datos y Redis
docker-compose up -d postgres redis ollama qdrant

# 2. Instalar dependencias Python
pip install -r requirements.txt

# 3. Migraciones
cd database && alembic upgrade head

# 4. API (terminal 1)
cd api && uvicorn api.main:app --reload --port 8000

# 5. Agent (terminal 2)
cd agent && python -m agent.main

# 6. Document Processor (terminal 3 - opcional)
cd api && python -m api.workers.document_processor_worker

# 7. Admin Panel (terminal 4)
cd admin-panel && npm install && npm run dev
```

### Con Docker Compose (recomendado)

```bash
# Todos los servicios
docker-compose up -d

# Ver logs específicos
docker-compose logs -f agent
docker-compose logs -f api

# Reiniciar servicio
docker-compose restart agent

# Ejecutar migraciones
docker-compose exec api alembic upgrade head

# Acceder a PostgreSQL
docker-compose exec postgres psql -U msia msia_db

# Acceder a Redis CLI
docker-compose exec redis redis-cli

# Ver modelos de Ollama
docker-compose exec ollama ollama list
```

---

## 🧪 Testing

```bash
# Backend (pytest)
pytest tests/ -v --cov --cov-report=html

# Specific test file
pytest tests/test_element_service.py -v

# Frontend (Jest)
cd admin-panel && npm test

# Coverage report
pytest tests/ --cov --cov-report=term-missing
```

**Coverage actual**: 89.2% overall (342 tests)

---

## 📊 Estructura de Base de Datos

### Modelos Principales (32 modelos)

**Core**:
- `User`: Clientes WhatsApp (teléfono, datos personales, tipo de cliente)
- `ConversationHistory`: Historial de conversaciones con Chatwoot
- `ConversationMessage`: Mensajes individuales

**Sistema de Tarifas**:
- `VehicleCategory`: Categorías de vehículos (motos-part, motos-prof, etc.)
- `TariffTier`: Niveles de tarifa (T1-T6) con precios
- `Element`: Catálogo de elementos homologables (~150 elementos)
- `ElementVariant`: Variantes de elementos (delantera/trasera, etc.)
- `ElementImage`: Imágenes de ejemplo por elemento
- `TierElementInclusion`: Inclusiones de elementos en tiers (+ herencia de tiers)
- `Warning`: Advertencias configurables (**sistema dual**: inline + associations)
- `BaseDocumentation`: Documentación base requerida
- `AdditionalService`: Servicios adicionales

**Expedientes**:
- `Case`: Expedientes de homologación con datos completos
- `CaseImage`: Imágenes subidas para expedientes
- `ElementData`: Datos requeridos por elemento

**Sistema RAG**:
- `RegulatoryDocument`: Documentos PDF de normativa
- `DocumentChunk`: Chunks semánticos con embeddings
- `RAGQuery`: Historial de consultas RAG
- `QueryCitation`: Citas de chunks en respuestas

**Administración**:
- `AdminUser`: Usuarios del panel (roles admin/user)
- `AdminAccessLog`: Log de accesos
- `Escalation`: Escalaciones a humanos
- `AuditLog`: Historial de cambios
- `SystemSetting`: Configuración del sistema
- `TokenUsage`: Métricas de uso de LLM
- `ToolLog`: Log de ejecución de tools
- `LLMMetrics`: Métricas detalladas de LLM

---

## 📖 Documentación

La documentación completa está en el directorio `docs/`:

```bash
# Leer documentación principal
cat docs/README.md

# Arquitectura actual (v2.0)
cat docs/architecture/current/00-overview.md

# Estándares de código
ls docs/coding-standards/

# Decisiones arquitectónicas (ADRs)
ls docs/decisions/

# Historial de deployments
ls docs/deployment/
```

### Documentación Clave

| Documento | Propósito |
|-----------|-----------|
| [AGENTS.md](AGENTS.md) | Guía para agentes de IA (Claude Code v2.0) |
| [docs/README.md](docs/README.md) | Índice maestro de documentación |
| [docs/architecture/README.md](docs/architecture/README.md) | Arquitectura del sistema |
| [docs/coding-standards/](docs/coding-standards/) | Estándares de código (9 archivos) |
| [docs/decisions/](docs/decisions/) | Architecture Decision Records |

---

## 🔧 Troubleshooting

### Ollama no descarga modelos

```bash
# Ver logs del setup
docker-compose logs ollama-setup

# Descargar manualmente
docker-compose exec ollama ollama pull qwen2.5:3b
docker-compose exec ollama ollama pull llama3:8b
docker-compose exec ollama ollama pull nomic-embed-text
```

### Base de datos no inicializa

```bash
# Ejecutar migraciones manualmente
docker-compose exec api alembic upgrade head

# Verificar estado
docker-compose exec api alembic current
```

### Agent no se conecta a Redis

```bash
# Verificar logs
docker-compose logs agent | head -50

# Verificar Redis
docker-compose exec redis redis-cli ping

# Verificar env var
docker-compose exec agent env | grep REDIS
```

### Admin Panel no carga

```bash
# Verificar logs
docker-compose logs admin-panel

# Reconstruir
docker-compose build admin-panel
docker-compose up -d admin-panel
```

---

## 🔐 Seguridad

### Características de Seguridad

- ✅ JWT authentication (HttpOnly cookies)
- ✅ RBAC (Role-Based Access Control)
- ✅ SSRF prevention (URL validation)
- ✅ Image security (multi-layer validation)
- ✅ Path traversal prevention
- ✅ Rate limiting (in-memory sliding window)
- ✅ Redis JWT blacklist
- ✅ Sanitized logging (phone numbers masked)

### Generar Secretos

```bash
# JWT Secret
openssl rand -hex 32

# Password Hash (Python)
python3 -c "from passlib.context import CryptContext; print(CryptContext(schemes=['bcrypt']).hash('tu_password'))"
```

---

## 📈 Métricas y Monitoreo

### Métricas Disponibles

- **Token Usage**: Consumo de tokens por modelo/conversación
- **Tool Logs**: Ejecución de tools con éxito/error
- **LLM Metrics**: Latencia, tokens, costo por request
- **Admin Access Logs**: Accesos al panel de admin
- **Escalations**: Escalaciones a humanos con contexto

### Acceso a Métricas

```bash
# Ver métricas desde admin panel
http://localhost:3000/logs/token-usage
http://localhost:3000/logs/tool-logs
http://localhost:3000/logs/llm-metrics
```

---

## 🤝 Contribución

Por favor, sigue las convenciones documentadas:

1. **Leer primero**: `AGENTS.md` y `docs/coding-standards/`
2. **Crear ADR**: Para decisiones arquitectónicas (ver `docs/decisions/template.md`)
3. **Escribir tests**: Coverage >90% para código crítico
4. **Conventional Commits**: Formato `type(scope): description`
5. **Pedir review**: Antes de merge a `main`

---

## 📄 Licencia

Proyecto propietario de MSI Automotive. Todos los derechos reservados.

---

## 🙏 Créditos

Desarrollado con la asistencia de **Claude Code v2.0** (Anthropic) en arquitectura multi-agente.

**Arquitectura**: Zanovix (Senior Architect)  
**Stack**: LangGraph, FastAPI, Next.js 16, PostgreSQL, Redis, Ollama, Qdrant

---

**Última actualización**: Febrero 2026  
**Versión**: 2.0 (Mode-based architecture)
