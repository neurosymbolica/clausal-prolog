# Move tabling key computation to C

## Context

The tabling subsystem computes variant keys for memoised calls and freezes
answer tuples.  Three functions dominate the tabling benchmark:

| Function | Calls | tottime | cumtime |
|----------|-------|---------|---------|
| `tabled_dispatch` | 300,000 | 0.276s | 0.783s |
| `_unify_answer` | 49,980 | 0.083s | 0.130s |
| `make_subgoal_key` | 99,990 | 0.048s | 0.114s |
| `freeze_args` | 50,010 | 0.027s | 0.081s |
| `_normalize_for_key` | 199,980 | 0.046s | 0.067s |
| `_deref_walk` | 100,020 | 0.032s | 0.054s |

Python-only micro-optimizations (type checks, hoisting imports, genexpr vs
listcomp) were attempted and showed negligible wall-clock improvement because the
overhead is in recursive Python function calls and per-element deref/isinstance
chains.

## Gotchas from prior attempt (Python-only micro-opts)

We tried four Python-level micro-optimizations:

1. **`_normalize_for_key` adding `str` fast path alongside `int`**: showed zero
   improvement because tabling args in the benchmark are almost exclusively ints.
   The `str` path was never exercised.  The C version should still handle both
   types efficiently, but don't expect str-specific optimizations to show up in
   `bench_tabling`.

2. **`make_subgoal_key` switching list-comp to genexpr**: zero measurable
   difference.  For the typical 2-arg tabled predicate, the intermediate list
   is tiny.

3. **`freeze_args` hoisting the import**: The `from clausal.logic.solve import
   _deref_walk` inside the function body runs on every call (50K calls).  We
   cached it in a module-level global.  This showed a -0.009s cumtime
   improvement (11%) under cProfile but vanished in wall-clock.  **Beware the
   circular import**: `solve.py` imports from `tabling.py`, so `_deref_walk`
   cannot be imported at module level in `tabling.py`.  The C version sidesteps
   this because the C module can call `_deref_walk` as a C function directly.

4. **`_deref_walk` adding `type(term) is int` fast path**: zero improvement.
   The function is recursive and the overhead is Python frame creation per
   recursive call, not the isinstance check.  This is exactly the function that
   benefits most from C — it's a classic recursive tree walk where C eliminates
   interpreter overhead per node.

5. **`_unify_answer` is trivially short** (zip + unify loop) but it's called 50K
   times.  The Python loop overhead per call is small, but moving to C eliminates
   the per-iteration attribute lookups and Python frame.

**Key lesson**: These functions are called hundreds of thousands of times with
shallow per-call work.  The overhead is Python function call / frame creation /
loop iteration, not algorithmic.  Python-level rearrangement doesn't help because
the interpreter overhead is fixed.  Only moving to C eliminates it.

## What to do

Add C implementations of `_normalize_for_key`, `make_subgoal_key`, `freeze_args`,
`_deref_walk`, and `_unify_answer`.  These can go in a new C extension module
`clausal/logic/_tabling_core.c` or be added to `_variables.c`.

### Current Python code

**`_normalize_for_key`** — `clausal/logic/tabling.py` lines 152–169:
```python
def _normalize_for_key(term):
    """Deref term; replace unbound Vars with _VAR sentinel."""
    term = deref(term)
    if type(term) is int:
        return term
    if is_var(term):
        return _VAR
    if term is None or isinstance(term, _SCALAR_TYPES):
        return term
    if isinstance(term, list):
        return ("__list__",) + tuple(_normalize_for_key(e) for e in term)
    if isinstance(term, Compound):
        return (term.functor,) + tuple(_normalize_for_key(a) for a in term.args)
    if is_term_instance(term):
        return (type(term).__name__,) + tuple(
            _normalize_for_key(getattr(term, f)) for f in term_field_names(term)
        )
    return term
```

**`make_subgoal_key`** — `clausal/logic/tabling.py` lines 172–174:
```python
def make_subgoal_key(args, trail):
    return tuple([_normalize_for_key(a) for a in args])
```

**`freeze_args`** — `clausal/logic/tabling.py` lines 180–183:
```python
def freeze_args(args, trail):
    from clausal.logic.solve import _deref_walk
    return tuple([_deref_walk(a) for a in args])
```

**`_deref_walk`** — `clausal/logic/solve.py` lines 49–68:
```python
def _deref_walk(term):
    term = deref(term)
    if is_var(term):
        return term
    if term is None or isinstance(term, (bool, int, float, str, bytes, complex)):
        return term
    if isinstance(term, list):
        return [_deref_walk(e) for e in term]
    if isinstance(term, Compound):
        return Compound(term.functor, tuple(_deref_walk(a) for a in term.args))
    if is_term_instance(term):
        return type(term)(**{
            name: _deref_walk(getattr(term, name))
            for name in term_field_names(term)
        })
    return term
```

**`_unify_answer`** — `clausal/logic/tabling.py` lines 189–194:
```python
def _unify_answer(args, stored, trail):
    for a, s in zip(args, stored):
        if not unify(a, s, trail):
            return False
    return True
```

### C implementation notes

- `_normalize_for_key` and `_deref_walk` are recursive.  For typical Prolog terms
  the recursion depth is shallow (<20), so C stack recursion is fine.
- The `Compound` type is a Python class with `.functor` (str) and `.args` (tuple)
  attributes.  Access via `PyObject_GetAttrString`.
- `is_term_instance` checks if a value is a PredicateMeta dataclass.  You can
  pass the check function in as a module-level callable or use `PyObject_IsInstance`
  against a cached type.
- `_VAR` is a sentinel: `_VAR = object()` at module level in tabling.py.
- For `_unify_answer`, just loop through two tuples calling `unify()`.

### Types needed from other modules

- `Var`, `deref`, `is_var`, `unify`, `Trail` — from `_variables.c`
- `Compound` — from `clausal.terms` (Python class)
- `is_term_instance`, `term_field_names` — from `clausal.logic.predicate` (Python)

### Build integration

Add to `setup.py`:
```python
ext_tabling_core = Extension(
    "clausal.logic._tabling_core",
    sources=["clausal/logic/_tabling_core.c"],
    extra_compile_args=extra_compile_args,
)
```

In `tabling.py` and `solve.py`, import with Python fallback:
```python
try:
    from clausal.logic._tabling_core import _normalize_for_key, make_subgoal_key, ...
except ImportError:
    pass  # Python fallbacks above
```

## How to verify

```bash
# Before
python benchmarks/workloads.py
python -m benchmarks.run_cprofile 2>&1 | grep -E '(normalize|subgoal|freeze|deref_walk|unify_answer)'

# After
pip install -e . && python benchmarks/workloads.py
python -m benchmarks.run_cprofile 2>&1 | grep -E '(normalize|subgoal|freeze|deref_walk|unify_answer)'

# Correctness
python -m pytest tests/test_tabling.py -x -q
python -m pytest tests/ --ignore=tests/test_trealla_backend.py -x -q
```

Expected: bench_tabling drops by ~0.15–0.25s.
Result values must not change.
