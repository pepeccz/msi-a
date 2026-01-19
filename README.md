# Pro -02— MSI-a: Local Infraestructure

Sistema de atención al cliente vía WhatsApp para **MSI Automotive**, empresa especializada en homologaciones de vehículos en España.

Construido con **LangGraph**, **FastAPI**, **Next.js** y **PostgreSQL** para proporcionar respuestas automáticas inteligentes a consultas sobre homologaciones.

## Arquitectura

El proyecto consta de 9 servicios orquestados en Docker:

- **PostgreSQL**: Base de datos relacional principal
- **Redis Stack**: Cache, colas de mensajes (Redis Streams), pub/sub y checkpoints de LangGraph
- **Ollama**: Servidor local de modelos LLM (embedding y generación de texto)
- **Qdrant**: Base de datos vectorial para el sistema RAG
- **API**: Backend FastAPI con webhooks y endpoints REST
- **Agent**: Orquestador conversacional con LangGraph (MSI-a)
- **Admin Panel**: Interfaz de administración con Next.js 16 + React 19
- **Document Processor**: Worker para procesamiento de documentos PDF y indexación RAG
- **Chatwoot**: Integración externa para mensajería WhatsApp (servicio externo)

## Estructura del Proyecto

```
msi-a/
├── docker/                 # Dockerfiles y scripts
├── shared/                 # Modulos compartidos (config, redis, chatwoot)
├── database/               # Modelos SQLAlchemy y migraciones Alembic
├── uploads/                # Documentos subidos (PDFs, imagenes)
├── api/                    # Backend FastAPI
│   ├── routes/             # Endpoints de la API (10 modulos)
│   ├── services/           # Logica de negocio (RAG, embeddings, etc.)
│   ├── workers/            # Workers asincronos (document processor)
│   └── models/             # Modelos Pydantic
├── agent/                  # Agente LangGraph
│   ├── graphs/             # StateGraph de conversacion
│   ├── nodes/              # Nodos del grafo (process_message, conversational_agent)
│   ├── state/              # Schemas y helpers de estado
│   ├── prompts/            # Prompts del sistema
│   ├── fsm/                # Maquinas de estado (case collection)
│   ├── routing/            # (Placeholder) Enrutamiento de intenciones
│   ├── tools/              # Herramientas LangGraph (20 tools)
│   └── services/           # Servicios de negocio (tarifas, elementos)
└── admin-panel/            # Panel de administracion Next.js
    └── src/
        ├── app/            # Next.js App Router
        ├── components/     # Componentes React + Radix UI
        ├── contexts/       # React contexts
        ├── hooks/          # Custom hooks
        └── lib/            # Utilidades
```

## Requisitos

- Docker y Docker Compose
- Python 3.11+
- Node.js 20+
- Cuenta de Chatwoot configurada
- API Key de OpenRouter

## Configuracion

1. Copia el archivo de ejemplo de variables de entorno:

```bash
cp .env.example .env
```

2. Edita `.env` con tus credenciales:

```env
# OpenRouter (obligatorio)
OPENROUTER_API_KEY=tu_api_key

# Chatwoot (obligatorio para WhatsApp)
CHATWOOT_API_URL=https://app.chatwoot.com
CHATWOOT_API_TOKEN=tu_token
CHATWOOT_ACCOUNT_ID=tu_account_id
CHATWOOT_INBOX_ID=tu_inbox_id
CHATWOOT_WEBHOOK_TOKEN=token_secreto

# Admin Panel
ADMIN_JWT_SECRET=secreto_jwt_seguro
ADMIN_PASSWORD_HASH=hash_bcrypt_de_tu_password
```

## Ejecucion

### Con Docker Compose (recomendado)

```bash
# Iniciar todos los servicios
docker-compose up -d

# Ver logs
docker-compose logs -f

# Detener
docker-compose down
```

### Desarrollo local

```bash
# Base de datos y Redis
docker-compose up -d postgres redis

# Migraciones
cd database && alembic upgrade head

# API (terminal 1)
cd api && uvicorn api.main:app --reload --port 8000

# Agent (terminal 2)
cd agent && python -m agent.main

# Admin Panel (terminal 3)
cd admin-panel && npm install && npm run dev
```

## URLs de Acceso

- **API REST**: http://localhost:8000
- **API Documentacion**: http://localhost:8000/docs
- **Admin Panel**: http://localhost:8001
- **Ollama**: http://localhost:11434
- **Qdrant**: http://localhost:6333 (Dashboard: http://localhost:6333/dashboard)

## Flujo de Mensajes

1. Cliente envia mensaje WhatsApp
2. Chatwoot recibe y envia webhook a `/api/chatwoot/webhook`
3. API publica mensaje en Redis Stream `incoming_messages`
4. Agent consume mensaje, procesa con LangGraph, genera respuesta
5. Agent publica respuesta en Redis PubSub `outgoing_messages`
6. Agent envia respuesta a Chatwoot, que la envia al cliente

## Sistema RAG (Retrieval-Augmented Generation)

El proyecto incluye un sistema RAG completo para consultas sobre normativa de homologaciones:

### Pipeline de Documentos

1. **Subida**: Admin sube PDF de normativa via panel de administracion
2. **Procesamiento**: Worker extrae texto con Docling/PyMuPDF
3. **Chunking**: Segmentacion semantica por articulos y secciones
4. **Embeddings**: Generacion con Ollama (nomic-embed-text)
5. **Indexacion**: Almacenamiento en Qdrant + metadatos en PostgreSQL

### Pipeline de Consultas

1. **Expansion**: Expansion de terminos tecnicos
2. **Busqueda Hibrida**: Vector (Qdrant) + Keywords (PostgreSQL) en paralelo
3. **Fusion**: Reciprocal Rank Fusion (RRF) para combinar resultados
4. **Reranking**: BGE reranker via Ollama para mejorar precision
5. **Generacion**: LLM genera respuesta con citas a articulos/secciones
6. **Cache**: Redis para consultas frecuentes

### URLs de Acceso RAG

- **Qdrant Dashboard**: http://localhost:6333/dashboard
- **RAG Query API**: http://localhost:8000/api/admin/rag/query

## Gestion de Expedientes (Cases)

El agente puede guiar a los clientes para abrir expedientes de homologacion:

### Flujo de Creacion

1. Cliente solicita iniciar expediente
2. FSM guia la recoleccion de datos:
   - Datos del vehiculo (matricula, VIN, marca, modelo)
   - Datos del propietario (nombre, NIF/CIF, direccion)
   - Datos del taller (opcional)
   - Imagenes requeridas segun tipo de homologacion
3. Revision y confirmacion
4. Expediente creado con estado `pending_review`

### Estados del Expediente

- `collecting`: Recopilando datos
- `pending_images`: Esperando imagenes
- `pending_review`: Listo para revision
- `in_progress`: En proceso de homologacion
- `resolved`: Completado

## Tecnologías

### Backend
- **Framework**: FastAPI (Python 3.11)
- **ORM**: SQLAlchemy
- **Migraciones**: Alembic
- **Validación**: Pydantic v2

### Agente Conversacional
- **Orquestación**: LangGraph
- **LLMs**: OpenRouter (API remota) / Ollama (local)
- **Embedding**: Ollama (nomic-embed-text)
- **Logging**: Estructurado en JSON

### Base de Datos
- **Principal**: PostgreSQL 15
- **Cache/Streams**: Redis Stack (con RedisSearch)
- **Vectorial**: Qdrant v1.7.4 (para RAG)

### Frontend
- **Framework**: Next.js 16 + React 19
- **UI Components**: Radix UI
- **Estilos**: Tailwind CSS
- **Tipo**: TypeScript

### Infraestructura
- **Orquestación**: Docker Compose
- **LLMs Locales**: Ollama (soporte GPU con NVIDIA)
- **Mensajería**: Chatwoot, Redis Streams/PubSub

## Configuración de LLMs

El proyecto soporta dos modos:

### 1. Modo OpenRouter (Recomendado para producción)
```env
OPENROUTER_API_KEY=tu_api_key
LLM_MODEL=openai/gpt-4o-mini  # o tu modelo preferido
```

### 2. Modo Ollama Local (Desarrollo, requiere GPU)
```env
OLLAMA_HOST=http://ollama:11434
LLM_MODEL=qwen2.5:3b  # o gpt-oss:20b
```

Ollama descargará automáticamente los modelos en el primer inicio.

## Variables de Entorno

Consulta `.env.example` para la lista completa. Variables clave:

```env
# Base de datos
POSTGRES_USER=msia
POSTGRES_PASSWORD=changeme
POSTGRES_DB=msia_db

# Redis
REDIS_PASSWORD=redis_password

# Chatwoot (WhatsApp)
CHATWOOT_API_URL=https://app.chatwoot.com
CHATWOOT_API_TOKEN=token
CHATWOOT_ACCOUNT_ID=id
CHATWOOT_INBOX_ID=id
CHATWOOT_WEBHOOK_TOKEN=secret

# LLM
OPENROUTER_API_KEY=key  # O usar Ollama
LLM_MODEL=openai/gpt-4o-mini

# Qdrant (RAG)
QDRANT_HOST=qdrant
QDRANT_PORT=6333

# Admin Panel
ADMIN_JWT_SECRET=secret_jwt_seguro
```

## Desarrollo

### Primeros pasos

1. Clona el repositorio
2. Copia `.env.example` a `.env` y configura tus credenciales
3. Inicia los servicios con Docker Compose

### Troubleshooting

**Problema**: Ollama no descarga los modelos
```bash
# Verifica los logs del setup
docker-compose logs ollama-setup
```

**Problema**: Base de datos no inicializa
```bash
# Ejecuta migraciones manualmente
docker-compose exec api alembic upgrade head
```

**Problema**: Agent no se conecta a Redis
```bash
# Verifica la contraseña de Redis en .env
docker-compose logs agent | head -50
```

## Estructura de Datos

### Modelos Principales (22 modelos)

**Core**
- **User**: Clientes de WhatsApp (telefono, datos personales, tipo de cliente)
- **ConversationHistory**: Historial de conversaciones con Chatwoot

**Sistema de Tarifas**
- **VehicleCategory**: Categorias de vehiculos (particular/profesional)
- **TariffTier**: Niveles de tarifa (T1-T6) con precios y reglas
- **Element**: Catalogo de elementos homologables
- **ElementImage**: Imagenes asociadas a elementos
- **TierElementInclusion**: Inclusiones de elementos en tiers
- **BaseDocumentation**: Documentacion base por categoria
- **AdditionalService**: Servicios adicionales
- **Warning**: Advertencias configurables
- **TariffPromptSection**: Secciones editables del prompt de tarifas

**Expedientes**
- **Case**: Expedientes de homologacion con datos completos
- **CaseImage**: Imagenes subidas para expedientes

**Sistema RAG**
- **RegulatoryDocument**: Documentos PDF de normativa
- **DocumentChunk**: Chunks semanticos con metadatos
- **RAGQuery**: Historial de consultas RAG
- **QueryCitation**: Citas de chunks en respuestas

**Administracion**
- **AdminUser**: Usuarios del panel (roles admin/user)
- **AdminAccessLog**: Log de accesos
- **Escalation**: Escalaciones a humanos
- **AuditLog**: Historial de cambios
- **SystemSetting**: Configuracion del sistema

### Redis Streams
- `incoming_messages`: Mensajes desde Chatwoot
- `outgoing_messages`: Respuestas del agente para enviar
- `document_processing`: Cola de procesamiento de documentos RAG

## Contribución

Por favor, sigue los convenios de codigo documentados en `AGENTS.md`.

## Licencia

Proyecto propietario de MSI Automotive bajo la autoridad de Zanovix. Todos los derechos reservados.
