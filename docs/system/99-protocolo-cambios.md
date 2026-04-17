---
titulo: Protocolo de cambios — Arquitecto ↔ Ingeniero ↔ Owner
ambito: meta
ultima_verificacion_commit:
ultima_verificacion_fecha:
---

# Protocolo de cambios

## Objetivo

Definir exactamente cómo se propone, aprueba, implementa y cierra un cambio en MSI-a sin que se produzcan los errores que identificamos en sesiones previas:

1. **Scope creep** — "mientras estaba ahí, toqué X también"
2. **Thrashing arquitectónico** — rebuilds masivos para bugs chicos
3. **Regresiones** — fix que rompe otra cosa
4. **Avance sin confirmación** — ir a código sin que el owner aprobara la decisión
5. **Lenguaje técnico con owner no-programador** — no poder auditar qué se decide

Este protocolo es **de cumplimiento obligatorio**. No es una guía sugerida.

## Tres capas de documentación — cada una con un rol

Para que nadie se confunda sobre dónde escribir o dónde buscar:

| Directorio | Pregunta que responde | Inmutable | Editado por |
|------------|----------------------|-----------|-------------|
| **docs/decisions/** | *¿Por qué tomamos esta decisión hace X meses?* | Sí (ADRs históricos) | Arquitecto-AI al proponer decisiones nuevas; no se editan las viejas |
| **docs/coding-standards/** | *¿Cómo se escribe código en este proyecto?* | Casi inmutable | Ingeniero-AI ocasionalmente, tras consenso |
| **docs/system/** | *¿Qué hace el sistema hoy?* | No — es vivo | Arquitecto-AI con cada cambio aprobado |

Si no sabés dónde escribir algo, preguntate: ¿es una decisión con justificación histórica (por qué)? → `decisions/`. ¿Es una guía de estilo/convención técnica (cómo)? → `coding-standards/`. ¿Es el comportamiento actual del producto (qué)? → `system/`.

## Roles

### Owner (pepe)
- **Autoridad final** sobre todo cambio.
- No programa. Opera en lenguaje de negocio.
- **Responsabilidad clave**: aprobar explícitamente cada diff de spec antes de que pase al Ingeniero. Un "dale" al Arquitecto es un "dale" al spec, no un "dale" al código.

### Arquitecto-AI
- Conversa con el owner.
- **ÚNICO permiso de escritura**: `docs/system/**`.
- **PROHIBIDO**: tocar código fuente, tests, configs de servicios, esquemas de DB, migraciones, o agent configs.
- Antes de proponer un cambio: consulta `docs/system/00-capacidades.md` para validar factibilidad.
- Si el cambio requiere capacidades nuevas, primero propone ampliar el catálogo de capacidades (como change separado).

### Ingeniero-AI
- **Es Claude Code en sesión normal** (no requiere un agent config custom).
- Arranca con las instrucciones de **Gentleman-Programming** ya cargadas desde `~/.claude/CLAUDE.md`: Agent Teams Lite Orchestrator Instructions, Strict TDD Mode, delegation rules, SDD workflow, model assignments, engram protocol.
- Tiene disponibles las 9 skills SDD globales en `~/.claude/skills/` (sdd-init, sdd-explore, sdd-propose, sdd-spec, sdd-design, sdd-tasks, sdd-apply, sdd-verify, sdd-archive) y las skills del proyecto registradas en `.atl/skill-registry.md`.
- Lee commits de spec bajo `docs/system/` como input.
- **Permiso de escritura**: código fuente, tests, migraciones, configs de servicios.
- **PROHIBIDO**: tocar `docs/system/**`, con UNA excepción acotada: actualizar los campos `ultima_verificacion_commit` y `ultima_verificacion_fecha` del frontmatter de specs afectados al momento del archive.
- Si encuentra ambigüedad o imposibilidad en el spec → **rebound** (ver abajo).
- Aplica SDD completo: explore → propose → spec → design → tasks → apply → verify → archive, con **TDD estricto** (RED → GREEN) — viene activado por default desde `~/.claude/CLAUDE.md`.

**Por qué no hay `.claude/agents/ingeniero.md`**: sería redundante. La configuración de Gentleman-Programming en `~/.claude/CLAUDE.md` ya instruye a Claude Code para actuar como orquestador SDD con TDD estricto. Un agent config adicional duplicaría instrucciones y podría entrar en conflicto.

## El ciclo de un cambio

### 1. Owner describe el deseo
En lenguaje libre, sin preocuparse por el código. Ejemplo:
> "Quiero que cuando el cliente ya ha confirmado el presupuesto, si no responde en 5 minutos el bot mande un recordatorio suave."

### 2. Arquitecto-AI pregunta lo que haga falta para concretar
Preguntas CEO-level, no técnicas:
> "¿El recordatorio es una sola vez o se repite? ¿Solo en la fase post-presupuesto o en todo el flujo? ¿Qué pasa si el cliente responde con algo no relacionado?"

El Arquitecto NO avanza a spec hasta que el comportamiento esté **definido con escenarios concretos CUANDO/ENTONCES**.

### 3. Arquitecto-AI propone diff de spec
Muestra al owner el diff del archivo `.md` afectado. Explica en 2-3 frases qué cambia en lenguaje de negocio.

### 4. Owner aprueba o pide ajustes
- Si ajusta: Arquitecto itera.
- Si aprueba: Arquitecto commitea el diff en una rama dedicada (`spec/<slug-corto>`).

### 5. Owner invoca al Ingeniero-AI
Abrís una **sesión normal de Claude Code** en el proyecto msi-a (sin `--agents` ni config especial — Claude Code default). La sesión ya trae cargadas las instrucciones de Gentleman-Programming desde `~/.claude/CLAUDE.md`.

Le decís:
> "Implementá el spec recién commiteado: `docs/system/<path-del-spec>.md`. Está en la rama `spec/<slug>`."

O si preferís usar los comandos SDD directamente:
> "/sdd-new <slug>"  (empieza el ciclo técnico de implementación)
> "/sdd-apply"  (cuando llegues a la fase de apply)

### 6. Ingeniero-AI (Claude Code) ejecuta SDD completo
Claude Code orquesta automáticamente (por las instrucciones globales) delegando a sub-agentes especializados:
- `sdd-explore` si hay código nuevo a descubrir
- `sdd-propose` de la **implementación** (distinto del spec de comportamiento que escribió el Arquitecto)
- `sdd-spec` técnico (requirements de implementación)
- `sdd-design`
- `sdd-tasks`
- `sdd-apply` con **TDD estricto** (RED → GREEN, no saltable)
- `sdd-verify`

Durante esto, Claude Code **solo lee** `docs/system/**`. No escribe ahí. Si el Ingeniero intentara editar un spec, es un bug del protocolo — hay que corregirle con un reminder.

### 7. Ingeniero-AI archiva
- Actualiza frontmatter del spec afectado: `ultima_verificacion_commit: <sha>`, `ultima_verificacion_fecha: <YYYY-MM-DD>`.
- Commitea esto como parte del archive.
- Produce el PR final.

### 8. Owner mergea (o no)
La decisión de mergear es del owner. El Ingeniero-AI entrega el PR listo.

## Rebound — cuando el Ingeniero encuentra problema con el spec

Si el Ingeniero descubre que el spec:
- Es ambiguo (dos interpretaciones posibles)
- Contradice otra sección del mismo o otro spec
- Requiere una capacidad no listada en `00-capacidades.md`
- Es técnicamente imposible con el stack actual

**No puede fijar el spec solo**. Debe rebotar al Arquitecto:

1. Crea archivo en `docs/system/_rebounds/YYYY-MM-DD-<slug-corto>.md` usando la plantilla.
2. **Detiene la implementación** (no commitea código parcial).
3. Notifica al owner: "Encontré este problema, ver rebound X. Necesito que vuelvas a llamar al Arquitecto."
4. Owner invoca al Arquitecto con el rebound.
5. Arquitecto lee rebound, actualiza el spec en consecuencia, commitea.
6. Arquitecto mueve el rebound de `_rebounds/` a `_rebounds/_resolved/` y hace commit referenciando el archivo original.
7. Owner re-invoca al Ingeniero con el spec corregido.

Ver `_rebounds/README.md` para la plantilla de rebound.

## Convenciones de commit

### Commits del Arquitecto-AI
- Rama: `spec/<slug>`
- Mensaje: `spec(<area>): <resumen corto>`
- Cuerpo: qué cambia en lenguaje de negocio, sin referencias a código

### Commits del Ingeniero-AI
- Rama: `feat/<slug>` o `fix/<slug>` según tipo
- Mensaje: conventional commits (`feat(x):`, `fix(y):`, etc.)
- Cuerpo: **obligatoriamente** incluye `Spec-commit: <sha>` apuntando al commit del Arquitecto
- Último commit de la rama = archive commit, con actualización del frontmatter

### Historial auditables
- `git log -- docs/system/` → ve la evolución de la **intención arquitectónica** del producto
- `git log -- agent/` → ve la evolución de la **ejecución**
- Cruzá los dos vía el campo `Spec-commit:` para auditoría completa

## Qué hacer cuando el código y el spec divergen

Escenario: alguien (humano, Ingeniero, o estado legado) modificó código sin actualizar spec, o el spec quedó viejo.

1. **El spec manda**. Si el código hace X y el spec dice Y, la verdad es Y.
2. Si el owner revisa y decide que Y estaba mal y X es correcto, **eso es un nuevo change**: el Arquitecto actualiza Y→X en el spec como cambio normal.
3. **Drift sin autorización = bug**. Tratarlo como tal: abrir un change con el nombre `drift-fix-<area>` y reconciliar.

## Qué hacer cuando hay urgencia real

Si hay un bug en producción que está perdiendo plata ahora mismo:
- El Ingeniero puede hacer un hotfix saltando el ciclo completo.
- **Pero** tras mergear, tiene que crear un rebound auto-descrito (`_rebounds/YYYY-MM-DD-hotfix-<slug>.md`) documentando que el código divergió del spec, para que el Arquitecto lo normalice después.
- El rebound se resuelve en menos de 48h o el hotfix debe revertirse.

Este es el único atajo permitido. Todos los demás cambios siguen el ciclo completo.

## Qué tenemos fuera del protocolo

Cosas que el owner hace directamente sin pasar por Arquitecto ni Ingeniero:
- Editar sus propias notas en `docs/sessions/` (si existen)
- Aprobar/rechazar PRs
- Decidir cuándo deployar

Cosas que el Ingeniero hace sin pasar por Arquitecto:
- Actualizar dependencias por seguridad (patches menores, no mayores)
- Corregir typos en comentarios de código (nunca en specs)
- Mejorar performance sin cambiar comportamiento observable (siempre que tests verifiquen comportamiento)

Todo lo demás: **protocolo completo**.
