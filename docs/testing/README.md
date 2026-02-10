# Testing Documentation

This directory contains all testing documentation, test suites, validation summaries, and test results.

---

## 📁 Structure

```
testing/
├── test-suite.md                    # Complete test suite overview
├── summary.md                       # Test summary and coverage
├── validation-summary.md            # Validation test results
├── semantic-validation-quick-reference.md  # Quick reference for validation patterns
├── test-fix-report.md               # Test fixes and improvements
└── results/                         # Test run results by date
    └── 2026-02-08-complete.md
```

---

## 🎯 Test Coverage

### Overall Coverage

| Component | Coverage | Status |
|-----------|----------|--------|
| API Routes | 92% | ✅ Excellent |
| Agent Tools | 88% | ✅ Good |
| Services | 91% | ✅ Excellent |
| Database Models | 85% | ✅ Good |
| Frontend Components | 78% | ⚠️ Needs improvement |

**Target**: >90% for critical paths

---

## 📄 Key Documents

### Test Suite

**File**: [test-suite.md](test-suite.md)

Complete overview of all tests:
- Unit tests (pytest)
- Integration tests
- E2E tests
- Frontend tests (Jest)

---

### Test Summary

**File**: [summary.md](summary.md)

High-level summary of test results:
- Pass/fail statistics
- Coverage by component
- Known issues
- Test improvements

---

### Validation Tests

**File**: [validation-summary.md](validation-summary.md)

Detailed validation test results:
- Parameter validation tests
- Semantic validation tests
- Database constraint tests
- Tool validation tests

---

### Quick Reference

**File**: [semantic-validation-quick-reference.md](semantic-validation-quick-reference.md)

Quick reference guide for validation patterns:
- How to validate category slugs
- How to validate element codes
- How to validate field keys
- Common validation patterns

---

## 🧪 Test Types

### Unit Tests

**Location**: `tests/`

**Framework**: pytest

**Run**: `pytest tests/ -v --cov`

**Coverage**: Tests individual functions/methods in isolation

**Example**:
```python
async def test_calculate_tariff_valid_elements():
    # Test tariff calculation with valid elements
    result = await calculate_tariff(["ESCAPE", "MANILLAR"], "motos-part")
    assert result["success"] is True
    assert result["precio"] > 0
```

---

### Integration Tests

**Location**: `tests/integration/`

**Coverage**: Tests interaction between components

**Example**:
```python
async def test_element_identification_flow():
    # Test full element identification flow
    # 1. User input
    # 2. Element service matching
    # 3. Variant resolution
    # 4. Database persistence
```

---

### E2E Tests

**Location**: `tests/e2e/`

**Coverage**: Tests complete user flows

**Example**:
```python
async def test_presupuesto_complete_flow():
    # Test complete presupuesto flow:
    # 1. User asks for quote
    # 2. Agent identifies elements
    # 3. Calculates tariff
    # 4. Sends images
    # 5. User confirms
```

---

### Frontend Tests

**Location**: `admin-panel/src/__tests__/`

**Framework**: Jest + React Testing Library

**Run**: `npm test`

**Coverage**: React components, hooks, contexts

**Example**:
```typescript
test('renders tariff list', async () => {
  render(<TariffList />);
  await waitFor(() => {
    expect(screen.getByText('Motos Particular')).toBeInTheDocument();
  });
});
```

---

## 🔍 Validation Testing

### Parameter Validation (Phase 1)

**What**: Defensive validation at tool entry points

**Tests**:
- Null/undefined parameters
- Wrong types (string vs UUID)
- Missing required parameters
- Empty strings/arrays

**Result**: 100% coverage, 0 validation failures in production

---

### Semantic Validation (Phase 2)

**What**: Database-backed validation of business logic

**Tests**:
- Invalid category slugs
- Non-existent element codes
- Invalid field keys
- Mismatched relationships

**Result**: 100% coverage, eliminated invalid data reaching DB

---

### Retry Logic (Phase 3)

**What**: Validation with retry on transient failures

**Tests**:
- Network timeout retry
- Database lock retry
- Rate limit retry
- Max retries exhausted

**Result**: 95% success rate on retries, proper fallback on exhaustion

---

## 📊 Test Results

### Latest Run: 2026-02-08

**File**: [results/2026-02-08-complete.md](results/2026-02-08-complete.md)

**Summary**:
- Total tests: 342
- Passed: 341 (99.7%)
- Failed: 1 (0.3%)
- Skipped: 0
- Duration: 3m 42s

**Coverage**:
- Lines: 89.2%
- Branches: 84.1%
- Functions: 91.3%

---

## 🚀 Running Tests

### Backend Tests

```bash
# All tests with coverage
pytest tests/ -v --cov --cov-report=html

# Specific test file
pytest tests/test_element_service.py -v

# Specific test
pytest tests/test_element_service.py::test_identify_elements -v

# With markers
pytest -m "not slow" -v
```

---

### Frontend Tests

```bash
# All tests
npm test

# Watch mode
npm test -- --watch

# Coverage
npm test -- --coverage

# Specific test
npm test -- TariffList
```

---

### Integration Tests

```bash
# Requires services running
docker-compose up -d postgres redis

# Run integration tests
pytest tests/integration/ -v
```

---

## 🔗 Related Documentation

- **Coding Standards**: `docs/coding-standards/07-testing.md` - Testing patterns
- **Architecture**: `docs/architecture/current/04-fallback.md` - Retry patterns
- **Deployment**: `docs/deployment/` - Test results before deployments
- **Skills**: `skills/pytest-async/SKILL.md`, `skills/msia-test/SKILL.md`

---

## 📝 Test Writing Guidelines

### Good Test Characteristics

✅ **Independent**: Each test runs in isolation  
✅ **Repeatable**: Same input → same output  
✅ **Fast**: Unit tests <100ms, integration <1s  
✅ **Clear**: Descriptive names, clear assertions  
✅ **Comprehensive**: Test happy path + edge cases  

### Test Naming Convention

```python
# Format: test_<what>_<condition>_<expected_result>

# Good
async def test_calculate_tariff_with_invalid_category_returns_error():
    pass

# Bad
async def test_tariff():
    pass
```

---

**Last Updated**: February 2026  
**Test Coverage**: 89.2% overall
