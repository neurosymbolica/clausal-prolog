# Profiling & Optimization Plan for Clausal

## Part A — Profiling Infrastructure (complete)

Benchmarks live in `benchmarks/`. Run them:

```bash
python benchmarks/workloads.py          # smoke-test all workloads
python -m benchmarks.run_cprofile       # cProfile → benchmarks/profiles/*.prof
python benchmarks/microbench.py         # ns-per-op for primitives
python benchmarks/run_pyspy.py          # SVG flamegraphs (needs py-spy)
```

---

## Part B — Optimization Work Items

### Overview & Dependency Graph

```
        ┌──────────────────────────────────────────────────────────┐
        │  INDEPENDENT — can all run in parallel with each other   │
        │                                                          │
        │   W1  CLP(FD) arithmetic fast path                      │
        │   W2  Query compilation cache                            │
        │   W3  Tabling key computation                            │
        │   W4  _ensure_term_imports elimination                   │
        └──────────────────────────────────────────────────────────┘
                                │
                                ▼
        ┌──────────────────────────────────────────────────────────┐
        │  DEPENDS ON W1 — must merge after W1 lands              │
        │                                                          │
        │   W5  Inline fd_gt/fd_ge delegation                     │
        └──────────────────────────────────────────────────────────┘

        ┌──────────────────────────────────────────────────────────┐
        │  INDEPENDENT — can run in parallel with everything       │
        │                                                          │
        │   W6  _head_list_unify_input fast path                  │
        │   W7  Compiler: omit mark/undo for ground-only clauses  │
        └──────────────────────────────────────────────────────────┘

        After all merge → run benchmarks/workloads.py for regression check
```

**Parallelism summary**: W1, W2, W3, W4, W6, W7 are all independent and can be done simultaneously.  W5 is a small follow-on that touches the same functions as W1.

---

### W1 — CLP(FD) arithmetic fast path for ground integers

**Impact**: fib −38%, nqueens −28% (single biggest win)

**Problem**: Every arithmetic comparison (`>`, `<`, `!=`, `<=`, `>=`, `==`) on ground integers goes through the full CLP(FD) dispatch chain:

```
fd_lt(l, r, trail):
    l = deref(l)                    # 20ns
    r = deref(r)                    # 20ns
    l = _resolve(l)                 # calls _ensure_term_imports() + isinstance(x, expr_types)
    r = _resolve(r)                 # same
    _any_real(l, r)                 # calls _is_real_arg(l) + _is_real_arg(r)
                                    #   each: deref + isinstance(float) + is_var + get_attr
    _both_ground(l, r)             # is_var×2 + _ensure_term_imports() + isinstance(l, 8-tuple)
    return l < r                    # ← the actual work: ~5ns
```

That is 12+ Python function calls to do one integer comparison.  In fib, each of the 121,392 `N > 1` comparisons costs ~9.2µs; in nqueens, each of the 450,066 `!=` comparisons costs ~4.5µs.

**Evidence** (from cProfile tottime):

| function | fib calls | fib self-time | nqueens calls | nqueens self-time |
|----------|-----------|---------------|---------------|-------------------|
| `fd_lt` | 121,392 | 0.087s | — | — |
| `fd_ne` | — | — | 450,066 | 0.319s |
| `_resolve` | 242,784 | 0.085s | 900,168 | 0.310s |
| `_is_real_arg` | 242,784 | 0.071s | 900,168 | 0.261s |
| `_both_ground` | 121,392 | 0.064s | 450,084 | 0.236s |
| `_any_real` | 121,392 | 0.034s | 450,084 | 0.123s |
| `_ensure_term_imports` | 364,176 | 0.019s | 1,350,252 | 0.066s |
| **total CLP overhead** | | **0.360s** | | **1.315s** |

**File**: `clausal/logic/clpfd.py`

**Change**: Add a 2-line fast path at the very top of each of the 6 comparison functions, **after** deref but **before** `_resolve`:

```python
def fd_lt(l, r, trail: Trail) -> bool:
    """Post X < Y.  Dispatches to CLP(R) when appropriate."""
    l = deref(l)
    r = deref(r)
    # ── fast path: ground integer comparison ──
    if type(l) is int and type(r) is int:
        return l < r
    # ── end fast path ──
    l = _resolve(l)
    r = _resolve(r)
    if _any_real(l, r):
        ...  # rest unchanged
```

Apply the same pattern to all six functions:

| Function | Line | Fast-path body |
|----------|------|----------------|
| `fd_eq` | 1095 | `return l == r` |
| `fd_ne` | 1147 | `return l != r` |
| `fd_lt` | 1166 | `return l < r` |
| `fd_le` | 1185 | `return l <= r` |
| `fd_gt` | 1204 | `return l < r` (note: fd_gt currently delegates to fd_lt with swapped args; after adding the fast path to fd_gt directly, it can short-circuit without calling fd_lt — see W5) |
| `fd_ge` | 1209 | `return l <= r` (same idea — see W5) |

**Why `type(x) is int` not `isinstance(x, int)`**: `bool` is a subclass of `int` in Python.  `isinstance(True, int)` is `True`, but we don't want `fd_lt(True, 3)` to hit the fast path (booleans are truth values, not arithmetic).  `type(True) is int` → `False`, correctly excluding bools.

**`fd_eq` special case**: `fd_eq` has extra logic for expression-tree linearisation (lines 1115–1134).  The fast path goes before all of that — for `type(l) is int and type(r) is int`, we know there are no expression trees to linearise:

```python
def fd_eq(l, r, trail: Trail) -> bool:
    l = deref(l)
    r = deref(r)
    if type(l) is int and type(r) is int:
        return l == r
    l = _resolve(l)
    r = _resolve(r)
    ...  # rest unchanged
```

**Extend fast path to `float`**: While we're at it, add float support since it's just as cheap:

```python
    if type(l) is int and type(r) is int:
        return l < r
    if type(l) is float or type(r) is float:
        if not (is_var(l) or is_var(r)):
            return float(l) < float(r)
```

Actually, **don't do the float extension** yet — keep it minimal to avoid accidentally changing semantics.  Float comparisons currently go through `clpr.real_lt` which may have different NaN handling.  Stick with the `int`-only fast path.

**Tests**: Run all existing tests — arithmetic semantics must not change:
```bash
pytest tests/ clausal/examples/ -q -x
```

Also run the benchmark to verify the speedup:
```bash
python benchmarks/workloads.py
```

---

### W2 — Cache compiled query dispatch functions

**Impact**: graph −64%, qsort −21%

**Problem**: Every call to `solve(goal, module)` — which is called by `__iter__` on every predicate instance — runs `_compile_as_query(goal, module)`.  This function:

1. Converts the goal to AST (`_term_to_goal`)
2. Collects vars (`_collect_vars`)
3. Compiles the goal's body to AST (`compile_body_trampoline`)
4. Builds a full function def (`_build_predicate_trampoline_funcdef`)
5. Runs `ast.fix_missing_locations` on the tree
6. Runs Python `compile()` + `exec()` to produce a callable
7. Returns the dispatch function

Steps 3–6 are the expensive part.  In the graph benchmark, 500 calls to `Path(1, Y, PATH)` repeat all of this identically — the compiled code is structurally the same because the goal is always `Path(arg0, arg1, arg2)`.  Only the specific Var objects change between calls, and those are injected via `extra_globals`.

**Evidence** (from cProfile cumtime):

| function | graph calls | graph cumtime | qsort calls | qsort cumtime |
|----------|-------------|---------------|-------------|---------------|
| `_compile_as_query` | 500 | 0.408s | 200 | 0.234s |
| `compile_predicate_trampoline` | 506 | 0.408s | 205 | 0.255s |
| `ast.fix_missing_locations` | 1065 | 0.224s | 457 | 0.143s |
| `functiondef_to_function` | 532 | 0.139s | 228 | 0.087s |

**File**: `clausal/logic/solve.py`

**Change**: Add a module-level LRU cache keyed on the structural identity of the goal.  The cache key must capture:
- The goal's type/functor (which predicate)
- Arity
- Which argument positions are ground vs. Var  (so `Path(1, Var(), Var())` and `Path(2, Var(), Var())` can share the same compiled code if the ground arg is in the same position)

Actually, a simpler and more effective key is: the **predicate class** + the **tuple of argument types** (using a sentinel for Var).  Since the compiled code references Vars by name through globals, the same compiled code works for any Var objects.

Add a cache dictionary at module level:

```python
# Module-level cache: (goal_class_or_functor, arg_type_key) → compiled dispatch fn + code object
_query_cache: dict[tuple, tuple] = {}
```

Modify `_compile_as_query` to:

1. Compute a cache key from the goal's structural identity
2. On cache hit: create a **new function** that shares the cached code object but has **fresh globals** with the current Var objects
3. On cache miss: compile as before, store the result

**Implementation sketch** (in `clausal/logic/solve.py`):

```python
_VAR_SENTINEL = object()

def _goal_cache_key(goal):
    """Structural key: predicate name + which positions are Var vs ground type."""
    from clausal.logic.predicate import PredicateMeta
    if isinstance(type(goal), PredicateMeta):
        cls = type(goal)
        fields = term_field_names(goal)
        arg_types = []
        for f in fields:
            v = getattr(goal, f)
            v = deref(v)
            arg_types.append(_VAR_SENTINEL if is_var(v) else type(v))
        return (cls, tuple(arg_types))
    if isinstance(goal, Compound):
        arg_types = []
        for a in goal.args:
            a = deref(a)
            arg_types.append(_VAR_SENTINEL if is_var(a) else type(a))
        return (goal.functor, len(goal.args), tuple(arg_types))
    return None  # not cacheable


_query_cache: dict = {}


def _compile_as_query(goal: Any, module: Module) -> Any:
    cache_key = _goal_cache_key(goal)

    if cache_key is not None and cache_key in _query_cache:
        cached_fn, cached_code = _query_cache[cache_key]
        # Build fresh globals with current Var objects
        goal_ast = _term_to_goal(goal)
        vars_in_goal = _collect_vars(goal_ast)
        new_globals = dict(cached_fn.__globals__)  # copy base globals
        new_globals.update({_var_python_name(v): v for v in vars_in_goal})
        # Create new function with same code but fresh globals
        import types
        fn = types.FunctionType(cached_code, new_globals, cached_fn.__name__)
        return fn

    # Cache miss — compile normally
    dispatch_fn = _compile_as_query_uncached(goal, module)

    if cache_key is not None:
        _query_cache[cache_key] = (dispatch_fn, dispatch_fn.__code__)

    return dispatch_fn
```

Move the current `_compile_as_query` body to `_compile_as_query_uncached`.

**Important correctness constraint**: The cache assumes the module's predicate definitions don't change between calls (i.e., no `assertz` / `retract` between iterations).  This is true for normal `.clausal` module usage.  Dynamic predicates (assertz/retract) should invalidate the cache — but for the first implementation, just don't cache if the module has any dynamic predicates, or clear the cache on assertz/retract.  A simpler approach: make the cache per-module (store it on the `Module` object) so that reloading a module naturally clears it.

**Edge cases to handle**:
- Goals that aren't simple predicate calls (And, Or, Not compound goals) — return `None` from `_goal_cache_key` so they're not cached.
- The `module.module_dict` must be part of the globals.  Since it's the same module between calls (the loop `for _ in Fib(25, F)` uses the same imported module), the cached function's base globals already include it.

**Tests**:
```bash
pytest tests/ clausal/examples/ -q -x
python benchmarks/workloads.py
```

---

### W3 — Tabling key computation optimisation

**Impact**: tabling benchmark −15%

**Problem**: `tabled_dispatch` (called 300K times, 0.261s self) computes `make_subgoal_key(args, trail)` on every call — even for cache hits where the table is already complete.  `make_subgoal_key` itself:
1. Creates a generator expression (object allocation overhead)
2. Calls `_normalize_for_key` per arg (function call overhead)
3. Each `_normalize_for_key` calls `deref` + `is_var` + `isinstance(term, (bool, int, float, str, bytes))` (5-type tuple)

**Evidence** (from cProfile, tabling benchmark):

| function | calls | self-time |
|----------|-------|-----------|
| `tabled_dispatch` | 300,000 | 0.261s |
| `make_subgoal_key` | 99,990 | 0.176s |
| `_normalize_for_key` | 199,980 | 0.056s |
| genexpr (line 169) | 299,970 | 0.052s |
| `freeze_args` | 50,010 | 0.037s |

**File**: `clausal/logic/tabling.py`

**Changes** (3 separate micro-optimisations in the same file):

**(a)** Replace the generator expression in `make_subgoal_key` with a list comprehension (avoids generator object allocation):

```python
# Before (line 169):
def make_subgoal_key(args, trail):
    return tuple(_normalize_for_key(a) for a in args)

# After:
def make_subgoal_key(args, trail):
    return tuple([_normalize_for_key(a) for a in args])
```

Yes, `tuple([...])` is faster than `tuple(genexpr)` in CPython because the list comprehension avoids the generator protocol overhead (send/StopIteration).

**(b)** Add a scalar fast path in `_normalize_for_key`:

```python
# Before (line 149):
def _normalize_for_key(term):
    term = deref(term)
    if is_var(term):
        return _VAR
    if term is None or isinstance(term, (bool, int, float, str, bytes)):
        return term
    ...

# After:
_SCALAR_TYPES = (bool, int, float, str, bytes)

def _normalize_for_key(term):
    term = deref(term)
    if type(term) is int:          # fast path for the most common case
        return term
    if is_var(term):
        return _VAR
    if term is None or isinstance(term, _SCALAR_TYPES):
        return term
    ...
```

The `type(term) is int` check is a single pointer comparison vs. `isinstance` which traverses a tuple of types.  For tabled Fibonacci where most args are plain ints, this skips the expensive isinstance.

Note: `_SCALAR_TYPES` is defined once at module level (not inside the function) to avoid re-creating the tuple each call.

**(c)** Same optimisation for `freeze_args` — replace genexpr with list comprehension:

```python
# Before (line 175):
def freeze_args(args, trail):
    from clausal.logic.solve import _deref_walk
    return tuple(_deref_walk(a) for a in args)

# After:
def freeze_args(args, trail):
    from clausal.logic.solve import _deref_walk
    return tuple([_deref_walk(a) for a in args])
```

**Tests**:
```bash
pytest tests/test_tabling.py tests/test_slg_termination.py tests/test_wfs.py -q
pytest tests/ clausal/examples/ -q -x
python benchmarks/workloads.py
```

---

### W4 — Eliminate `_ensure_term_imports` lazy-import overhead

**Impact**: nqueens −1.2%, fib −0.8% (also removes overhead from `_resolve` and `_both_ground`)

**Problem**: `_ensure_term_imports()` is called 1,350,252 times in nqueens (0.066s).  After the first call, it's a no-op (`if _Add is None:` → False), but each call still pays Python function-call overhead (~50ns).

**File**: `clausal/logic/clpfd.py`

**Change**: Replace the function call with an inline guard at each call site.  The pattern:

```python
# Before:
_ensure_term_imports()
if _Add is not None and isinstance(x, (_Add, _Sub, _Mult, _Negate)):
    ...

# After:
if _Add is None:
    _ensure_term_imports()
if isinstance(x, (_Add, _Sub, _Mult, _Negate)):
    ...
```

This way, after the first successful import, the `_Add is None` check is a single global-variable load + comparison (≈5ns), with no function call overhead.

**Call sites** to modify (search for `_ensure_term_imports()` in clpfd.py):
- `_resolve()` at line ~1071
- `_both_ground()` at line ~1087
- `fd_eq()` at line ~1115 (inside the expression-tree linearisation block)
- Any other call sites found by grepping

Note: keep the `_ensure_term_imports` function itself for the first-call path; just stop calling it unconditionally.

**Alternative** (if preferred): Move the imports to module load time.  The circular import concern (`clpfd` imports from `terms.py`) may be resolvable by importing at the bottom of the file.  But the inline-guard approach is safer and sufficient.

**Tests**:
```bash
pytest tests/ clausal/examples/ -q -x
python benchmarks/workloads.py
```

---

### W5 — Inline `fd_gt` / `fd_ge` delegation

**Impact**: fib −2% (eliminates one Python function call per `>` or `>=`)

**Depends on**: W1 (merge W1 first, then apply W5 on top)

**Problem**: `fd_gt(l, r, trail)` is a one-liner that delegates to `fd_lt(r, l, trail)`:

```python
def fd_gt(l, r, trail: Trail) -> bool:
    return fd_lt(r, l, trail)
```

This adds one extra Python frame per call.  After W1 adds the integer fast path to `fd_lt`, `fd_gt` would call `fd_lt` which then hits the fast path.  But the function-call overhead of entering `fd_gt` itself is still paid.

**File**: `clausal/logic/clpfd.py`

**Change**: Give `fd_gt` and `fd_ge` their own fast paths so they don't delegate for the common case:

```python
def fd_gt(l, r, trail: Trail) -> bool:
    """Post X > Y.  Dispatches to CLP(R) when appropriate."""
    l = deref(l)
    r = deref(r)
    if type(l) is int and type(r) is int:
        return l > r
    return fd_lt(r, l, trail)   # note: fd_lt will re-deref, which is fine


def fd_ge(l, r, trail: Trail) -> bool:
    """Post X >= Y.  Dispatches to CLP(R) when appropriate."""
    l = deref(l)
    r = deref(r)
    if type(l) is int and type(r) is int:
        return l >= r
    return fd_le(r, l, trail)
```

This is a 5-line change.  The redundant deref in the non-fast-path is fine — it's only paid when we actually need the full CLP machinery (rare).

**Tests**: Same as W1.

---

### W6 — `_head_list_unify_input` fast path for `[H|T]` patterns

**Impact**: nqueens −5.6%, qsort −8%

**Problem**: `_head_list_unify_input` is called 319K times in nqueens (0.398s self).  It handles all list-head patterns but the most common case is `[H, *T]` (one element + star rest).  The function does isinstance checks for SegList and list/str on every call.

**File**: `clausal/logic/compiler.py` (lines 217–265)

**Change**: Add a fast path at the top for the common case: `target` is already a plain list, `var_vals` has 1 element, `star_val` is not None, `after_vals` is empty.

```python
def _head_list_unify_input(target, var_vals, star_val, after_vals, trail):
    d = deref(target)

    # ── fast path: [H, *T] on a plain list ──
    if type(d) is list and star_val is not None and not after_vals:
        n = len(var_vals)
        if len(d) < n:
            return False
        for i in range(n):
            if not unify(var_vals[i], d[i], trail):
                return False
        return unify(star_val, d[n:], trail)
    # ── end fast path ──

    # ... existing code unchanged ...
```

Using `type(d) is list` avoids the `isinstance(d, SegList)` check and the `isinstance(d, (list, str))` check.  The `not after_vals` check is cheap (empty list is falsy).

**Correctness**: The fast path is semantically identical to the existing code for the specific case of `type(d) is list` + `after_vals == []`.  All other cases (SegList, str, after_vals, unbound Var) fall through to the existing logic.

**Tests**:
```bash
pytest tests/ clausal/examples/ -q -x
python benchmarks/workloads.py
```

---

### W7 — Compiler: omit `trail.mark()` / `trail.undo()` for ground-only clauses

**Impact**: fib −3%, nqueens −2%

**Problem**: The compiler wraps every clause in a try/finally with `trail.mark()` + `trail.undo()`, even when the clause cannot modify the trail (e.g., Fibonacci base cases `Fib(0, 0)` and `Fib(1, 1)` which are ground facts).  In fib: 1.485M marks for 485K invocations (3 clauses each), but only 635K undos are actually needed.

**File**: `clausal/logic/compiler.py`

**Where**: Inside `_build_predicate_trampoline_funcdef` (line 5266), in the loop that emits code for each clause (the section that generates the `try/finally` blocks around each clause arm).

**Change**: Before emitting the try/finally, analyse the clause:
- If the clause head is fully ground (all patterns are constants, no Var captures)
- AND the clause has no body goals that could modify the trail (no sub-predicate calls, no unify)
- THEN emit the match arm WITHOUT the try/finally wrapper

This analysis can be conservative: only omit the try/finally for clauses where `body == [BoolLiteral(True)]` (i.e., ground facts with no body) AND the head patterns contain no Var captures (all patterns are `MatchValue` or `MatchSingleton`, no `MatchAs` with a name).

To find where the try/finally is emitted, search in `_build_predicate_trampoline_funcdef` for `trail.mark()` or `_mark`:

```python
# The compiler generates something like:
#   _mark = trail.mark()
#   try:
#       match (deref(arg0), ...):
#           case [...]:
#               ...
#   finally:
#       trail.undo(_mark)
```

The key insight is: **if a clause is a ground fact** (no variables in head, body is `True`), then the only possible action inside the match arm is `yield (_tramp_parent, None)`.  No unification occurs, so no trail entries are made, and `trail.undo(_mark)` is a no-op.  Omitting it saves the `mark()` call, the try/finally setup, and the `undo()` call.

**Implementation**:

Add a helper function:

```python
def _clause_is_ground_fact(clause: Clause, arity: int) -> bool:
    """True if clause is a ground fact (no body, no head variables)."""
    from clausal.pythonic_ast import nodes as n
    # Body must be trivial (True or empty)
    if clause.body not in (True, [n.BoolLiteral(value=True)]):
        if clause.body != [True]:
            return False
    # Head must have no Var names — all args are constants
    head = clause.head
    if hasattr(head, 'args'):
        for arg in head.args:
            if isinstance(arg, n.LoadName):
                return False  # variable reference
            # Could recurse for nested terms, but ground facts are simple
    return True
```

Then in the clause loop, branch:
```python
if _clause_is_ground_fact(clause, arity):
    # Emit match arm directly, no try/finally
    all_stmts.append(ast.Match(subject=subject, cases=[case_arm]))
else:
    # Emit with try/finally as before
    ...
```

**Caution**: This is a compiler change — it affects the generated code for all predicates.  Be very conservative in what you classify as "ground fact".  If in doubt, leave the try/finally in place.

**Tests**:
```bash
pytest tests/ clausal/examples/ -q -x
python benchmarks/workloads.py
```

Also verify the generated code for a simple predicate with ground facts:
```python
from clausal.tools.visualize import predicate_to_source
# Inspect the compiled output for a predicate with ground base cases
```

---

## Part C — Verification Protocol

After all work items are merged:

1. **Full test suite**:
   ```bash
   pytest tests/ clausal/examples/ docs/ -q
   ```
   Expected: all previously-passing tests still pass.

2. **Benchmark regression check**:
   ```bash
   python benchmarks/workloads.py
   ```
   Compare against baseline (recorded before changes):

   | Workload | Baseline | Expected after |
   |----------|----------|----------------|
   | bench_fib | 0.90s | ~0.50s |
   | bench_nqueens | 1.44s | ~0.90s |
   | bench_qsort | 0.33s | ~0.13s |
   | bench_graph | 0.21s | ~0.08s |
   | bench_tabling | 0.81s | ~0.65s |

3. **Micro-benchmark check** (should not regress):
   ```bash
   python benchmarks/microbench.py
   ```

4. **cProfile re-run** to verify hotspot shifts:
   ```bash
   python -m benchmarks.run_cprofile
   ```
   The CLP functions (`_resolve`, `_is_real_arg`, `_both_ground`, `_any_real`) should drop out of the top-30 for fib and nqueens.

---

## Part D — What Sonnet's Analysis Got Right and Where It Needs Correction

**Correct findings**:
- #1 (CLP arithmetic overhead) — confirmed, this is the biggest single win
- #2 (query recompilation) — confirmed, the `_compile_as_query` path is extremely expensive
- #3 (_head_list_unify_input) — confirmed
- #4 (isinstance proliferation) — confirmed, but mostly a side-effect of #1
- #5-#6 (tabling dispatch/key) — confirmed
- #8 (_ensure_term_imports) — confirmed

**Correction — Sonnet's #10 (deref hoisting) is already implemented**:
The code at `compiler.py:5301–5306` already hoists deref into locals before the match arms:
```python
deref_names = [f"_d{i}" for i in range(arity)]
for i, arg in enumerate(arg_names):
    loop_stmts.append(_assign(deref_names[i], _call(_name("deref"), _name(arg))))
subject = ast.Tuple(elts=[_name(n) for n in deref_names], ctx=ast.Load())
```
This means the per-clause repeated `deref` issue described in `COMPILER_OPTIMIZATION.md` has already been fixed.  **Do not implement Sonnet's #10 — the work is done.**

**Correction — Sonnet's #9 (_resolve overhead) is subsumed by W1**:
Adding the `type(l) is int` fast path to the comparison functions means `_resolve` is never called for ground ints.  No separate fix is needed.

**Not included in this plan (diminishing returns)**:
- Moving `_head_list_unify_input` to a C extension (W6 adds a Python fast path which is simpler and captures most of the gain)
- StepGenerator object pooling (Sonnet's #9; 129ns per allocation is already quite fast due to the C extension; the gain is ~60ms on fib which is <3%)
- Moving `tabled_dispatch` to C (W3's Python-level fixes capture the easy wins; C is a larger effort for ~15% on a single benchmark)
