# `_runtime_arg_key` int/str fast path

## Context

`_runtime_arg_key` is called from every clause dispatch to extract the hashable
index key from a deref'd argument.  It does `isinstance(a, _INDEXABLE_TYPES)`
which checks against a 6-element tuple `(int, float, str, bytes, bool, NoneType)`.
For the most common dispatch types (int, str), a direct `type(a) is int` check
is faster than isinstance against a tuple.

### Profile data

The function is inlined into dispatch closures (not separately profiled), but it
runs on every clause entry: ~485K times in fib, ~375K in nqueens, ~119K in qsort.

## What to do

**File:** `clausal/logic/compiler.py`
**Function:** `_runtime_arg_key` (line ~7124)

Current:
```python
def _runtime_arg_key(a: Any) -> Any:
    if isinstance(a, _INDEXABLE_TYPES):
        return a
    if isinstance(a, Compound):
        return (a.functor, len(a.args))
    if is_term_instance(a):
        cls = type(a)
        return (cls.__name__, len(term_field_names(a)))
    return _INDEX_VAR
```

### Gotchas from prior attempt

We implemented this exact change.  It showed no measurable wall-clock difference.
The function is not separately visible in cProfile because it's called from within
dispatch closures (the time is attributed to `dispatch`, not `_runtime_arg_key`).

The change is trivial and risk-free.  The only subtlety: `bool` is a subclass of
`int` in Python, so `type(True) is int` returns `False` — bools will correctly
fall through to the `isinstance(a, _INDEXABLE_TYPES)` check which includes
`bool`.  This is the desired behavior since `True` and `1` should have different
index keys in Prolog semantics (atoms vs integers).

Add type-identity fast checks for the two most common types:
```python
def _runtime_arg_key(a: Any) -> Any:
    t = type(a)
    if t is int or t is str:
        return a
    if isinstance(a, _INDEXABLE_TYPES):
        return a
    if isinstance(a, Compound):
        return (a.functor, len(a.args))
    if is_term_instance(a):
        cls = type(a)
        return (cls.__name__, len(term_field_names(a)))
    return _INDEX_VAR
```

## How to verify

```bash
# Before
python benchmarks/workloads.py
python benchmarks/microbench.py

# After
python benchmarks/workloads.py
python benchmarks/microbench.py

# Correctness
python -m pytest tests/test_groundness_dispatch.py -x -q
python -m pytest tests/ --ignore=tests/test_trealla_backend.py -x -q
```

Expected: Minor improvement.  May not be visible in wall-clock benchmarks.
Result values must not change.
