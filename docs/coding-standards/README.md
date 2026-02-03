# Coding Standards MSI-a

Estándares de código consolidados para mantener consistencia across todos los servicios del proyecto MSI-a.

## Estructura

| Archivo | Líneas est. | Propósito | Estado |
|---------|-------------|-----------|---------|
| `00-general.md` | ~1 00 | Fundamentos aplicables a TODOS los componentes | ✅ Creado |
| `01-python-backend.md` | ~200 | FastAPI, Pydantic, estructura de routes/services | ⏳ Pendiente |
| `02-database.md` | ~250 | SQLAlchemy, Alembic, seeds, dual warning system | ⏳ Pendiente |
| `03-agent-architecture.md` | ~300 | LangGraph, modes, FSM, tools, anti-patterns | ⏳ Pendiente |
| `04-frontend-react.md` | ~250 | Next.js, Client Components, Radix UI, API client | ⏳ Pendiente |
| `05-security.md` | ~150 | JWT, RBAC, SSRF, image validation, path traversal | ⏳ Pendiente |
| `06-shared-utilities.md` | ~150 | Pydantic Settings, Redis Streams, LLM Router | ⏳ Pendiente |
| `07-testing.md` | ~100 | pytest-async, Jest, fixtures, mocking | ⏳ Pendiente |
| `08-git-commits.md` | ~50 | Conventional Commits, branch strategy | ⏳ Pendiente |

**Total**: ~1,550 líneas (consolidado desde ~3,085 líneas de 5 AGENTS.md)

---

## Cómo Usar Estos Estándares

### Para Desarrolladores Humanos

1. **Lee `00-general.md`** primero - contiene las reglas fundamentales
2. **Lee el estándar específico** de tu área (backend/frontend/database/agent)
3. **Referencia** los estándares durante code reviews
4. **Actualiza** los estándares cuando surjan nuevos patrones

### Para Agentes de IA (Zanovix, Subagentes)

Los agentes están configurados para cargar automáticamente estos estándares vía la directiva `instructions` en `opencode.json`:

```json
"instructions": [
  "AGENTS.md",
  "docs/coding-standards/*.md"
]
```

**Cada subagente tiene en su prompt**:
```
REFERENCIAS:
Antes de empezar, lee:
- docs/coding-standards/XX-[area].md
- [area]/AGENTS.md (sección Critical Rules)
```

---

## Orden de Lectura Recomendado

1. **00-general.md** → Fundamentos (TODOS los devs)
2. **Tu área específica** → Patrones detallados
3. **05-security.md** → Security concerns (TODOS los devs)
4. **07-testing.md** → Testing patterns (TODOS los devs)
5. **Otros** según necesites

---

## Relación con AGENTS.md

Los `AGENTS.md` en cada directorio (`api/`, `agent/`, `database/`, `admin-panel/`) contienen:
- Inventarios de componentes (routes, tools, models, etc.)
- Diagramas de arquitectura
- Flujos de datos
- Referencias a skills
- Critical rules (las más importantes están aquí también)

**Estos coding standards** consolidan las reglas críticas comunes y agregan ejemplos detallados de código.

---

## Creación de Archivos Pendientes

### Comando para crear todos a la vez

```bash
# Desde Zanovix o architect:
"Crea los archivos de coding standards pendientes (01-08) basándote en el análisis 
de AGENTS.md y patterns existentes que ya tienes en contexto de esta sesión."
```

### Crear uno por uno

```bash
# Ejemplo para backend:
"Crea docs/coding-standards/01-python-backend.md basándote en:
- api/AGENTS.md sección Critical Rules
- Análisis de patrones en api/routes/ y api/services/
- Skills fastapi y msia-api"
```

---

## Fuentes de Información (Para Generación)

Cada archivo debe extraer información de:

### 01-python-backend.md
- `api/AGENTS.md` - Critical Rules, Route Architecture, Security
- `skills/fastapi/SKILL.md` - FastAPI patterns
- `skills/msia-api/SKILL.md` - MSI-a specific API patterns
- Análisis de código: `api/routes/*.py`, `api/services/*.py`

### 02-database.md
- `database/AGENTS.md` - Critical Rules, Model Inventory, Migration Patterns
- `database/seeds/WARNING_SYSTEM.md` - Dual warning system
- `skills/sqlalchemy-async/SKILL.md` - SQLAlchemy patterns
- `skills/msia-database/SKILL.md` - MSI-a specific DB patterns

### 03-agent-architecture.md
- `agent/AGENTS.md` - Critical Rules, Anti-Patterns, Mode Architecture
- `skills/langgraph/SKILL.md` - LangGraph patterns
- `skills/msia-agent/SKILL.md` - MSI-a specific agent patterns
- Análisis de código: `agent/tools/*.py`, `agent/modes/*.py`

### 04-frontend-react.md
- `admin-panel/AGENTS.md` - Critical Rules, Component Patterns
- `skills/nextjs-16/SKILL.md` - Next.js patterns
- `skills/radix-tailwind/SKILL.md` - Radix UI patterns
- `skills/typescript-frontend-patterns/SKILL.md`
- Análisis de código: `admin-panel/src/components/`, `admin-panel/src/app/`

### 05-security.md
- `AGENTS.md` (root) - Security Architecture
- `api/AGENTS.md` - JWT, RBAC, SSRF, Image Security
- `shared/image_security.py` - Multi-layer validation
- `shared/chatwoot_client.py` - SSRF prevention

### 06-shared-utilities.md
- `AGENTS.md` (root) - Shared Component inventory
- `shared/config.py` - Pydantic Settings
- `shared/redis_client.py` - Redis Streams
- `shared/llm_router.py` - Hybrid LLM architecture

### 07-testing.md
- `tests/conftest.py` - Fixtures
- `skills/pytest-async/SKILL.md` - pytest patterns
- `skills/msia-test/SKILL.md` - MSI-a testing conventions
- `admin-panel/jest.config.js` - Jest config

### 08-git-commits.md
- `skills/git-commits/SKILL.md` - Conventional Commits
- `.git/config` - Branch strategy

---

## Mantenimiento

### Cuándo Actualizar

- **Nueva pattern emerge** → Documentar aquí
- **Decisión de arquitectura** → Actualizar estándares afectados
- **Bug causado por no seguir estándar** → Clarificar estándar
- **Nueva tecnología agregada** → Crear/actualizar sección

### Proceso de Actualización

1. Identificar qué archivo(s) necesitan cambio
2. Proponer cambio en PR o discusión
3. Actualizar archivo con fecha de última actualización
4. Notificar al equipo del cambio

---

## Enlaces Rápidos

- [AGENTS.md (root)](../../AGENTS.md) - Overview completo del proyecto
- [Architecture Decisions](../decisions/) - ADRs
- [Skills Directory](../../skills/) - Patrones detallados por tecnología
- [API Documentation](../../api/AGENTS.md)
- [Agent Documentation](../../agent/AGENTS.md)
- [Database Documentation](../../database/AGENTS.md)
- [Admin Panel Documentation](../../admin-panel/AGENTS.md)

---

**Creado**: Febrero 2026  
**Última actualización**: Febrero 2026
