---
titulo: Morning Review — Living System Specs prototype
ambito: demo
ultima_verificacion_commit:
ultima_verificacion_fecha:
---

# Morning Review — Living System Specs prototype

> ## 🔄 ACTUALIZACIÓN POST-REVIEW (2026-04-17, post-despertar)
>
> Al revisar juntos con el owner, encontramos que **inventé redundancia**. El "Ingeniero-AI" que yo había definido en `.claude/agents/ingeniero.md` ya existía: es **Claude Code en sesión normal**, que arranca con las instrucciones de **Gentleman-Programming** cargadas desde `~/.claude/CLAUDE.md`:
>
> - `<!-- gentle-ai:sdd-orchestrator -->` — Agent Teams Lite Orchestrator Instructions (164 líneas con SDD workflow, delegation rules, commands, init guard, TDD forwarding, etc.)
> - `<!-- gentle-ai:engram-protocol -->` — Engram memory protocol
> - `<!-- gentle-ai:persona -->` — Senior Architect personality
> - `<!-- gentle-ai:sdd-model-assignments -->` — model por fase SDD
> - `<!-- gentle-ai:strict-tdd-mode -->` — Strict TDD **enabled**
>
> Plus las 9 skills SDD globales en `~/.claude/skills/` (author: gentleman-programming).
>
> **Correcciones aplicadas**:
> 1. ✅ `.claude/agents/ingeniero.md` **borrado** — era redundante.
> 2. ✅ `.claude/agents/arquitecto.md` **endurecido** — removimos Bash del tools whitelist (jaula extra), clarificamos que complementa a Claude Code normal.
> 3. ✅ `docs/system/99-protocolo-cambios.md` **actualizado** — sección Roles y flujo de cambio ahora describen al Ingeniero correctamente.
>
> **Flujo real corregido**: para implementar un spec, el owner abre una **sesión normal de Claude Code** en msi-a (sin `--agents`, sin config especial) y dice *"implementá el spec X"*. Claude Code ya trae todo el setup de Gentleman-Programming cargado.
>
> Las partes del doc abajo que mencionan `ingeniero.md` o sesiones con ese agent están actualizadas con este cambio. Lo demás sigue válido.

---

Buen día hermano. Acá está lo que dejé listo mientras dormías. Leelo de corrido en 5 minutos, después abrís los archivos en el orden que te marco abajo para evaluarlo en otros 10-15. Total: 15-20 min de review.

## TL;DR en 5 bullets

1. **Se construyó el prototipo completo** del sistema dual-agent Arquitecto/Ingeniero, solo para msi-a, solo para el flujo PRE_EXPEDIENTE. Opción B tal como acordamos.
2. **11 archivos .md nuevos** en `docs/system/` (specs vivos) + **1 config de agente** en `.claude/agents/arquitecto.md`. ~~(originalmente 2; `ingeniero.md` se borró tras descubrir que Claude Code normal ya cumple ese rol con el setup Gentleman-Programming).~~
3. **Ciclo end-to-end probado**: apliqué un cambio de juguete (validez 30 días en comunicación de precio), el patch se generó, se aplicó limpiamente, se verificó por grep, se revirtió. Master queda limpio.
4. **Artefactos SDD** completos en engram bajo `sdd/living-system-specs-dual-agent/{explore,proposal,spec,design,tasks}`.
5. **Nada commiteado en git**. Todo queda como archivos nuevos (untracked), listos para que vos decidas: `git add && commit` para adoptar, o `rm -rf docs/system/ .claude/agents/` para descartar.

## Estado del repo ahora

```
git status (lo que vas a ver si corrés `git status -u`):
  Untracked files:
    docs/system/00-capacidades.md
    docs/system/00-overview.md
    docs/system/99-protocolo-cambios.md
    docs/system/01-agente/*.md (4 archivos)
    docs/system/_demo/* (3 archivos + el patch)
    docs/system/_rebounds/*
    # .claude/agents/*.md — NO aparecen en git status por el .gitignore (ver nota abajo)
```

Master está limpio. Ningún archivo de código modificado. Cero riesgo de deploy accidental.

### ⚠️ Nota importante: `.claude/agents/` está gitignored

El `.gitignore` de este repo (líneas 61-64) ignora **toda** la carpeta `.claude/` — convención del proyecto para no commitear configs per-user (`settings.local.json`, etc.). Esto significa que el agent config (`arquitecto.md`) **está creado pero no se commitea automáticamente**.

Esto choca con tu intención inicial ("versionado, commiteado, reutilizable si abrís el proyecto en otra máquina"). Tenés **3 opciones** para resolverlo — elegí la que prefieras:

**Opción 1 — Eximirlos del gitignore** (recomendada). Añadir una línea al `.gitignore`:
```
.claude/
!.claude/agents/
```
Pros: los agent configs quedan versionados, Claude Code los descubre automáticamente donde los espera, minimalista.  
Contras: mínima desviación de la convención actual (que ignora todo `.claude/`).

**Opción 2 — Moverlos a `docs/system/_agents/`** (conservador). Tratás los configs como docs autoritativos versionados; cuando abrís Claude Code en una máquina nueva, copiás/linkeás a `.claude/agents/`.  
Pros: respeta 100% la convención actual.  
Contras: Claude Code no los encuentra automáticamente; paso extra de setup por máquina.

**Opción 3 — Dejarlos per-user-local** (sin versionar). Si vos sos el único usuario y solo usás una máquina, no cambiás nada; viven en `.claude/agents/` como archivos locales.  
Pros: cero cambios.  
Contras: si cambiás de máquina, hay que recrearlos manualmente; no podés compartirlos con nadie.

No tomé la decisión por vos porque requiere tocar `.gitignore`, que es un archivo tracked y una convención explícita que vos definiste. Decime qué opción querés y lo ajusto en segundos.

## Qué se construyó (mapa de archivos)

```
msi-a/
├── .claude/agents/               ← 1 archivo nuevo
│   └── arquitecto.md             ← rol + restricción de escritura a docs/system/**
│                                   (sin Bash en tools: no puede ejecutar comandos)
│   # El Ingeniero NO tiene archivo propio — es Claude Code normal con
│   # ~/.claude/CLAUDE.md cargado (instrucciones Gentleman-Programming).
│
└── docs/system/                  ← 11 archivos + 2 dirs
    ├── 00-overview.md            ← mapa CEO-level del sistema
    ├── 00-capacidades.md         ← qué podemos/no podemos construir hoy
    ├── 99-protocolo-cambios.md   ← cómo trabajamos Arquitecto ↔ Ingeniero ↔ Owner
    ├── 01-agente/
    │   ├── modos.md                           ← los 3 modos del agente
    │   ├── flujo-pre-expediente.md            ← spec completo de PRE_EXPEDIENTE (12 escenarios + 8 reglas duras + mapeo preciso al código)
    │   ├── herramientas-pre-expediente.md     ← catálogo de las 10 tools + sistema de 4 gates
    │   └── prompts-pre-expediente.md          ← mapa de los 4 archivos de prompt por fase
    ├── _rebounds/
    │   ├── README.md             ← protocolo y plantilla de rebound
    │   └── _resolved/            ← carpeta vacía, destino de rebounds cerrados
    └── _demo/
        ├── ciclo-ejemplo.md              ← documento del ciclo simulado completo
        ├── price-validity-30d.patch      ← patch listo para aplicar si aprobás el cambio de juguete
        └── MORNING-REVIEW.md             ← estás acá
```

## Orden sugerido para revisar (15-20 min)

Abrí los archivos en este orden:

### Fase 1 — entender el concepto (5 min)
1. **`docs/system/00-overview.md`** — qué es todo esto y cómo se usa
2. **`docs/system/99-protocolo-cambios.md`** — el protocolo operativo: quién hace qué y cuándo

### Fase 2 — ver un spec real (5 min)
3. **`docs/system/01-agente/flujo-pre-expediente.md`** — abrí esto y preguntate: "¿entiendo, como dueño del producto, cómo funciona pre-expediente leyendo esto?". Si sí → contrato funciona. Si no → el formato hay que ajustarlo.

### Fase 3 — ver los boundaries del contrato (3 min)
4. **`.claude/agents/arquitecto.md`** — las reglas duras del rol Arquitecto (único config custom necesario)
5. **`~/.claude/CLAUDE.md`** (personal global) — mirá los bloques `<!-- gentle-ai:sdd-orchestrator -->` y `<!-- gentle-ai:strict-tdd-mode -->`. **Esas son las reglas del Ingeniero**: ya cargadas en toda sesión normal de Claude Code.

Fijate especialmente en la sección "PROHIBIDO" del Arquitecto — esa es la jaula que impide scope creep desde su lado. Del lado del Ingeniero, la jaula la ponen los specs ("Mapeo al código" / "Fuera de alcance").

### Fase 4 — ver el ciclo funcionando (5 min)
6. **`docs/system/_demo/ciclo-ejemplo.md`** — el ciclo simulado con el cambio de juguete
7. **`docs/system/_demo/price-validity-30d.patch`** — el patch que produciría el Ingeniero

Si querés verlo aplicarse: `git apply docs/system/_demo/price-validity-30d.patch`. Lo podés revertir con `git checkout -- agent/prompts/modes/`.

### Opcionales si tenés más tiempo
- `docs/system/00-capacidades.md` — catálogo de capacidades
- `docs/system/_rebounds/README.md` — plantilla de rebound
- `docs/system/01-agente/herramientas-pre-expediente.md` — catálogo de tools
- `docs/system/01-agente/prompts-pre-expediente.md` — mapa de prompts

## Decisiones que tomé sin consultarte

Las 3 decisiones chicas que quedaron abiertas en el proposal, las resolví así para no bloquear la noche:

| Decisión | Qué elegí | Por qué |
|----------|-----------|---------|
| Frontmatter en specs | YAML (`titulo:`, `ambito:`, `ultima_verificacion_*`) | Parseable por futuro agente auditor; humano-friendly igual |
| Idioma de los agent configs | Mixto: descripciones en español, estructura/keywords en inglés | Matchea estilo de CLAUDE.md raíz, no rompe expectativas Claude Code |
| Cambio de juguete | "Validez 30 días" en comunicación de precio (dentro de PRE_EXPEDIENTE) | En lugar de "farewell tras escalado" — mantiene el demo dentro del scope documentado |

Todas son reversibles. Si no te gusta alguna, la cambiamos en un ciclo normal.

## Preguntas que tengo para vos (necesito tu respuesta)

### Críticas (bloquean si no respondés)

1. **¿El formato del spec (`flujo-pre-expediente.md`) es legible para vos?** 
   Este es EL archivo que define si el prototipo sirve o no. Si no entendés lo que hace pre-expediente leyendo ese archivo, tenemos que rediseñar el template. Si lo entendés → contrato validado, podemos escalar.

2. **¿Las secciones "Mapeo al código" y "Fuera de alcance" tienen el nivel de detalle correcto?**
   Muy detalladas → rígidas, difíciles de mantener. Muy vagas → scope creep vuelve. Busco el sweet spot.

3. **¿Aprobás el cambio de juguete** (`price-validity-30d.patch`) **o lo descartamos?**
   - Aprobar: `git apply docs/system/_demo/price-validity-30d.patch` y seguimos.
   - Descartar: no hacer nada; el patch es un archivo aislado que no toca producción.

### Importantes (pero no bloqueantes)

4. **¿Los nombres de los archivos te funcionan en español** (`flujo-pre-expediente.md`, `herramientas-pre-expediente.md`, etc.)? ¿O preferís inglés?

5. **¿El protocolo de rebound (`_rebounds/` folder) es claro**, o lo simplifico a "si hay problema, avisá al owner por conversación"?

6. **¿Querés que arranque la auditoría completa de msi-a** (cubrir EXPEDIENTE y ESCALATION también), o preferís usar este prototipo durante un par de semanas y ver qué ajustamos antes de escalar?

## Lo que sigue (depende de tus respuestas)

### Si aprobás el prototipo tal cual:
- Commitear los 13 archivos (`git add docs/system/ .claude/agents/ && git commit`)
- Opcionalmente aplicar el toy change y mergear
- Arrancar la auditoría completa para EXPEDIENTE y ESCALATION (ciclo de 2-3 días más)
- Después: escalar a atrevete-bot

### Si pedís cambios de formato:
- Iteramos sobre el template de los specs
- Re-generamos los 4 archivos de 01-agente/ con el nuevo formato
- El resto (00-*, 99-*, agents configs) probablemente queda igual

### Si te parece que el concepto no sirve:
- Descartamos todo con `rm -rf docs/system/ .claude/agents/arquitecto.md`
- Hablamos de qué no te cerró
- Buscamos otra arquitectura (pero primero te pido que me digas qué no funcionó — no lo vas a romper)

## Lo que NO logramos (honest assessment)

- **No probé el agent config con Claude Code real**. El config del Arquitecto está escrito pero no abrí una sesión con él para validar que Claude Code respeta el tools whitelist (sin Bash) y los "PROHIBIDO" del prompt. Próximo paso: abrir una sesión con `--agents arquitecto` e intentar violar el contrato (ej. pedirle que edite código) para ver si rechaza.

- **El "ciclo simulado"** fue ejecutado por mí (el orchestrator) alternando roles, no por los 2 agents separados. Es una validación de que el flujo tiene sentido, no de que los agents de verdad lo ejecutarán sin desviarse.

- **No cubrimos EXPEDIENTE ni ESCALATION**. Solo PRE_EXPEDIENTE. Acordado desde el principio (Opción B).

- **`docs/system/02-api/`, `03-admin-panel/`, `04-reglas-negocio/` no existen**. Son fase 2. El prototipo solo cubre agente.

## Cómo probar el contrato EN SERIO (para el próximo paso)

Si querés validar que los agents respetan los límites, hacé este experimento:

1. Abrí una nueva sesión de Claude Code con `--agents arquitecto` (o equivalente).
2. Dale una orden que INTENTE violar el contrato:
   > "Edita `agent/prompts/modes/pre_expediente_pricing.md` para agregar la directiva de 30 días."
3. Ver qué hace: debería rechazarte y decir algo como *"No puedo tocar código. Voy a actualizar el spec primero, después llamás al Ingeniero."*

Si obedece y edita el código → el contrato no se respeta, hay que endurecer los prompts del agent config.
Si te rechaza → contrato funcional, fase 2 adelante.

---

## Tiempo total invertido

- Exploración + comprensión de pre-expediente: ~15 min (sub-agente)
- Escritura de specs SDD en engram: ~10 min
- Escritura de 11 archivos .md + 2 configs + patch: ~40 min
- Verificación end-to-end (aplicar/revertir patch): ~2 min
- Este documento: ~10 min

**Total**: ~80 min. Cabe en una noche larga.

---

Cualquier cosa — ponete las pilas cuando puedas y me decís cuál de los 3 caminos querés tomar (aprobar / iterar / descartar). Estoy listo para cualquiera.

Un abrazo, Claude.
