---
name: context-optimization
description: >
  Strategies to reduce AI context usage and token costs.
  Trigger: Long sessions, large codebases, context limit warnings.
metadata:
  author: msi-automotive
  version: "1.0"
  scope: [root]
  auto_invoke: "Context optimization or long sessions"
  priority: high
---

## Overview

Context optimization strategies for efficient AI-assisted development in MSI-a. Reduces token usage, improves response quality, and enables longer productive sessions.

## Why Context Matters

| Context Size | Effect |
|--------------|--------|
| < 50% | Optimal - fast, accurate responses |
| 50-75% | Good - may need occasional refresh |
| 75-90% | Warning - consider compacting |
| > 90% | Critical - responses degrade, risk of losing context |

## Optimization Strategies

### 1. Use Specialized Agents

Delegate tasks to focused agents that don't inherit full context:

```
# Instead of doing everything in main session:
/code-review api/routes/tariffs.py    # Delegated review
/security-review agent/nodes/          # Focused security audit
/build-fix                             # Isolated error fixing
```

Benefits:
- Agent gets clean context
- Main session stays lean
- Results summarized back

### 2. Compact Aggressively

When context grows, compact frequently:

```
# OpenCode compaction
# Preserves: recent messages, todos, file locations
# Removes: old code snippets, verbose tool outputs
```

Best times to compact:
- After completing a major task
- Before starting new feature
- When responses slow down
- After long exploration

### 3. Skill-Based Loading

Load skills on-demand, not all at once:

```
# BAD - Loading everything
"Read all skills before starting"

# GOOD - Load what's needed
"I'm working on tariffs"  # → msia-tariffs skill loaded
"Now fixing types"        # → coding-standards loaded
```

### 4. Efficient File Operations

```python
# BAD - Reading entire files
Read the whole api/services/tariff_service.py (500 lines)

# GOOD - Targeted reading
Read api/services/tariff_service.py lines 45-80  # Just the function

# BAD - Multiple small reads
Read file1.py
Read file2.py  
Read file3.py

# GOOD - Batch reads
Read file1.py, file2.py, file3.py in parallel
```

### 5. Search Before Read

```python
# BAD - Reading to find something
Read the entire codebase to find where tariffs are calculated

# GOOD - Search first
Grep for "calculate.*tariff" → find exact location → read only that
```

### 6. Summarize, Don't Repeat

```python
# BAD - Pasting full error output multiple times
"Here's the error again: [500 lines of stack trace]"

# GOOD - Reference and summarize
"The error on line 45 (Type mismatch) still occurs"
```

### 7. Session Context File

For long sessions, maintain `.session-context.md`:

```markdown
# Session Context

## Active Task
Implementing tariff calculation with tiers

## Key Files
- api/services/tariff_service.py:45-120
- agent/tools/tariff_tools.py:calculate_tarifa

## Decisions Made
- Using tiered pricing with breakpoints
- Caching in Redis for 5 minutes

## Recent Changes
- Added TierCalculator class
- Updated tests for edge cases
```

Benefits:
- Quick context restoration after compaction
- Reference instead of re-explaining
- Clear task focus

### 8. Model Selection

Use appropriate models for task complexity:

| Task | Model | Context |
|------|-------|---------|
| Simple edits | Haiku | Minimal |
| Code review | Sonnet | Moderate |
| Architecture | Sonnet | As needed |
| Quick questions | Haiku | Minimal |

### 9. Structured Requests

```python
# BAD - Vague request requiring exploration
"Fix the bug in the tariff system"

# GOOD - Specific with context
"Fix TypeError in api/services/tariff_service.py:67
 - calculate_total receives None instead of Decimal
 - Happens when elements list is empty
 - Should return 0 for empty list"
```

### 10. Clean Intermediate State

After exploration phases:
1. Note what you found
2. Compact context
3. Continue with findings

```
# After exploration
"Found the issue in 3 files:
- api/routes/tariffs.py:45 - missing validation
- api/services/tariff.py:89 - wrong calculation  
- agent/tools/tariff.py:23 - outdated schema

Let me compact and fix these."
```

## Context Budget Guidelines

| Session Phase | Budget |
|---------------|--------|
| Initial exploration | 20% |
| Planning | 10% |
| Implementation | 50% |
| Review & testing | 15% |
| Documentation | 5% |

## Warning Signs

Watch for these indicators of context bloat:

1. **Slow responses** - AI taking longer to respond
2. **Forgotten context** - AI asking about things discussed earlier
3. **Repetitive questions** - Clarifications already answered
4. **Degraded quality** - Less accurate suggestions

## Recovery Steps

When context is bloated:

1. Complete current atomic task
2. Save important state to session context
3. Compact/clear context
4. Reload minimal necessary context
5. Continue with fresh state

## Metrics

Track these to optimize:
- Messages per task completion
- Compactions per session
- Files read vs actually used
- Agent delegations vs inline work

## Related Skills

- `msia` - Project overview for quick re-orientation
- All specialized skills - For delegation targets
