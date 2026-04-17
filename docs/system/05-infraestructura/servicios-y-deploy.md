---
titulo: Servicios Docker y flujo de deploy
ambito: infraestructura
ultima_verificacion_commit:
ultima_verificacion_fecha:
---

# Servicios Docker y flujo de deploy

## Resumen

MSI-a ejecuta **6 servicios Docker en producción** orquestados vía `docker-compose.yml`:

1. **PostgreSQL 15** (`postgres`) — base de datos relacional con 32 modelos
2. **Redis Stack** (`redis`) — cache, sesiones LangGraph, pub/sub, RedisSearch
3. **API FastAPI** (`api`) — webhook receptor de Chatwoot, CRUD tariffs/elementos, rutas admin
4. **Agent LangGraph** (`agent`) — orquestador de conversación, modos, tool loops
5. **Ollama** (`ollama`) — servidor LLM local (Tier 1, gemma4:e4b para clasificación y validación)
6. **Admin Panel Next.js** (`admin-panel`) — UI de gestión

Adicionales (perfiles): **GC Scheduler** (limpieza semanal de conversaciones antiguas) y **Test Runner** (tests defensivos en Docker, perfil `test`).

En **desarrollo**, `docker-compose.override.yml` habilita hot-reload (uvicorn --reload) para API y dev server Next.js. Ollama es **opcional en runtime**: el agent falla gracefully si no está disponible (fallback automático a cloud).

**Servidor remoto de producción**: `autohomologacion-server` con SSH + rsync para deploy.

## Escenarios

### 1. Arranque inicial del stack en desarrollo
- CUANDO se ejecuta `docker-compose up` en máquina local
- ENTONCES: PostgreSQL (healthcheck 5×10s), Redis (healthcheck 5×), ollama (descarga gemma4:e4b via ollama-setup), API (uvicorn --reload en 8000), Agent (LangGraph worker), Admin Panel (Next.js dev en 3000). Espera: todos los healthchecks deben pasar antes de que API y Agent arranquen.

### 2. Deploy de cambio en remote (hot update)
- CUANDO el desarrollador ejecuta `./scripts/clean-build-deploy.sh` en autohomologacion-server tras `git push`
- ENTONCES: script para servicios → `docker-compose pull` → `docker-compose up -d` (recreate images) → `alembic upgrade head` (migraciones BD) → `python -m database.seeds.run_all_seeds` (rehidrata seed data) → verifica healthchecks. Cero downtime si no hay cambios de schema; downtime mínimo (solo migraciones) si schema cambia.

### 3. Rollback de versión tras bug en producción
- CUANDO se detecta bug crítico en agent/API
- ENTONCES: `git checkout HEAD~1 && ./scripts/clean-build-deploy.sh` → vuelve a compilar imágenes de la versión anterior → reejecuta migraciones (idempotent, Alembic solo aplica nuevas). Precondición: cambios en `main` son reversibles.

### 4. Update de dependencias Python/Node.js
- CUANDO `requirements.txt` o `package.json` tiene cambios
- ENTONCES: `docker-compose build --no-cache api` + rebuild agent + rebuild admin-panel → `docker-compose up -d` (reinicia con nuevas imágenes).

### 5. Restart de un servicio tras bug (sin recompile)
- CUANDO el agent queda stuck o API necesita reinicio rápido sin rebuild
- ENTONCES: `docker-compose restart agent` o `docker-compose restart api` → contenedor permanece, solo reinicia proceso (preserva volumes). Tiempo: ~3s vs ~1m para rebuild completo.

### 6. Acceso a logs de servicios en producción
- CUANDO debugging de error en agent o API
- ENTONCES: SSH a autohomologacion-server → `docker-compose logs -f agent` (real-time) o `docker-compose logs --tail 100 api` (últimas 100 líneas) → grep para patrones.

### 7. Migración de base de datos
- CUANDO nuevo campo de modelo o tabla requerida
- ENTONCES: desarrollador crea migración Alembic → `alembic revision -m "add_rag_tables"` → escribe `upgrade()` + `downgrade()` → deploy corre migraciones antes de restart agent. Migrations MUST be backwards-compatible.

### 8. Backup y restore de PostgreSQL
- CUANDO backup semanal de BD (ej. viernes 3am)
- ENTONCES: `docker-compose exec -T postgres pg_dump -U msia -d msia_db | gzip > backup_$(date +%Y%m%d).sql.gz` → almacena en backups/. Restore: `gunzip < backup_file.sql.gz | docker-compose exec -T postgres psql -U msia -d msia_db`.

### 9. Garbage Collection de conversaciones antiguas (scheduled)
- CUANDO cron semanal (domingo 3am, vía gc-scheduler)
- ENTONCES: gc-scheduler llama `POST /admin/gc/run` con `dry_run=false, retention_days=90` → API elimina ConversationHistory + messages + state anterior a 90 días → loguea resultados.

### 10. Monitoring y alertas de healthchecks
- CUANDO un servicio falla healthcheck (ej. Redis no responde `PING`)
- ENTONCES: Docker marca contenedor como unhealthy. Verificación manual: `docker-compose ps` → columna "Status" muestra "Up (healthy)" o "Up (unhealthy)". El agent tiene fallback a cloud si Ollama unhealthy.

## Reglas duras

1. **6 servicios core, 2 opcionales**: los 6 son obligatorios en producción. gc-scheduler y test-runner son perfiles que se activan con `--profile`.

2. **Healthchecks en todos los servicios**: cada servicio tiene healthcheck con timeout, retries, interval. postgres + redis especialmente críticos. Ollama es optional: agent falla gracefully.

3. **`docker-compose exec -T` para scripts**: el flag `-T` desactiva pseudo-TTY (necesario en CI/scripts). Sin él, los pipes fallan.

4. **Alembic migrations siempre idempotent**: cada `alembic upgrade head` es safe re-ejecutar. Pre-requisito: `downgrade()` DEBE estar definido.

5. **No ejecutar servicios localmente (regla proyecto)**: todos los tests, desarrollo, migraciones ocurren en Docker. Excepción: IDE puede correr pytest localmente contra BD en Docker.

6. **`docker-compose.override.yml` solo en dev**: no committear a producción. Dev habilita hot-reload, volumes para código. Producción usa solo `docker-compose.yml`.

7. **Remote deploy vía SSH + git pull + compose**: producción accesible en `autohomologacion-server`. Deploy: SSH → git pull → docker-compose pull/build → up -d → alembic upgrade.

8. **Seeds siempre post-migration**: `run_all_seeds` corre DESPUÉS de `alembic upgrade` (las tablas deben existir). Idempotent: upsert con UUIDs v5 determinísticos.

9. **Volumes para uploads, invoices, data**: `postgres_data`, `redis_data`, `ollama_data`, `uploads/`, `invoices/` son volumes/paths que persisten restart. No borrar sin backup.

10. **Health check ports**: postgres:5432, redis:6379, api:8000 (`curl /health`), agent:6379 (redis check), ollama:11434 (api/tags), admin-panel:3000.

## Mapeo al código

### Orquestación Docker
- `docker-compose.yml:1-259` — Definición de 6 servicios + gc-scheduler + test-runner, networks, volumes, healthchecks
- `docker-compose.override.yml:1-50` — Overrides para hot-reload en dev
- `docker/Dockerfile.api:1-40` — Build API
- `docker/Dockerfile.agent:1-46` — Build Agent
- `docker/Dockerfile.admin-panel:1-40` — Build admin UI
- `docker/Dockerfile.admin-panel.dev:1-30` — Dev version con hot-reload

### Scripts de Deploy
- `scripts/clean-build-deploy.sh:1-380` — Orquestador: stop → clean → pull → build → start → migrate → seed → verify. Flags: `--backup`, `--dry-run`
- `docker/entrypoint-agent.sh` — Entry script para agent container
- `docker/init-db.sh` — Script de inicialización de BD

### Database Configuration
- `database/connection.py:88` — Async engine, pool config (pool_size=10, max_overflow=20, pre_ping=True)
- `alembic.ini` — Alembic environment; DATABASE_URL vía env var
- `database/alembic/versions/` — 34 migrations (~4490 líneas)

### Seed Infrastructure
- `database/seeds/run_all_seeds.py` — Orquestador de seeds
- `database/seeds/seeders/base.py` — BaseSeeder con upsert + logging

### Health Checks
- `docker-compose.yml`: `healthcheck` para cada servicio (test, interval, timeout, retries, start_period)
- Verificación manual: `docker-compose ps`, `curl http://localhost:8000/health`

## Fuera de alcance

- `api/main.py`, `api/routes/**` — lógica de API routes (otro scope)
- `agent/main.py`, `agent/graph/**` — lógica LangGraph (otro scope)
- `admin-panel/src/**` — frontend (otro scope)
- `agent/services/**`, `api/services/**` — business logic
- Database models directamente (usar Alembic migrations)
- `shared/config.py` excepto para agregar NUEVAS variables
- Testing (pytest, test runners) — scope distinto
