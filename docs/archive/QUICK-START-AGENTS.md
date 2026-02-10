# Guía de Inicio Rápido: Arquitectura de Agentes MSI-a

**Fecha**: 3 de Febrero de 2026  
**Versión**: OpenCode v2.0

---

## 🎯 Agentes Disponibles

### Agentes Primarios (Invoca directamente)

| Agente | Cuándo Usar | Comando |
|--------|-------------|---------|
| **zanovix** | Por defecto - Mentor general, tareas simples/medias | (default) |
| **architect** | Planificar features complejas | `/plan [descripción]` |
| **deploy-dev** | Operaciones Docker, estado del sistema | `/status`, `/logs [servicio]` |
| **general-helper** | Tareas muy simples, lookups rápidos | Llamar directamente |

### Subagentes Especializados (Llamados por architect)

- **backend-dev**: FastAPI routes, services, Pydantic
- **agent-dev**: LangGraph tools, nodes, FSM
- **frontend-dev**: Next.js pages, Radix UI components
- **database-dev**: SQLAlchemy models, Alembic migrations, seeds
- **qa-dev**: pytest, Jest, coverage verification
- **investigator-dev**: Diagnóstico de problemas (read-only)

---

## 🚀 Comandos Rápidos

### Ver Estado del Sistema
```bash
/status
```
Muestra el estado de todos los servicios Docker.

### Ver Logs
```bash
/logs api          # Logs del API
/logs agent        # Logs del agente
/logs admin-panel  # Logs del admin panel
```

### Ejecutar Tests
```bash
/test              # Todos los tests
/test api          # Solo tests del API
/test agent        # Solo tests del agente
```

### Crear un Plan
```bash
/plan agregar sistema de notificaciones por email
```
El architect creará un plan detallado en `docs/plans/`.

---

## 💡 Flujos de Trabajo

### 1. Pregunta Simple
```
Tú: "¿Cómo funciona el dual warning system?"

zanovix: [Explica directamente usando AGENTS.md]
```

### 2. Tarea Simple (Editar un archivo)
```
Tú: "Agrega un campo 'email' al modelo User"

zanovix: [Analiza] "Esto requiere cambios en database + migration + api."
         "¿Quieres que active el architect para planificarlo?"

Tú: "No, solo el campo básico"

zanovix: [Edita database/models.py directamente]
```

### 3. Tarea Compleja (Multi-servicio)
```
Tú: "/plan agregar plantillas de documentos"

architect: [Analiza servicios afectados]
           [Crea docs/plans/plantillas-feature.md]
           [Presenta resumen]
           "Servicios afectados: database, api, agent, admin-panel"
           "Tareas: 7 total (2 database, 2 api, 1 agent, 2 frontend)"
           "¿Procedo con la implementación?"

Tú: "Aprobado"

architect: [Delega a subagentes]
           database-dev → CREATE TABLE document_templates
           backend-dev → CRUD endpoints
           agent-dev → Tool generar_documento()
           frontend-dev → Página /plantillas
           qa-dev → Tests + coverage

architect: "Implementación completa. Tests: 12/12 ✅. Coverage: 94%."

Tú: "Despliega"

deploy-dev: "¿Confirmas reiniciar servicios en producción?"
Tú: "Sí"
deploy-dev: [docker-compose restart api agent]
```

### 4. Investigar un Problema
```
Tú: "El agente no responde después de enviar imágenes"

zanovix: "Vale, voy a activar el investigator-dev"

investigator-dev: [Analiza logs, código, estado]
                  [Reporta hallazgos]
                  "Problema identificado: timeout en Chatwoot API"
                  "Causa: send_images() no tiene retry logic"
                  "Solución propuesta: Agregar tenacity decorator"

zanovix: "¿Quieres que lo arregle directamente o hacemos un plan?"

Tú: "Arréglalo"

backend-dev: [Agrega retry logic]
qa-dev: [Tests para el fix]
```

---

## 📚 Recursos Clave

### Documentación por Servicio
- `api/AGENTS.md` - API routes, services, webhooks
- `agent/AGENTS.md` - LangGraph tools, modes, FSM
- `database/AGENTS.md` - Models, migrations, seeds
- `admin-panel/AGENTS.md` - Next.js pages, components

### Coding Standards Consolidados
- `docs/coding-standards/README.md` - Guía de navegación
- `docs/coding-standards/00-general.md` - Fundamentos (LEER PRIMERO)
- `docs/coding-standards/01-python-backend.md` - FastAPI patterns
- `docs/coding-standards/02-database.md` - SQLAlchemy, Alembic
- `docs/coding-standards/03-agent-architecture.md` - LangGraph, FSM
- `docs/coding-standards/04-frontend-react.md` - Next.js, Radix UI
- `docs/coding-standards/05-security.md` - JWT, RBAC, SSRF
- `docs/coding-standards/06-shared-utilities.md` - Config, Redis, LLM
- `docs/coding-standards/07-testing.md` - pytest, Jest
- `docs/coding-standards/08-git-commits.md` - Conventional Commits

### Plans (Planes de Implementación)
- `docs/plans/` - Planes creados por architect

---

## ⚠️ Recordatorios Importantes

### Entorno de Producción
- Estás trabajando en el servidor de **PRODUCCIÓN**
- Todo cambio puede afectar al servicio de WhatsApp
- Los agentes tienen permisos completos (sin confirmación)
- Prudencia antes de comandos destructivos

### Permisos de Agentes
- **TODOS** los agentes pueden ejecutar bash sin pedir confirmación
- Incluye comandos destructivos como `docker-compose down`, `rm -rf`, etc.
- **TÚ** eres el control final - revisa antes de aprobar acciones críticas

### Filosofía de Trabajo
1. **Tareas simples**: zanovix responde directamente
2. **Tareas complejas**: architect planifica primero
3. **Siempre preguntar**: Para cambios en producción
4. **Plans son documentos**: Quedan en docs/plans/ para referencia

---

## 🔍 Troubleshooting

### "No encuentro el agente X"
Verifica que `opencode.json` está en la raíz del proyecto:
```bash
ls -la opencode.json
```

### "El agente no carga los coding standards"
Verifica que existen:
```bash
ls -la docs/coding-standards/
```

### "El architect no crea planes"
Verifica que el directorio existe:
```bash
ls -la docs/plans/
```

### "Los servicios no responden"
Verifica el estado:
```bash
docker-compose ps
```

Revisa logs:
```bash
docker-compose logs -f [servicio]
```

---

## 📋 Checklist: Primera Vez

- [ ] Verificar que `opencode.json` existe
- [ ] Verificar que `docs/coding-standards/` está completo (9 archivos)
- [ ] Verificar servicios Docker funcionando (`/status`)
- [ ] Probar comando simple: "¿Qué es MSI-a?"
- [ ] Probar comando complejo: `/plan ejemplo simple`
- [ ] Revisar plan creado en `docs/plans/`

---

## 🎓 Próximos Pasos Sugeridos

1. **Familiarízate con los comandos**:
   - Ejecuta `/status` para ver el estado
   - Ejecuta `/logs api` para ver logs
   - Pregunta algo simple a zanovix

2. **Crea tu primer plan**:
   - Piensa en una feature que necesites
   - Ejecuta `/plan [tu feature]`
   - Revisa el plan generado
   - Aprueba o pide ajustes

3. **Explora los coding standards**:
   - Lee `docs/coding-standards/README.md`
   - Lee `docs/coding-standards/00-general.md`
   - Lee el estándar de tu área (backend, frontend, database, agent)

4. **Revisa un plan existente**:
   - Abre `docs/plans/fix-conversation-context-loss.md`
   - Observa la estructura de un plan completo
   - Usa como referencia para futuros planes

---

## 🌟 Diferencias con la Arquitectura Anterior

### Antes (Gentleman)
- Un solo agente hacía todo
- Sin planificación formal
- Sin separación de concerns
- Expresiones en español latino

### Ahora (OpenCode v2.0)
- ✅ **architect** planifica, subagentes ejecutan
- ✅ Planes documentados en `docs/plans/`
- ✅ Cada subagente experto en su servicio
- ✅ **zanovix** habla castellano de España
- ✅ Coding standards consolidados
- ✅ Comandos predefinidos (`/plan`, `/test`, `/status`, `/logs`)

---

## 🔗 Enlaces Útiles

- [AGENTS.md (root)](../AGENTS.md) - Overview del proyecto
- [Coding Standards](coding-standards/README.md) - Guía de estándares
- [Architecture Decisions](decisions/) - ADRs
- [Skills Directory](../skills/) - Patrones detallados
- [Implementación Completa](coding-standards/IMPLEMENTACION-COMPLETA.md) - Detalles de la implementación
- [Migración v1→v2](MIGRACION-AGENTS-V2.md) - Guía de migración

---

**¡Listo para empezar a desarrollar con la nueva arquitectura!**

**Creado**: 3 de Febrero de 2026  
**Última actualización**: 3 de Febrero de 2026
