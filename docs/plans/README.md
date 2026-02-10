# Implementation Plans

This directory contains implementation plans for features, refactors, and system improvements.

> **Note**: The original detailed migration plan has been preserved as [OLD-README.md](OLD-README.md)

---

## 📁 Structure

```
plans/
├── active/       # Plans currently in progress
├── completed/    # Archived completed plans
└── OLD-README.md # Original v1→v2 migration master plan (detailed)
```

---

## 🎯 Active Plans

| Plan | Status | Started | Priority |
|------|--------|---------|----------|
| [migracion-v1-v2-bigbang.md](active/migracion-v1-v2-bigbang.md) | ⏳ In Progress | 2026-02 | HIGH |

### Active Plan Details

**Migration v1 → v2 (Big Bang)**

- **Status**: 33% complete (Phases 1-2 done)
- **Strategy**: Eliminate FSM v1.0 completely, replace with mode-based v2.0
- **Progress**:
  - [x] Phase 1: Foundation (State, Router, Fallback, Digression Manager)
  - [x] Phase 2: VIABILIDAD_MODE (65% traffic)
  - [ ] Phase 3: CONSULTA_MODE (10% traffic)
  - [ ] Phase 4: PRESUPUESTO_MODE + EVALUACION_GATEWAY
  - [ ] Phase 5: EXPEDIENTE_MODE (complete redesign)
  - [ ] Phase 6: Big Bang (eliminate v1, deploy v2)

---

## ✅ Completed Plans

### Major Features

| Plan | Completed | Summary |
|------|-----------|---------|
| [fase-1-foundation.md](completed/fase-1-foundation.md) | 2026-02-08 | Foundation: State, Router, Fallback, Digression Manager |
| [fase-2-viabilidad-mode.md](completed/fase-2-viabilidad-mode.md) | 2026-02-08 | VIABILIDAD_MODE implementation (65% traffic) |
| [defensive-parameter-validation-system.md](completed/defensive-parameter-validation-system.md) | 2026-02-08 | 3-phase defensive validation system |
| [phase3-error-recovery-design.md](completed/phase3-error-recovery-design.md) | 2026-02-08 | Error recovery and retry patterns |
| [fusion-viabilidad-presupuesto.md](completed/fusion-viabilidad-presupuesto.md) | 2026-02-08 | Merged viabilidad and presupuesto flows |

### Bug Fix Plans

| Plan | Completed | Bug Fixed |
|------|-----------|-----------|
| [fix-tool-flags-bug.md](completed/fix-tool-flags-bug.md) | 2026-02-06 | Tool flags STRING parsing (CRITICAL) |
| [fix-image-sending-system.md](completed/fix-image-sending-system.md) | 2026-02-07 | Image URL normalization |
| [fix-conversation-context-loss.md](completed/fix-conversation-context-loss.md) | 2026-02-08 | Context loss between messages |
| [fix-precio-comunicado-full-state-pattern.md](completed/fix-precio-comunicado-full-state-pattern.md) | 2026-02-08 | precio_comunicado flag pattern |
| [fix-presupuesto-option-a-bug.md](completed/fix-presupuesto-option-a-bug.md) | 2026-02-08 | Presupuesto option A edge case |
| [fix-variant-keywords-empty.md](completed/fix-variant-keywords-empty.md) | 2026-02-08 | Empty variant keywords handling |
| [fix-mode-context-opcion1-implementation.md](completed/fix-mode-context-opcion1-implementation.md) | 2026-02-08 | Mode context preservation |
| [fix-mode-context-opcion3.md](completed/fix-mode-context-opcion3.md) | 2026-02-08 | Alternative mode context approach |

### Phase Completions

| Plan | Completed | Phase |
|------|-----------|-------|
| [FASE1-COMPLETADA.md](completed/FASE1-COMPLETADA.md) | 2026-02-08 | Phase 1 completion summary |
| [FASE-5-IMPLEMENTADA.md](completed/FASE-5-IMPLEMENTADA.md) | 2026-02-08 | Phase 5 implementation complete |

---

## 📝 Plan Structure

A good implementation plan includes:

### 1. Overview
- **Problem**: What are we solving?
- **Solution**: High-level approach
- **Impact**: What will change?

### 2. Requirements
- Functional requirements
- Non-functional requirements (performance, security, etc.)
- Constraints

### 3. Architecture
- Component diagram
- Data flow
- Integration points

### 4. Implementation
- Phases/milestones
- File changes
- Database migrations (if any)

### 5. Testing
- Unit test coverage
- Integration test scenarios
- E2E test flows
- Performance/load testing (if needed)

### 6. Deployment
- Pre-deployment checklist
- Deployment steps
- Rollback plan
- Monitoring/alerts

### 7. Acceptance Criteria
- How do we know it's done?
- Success metrics

---

## 🚀 Plan Lifecycle

```
Proposed → Approved → In Progress → Implemented → Tested → Deployed → Completed
                                                                          ↓
                                                                      Archived
```

### Status Definitions

| Status | Meaning |
|--------|---------|
| **Proposed** | Plan drafted, awaiting review |
| **Approved** | Plan approved, ready to implement |
| **In Progress** | Currently being implemented |
| **Implemented** | Code complete, awaiting testing |
| **Tested** | Tests pass, awaiting deployment |
| **Deployed** | In production, monitoring |
| **Completed** | Done, archived |
| **Blocked** | Cannot proceed (dependency/issue) |
| **Cancelled** | No longer needed |

---

## 📊 Statistics

### By Status

| Status | Count |
|--------|-------|
| In Progress | 1 |
| Completed | 15 |
| **Total** | 16 |

### By Type

| Type | Count |
|------|-------|
| Feature | 5 |
| Refactor | 3 |
| Bug Fix | 8 |

---

## 🔗 Related Documentation

- **Architecture**: `docs/architecture/` - System architecture context
- **Decisions**: `docs/decisions/` - ADRs for architectural decisions
- **Deployment**: `docs/deployment/` - Deployment history
- **Bugs**: `docs/bugs/` - Bug fixes documentation

---

## 💡 Creating a New Plan

1. **Copy template** from `docs/decisions/template.md` (similar structure)
2. **Name file**: `[type]-[short-description].md`
   - Types: `feat`, `fix`, `refactor`, `perf`, `docs`
   - Example: `feat-document-templates.md`
3. **Write plan** following structure above
4. **Get approval** before moving to `active/`
5. **Move to completed/** when done

---

**Last Updated**: February 2026  
**Total Plans**: 16 (1 active, 15 completed)
