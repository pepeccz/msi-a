---
titulo: Panel admin — monitoring y sistema
ambito: ui
ultima_verificacion_commit:
ultima_verificacion_fecha: 2026-04-17
---

# Panel admin — monitoring y sistema

## Resumen

El área de sistema da visibilidad en tiempo real del estado operativo de MSI-a: salud de los servicios (FastAPI, Redis, PostgreSQL), consumo de tokens LLM, distribución de tráfico entre modelos local y cloud, y métricas del sistema de validación del agente. Incluye el botón de emergencia ("Panic") para apagar el agente si hace falta. Es exclusiva para el rol admin.

## Escenarios

### 10. Admin consulta métricas de uso y tokens
- CUANDO abre **Settings → Uso de Tokens** (`/settings/usage`) o **Métricas LLM** (`/settings/llm-metrics`)
- ENTONCES gráficos de: tokens consumidos hoy/mes, costo estimado, promedio por conversación. LLM Metrics muestra qué porcentaje del tráfico usa qué modelo (local/cloud, fallbacks).

### 11. Admin monitorea salud del sistema
- CUANDO abre **Settings → Sistema** (`/settings/system`)
- ENTONCES dashboard en vivo: estado de servicios (FastAPI, Redis, PostgreSQL — verde/naranja/rojo), últimos errores de API, logs de Docker en tiempo real (SSE stream), botón "Panic" para apagar agent.

### 15. Admin consulta métricas de validación del agente
- CUANDO abre **Settings → Validación** o sección de monitoring
- ENTONCES ve `GET /api/validation-metrics` — estadísticas agregadas del sistema de validación: intentos totales, fallos por tool, tasa de escalación, tasa de éxito en reintento
- Admin puede resetear el contador con `POST /api/validation-metrics/reset` para iniciar nueva ventana de medición
- Acceso: solo admin (requiere JWT + rol admin)
- API backend: `api/routes/validation_metrics.py` — importa `agent.utils.validation_metrics.get_validation_metrics()`

## Reglas duras

Ver "Reglas compartidas (aplican a todo el panel)" en [conversaciones.md](./conversaciones.md) para las 13 reglas base del panel.

Reglas propias de sistema:

- Las tres secciones de esta área (`/settings/usage`, `/settings/llm-metrics`, `/settings/system`) verifican `const { isAdmin } = useAuth()`. Si `isAdmin` es false, renderizan "No tenés permisos" sin hacer ningún fetch.
- Los logs de Docker llegan por SSE stream — el componente debe subscribirse en `useEffect` y cerrar la conexión en el cleanup (return del effect).
- El botón "Panic" requiere confirmación explícita (AlertDialog) antes de ejecutar la acción de apagado del agente.
- Para el modelo de métricas de telemetría y costos, ver [`../../infra/observabilidad/telemetria.md`](../../infra/observabilidad/telemetria.md).
- Para la lógica de routing LLM (qué modelo maneja qué tráfico), ver [`../../infra/llm-router/hibrido.md`](../../infra/llm-router/hibrido.md).

## Mapeo al código

| Ruta | Archivo | Líneas | Qué hace |
|------|---------|--------|----------|
| `/settings/system` | `admin-panel/src/app/(authenticated)/settings/system/page.tsx` | 1030 | Monitor salud, SSE logs, panic button |
| `GET /api/validation-metrics` | `api/routes/validation_metrics.py` | — | Métricas de validación del agente (admin only) |
| `POST /api/validation-metrics/reset` | `api/routes/validation_metrics.py` | — | Reset contadores de validación (admin only) |

## Fuera de alcance

- `agent/**` — lógica interna de validación, `agent.utils.validation_metrics`
- `api/**` — endpoints de métricas, recolección de datos de telemetría
- `database/**` — almacenamiento de métricas históricas
- `shared/**` — LLM router, lógica de fallback entre modelos
