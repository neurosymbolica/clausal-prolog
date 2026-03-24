# Destructive reuse optimization

## Idea

When the compiler can prove that the original list or dict is never used again
after a construction operation (e.g. append, DictPut, DictMerge, set union),
emit a Python-level **mutation** instead of creating a new object.

## Motivation

Clausal semantics are purely logical — no mutation is visible to the program.
But under the hood, if the source value is about to be garbage-collected anyway,
we can safely mutate it. This is the same insight behind:

- Haskell's fusion/rewrite rules
- Mercury's compile-time uniqueness analysis
- Python list `.append()` vs `[*old, x]`

## Scope

- **Lists**: `Append(OLD, [X], NEW)` where OLD is dead after this goal
  → compile to `old.append(x); new = old` instead of `new = old + [x]`
- **Dicts**: `DictPut(KEY, VALUE, OLD, NEW)` where OLD is dead
  → compile to `old[key] = value; new = old` instead of `new = {**old, key: value}`
- **Sets**: `SetUnion(OLD, {X}, NEW)` where OLD is dead
  → compile to `old.add(x); new = old`

## Requirements

- Liveness / uniqueness analysis at compile time (or reference-count check at
  runtime, a la `sys.getrefcount`)
- Must not affect backtracking: if trail-undo is needed, the mutation must be
  reversible or the optimization must be suppressed for goals inside choice points
- Start with the easy case: last goal in a clause body, deterministic context,
  source variable appears nowhere else in the clause
