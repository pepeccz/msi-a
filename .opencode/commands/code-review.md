# /code-review Command

Review code for quality, security, and best practices.

## Usage

```
/code-review <file path or description>
/code-review                          # Review recent changes
```

## Examples

```
/code-review api/routes/tariffs.py
/code-review the changes I just made
/code-review agent/tools/
```

## Behavior

1. Delegates to the **code-reviewer** agent
2. Analyzes code against quality checklist
3. Checks for security vulnerabilities
4. Verifies adherence to project standards

## Review Checklist

- **Code Quality**: Types, naming, structure, DRY
- **Security**: Injection, secrets, auth, validation
- **Async Patterns**: Proper await, no blocking
- **React Patterns**: Server components, keys, hooks
- **Testing**: Coverage, edge cases, mocks
- **MSI-a Specific**: Spanish strings, Pydantic, FSM

## Output

```markdown
## Code Review Summary

### Grade: A/B/C/D/F

### Critical Issues (Must Fix)
...

### Improvements (Should Fix)
...

### Minor Notes (Consider)
...

### Positive Highlights
...
```

## When to Use

- After completing a feature
- Before creating a PR
- When unsure about code quality
- When reviewing someone else's code

## Notes

- Critical issues should be fixed before merging
- Security issues are always critical
- The grade is a guideline, not absolute
