# MSI Automotive - Infraestructure

Sistema de atencion al cliente via WhatsApp para **MSI Automotive**, empresa especializada en homologaciones de vehiculos en Espana.

## Arquitectura

El proyecto consta de 5 servicios:

- **PostgreSQL**: Base de datos principal
- **Redis**: Cache, colas de mensajes (Redis Streams) y checkpoints de LangGraph
- **API**: Backend FastAPI con endpoints REST
- **Agent**: Agente conversacional LangGraph (MSI-a)
- **Admin Panel**: Panel de administracion Next.js

## Estructura del Proyecto

```
msi-a/
├── docker/                 # Dockerfiles y scripts
├── shared/                 # Modulos compartidos (config, redis, chatwoot)
├── database/               # Modelos SQLAlchemy y migraciones Alembic
├── api/                    # Backend FastAPI
│   ├── routes/             # Endpoints de la API
│   └── models/             # Modelos Pydantic
├── agent/                  # Agente LangGraph
│   ├── graphs/             # StateGraph de conversacion
│   ├── nodes/              # Nodos del grafo
│   ├── state/              # Schemas y helpers de estado
│   ├── prompts/            # Prompts del sistema
│   ├── fsm/                # (Placeholder) Maquinas de estado
│   ├── routing/            # (Placeholder) Enrutamiento de intenciones
│   ├── tools/              # (Placeholder) Herramientas LangGraph
│   └── services/           # (Placeholder) Servicios de negocio
└── admin-panel/            # Panel de administracion Next.js
```

## Requisitos

- Docker y Docker Compose
- Python 3.12+
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

## URLs

- **API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Admin Panel**: http://localhost:3001

## Flujo de Mensajes

1. Cliente envia mensaje WhatsApp
2. Chatwoot recibe y envia webhook a `/api/chatwoot/webhook`
3. API publica mensaje en Redis Stream `incoming_messages`
4. Agent consume mensaje, procesa con LangGraph, genera respuesta
5. Agent publica respuesta en Redis PubSub `outgoing_messages`
6. Agent envia respuesta a Chatwoot, que la envia al cliente

## Tecnologias

- **Backend**: Python 3.12, FastAPI, SQLAlchemy, Alembic
- **Agente**: LangGraph, LangChain, OpenRouter (GPT-4o-mini)
- **Base de datos**: PostgreSQL 15, Redis Stack
- **Frontend**: Next.js 16, React 19, Tailwind CSS, Radix UI
- **Mensajeria**: Chatwoot, Redis Streams/PubSub
- **Contenedores**: Docker, Docker Compose

## Licencia

Proyecto propietario de MSI Automotive.
