# CLAUDE.md - Instrucciones para Claude Code

## IMPORTANTE: Entorno de Desarrollo

- **NO arranques servicios ni ejecutes comandos** (docker, npm, python, etc.) a menos que se solicite explicitamente.
- El desarrollo se realiza en local, pero los servicios se ejecutan en **otro equipo** con la potencia necesaria para testing y ejecucion.
- Limitate a editar codigo, analizar y responder preguntas salvo indicacion contraria.
- Mantén coherencia siempre entre backend y frontend

## Sobre el Proyecto

Este es **MSI-a**, un sistema de atencion al cliente via WhatsApp para MSI Automotive, empresa de homologaciones de vehiculos en Espana. El proyecto usa:

- **LangGraph** para el agente conversacional
- **FastAPI** para la API backend
- **Next.js** para el panel de administracion
- **Redis Streams** para mensajeria persistente
- **PostgreSQL** para persistencia de datos
- **Chatwoot** para integracion con WhatsApp

## Estructura de Archivos Clave

```
msi-a/
├── docker-compose.yml      # Orquestacion de servicios
├── requirements.txt        # Dependencias Python
├── .env.example            # Variables de entorno de ejemplo
│
├── shared/
│   ├── config.py           # Configuracion centralizada (Pydantic Settings)
│   ├── redis_client.py     # Cliente Redis con Streams
│   ├── chatwoot_client.py  # Cliente API de Chatwoot
│   └── logging_config.py   # Configuracion de logging JSON
│
├── database/
│   ├── models.py           # Modelos SQLAlchemy (Customer, ConversationHistory, etc.)
│   ├── connection.py       # Conexion async a PostgreSQL
│   └── alembic/            # Migraciones de base de datos
│
├── api/
│   ├── main.py             # Punto de entrada FastAPI
│   ├── routes/
│   │   ├── chatwoot.py     # Webhook de Chatwoot
│   │   └── admin.py        # Endpoints del panel admin
│   └── models/
│       └── chatwoot_webhook.py  # Modelos Pydantic para webhooks
│
├── agent/
│   ├── main.py             # Punto de entrada del agente
│   ├── graphs/
│   │   └── conversation_flow.py  # StateGraph de LangGraph
│   ├── nodes/
│   │   ├── process_message.py    # Nodo de procesamiento de mensajes
│   │   └── conversational_agent.py  # Nodo de generacion de respuestas
│   ├── state/
│   │   ├── schemas.py      # ConversationState TypedDict
│   │   ├── checkpointer.py # Redis checkpointer para LangGraph
│   │   └── helpers.py      # Funciones auxiliares de estado
│   └── prompts/
│       └── system.md       # Prompt del sistema MSI-a
│
└── admin-panel/            # Next.js 16 con React 19
    ├── src/
    │   ├── app/            # App Router de Next.js
    │   ├── components/     # Componentes React (UI de Radix)
    │   ├── contexts/       # Contextos React (Auth, Sidebar)
    │   └── lib/            # Utilidades (API client, auth, types)
    └── package.json
```

## Comandos Utiles

```bash
# Iniciar servicios
docker-compose up -d

# Ver logs del agente
docker-compose logs -f agent

# Ejecutar migraciones
docker-compose exec api alembic upgrade head

# Acceder a PostgreSQL
docker-compose exec postgres psql -U msia msia_db

# Acceder a Redis CLI
docker-compose exec redis redis-cli
```

## Convenios de Codigo

### Python
- Tipado estricto con type hints
- Async/await para operaciones I/O
- Logging estructurado JSON
- Pydantic para validacion de datos

### TypeScript/React
- Next.js App Router
- Server Components por defecto
- Radix UI para componentes
- Tailwind CSS para estilos

## Flujo del Agente

1. `process_incoming_message_node`: Recibe mensaje, lo anade al historial
2. `conversational_agent_node`: Genera respuesta con LLM via OpenRouter
3. Estado persistido en Redis con checkpointer

## Variables de Entorno Importantes

- `OPENROUTER_API_KEY`: API key para LLM
- `LLM_MODEL`: Modelo a usar (default: openai/gpt-4o-mini)
- `CHATWOOT_*`: Configuracion de Chatwoot
- `USE_REDIS_STREAMS`: true para usar Streams (recomendado)
- `MESSAGE_BATCH_WINDOW_SECONDS`: Ventana de batching (0 = deshabilitado)

## Notas para Desarrollo

- El agente MSI-a esta disenado para responder consultas sobre homologaciones
- Los flujos especificos de recopilacion de datos se anadiran posteriormente
- Los precios son fijos por tipo de homologacion (no hay recursos asignables)
- Escalar a humano cuando el caso sea complejo o el cliente lo solicite

## Archivos Placeholder

Los siguientes directorios estan preparados para expansion futura:
- `agent/fsm/`: Maquinas de estado para flujos complejos
- `agent/routing/`: Clasificacion de intenciones
- `agent/tools/`: Herramientas LangGraph (escalacion, notificaciones)
- `agent/services/`: Logica de negocio (precios, consultas)
