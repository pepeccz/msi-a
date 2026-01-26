# /test Command

Run tests for the MSI-a project (Python backend or TypeScript frontend).

## Usage

```
/test                          # Run all tests (backend + frontend)
/test backend                  # Run Python tests only
/test frontend                 # Run React/Next.js tests only
/test <file or pattern>        # Run specific test file
```

## Examples

```
/test
/test backend
/test frontend
/test agent/test_validation.py
/test elements-tree-section
/test --coverage
```

## Behavior

### Backend (Python + pytest)
- Runs pytest with coverage tracking
- Uses structured logging for test output
- Shows detailed failure information

### Frontend (TypeScript + Jest + React Testing Library)
- Runs Jest with React Testing Library
- Generates coverage report
- Supports watch mode for development

## Commands Executed

**All tests**:
```bash
# Backend
pytest tests/ -v --tb=short --cov=agent --cov=api --cov-report=term-missing

# Frontend  
cd admin-panel && npm test -- --coverage
```

**Backend only**:
```bash
pytest tests/ -v --tb=short --cov=agent --cov=api --cov-report=term-missing
```

**Frontend only**:
```bash
cd admin-panel && npm test -- --coverage
```

**Specific file (auto-detect)**:
```bash
# Python file
pytest tests/agent/test_validation.py -v

# TypeScript/React file
cd admin-panel && npm test -- elements-tree-section
```

**With coverage**:
```bash
# Adds --coverage flag to npm test or --cov to pytest
```

## Output

### Backend Output
- Test results with pass/fail status
- Coverage percentage per module
- Failed test details with stack traces
- Warnings and deprecations

### Frontend Output
- Test suite summary
- Coverage table (statements, branches, functions, lines)
- Failed test details
- Snapshot diffs (if applicable)

## When to Use

- ✅ Before committing code
- ✅ After implementing new features
- ✅ When fixing bugs (write test first, then fix)
- ✅ After code review fixes
- ✅ Before deploying to production
- ✅ When refactoring code

## Related Commands

- `/tdd` - Guide Test-Driven Development implementation
- `/code-review` - Review code quality and standards
- `/build-fix` - Fix TypeScript/build errors
- `/security-review` - Security audit

## Notes

- Backend tests require a running PostgreSQL and Redis instance (use docker-compose)
- Frontend tests run in jsdom environment (no real browser needed)
- Coverage reports are saved to:
  - Backend: `.coverage` and console output
  - Frontend: `admin-panel/coverage/`
- Test files must follow naming convention:
  - Backend: `test_*.py` or `*_test.py`
  - Frontend: `*.test.tsx` or `*.spec.tsx` or `__tests__/*`
