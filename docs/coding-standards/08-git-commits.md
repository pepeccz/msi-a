# Estándares de Git Commits

---

## 1. Conventional Commits

```
<type>(<scope>): <subject>

[optional body]
```

### Types

- `feat`: Nueva funcionalidad
- `fix`: Corrección de bug
- `docs`: Cambios en documentación
- `refactor`: Refactor sin cambio de comportamiento
- `test`: Agregar/modificar tests
- `chore`: Mantenimiento (deps, config)
- `perf`: Mejoras de performance
- `style`: Formato de código (no funcionalidad)

### Examples

```
feat(api): add document template endpoints
fix(agent): prevent re-identification after variant question
docs(database): update seed system documentation
refactor(admin): extract dialog component to shared
test(api): add coverage for tariff calculation
chore(deps): update fastapi to 0.104.1
perf(database): add index on users.phone column
```

---

## 2. Branch Strategy

```
main              # Producción
  ├── develop       # Desarrollo
  │   ├── feature/document-templates
  │   ├── fix/agent-price-before-images
  │   └── refactor/admin-dialog-components
```

### Naming

- Feature: `feature/short-description`
- Fix: `fix/short-description`
- Refactor: `refactor/short-description`

---

## 3. Reglas

1. ✅ Commits atómicos (1 logical change)
2. ✅ Subject en imperativo ("add" not "added")
3. ✅ Subject < 72 chars
4. ✅ Body explains "why" not "what"
5. ❌ NUNCA commit directo a main
6. ❌ NUNCA "WIP", "test", "fix" sin contexto

---

**Referencias:**
- `skills/git-commits/SKILL.md`

**Última actualización:** Febrero 2026
