# /plan Command

Plan implementation before coding.

## Usage

```
/plan <feature or task description>
```

## Examples

```
/plan Add email notifications for new homologation requests
/plan Refactor tariff calculation to support discounts
/plan Create new admin page for managing document templates
```

## Behavior

1. Delegates to the **planner** agent
2. Analyzes the request and identifies affected components
3. Creates a detailed implementation plan
4. **Waits for user confirmation before any coding**

## Output

A structured plan including:
- Summary of changes
- Affected components (agent, api, admin-panel, database)
- Step-by-step implementation order
- Testing strategy
- Risks and considerations

## When to Use

- Before starting any non-trivial feature
- When requirements are unclear
- When changes span multiple components
- When you want to think through the approach first

## Notes

- The agent will NOT write code until you confirm the plan
- You can ask for modifications to the plan
- Plans are saved for reference during implementation
