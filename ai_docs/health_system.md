# Guideline: Building a Robust Health System

To create a professional health system in NodeCanvas, follow these architectural rules:

## 1. Use Variables for State
**NEVER** use a `Constant` node to store the current health value. Always create a **Variable** named `Health` (float).
- Use `add_variable` to initialize `Health` and `MaxHealth`.
- Use the `GetVariable` node to read the current health.
- Use the `SetVariable` node to update it.

## 2. Mandatory Initialization Logic
A professional health system must initialize itself.
- On the `OnStart` event, the first action should be a `SetVariable` that sets `Health` equal to the value of `MaxHealth`.
- **Logic Flow**: `OnStart` (Exec) → `SetVariable` (Health) ← `GetVariable` (MaxHealth).

## 3. Damage & Calculation Logic
... (as before) ...

## 4. Efficiency & Completeness Rule
- **USE OR DELETE**: If you create a variable or a node, you **MUST** connect it to the logic flow. If it's not needed, delete it.
- **NEVER** leave a `MaxHealth` variable orphaned while hardcoding 100 into a calculation.
- **Aim for COMPONENT-LEVEL ROBUSTNESS**: A simple print is not a system. A system includes initialization, bounds checking (clamping), and meaningful feedback.
