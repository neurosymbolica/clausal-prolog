# TFilter/TPartition: Trampoline Protocol Mismatch

**Status:** Working but architecturally inconsistent.

**Affects:** `TFilter/3`, `TPartition/4` in `clausal/logic/builtins/higher_order.py`

## Current Implementation

`Filter/3`, `Exclude/3`, and `Partition/4` yield `StepGenerator` objects to
the trampoline, letting the trampoline drive the sub-goal execution:

```python
sg = StepGenerator(dispatch, this_generator, deref(elem), trail)
_st = yield (sg, None)
found = _st is not DONE
```

`TFilter/3` and `TPartition/4` instead use `_run_goal_once()`, a helper that
drives the trampoline internally:

```python
for _ in _run_goal_once(dispatch, deref(elem), t_var, trail):
    t_val = deref(t_var)
    break  # committed choice
```

## Why

Reified goals like `Eq/3` produce multiple solutions — one for T=True, one
for T=False (when the result is undetermined). TFilter needs committed-choice
semantics: take the first truth value and move on. The trampoline yield
protocol doesn't have a built-in "take first solution only" mechanism — once
you yield `(sg, None)`, the trampoline will keep sending solutions until DONE.

Driving the sub-goal internally via `_run_goal_once` sidesteps this, but it
means the sub-goal's execution doesn't participate in the trampoline's
cooperative scheduling. For deeply nested or recursive reified goals, this
could cause stack growth.

## Potential Fix

Add a "once" wrapper to the trampoline protocol:

1. A `OnceStepGenerator` that wraps a `StepGenerator` and stops after the
   first solution (converts the second yield to DONE).
2. Or: a flag on `StepGenerator` that limits solutions to 1.

Then TFilter/TPartition could use the standard yield protocol:

```python
sg = OnceStepGenerator(dispatch, this_generator, deref(elem), t_var, trail)
_st = yield (sg, None)
# _st is the first solution or DONE
```

This would make TFilter/TPartition consistent with Filter/Exclude/Partition
and preserve stack-safe execution.

## Priority

Low. The current implementation works correctly for all practical use cases.
The inconsistency only matters for deeply recursive reified goals where stack
depth could be a concern.

## Files

- `clausal/logic/builtins/higher_order.py` — `_tfilter__3`, `_tpartition__4`, `_run_goal_once`
- `clausal/logic/trampoline.py` — `StepGenerator` (would need `OnceStepGenerator`)
