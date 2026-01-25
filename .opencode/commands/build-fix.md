# /build-fix Command

Diagnose and fix build, type, and lint errors.

## Usage

```
/build-fix                    # Fix all current errors
/build-fix <error message>    # Fix specific error
/build-fix api/               # Fix errors in directory
```

## Examples

```
/build-fix
/build-fix TypeScript error TS2339
/build-fix the mypy errors in agent/
```

## Behavior

1. Delegates to the **build-error-resolver** agent
2. Runs build/type checking if needed
3. Categorizes errors by type
4. Applies fixes in order of severity
5. Verifies fixes with another build

## Error Categories

| Category | Tools | Priority |
|----------|-------|----------|
| Type Errors | mypy, tsc | High |
| Lint Errors | ruff, eslint | Medium |
| Build Errors | next build, python | High |
| Import Errors | - | High |

## Output

```markdown
## Build Error Analysis

### Error Count: X errors

### Error 1: [Code]
- **File**: path:line
- **Cause**: [explanation]
- **Fix**: [code change]

### Verification
[Commands to verify fixes]
```

## Quick Reference

| Error | Quick Fix |
|-------|-----------|
| `implicitly has 'any'` | Add type annotation |
| `possibly 'undefined'` | Add `?.` or null check |
| `Cannot find module` | Check import path |
| `unused variable` | Remove or prefix `_` |
| `'use client'` needed | Add directive |

## When to Use

- After npm/pip install
- When CI fails
- After major refactoring
- When upgrading dependencies
- Before committing code

## Notes

- Don't use `any` to silence errors
- Don't use `# type: ignore` without reason
- Run tests after fixing errors
