---
name: msia-prompts
description: >
  MSI-a agent prompts editing gateway — canonical location map, token budgets, and anti-patterns.
  Trigger: When editing, reviewing, or creating any file under agent/prompts/**/*.md.
metadata:
  author: msi-automotive
  version: "1.0"
  scope: [root, agent]
  auto_invoke:
    - "Editing agent system prompts"
    - "Modifying files in agent/prompts/"
    - "Adding rules to prompt modules"
    - "Working on prompt .md files"
    - "Creating new prompt module"
    - "Reviewing prompt token budget"
    - "Working on system prompts"
    - "Modifying core prompt rules"
    - "Modifying mode prompt instructions"
---

## When to Use This Skill

Load this skill **before** editing any file under `agent/prompts/**/*.md`.

It answers:
1. **Where does this rule belong?** → Canonical Location Map
2. **Am I over budget?** → Token Budgets table
3. **Am I making a classic mistake?** → Anti-Patterns (AP-1 to AP-6)
4. **Is this file getting too large?** → Large File Split Guidance

Also load when:
- Reviewing prompt quality after a change
- Auditing token usage in the prompt system
- Planning a new prompt module or section

Do NOT skip this skill to "save time" — prompt degradation is cumulative and hard to reverse.

---

## Prompt Assembly Architecture

The assembly pipeline in `agent/prompts/loader.py`:

```
SECURITY_START (Python constant in loader.py)
  → core/01_security.md
  → core/02_identity.md
  → core/03_format_style.md
  → core/04_anti_patterns.md
  → core/05_tools_efficiency.md
  → core/06_escalation.md
  → core/07_pricing_rules.md
  → core/08_documentation.md
  → core/09_inline_questions.md
  → modes/{current_mode}.md
  → client_context  (injected dynamically by loader.py)
  → mode_context    (injected dynamically by loader.py)
SECURITY_END (Python constant in loader.py)
```

**Key points**:
- `SECURITY_START` and `SECURITY_END` are Python string constants in `loader.py`, NOT `.md` files
- `client_context` and `mode_context` are dynamically injected — **DO NOT** hardcode them in `.md` files
- All `.md` files are read-cached at startup; changes require agent service restart
- `loader.py:get_prompt_stats()` returns token estimates per module (use for auditing)

---

## Canonical Location Map

Each rule/instruction type has exactly ONE canonical home. Adding content to the wrong file creates duplicates and contradictions.

| Rule / Instruction Type | Canonical File | Notes |
|-------------------------|----------------|-------|
| Jailbreak / prompt-injection defence | `core/01_security.md` | NEVER add security rules elsewhere |
| Agent name, company, identity, EU AI Act | `core/02_identity.md` | Single source of truth for identity |
| Response format (lists, length, markdown, WhatsApp) | `core/03_format_style.md` | Tone and castellano formatting live here |
| Anti-patterns checklist (agent behaviours to avoid) | `core/04_anti_patterns.md` | Mode files may reference but NEVER duplicate |
| Tool call order, dedup, efficiency rules | `core/05_tools_efficiency.md` | "Llama calcular_tarifa antes de enviar_imagenes" |
| Human escalation rules and thresholds | `core/06_escalation.md` | "Escala si el cliente insiste 3 veces" |
| Pricing format, warnings algorithm, IVA rules | `core/07_pricing_rules.md` | "Precio siempre antes que imágenes" |
| Anti-hallucination rules for RAG / documents | `core/08_documentation.md` | "Cita siempre la fuente del documento" |
| Variant question format (CANONICAL) | `core/09_inline_questions.md` | This is the **single source** — ALL other files must NOT define this |
| Mode-specific flow and tool sequence | `modes/{mode}.md` | Presupuesto step-by-step flow, expediente collection logic |
| Dynamic client data (client_type, phone, history) | `loader.py` ONLY | **NEVER** hardcode in `.md` files |
| Mode transition context ("Vienes del modo...") | `loader.py` ONLY | loader injects `mode_context` — `.md` files must NOT add transition blocks |

**PROHIBITED duplications** (will cause contradictions):
- Variant question format defined in mode files → use `core/09_inline_questions.md` only
- "Si vienes de / coming from" blocks in mode `.md` files → that is `loader.py`'s job
- Pricing rules copied into mode files → `core/07_pricing_rules.md` is the source
- Security rules outside `core/01_security.md`

---

## Token Budgets

Token estimate formula: `len(file_content) // 4` (matches `loader.py:get_prompt_stats()` convention).
Budgets = current measured size + 10% headroom.

### Core Modules

| File | Token Budget | Char Budget | Current | Status |
|------|-------------|-------------|---------|--------|
| `core/01_security.md` | ≤500 | ≤2,000 | ~451 | ✅ |
| `core/02_identity.md` | ≤1,150 | ≤4,600 | ~1,031 | ✅ |
| `core/03_format_style.md` | ≤460 | ≤1,840 | ~413 | ✅ |
| `core/04_anti_patterns.md` | ≤2,460 | ≤9,840 | ~2,235 | ✅ |
| `core/05_tools_efficiency.md` | ≤700 | ≤2,800 | ~634 | ✅ |
| `core/06_escalation.md` | ≤490 | ≤1,960 | ~441 | ✅ |
| `core/07_pricing_rules.md` | ≤1,970 | ≤7,880 | ~1,787 | ✅ |
| `core/08_documentation.md` | ≤700 | ≤2,800 | ~631 | ✅ |
| `core/09_inline_questions.md` | ≤230 | ≤920 | ~209 | ✅ |
| **CORE TOTAL** | **≤8,600** | **≤34,400** | **~7,835** | **✅** |

### Mode Files

| File | Token Budget | Char Budget | Current | Status |
|------|-------------|-------------|---------|--------|
| `modes/presupuesto_mode.md` | ≤10,800 | ≤43,200 | ~9,834 | ⚠️ 91% |
| `modes/consulta_mode.md` | ≤2,150 | ≤8,600 | ~1,948 | ✅ |
| `modes/expediente_documentacion_elementos.md` | ≤3,780 | ≤15,120 | ~3,429 | ✅ |
| `modes/expediente_documentacion_base.md` | ≤1,430 | ≤5,720 | ~1,292 | ✅ |
| `modes/expediente_datos_personales.md` | ≤1,440 | ≤5,760 | ~1,302 | ✅ |
| `modes/expediente_datos_vehiculo.md` | ≤1,020 | ≤4,080 | ~918 | ✅ |
| `modes/expediente_taller.md` | ≤1,380 | ≤5,520 | ~1,245 | ✅ |
| `modes/expediente_revision.md` | ≤1,570 | ≤6,280 | ~1,425 | ✅ |
| `modes/presupuesto_mode_post_price.md` | ≤2,400 | ≤9,600 | ~2,209 | ✅ |

> ⚠️ `presupuesto_mode.md` is at 91% of its cap. See "Large File Split Guidance" below before adding anything to this file.

**Measure current size**:
```bash
python -c "print(len(open('agent/prompts/PATH').read()) // 4)"
# or use the loader:
# from agent.prompts.loader import get_prompt_stats; print(get_prompt_stats())
```

---

## Pre-Edit Checklist

**MANDATORY before any change to `agent/prompts/`**:

1. **Load this skill** — Read `skills/msia-prompts/SKILL.md` fully
2. **Locate the canonical file** — Use the Canonical Location Map above to confirm you're editing the RIGHT file
3. **Measure current tokens** — Run `python -c "print(len(open('agent/prompts/PATH').read()) // 4)"` or use `get_prompt_stats()`
4. **Check for duplicates** — Search other prompt files for the rule you're about to add:
   ```bash
   rg "your rule keyword" agent/prompts/
   ```
   If the rule exists elsewhere, DO NOT duplicate — update only the canonical file
5. **Check for stale markers** — Before submitting, grep for:
   ```bash
   rg "FIX-|INTERNAL_MARKER|T-[0-9]|version history|versión anterior" agent/prompts/
   ```
6. **Measure tokens after edit** — Confirm the file stays within its budget
7. **Run lint tests** — `pytest tests/agent/prompts/test_prompt_lint.py -v` must pass

---

## Anti-Patterns

### AP-1: Stale Markers

❌ `# FIX-1: workaround for bug`, `<!-- T-6: temporary -->`, `INTERNAL_MARKER`

**Why harmful**: These are developer notes, not LLM instructions. They consume tokens and confuse the model about what it should actually do.

**Rule**: Remove all markers before committing. Notes belong in ADRs (`docs/decisions/`) or code comments, never in `.md` prompt files.

---

### AP-2: Duplicate Rules

❌ Same variant question format defined in `presupuesto_mode.md` AND `consulta_mode.md` AND `expediente_*.md`

**Why harmful**: Creates contradictions when rules diverge across files, wastes tokens (7x in a real documented case), and requires synchronised updates across every file.

**Rule**: One canonical file per rule type. All others reference or omit — never duplicate.

---

### AP-3: Transition Blocks in Mode Files

❌ `## Si vienes de una transición\nRecuerda el contexto previo...` in mode `.md` files

**Why harmful**: `loader.py` already injects `mode_context` dynamically. The `.md` block is always overridden and just wastes tokens.

**Rule**: Never add "Si vienes de / coming from" sections in mode `.md` files. That logic lives in `loader.py`.

---

### AP-4: Version History / Migration Notes

❌ `## Diferencias clave vs versión anterior\n- Se eliminó el campo X...`

**Why harmful**: Migration notes are for developers, not the LLM. They're outdated within one sprint and cost real tokens per turn.

**Rule**: Delete version history sections. Architectural decisions go in `docs/decisions/` (ADRs).

---

### AP-5: Emphasis Bloat

❌ 71 instances of `NUNCA`/`CRITICAL`/`PROHIBIDO`/🚨 across prompt files

**Why harmful**: Emphasis loses meaning when overused. LLM attention is diluted when every sentence is "critical".

**Rule**: Max 5 `NUNCA`/`CRITICAL` per file. Use sparingly for truly critical behaviours only.

---

### AP-6: Unbounded Growth

❌ `presupuesto_mode.md` growing from ~20 KB to ~43 KB over 6 months

**Why harmful**: Per-turn token cost compounds. At 18,600 tokens/turn × thousands of turns = significant cumulative cost.

**Rule**: Check token budget after every edit. If a file exceeds 80% of its cap, evaluate splitting before adding more content.

---

## Large File Split Guidance

If a mode file exceeds 80% of its token cap (8,640 tokens / 34,560 chars for modes), consider splitting:

**Steps**:

1. **Identify functional sections** in the file (e.g., `presupuesto_mode.md` has: step-by-step flow, pricing algorithm, image rules, FAQ examples)

2. **Name split files** as `{mode}_{section}.md` (e.g., `presupuesto_mode_pricing.md`)

3. **Update `loader.py`** to conditionally load split files based on sub-state:
   ```python
   # In loader.py — conditional mode file loading
   if mode == "PRESUPUESTO_MODE":
       parts = ["presupuesto_mode_core.md"]
       if context.get("showing_pricing"):
           parts.append("presupuesto_mode_pricing.md")
   ```

4. **Never split** core modules — they are always loaded together

**Current candidate**: `presupuesto_mode.md` at 91% cap (~9,834 tokens). Recommended next split point: when it exceeds 10,000 tokens.

---

## Critical Rules

1. ✅ ALWAYS load `msia-prompts` skill before editing any file in `agent/prompts/`
2. ✅ ALWAYS check Canonical Location Map before adding a rule
3. ✅ ALWAYS measure tokens before AND after your edit
4. ✅ ALWAYS run `test_prompt_lint.py` after edits
5. ✅ ALWAYS remove stale markers before submitting
6. ❌ NEVER duplicate rules across files — one canonical location per rule type
7. ❌ NEVER add client/context data to `.md` files — that is `loader.py`'s job
8. ❌ NEVER add transition blocks ("Si vienes de...") to mode `.md` files
9. ❌ NEVER add version history or migration notes to `.md` files
10. ❌ NEVER commit if `test_prompt_lint.py` fails

---

## Resources

- **Prompt files**: `agent/prompts/` (`core/` + `modes/`)
- **Assembly logic**: `agent/prompts/loader.py`
- **Lint tests**: `tests/agent/prompts/test_prompt_lint.py`
- **Token stats**: `loader.py:get_prompt_stats()`
- **Architecture**: `agent/AGENTS.md` → Prompt System section
- **Related skill**: [`msia-agent`](../msia-agent/SKILL.md) — agent architecture, tools, modes, state
- **ADRs**: `docs/decisions/` — especially `002-dynamic-prompts.md`
