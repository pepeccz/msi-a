---
titulo: Panel admin — usuarios y permisos
ambito: ui
ultima_verificacion_commit:
ultima_verificacion_fecha: 2026-04-17
---

# Panel admin — usuarios y permisos

## Resumen

El área de usuarios permite al admin crear y gestionar las cuentas del equipo de operaciones: crear nuevos operadores, asignar roles (operator/admin), bloquear acceso y revisar el historial de actividad de cada cuenta. La sección de auditoría (`/settings/admin-users`) es exclusiva para admins y registra todos los cambios de roles y permisos.

## Escenarios

### 8. Admin crea usuario nuevo o edita permisos
- CUANDO abre **Usuarios** (`/users`) → botón "Crear Usuario" o click fila → `/users/[id]`
- ENTONCES Dialog de crear con fields: nombre, email, teléfono, rol (operator/admin), estado (activo/bloqueado). Editar en inline form con botón "Guardar Cambios" solo si hay cambios. Delete → AlertDialog rojo "¿Eliminar?".

### 9. Admin ve historial de acceso y actividad
- CUANDO abre **Settings → Admin-Only Sections** (solo admins) → Usuarios Admin (`/settings/admin-users`)
- ENTONCES tabla: usuario, último login, IP, acciones recientes. Log de auditoría. Los cambios de roles/permisos quedan registrados aquí.

## Reglas duras

Ver "Reglas compartidas (aplican a todo el panel)" en [conversaciones.md](./conversaciones.md) para las 13 reglas base del panel.

Reglas propias de usuarios:

- El botón "Guardar Cambios" solo se habilita si el operador modificó al menos un campo respecto al valor guardado (change tracking). No permitir submit vacío.
- La sección `/settings/admin-users` verifica `const { isAdmin } = useAuth()` al montarse. Si `isAdmin` es false, renderiza "No tenés permisos" sin hacer ningún fetch.
- Para las reglas de JWT y RBAC (tokens, roles válidos, expiración), ver [`../../infra/auth-rbac/jwt-roles.md`](../../infra/auth-rbac/jwt-roles.md).

## Mapeo al código

| Ruta | Archivo | Líneas | Qué hace |
|------|---------|--------|----------|
| `/users` | `admin-panel/src/app/(authenticated)/users/page.tsx` | 608 | CRUD usuarios, search, filter rol |
| `/users/[id]` | `admin-panel/src/app/(authenticated)/users/[id]/page.tsx` | 642 | Edit inline, change tracking |
| `/settings/admin-users` | `admin-panel/src/app/(authenticated)/settings/admin-users/page.tsx` | 866 | Admin CRUD + audit logs (admin-only) |

Contextos relevantes:

- `admin-panel/src/contexts/auth-context.tsx` — `AuthProvider`, `useAuth()` = `{ user, isAdmin, hasRole(), logout() }`

API client:

- `admin-panel/src/lib/api.ts` — `api.getUsers()`, `api.createUser()`

## Fuera de alcance

- `api/**` — endpoints de usuarios, hashing de passwords, validación JWT
- `database/**` — modelo ORM de User, migraciones
- `shared/**` — librerías compartidas
