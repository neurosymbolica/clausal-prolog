# Move `_head_list_unify_input` and `_head_list_unify_output` to C

## Context

`_head_list_unify_input` and `_head_list_unify_output` are the runtime helpers
for destructuring and constructing lists in clause head patterns (`[H, *T]`,
`[A, B, C]`, `[H, *M, T]`, etc.).  They are called from every compiled clause
that has a list pattern in its head.

### Profile data (cProfile, single run)

| Function | Benchmark | Calls | tottime | cumtime |
|----------|-----------|-------|---------|---------|
| `_head_list_unify_input` | nqueens | 319,488 | 0.213s | 0.345s |
| `_head_list_unify_input` | qsort | 80,000 | 0.055s | 0.092s |
| `_head_list_unify_input` | graph | 10,000 | 0.005s | 0.009s |
| `_head_list_unify_output` | qsort | 38,000 | 0.039s | 0.086s |
| `_head_list_unify_output` | graph | 19,500 | 0.019s | 0.036s |

These functions account for ~0.35s of nqueens and ~0.18s of qsort under cProfile.
Python-only fast paths (type checks before isinstance) were attempted and showed
zero wall-clock improvement because the overhead is in the per-element `unify()`
C calls and list slicing, not in the Python dispatch logic.  Moving the entire
function to C eliminates Python frame creation, Python loop overhead, and
per-iteration attribute lookups.

## Gotchas from prior attempt (Python-only fast paths)

We tried adding Python-level fast paths (three `type(d) is list` branches
covering all combinations of star_val/after_vals).  Results:

1. **nqueens `_head_list_unify_input` showed exactly zero improvement.**  The
   319K nqueens calls already hit the EXISTING fast path 1 (`[H, *T]` — line 231).
   Our new fast paths 2 and 3 handled other patterns (`[A,B,C]` and `[H,*M,T]`)
   that nqueens doesn't use.  The benchmark that would have benefited most
   didn't even exercise the new code.

2. **`_head_list_unify_output` DID improve** under cProfile: cumtime dropped
   from 0.086s to 0.049s (43%) in qsort.  The fast path for "star is plain list,
   no after_vals" genuinely skips the SegList/Var isinstance cascade.  But this
   0.037s cProfile saving did not register in wall-clock because cProfile inflates
   Python-call overhead ~2x, making Python-level gains look bigger than they are.

3. **The bottleneck is the inner `unify()` C calls**, not the Python control
   flow around them.  Each fast path still calls `unify(var_vals[i], d[i], trail)`
   in a Python `for` loop — that's a Python→C→Python round-trip per element.
   Moving the whole function to C makes the per-element unify a direct C function
   call with no interpreter overhead.

4. **SegList handling is load-bearing.**  Don't skip it — some clausal programs
   produce SegList values from partial unification.  The `__walk__()` call
   converts a ground SegList to a plain list.  If `__walk__` returns a SegList
   (still partially unbound), the function correctly returns False.  The C version
   must handle this by calling back into Python for SegList operations, or by
   importing the SegList type and replicating the walk logic.

5. **String support**: Strings are treated as lists of single-char strings.
   `d[i]` on a string returns a 1-char string, and `d[n:]` returns a substring.
   The C code should handle `PyUnicode_Check` alongside `PyList_Check`.

## What to do

Add a new C extension module `clausal/logic/_list_unify.c` (or add functions to
the existing `_variables.c` module) that implements both functions in C.

### Current Python signatures

```python
# clausal/logic/compiler.py, line 217
def _head_list_unify_input(target, var_vals, star_val, after_vals, trail):
    """Destructure a list/string into head pattern variables.
    Returns True (match), False (fail), or None (defer — target is unbound Var).
    """

# clausal/logic/compiler.py, line 286 (after the above)
def _head_list_unify_output(target, var_vals, star_val, after_vals, trail):
    """Construct list from bound vars and unify with target.
    Called after body execution when target was an unbound Var.
    """
```

Arguments:
- `target`: the value to match against (already deref'd in caller context, but
  function calls `deref(target)` internally)
- `var_vals`: a Python `list` of Var objects (the `[H, ...]` elements before the star)
- `star_val`: a Var or `None` (the `*T` variable, or None if no star)
- `after_vals`: a Python `list` of Var objects (elements after the star, e.g., `[..., *M, T]`)
- `trail`: a `Trail` object (C type from `_variables.c`)

### C implementation approach

The C functions should:

1. **Call `deref`** on target (reuse `py_deref` or the internal C deref logic).
2. **Check if result is a `list`** (`PyList_Check`).  For lists:
   - Compare lengths against `len(var_vals) + len(after_vals)`.
   - Call `unify(var_vals[i], list[i], trail)` for each before-star element.
   - If star_val is not None, slice the list and unify with star_val.
   - Call `unify(after_vals[i], list[end-n+i], trail)` for each after-star element.
3. **Check if result is a `str`** — same indexing logic, but elements are
   single-char strings.
4. **Check for SegList** (`isinstance` check against `SegList` type, imported as
   a module-level reference).  Call `__walk__()` on it and retry.
5. **Check if result is an unbound Var** — return `Py_None` (the Python `None`).
6. **Otherwise** — return `Py_False`.

For `_head_list_unify_output`:
1. Call `deref(target)`.
2. If not an unbound Var, delegate to `_head_list_unify_input`.
3. Build a Python list from `[deref(v) for v in var_vals]`.
4. If star_val is not None, deref it:
   - If plain list: extend result.
   - If SegList: walk it, extend if ground, else build SegList.
   - If unbound Var: build SegList with VarSeg.
   - Otherwise: append it.
5. Extend with `[deref(v) for v in after_vals]`.
6. Call `unify(d, result, trail)`.

### Where the current Python code lives

Read these carefully before implementing:

- `clausal/logic/compiler.py` lines 217–276 (`_head_list_unify_input`)
- `clausal/logic/compiler.py` lines 286–365 (`_head_list_unify_output`)
- `clausal/logic/variables/_variables.c` — for the C `unify`, `deref`, `is_var`
  functions and the Trail/Var type definitions
- `clausal/logic/seglist.py` — for `SegList`, `ConcreteSeg`, `VarSeg` types

### Build integration

- Add a new Extension to `setup.py` (or add to `_variables.c`).
- In `clausal/logic/compiler.py`, replace the Python implementations with
  imports from the C module, keeping the Python versions as fallbacks if the C
  module is not available.

### Keeping the Python fallback

Keep the Python implementations renamed to `_head_list_unify_input_py` etc.
At module level:

```python
try:
    from clausal.logic._list_unify import (
        _head_list_unify_input,
        _head_list_unify_output,
    )
except ImportError:
    pass  # Python fallbacks defined above
```

## How to verify

```bash
# Before: record baseline
python benchmarks/workloads.py            # note all 5 timings
python -m benchmarks.run_cprofile 2>&1 | grep _head_list  # note per-function times

# After: rebuild C extension and compare
pip install -e . && python benchmarks/workloads.py
python -m benchmarks.run_cprofile 2>&1 | grep _head_list

# Correctness
python -m pytest tests/test_compiler.py::TestHeadListUnify -x -q
python -m pytest tests/test_string_list_unification.py tests/test_list_edge_cases.py -x -q
python -m pytest tests/ --ignore=tests/test_trealla_backend.py -x -q
```

Expected: nqueens drops by ~0.15–0.25s, qsort by ~0.05–0.10s.
Result values must not change: fib=75025, nqueens=92, qsort=20, graph=5000.
