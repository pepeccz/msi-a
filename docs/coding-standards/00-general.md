# Estándares Generales de Desarrollo MSI-a

## Propósito

Este documento establece las reglas fundamentales que aplican a **TODOS** los componentes del proyecto MSI-a (API, Agent, Database, Admin Panel). Son la base sobre la que se construyen los estándares específicos de cada servicio.

---

## 1. Política de Idioma

### Regla Fundamental

```
User-facing content → ESPAÑOL
Code & Documentation → INGLÉS
```

### Ejemplos

**✅ CORRECTO:**
```python
# Code en inglés
def calculate_total_price(elements: list[str]) -> Decimal:
    """Calculate total price for homologation elements."""
    # User-facing message en español
    return {
        "message": "El presupuesto total es de 450€ + IVA",
        "price": Decimal("450.00")
    }
```

**❌ INCORRECTO:**
```python
# Code mezclado
def calcularPrecioTotal(elementos: list[str]) -> Decimal:
    """Calcula el precio total para elementos de homologación."""
    return {
        "message": "The total budget is 450€ + VAT",  # WRONG!
        "precio": Decimal("450.00")
    }
```

### User-Facing Content Incluye

- Mensajes del agente conversacional
- Labels de UI en admin panel
- Mensajes de error mostrados al usuario
- Notificaciones toast
- Emails y comunicaciones

### Code & Documentation Incluye

- Nombres de variables, funciones, clases
- Comentarios en código
- Docstrings
- Documentación técnica (este archivo)
- Commits de git
- Nombres de archivos

---

## 2. Entorno de Desarrollo

### ⚠️ CRÍTICO: No Ejecutar Servicios Localmente

El desarrollo ocurre en tu máquina local, pero **los servicios corren en un servidor separado** que tiene la potencia necesaria para testing y ejecución.

**Reglas:**
- ✅ Edita código localmente
- ✅ Analiza y responde preguntas
- ✅ Crea archivos y modificaciones
- ❌ **NO** ejecutes docker-compose up/down sin que te lo pidan explícitamente
- ❌ **NO** ejecutes npm start/dev
- ❌ **NO** ejecutes python -m agent.main o python -m api.main

### Comandos Permitidos

**Análisis de código (siempre OK):**
```bash
rg "pattern" --type python        # Buscar en código
fd "*.py" api/                    # Encontrar archivos
bat file.py                       # Ver contenido
```

**Testing (OK con precaución):**
```bash
pytest tests/test_specific.py    # Tests unitarios
jest admin-panel/               # Tests frontend
```

**Docker (SOLO si el usuario lo pide):**
```bash
docker-compose ps               # Ver estado (solo lectura)
docker-compose logs api         # Ver logs (solo lectura)
docker-compose up -d            # SOLO si lo pide el usuario
```

---

## 3. Auto-invoke Skills

Antes de comenzar cualquier tarea, **SIEMPRE** carga el skill correspondiente al dominio.

### Mapeo de Acciones → Skills

| Acción                                    | Skill                   |
| ----------------------------------------- | ----------------------- |
| Crear/modificar routes API                | `msia-api`, `fastapi`     |
| Crear/modificar agent tools               | `msia-agent`, `langgraph` |
| Crear/modificar database models           | `msia-database`           |
| Crear/modificar admin components          | `msia-admin`              |
| Trabajar con sistema de tarifas           | `msia-tariffs`            |
| Trabajar con sistema RAG                  | `msia-rag`                |
| Escribir tests                            | `msia-test`, `pytest-async` |
| Commits de git                            | `git-commits`             |
| Crear nuevos skills                       | `skill-creator`           |
| General MSI-a overview                    | `msia`                    |

### Cómo Cargar Skills

El sistema carga skills automáticamente basándose en las reglas de auto-invoke. Si no estás seguro de qué skill cargar, pregunta al usuario o revisa `AGENTS.md`.

---

## 4. Architecture Decision Records (ADRs)

Antes de proponer cambios arquitectónicos significativos, **SIEMPRE** revisa los ADRs existentes en `docs/decisions/`.

### ADRs Existentes

| ADR | Decisión                                         | Implicaciones                                |
| --- | ------------------------------------------------ | -------------------------------------------- |
| 001 | Redis Streams para message queuing               | Usar Streams, no Pub/Sub                     |
| 002 | Dynamic prompts (core + phase)                   | Token optimization, mantener estructura      |
| 003 | Eliminar Chatwoot attention check                | El agente nunca pregunta si necesita atención |

### Cuándo Crear un Nuevo ADR

- Cambio de tecnología core (ej: cambiar de PostgreSQL a MongoDB)
- Cambio de patrón arquitectónico (ej: de FSM a Event Sourcing)
- Decisión que afecta a múltiples servicios
- Trade-off técnico significativo

### Formato de ADR

```markdown
# ADR-004: [Título]

## Status
Proposed | Accepted | Deprecated

## Context
[Por qué consideramos este cambio]

## Decision
[Qué decidimos hacer]

## Consequences
**Positivas:**
- Beneficio 1
- Beneficio 2

**Negativas:**
- Trade-off 1
- Trade-off 2

## Alternatives Considered
- Alternativa 1: [Razón por la que no se eligió]
- Alternativa 2: [Razón por la que no se eligió]
```

---

## 5. Configuration Management

### NUNCA Usar `os.getenv()` Directamente

**✅ CORRECTO:**
```python
from shared.config import get_settings

settings = get_settings()
database_url = settings.DATABASE_URL
llm_model = settings.LLM_MODEL
```

**❌ INCORRECTO:**
```python
import os

database_url = os.getenv("DATABASE_URL")  # WRONG!
llm_model = os.environ.get("LLM_MODEL")   # WRONG!
```

### Por Qué

- **Centralización**: Todas las variables de entorno en un solo lugar (`shared/config.py`)
- **Validación**: Pydantic valida tipos y valores al inicio
- **Testing**: Más fácil mockear `get_settings()` que `os.getenv()`
- **Type Safety**: Auto-completado en IDEs
- **Documentación**: Todas las variables documentadas en una sola clase

### Agregar Nueva Variable de Entorno

1. Agregar a `shared/config.py`:
```python
class Settings(BaseSettings):
    # Existing...
    NEW_FEATURE_ENABLED: bool = Field(False, description="Enable new feature")
```

2. Agregar a `.env.example`:
```bash
# New Feature
NEW_FEATURE_ENABLED=false
```

3. Actualizar lista de variables en `AGENTS.md` (sección Environment Variables)

---

## 6. Logging

### Structured JSON Logging Solamente

**✅ CORRECTO:**
```python
import structlog

logger = structlog.get_logger(__name__)

logger.info(
    "user_created",
    user_id=str(user.id),
    phone=sanitize_phone(user.phone),
    client_type=user.client_type
)
```

**❌ INCORRECTO:**
```python
print(f"User created: {user.id}")  # WRONG!
logging.info("User created")       # WRONG! (no structured)
```

### Por Qué

- **Parseable**: Logs pueden ser parseados por herramientas (CloudWatch, ELK, etc.)
- **Searchable**: Buscar por campos específicos (`user_id`, `error_type`)
- **Sanitized**: Función `sanitize_phone()` oculta números de teléfono completos
- **Contextual**: Incluir información relevante como `conversation_id`, `tool_name`

### Niveles de Log

| Nivel   | Uso                                                       |
| ------- | --------------------------------------------------------- |
| DEBUG   | Información detallada para debugging (no en producción)   |
| INFO    | Eventos normales del sistema (user created, message sent) |
| WARNING | Eventos inesperados pero manejables (fallback usado)      |
| ERROR   | Errores que requieren atención (API call failed)          |
| CRITICAL | Sistema no funcional (DB connection lost)                 |

---

## 7. Error Handling

### Principio: Never Trust Input, Never Expose Internals

**Backend (API/Agent):**
```python
try:
    result = await external_service.call()
except ServiceUnavailableError as e:
    # Log internal details
    logger.error("external_service_failed", error=str(e), stack_trace=traceback.format_exc())
    
    # Return generic error to user
    raise HTTPException(status_code=503, detail="Servicio temporalmente no disponible")
```

**Frontend (Admin):**
```typescript
try {
  await api.createUser(data);
  toast.success("Usuario creado correctamente");
} catch (error) {
  console.error("Create user failed:", error);
  toast.error("Error al crear usuario. Por favor, intenta de nuevo.");
}
```

### Por Qué

- **Security**: No exponer detalles de implementación (rutas de archivos, stack traces, versiones)
- **UX**: Mensajes útiles para el usuario, no dumps técnicos
- **Debugging**: Logs completos en servidor para diagnóstico

---

## 8. Version Control

### Conventional Commits

Todos los commits deben seguir el formato:

```
<type>(<scope>): <subject>

[optional body]
```

**Types:**
- `feat`: Nueva funcionalidad
- `fix`: Corrección de bug
- `docs`: Cambios en documentación
- `refactor`: Refactor sin cambio de comportamiento
- `test`: Agregar/modificar tests
- `chore`: Mantenimiento (deps, config)

**Examples:**
```
feat(api): add document template endpoints
fix(agent): prevent re-identification after variant question
docs(database): update seed system documentation
refactor(admin): extract dialog component to shared
test(api): add coverage for tariff calculation
```

### Branch Strategy

```
main           # Producción (protegido)
  ├── develop    # Desarrollo (integración)
  │   ├── feature/add-document-templates
  │   ├── fix/agent-price-before-images
  │   └── refactor/admin-dialog-components
```

**Reglas:**
- NUNCA commit directo a `main`
- Feature branches desde `develop`
- Pull Request para merge a `develop` o `main`
- Squash commits en merge (mantener historia limpia)

---

## 9. Herramientas CLI Preferidas

Usa herramientas modernas sobre legacy:

| Legacy | Moderno | Uso                          |
| ------ | ------- | ---------------------------- |
| `cat`    | `bat`     | Ver contenido de archivos    |
| `grep`   | `rg`      | Buscar en archivos           |
| `find`   | `fd`      | Encontrar archivos           |
| `sed`    | `sd`      | Buscar y reemplazar          |
| `ls`     | `eza`     | Listar archivos con detalles |

**Instalación (si faltan):**
```bash
brew install bat ripgrep fd sd eza
```

---

## 10. Security Basics

Estos se profundizan en `05-security.md`, pero son fundamentales:

1. **Nunca hardcodear secretos** → usar `.env` y `get_settings()`
2. **Validar TODO input del usuario** → usar Pydantic models
3. **Sanitizar outputs** → prevenir XSS, SQL injection
4. **HTTPS only** → nunca HTTP en producción
5. **Rate limiting** → proteger endpoints públicos
6. **JWT con expiry** → tokens de autenticación con TTL

---

## 11. Testing Philosophy

```
Unit Tests > Integration Tests > E2E Tests
```

**Coverage target**: >90% para código crítico (API routes, Agent tools, Database models)

**Testing Pyramid:**
```
     /\        E2E (pocos, lentos, frágiles)
    /  \       
   /____\      Integration (algunos, medios)
  /      \     
 /________\    Unit (muchos, rápidos, confiables)
```

**Reglas:**
- Tests unitarios NUNCA dependen de DB real → usar SQLite in-memory
- Tests NUNCA dependen de servicios externos → usar mocks
- Tests deben ser determinísticos → no depender de timestamps, random, etc.

---

## 12. Documentation Standards

### Code Comments

**Cuándo comentar:**
- Lógica compleja no obvia
- Workarounds temporales (con TODO/FIXME)
- Business rules importantes
- Decisiones arquitectónicas no evidentes

**Cuándo NO comentar:**
```python
# BAD: Obvio
user_count = len(users)  # Count users

# GOOD: Explica el "por qué"
# Usamos +1 porque el admin user no está en la lista pero cuenta para el límite
user_count = len(users) + 1
```

### Docstrings

**Python (Google style):**
```python
def calculate_tariff(
    elements: list[str],
    category_slug: str,
    skip_validation: bool = False
) -> dict[str, Any]:
    """
    Calculate homologation tariff based on elements and category.
    
    Args:
        elements: List of element codes (e.g., ["ESCAPE", "MANILLAR"])
        category_slug: Vehicle category (e.g., "motos-part")
        skip_validation: Skip element validation (use after identification)
    
    Returns:
        Dict with:
            - success (bool): Whether calculation succeeded
            - precio (Decimal): Price without VAT
            - warnings (list[str]): Applicable warnings
            - message (str): User-facing message in Spanish
    
    Raises:
        ValueError: If category doesn't exist
        ValidationError: If elements are invalid and skip_validation=False
    """
    ...
```

**TypeScript (JSDoc):**
```typescript
/**
 * Create a new vehicle category.
 * 
 * @param data - Category creation data
 * @returns Created category with ID
 * @throws {Error} If category slug already exists
 */
async function createCategory(data: CategoryCreate): Promise<Category> {
  ...
}
```

---

## 13. Dependency Management

### Python (Backend/Agent)

- **File**: `requirements.txt`
- **Versiones**: Pin MAJOR.MINOR (ej: `fastapi==0.104.1`)
- **Testing deps**: Separadas en `requirements-dev.txt` si es necesario

**Actualizar dependencias:**
```bash
pip install --upgrade [package]
pip freeze > requirements.txt
```

### TypeScript (Admin Panel)

- **File**: `package.json`
- **Versiones**: Use caret `^` para MINOR updates (ej: `"next": "^16.0.0"`)
- **Lock file**: `package-lock.json` (commitear)

**Actualizar dependencias:**
```bash
npm update [package]
npm audit fix  # Vulnerabilities
```

---

## 14. Performance Guidelines

### General

- **Async/await** para todas las operaciones I/O
- **Pagination** en TODOS los endpoints de lista
- **Caching** para datos que cambian poco (Redis)
- **Eager loading** para relaciones frecuentes (selectinload)
- **Indexes** en columnas de búsqueda/filtro frecuentes

### Database

```python
# BAD: N+1 query problem
users = await session.execute(select(User))
for user in users:
    # Lazy load = 1 query per user!
    print(user.conversations)

# GOOD: Eager loading
stmt = select(User).options(selectinload(User.conversations))
users = await session.execute(stmt)
for user in users:
    print(user.conversations)  # Already loaded!
```

### API

```python
# BAD: No pagination
@router.get("/users")
async def list_users():
    users = await session.execute(select(User))
    return users.scalars().all()  # Could be millions!

# GOOD: Pagination
@router.get("/users")
async def list_users(limit: int = 50, offset: int = 0):
    total = (await session.execute(select(func.count(User.id)))).scalar()
    users = await session.execute(select(User).offset(offset).limit(limit))
    return {
        "items": users.scalars().all(),
        "total": total,
        "has_more": offset + limit < total
    }
```

---

## 15. Git Workflow para Planes

### Después de Crear un Plan

1. **Architect crea plan** en `docs/plans/[nombre].md`
2. **Usuario aprueba** el plan
3. **Architect delega** a subagentes con contexto
4. **Subagentes ejecutan** sus tareas
5. **QA verifica** tests y criteria
6. **Usuario aprueba deploy**
7. **Deploy-dev ejecuta** con confirmación

### Commits Durante Implementación

**NO commitear** hasta que el plan esté completamente implementado y testeado.

**Razón**: Queremos commits atómicos por feature completa, no commits intermedios de cada archivo.

**Excepción**: Si el plan tiene fases claramente separadas, se puede commitear por fase.

---

## 16. Continuous Integration (CI/CD)

Actualmente el proyecto NO tiene CI/CD automatizado. El flujo es:

```
Local Dev → Manual Testing → Manual Deploy (deploy-dev agent)
```

**Futuro (recomendado):**
- GitHub Actions para run tests en PR
- Linting automático (ruff, eslint)
- Type checking (mypy, tsc)
- Deploy automático a staging tras merge a develop

---

## Referencias

- `AGENTS.md` (root) - Overview completo del proyecto
- `docs/decisions/` - Architecture Decision Records
- Skills específicos en `skills/msia-*/` - Patrones detallados por servicio
- Coding standards específicos en `docs/coding-standards/01-08-*.md`

---

**Última actualización**: Febrero 2026
