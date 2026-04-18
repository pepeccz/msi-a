---
titulo: Servicios Docker — stack y persistencia
ambito: infra
ultima_verificacion_commit:
ultima_verificacion_fecha:
---

# Servicios Docker — stack y persistencia

## Resumen

MSI-a ejecuta **6 servicios Docker core** orquestados vía `docker-compose.yml`. Cada servicio tiene healthcheck configurado y la mayoría depende de que postgres y redis estén healthy antes de arrancar. Dos servicios adicionales (GC Scheduler y Test Runner) son opcionales y se activan con `--profile`.

En **desarrollo**, `docker-compose.override.yml` habilita hot-reload (uvicorn --reload para API, dev server para Next.js). Ollama es opcional en runtime: el agente falla gracefully si no está disponible, con fallback automático a cloud.

## Escenarios

### 1. Arranque inicial del stack en desarrollo
- CUANDO se ejecuta `docker-compose up` en máquina local
- ENTONCES arrancan en orden: PostgreSQL (healthcheck 5×10s) → Redis (healthcheck 5×) → Ollama (descarga `gemma4:e4b` via `ollama-setup`) → API (uvicorn --reload en puerto 8000) → Agent (LangGraph worker) → Admin Panel (Next.js dev en puerto 3000). API y Agent esperan que postgres y redis pasen healthcheck antes de iniciar.

### 2. Servicio individual falla healthcheck
- CUANDO Redis no responde a `PING` (el container está up pero el proceso está colgado)
- ENTONCES Docker marca el container como `unhealthy`. El agente tiene fallback automático: si Ollama está unhealthy, ruta a cloud tier. Si Redis está unhealthy, la ingesta de mensajes se detiene (no hay fallback para Streams). Verificación: `docker-compose ps` → columna Status muestra `Up (unhealthy)`.

### 3. Actualización de dependencias Python/Node.js
- CUANDO `requirements.txt` o `package.json` tiene cambios
- ENTONCES se rebuildan las imágenes afectadas: `docker-compose build --no-cache api` + rebuild agent + rebuild admin-panel → `docker-compose up -d` (reinicia con nuevas imágenes).

### 4. Restart rápido de un servicio sin rebuild
- CUANDO el agente queda stuck o la API necesita reinicio rápido sin recompilar
- ENTONCES `docker-compose restart agent` o `docker-compose restart api` → el container permanece, solo reinicia el proceso, preserva volumes. Tiempo: ~3s vs ~1m para rebuild completo.

### 5. Acceso a logs de servicios en producción
- CUANDO debugging de un error en agent o API
- ENTONCES SSH a `autohomologacion-server` → `docker-compose logs -f agent` (real-time) o `docker-compose logs --tail 100 api` (últimas 100 líneas). Todos los servicios loguean en JSON estructurado (structlog).

### 6. Backup y restore de PostgreSQL
- CUANDO se realiza backup semanal de BD
- ENTONCES `docker-compose exec -T postgres pg_dump -U msia -d msia_db | gzip > backup_$(date +%Y%m%d).sql.gz` → almacena en `backups/`. Restore: `gunzip < backup_file.sql.gz | docker-compose exec -T postgres psql -U msia -d msia_db`.

### 7. Garbage Collection de conversaciones antiguas
- CUANDO cron semanal (domingo 3am, vía gc-scheduler con `--profile`)
- ENTONCES `gc-scheduler` llama `POST /admin/gc/run` con `dry_run=false, retention_days=90` → API elimina ConversationHistory + messages + state con más de 90 días → loguea resultados.

## Reglas duras

1. **6 servicios core, 2 opcionales**: postgres, redis, api, agent, ollama, admin-panel son obligatorios en producción. `gc-scheduler` y `test-runner` son perfiles que se activan con `--profile`.
2. **Healthchecks en todos los servicios**: postgres y redis son especialmente críticos (otros servicios dependen de ellos). Ollama es optional: el agente falla gracefully si está unhealthy.
3. **`docker-compose exec -T` para scripts**: el flag `-T` desactiva pseudo-TTY (necesario en CI/scripts). Sin él, los pipes fallan.
4. **`docker-compose.override.yml` solo en dev**: no committear a producción. Dev habilita hot-reload y volumes de código. Producción usa solo `docker-compose.yml`.
5. **Volumes para datos persistentes**: `postgres_data`, `redis_data`, `ollama_data`, `uploads/`, `invoices/` son volumes/paths que persisten al restart. No borrar sin backup previo.
6. **No ejecutar servicios localmente (regla proyecto)**: todos los tests, migraciones y operaciones ocurren en Docker. Excepción: IDE puede correr pytest localmente contra BD en Docker.
7. **Health check ports**: postgres:5432, redis:6379, api:8000 (`curl /health`), ollama:11434 (`/api/tags`), admin-panel:3000.

## Mapeo al código

- `docker-compose.yml:1-259` — Definición de 6 servicios + gc-scheduler + test-runner, networks, volumes, healthchecks.
- `docker-compose.override.yml:1-50` — Overrides para hot-reload en dev.
- `docker/Dockerfile.api:1-40` — Build de la imagen API.
- `docker/Dockerfile.agent:1-46` — Build de la imagen Agent.
- `docker/Dockerfile.admin-panel:1-40` — Build de la imagen Admin UI (producción).
- `docker/Dockerfile.admin-panel.dev:1-30` — Build Admin UI dev con hot-reload.
- `database/connection.py:88` — Async engine, pool config (`pool_size=10`, `max_overflow=20`, `pre_ping=True`).

## Fuera de alcance

- Procedimiento de deploy SSH y migraciones: documentado en `../deploy/procedimiento.md`
- `api/main.py`, `api/routes/**` — lógica de API routes
- `agent/main.py`, `agent/graph/**` — lógica LangGraph
- `admin-panel/src/**` — frontend
- Database models directamente (usar Alembic migrations)
- Testing (pytest, test runners) — scope distinto
