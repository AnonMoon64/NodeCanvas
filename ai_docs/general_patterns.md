# General NodeCanvas Logic Patterns

## State vs. Pure Functions
- **State**: Any data that persists over time (Health, Score, Position) MUST be a **Variable**.
- **Pure Functions**: Math operations (Add, Mul) should be used as data providers for state writers.

## Execution Flow
- Execution pins (white) define the **temporal order** of operations.
- Always ensure the execution chain is linear and logical.
- Avoid "magic" connections; if a node has an `exec_in`, it must be part of a chain to ever run.

## Readability & Layout
- Keep **Event** nodes at the far left.
- Keep **Data Provider** nodes (Variables, Math) below the main execution line to avoid path crossing.
- Use **Rename Node** to give descriptive labels to constants (e.g., rename a Const to "DefaultSpeed").
