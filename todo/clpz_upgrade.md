# Upgrade CLP(FD) to CLP(Z) semantics

## Context

Markus Triska (author of SWI-Prolog's `library(clpz)`) recommends CLP(Z) over
CLP(FD).  The key difference: CLP(Z) operates over **all integers** (Z), not
just finite bounded domains.  Variables default to the entire integer line
`(-inf, +inf)` rather than requiring explicit domain declarations.  This makes
the solver **sound** — it never silently misses solutions outside declared bounds.

Clausal's current CLP(FD) (`clausal/logic/clpfd.py`, 1706 lines) uses
`DEFAULT_MIN = -(2**63)` / `DEFAULT_MAX = 2**63` as a "big enough" approximation.
The Prolog dialect tool already maps it to `library(clpz)`.  The good news:
**most of the implementation is already compatible with infinite domains**.

### What works unchanged

The core engine — domain intersection, union, removal, truncation, all constraint
propagate() methods, the AC-3 worklist loop, and bounds-consistency propagation —
all use `domain_min()`, `domain_max()`, and comparison operators that work with
`±inf` sentinels.  Specifically, these functions are already compatible:

- `domain_from_range`, `domain_contains`, `domain_min`, `domain_max`,
  `domain_singleton`, `domain_intersection`, `domain_union`, `domain_remove`,
  `domain_remove_above`, `domain_remove_below`
- All constraint `propagate()` methods: `EqConstraint`, `NeConstraint`,
  `LtConstraint`, `LeConstraint`, `AllDiffConstraint`, `SumConstraint`,
  `ScalarProductConstraint`, `CircuitConstraint`
- `propagate()` worklist loop (line 1003)
- `_post_constraint()` (line 1030)
- `_narrow()`, `_narrow_if_changed()` (lines 186, 222)
- Arithmetic domain operations: `_domain_add`, `_domain_sub`, `_domain_mult`,
  `_domain_negate`
- `_linearise()` for expression compilation
- `reify_fd()` — three-valued reification

### What breaks

Only **4 functions** and **2 constants** need changes:

| What | Line | Problem |
|------|------|---------|
| `DEFAULT_MIN` / `DEFAULT_MAX` | 44–45 | Finite bounds `-(2^63)` / `2^63` |
| `domain_size(domain)` | 100–102 | `sum(hi - lo + 1)` — overflows/TypeError with inf |
| `domain_values(domain)` | 164–167 | `range(lo, hi+1)` — cannot enumerate infinite range |
| `label(vars, trail)` | 1381–1432 | Calls `domain_size()` at line 1412 and `domain_values()` at line 1427 |
| `ElementConstraint.propagate()` | 666 | Iterates `domain_values(idx_domain)` — but index is already bounded to `[1,n]` at line 654, so this is safe in practice |
| `_fd_hook()` real-to-int conversion | 1272–1273 | Uses `DEFAULT_MIN`/`DEFAULT_MAX` as fallback when real interval is `(-inf, inf)` |

## What to do

### Step 1 — Introduce infinity sentinels

Replace the bounded defaults with infinity sentinels.  Python `float('inf')` works
for comparisons with ints (`float('inf') > any_int` is `True`), but arithmetic
like `inf - inf` produces `nan`.  Two approaches:

**Option A: Use `float('inf')` directly**
```python
_NEG_INF = float('-inf')
_POS_INF = float('inf')
DEFAULT_MIN = _NEG_INF
DEFAULT_MAX = _POS_INF
```
Pros: `max(float('-inf'), 5) == 5` works, comparisons work.
Cons: `float('inf') - float('inf')` is `nan`; `domain_size` needs special handling.

**Option B: Use large sentinel integers**
```python
_NEG_INF = -(2**256)  # larger than any practical integer
_POS_INF = 2**256
```
Pros: All integer arithmetic works; domain_size returns a huge-but-finite number.
Cons: Not truly infinite; CLP(Z) purists would object.

**Recommendation: Option A** (`float` inf) — it's semantically correct and the
only functions that do arithmetic on bounds (`domain_size`, `domain_values`,
`label`) need changes anyway.

### Step 2 — Fix `domain_size`

```python
def domain_size(domain: Domain) -> int | float:
    """Return the number of integers in the domain, or float('inf') if unbounded."""
    total = 0
    for lo, hi in domain:
        if lo == _NEG_INF or hi == _POS_INF:
            return _POS_INF  # infinite domain
        total += hi - lo + 1
    return total
```

Callers that compare sizes (`label`'s first-fail heuristic) already work because
`float('inf') > any_int` is `True` — infinite domains are always "largest" and
picked last.

### Step 3 — Fix `domain_values`

```python
def domain_values(domain: Domain):
    """Yield all integer values in a finite domain.

    Raises ValueError if domain is unbounded — caller must bound first.
    """
    for lo, hi in domain:
        if lo == _NEG_INF or hi == _POS_INF:
            raise ValueError(
                "Cannot enumerate unbounded domain. "
                "Use in_fd/3 to declare bounds before labeling."
            )
        yield from range(lo, hi + 1)
```

### Step 4 — Fix `label`

The first-fail heuristic at line 1412 already works (Step 2 makes `domain_size`
return `inf` for unbounded domains, which sorts them last).

The enumeration at line 1427 needs a guard:

```python
    state = get_attr(best, FD_KEY)
    if state is None:
        yield None
        return

    # CLP(Z): if domain is unbounded, require explicit bounds
    if domain_size(state.domain) == _POS_INF:
        raise ValueError(
            f"Cannot label variable with unbounded domain "
            f"[{domain_min(state.domain)}, {domain_max(state.domain)}]. "
            f"Use in_fd/3 to declare bounds before labeling."
        )

    for val in domain_values(state.domain):
        ...
```

Alternatively, implement **enumerating from the center** for partially-bounded
domains (e.g., `X #> 0` gives domain `(1, +inf)` — enumerate 1, 2, 3, ...):

```python
def _enumerate_domain(domain):
    """Enumerate domain values, starting from the tightest bound."""
    lo = domain_min(domain)
    hi = domain_max(domain)
    if lo != _NEG_INF and hi != _POS_INF:
        yield from domain_values(domain)  # finite — enumerate normally
    elif lo != _NEG_INF:
        # Bounded below: enumerate upward
        val = lo
        while True:
            if domain_contains(domain, val):
                yield val
            val += 1
    elif hi != _POS_INF:
        # Bounded above: enumerate downward
        val = hi
        while True:
            if domain_contains(domain, val):
                yield val
            val -= 1
    else:
        # Fully unbounded: enumerate from 0 outward (0, 1, -1, 2, -2, ...)
        yield 0
        n = 1
        while True:
            if domain_contains(domain, n):
                yield n
            if domain_contains(domain, -n):
                yield -n
            n += 1
```

This is what SWI-Prolog's `library(clpz)` does for `labeling([],[X])` when X
has no declared bounds.  It's not guaranteed to terminate (infinite search space),
but that's the correct CLP(Z) semantics — the user is responsible for bounding
the search when termination is needed.

### Step 5 — Fix `_ensure_fd`

Line 178: change from bounded default to infinite default:

```python
def _ensure_fd(var: Var, trail: Trail) -> FDVar:
    state = get_attr(var, FD_KEY)
    if state is not None:
        return state
    state = FDVar(domain_from_range(_NEG_INF, _POS_INF))
    put_attr(var, FD_KEY, state, trail)
    return state
```

### Step 6 — Fix `_fd_hook` real-to-integer conversion

Lines 1272–1273:
```python
r_lo = math.ceil(real_state.lo) if real_state.lo != -math.inf else _NEG_INF
r_hi = math.floor(real_state.hi) if real_state.hi != math.inf else _POS_INF
```

This already handles infinite real bounds by mapping to `DEFAULT_MIN`/`DEFAULT_MAX`.
After Step 1, `_NEG_INF` and `_POS_INF` are `float('-inf')` and `float('inf')`,
so this becomes:
```python
r_lo = math.ceil(real_state.lo) if real_state.lo != -math.inf else _NEG_INF
r_hi = math.floor(real_state.hi) if real_state.hi != math.inf else _POS_INF
```
Same code, just different sentinel values.  **But** `math.ceil(float('-inf'))`
raises `OverflowError`.  Add a guard:
```python
r_lo = _NEG_INF if real_state.lo == -math.inf else math.ceil(real_state.lo)
r_hi = _POS_INF if real_state.hi == math.inf else math.floor(real_state.hi)
```

### Step 7 — Add `in_fd/3` predicate for explicit domain declaration

Currently domains are auto-created by `_ensure_fd`.  CLP(Z) still needs a way
to declare finite domains for labeling:

```python
def in_fd(var, lo, hi, trail):
    """Declare that var's domain is [lo, hi].

    Equivalent to SWI-Prolog's `X in Lo..Hi`.
    """
    var = deref(var)
    if not is_var(var):
        # Ground: just check containment
        return isinstance(var, int) and lo <= var <= hi
    state = _ensure_fd(var, trail)
    new_dom = domain_intersection(state.domain, domain_from_range(lo, hi))
    if not new_dom:
        return False
    return _narrow(var, new_dom, trail, deque()) if new_dom != state.domain else True
```

This may already exist — check if `in_domain` in `builtins/constraints.py` does
this.  If so, ensure it works with the new infinite defaults.

### Step 8 — Rename module references

Consider renaming `clpfd` → `clpz` in user-facing documentation and the module
name, while keeping `clpfd` as an alias.  The internal module can stay as
`clpfd.py` for now (rename is cosmetic).

## Gotchas

1. **`float('inf')` in tuple keys**: Domain tuples like `((-inf, inf),)` will
   contain floats mixed with ints.  This is fine for comparison but be careful
   with hashing — `hash(float('inf'))` works in Python.  Domain tuples used as
   dict keys (e.g., in caches) will still work.

2. **`domain_intersection` with two infinite domains**: `max(-inf, -inf) = -inf`,
   `min(inf, inf) = inf` — both work in Python.  `max(-inf, 5) = 5` — correct.

3. **Arithmetic with inf**: `5 + float('inf') = float('inf')` — correct for
   bounds computation.  `float('inf') - float('inf') = nan` — this must NEVER
   happen in domain operations (and it won't, because intersection always
   produces `lo <= hi`).

4. **`domain_size` returning float('inf')**: Code that does `if size < best_size`
   works because `float('inf') < 10` is `False`.  But code that does
   `if size == 0` also works because `float('inf') == 0` is `False`.

5. **Backward compatibility**: Existing clausal programs that use explicit
   `in_domain(X, 1, 100)` will continue to work.  Programs that rely on the
   implicit `-(2^63)..2^63` bounds will now get truly infinite domains.
   The only user-visible change is that `label/1` without explicit bounds will
   raise an error (or enumerate from center, depending on Step 4 choice).

6. **Performance**: Infinite domains are a single interval `((-inf, inf),)` —
   the cheapest possible representation.  Propagation with infinite domains is
   actually FASTER than with `-(2^63)..2^63` because there's less arithmetic.

## Tests to write

Create `tests/test_clpz.py`.  Follow the existing pattern in `tests/test_clpfd.py`:
imports from `clausal.logic.variables` (Var, Trail, deref, unify, is_var, get_attr)
and `clausal.logic.clpfd`.  Helper: `def fresh_trail(): return Trail()`.

### TestInfiniteDomains — core domain operations with inf

```python
class TestInfiniteDomains:
    def test_default_domain_is_infinite(self):
        """_ensure_fd on a fresh var creates (-inf, +inf) domain."""
        trail = fresh_trail()
        x = Var()
        state = _ensure_fd(x, trail)
        assert state.domain == ((_NEG_INF, _POS_INF),)

    def test_domain_size_infinite(self):
        """domain_size returns inf for unbounded domain."""
        d = domain_from_range(_NEG_INF, _POS_INF)
        assert domain_size(d) == _POS_INF

    def test_domain_size_half_bounded(self):
        """domain_size returns inf for (0, +inf)."""
        d = domain_from_range(0, _POS_INF)
        assert domain_size(d) == _POS_INF

    def test_domain_size_finite(self):
        """domain_size still works for finite domains."""
        d = domain_from_range(1, 10)
        assert domain_size(d) == 10

    def test_domain_contains_infinite(self):
        """Any integer is in (-inf, +inf)."""
        d = domain_from_range(_NEG_INF, _POS_INF)
        assert domain_contains(d, 0)
        assert domain_contains(d, 999999999)
        assert domain_contains(d, -999999999)

    def test_domain_min_infinite(self):
        d = domain_from_range(_NEG_INF, _POS_INF)
        assert domain_min(d) == _NEG_INF

    def test_domain_max_infinite(self):
        d = domain_from_range(_NEG_INF, _POS_INF)
        assert domain_max(d) == _POS_INF

    def test_domain_values_infinite_raises(self):
        """Cannot enumerate infinite domain."""
        d = domain_from_range(_NEG_INF, _POS_INF)
        with pytest.raises(ValueError, match="[Uu]nbounded"):
            list(domain_values(d))

    def test_domain_values_half_bounded_raises(self):
        """Cannot enumerate half-bounded domain."""
        d = domain_from_range(0, _POS_INF)
        with pytest.raises(ValueError, match="[Uu]nbounded"):
            list(domain_values(d))

    def test_domain_values_finite_works(self):
        """Finite domains still enumerate normally."""
        d = domain_from_range(1, 3)
        assert list(domain_values(d)) == [1, 2, 3]
```

### TestInfiniteIntersection — propagation with infinite domains

```python
class TestInfiniteIntersection:
    def test_intersect_infinite_with_finite(self):
        """(-inf, +inf) ∩ (1, 10) = (1, 10)."""
        d1 = domain_from_range(_NEG_INF, _POS_INF)
        d2 = domain_from_range(1, 10)
        result = domain_intersection(d1, d2)
        assert result == ((1, 10),)

    def test_intersect_infinite_with_infinite(self):
        """(-inf, +inf) ∩ (-inf, +inf) = (-inf, +inf)."""
        d = domain_from_range(_NEG_INF, _POS_INF)
        assert domain_intersection(d, d) == ((_NEG_INF, _POS_INF),)

    def test_intersect_half_bounded(self):
        """(-inf, 5) ∩ (0, +inf) = (0, 5)."""
        d1 = domain_from_range(_NEG_INF, 5)
        d2 = domain_from_range(0, _POS_INF)
        result = domain_intersection(d1, d2)
        assert result == ((0, 5),)

    def test_remove_from_infinite(self):
        """Remove 5 from (-inf, +inf) → (-inf,4) ∪ (6,+inf)."""
        d = domain_from_range(_NEG_INF, _POS_INF)
        result = domain_remove(d, 5)
        assert len(result) == 2
        assert result[0][1] == 4
        assert result[1][0] == 6

    def test_remove_above_infinite(self):
        """(-inf, +inf) with upper bound 10 → (-inf, 10)."""
        d = domain_from_range(_NEG_INF, _POS_INF)
        result = domain_remove_above(d, 10)
        assert result == ((_NEG_INF, 10),)

    def test_remove_below_infinite(self):
        """(-inf, +inf) with lower bound 0 → (0, +inf)."""
        d = domain_from_range(_NEG_INF, _POS_INF)
        result = domain_remove_below(d, 0)
        assert result == ((0, _POS_INF),)
```

### TestConstraintWithInfiniteDomains — constraints narrow from infinity

```python
class TestConstraintWithInfiniteDomains:
    def test_eq_narrows_to_singleton(self):
        """X == 5 on infinite domain → X = 5."""
        trail = fresh_trail()
        x = Var()
        assert fd_eq(x, 5, trail)
        assert deref(x) == 5

    def test_lt_narrows_upper(self):
        """X < 10 on infinite domain → domain becomes (-inf, 9)."""
        trail = fresh_trail()
        x = Var()
        assert fd_lt(x, 10, trail)
        state = get_attr(x, FD_KEY)
        assert state is not None
        assert domain_max(state.domain) == 9
        # Lower bound should still be infinite
        assert domain_min(state.domain) == _NEG_INF

    def test_gt_narrows_lower(self):
        """X > 0 on infinite domain → domain becomes (1, +inf)."""
        trail = fresh_trail()
        x = Var()
        assert fd_gt(x, 0, trail)
        state = get_attr(x, FD_KEY)
        assert state is not None
        assert domain_min(state.domain) == 1
        assert domain_max(state.domain) == _POS_INF

    def test_gt_and_lt_narrows_to_finite(self):
        """X > 0, X < 10 → domain (1, 9)."""
        trail = fresh_trail()
        x = Var()
        assert fd_gt(x, 0, trail)
        assert fd_lt(x, 10, trail)
        state = get_attr(x, FD_KEY)
        assert state is not None
        assert domain_min(state.domain) == 1
        assert domain_max(state.domain) == 9

    def test_ne_on_infinite(self):
        """X != 5 on infinite domain → (-inf,4) ∪ (6,+inf)."""
        trail = fresh_trail()
        x = Var()
        assert fd_ne(x, 5, trail)
        state = get_attr(x, FD_KEY)
        assert state is not None
        assert not domain_contains(state.domain, 5)
        assert domain_contains(state.domain, 4)
        assert domain_contains(state.domain, 6)

    def test_eq_chain_propagates(self):
        """X == Y, Y == 5 → X = 5 (propagation through infinite domains)."""
        trail = fresh_trail()
        x, y = Var(), Var()
        assert fd_eq(x, y, trail)
        assert fd_eq(y, 5, trail)
        assert deref(x) == 5

    def test_all_different_infinite(self):
        """all_different on infinite-domain vars succeeds (constraints posted)."""
        trail = fresh_trail()
        x, y, z = Var(), Var(), Var()
        assert all_different([x, y, z], trail)
        # Assigning x=1 should propagate: y!=1, z!=1
        assert fd_eq(x, 1, trail)
        state_y = get_attr(y, FD_KEY)
        assert state_y is not None
        assert not domain_contains(state_y.domain, 1)
```

### TestLabelInfinite — labeling edge cases

```python
class TestLabelInfinite:
    def test_label_bounded_from_constraints(self):
        """X > 0, X < 4 then label → [1, 2, 3]."""
        trail = fresh_trail()
        x = Var()
        assert fd_gt(x, 0, trail)
        assert fd_lt(x, 4, trail)
        results = []
        for _ in label([x], trail):
            results.append(deref(x))
        assert results == [1, 2, 3]

    def test_label_unbounded_errors_or_enumerates(self):
        """label on unbounded var either raises ValueError or enumerates."""
        trail = fresh_trail()
        x = Var()
        assert fd_gt(x, 0, trail)
        # x has domain (1, +inf) — cannot enumerate finitely
        # Implementation choice: raise error or enumerate from 1 upward.
        # Test whichever behavior is implemented:
        gen = label([x], trail)
        try:
            first = next(gen)
            # If it enumerates, first solution should be x=1
            assert deref(x) == 1
        except ValueError:
            pass  # Also acceptable: error on unbounded labeling

    def test_label_first_fail_prefers_finite(self):
        """First-fail heuristic picks finite-domain var over infinite one."""
        trail = fresh_trail()
        x, y = Var(), Var()
        assert in_domain(x, 1, 2, trail)  # finite: {1, 2}
        assert fd_gt(y, 0, trail)          # infinite: (1, +inf)
        # First-fail should pick x first (size 2 < inf)
        results = []
        gen = label([x, y], trail)
        # We just need to verify x is labeled first — check first solution
        next(gen)
        # x should be ground, y should still be unbound or ground
        assert not is_var(deref(x))
```

### TestBacktrackingWithInfinite — trail safety

```python
class TestBacktrackingWithInfinite:
    def test_undo_restores_infinite_domain(self):
        """After undo, var goes back to infinite domain."""
        trail = fresh_trail()
        x = Var()
        mark = trail.mark()
        assert fd_lt(x, 10, trail)
        state = get_attr(x, FD_KEY)
        assert domain_max(state.domain) == 9
        trail.undo(mark)
        state_after = get_attr(x, FD_KEY)
        # After undo, should be back to infinite (or no FD attr at all)
        if state_after is not None:
            assert domain_max(state_after.domain) == _POS_INF
        # Alternatively, FD attr was removed entirely (also valid)

    def test_undo_restores_after_eq(self):
        """X == 5 then undo → X is unbound again."""
        trail = fresh_trail()
        x = Var()
        mark = trail.mark()
        assert fd_eq(x, 5, trail)
        assert deref(x) == 5
        trail.undo(mark)
        assert is_var(deref(x))
```

### TestExistingBehaviorUnchanged — regression guard

```python
class TestExistingBehaviorUnchanged:
    def test_nqueens_still_finds_92(self):
        """N-queens(8) still finds exactly 92 solutions."""
        from benchmarks.workloads import bench_nqueens
        assert bench_nqueens() == 92

    def test_in_domain_still_works(self):
        """Explicit in_domain(X, 1, 5) still constrains correctly."""
        trail = fresh_trail()
        x = Var()
        assert in_domain(x, 1, 5, trail)
        state = get_attr(x, FD_KEY)
        assert state.domain == ((1, 5),)
        assert not unify(x, 7, trail)

    def test_sudoku_example_loads(self):
        """sudoku.clausal still loads and runs."""
        from clausal.testing import load_clausal_module, collect_tests, run_test
        mod = load_clausal_module("clausal/examples/sudoku.clausal")
        tests = collect_tests(mod)
        for desc in tests:
            result = run_test(mod, desc)
            assert result.passed, f"sudoku test {desc!r} failed"
```

## How to verify

```bash
# ALL existing tests must still pass
python -m pytest tests/ --ignore=tests/test_trealla_backend.py -x -q

# New CLP(Z) tests
python -m pytest tests/test_clpz.py -x -v

# CLP-specific existing tests
python -m pytest tests/ -k "clpfd or clp_fd or nqueens or sudoku" -x -q
python -m pytest tests/conformity/ -x -q

# Benchmarks — must not regress
python benchmarks/workloads.py
```

Expected: All existing tests pass.  Benchmarks unchanged (nqueens/fib always
declare finite domains via constraints, so they never hit infinite paths).
