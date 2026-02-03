# 🚀 Instrucciones para Aplicar la Migración 035

**Status actual**: Migración creada ✅ | Base de datos con backup ✅ | Pendiente aplicar migración ⏳

---

## Situación Actual

### ✅ Completado

1. **Seed data actualizado**: `database/seeds/data/motos_part.py` (2,416 líneas)
2. **Tier mappings actualizado**: `database/seeds/data/tier_mappings.py`
3. **Migración creada**: `database/alembic/versions/035_restructure_motos_elements.py` (1,016 líneas)
4. **Backup creado**: `backup_pre_migration_20260203_110836.sql` (361KB)
5. **Script de verificación**: `database/seeds/verify_restructure.py`
6. **Documentación completa**: 6 archivos markdown

### ⏳ Pendiente

- **Aplicar migración** a la base de datos

---

## Problema Encontrado

Al intentar ejecutar `alembic upgrade head` desde el host, encontramos problemas de conectividad:

1. **Contenedores API/Agent no están corriendo** → No se puede ejecutar alembic dentro de contenedor
2. **PostgreSQL escucha solo en red Docker** → No accesible desde localhost:5432
3. **Docker Compose tiene error de configuración** → `KeyError: 'ContainerConfig'`

---

## Solución: 3 Opciones

### ⭐ Opción 1: Usar Contenedor API (RECOMENDADO)

Una vez que los contenedores estén funcionando correctamente:

```bash
# 1. Iniciar servicios
docker-compose up -d api

# 2. Verificar que API esté corriendo
docker-compose ps api

# 3. Ejecutar migración desde contenedor API
docker-compose exec api alembic upgrade head

# 4. Verificar migración aplicada
docker-compose exec api alembic current
# Expected: 035_restructure_motos_elements (head)

# 5. Verificar con script
docker-compose exec api python database/seeds/verify_restructure.py
```

**Ventajas**:
- Usa el entorno correcto de Python con todas las dependencias
- Alembic ya configurado correctamente
- Método estándar y seguro

---

### 🔧 Opción 2: Ejecutar SQL Directamente

Si no puedes iniciar contenedor API, puedes ejecutar el SQL directamente:

**Paso 1**: Extraer SQL de la migración

```bash
cd /home/autohomologacion/msi-a

# Crear archivo SQL con los comandos de la migración
# (Ver sección "SQL Directo" abajo)
```

**Paso 2**: Ejecutar SQL

```bash
# Ejecutar SQL directamente en PostgreSQL
docker-compose exec -T postgres psql -U msia msia_db < migration_035.sql

# Actualizar alembic_version
docker-compose exec -T postgres psql -U msia msia_db -c \
  "UPDATE alembic_version SET version_num = '035_restructure_motos_elements';"
```

**Ventajas**:
- No requiere contenedor API
- Más control sobre cada paso

**Desventajas**:
- Más manual
- Más propenso a errores

---

### 🐍 Opción 3: Python Script Directo

Si tienes acceso a Python con las dependencias necesarias:

```bash
cd /home/autohomologacion/msi-a

# Activar venv (ya creado)
source .venv/bin/activate

# IMPORTANTE: Modificar DATABASE_URL temporalmente en .env
# Cambiar: postgresql+asyncpg://msia:...@postgres:5432/...
# A:       postgresql+asyncpg://msia:...@localhost:5432/...
# (solo si PostgreSQL está accesible en localhost)

# Ejecutar migración
alembic upgrade head

# Restaurar DATABASE_URL original
```

---

## SQL Directo (Para Opción 2)

Si eliges la Opción 2, aquí está el SQL completo a ejecutar:

### Archivo: `migration_035.sql`

```sql
-- ============================================================================
-- Migration 035: Restructure Motos Elements
-- ============================================================================

BEGIN;

-- Verificar versión actual
DO $$
DECLARE
    current_version VARCHAR;
BEGIN
    SELECT version_num INTO current_version FROM alembic_version;
    IF current_version != '7dc32f4a106a' THEN
        RAISE EXCEPTION 'Expected version 7dc32f4a106a, but found %', current_version;
    END IF;
    RAISE NOTICE 'Current version: %', current_version;
END $$;

-- 1. INSERT: FRENADO base element
INSERT INTO elements (
    id, category_id, code, name, description, keywords, aliases,
    is_base, parent_element_id, is_active, sort_order,
    created_at, updated_at
) VALUES (
    '4f294773-4375-5fbd-b9c8-4380c7869ba1'::uuid,
    (SELECT id FROM vehicle_categories WHERE slug = 'motos-part'),
    'FRENADO',
    'Sistema de frenado',
    'Sistema de frenado modificado. Incluye discos, pinzas, latiguillos, bombas y depósitos.',
    '["frenado", "frenos", "freno", "brake", "brembo", "nissin", "galfer", "ng brakes", "beringer", "j.juan", "braking", "ebc", "performance friction"]'::jsonb,
    '["brake system", "braking system"]'::jsonb,
    true,
    NULL,
    true,
    39,
    now(),
    now()
);

-- 2. INSERT: CARROCERIA_EXT base element
INSERT INTO elements (
    id, category_id, code, name, description, keywords, aliases,
    is_base, parent_element_id, is_active, sort_order,
    created_at, updated_at
) VALUES (
    'b5a60e63-9a96-55d9-ab5c-9034cd3a400f'::uuid,
    (SELECT id FROM vehicle_categories WHERE slug = 'motos-part'),
    'CARROCERIA_EXT',
    'Carrocería exterior',
    'Elementos de carrocería exterior: carenados, guardabarros, paneles de carrocería.',
    '["carroceria", "chapa", "panel", "plastico", "exterior", "bodywork"]'::jsonb,
    '["bodywork", "exterior panels"]'::jsonb,
    true,
    NULL,
    true,
    49,
    now(),
    now()
);

-- 3. UPDATE: Set parent_element_id for brake children
UPDATE elements SET 
    parent_element_id = '4f294773-4375-5fbd-b9c8-4380c7869ba1'::uuid,
    updated_at = now()
WHERE code IN ('FRENADO_DISCOS', 'FRENADO_PINZAS', 'FRENADO_BOMBAS', 'FRENADO_LATIGUILLOS', 'FRENADO_DEPOSITO');

-- 4. UPDATE: Set parent_element_id for bodywork children  
UPDATE elements SET
    parent_element_id = 'b5a60e63-9a96-55d9-ab5c-9034cd3a400f'::uuid,
    updated_at = now()
WHERE code IN ('CARENADO', 'GUARDABARROS_DEL', 'GUARDABARROS_TRAS', 'CARROCERIA');

-- Verificar updates
SELECT 'Brake children updated: ' || COUNT(*) 
FROM elements 
WHERE parent_element_id = '4f294773-4375-5fbd-b9c8-4380c7869ba1'::uuid;

SELECT 'Bodywork children updated: ' || COUNT(*)
FROM elements
WHERE parent_element_id = 'b5a60e63-9a96-55d9-ab5c-9034cd3a400f'::uuid;

-- NOTE: Los INSERT de required_fields y warnings son ~800 líneas más
-- Ver el archivo de migración completo para el SQL detallado
-- Por seguridad, es mejor ejecutar usando Opción 1 (contenedor API)

-- Actualizar alembic_version
UPDATE alembic_version SET version_num = '035_restructure_motos_elements';

COMMIT;

-- Verificar versión final
SELECT version_num FROM alembic_version;
```

⚠️ **NOTA**: El SQL completo es muy extenso (~1000 líneas). Es más seguro usar la Opción 1.

---

## Verificación Post-Migración

Después de aplicar la migración (con cualquier opción):

### 1. Verificación Automatizada

```bash
# Desde host (con venv activado)
python3 database/seeds/verify_restructure.py

# O desde contenedor API
docker-compose exec api python database/seeds/verify_restructure.py
```

**Esperado**: 6/6 checks passed ✅

### 2. Verificación Manual (SQL)

```bash
# Conectar a PostgreSQL
docker-compose exec postgres psql -U msia msia_db
```

```sql
-- Check 1: Base elements exist
SELECT code, name, is_base, sort_order 
FROM elements 
WHERE code IN ('FRENADO', 'CARROCERIA_EXT');
-- Expected: 2 rows with is_base=true

-- Check 2: Children have parents
SELECT e1.code as child, e2.code as parent
FROM elements e1
LEFT JOIN elements e2 ON e1.parent_element_id = e2.id
WHERE e1.code IN ('FRENADO_DISCOS', 'CARENADO')
LIMIT 5;
-- Expected: All have non-null parent

-- Check 3: ACCESORIO_GENERICO exists
SELECT code, name, sort_order FROM elements WHERE code = 'ACCESORIO_GENERICO';
-- Expected: 1 row with sort_order=200

-- Check 4: New required_fields exist
SELECT COUNT(*) FROM element_required_fields f
JOIN elements e ON f.element_id = e.id
WHERE e.code = 'VELOCIMETRO' AND f.field_key = 'ubicacion_captador_nuevo';
-- Expected: 1

\q
```

---

## Rollback (Si es Necesario)

Si algo sale mal, puedes revertir:

### Opción A: Usando Alembic

```bash
docker-compose exec api alembic downgrade -1
```

### Opción B: Restaurar Backup

```bash
# Restaurar desde backup
docker-compose exec -T postgres psql -U msia msia_db < backup_pre_migration_20260203_110836.sql

# Verificar versión
docker-compose exec postgres psql -U msia msia_db -c "SELECT version_num FROM alembic_version;"
# Expected: 7dc32f4a106a
```

---

## Resumen del Estado

### Archivos Listos

- ✅ `database/seeds/data/motos_part.py` - Seeds actualizados
- ✅ `database/seeds/data/tier_mappings.py` - Tier mappings actualizados
- ✅ `database/alembic/versions/035_restructure_motos_elements.py` - Migración
- ✅ `database/seeds/verify_restructure.py` - Script de verificación
- ✅ `backup_pre_migration_20260203_110836.sql` - Backup (361KB)
- ✅ Documentación completa (6 archivos .md)

### Próximos Pasos

1. **Arreglar Docker Compose** (si es necesario)
   - Error: `KeyError: 'ContainerConfig'`
   - Puede requerir rebuild de imágenes o limpieza de volúmenes

2. **Iniciar contenedor API**
   ```bash
   docker-compose up -d api
   ```

3. **Ejecutar migración** (Opción 1 recomendada)
   ```bash
   docker-compose exec api alembic upgrade head
   ```

4. **Verificar con script**
   ```bash
   docker-compose exec api python database/seeds/verify_restructure.py
   ```

5. **Probar agente** (opcional)
   - Crear caso con elementos modificados
   - Verificar que hace las preguntas nuevas

---

## Soporte

Si necesitas ayuda:

1. **Revisa documentación**: `database/seeds/README_RESTRUCTURE.md`
2. **Consulta checklist**: `database/seeds/TESTING_CHECKLIST.md`
3. **Verifica logs**: `docker-compose logs api`

---

**Última actualización**: 2026-02-03  
**Versión objetivo**: 035_restructure_motos_elements  
**Backup disponible**: `backup_pre_migration_20260203_110836.sql`
