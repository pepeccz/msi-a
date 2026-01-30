---
name: skill-creator
description: >
  Creates new AI agent skills following the Agent Skills spec.
  Trigger: When user asks to create a new skill, add agent instructions, or document patterns for AI.
metadata:
  author: msi-automotive
  version: "1.0"
  scope: [root]
  auto_invoke: "Creating new skills"
---

## When to Create a Skill

Create a skill when:
- A pattern is used repeatedly and AI needs guidance
- Project-specific conventions differ from generic best practices
- Complex workflows need step-by-step instructions
- Decision trees help AI choose the right approach

**Don't create a skill when:**
- Documentation already exists (create a reference instead)
- Pattern is trivial or self-explanatory
- It's a one-off task

---

## Skill Structure

```
skills/{skill-name}/
├── SKILL.md              # Required - main skill file
├── assets/               # Optional - templates, schemas, examples
│   ├── template.py
│   └── schema.json
└── references/           # Optional - links to local docs
    └── docs.md
```

---

## SKILL.md Template

See [assets/skill_template.md](assets/skill_template.md) for a ready-to-use template.

```markdown
---
name: {skill-name}
description: >
  {One-line description of what this skill does}.
  Trigger: {When the AI should load this skill}.
metadata:
  author: msi-automotive
  version: "1.0"
  scope: [root, api, agent, admin-panel, database]
  auto_invoke: "Action that triggers this skill"
---

## When to Use

{Bullet points of when to use this skill}

## Critical Patterns

{The most important rules - what AI MUST know}

## Code Examples

{Minimal, focused examples}

## Commands

```bash
{Common commands}
```

## Resources

- **Templates**: See [assets/](assets/) for {description}
- **Documentation**: See [references/](references/) for local docs
```

---

## Naming Conventions

| Type | Pattern | Examples |
|------|---------|----------|
| Generic skill | `{technology}` | `fastapi`, `langgraph`, `pytest-async` |
| MSI-a specific | `msia-{component}` | `msia-api`, `msia-agent`, `msia-admin` |
| Workflow skill | `{action}-{target}` | `skill-creator` |

---

## Frontmatter Fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Skill identifier (lowercase, hyphens) |
| `description` | Yes | What + Trigger in one block |
| `metadata.author` | Yes | `msi-automotive` |
| `metadata.version` | Yes | Semantic version as string |
| `metadata.scope` | Yes | Where it applies: root, api, agent, admin-panel, database |
| `metadata.auto_invoke` | Yes | Action phrase that triggers loading |

---

## Scope Values

| Scope | Meaning |
|-------|---------|
| `root` | Applies project-wide |
| `api` | Applies to `api/` directory |
| `agent` | Applies to `agent/` directory |
| `admin-panel` | Applies to `admin-panel/` directory |
| `database` | Applies to `database/` directory |

---

## Decision: assets/ vs references/

```
Need code templates?        → assets/
Need JSON schemas?          → assets/
Need example configs?       → assets/
Link to existing docs?      → references/
Link to external guides?    → references/
```

---

## Decision: MSI-a Specific vs Generic

```
Patterns apply to ANY project?     → Generic skill (e.g., fastapi, pytest-async)
Patterns are MSI-a specific?       → msia-{name} skill
Generic skill needs MSI-a info?    → Add references/ pointing to local docs
```

---

## Content Guidelines

### DO
- Start with the most critical patterns
- Use tables for decision trees
- Keep code examples minimal and focused
- Include Commands section with copy-paste commands
- Use "ALWAYS" and "NEVER" for critical rules

### DON'T
- Duplicate content from existing docs (reference instead)
- Include lengthy explanations (link to docs)
- Add troubleshooting sections (keep focused)
- Make skills longer than ~300 lines

---

## Registering the Skill

After creating the skill, update `AGENTS.md`:

1. Add to "Available Skills" table:
```markdown
| `{skill-name}` | {Description} | [SKILL.md](skills/{skill-name}/SKILL.md) |
```

2. Add to "Auto-invoke Skills" table:
```markdown
| {Action that triggers} | `{skill-name}` |
```

3. If component-specific, also update the component's `AGENTS.md`:
   - `agent/AGENTS.md`
   - `api/AGENTS.md`
   - `admin-panel/AGENTS.md`
   - `database/AGENTS.md`

---

## Checklist Before Creating

- [ ] Skill doesn't already exist (check `skills/`)
- [ ] Pattern is reusable (not one-off)
- [ ] Name follows conventions
- [ ] Frontmatter is complete
- [ ] Description includes trigger keywords
- [ ] Critical patterns are clear
- [ ] Code examples are minimal
- [ ] Added to AGENTS.md Available Skills table
- [ ] Added to AGENTS.md Auto-invoke table
- [ ] Added to component AGENTS.md if scoped

---

## Example: Creating a New Skill

```bash
# 1. Create directory
mkdir -p skills/msia-chatwoot

# 2. Create SKILL.md (copy from template)
cp skills/skill-creator/assets/skill_template.md skills/msia-chatwoot/SKILL.md

# 3. Edit SKILL.md with your content

# 4. Add templates if needed
mkdir -p skills/msia-chatwoot/assets

# 5. Update AGENTS.md tables
```

## Resources

- **Templates**: See [assets/](assets/) for SKILL.md template
