# Bug Fixes Documentation

This directory tracks bug fixes with root cause analysis and solutions.

---

## 📁 Structure

```
bugs/
├── fixed/    # Resolved bugs with complete documentation
└── active/   # Bugs currently under investigation
```

---

## 🐛 Fixed Bugs

### Critical Bugs (Severity: 🔴)

| # | Title | Date Fixed | Root Cause | Files |
|---|-------|------------|------------|-------|
| 001 | Tool Flags STRING Parsing | 2026-02-06 | LangGraph converted list flags to JSON strings | [001-tool-flags-parsing.md](fixed/001-tool-flags-parsing.md) |
| 002 | Image URLs Not Sending | 2026-02-06 | URL normalization missing for Chatwoot storage domain | [002-image-urls.md](fixed/002-image-urls.md) |
| 004 | Expediente Created Without Tariff | 2026-02-07 | No defensive fallback when tariff missing in state | [004-expediente-tariff-fallback.md](fixed/004-expediente-tariff-fallback.md) |

### Feature Enhancements (Severity: 🟡)

| # | Title | Date Fixed | What Changed | Files |
|---|-------|------------|--------------|-------|
| 003 | Image Captions Missing | 2026-02-07 | Added context captions to WhatsApp images | [003-image-captions.md](fixed/003-image-captions.md) |

---

## 🔍 Bug Fix Details

### 001: Tool Flags STRING Parsing

**Severity**: 🔴 CRITICAL

**Impact**: Tool-driven state management completely broken. Flags like `precio_comunicado`, `imagenes_enviadas` were strings `"True"` instead of booleans.

**Root Cause**: LangGraph serialization converted lists/dicts in tool returns to JSON strings.

**Solution**: 
- Parser to extract flags from string
- Type coercion to boolean
- Defensive checks for both formats

**Related**:
- ADR: `docs/decisions/005-tool-driven-state-management.md`
- Coding Standard: `docs/coding-standards/03-agent-architecture.md` (Tool Return Pattern)

---

### 002: Image URLs Not Sending

**Severity**: 🔴 HIGH

**Impact**: Example images feature completely broken. Images not displayed in WhatsApp.

**Root Cause**: Chatwoot uses storage domain `storage.chatwoot.com` for attachments, but validation only allowed `app.chatwoot.com`.

**Solution**:
- URL normalization in `ChatwootClient.send_images()`
- Support for both `app.chatwoot.com` and `storage.chatwoot.com` domains
- SSRF validation updated

**Related**:
- Security: `docs/coding-standards/05-security.md` (SSRF Prevention)
- Shared Utility: `shared/chatwoot_client.py`

---

### 003: Image Captions Missing

**Severity**: 🟡 MEDIUM (Feature gap, not bug)

**Impact**: Images sent without context. User didn't know what they were looking at.

**Root Cause**: WhatsApp API supports captions, but we weren't using them.

**Solution**:
- Added `caption` parameter to `ChatwootClient.send_images()`
- Agent now sends captions like "Foto de ejemplo: Suspensión delantera homologada"

**Related**:
- Tool Pattern: `agent/tools/image_tools.py`
- Chatwoot Client: `shared/chatwoot_client.py`

---

### 004: Expediente Created Without Tariff

**Severity**: 🔴 HIGH

**Impact**: Cases created with `precio_total=0` when user skipped presupuesto step or state lost tariff data.

**Root Cause**: No defensive fallback. Tool `crear_expediente_y_escalar()` assumed tariff always exists in state.

**Solution**:
- Defensive fallback: Calculate tariff on-the-fly if missing
- Warning logged when fallback triggered
- User sees correct price even if state inconsistent

**Related**:
- Tool: `agent/tools/case_tools.py`
- Service: `agent/services/tarifa_service.py`
- Standard: `docs/coding-standards/03-agent-architecture.md` (Defensive Programming)

---

## 🔄 Bug Lifecycle

```
Reported → Triaged → Root Cause Analysis → Fixed → Tested → Deployed → Documented
```

### Documentation Template

When documenting a fixed bug, include:

1. **Title**: Clear, descriptive
2. **Severity**: 🔴 Critical | 🟡 High | 🟢 Medium | ⚪ Low
3. **Date Fixed**: When deployed
4. **Status**: Fixed | Deployed | Verified
5. **Impact**: What broke, who was affected
6. **Root Cause**: Technical explanation
7. **Solution**: What changed
8. **Verification**: How to test it's fixed
9. **Related**: Links to ADRs, standards, code files

---

## 📊 Bug Statistics

### By Severity (All Time)

| Severity | Count | % |
|----------|-------|---|
| 🔴 Critical | 3 | 75% |
| 🟡 Feature | 1 | 25% |
| **Total** | 4 | 100% |

### By Category

| Category | Count |
|----------|-------|
| Tool execution | 2 |
| Data validation | 1 |
| External API | 1 |
| Feature gap | 1 |

---

## 🔗 Related Documentation

- **Coding Standards**: `docs/coding-standards/` - Patterns to prevent bugs
- **Testing**: `docs/testing/` - Test coverage to catch bugs
- **Deployment**: `docs/deployment/` - When bugs were fixed
- **Sessions**: `docs/sessions/` - Session notes during bug fixing

---

**Last Updated**: February 2026  
**Total Bugs Fixed**: 4
