# /doc-update Command

Synchronize documentation with code changes.

## Usage

```
/doc-update                      # Check all docs need updating
/doc-update <file or feature>    # Update docs for specific change
```

## Examples

```
/doc-update
/doc-update api/routes/tariffs.py
/doc-update after adding the new webhook endpoint
```

## Behavior

1. Delegates to the **doc-updater** agent
2. Identifies documentation that needs updating
3. Generates documentation updates
4. Maintains consistency across docs

## Documentation Hierarchy

```
AGENTS.md           # AI guidelines (root)
README.md           # Project overview
docs/decisions/     # Architecture Decision Records
skills/*/           # Skill documentation
*/AGENTS.md         # Component-specific guidelines
.env.example        # Environment variables
```

## What Gets Updated

| Code Change | Documentation |
|-------------|---------------|
| New API endpoint | API docs, AGENTS.md |
| New env variable | .env.example |
| New database model | Schema docs |
| Architecture change | ADR in docs/decisions/ |
| New skill/agent | Skill index |

## Output

```markdown
## Documentation Updates Required

### Files to Update
1. **path/to/doc.md**
   - [What needs changing]

### Changes Made
[Diff of changes]

### No Changes Needed
[Files that are still accurate]
```

## When to Use

- After completing a feature
- Before creating a PR
- After API changes
- When adding new components
- During documentation reviews

## Notes

- Only update when code changes require it
- Don't duplicate information
- Keep docs focused on "what" and "why", not "how"
- Spanish for user-facing, English for technical docs
