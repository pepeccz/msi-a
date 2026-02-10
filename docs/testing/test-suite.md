# Testing Guide - MSI-a

This guide explains how to run tests in the MSI-a project using Docker-based test runner.

---

## Table of Contents

1. [Overview](#overview)
2. [Docker Test Runner](#docker-test-runner)
3. [Running Tests](#running-tests)
4. [Coverage Reports](#coverage-reports)
5. [Test Structure](#test-structure)
6. [Troubleshooting](#troubleshooting)

---

## Overview

MSI-a uses **pytest** for testing with the following setup:

- **Test Framework**: pytest + pytest-asyncio + pytest-cov
- **Test Location**: `tests/` directory
- **Execution Environment**: Docker containers (production-like environment)
- **Coverage Target**: ≥95% for critical validation code
- **Database**: PostgreSQL test database (`msia_db_test`)

### Why Docker-based Testing?

Tests run in Docker containers to:
- Ensure consistent environment across development machines
- Match production environment configuration
- Properly handle Python import paths
- Isolate test execution from local development
- Enable CI/CD integration

---

## Docker Test Runner

### Service Configuration

The `test-runner` service is defined in `docker-compose.yml`:

```yaml
test-runner:
  build:
    context: .
    dockerfile: docker/Dockerfile.agent
  container_name: msia-test-runner
  env_file: .env
  environment:
    - ENVIRONMENT=test
    - LOG_LEVEL=INFO
  depends_on:
    postgres:
      condition: service_healthy
    redis:
      condition: service_healthy
  networks:
    - msia-network
  volumes:
    - ./tests:/app/tests       # Mount tests directory
    - ./uploads:/app/uploads   # Mount uploads for test data
  profiles:
    - test                     # Only start with --profile test
```

### Key Features

- ✅ Uses same base image as agent service (`Dockerfile.agent`)
- ✅ Mounts `tests/` directory into container
- ✅ Connects to test database and Redis
- ✅ Environment isolated from production services
- ✅ Coverage reports generated automatically
- ✅ Activated via `--profile test` (won't interfere with normal operations)

---

## Running Tests

### 1. Run All Phase 1 Tests (48 tests)

Execute the defensive validation test suite:

```bash
docker-compose --profile test up test-runner
```

This will:
1. Build the test-runner container (if needed)
2. Wait for PostgreSQL and Redis to be healthy
3. Install test dependencies (pytest-cov, coverage)
4. Run Phase 1 tests:
   - `tests/agent/utils/test_tool_validation.py` (32 tests)
   - `tests/agent/modes/test_base_mode_validation.py` (16 tests)
5. Generate coverage reports
6. Keep container running for log inspection

### 2. Run Specific Test File

To run a specific test file:

```bash
docker-compose run --rm test-runner pytest tests/agent/utils/test_tool_validation.py -v
```

### 3. Run Specific Test Function

To run a specific test:

```bash
docker-compose run --rm test-runner pytest tests/agent/utils/test_tool_validation.py::test_validate_tool_args_success -v
```

### 4. Run All Tests (Entire Test Suite)

To run all tests in the project:

```bash
docker-compose run --rm test-runner pytest tests/ -v
```

### 5. Run Tests with Custom Options

```bash
# Run with verbose output and show local variables on failure
docker-compose run --rm test-runner pytest tests/ -vv --showlocals

# Run only unit tests (exclude integration/e2e)
docker-compose run --rm test-runner pytest tests/ -v -m unit

# Run tests in parallel (requires pytest-xdist)
docker-compose run --rm test-runner pytest tests/ -v -n auto

# Stop on first failure
docker-compose run --rm test-runner pytest tests/ -v -x

# Run last failed tests
docker-compose run --rm test-runner pytest tests/ -v --lf
```

### 6. Interactive Test Shell

To enter the container for debugging:

```bash
docker-compose run --rm test-runner bash
```

Then inside the container:
```bash
# Run tests manually
pytest tests/ -v

# Run Python REPL with modules loaded
python -c "from agent.utils.tool_validation import validate_tool_args; print(validate_tool_args.__doc__)"

# Check imports work
python -c "import agent.utils.tool_validation; print('Import successful')"
```

---

## Coverage Reports

### Coverage Target

**Target**: ≥95% coverage for defensive validation code:
- `agent/utils/tool_validation.py`
- `agent/modes/base_mode.py` (validation-related methods)

### Viewing Coverage

#### Terminal Report (Auto-generated)

After running tests, coverage is displayed in terminal:

```
---------- coverage: platform linux, python 3.11.x -----------
Name                                    Stmts   Miss  Cover   Missing
---------------------------------------------------------------------
agent/utils/tool_validation.py            156      8    95%   45-52
agent/modes/base_mode.py                  234     12    95%   112-118, 234-240
---------------------------------------------------------------------
TOTAL                                     390     20    95%
```

#### HTML Report (Detailed)

Coverage HTML report is generated at `tests/htmlcov/index.html`:

```bash
# Open in browser (from host machine)
open tests/htmlcov/index.html   # macOS
xdg-open tests/htmlcov/index.html  # Linux
start tests/htmlcov/index.html  # Windows
```

The HTML report shows:
- Line-by-line coverage highlighting
- Branch coverage analysis
- Missing lines highlighted in red
- Covered lines in green

#### JSON Report (CI/CD)

Machine-readable coverage report at `tests/coverage.json`:

```bash
cat tests/coverage.json | jq '.totals.percent_covered'
```

### Interpreting Coverage

```
Stmts   = Total statements (lines of code)
Miss    = Statements not executed during tests
Cover   = Coverage percentage
Missing = Line numbers not covered
```

**Example**:
```
agent/utils/tool_validation.py  156  8  95%  45-52
```
- 156 total statements
- 8 statements not executed
- 95% coverage
- Lines 45-52 need test coverage

---

## Test Structure

### Directory Layout

```
tests/
├── conftest.py                          # Shared fixtures
├── pytest.ini                           # Pytest configuration
├── agent/
│   ├── __init__.py
│   ├── utils/
│   │   ├── __init__.py
│   │   └── test_tool_validation.py      # 32 tests - Tool validation
│   ├── modes/
│   │   ├── __init__.py
│   │   └── test_base_mode_validation.py # 16 tests - Mode validation
│   ├── test_element_tools_cache.py
│   ├── test_case_tools_validation.py
│   └── ...
└── htmlcov/                             # Coverage HTML reports (generated)
```

### Test Fixtures (conftest.py)

Shared fixtures available to all tests:

```python
# Database
db_engine          # Test database engine
db_session         # Test database session
test_category_setup  # Pre-created test category
test_tiers_setup    # Pre-created test tiers

# Mocks
mock_redis         # Mock Redis client
mock_llm           # Mock LLM
mock_chatwoot      # Mock Chatwoot client

# Utilities
random_string      # Generate random strings
random_uuid        # Generate UUIDs
```

### Test Markers

Use markers to categorize tests:

```python
@pytest.mark.unit          # Unit tests (fast, isolated)
@pytest.mark.integration   # Integration tests (cross-service)
@pytest.mark.slow          # Slow tests (>1s)
@pytest.mark.e2e           # End-to-end tests
```

Run specific markers:
```bash
pytest -v -m unit              # Only unit tests
pytest -v -m "not slow"        # Exclude slow tests
pytest -v -m "unit or integration"  # Multiple markers
```

---

## Phase 1 Test Details

### Test Files

#### 1. `test_tool_validation.py` (32 tests, 684 lines)

**Coverage**: `agent/utils/tool_validation.py`

**Test Categories**:
- Basic validation (12 tests)
  - Missing required arguments
  - Invalid argument types
  - Unknown arguments rejection
  - Empty/None value handling
  
- Schema validation (8 tests)
  - Nested schema validation
  - List validation (homogeneous types)
  - Dict validation (typed keys/values)
  - Complex nested structures
  
- Edge cases (12 tests)
  - Unicode strings
  - Large numbers
  - Boolean edge cases
  - Empty collections
  - Null/None handling
  - Special characters

**Example Test**:
```python
async def test_validate_tool_args_missing_required():
    """Test that missing required arguments are rejected."""
    schema = {
        "required_field": {"type": "string", "required": True},
    }
    
    with pytest.raises(ValueError, match="Missing required argument"):
        validate_tool_args({}, schema, "test_tool")
```

#### 2. `test_base_mode_validation.py` (16 tests, 593 lines)

**Coverage**: `agent/modes/base_mode.py` (validation methods)

**Test Categories**:
- Pre-execution validation (8 tests)
  - Tool existence verification
  - Argument schema validation
  - Dangerous pattern detection
  - State corruption prevention
  
- Post-execution validation (8 tests)
  - Return value validation
  - Error handling verification
  - State consistency checks
  - Tool call logging verification

**Example Test**:
```python
async def test_base_mode_rejects_dangerous_patterns():
    """Test that dangerous patterns are rejected before execution."""
    mode = MyTestMode()
    
    # Try to execute tool with state corruption pattern
    with pytest.raises(ValueError, match="Dangerous pattern"):
        await mode._validate_tool_call(
            "update_conversation_state",
            {"updates": {"current_mode": "HACKED"}},
            state
        )
```

### Success Criteria

✅ All 48 tests pass  
✅ Coverage ≥95% for validation code  
✅ No import errors  
✅ Reproducible test runs  
✅ Tests complete in <30 seconds  

---

## Troubleshooting

### Import Errors

**Problem**: `ModuleNotFoundError: No module named 'agent.utils.tool_validation'`

**Solution**: Use Docker test runner (not local pytest):
```bash
# ❌ WRONG (local pytest)
pytest tests/

# ✅ CORRECT (Docker test runner)
docker-compose --profile test up test-runner
```

**Why**: Tests directory is not mounted in regular agent container. The test-runner service has tests mounted properly.

---

### Database Connection Errors

**Problem**: `connection refused` or `database "msia_db_test" does not exist`

**Solution**: Ensure PostgreSQL is healthy:
```bash
# Check service health
docker-compose ps

# Verify PostgreSQL is running
docker-compose exec postgres pg_isready -U msia
```

The test runner automatically waits for PostgreSQL via `depends_on: condition: service_healthy`.

---

### Permission Errors on Coverage Files

**Problem**: Cannot write to `tests/htmlcov/` or `tests/coverage.json`

**Solution**: Fix permissions on host:
```bash
sudo chown -R $USER:$USER tests/htmlcov tests/coverage.json
```

Or run container with host user:
```bash
docker-compose run --rm --user $(id -u):$(id -g) test-runner pytest tests/ -v
```

---

### Test Container Keeps Running

**Problem**: Test container doesn't exit after tests complete

**Solution**: This is intentional (for log inspection). Stop manually:
```bash
docker-compose --profile test down
```

For auto-exit, use `docker-compose run --rm`:
```bash
docker-compose run --rm test-runner pytest tests/ -v
```

---

### Redis Connection Errors

**Problem**: `redis.exceptions.ConnectionError: Error connecting to Redis`

**Solution**: Verify Redis is healthy:
```bash
docker-compose exec redis redis-cli -a $REDIS_PASSWORD ping
```

Check `.env` has correct `REDIS_PASSWORD`.

---

### Slow Test Execution

**Problem**: Tests take >1 minute to run

**Solutions**:
1. Run tests in parallel:
   ```bash
   docker-compose run --rm test-runner sh -c "pip install pytest-xdist && pytest tests/ -n auto"
   ```

2. Run only fast tests:
   ```bash
   docker-compose run --rm test-runner pytest tests/ -v -m "not slow"
   ```

3. Use test database caching (already configured in conftest.py)

---

### Clean Test Environment

**Problem**: Need to reset test database or clear test data

**Solution**:
```bash
# Stop all services
docker-compose down

# Remove test database volume (⚠️ destroys data)
docker volume rm msi-a_postgres_data

# Restart with fresh database
docker-compose up -d postgres redis
docker-compose --profile test up test-runner
```

---

## Best Practices

### Writing New Tests

1. **Place tests in correct directory**:
   ```
   tests/agent/utils/          # For agent/utils/ modules
   tests/agent/modes/          # For agent/modes/ modules
   tests/api/routes/           # For api/routes/ modules
   ```

2. **Use descriptive test names**:
   ```python
   # ❌ BAD
   def test_validation():
       pass
   
   # ✅ GOOD
   async def test_validate_tool_args_rejects_missing_required_fields():
       pass
   ```

3. **Use fixtures**:
   ```python
   async def test_my_feature(db_session, mock_redis):
       # Use shared fixtures
       pass
   ```

4. **Mark tests appropriately**:
   ```python
   @pytest.mark.unit
   async def test_pure_function():
       pass
   
   @pytest.mark.integration
   async def test_cross_service_flow():
       pass
   ```

5. **Write async tests**:
   ```python
   # ✅ CORRECT - async test
   async def test_async_function():
       result = await my_async_function()
       assert result == expected
   ```

### Running Tests Locally (Development)

For rapid iteration during development:

```bash
# Start test-runner in background
docker-compose --profile test up -d test-runner

# Exec into running container
docker-compose exec test-runner bash

# Inside container: run tests repeatedly
pytest tests/agent/utils/test_tool_validation.py -v
# Edit code on host, tests auto-detect changes
pytest tests/agent/utils/test_tool_validation.py -v
```

### Continuous Integration

For CI/CD pipelines:

```bash
# Run tests and exit (non-interactive)
docker-compose run --rm test-runner pytest tests/ -v --cov --cov-report=json

# Check exit code
if [ $? -eq 0 ]; then
  echo "Tests passed"
else
  echo "Tests failed"
  exit 1
fi

# Verify coverage threshold
python -c "
import json
with open('tests/coverage.json') as f:
    coverage = json.load(f)['totals']['percent_covered']
    assert coverage >= 95, f'Coverage {coverage}% below threshold'
"
```

---

## Additional Commands

### View Test Logs

```bash
# View test-runner logs
docker-compose --profile test logs -f test-runner

# View logs from specific test run
docker-compose run --rm test-runner pytest tests/ -v 2>&1 | tee test-output.log
```

### Clean Up Test Artifacts

```bash
# Remove coverage reports
rm -rf tests/htmlcov tests/coverage.json tests/.coverage

# Remove pytest cache
rm -rf tests/.pytest_cache
```

### Update Test Dependencies

If test requirements change:

```bash
# Rebuild test-runner with new dependencies
docker-compose build --no-cache test-runner

# Or install in running container
docker-compose exec test-runner pip install pytest-xdist
```

---

## Quick Reference

| Task | Command |
|------|---------|
| Run Phase 1 tests | `docker-compose --profile test up test-runner` |
| Run all tests | `docker-compose run --rm test-runner pytest tests/ -v` |
| Run specific file | `docker-compose run --rm test-runner pytest tests/agent/utils/test_tool_validation.py -v` |
| Run with coverage | `docker-compose run --rm test-runner pytest tests/ -v --cov --cov-report=term-missing` |
| Enter test shell | `docker-compose run --rm test-runner bash` |
| View coverage HTML | `open tests/htmlcov/index.html` |
| Stop test runner | `docker-compose --profile test down` |
| Clean environment | `docker-compose down && docker volume rm msi-a_postgres_data` |

---

## Related Documentation

- [pytest documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [pytest-cov](https://pytest-cov.readthedocs.io/)
- [Testing standards](coding-standards/07-testing.md)
- [Agent architecture](coding-standards/03-agent-architecture.md)

---

**Last Updated**: February 2026  
**Maintained by**: QA-dev team
