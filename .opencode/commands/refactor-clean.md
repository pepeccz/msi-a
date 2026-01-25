# /refactor-clean Command

Find and remove dead code, improve organization.

## Usage

```
/refactor-clean                   # Scan entire codebase
/refactor-clean <file or dir>     # Focus on specific area
```

## Examples

```
/refactor-clean
/refactor-clean api/services/
/refactor-clean agent/tools/
```

## Behavior

1. Delegates to the **refactor-cleaner** agent
2. Scans for dead code and unused dependencies
3. Identifies refactoring opportunities
4. Applies safe cleanups
5. Verifies tests still pass

## Cleanup Categories

| Category | What It Finds |
|----------|---------------|
| Dead Code | Unused functions, variables, imports |
| Commented Code | Old code in comments |
| Large Files | Files > 500 lines |
| Long Functions | Functions > 50 lines |
| Duplicated Code | Similar code blocks |
| Unused Dependencies | Packages not used |

## Output

```markdown
## Cleanup Report

### Dead Code Found
| File | Type | Code |
|------|------|------|

### Refactoring Opportunities
1. [Description with location]

### Recommended Actions
1. [ ] [Action item]

### Estimated Impact
- Lines removed: ~X
- Risk level: Low/Medium/High
```

## Safety Checks

- Only removes code covered by tests
- Preserves dynamic imports/exports
- Keeps code used by external tools
- Commits frequently

## When to Use

- During sprint cleanup
- Before major releases
- When codebase feels cluttered
- After removing features
- Monthly maintenance

## Notes

- Always run tests after cleanup
- Review changes before committing
- Don't refactor while adding features
- Use `git diff` to verify changes
