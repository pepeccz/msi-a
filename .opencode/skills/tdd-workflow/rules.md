# TDD Quick Rules

## The Cycle

1. **RED** - Write test that fails
2. **GREEN** - Minimal code to pass
3. **REFACTOR** - Clean up

## Test Pattern

```python
@pytest.mark.asyncio
async def test_behavior_description():
    # Arrange
    service = MyService()
    
    # Act
    result = await service.do_thing()
    
    # Assert
    assert result.value == expected
```

## Mocking

```python
@patch("module.function", new_callable=AsyncMock)
async def test_with_mock(mock_fn):
    mock_fn.return_value = {"data": "test"}
    # ...
    mock_fn.assert_called_once()
```

## Coverage Goals

- Minimum: 70%
- Target: 85%
- Critical: 100%

## Don't

- Don't write code before test
- Don't test implementation details
- Don't skip the refactor step
- Don't write multiple tests at once
