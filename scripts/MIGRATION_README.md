# Scripts de Migración VIABILIDAD_MODE → PRESUPUESTO_MODE

Este directorio contiene scripts para migrar conversaciones activas después del deployment de la fusión VIABILIDAD + PRESUPUESTO.

---

## Scripts Disponibles

### 1. `migrate_viabilidad_to_presupuesto.py`
**Propósito:** Migrar checkpoints PostgreSQL (si existen)

**Nota:** Actualmente MSI-a usa Redis checkpointer, por lo que este script está preparado pero no ejecuta cambios en PostgreSQL. Usar el script Redis en su lugar.

**Uso:**
```bash
# Dry run (ver qué se migraría)
python3 scripts/migrate_viabilidad_to_presupuesto.py --dry-run

# Ejecutar migración
python3 scripts/migrate_viabilidad_to_presupuesto.py
```

---

### 2. `migrate_redis_viabilidad_state.py` ⭐ (PRINCIPAL)
**Propósito:** Migrar checkpoints activos en Redis

**Qué hace:**
- Escanea TODAS las claves `checkpoint:*` en Redis
- Busca conversaciones con `current_mode = "VIABILIDAD_MODE"`
- Actualiza a `current_mode = "PRESUPUESTO_MODE"`
- Elimina `estimacion_precio` del context (concepto obsoleto)
- Renombra `precio_exacto` → `precio_calculado` (si existe)
- Agrega `VIABILIDAD_MODE` al `mode_history` para tracking
- Preserva todos los demás datos (`categoria_slug`, `elemento_confirmado`, etc.)

**Uso:**
```bash
# Dry run (RECOMENDADO primero)
python3 scripts/migrate_redis_viabilidad_state.py --dry-run

# Ejecutar migración real
python3 scripts/migrate_redis_viabilidad_state.py
```

**Output esperado:**
```
================================================================================
✅ MIGRATION COMPLETE
================================================================================

Statistics:
  - Checkpoints scanned:  245
  - Checkpoints migrated: 12
  - Checkpoints skipped:  233
  - Errors:               0
  - Started at:           2026-02-04T01:15:30.123456+00:00
  - Completed at:         2026-02-04T01:15:32.654321+00:00

================================================================================
```

---

## Cuándo Ejecutar

**TIMING:** Ejecutar DESPUÉS del deployment del código fusionado, ANTES de que los usuarios empiecen a usar el nuevo sistema.

**Orden recomendado:**
1. ✅ Deploy código fusionado (agent-dev completa tareas 1-8)
2. ✅ Verificar que el servicio arranca correctamente
3. ✅ **Dry run** del script Redis: `--dry-run`
4. ✅ Revisar output del dry run
5. ✅ Ejecutar migración real (sin `--dry-run`)
6. ✅ Verificar logs en Chatwoot/Redis
7. ✅ Monitorear conversaciones activas

---

## Validación Post-Migración

Después de ejecutar la migración:

### 1. Verificar Redis directamente
```bash
# Conectar a Redis
docker-compose exec redis redis-cli

# Buscar checkpoints
KEYS checkpoint:*

# Inspeccionar uno
GET checkpoint:12345

# Verificar que no hay VIABILIDAD_MODE
KEYS checkpoint:* | xargs -I {} redis-cli GET {} | grep VIABILIDAD_MODE
```

### 2. Verificar logs
```bash
# Ver logs del script
docker-compose logs -f agent | grep migration

# Buscar errores
docker-compose logs agent | grep -i error
```

### 3. Probar con conversación real
- Enviar mensaje de WhatsApp: "Quiero homologar un escape"
- Verificar que va directo a PRESUPUESTO_MODE
- Verificar que calcula precio inmediatamente
- Verificar que ofrece 2 opciones (A y B)

---

## Rollback

Si algo sale mal durante la migración:

### Opción 1: Redis Backup (ANTES de migrar)
```bash
# Antes de la migración, crear backup
docker-compose exec redis redis-cli --rdb /data/backup-pre-migration.rdb

# Restaurar si es necesario
docker-compose down
docker-compose up -d redis
# Copiar backup a volumen Redis
```

### Opción 2: Código Rollback
Si el código nuevo falla:
```bash
# Volver a commit anterior
git revert <commit-hash>
docker-compose restart agent
```

---

## Logs y Debugging

Los scripts usan `structlog` con JSON output.

**Ver logs estructurados:**
```bash
# Durante ejecución
python3 scripts/migrate_redis_viabilidad_state.py 2>&1 | grep -v "^{" | less

# Ver solo errores
python3 scripts/migrate_redis_viabilidad_state.py 2>&1 | grep '"level":"error"'

# Ver solo migraciones exitosas
python3 scripts/migrate_redis_viabilidad_state.py 2>&1 | grep 'checkpoint_migrated'
```

---

## Troubleshooting

### Error: "No module named 'shared'"
**Solución:** Ejecutar desde la raíz del proyecto:
```bash
cd /home/autohomologacion/msi-a
python3 scripts/migrate_redis_viabilidad_state.py --dry-run
```

### Error: "Redis connection refused"
**Solución:** Verificar que Redis está corriendo:
```bash
docker-compose ps redis
docker-compose up -d redis
```

### Error: "JSONDecodeError"
**Solución:** Checkpoint corrupto. El script lo marca como error y continúa con los demás.

### Migrated = 0 (ninguno migrado)
**Posibles causas:**
- No hay conversaciones activas en VIABILIDAD_MODE (esperado si ya se migró)
- Los checkpoints usan otra estructura de keys (verificar con `KEYS checkpoint:*`)

---

## Características de los Scripts

✅ **Dry-run mode:** Ver qué se migraría sin hacer cambios  
✅ **Logging detallado:** JSON structured logs para debugging  
✅ **Error handling:** Continúa aunque un checkpoint falle  
✅ **Estadísticas:** Resumen completo al final  
✅ **Idempotente:** Se puede ejecutar múltiples veces sin problemas  
✅ **No destructivo:** Preserva todos los datos originales (solo actualiza campos)

---

## Contacto

**Implementado por:** database-dev (Tarea 9-10 del plan de fusión)  
**Fecha:** 4 de Febrero de 2026  
**Plan:** `docs/plans/fusion-viabilidad-presupuesto.md`

Para preguntas o problemas, revisar el plan completo o contactar al equipo de desarrollo.
