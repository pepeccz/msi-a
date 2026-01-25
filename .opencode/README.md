# OpenCode AI Development System

Enhanced AI-assisted development for MSI-a, inspired by [everything-claude-code](https://github.com/anthropics/everything-claude-code).

## Overview

This system provides specialized agents, commands, and skills to improve AI-assisted development:

- **Agents**: Focused AI assistants for specific tasks
- **Commands**: Quick access to common workflows
- **Skills**: Domain knowledge and coding patterns
- **Scripts**: Automation hooks (formatting, session logging)

## Quick Start

### Commands

```bash
/plan <feature>          # Plan before coding
/tdd <function>          # Test-driven development
/code-review <file>      # Quality review
/security-review <file>  # Security audit
/architecture <question> # Design guidance
/build-fix               # Fix build errors
/doc-update              # Sync documentation
/refactor-clean          # Remove dead code
```

### Example Workflow

```bash
# 1. Plan the feature
/plan Add email notifications for new cases

# 2. Implement with TDD
/tdd send_notification function

# 3. Review before commit
/code-review api/services/notification.py
/security-review api/services/notification.py

# 4. Update documentation
/doc-update
```

## Directory Structure

```
.opencode/
├── README.md           # This file
├── agents/             # Specialized AI agents
│   ├── planner.md
│   ├── code-reviewer.md
│   ├── tdd-guide.md
│   ├── security-reviewer.md
│   ├── architect.md
│   ├── build-error-resolver.md
│   ├── doc-updater.md
│   └── refactor-cleaner.md
├── commands/           # Slash commands
│   ├── plan.md
│   ├── tdd.md
│   ├── code-review.md
│   ├── security-review.md
│   ├── architecture.md
│   ├── build-fix.md
│   ├── doc-update.md
│   └── refactor-clean.md
├── skills/             # Domain knowledge
│   ├── coding-standards/
│   ├── python-backend-patterns/
│   ├── typescript-frontend-patterns/
│   ├── tdd-workflow/
│   ├── security-review/
│   └── context-optimization/
├── scripts/            # Automation
│   ├── lib/
│   │   ├── utils.js
│   │   └── formatters.js
│   ├── hooks/
│   │   ├── post-edit-format.js
│   │   ├── pre-bash-warn.js
│   │   └── session-end.js
│   └── package.json
└── sessions/           # Session logs (auto-generated)
```

## Agents

| Agent | Purpose |
|-------|---------|
| **planner** | Create implementation plans before coding |
| **code-reviewer** | Review code quality and patterns |
| **tdd-guide** | Guide test-driven development |
| **security-reviewer** | OWASP + LLM security audit |
| **architect** | System design and ADRs |
| **build-error-resolver** | Fix type and build errors |
| **doc-updater** | Keep documentation in sync |
| **refactor-cleaner** | Find and remove dead code |

## Skills

| Skill | Description |
|-------|-------------|
| **coding-standards** | Python/TypeScript coding rules |
| **python-backend-patterns** | FastAPI, SQLAlchemy async |
| **typescript-frontend-patterns** | Next.js 16, Radix UI |
| **tdd-workflow** | Red-Green-Refactor methodology |
| **security-review** | Security checklist |
| **context-optimization** | Reduce token usage |

Each skill has:
- `SKILL.md` - Full documentation
- `rules.md` - Quick reference

## Scripts

### Formatters

Auto-formatting after edits:
- **Python**: ruff (fast, opinionated)
- **TypeScript**: prettier

### Hooks

- **post-edit-format.js** - Format files after editing
- **pre-bash-warn.js** - Warn about remote-only commands
- **session-end.js** - Log session summary

## Global Rules

Located in `~/.config/opencode/rules/`:

| Rule | Purpose |
|------|---------|
| `security.md` | Security best practices |
| `coding-style.md` | Code style guidelines |
| `testing.md` | Testing requirements |
| `git-workflow.md` | Commit conventions |
| `agents.md` | When to delegate |
| `performance.md` | Model selection |

## Context Optimization

For long coding sessions:

1. **Delegate to agents** - Use `/code-review`, `/security-review`
2. **Compact often** - After completing tasks
3. **Use session context** - Track state in `.session-context.md`
4. **Load skills on-demand** - Don't load everything at once

See `skills/context-optimization/SKILL.md` for details.

## Configuration

OpenCode configuration in `~/.config/opencode/opencode.json`:

```json
{
  "model": {
    "default": "claude-sonnet-4-5-20250514"
  },
  "commands": {
    "plan": ".opencode/commands/plan.md",
    "tdd": ".opencode/commands/tdd.md",
    ...
  }
}
```

## Best Practices

1. **Plan first** - Use `/plan` for non-trivial features
2. **TDD when possible** - Better test coverage
3. **Review before commit** - Catch issues early
4. **Fix errors quickly** - Don't let them pile up
5. **Keep docs updated** - Part of the feature

## MSI-a Specific

This system is customized for MSI-a:

- **Spanish for users** - User-facing text in Spanish
- **English for code** - Variables, comments, docs
- **Async everywhere** - All I/O operations
- **Type safety** - Pydantic + TypeScript strict
- **LLM security** - Multi-layer prompt injection defense

## Related Documentation

- [AGENTS.md](../AGENTS.md) - Main repository guidelines
- [skills/](../skills/) - MSI-a specific skills
- [docs/decisions/](../docs/decisions/) - Architecture decisions
