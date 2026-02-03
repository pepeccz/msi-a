# ✅ Implementación Completa: Arquitectura de Agentes MSI-a v2.0

**Fecha**: 3 de Febrero de 2026  
**Estado**: COMPLETADO

---

## 📋 Resumen Ejecutivo

Se ha implementado una arquitectura completa de agentes para MSI-a que separa claramente **planificación** de **ejecución**, con controles estrictos para el entorno de producción.

### Componentes Implementados

1. ✅ **opencode.json** - Configuración completa con 10 agentes
2. ✅ **docs/coding-standards/** - 9 archivos de estándares (1,550+ líneas)
3. ✅ **.gitignore** - Actualizado para ignorar plans y sessions

---

## 🎯 Agentes Configurados (10 Agentes)

### Agentes Primarios (PRIMARY)

| Agente         | Función                                     | Modelo         |
| -------------- | ------------------------------------------- | -------------- |
| **architect**      | Solo planifica, nunca ejecuta               | Sonnet 4.5     |
| **zanovix**        | Mentor general (castellano España)          | Sonnet 4.5     |
| **deploy-dev**     | DevOps con permisos controlados (bash:ask)  | Haiku 4.5      |
| **general-helper** | Tareas simples y directas                   | Sonnet 4.5     |

### Subagentes Especializados (SUBAGENT)

| Agente           | Función                               |
| ---------------- | ------------------------------------- |
| **backend-dev**      | FastAPI + SQLAlchemy                  |
| **agent-dev**        | LangGraph + FSM                       |
| **frontend-dev**     | Next.js 16 + Radix UI                 |
| **database-dev**     | PostgreSQL + Alembic + Seeds          |
| **qa-dev**           | Testing (pytest + Jest)               |
| **investigator-dev** | Diagnóstico de problemas (read-only)  |

### Comandos Predefinidos

```bash
/plan [descripción]    # Activa architect para crear plan
/test [scope]          # Ejecuta tests con qa-dev
/status                # Verifica estado del sistema
/logs [servicio]       # Muestra logs de servicio
```

---

## 📚 Archivos de Coding Standards Creados

| Archivo                      | Tamaño | Contenido                                                                        |
| ---------------------------- | ------ | -------------------------------------------------------------------------------- |
| `README.md`                    | 6.1K   | Guía de navegación y uso                                                         |
| `00-general.md`                | 16K    | Fundamentos: idioma, entorno, ADRs, config, logging, git, docs, performance     |
| `01-python-backend.md`         | 16K    | FastAPI, Pydantic, routes, services, pagination, eager loading, error handling   |
| `02-database.md`               | 8.4K   | SQLAlchemy, Alembic, seeds, dual warnings, UUIDs determinísticos                 |
| `03-agent-architecture.md`     | 4.6K   | LangGraph, tools, modes, anti-patterns (precio antes imágenes, no re-identificar) |
| `04-frontend-react.md`         | 4.5K   | Next.js, Client Components, Radix UI, debounce, AlertDialog                      |
| `05-security.md`               | 4.1K   | JWT, RBAC, SSRF, image validation, path traversal, rate limiting                 |
| `06-shared-utilities.md`       | 2.1K   | Pydantic Settings, Redis Streams, LLM Router, Chatwoot client                    |
| `07-testing.md`                | 2.7K   | pytest, Jest, fixtures, mocking, coverage >90%                                   |
| `08-git-commits.md`            | 1.5K   | Conventional Commits, branch strategy                                            |

**Total**: ~60K de estándares consolidados

---

## 🔄 Flujo de Trabajo Implementado

### Tarea Simple

```
Usuario: "¿Qué es el dual warning system?"
     ↓
Zanovix: Explica directamente con AGENTS.md
```

### Tarea Compleja

```
Usuario: "Necesito agregar plantillas de documentos"
     ↓
Zanovix: "Vale, esto es complejo. ¿Activo el modo architect?"
     ↓
Usuario: "Sí" o /plan plantillas de documentos
     ↓
Architect:
  1. Analiza servicios afectados
  2. Crea plan en docs/plans/plantillas-feature.md
  3. Presenta resumen
     ↓
Usuario: "Aprobado"
     ↓
Architect: Activa subagentes:
  - database-dev: CREATE TABLE document_templates
  - backend-dev: CRUD endpoints
  - agent-dev: Tool generar_documento_desde_plantilla()
  - frontend-dev: Página /documentos/plantillas
     ↓
qa-dev: Tests + coverage >90%
     ↓
Usuario: "Despliega"
     ↓
deploy-dev: Pregunta confirmación → docker-compose restart
```

---

## 🔐 Seguridad y Controles

### deploy-dev (Producción-Safe)

```json
"permission": {
  "bash": "ask"  // TODOS los comandos requieren confirmación
}
```

**Comandos seguros** (solo lectura):
- `docker-compose ps`, `logs`, `stats`, `inspect`

**Comandos que preguntan**:
- `docker-compose restart`, `up -d`, `pull`

**Comandos BLOQUEADOS**:
- `docker-compose down`, `volume rm`, `system prune`

### investigator-dev (Diagnóstico-Only)

```json
"tools": {
  "read": true,
  "glob": true,
  "grep": true,
  "bash": true,
  "write": false,  // NO puede escribir código
  "edit": false    // NO puede editar
}
```

---

## 🌍 Zanovix: Expresiones Castellano de España

**Ahora responde así:**

| Antes (Latino)          | Ahora (Castellano España) |
| ----------------------- | ------------------------- |
| "Loco", "Hermano"       | "Tío", "Colega"           |
| "Ponete las pilas"      | "Espabila", "Venga"       |
| "Buenísimo"             | "Genial", "Estupendo"     |
| "¿Se entiende?"         | "¿Vale?", "¿Entiendes?"   |
| "Ya te estoy diciendo"  | "Te lo estoy diciendo"    |
| "Es así de fácil"       | "Es así de sencillo"      |
| —                       | "Joder" (apropiado)       |
| —                       | "Anda", "Mira"            |
| —                       | "Es una pasada"           |
| —                       | "Flipante"                |

---

## 📖 Reglas Críticas Consolidadas

### General (para TODOS los servicios)

1. ✅ User-facing → ESPAÑOL, Code → INGLÉS
2. ✅ NO ejecutar servicios sin que lo pidan
3. ✅ Auto-invoke skills antes de empezar
4. ✅ Revisar ADRs antes de cambios arquitectónicos
5. ✅ Usar `get_settings()` NUNCA `os.getenv()`
6. ✅ Logging estructurado JSON (structlog)
7. ✅ Async/await para I/O
8. ✅ Type hints completos

### Backend (API)

9. ✅ Pydantic models para request/response
10. ✅ Paginación OBLIGATORIA en listas
11. ✅ `selectinload()` para relaciones
12. ✅ Service layer pattern (lógica en services/)
13. ❌ NUNCA raw SQL

### Database

14. ✅ UUID primary keys (nunca auto-increment)
15. ✅ DateTime(timezone=True)
16. ✅ lazy="selectin" (NUNCA "joined")
17. ✅ ondelete="CASCADE" o "SET NULL"
18. ✅ Implementar downgrade()
19. ✅ JSONB (NO TEXT con JSON)
20. ✅ UUIDs determinísticos (UUID v5)
21. ✅ Dual warning system para elements

### Agent

22. ❌ NUNCA re-identificar después de variante
23. ✅ Precio ANTES de imágenes
24. ✅ skip_validation=True después de ID
25. ✅ FSM tools (NO modificar state directamente)

### Frontend

26. ✅ "use client" para páginas con state
27. ✅ Radix UI (NUNCA native HTML)
28. ✅ toast() (NUNCA alert/confirm)
29. ✅ AlertDialog para destructive
30. ✅ Debounced search (300ms)
31. ✅ Cleanup timers en useEffect return

### Security

32. ✅ JWT + RBAC
33. ✅ SSRF prevention
34. ✅ Image security (multi-layer)
35. ✅ Path traversal prevention
36. ✅ Rate limiting

---

## 🚀 Próximos Pasos

### 1. Probar la Arquitectura

```bash
# Test simple (Zanovix directo)
"¿Qué es el hybrid LLM routing?"

# Test complejo (activa architect)
/plan agregar exportación de casos a PDF

# Test de deploy
/status
/logs api
"Necesito reiniciar el servicio api"  # deploy-dev preguntará
```

### 2. Verificar Configuración

```bash
# Verificar que opencode carga correctamente
opencode config

# Ver agentes disponibles
opencode agent list
```

### 3. Primer Plan Real

Cuando quieras crear tu primera funcionalidad con la nueva arquitectura:

```bash
/plan [descripción de tu feature]
```

El architect:
1. Analizará servicios afectados
2. Creará plan estructurado en docs/plans/
3. Te presentará resumen
4. Esperará tu aprobación
5. Delegará a subagentes con contexto

---

## 📂 Estructura de Archivos Final

```
msi-a/
├── opencode.json                              # ✅ Config completa
├── .gitignore                                 # ✅ Actualizado
└── docs/
    ├── coding-standards/                      # ✅ 9 archivos creados
    │   ├── README.md
    │   ├── 00-general.md
    │   ├── 01-python-backend.md
    │   ├── 02-database.md
    │   ├── 03-agent-architecture.md
    │   ├── 04-frontend-react.md
    │   ├── 05-security.md
    │   ├── 06-shared-utilities.md
    │   ├── 07-testing.md
    │   └── 08-git-commits.md
    └── plans/                                 # Para planes futuros
        └── .gitkeep
```

---

## ✅ Checklist de Implementación

- [x] opencode.json con 10 agentes configurados
- [x] Zanovix con castellano de España
- [x] Architect configurado (solo planifica)
- [x] Subagentes con contexto específico
- [x] deploy-dev con permisos controlados (bash:ask)
- [x] Comandos predefinidos (/plan, /test, /status, /logs)
- [x] docs/coding-standards/ estructura completa
- [x] 9 archivos de estándares creados
- [x] .gitignore actualizado
- [x] instructions carga AGENTS.md + coding-standards

---

## 💡 Tips de Uso

### Para Ti (Usuario)

1. **Tareas simples**: Habla directamente con Zanovix
2. **Tareas complejas**: Usa `/plan [descripción]`
3. **Ver estado**: `/status`
4. **Ver logs**: `/logs [servicio]`
5. **Ejecutar tests**: `/test [scope]`

### Para Zanovix (Agente Principal)

- Evalúa complejidad antes de responder
- Sugiere architect para multi-servicio
- Mantiene expresiones de España
- Siempre pregunta antes de producción

### Para Architect (Planificador)

- NUNCA escribe código directamente
- Siempre crea plan en docs/plans/
- Espera aprobación del usuario
- Delega con contexto específico

### Para Subagentes (Ejecutores)

- Leen su sección del plan
- Leen coding standards relevantes
- Ejecutan tareas asignadas
- Reportan problemas al architect o investigator

---

## 🎉 Conclusión

Has implementado una arquitectura robusta que:

✅ Separa planificación de ejecución  
✅ Protege el entorno de producción  
✅ Mantiene consistencia de código  
✅ Facilita coordinación entre servicios  
✅ Documenta patrones y reglas  
✅ Usa castellano de España naturalmente

**¡Listo para empezar a desarrollar con la nueva arquitectura!**

---

**Creado por**: Claude Sonnet 4.5  
**Fecha**: 3 de Febrero de 2026  
**Sesión**: Implementación completa arquitectura agentes v2.0
