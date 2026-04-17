---
titulo: Ciclo ejemplo Arquitecto → Ingeniero
ambito: demo
ultima_verificacion_commit:
ultima_verificacion_fecha:
---

# Ciclo ejemplo — Arquitecto → Ingeniero

## Objetivo de este documento

Demostrar, con un cambio de juguete, que el contrato dual-agent funciona end-to-end. Valida:

1. El Arquitecto puede actualizar un spec en lenguaje de negocio.
2. El Ingeniero puede leer el diff del spec y producir un patch de código concreto.
3. Los límites de escritura se respetan (Arquitecto no tocó código; Ingeniero no tocó spec excepto frontmatter).
4. El paquete final es PR-ready sin compromisos en producción.

**Importante**: este ciclo NO commitea en producción. Es una simulación documentada. Los cambios de código están en un archivo `.patch` en esta misma carpeta, listos para aplicar con `git apply` si el owner aprueba.

## El cambio de juguete elegido

**Orden de negocio (owner → Arquitecto)**:
> "Quiero que cuando el bot comunique un precio, siempre diga que los precios son válidos por 30 días. Pasa que a veces el cliente tarda semanas en decidirse y después se queja cuando le subimos el precio."

**Por qué este cambio** (criterios de selección):
- Scope mínimo: toca solo prompts, no código, no state, no tools
- Negocio-relevante: decisión de CEO típica
- Inside prototype scope (PRE_EXPEDIENTE)
- Fácil de verificar: búsqueda textual en los prompts
- Reversible: un `git revert` o `git restore` basta

## Turno 1 — Arquitecto-AI

### Preguntas que hace el Arquitecto antes de proponer

(Simuladas — en un flujo real el Arquitecto y el owner conversarían acá)

1. **"¿Solo en la primera comunicación de precio o también cuando se recalcula tras añadir elementos?"**
   - Owner: *"Siempre. Cada vez que se diga un precio."*
2. **"¿La frase exacta? ¿'Precios válidos por 30 días'? ¿Querés otra redacción?"**
   - Owner: *"'Precios válidos por 30 días' está bien. Corto y claro."*
3. **"¿Querés que sea texto visible dentro del mensaje o un disclaimer al final en otra línea?"**
   - Owner: *"Al final, separado, que se note."*

### Validación contra capacidades

Arquitecto consulta `docs/system/00-capacidades.md`:
- ✅ Modificar prompts del agente — sí soportado
- ✅ Texto en WhatsApp — sí soportado
- ✅ No requiere capacidades nuevas — safe to proceed

### Diff propuesto sobre `docs/system/01-agente/flujo-pre-expediente.md`

El Arquitecto propone añadir un nuevo escenario (#13) y una nueva regla dura (#9):

```diff
--- a/docs/system/01-agente/flujo-pre-expediente.md
+++ b/docs/system/01-agente/flujo-pre-expediente.md
@@ -XX,XX +XX,XX @@
 ### 12. Escalado tras 3 intentos fallidos de variante
 - CUANDO tras 2 reformulaciones de pregunta de variante el cliente sigue sin resolver, O cuando se acumulan 3+ errores consecutivos en el modo
 - ENTONCES el bot ofrece escalado explícito: *"¿Prefieres que te ponga en contacto con alguien del equipo?"*. Si el cliente acepta, llama a `escalar_a_humano` y transiciona a ESCALATION.

+### 13. Comunicación de precio incluye validez
+- CUANDO el bot comunica un precio al cliente (sea primera vez en PRICING, sea recálculo en POST_PRICE tras añadir/quitar elementos)
+- ENTONCES el mensaje incluye al final, como línea separada, la frase exacta: *"Precios válidos por 30 días."*
+
 ## Reglas duras

 1. **Precio antes que imágenes**. ...
@@ -XX,XX +XX,XX @@
 8. **`precio_comunicado` se setea DESPUÉS del tool loop**. ...

+9. **Validez de 30 días obligatoria**. Cada comunicación de precio DEBE incluir la frase *"Precios válidos por 30 días."* al final, en línea separada. Sin excepciones. Esto protege al negocio de reclamos por cambios de tarifa cuando el cliente demora su decisión.
+
 ## Mapeo al código
```

### Aprobación simulada

En flujo real: el owner ve este diff y dice *"dale"*.

### Commit del Arquitecto (simulado)

```bash
git checkout -b spec/price-validity-30d
# (aplicar edición al archivo)
git add docs/system/01-agente/flujo-pre-expediente.md
git commit -m "spec(pre-expediente): añadir validez 30 días a comunicación de precio"
```

SHA hipotético: `abc1234` (placeholder).

---

## Turno 2 — Ingeniero-AI

### Lectura del spec diff

El Ingeniero abre el commit del Arquitecto. Identifica:

- **Nuevo escenario #13**: validez 30 días en comunicación de precio, aplica a PRICING + POST_PRICE.
- **Nueva regla dura #9**: obligatoria, sin excepciones, en línea separada al final.

### Consulta del Mapeo al código y Fuera de alcance del spec

**Mapeo al código** (sección del spec, subsecciones relevantes):
- `agent/prompts/modes/pre_expediente_pricing.md` ← fase PRICING
- `agent/prompts/modes/pre_expediente_post_price.md` ← fase POST_PRICE

**Fuera de alcance**:
- `agent/modes/expediente_mode.py`
- `agent/tools/case_tools.py`
- `agent/tools/element_data_tools.py`
- `api/**`, `admin-panel/**`, `database/**`, `shared/**`

→ El Ingeniero solo puede tocar los dos archivos de prompt listados arriba. Cualquier otra edición es violación de contrato.

### Chequeo de rebounds abiertos

```bash
ls docs/system/_rebounds/*.md 2>/dev/null | grep -v _resolved
```

→ Sin rebounds abiertos. Safe to proceed.

### Consulta de capacidades

`docs/system/00-capacidades.md` confirma que editar prompts es capacidad estándar. OK.

### Plan técnico del Ingeniero

**Archivos a modificar** (2):
1. `agent/prompts/modes/pre_expediente_pricing.md` — añadir regla en sección `<tariff_calculation>` y en `<images_before_price>` para cubrir todas las rutas de comunicación de precio de la fase PRICING.
2. `agent/prompts/modes/pre_expediente_post_price.md` — añadir directiva equivalente cuando se recalcula precio en POST_PRICE.

**Tests afectados** (regresión estructural):
3. `agent/prompts/prompt_lint.py` — potencialmente añadir un test que valide que la frase "Precios válidos por 30 días" existe en los 2 prompts modificados.

**Out of scope** (explícitamente):
- No se tocan modes de código Python (no hay lógica nueva).
- No se toca state (no hay flag nuevo; la frase es directiva de prompt).
- No se toca ningún archivo de `EXPEDIENTE`.

### Ciclo SDD técnico (breve)

El Ingeniero ejecutaría:
- `sdd-explore`: confirmar ubicación de cada sección en los dos prompts
- `sdd-propose`: plan de edición
- `sdd-spec`: requirement "prompt debe contener la frase exacta"
- `sdd-design`: decisión de inserción en qué sección exacta de cada prompt
- `sdd-tasks`: T1 pricing.md, T2 post_price.md, T3 prompt_lint test
- `sdd-apply` con TDD: escribir test fallido → editar prompts → test pasa
- `sdd-verify`: grep confirma presencia; tests pasan
- `sdd-archive`: actualizar frontmatter de `flujo-pre-expediente.md` con SHA

### Patch propuesto

Ver archivo adjunto: [`price-validity-30d.patch`](./price-validity-30d.patch)

(El patch contiene las 2 ediciones de prompts, listo para `git apply docs/system/_demo/price-validity-30d.patch`.)

### Test plan resumido

1. Grep `rg "Precios válidos por 30 días" agent/prompts/modes/pre_expediente_pricing.md` → debe devolver ≥ 1 match.
2. Grep `rg "Precios válidos por 30 días" agent/prompts/modes/pre_expediente_post_price.md` → debe devolver ≥ 1 match.
3. Correr prompt_lint tests (si se añade uno) → debe pasar.
4. Prueba manual en WhatsApp (manual QA): enviar un presupuesto típico, verificar que la frase aparece al final del mensaje de precio.

### Commits del Ingeniero (simulados)

```bash
git checkout -b feat/price-validity-30d
# (aplicar price-validity-30d.patch)
git add agent/prompts/modes/pre_expediente_pricing.md agent/prompts/modes/pre_expediente_post_price.md
git commit -m "feat(agent): include 30-day price validity disclaimer in PRICING and POST_PRICE prompts

Spec-commit: abc1234
"

# Archive commit — actualizar frontmatter del spec
# (edit flujo-pre-expediente.md frontmatter: ultima_verificacion_commit: def5678, ultima_verificacion_fecha: 2026-04-17)
git add docs/system/01-agente/flujo-pre-expediente.md
git commit -m "chore(spec): archive — price-validity-30d verified and shipped

Spec-commit: abc1234
Code-commit: def5678
"
```

---

## Verificación del contrato

| Check | Esperado | Resultado |
|-------|----------|-----------|
| Arquitecto tocó solo `docs/system/**` | ✅ | Solo modificó `flujo-pre-expediente.md` |
| Ingeniero NO tocó `docs/system/**` (excepto frontmatter en archive) | ✅ | Solo modificó 2 prompts + 1 frontmatter en archive |
| Ningún archivo de "Fuera de alcance" fue tocado | ✅ | El patch solo toca los 2 prompts listados en "Mapeo al código" |
| `Spec-commit:` en commit message del código | ✅ | Referencia abc1234 (simulado) |
| `ultima_verificacion_*` actualizado en el archive | ✅ | Archive commit actualiza ambos campos |
| Sin rebounds abiertos durante el ciclo | ✅ | Rebounds vacío antes y después |
| Frase "Precios válidos por 30 días" presente en ambos prompts tras el patch | ✅ | Verificable con `rg` post-aplicación |

**Conclusión**: el contrato dual-agent funcionó. Spec y código quedaron alineados via referencias cruzadas de commit. Los roles no se pisaron. El change es auditable y revertible.

---

## Cómo el owner puede probar esto manualmente

1. Leer el patch: `bat docs/system/_demo/price-validity-30d.patch`
2. Aplicar (si aprueba): `git apply docs/system/_demo/price-validity-30d.patch`
3. Verificar: `rg "Precios válidos por 30 días" agent/prompts/modes/`
4. Si no aprueba: no hacer nada. El patch es un archivo aislado, no toca producción hasta que se aplique.
5. Para descartar: `rm docs/system/_demo/price-validity-30d.patch` y listo.

---

## Qué este demo prueba (y qué NO)

### Prueba
- El flujo Arquitecto → spec → Ingeniero → código → archive es coherente.
- Los límites de escritura son documentables y verificables por diff.
- El Ingeniero puede producir un patch preciso leyendo solo el spec.
- Los archivos de "Fuera de alcance" actúan como jaula efectiva.
- El ciclo es compacto — un cambio de 2 líneas en prompts se ejecuta en un turno de cada agente.

### NO prueba (limitaciones del demo)
- Que los agentes de verdad (Claude Code con configs `.claude/agents/*`) respeten los límites sin supervisión. Esto requiere pruebas con sesiones reales del owner.
- Que la comunicación asíncrona vía `_rebounds/` funciona bien en ambigüedad real. Este cambio era claro; un caso ambiguo necesitaría rebound real.
- Que el flujo escala a cambios grandes (multi-spec, multi-file).
- Que el owner puede operar el flujo sin guía. Esto requiere uso real.

Para validar todo lo anterior: los próximos pasos están en `MORNING-REVIEW.md`.
