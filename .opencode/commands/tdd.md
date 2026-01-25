# /tdd Command

Guide implementation using Test-Driven Development.

## Usage

```
/tdd <feature or function to implement>
```

## Examples

```
/tdd Calculate tariff with tiered pricing
/tdd Validate vehicle plate format
/tdd Create user registration endpoint
```

## Behavior

1. Delegates to the **tdd-guide** agent
2. Writes a failing test FIRST
3. Guides minimal implementation to pass
4. Suggests refactoring opportunities

## The TDD Cycle

```
┌─────────┐     ┌─────────┐     ┌──────────┐
│   RED   │────▶│  GREEN  │────▶│ REFACTOR │
│  Write  │     │  Make   │     │  Clean   │
│  Test   │     │  Pass   │     │   Up     │
└─────────┘     └─────────┘     └────┬─────┘
     ▲                               │
     └───────────────────────────────┘
```

## Output

1. A test file with failing test(s)
2. Minimal implementation to pass
3. Refactoring suggestions
4. Additional edge case tests

## When to Use

- When implementing new functions
- When fixing bugs (write test that reproduces first)
- When you want better test coverage
- When learning TDD practices

## Notes

- Tests are written in pytest (Python) or Jest (TypeScript)
- Focus on behavior, not implementation details
- Each cycle should be small and focused
