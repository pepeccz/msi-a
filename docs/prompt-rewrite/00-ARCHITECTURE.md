# System Prompt Rewrite — Architecture Design

## Goals

1. **LLM compliance**: Instructions followed >90% (currently ~30-70% for complex rules)
2. **Token efficiency**: ~5,500-6,500 total (down from ~9,500)
3. **Scalability**: New modes/tools added without restructuring
4. **Tool alignment**: Prompts grounded in what tools actually do
5. **No competing instructions**: Tool results complement, never override

## Architecture: What Changes

### Before (current)

```
[SECURITY_START delimiter]                    ~70 tokens
[10 core modules concatenated with ---]       ~6,066 tokens
  01_security.md
  02_identity.md
  03_format_style.md
  04_anti_patterns.md      ← rules far from tools
  05_tools_efficiency.md   ← rules far from tools
  06_escalation.md
  07_pricing_rules.md      ← rules far from tools
  08_documentation.md
  09_inline_questions.md
  10_expediente_universal.md
[1 mode module]                               ~500-2,300 tokens
[client context]                              ~0-200 tokens
[mode context]                                ~200-500 tokens
[SECURITY_END delimiter]                      ~130 tokens
                                              ─────────────────
                                              ~8,600-10,400 tokens
```

**Problems**: Flat structure, rules separated from tools, security bookend wastes tokens, redundancy between core and mode modules, no semantic sections.

### After (new)

```
<system>                                      ~800 tokens
  <identity/>           — Who, limits
  <execution_model/>    — WhatsApp loop, 1 turn = read → tool → respond
  <security/>           — Anti-jailbreak (condensed)
  <principles/>         — Grounded not agreeable, data hierarchy, tool-first
  <format/>             — Tone, WhatsApp, language
</system>

<mode>                                        ~800-1,500 tokens
  Phase-specific instructions with:
  - Tool rules CO-LOCATED with usage context
  - CTA table (prescriptive)
  - Edge cases (table format, not prose)
</mode>

<context>                                     ~200-500 tokens
  Dynamic state (same as current format_mode_context)
</context>
                                              ─────────────────
                                              ~1,800-2,800 tokens
```

**Target**: 60-70% token reduction. Rules next to where they're used.

## Key Design Decisions

### D1: Single core file with semantic XML tags

Instead of 10 numbered .md files, one `core.md` with `<identity>`, `<security>`, `<principles>`, `<format>`, `<execution_model>` sections. The LLM gets a parse tree, not a flat stream.

**Why**: GPT-5 and Cursor prove that co-located, tagged sections get higher compliance than numbered file concatenation.

### D2: Mode files carry their own tool rules

Instead of `04_anti_patterns.md` (generic) + `05_tools_efficiency.md` (generic) + mode-specific instructions, each mode file includes:
- What tools are available
- How to use each tool (params, expected return)
- What NOT to do with each tool
- Examples with reasoning

**Why**: When the LLM reads the tool result, the rules about that tool are in the SAME section it just processed — not 4,000 tokens ago.

### D3: Table format for edge cases

Instead of prose paragraphs, use tables:
```
| User says | Action | Tools | CTA |
```

**Why**: Tables compress information and are parsed by LLMs more reliably than multi-paragraph prose. Meta AI WhatsApp achieves excellent compliance with 530 tokens because every instruction is a single directive.

### D4: Tool results become minimal

Current tool results include:
- Full documentation arrays (700-1,700 tokens)
- Embedded instructions that COMPETE with system prompt

New approach:
- Tool results return data only, no embedded instructions
- `instrucciones` field removed from tool returns
- Documentation pre-filtered (only NEW elements, not already-shown docs)

**Why**: The root cause of non-compliance is tool results overriding system prompt instructions. Remove the competition.

### D5: No security bookend

Remove `SECURITY_END` delimiter. Security rules in `<security>` section are sufficient. The bookend adds ~130 tokens between dynamic context and user message — exactly where recency bias matters most.

**Why**: None of the top system prompts (GPT-5, Cursor, Manus, Windsurf) use security bookends.

### D6: Execution model section

Add explicit:
```
You operate in a WhatsApp conversation. Each turn:
1. Read the user's message
2. Optionally call 1+ tools
3. Generate ONE response (2-3 sentences max)
The user may take minutes or hours to reply. Each response is a complete turn.
```

**Why**: Manus's `<agent_loop>` has the highest tool-calling compliance of any studied prompt.

### D7: Expediente universal rules merged into mode files

`10_expediente_universal.md` gets split: common rules go into `<system><principles>`, phase-specific rules go into each expediente mode file.

**Why**: Reduces token count and puts rules where they're used.

## File Structure

```
agent/prompts/
├── core.md                              — <system> block (replaces 01-10)
├── modes/
│   ├── pre_expediente_discovery.md      — Phase 1: info + identification
│   ├── pre_expediente_pricing.md        — Phase 2: tariff + price
│   ├── pre_expediente_post_price.md     — Phase 3: images + expediente offer
│   ├── expediente_elements.md           — Element photos + data collection
│   ├── expediente_base_docs.md          — Vehicle documentation
│   ├── expediente_personal.md           — Personal data
│   ├── expediente_vehicle.md            — Vehicle data
│   ├── expediente_workshop.md           — Workshop/certification
│   ├── expediente_review.md             — Final review + confirmation
│   └── session_recovery.md              — Orphaned case recovery
└── loader.py                            — Modified assembly pipeline
```

## Token Budget

| Section | Current | New | Savings |
|---------|---------|-----|---------|
| Core (identity+security+format+principles) | ~6,066 | ~800 | -87% |
| Mode module (avg) | ~1,500 | ~1,000 | -33% |
| Dynamic context | ~400 | ~400 | 0% |
| Security bookend | ~130 | 0 | -100% |
| **TOTAL** | **~8,100** | **~2,200** | **-73%** |

## Migration Plan

### Phase A: Write new prompt files (in docs/prompt-rewrite/)
- Write core.md
- Write all 9 mode files
- Write loader changes spec

### Phase B: Modify tool results (code changes)
- Remove `instrucciones` field from tool returns
- Filter `documentacion_base` when already shown
- Filter `documentacion` to only new elements when adding

### Phase C: Update loader.py
- New assembly: `<system>` + `<mode>` + `<context>`
- Remove security bookend
- Update _resolve_mode_key for new file names

### Phase D: Test + deploy
- Test with same conversation scenarios that failed before
- Compare compliance
- Deploy

## What This Document Does NOT Change

- Tool implementations (params, returns, state effects) — stay the same
- State machine (modes, transitions) — stay the same
- Dynamic context injection (format_mode_context) — mostly same, minor tweaks
- LangGraph graph structure — untouched
- Post-tool hooks — untouched
