# ⚠️ PERMISOS ACTUALIZADOS - Ejecución Sin Restricciones

**Fecha**: 3 de Febrero de 2026  
**Estado**: ACTIVO

---

## Cambio Realizado

Se ha **eliminado la restricción de permisos** `"permission": { "bash": "ask" }` del archivo `opencode.json`.

### Antes ❌

```json
"permission": {
  "bash": "ask"  // Pedía confirmación para cada comando
}
```

Los agentes pedían confirmación antes de ejecutar **cualquier** comando bash.

### Ahora ✅

```json
// Sin restricciones de permisos
```

Los agentes pueden ejecutar comandos bash **directamente** sin pedir permiso.

---

## ⚠️ IMPORTANTE: Servidor de Producción

Estás trabajando en el **servidor de PRODUCCIÓN** de MSI-a donde corre el servicio de WhatsApp para clientes reales.

### Ventajas del Cambio

✅ **Mayor velocidad** - No interrupciones para comandos simples  
✅ **Flujo continuo** - Los agentes completan tareas sin pausas  
✅ **Menos fricción** - Para tests, builds, deploys rutinarios  

### Riesgos del Cambio

⚠️ **Comandos destructivos** - Los agentes pueden ejecutar `docker-compose down`, `rm -rf`, etc.  
⚠️ **Impacto en producción** - Errores pueden afectar el servicio de WhatsApp  
⚠️ **Mayor responsabilidad** - Tú debes ser más específico con las instrucciones  

---

## Permisos por Agente

### Agentes PRIMARY

| Agente         | Bash | Write | Edit | Puede Hacer                                       |
| -------------- | ---- | ----- | ---- | ------------------------------------------------- |
| **zanovix**        | ✅    | ✅     | ✅    | Comandos completos, editar código, ejecutar tests |
| **architect**      | ❌    | ✅     | ❌    | Solo crear planes (NO ejecuta código ni comandos) |
| **deploy-dev**     | ✅    | ❌     | ❌    | Comandos Docker completos (lectura + gestión)     |
| **general-helper** | ✅    | ✅     | ✅    | Comandos básicos, editar archivos simples         |

### Subagentes (SUBAGENT)

| Agente           | Bash | Write | Edit | Puede Hacer                          |
| ---------------- | ---- | ----- | ---- | ------------------------------------ |
| **backend-dev**      | ✅    | ✅     | ✅    | pytest, pip install, editar API      |
| **agent-dev**        | ✅    | ✅     | ✅    | pytest, editar tools, prompts        |
| **frontend-dev**     | ✅    | ✅     | ✅    | npm test, build, editar componentes  |
| **database-dev**     | ✅    | ✅     | ✅    | alembic migrate, seeds, editar models |
| **qa-dev**           | ✅    | ✅     | ✅    | pytest, jest, coverage reports       |
| **investigator-dev** | ✅    | ❌     | ❌    | Solo lectura + diagnóstico           |

---

## Comandos que Ahora se Ejecutan sin Pedir

### Desarrollo (Safe)

```bash
# Tests
pytest tests/
npm test
jest

# Build
npm run build
docker-compose build

# Logs y estado (lectura)
docker-compose ps
docker-compose logs api
docker stats

# Git
git status
git diff
git log
```

### Gestión (Moderado)

```bash
# Servicios
docker-compose restart api
docker-compose up -d agent
docker-compose pull

# Base de datos
alembic upgrade head
python -m database.seeds.run_all_seeds

# Dependencias
pip install -r requirements.txt
npm install
```

### Destructivos (⚠️ Usar con Precaución)

```bash
# ESTOS AHORA SE EJECUTAN SIN PEDIR CONFIRMACIÓN
docker-compose down              # Detiene TODOS los servicios
docker-compose down -v           # Elimina volúmenes (DATOS)
docker volume rm msi-a_postgres  # Elimina datos de DB
docker system prune              # Limpia Docker (puede borrar cosas)
rm -rf uploads/                  # Borra archivos
```

---

## Recomendaciones de Uso

### 1. Sé Específico con tus Instrucciones

**❌ Vago:**
```
"Arregla el servicio api"
```

**✅ Específico:**
```
"Reinicia el servicio api con docker-compose restart api y muéstrame los logs"
```

### 2. Revisa Planes Antes de Aprobar

Cuando uses `/plan`, el architect te mostrará qué se va a hacer. **Revísalo antes de decir "Aprobado"**.

### 3. Usa Comandos de Lectura Primero

```bash
# Antes de reiniciar, verifica estado
/status                    # Ver qué está corriendo
/logs api                  # Ver si hay errores
```

### 4. Backups

Asegúrate de tener backups recientes antes de:
- Cambios en base de datos (migraciones)
- Actualizaciones de dependencias
- Cambios en configuración Docker

### 5. Horarios de Bajo Tráfico

Para cambios con impacto, considera:
- Madrugada (2-6 AM)
- Domingos
- Días festivos

---

## Seguridad Adicional en los Prompts

Aunque los agentes tienen permisos completos, están instruidos para:

### deploy-dev

```
"TRABAJAS EN PRODUCCIÓN. Extrema cautela requerida."

"Un error puede detener el servicio de WhatsApp de clientes reales."

"Cuando en duda, PREGUNTAR siempre."
```

### Todos los agentes

```
"RECUERDA: Estás trabajando en el servidor de PRODUCCIÓN de MSI-a."

"Todo cambio puede afectar al servicio de WhatsApp."

"Prudencia y planificación primero."
```

Pero **la última línea de defensa eres TÚ**. Los agentes ejecutarán lo que les pidas.

---

## Rollback (Volver a Pedir Confirmación)

Si quieres volver al sistema anterior donde se pide confirmación:

1. Edita `opencode.json`
2. Agrega antes de `"mcp"`:

```json
"permission": {
  "bash": "ask"
},
```

3. Guarda el archivo

Los agentes volverán a pedir confirmación para cada comando bash.

---

## Monitoreo

Para estar seguro, monitorea:

```bash
# Ver qué está pasando
docker-compose ps

# Ver logs en tiempo real
docker-compose logs -f api
docker-compose logs -f agent

# Ver uso de recursos
docker stats

# Ver últimos comandos ejecutados
history | tail -20
```

---

## Conclusión

**Tienes el control total** pero con **mayor responsabilidad**.

Los agentes están instruidos para ser cautelosos, pero ejecutarán lo que les pidas sin pedir confirmación.

**Recomendación**: Sé claro, específico y revisa los planes antes de aprobarlos.

---

**Creado**: 3 de Febrero de 2026  
**Autor**: Claude Sonnet 4.5
