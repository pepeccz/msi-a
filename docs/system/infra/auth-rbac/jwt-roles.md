---
titulo: Autenticación y RBAC — JWT + require_role
ambito: infra
ultima_verificacion_commit:
ultima_verificacion_fecha: 2026-04-17
---

# Autenticación y RBAC — JWT + require_role

## Resumen

El acceso al panel de administración y a los endpoints de la API está protegido por JWT (JSON Web Tokens) con RBAC (Role-Based Access Control). Existen dos roles: `operator` y `admin`. El rol determina qué rutas de la API son accesibles. La dependencia `require_role` de FastAPI actúa como guard en cada endpoint protegido.

El panel (Next.js) valida la sesión client-side al cargar y redirige al login si el token expiró. La protección server-side real ocurre en la API: sin JWT válido, los endpoints retornan 401.

## Escenarios

### 1. Login exitoso — emisión de JWT
- CUANDO un usuario del panel envía credenciales válidas a `POST /api/auth/login`
- ENTONCES la API valida usuario + contraseña contra la BD, genera un JWT firmado con `JWT_SECRET_KEY` que incluye `user_id`, `role` y `exp` (expiración configurada en settings), y lo retorna en la respuesta. El panel almacena el token (localStorage o cookie según configuración).

### 2. Request a endpoint protegido — validación JWT
- CUANDO el panel llama a un endpoint protegido (ej. `GET /api/billing/invoices`) con `Authorization: Bearer {token}`
- ENTONCES FastAPI ejecuta la dependencia de autenticación: verifica firma del JWT, verifica `exp` no expirado, extrae el `role` del payload. Si cualquier check falla → 401 Unauthorized. Si pasa → inyecta el usuario en el handler.

### 3. Rol insuficiente — 403 Forbidden
- CUANDO un usuario con rol `operator` intenta acceder a `POST /api/billing/invoices/generate` (que requiere `admin`)
- ENTONCES `require_role("admin")` verifica que el rol del token sea exactamente `admin`. Como el token tiene `operator`, retorna 403 Forbidden. El operador ve un error de permisos en el panel.

### 4. Token expirado — redirect al login
- CUANDO el panel hace una request y recibe 401 (token expirado)
- ENTONCES el cliente del panel (singleton API client) detecta el 401, limpia el token almacenado, y redirige al usuario a la página de login. No hay refresh token automático en el flujo actual.

### 5. Acceso de rol `operator` — rutas permitidas
- CUANDO un usuario con rol `operator` está logueado en el panel
- ENTONCES puede acceder a: gestión de conversaciones, consulta de expedientes, visualización de tariffs/elementos, panel de conversaciones activas. NO puede acceder a: generación de facturas, configuración de billing, gestión de usuarios, seeds, GC.

### 6. Acceso de rol `admin` — rutas completas
- CUANDO un usuario con rol `admin` está logueado en el panel
- ENTONCES tiene acceso a todas las rutas del panel: todo lo del operador más gestión de facturación, configuración del sistema, gestión de usuarios, métricas de validación, token usage, y operaciones destructivas.

### 7. Webhook de Stripe — sin JWT (firma propia)
- CUANDO Stripe llama a `POST /api/billing/stripe/webhook`
- ENTONCES este endpoint NO usa JWT ni `require_role`. La autenticación se realiza exclusivamente mediante `stripe.Webhook.construct_event()` con `STRIPE_WEBHOOK_SECRET`. Firma inválida → 400.

## Reglas duras

1. **JWT + `require_role` en todos los endpoints protegidos**: ningún endpoint que modifique estado o devuelva datos sensibles queda sin guard. La única excepción explícita es el webhook de Stripe (que usa firma propia de Stripe).
2. **`require_role` verifica rol exacto**: no hay herencia de roles (un `operator` no puede hacer lo que hace `admin` aunque ambos tengan JWT válido). La comparación es string equality.
3. **No hay refresh token automático actualmente**: cuando el JWT expira, el usuario debe re-loguearse. No implementar lógica de refresh sin actualizar este spec.
4. **`JWT_SECRET_KEY` en Settings**: la clave de firma nunca se hardcodea en código. Se lee desde `get_settings()` (Pydantic Settings), que la obtiene de variable de entorno.
5. **Protección client-side en el panel es secundaria**: las rutas del panel pueden ocultar secciones según el rol del token, pero la protección real es server-side en la API. El panel puede mostrar u ocultar UI; la API es el boundary de seguridad.

## Mapeo al código

- `api/dependencies/auth.py` (o equivalente) — `require_role` dependency, extracción y validación de JWT del header Authorization.
- `api/routes/auth.py` — `POST /api/auth/login`: validación de credenciales, emisión de JWT.
- `shared/config.py` — `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `JWT_EXPIRATION_MINUTES` (Pydantic Settings).
- `admin-panel/src/lib/api-client.ts` (o equivalente) — Singleton API client que inyecta el token en cada request y maneja 401 redirecting al login.
- `admin-panel/src/middleware.ts` (o equivalente) — Protección client-side de rutas del panel por rol.
- `api/routes/billing.py:316-322` — Webhook de Stripe: sin JWT, con `stripe.Webhook.construct_event()`.

## Fuera de alcance

- Gestión de usuarios (crear/editar/borrar cuentas admin): `api/routes/admin.py`
- Configuración de password hashing: `shared/` o `api/services/auth_service.py`
- Panel de login en el frontend: `admin-panel/src/app/login/**`
- Integración OAuth o SSO — no implementado; este sistema usa credenciales propias
- `database/models.py` — modelo `User` del panel admin (no confundir con `User` de clientes WhatsApp)
