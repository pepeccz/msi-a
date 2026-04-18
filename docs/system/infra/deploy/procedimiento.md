---
titulo: Deploy — procedimiento SSH
ambito: infra
ultima_verificacion_commit:
ultima_verificacion_fecha:
---

# Deploy — procedimiento SSH

## Resumen

La producción corre en `autohomologacion-server`, un servidor remoto accesible vía SSH. El deploy se hace con `git push` + ejecución de `./scripts/clean-build-deploy.sh` en el servidor remoto. El script orquesta todo: stop → build → start → migraciones → seeds → healthcheck verification. Para rollback, se hace `git checkout HEAD~1` y se re-ejecuta el script.

No hay CI/CD automatizado: el deploy es siempre manual, iniciado por el desarrollador desde SSH. Esta es una decisión intencional para el estado actual del proyecto.

## Escenarios

### 1. Deploy de cambio en producción (hot update)
- CUANDO el desarrollador ejecuta `./scripts/clean-build-deploy.sh` en `autohomologacion-server` tras `git pull`
- ENTONCES el script: para servicios → `docker-compose pull` → `docker-compose up -d` (recrea con nuevas imágenes) → `alembic upgrade head` (migraciones BD) → `python -m database.seeds.run_all_seeds` (rehidrata seed data) → verifica healthchecks. Cero downtime si no hay cambios de schema; downtime mínimo (solo durante migraciones) si el schema cambia.

### 2. Rollback de versión tras bug en producción
- CUANDO se detecta bug crítico en agent o API
- ENTONCES `git checkout HEAD~1 && ./scripts/clean-build-deploy.sh` → recompila imágenes de la versión anterior → re-ejecuta migraciones (idempotent, Alembic solo aplica las pendientes). Precondición: los cambios en `main` deben ser reversibles (downgrade de Alembic disponible).

### 3. Migración de base de datos
- CUANDO se agrega un nuevo campo o tabla al modelo
- ENTONCES el desarrollador crea la migración localmente: `alembic revision -m "descripción"` → escribe `upgrade()` + `downgrade()` → commitea → en el próximo deploy, `alembic upgrade head` la aplica automáticamente antes de reiniciar agent. Migrations MUST be backwards-compatible.

### 4. Monitoring post-deploy
- CUANDO el deploy termina y los healthchecks pasan
- ENTONCES `docker-compose ps` muestra todos los servicios como `Up (healthy)`. Para verificar que el agente procesa mensajes: `docker-compose logs -f agent` → se ven logs `turn_telemetry` ante la primera conversación entrante.

## Reglas duras

1. **Remote deploy vía SSH + git pull + compose**: producción solo se actualiza en `autohomologacion-server`. Deploy local está prohibido. Flujo: SSH → `git pull` → `docker-compose pull/build` → `up -d` → `alembic upgrade`.
2. **Seeds siempre post-migration**: `run_all_seeds` corre DESPUÉS de `alembic upgrade head`. Las tablas deben existir antes de intentar insertar seed data. Seeds son idempotent: upsert con UUIDs v5 determinísticos.
3. **Alembic migrations siempre idempotent**: cada `alembic upgrade head` es safe de re-ejecutar. Pre-requisito: `downgrade()` DEBE estar definido y no ser `pass`.
4. **`--backup` antes de cambios de schema**: `./scripts/clean-build-deploy.sh --backup` crea snapshot de BD antes de migrar. Recomendado siempre que haya migraciones nuevas.
5. **Dry-run disponible**: `./scripts/clean-build-deploy.sh --dry-run` simula el proceso sin ejecutar cambios. Usar para validar en casos de duda.

## Mapeo al código

- `scripts/clean-build-deploy.sh:1-380` — Orquestador del deploy: stop → clean → pull → build → start → migrate → seed → verify. Flags: `--backup`, `--dry-run`.
- `docker/entrypoint-agent.sh` — Entry script para el container del agente.
- `docker/init-db.sh` — Script de inicialización de BD (primera vez).
- `alembic.ini` — Configuración Alembic; `DATABASE_URL` vía env var.
- `database/alembic/versions/` — Migraciones (~34 archivos, ~4490 líneas totales).
- `database/seeds/run_all_seeds.py` — Orquestador de seeds.
- `database/seeds/seeders/base.py` — `BaseSeeder` con upsert + logging.

## Fuera de alcance

- Stack de servicios Docker y definición de healthchecks: documentado en `../persistencia/servicios-y-deploy.md`
- `api/routes/**` — lógica de API routes
- `database/models.py` directamente (usar Alembic migrations para cambios de schema)
- Testing (pytest, test runners) — scope distinto
- Configuración de variables de entorno del servidor (`.env` en servidor remoto, gestionado manualmente)
