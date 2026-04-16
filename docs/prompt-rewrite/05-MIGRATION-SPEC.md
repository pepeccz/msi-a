# Spec de Migración — Cambios de Código Necesarios

> Este documento lista los cambios de código necesarios para activar los nuevos prompts.
> NO son cambios de prompt — son cambios en loader.py y tool results.

---

## Cambio 1: loader.py — Nueva pipeline de ensamblado

### Antes
```python
CORE_MODULES = [
    "core/01_security.md", "core/02_identity.md", "core/03_format_style.md",
    "core/04_anti_patterns.md", "core/05_tools_efficiency.md", "core/06_escalation.md",
    "core/07_pricing_rules.md", "core/08_documentation.md", "core/09_inline_questions.md",
    "core/10_expediente_universal.md",
]
# + SECURITY_START + mode + context + SECURITY_END
```

### Después
```python
CORE_MODULE = "core.md"  # Single file with XML tags
# Assembly: core + mode + context (no security bookend)
```

### Cambios específicos:
1. `load_core_modules()` → carga un solo `core.md` en vez de 10 archivos
2. `assemble_system_prompt()`:
   - Eliminar `SECURITY_START` y `SECURITY_END` (seguridad ya está en `<security>` del core)
   - Orden: core → mode → context (sin bookends)
3. `MODE_MODULES` dict → actualizar nombres de archivos para los nuevos
4. `_resolve_mode_key()` → sin cambios (misma lógica de selección)

---

## Cambio 2: Tool results — Eliminar instrucciones embebidas que compiten

### identificar_y_resolver_elementos (element_tools.py ~línea 1588)

**Antes**: El tool result incluye:
```python
response["instrucciones"] = (
    "Si el usuario pidió PRECIO → llama calcular_tarifa... "
    "Si pidió DOCUMENTACIÓN → responde con el campo documentacion..."
)
```

**Después**: Eliminar el campo `instrucciones` del return. El system prompt ya tiene las instrucciones. El tool result solo devuelve DATOS.

### Filtrar documentacion_base cuando ya fue mostrada

**Antes**: `identificar_y_resolver_elementos` siempre retorna `documentacion_base` completa.

**Después**: Si `mode_context.get("element_codes")` ya tiene elementos (es un "agregar"), NO incluir `documentacion_base` en el return — ya fue mostrada. Solo incluir la documentación del nuevo elemento.

**Implementación**: En la función del tool, verificar el state:
```python
# Si ya hay elementos previos, omitir documentacion_base
existing_codes = state_context.get("element_codes", [])
if existing_codes:
    response.pop("documentacion_base", None)
```

---

## Cambio 3: Archivos de prompt — Swap

### Mover archivos actuales a backup
```bash
mv agent/prompts/core/ agent/prompts/core-v1/
mv agent/prompts/modes/ agent/prompts/modes-v1/
```

### Copiar nuevos archivos
```bash
cp docs/prompt-rewrite/new-prompts/core.md agent/prompts/core.md
cp docs/prompt-rewrite/new-prompts/modes/*.md agent/prompts/modes/
```

### Mantener sin cambios
- `agent/prompts/loader.py` — modificar según Cambio 1
- `agent/prompts/state_summary.py` — sin cambios
- `agent/prompts/calculator_base.py` — sin cambios (legacy)

---

## Cambio 4: format_mode_context — Sin cambios sustanciales

El `format_mode_context()` en loader.py se mantiene igual — inyecta el mismo contexto dinámico. Solo ajustar si el nuevo core.md espera un formato diferente (no debería).

---

## Resumen de impacto

| Archivo | Tipo de cambio | Riesgo |
|---------|---------------|--------|
| `agent/prompts/core.md` | NUEVO (reemplaza 10 archivos) | Bajo — es texto |
| `agent/prompts/modes/*.md` | NUEVOS (reemplazan 9 archivos) | Bajo — es texto |
| `agent/prompts/loader.py` | MODIFICAR assembly pipeline | Medio — afecta qué ve el LLM |
| `agent/tools/element_tools.py` | MODIFICAR tool return | Medio — eliminar instrucciones embebidas |
| `agent/prompts/core-v1/` | BACKUP | Sin riesgo |
| `agent/prompts/modes-v1/` | BACKUP | Sin riesgo |

## Rollback

Si algo falla:
```bash
rm agent/prompts/core.md
mv agent/prompts/core-v1/ agent/prompts/core/
rm agent/prompts/modes/*.md
mv agent/prompts/modes-v1/ agent/prompts/modes/
# Revert loader.py y element_tools.py via git
```
