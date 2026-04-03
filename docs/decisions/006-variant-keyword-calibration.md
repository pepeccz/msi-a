# ADR-006: Variant Keyword Calibration

## Status
Accepted

## Context

**Bug root cause (TOLDO session 2026-04-03)**:
`qwen2.5:3b` (Tier 1 LLM) receives ambiguous inputs like `"sí"` as the user's variant selection response. Because the keyword scoring (`best_score`) returns 0.0 for `"sí"` (no keyword in the TOLDO variants matches), the code falls into the LLM interpretation path. `qwen2.5:3b` then hallucinates `"a"` as the allocation code with `confidence=0.95`, and the bare-letter guard did not exist in earlier versions.

Even after the bare-letter confidence gate (REQ-3) was added, there was a window of ambiguity: for non-bare-letter allocations, the LLM could still hallucinate a valid-looking code. Additionally, a number of seed keywords (`"si"` standalone) acted as triggers that caused keyword matching to return inflated scores for unambiguous yes/no inputs.

**The pattern repeats** across multiple elements where one variant means "yes" and another means "no":
- `TOLDO_GALIBO` / `TOLDO_LAT`: `"sí"` assigned to first variant
- `BOLA_CON_MMR`: had `"si"` as a keyword
- `CAMBIO_CLASIF_CON` (aseicars-part and aseicars-prof): had `"si"` as a keyword

## Decision

**Two-layer fix** (defense in depth):

### Layer 1: Seed keyword cleanup
Remove `"si"` as a standalone keyword from elements where it is ambiguous. Preserve compound forms like `"si aumenta"`, `"si afecta"`, `"si tienes"` since these carry semantic specificity.

Affected elements:
- `aseicars_part.py`: `BOLA_CON_MMR`, `CAMBIO_CLASIF_CON`
- `aseicars_prof.py`: `BOLA_CON_MMR`, `CAMBIO_CLASIF_CON`

### Layer 2: Early ambiguity exit (Phase 4)
Add `AMBIGUITY_THRESHOLD = 0.3` in `agent/tools/element_tools.py`.

Add helper `_has_domain_vocabulary_from_variants(user_input, variant_options)` that dynamically checks whether the user's input contains vocabulary specific to the available variants (keywords or name words > 3 chars, accent-insensitive).

Add early exit block in `seleccionar_variante_por_respuesta` **before** calling `interpret_variant_allocations` (Tier 1 LLM):

```python
if (
    not is_multi_unit
    and best_score < AMBIGUITY_THRESHOLD
    and not _has_domain_vocabulary_from_variants(respuesta_usuario, variants)
):
    return {
        "needs_clarification": True,
        "clarification_reason": "La respuesta no contiene vocabulario específico de la variante.",
        ...
    }
```

This ensures that for single-unit requests with ambiguous input, the main LLM (Tier 3, deepseek-chat) handles the clarification question instead of Tier 1 hallucinating a selection.

## Elements with variant ambiguity risk

| Element                   | Keywords at risk | Data file        | Status               |
|---------------------------|-----------------|------------------|----------------------|
| TOLDO_GALIBO / TOLDO_LAT  | "si", "no"      | motos_part.py    | Fixed (2026-04-03)   |
| BOLA_CON_MMR              | "si"            | aseicars_part.py | Fixed (Phase 4)      |
| BOLA_CON_MMR              | "si"            | aseicars_prof.py | Fixed (Phase 4)      |
| CAMBIO_CLASIF_CON         | "si"            | aseicars_part.py | Fixed (Phase 4)      |
| CAMBIO_CLASIF_CON         | "si"            | aseicars_prof.py | Fixed (Phase 4)      |

## Consequences

**Positive:**
- `"sí"` as a bare response to a variant question now triggers a clarifying question from the main LLM instead of a silent wrong selection
- The pattern is generalizable: any element whose variants don't contain specific domain vocabulary in their names/keywords will benefit
- Multi-unit requests are exempt (they need LLM to distribute quantities)
- Compound keywords like `"si aumenta"` are preserved (they carry intent)

**Negative:**
- For users who respond with the exact correct variant name or a strong keyword match (score ≥ 0.3), behavior is unchanged
- Elements with very short/generic keywords may now require an extra clarification turn (acceptable UX trade-off vs. silent wrong selection)

## SQL para producción

After re-running seeds, the DB will be updated automatically. If re-seeding is not possible, run:

```sql
-- BOLA_CON_MMR: remove standalone "si" from keywords
UPDATE elements
SET keywords = (
  SELECT jsonb_agg(k)
  FROM jsonb_array_elements(keywords) AS k
  WHERE k::text != '"si"'
)
WHERE code = 'BOLA_CON_MMR';

-- CAMBIO_CLASIF_CON: remove standalone "si" from keywords
UPDATE elements
SET keywords = (
  SELECT jsonb_agg(k)
  FROM jsonb_array_elements(keywords) AS k
  WHERE k::text != '"si"'
)
WHERE code = 'CAMBIO_CLASIF_CON';
```

## Related

- [ADR-005: Tool-driven state management](005-tool-driven-state-management.md)
- `agent/tools/element_tools.py` — `AMBIGUITY_THRESHOLD`, `_has_domain_vocabulary_from_variants`, early exit block (~line 1250)
- `tests/unit/test_early_ambiguity_exit_phase4.py` — 10 tests covering this change
- `tests/unit/test_variant_confidence_gate.py` — 4 tests covering bare-letter gate (REQ-3)
