# Migración AGENTS.md a Arquitectura v2.0

**Fecha**: 3 de Febrero de 2026  
**Estado**: COMPLETADO

---

## Cambios Realizados

### 1. AGENTS.md (root) - ACTUALIZADO ✅

**Agregado:**
- Nueva sección "Agent Architecture (OpenCode v2.0)" al principio
- Tabla de agentes disponibles (10 agentes)
- Comandos predefinidos (`/plan`, `/test`, `/status`, `/logs`)
- Workflow examples (Simple Task vs Complex Task)
- Referencia a `docs/coding-standards/`

**Ubicación**: Líneas 3-58 del archivo raíz AGENTS.md

---

## Mapeo de Agentes Viejos → Nuevos

| Antes | Ahora | Cambio |
|-------|-------|--------|
| `gentleman` | `zanovix` | Renombrado + castellano España |
| (no existía) | `architect` | NUEVO - Solo planifica |
| `backend-dev` | `backend-dev` | Sin cambios (ahora subagent) |
| `agent-dev` | `agent-dev` | Sin cambios (ahora subagent) |
| `frontend-dev` | `frontend-dev` | Sin cambios (ahora subagent) |
| `database-eng` | `database-dev` | Renombrado |
| (no existía) | `qa-dev` | NUEVO - Testing specialist |
| (no existía) | `deploy-dev` | NUEVO - DevOps controlado |
| (no existía) | `investigator-dev` | NUEVO - Diagnóstico read-only |
| `general-helper` | `general-helper` | Sin cambios (sigue siendo PRIMARY) |

---

## Agentes Específicos por Componente

Los AGENTS.md de cada componente (`api/`, `agent/`, `database/`, `admin-panel/`) **NO necesitan actualización** porque:

1. Se enfocan en **patrones técnicos específicos** del componente
2. No mencionan agentes específicos de OpenCode
3. Los subagentes los leen automáticamente según su dominio:
   - `backend-dev` lee `api/AGENTS.md`
   - `agent-dev` lee `agent/AGENTS.md`
   - `database-dev` lee `database/AGENTS.md`
   - `frontend-dev` lee `admin-panel/AGENTS.md`

---

## Nuevos Comandos Disponibles

Antes no había comandos predefinidos. Ahora:

```bash
/plan [descripción]     # Activa architect para crear plan
/test [scope]           # Ejecuta tests con qa-dev
/status                 # Verifica estado del sistema
/logs [servicio]        # Muestra logs de Docker
```

---

## Coding Standards (NUEVO)

Antes: Todo estaba disperso en múltiples AGENTS.md

Ahora: Consolidado en `docs/coding-standards/`:
- `00-general.md` - Fundamentos para TODOS
- `01-python-backend.md` - FastAPI patterns
- `02-database.md` - SQLAlchemy + Alembic
- `03-agent-architecture.md` - LangGraph + FSM
- `04-frontend-react.md` - Next.js + Radix UI
- `05-security.md` - JWT, RBAC, SSRF
- `06-shared-utilities.md` - Config, Redis, LLM Router
- `07-testing.md` - pytest + Jest
- `08-git-commits.md` - Conventional Commits

---

## Workflow Anterior vs Nuevo

### Anterior (Problema)

```
Usuario: "Agrega feature X"
     ↓
gentleman: Implementa directamente (sin plan)
     ↓
Riesgo: Cambios en producción sin coordinación
```

### Nuevo (Solución)

```
Usuario: "Agrega feature X" o /plan feature X
     ↓
zanovix: Evalúa complejidad
  - Si SIMPLE → Ayuda directa
  - Si COMPLEJO → Sugiere architect
     ↓
architect: 
  1. Analiza servicios afectados
  2. Crea plan en docs/plans/
  3. Espera aprobación
     ↓
Usuario: "Aprobado"
     ↓
architect: Delega a subagents (database-dev, backend-dev, etc.)
     ↓
qa-dev: Verifica tests
     ↓
Usuario: "Deploy"
     ↓
deploy-dev: Pregunta confirmación → Ejecuta
```

---

## Beneficios de v2.0

1. ✅ **Separación planificación/ejecución** - architect solo planifica
2. ✅ **Seguridad en producción** - deploy-dev siempre pregunta
3. ✅ **Coordinación multi-servicio** - planes estructurados
4. ✅ **Estándares consolidados** - docs/coding-standards/
5. ✅ **Diagnóstico sin riesgo** - investigator-dev read-only
6. ✅ **Testing automático** - qa-dev verifica coverage
7. ✅ **Idioma coherente** - zanovix con castellano España

---

## Verificación de Compatibilidad

### ✅ Archivos Actualizados

- [x] `opencode.json` - Nueva configuración
- [x] `AGENTS.md` (root) - Sección Agent Architecture agregada
- [x] `.gitignore` - Ignora docs/plans/, .opencode/sessions/
- [x] `docs/coding-standards/` - 9 archivos creados
- [x] `docs/coding-standards/README.md` - Guía de uso

### ✅ Archivos Sin Cambios (Compatibles)

- [x] `api/AGENTS.md` - Patterns técnicos, leído por backend-dev
- [x] `agent/AGENTS.md` - Patterns técnicos, leído por agent-dev
- [x] `database/AGENTS.md` - Patterns técnicos, leído por database-dev
- [x] `admin-panel/AGENTS.md` - Patterns técnicos, leído por frontend-dev
- [x] `skills/**/SKILL.md` - Sin cambios, siguen siendo válidos

---

## Próximos Pasos Recomendados

### 1. Testear Comandos

```bash
# Simple
"¿Qué es el hybrid LLM routing?"

# Complejo
/plan agregar sistema de notificaciones push

# Status
/status

# Logs
/logs api
```

### 2. Primer Plan Real

Cuando necesites una feature:
```bash
/plan [descripción detallada]
```

### 3. Familiarizarse con Coding Standards

Lee en orden:
1. `docs/coding-standards/00-general.md`
2. Tu área específica (backend/agent/frontend/database)
3. `docs/coding-standards/05-security.md`

---

## Notas de Compatibilidad

### Skills

Todos los skills existentes **siguen siendo válidos** y compatibles con la nueva arquitectura. Los subagentes los cargan según necesidad.

### ADRs (Architecture Decision Records)

Los ADRs en `docs/decisions/` **siguen vigentes**. La nueva arquitectura no cambia decisiones técnicas previas.

### Migraciones y Seeds

No hay cambios en el sistema de migraciones o seeds. La arquitectura es solo para **desarrollo** y **despliegue**, no afecta el schema de base de datos.

---

**Creado por**: Claude Sonnet 4.5  
**Fecha**: 3 de Febrero de 2026
