# Architecture Documentation

This directory contains all architectural documentation for MSI-a.

---

## 📁 Structure

```
architecture/
├── current/           # v2.0 Mode-based Architecture (ACTIVE)
│   ├── diagrams/      # Mermaid diagrams + exports
│   └── modes/         # Mode-specific documentation
└── legacy/            # Historical architectures (ARCHIVE)
```

---

## 🎯 Current Architecture (v2.0)

MSI-a uses a **mode-based conversation architecture** with LangGraph.

### Core Documents

| File | Purpose | Status |
|------|---------|--------|
| [00-overview.md](current/00-overview.md) | Complete system overview | ✅ Active |
| [01-philosophy.md](current/01-philosophy.md) | Design philosophy & principles | ✅ Active |
| [02-modes-overview.md](current/02-modes-overview.md) | All conversation modes explained | ✅ Active |
| [03-transitions.md](current/03-transitions.md) | Mode transitions & routing | ✅ Active |
| [04-fallback.md](current/04-fallback.md) | Fallback & error recovery | ✅ Active |
| [05-gaps-solutions.md](current/05-gaps-solutions.md) | Solutions to v1 gaps | ✅ Active |

### Mode-Specific Documentation

| Mode | Traffic | File |
|------|---------|------|
| CONSULTA_MODE | ~10% | [modes/consulta.md](current/modes/consulta.md) |
| VIABILIDAD_MODE | ~65% | [modes/viabilidad.md](current/modes/viabilidad.md) |
| PRESUPUESTO_MODE | ~25% | [modes/presupuesto.md](current/modes/presupuesto.md) |

### Diagrams

- [diagrams/diagrama-principal.mmd](current/diagrams/diagrama-principal.mmd) - Main agent flow
- [diagrams/diagrama-decisiones.mmd](current/diagrams/diagrama-decisiones.mmd) - Decision tree
- [diagrams/arquitectura-agente.pdf](current/diagrams/arquitectura-agente.pdf) - Complete diagram (PDF export)

---

## 🕰️ Legacy Architecture (v1.0)

MSI-a originally used an **FSM (Finite State Machine)** linear architecture.

| File | Content |
|------|---------|
| [legacy/fsm-v1-archive.md](legacy/fsm-v1-archive.md) | Consolidated FSM v1.0 documentation |

**Why it was replaced**: See [05-gaps-solutions.md](current/05-gaps-solutions.md) for critical gaps that led to v2.0 redesign.

**Full archive**: Original files preserved in `docs/archive/arquitectura-conversacion/`

---

## 🔄 Migration History

The migration from v1.0 (FSM) to v2.0 (Modes) was documented in:
- **Migration Plan**: `docs/plans/completed/migracion-v1-v2-bigbang.md`
- **Implementation Phases**: `docs/deployment/2026-02-08-phase*.md`
- **Decisions**: `docs/decisions/005-tool-driven-state-management.md`

---

## 🎓 Key Concepts

### Modes vs States

| v1.0 (States/FSM) | v2.0 (Modes) |
|-------------------|--------------|
| Linear flow only | Non-linear, intent-based |
| States know each other | Modes are independent |
| FSM-aware prompts | Mode-specific prompts |
| Hard transitions | Soft routing via intent |

### Mode Types

1. **Informational** (CONSULTA_MODE): Answer questions, no state change
2. **Transactional** (VIABILIDAD, PRESUPUESTO): Collect data, calculate, provide output
3. **Workflow** (EXPEDIENTE_MODE): Multi-step process with sub-modes
4. **Gateway** (EVALUACION_GATEWAY): Yes/no decision points

---

## 📊 Architecture Diagrams

### High-Level Flow (v2.0)

```
WhatsApp → Chatwoot → API Webhook → Redis Streams → Agent
                                                        ↓
                                              Intent Router
                                    (Keyword + LLM classification)
                                                        ↓
                                              ┌─────────┴─────────┐
                                              ↓                   ↓
                                        CONSULTA_MODE      VIABILIDAD_MODE
                                                                  ↓
                                                          PRESUPUESTO_MODE
                                                                  ↓
                                                        EVALUACION_GATEWAY
                                                                  ↓
                                                         EXPEDIENTE_MODE
                                                                  ↓
                                                          (Escalation)
```

### Tool Execution Pattern

```
Mode Node → Select Tools → LLM Invocation → Tool Calls → Update Context
    ↑                                                            ↓
    └────────────────── Iterate (max 10) ─────────────────────────┘
                                ↓
                          Extract Updates
                                ↓
                        Return to StateGraph
```

---

## 🔗 Related Documentation

- **Coding Standards**: `docs/coding-standards/03-agent-architecture.md`
- **ADRs**: `docs/decisions/` (especially ADR-005)
- **Implementation Plans**: `docs/plans/completed/fase-*.md`
- **Skills**: `skills/msia-agent/SKILL.md`, `skills/langgraph/SKILL.md`

---

**Last Updated**: February 2026  
**Architecture Version**: 2.0 (Mode-based)
