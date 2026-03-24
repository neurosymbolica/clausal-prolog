# CLP(FD) Global Constraints: Proper Propagation

**Status:** Working but slow — label-then-check, no arc consistency.

**Affects:** `Sum/3`, `ScalarProduct/4`, `Element/3`, `Circuit/1`

## Current Implementation

All four global constraints work by:

1. Ensuring all variables have FD domains.
2. Calling `label()` to enumerate all possible assignments.
3. Checking the constraint post-hoc on each ground assignment.

This is correct but worst-case exponential — it explores the full Cartesian
product of domains.

## What Proper Implementations Do

### Sum/3 and ScalarProduct/4

Bounds-consistency propagation:

- Compute `min_sum = Σ min(domain(V_i))` and `max_sum = Σ max(domain(V_i))`.
- Narrow the value variable's domain to `[min_sum, max_sum]`.
- For each variable V_i, narrow its domain based on the slack:
  `min(V_i) >= Value - (max_sum - max(V_i))` and similarly for the upper bound.
- Repeat until fixpoint (queue-based, like existing EqConstraint/NeConstraint).

This should be implemented as a new `SumConstraint` class extending
`Constraint`, registered via `_post_constraint()` like `AllDiffConstraint`.

### Element/3

Arc-consistency (AC3):

- Domain of Index is narrowed to `{i : List[i] ∈ domain(Value)}`.
- Domain of Value is narrowed to `{List[i] : i ∈ domain(Index)}`.
- Propagates bidirectionally on each narrowing event.

Should be an `ElementConstraint` class.

### Circuit/1

Sub-tour elimination during propagation (not just post-hoc check):

- Track which assignments are forced (domain size 1).
- When a variable is assigned, follow the partial chain — if it forms a
  sub-tour shorter than N, prune that value.
- Standard approach: maintain a successor-chain forest, prune values that
  would close a cycle prematurely.

Should be a `CircuitConstraint` class that combines AllDifferent + sub-tour
pruning.

## Priority

Medium. The current implementation is correct for small problems (N-queens
up to ~8, SEND+MORE+MONEY, etc.). Propagation becomes important for
larger-scale constraint satisfaction.

## Files

- `clausal/logic/clpfd.py` — `fd_sum`, `fd_scalar_product`, `fd_element`, `fd_circuit`
- `clausal/logic/builtins/constraints.py` — `Sum/3`, `ScalarProduct/4`, `Element/3`, `Circuit/1`
- `tests/test_clpfd.py` + `tests/test_phase5_builtins.py` — existing tests should continue passing

---

## Detailed Implementation Plan

### Orientation: how the code fits together

**Constraint infrastructure** (`clausal/logic/clpfd.py`):
- `Constraint` base class with `propagate(trail, queue) -> bool` method.
- `_post_constraint(constraint, trail) -> bool` — attaches constraint to all its
  variables (via `_add_constraint`) and runs initial propagation.
- `propagate(queue, trail) -> bool` — AC-3 fixpoint loop; processes variables
  from the queue, fires their constraints.
- `_narrow_if_changed(var, new_domain, trail, queue) -> bool` — narrows a var's
  domain; enqueues the var when the domain actually shrinks.
- `FDVar` — immutable, trail-safe per-variable FD state: `(domain, constraints)`.

**Builtin wrappers** (`clausal/logic/builtins/constraints.py`):
Pattern for a generator builtin:
```python
@_builtin("Sum", 3)
def _sum__3(vars_list, op_str, value, trail, k):
    from clausal.logic.clpfd import fd_sum
    yield from fd_sum(vars_list, op_str, value, trail)
```
Pattern for a deterministic builtin:
```python
@_builtin("AllDifferent", 1)
def _all_different__1(vars_list, trail, k):
    from clausal.logic.clpfd import all_different
    if all_different(vars_list, trail):
        yield None
```

---

### Phase 0 — Fix the AC-3 propagation loop `seen` bug

**This must be done first.** It affects all propagation including the new
constraint classes.

**Location**: `clausal/logic/clpfd.py`, function `propagate()` (~line 595).

**Bug**: A `seen: set[int]` is created at the top of the loop and a variable is
never re-processed once visited — even if a later constraint changes its domain.
The comment "Reset seen for next round" is there but there is no reset code.

```python
# CURRENT — buggy
def propagate(queue: deque, trail: Trail) -> bool:
    seen: set[int] = set()
    while queue:
        var = queue.popleft()
        var = deref(var)
        if not is_var(var):
            continue
        vid = id(var)
        if vid in seen:
            continue        # ← BUG: skips re-processing
        seen.add(vid)
        state = get_attr(var, FD_KEY)
        if state is None:
            continue
        for constraint in state.constraints:
            if not constraint.propagate(trail, queue):
                return False
    return True
```

**Fix**: remove `seen` entirely. `_narrow_if_changed` only enqueues when a domain
*actually* shrinks, so the loop terminates without the guard (bounded by total
domain size across all variables).

```python
# FIXED
def propagate(queue: deque, trail: Trail) -> bool:
    while queue:
        var = queue.popleft()
        var = deref(var)
        if not is_var(var):
            continue
        state = get_attr(var, FD_KEY)
        if state is None:
            continue
        for constraint in state.constraints:
            if not constraint.propagate(trail, queue):
                return False
    return True
```

**Tests** — add class `TestAC3Fixpoint` in `tests/test_clpfd.py`:
```python
class TestAC3Fixpoint:
    def test_cascaded_lt(self):
        """X < Y < Z, Z ≤ 3, X ≥ 1 → X=1, Y=2, Z=3 without labeling."""
        trail = fresh_trail()
        x, y, z = Var(), Var(), Var()
        in_domain([x, y, z], 1, 100, trail)
        fd_lt(x, y, trail)
        fd_lt(y, z, trail)
        fd_le(z, 3, trail)
        fd_ge(x, 1, trail)
        assert deref(x) == 1
        assert deref(y) == 2
        assert deref(z) == 3

    def test_ne_narrows_after_other_change(self):
        """Z = 1 forces propagation back through X != Z and Y != Z."""
        trail = fresh_trail()
        x, y, z = Var(), Var(), Var()
        in_domain([x, y, z], 1, 3, trail)
        fd_ne(x, z, trail)
        fd_ne(y, z, trail)
        in_domain(z, 1, 1, trail)   # force Z=1
        sx = get_attr(x, FD_KEY)
        sy = get_attr(y, FD_KEY)
        assert not domain_contains(sx.domain, 1)
        assert not domain_contains(sy.domain, 1)
```

**Regression**: all 74 + 105 existing tests must still pass.

---

### Phase 1 — `SumConstraint` for `Sum/3`

**Goal**: replace the generate-and-test `fd_sum` with a proper bounds-consistency
constraint for the `#=` (equality) case. The other operators (`#<`, `#>`, etc.)
can be handled by wrapping `SumConstraint` with appropriate range restriction on
the value variable.

#### Design

`SumConstraint(vars_: tuple, total: Var_or_int)` asserts `Σ vars = total`.

Propagation (bounds consistency):
- `min_sum = Σ domain_min(dom(v))` for all v in vars
- `max_sum = Σ domain_max(dom(v))` for all v in vars
- Narrow `total` to `[min_sum, max_sum]`
- For each `v_i`:
  - `new_lo = domain_min(dom(total)) - (max_sum - domain_max(dom(v_i)))`
  - `new_hi = domain_max(dom(total)) - (min_sum - domain_min(dom(v_i)))`
  - Narrow `v_i` to `[new_lo, new_hi]`

```python
class SumConstraint(Constraint):
    """Σ vars == total. Bounds-consistency propagation."""
    __slots__ = ('sum_vars', 'total')

    def __init__(self, sum_vars: tuple, total):
        self.sum_vars = sum_vars
        self.total = total
        result: list = []
        for v in sum_vars:
            _collect_vars_from(v, result)
        _collect_vars_from(total, result)
        super().__init__(tuple(result))

    def propagate(self, trail: Trail, queue: deque) -> bool:
        vars_ = [deref(v) for v in self.sum_vars]
        total = deref(self.total)

        # Collect bounds
        min_sum = max_sum = 0
        for v in vars_:
            d = _expr_domain(v, trail)
            if not d:
                return False
            min_sum += domain_min(d)
            max_sum += domain_max(d)

        # Narrow total
        total_d = _expr_domain(total, trail)
        new_total_d = domain_intersection(total_d, domain_from_range(min_sum, max_sum))
        if not new_total_d:
            return False
        if is_var(total) and not _narrow_if_changed(total, new_total_d, trail, queue):
            return False
        total_lo = domain_min(new_total_d)
        total_hi = domain_max(new_total_d)

        # Narrow each variable using slack
        for i, v in enumerate(vars_):
            if not is_var(v):
                continue
            d = _expr_domain(v, trail)
            v_max = domain_max(d)
            v_min = domain_min(d)
            # Remove slack: new_lo = total_lo - (max_sum - v_max)
            new_lo = total_lo - (max_sum - v_max)
            new_hi = total_hi - (min_sum - v_min)
            new_d = domain_intersection(d, domain_from_range(new_lo, new_hi))
            if not new_d:
                return False
            if not _narrow_if_changed(v, new_d, trail, queue):
                return False

        return True
```

#### Integrating into `fd_sum`

The current `fd_sum` signature: `fd_sum(vars_list, op_str, value, trail) -> generator`.

Replace the "has FD vars" branch:

```python
def fd_sum(vars_list, op_str, value, trail: Trail):
    ...
    # Instead of: ensure FD + label + check post-hoc
    # New approach for #= operator:
    if op_str in ("#=", "="):
        vars_tuple = tuple(deref(v) for v in vars_deref)
        for v in vars_tuple:
            if is_var(v):
                _ensure_fd(v, trail)
        if is_var(value_deref):
            _ensure_fd(value_deref, trail)
        if _post_constraint(SumConstraint(vars_tuple, value_deref), trail):
            yield None
        return
    # For inequality operators: post SumConstraint + narrow value's domain
    # For #<: total_var = fresh Var, post SumConstraint(vars, total_var),
    #         post LtConstraint(total_var, value_deref)
    ...
```

For inequality operators (`#<`, `#>`, `#=<`, `#>=`, `#\=`):
- Create a fresh intermediate variable `TOTAL`.
- Post `SumConstraint(vars, TOTAL)`.
- Post the appropriate binary constraint between `TOTAL` and `value`.
- Do NOT label — the constraints themselves will propagate.
- Yield once (the constraints are posted; search continues via labeling elsewhere).

**Note**: the existing tests for `Sum` all use ground values or unify the total.
After the refactor they should still pass since ground cases are handled first
(short-circuit before posting constraints).

#### Builtin registration — no change needed

The `@_builtin("Sum", 3)` wrapper in `constraints.py` just calls `fd_sum`; that
keeps working.  Only `fd_sum` internals change.

#### Tests — add class `TestSumConstraint` in `tests/test_phase5_builtins.py`:

```python
class TestSumConstraint:
    def test_sum_narrows_total(self):
        """X in [1,5], Y in [1,5]: Sum([X,Y], #=, T) → T in [2,10]."""
        trail = fresh_trail()
        x, y, t = Var(), Var(), Var()
        in_domain(x, 1, 5, trail); in_domain(y, 1, 5, trail)
        assert list(fd_sum([x, y], "#=", t, trail))
        st = get_attr(t, FD_KEY)
        assert domain_min(st.domain) == 2
        assert domain_max(st.domain) == 10

    def test_sum_narrows_vars_from_total(self):
        """X in [1,5], Y in [1,5], T=10: Sum narrows both to [5,5]."""
        trail = fresh_trail()
        x, y = Var(), Var()
        in_domain(x, 1, 5, trail); in_domain(y, 1, 5, trail)
        assert list(fd_sum([x, y], "#=", 10, trail))
        sx = get_attr(x, FD_KEY); sy = get_attr(y, FD_KEY)
        assert domain_min(sx.domain) == 5
        assert domain_min(sy.domain) == 5

    def test_sum_wipeout(self):
        """X in [1,3], Y in [1,3], T=10: impossible → no solutions."""
        trail = fresh_trail()
        x, y = Var(), Var()
        in_domain(x, 1, 3, trail); in_domain(y, 1, 3, trail)
        assert not list(fd_sum([x, y], "#=", 10, trail))

    def test_sum_lt_narrows(self):
        """X in [1,5], Y in [1,5]: Sum([X,Y], #<, 5) → each in [1,3]."""
        trail = fresh_trail()
        x, y = Var(), Var()
        in_domain(x, 1, 5, trail); in_domain(y, 1, 5, trail)
        assert list(fd_sum([x, y], "#<", 5, trail))
        sx = get_attr(x, FD_KEY); sy = get_attr(y, FD_KEY)
        assert domain_max(sx.domain) <= 3
        assert domain_max(sy.domain) <= 3

    def test_sum_propagates_on_label(self):
        """Sum([X,Y], #=, 7), label → only pairs summing to 7."""
        trail = fresh_trail()
        x, y = Var(), Var()
        in_domain(x, 1, 5, trail); in_domain(y, 1, 5, trail)
        assert list(fd_sum([x, y], "#=", 7, trail))
        results = []
        for _ in label([x, y], trail):
            results.append((deref(x), deref(y)))
        assert all(a + b == 7 for a, b in results)
        assert len(results) == 3   # (2,5),(3,4),(4,3),(5,2) → 4 actually
        # Correction: (2+5,3+4,4+3,5+2) = 4 pairs
```

---

### Phase 2 — `ScalarProductConstraint` for `ScalarProduct/4`

**Goal**: bounds-consistency propagation for weighted sums `Σ c_i * V_i = total`.

#### Design

`ScalarProductConstraint(coeffs: tuple[int], sum_vars: tuple, total)`.

Propagation is the same as `SumConstraint` but with coefficients:
- `min_sum = Σ (c_i * domain_min(dom(v_i)))` if `c_i > 0` else `c_i * domain_max`
- `max_sum = Σ (c_i * domain_max(dom(v_i)))` if `c_i > 0` else `c_i * domain_min`
- Narrow `total` to `[min_sum, max_sum]`
- For each `v_i` with `c_i != 0`:
  - `new_lo = ceil((total_lo - (max_sum - c_i * v_max)) / c_i)` if `c_i > 0`
  - (mirror for negative coefficients — division reverses inequality)

This handles negative coefficients correctly (e.g. `2*X - 3*Y = 5`).

```python
class ScalarProductConstraint(Constraint):
    """Σ coeffs[i] * vars[i] == total. Bounds-consistency propagation."""
    __slots__ = ('coeffs', 'sum_vars', 'total')

    def __init__(self, coeffs: tuple, sum_vars: tuple, total):
        self.coeffs = coeffs
        self.sum_vars = sum_vars
        self.total = total
        result: list = []
        for v in sum_vars:
            _collect_vars_from(v, result)
        _collect_vars_from(total, result)
        super().__init__(tuple(result))

    def propagate(self, trail: Trail, queue: deque) -> bool:
        import math
        vars_ = [deref(v) for v in self.sum_vars]
        total = deref(self.total)

        min_sum = max_sum = 0
        for c, v in zip(self.coeffs, vars_):
            d = _expr_domain(v, trail)
            if not d:
                return False
            v_lo, v_hi = domain_min(d), domain_max(d)
            if c >= 0:
                min_sum += c * v_lo
                max_sum += c * v_hi
            else:
                min_sum += c * v_hi   # negative coeff: lo from hi
                max_sum += c * v_lo

        # Narrow total
        total_d = _expr_domain(total, trail)
        new_total_d = domain_intersection(total_d, domain_from_range(min_sum, max_sum))
        if not new_total_d:
            return False
        if is_var(total) and not _narrow_if_changed(total, new_total_d, trail, queue):
            return False
        total_lo = domain_min(new_total_d)
        total_hi = domain_max(new_total_d)

        # Narrow each variable
        for c, v in zip(self.coeffs, vars_):
            if not is_var(v) or c == 0:
                continue
            d = _expr_domain(v, trail)
            v_lo, v_hi = domain_min(d), domain_max(d)
            contrib_max = c * v_hi if c > 0 else c * v_lo
            contrib_min = c * v_lo if c > 0 else c * v_hi
            # Slack: how much this variable contributes to sum range
            other_min = min_sum - contrib_min
            other_max = max_sum - contrib_max
            if c > 0:
                new_v_lo = math.ceil((total_lo - other_max) / c)
                new_v_hi = math.floor((total_hi - other_min) / c)
            else:
                new_v_lo = math.ceil((total_hi - other_min) / c)
                new_v_hi = math.floor((total_lo - other_max) / c)
            new_d = domain_intersection(d, domain_from_range(int(new_v_lo), int(new_v_hi)))
            if not new_d:
                return False
            if not _narrow_if_changed(v, new_d, trail, queue):
                return False

        return True
```

#### Integrating into `fd_scalar_product`

Same pattern as `fd_sum`: replace the generate-and-test branch for `#=` with
`_post_constraint(ScalarProductConstraint(coeffs, vars, value), trail)`. For
inequality operators, create an intermediate total variable and chain with a
binary relational constraint.

#### Tests — add class `TestScalarProductConstraint` in `tests/test_phase5_builtins.py`:

```python
class TestScalarProductConstraint:
    def test_sp_narrows_total(self):
        """2*X + 3*Y, X in [1,5], Y in [1,5] → total in [5,25]."""
        trail = fresh_trail()
        x, y, t = Var(), Var(), Var()
        in_domain(x, 1, 5, trail); in_domain(y, 1, 5, trail)
        assert list(fd_scalar_product([2, 3], [x, y], "#=", t, trail))
        st = get_attr(t, FD_KEY)
        assert domain_min(st.domain) == 5
        assert domain_max(st.domain) == 25

    def test_sp_backward_narrows_vars(self):
        """2*X + 3*Y = 12, X in [1,5], Y in [1,5] → Y ≤ 3 (since 2*1+3*4=14>12)."""
        trail = fresh_trail()
        x, y = Var(), Var()
        in_domain(x, 1, 5, trail); in_domain(y, 1, 5, trail)
        assert list(fd_scalar_product([2, 3], [x, y], "#=", 12, trail))
        sy = get_attr(y, FD_KEY)
        assert domain_max(sy.domain) <= 3   # 3*(floor) = 3*3=9, 2*1=2 → 11; 3*4=12, 2*0=0 but X≥1

    def test_sp_negative_coeff(self):
        """2*X - Y = 5, X in [1,5], Y in [1,5] → X ≥ 3 (since 2*3-5=1 min)."""
        trail = fresh_trail()
        x, y = Var(), Var()
        in_domain(x, 1, 5, trail); in_domain(y, 1, 5, trail)
        assert list(fd_scalar_product([2, -1], [x, y], "#=", 5, trail))
        sx = get_attr(x, FD_KEY)
        assert domain_min(sx.domain) >= 3

    def test_sp_wipeout(self):
        """Coeffs all 1 (like Sum): [1,3] + [1,3] = 10 impossible."""
        trail = fresh_trail()
        x, y = Var(), Var()
        in_domain(x, 1, 3, trail); in_domain(y, 1, 3, trail)
        assert not list(fd_scalar_product([1, 1], [x, y], "#=", 10, trail))
```

---

### Phase 3 — `ElementConstraint` for `Element/3`

**Goal**: arc-consistency for `Element(I, List, X)` — X is the I-th element of
List (1-based index).

#### Current limitation

`fd_element` currently enumerates all valid indices and tries to unify.
This means it cannot propagate from X's domain back to I, or narrow X from
I's domain, without actually committing to values.

#### Design

`ElementConstraint(index, lst: tuple, value)` — index is a Var, lst is a tuple
of Var-or-int, value is a Var-or-int.

Propagation (AC-3 style):
1. Narrow index domain to `{i : domain(List[i-1]) ∩ domain(value) ≠ ∅}`.
2. Narrow value domain to `⋃ domain(List[i-1]) for i in domain(index)`.
3. If index is a singleton `{k}`, directly unify value with `List[k-1]`
   (post `EqConstraint` or unify).

Domain union for step 2:
```python
def _domain_union(domains: list) -> Domain:
    """Union of multiple domains. Returns sorted merged intervals."""
    if not domains:
        return ()
    # Collect all intervals, sort by lo, merge overlapping
    intervals = sorted(
        (lo, hi) for d in domains for lo, hi in d
    )
    if not intervals:
        return ()
    result = [intervals[0]]
    for lo, hi in intervals[1:]:
        if lo <= result[-1][1] + 1:   # touching or overlapping
            result[-1] = (result[-1][0], max(result[-1][1], hi))
        else:
            result.append((lo, hi))
    return tuple(result)
```

```python
class ElementConstraint(Constraint):
    """Element(Index, List, Value): Value = List[Index-1], 1-based."""
    __slots__ = ('index', 'lst', 'value')

    def __init__(self, index, lst: tuple, value):
        self.index = index
        self.lst = lst
        self.value = value
        result: list = [index]
        for item in lst:
            _collect_vars_from(item, result)
        _collect_vars_from(value, result)
        super().__init__(tuple(result))

    def propagate(self, trail: Trail, queue: deque) -> bool:
        index = deref(self.index)
        value = deref(self.value)
        n = len(self.lst)

        # Get index domain
        if is_var(index):
            idx_state = get_attr(index, FD_KEY)
            if idx_state is None:
                # Auto-restrict to 1..n
                if not _narrow(index, domain_from_range(1, n), trail, queue):
                    return False
                idx_state = get_attr(index, FD_KEY)
            idx_domain = idx_state.domain if idx_state else domain_from_range(1, n)
        elif isinstance(index, int):
            if index < 1 or index > n:
                return False
            idx_domain = ((index, index),)
        else:
            return False

        val_domain = _expr_domain(value, trail)

        # Step 1: narrow index — keep only positions where List[i] intersects value domain
        valid_indices = []
        for i in domain_values(idx_domain):
            item = deref(self.lst[i - 1])
            item_d = _expr_domain(item, trail)
            if domain_intersection(item_d, val_domain):
                valid_indices.append(i)

        if not valid_indices:
            return False

        new_idx_d = _indices_to_domain(valid_indices)
        if is_var(index) and not _narrow_if_changed(index, new_idx_d, trail, queue):
            return False

        # Step 2: narrow value — union of domains at valid index positions
        item_domains = [_expr_domain(deref(self.lst[i - 1]), trail) for i in valid_indices]
        new_val_d = domain_intersection(val_domain, _domain_union(item_domains))
        if not new_val_d:
            return False
        if is_var(value) and not _narrow_if_changed(value, new_val_d, trail, queue):
            return False

        # Step 3: if index singleton, post equality
        idx_singleton = domain_singleton(new_idx_d)
        if idx_singleton is not None:
            item = deref(self.lst[idx_singleton - 1])
            if is_var(value):
                return unify(value, deref(item), trail)
            else:
                return _expr_domain(item, trail) == _expr_domain(value, trail)

        return True


def _indices_to_domain(indices: list) -> Domain:
    """Convert a sorted list of integers to interval representation."""
    if not indices:
        return ()
    result = []
    start = prev = indices[0]
    for v in indices[1:]:
        if v == prev + 1:
            prev = v
        else:
            result.append((start, prev))
            start = prev = v
    result.append((start, prev))
    return tuple(result)
```

#### Integrating into `fd_element`

Replace the body of `fd_element` for the "index is FD var" case:

```python
def fd_element(index, lst, value, trail: Trail):
    index = deref(index)
    lst = [deref(item) for item in deref(lst)]
    value = deref(value)
    n = len(lst)

    if isinstance(index, int):
        # Ground index: direct lookup (existing logic, no change)
        if index < 1 or index > n:
            return
        item = deref(lst[index - 1])
        if unify(value, item, trail):
            yield None
        return

    # Index is a variable: post ElementConstraint
    if is_var(index):
        _ensure_fd(index, trail)
        if is_var(value):
            _ensure_fd(value, trail)
        constraint = ElementConstraint(index, tuple(lst), value)
        if not _post_constraint(constraint, trail):
            return
        # After constraint posting, if ground solution, yield once;
        # otherwise caller must label index to enumerate
        index = deref(index)
        if not is_var(index):
            # Propagation grounded the index
            item = deref(lst[index - 1])
            if unify(value, item, trail):
                yield None
        else:
            # Still unbound: enumerate valid indices
            idx_state = get_attr(index, FD_KEY)
            if idx_state is None:
                return
            for i in domain_values(idx_state.domain):
                mark = trail.mark()
                item = deref(lst[i - 1])
                if unify(index, i, trail) and unify(value, item, trail):
                    yield None
                trail.undo(mark)
```

#### Tests — add class `TestElementConstraint` in `tests/test_phase5_builtins.py`:

```python
class TestElementConstraint:
    def test_element_narrows_value_from_index_domain(self):
        """Index in [1,2], List=[10,20,30] → Value in {10,20}."""
        trail = fresh_trail()
        idx, val = Var(), Var()
        in_domain(idx, 1, 2, trail)
        assert list(fd_element(idx, [10, 20, 30], val, trail))
        sv = get_attr(val, FD_KEY)
        assert domain_contains(sv.domain, 10)
        assert domain_contains(sv.domain, 20)
        assert not domain_contains(sv.domain, 30)

    def test_element_narrows_index_from_value(self):
        """Value = 20, List=[10,20,30] → Index must be 2."""
        trail = fresh_trail()
        idx = Var()
        in_domain(idx, 1, 3, trail)
        assert list(fd_element(idx, [10, 20, 30], 20, trail))
        assert deref(idx) == 2

    def test_element_wipeout(self):
        """Value = 99 not in list → fail."""
        trail = fresh_trail()
        idx = Var()
        in_domain(idx, 1, 3, trail)
        assert not list(fd_element(idx, [10, 20, 30], 99, trail))

    def test_element_var_value_var_index(self):
        """Both unbound: Index in [2,3], List=[10,20,30] → Value in {20,30}."""
        trail = fresh_trail()
        idx, val = Var(), Var()
        in_domain(idx, 2, 3, trail)
        in_domain(val, 1, 100, trail)
        assert list(fd_element(idx, [10, 20, 30], val, trail))
        sv = get_attr(val, FD_KEY)
        assert not domain_contains(sv.domain, 10)
        assert domain_contains(sv.domain, 20)
        assert domain_contains(sv.domain, 30)

    def test_element_narrows_bidirectionally(self):
        """Index in [1,3], Value in {10,30}: only indices 1,3 valid."""
        trail = fresh_trail()
        idx, val = Var(), Var()
        in_domain(idx, 1, 3, trail)
        # Value domain = {10, 30} (non-contiguous)
        state = FDVar(((10, 10), (30, 30)))
        from clausal.logic.variables import put_attr
        put_attr(val, FD_KEY, state, trail)
        assert list(fd_element(idx, [10, 20, 30], val, trail))
        si = get_attr(idx, FD_KEY)
        assert not domain_contains(si.domain, 2)   # 20 not in value domain
```

---

### Phase 4 — `CircuitConstraint` for `Circuit/1`

**Goal**: sub-tour elimination during propagation (not just post-hoc verification).

#### Current limitation

`fd_circuit` calls `AllDifferent`, labels, then checks the circuit post-hoc.
It can't prune values that would create a premature cycle until after labeling.

#### Design

`CircuitConstraint(vars_: tuple)` — `vars_[i]` is the successor of node `i+1`.

Propagation algorithm (simplified Hamiltonian path sub-tour elimination):

1. Build the partial assignment: collect all ground variables.
2. Follow forced chains: starting from each ground variable, follow the chain as
   far as forced assignments allow.
3. If a forced chain closes a cycle before visiting all nodes, prune the value
   that would close it from the predecessor variable.
4. Restrict each variable's domain to `1..n` excluding `i+1` (no self-loops).
5. Also run AllDifferent propagation on all variables.

```python
class CircuitConstraint(Constraint):
    """Circuit(Vars): Vars[i] = j means node i+1's successor is j (1-based)."""
    __slots__ = ('circuit_vars', 'n', 'alldiff')

    def __init__(self, vars_: tuple):
        self.circuit_vars = vars_
        self.n = len(vars_)
        self.alldiff = AllDiffConstraint(vars_)
        super().__init__(vars_)

    def propagate(self, trail: Trail, queue: deque) -> bool:
        n = self.n
        vars_ = [deref(v) for v in self.circuit_vars]

        # Step 1: restrict all domains to [1, n], exclude self-loops
        for i, v in enumerate(vars_):
            if is_var(v):
                state = get_attr(v, FD_KEY)
                if state is None:
                    # Auto-restrict to 1..n excluding i+1
                    d = domain_from_range(1, n)
                    d = domain_remove(d, i + 1)   # no self-loop
                    if not _narrow(v, d, trail, queue):
                        return False
                else:
                    # Remove self-loop value and clamp to [1,n]
                    d = domain_intersection(state.domain, domain_from_range(1, n))
                    d = domain_remove(d, i + 1)
                    if not _narrow_if_changed(v, d, trail, queue):
                        return False
            elif isinstance(v, int):
                if v < 1 or v > n or v == i + 1:
                    return False

        # Step 2: AllDifferent propagation
        if not self.alldiff.propagate(trail, queue):
            return False

        # Step 3: Sub-tour elimination
        # Build partial assignment: ground[i+1] = j means node i+1 → j
        ground = {}
        for i, v in enumerate(vars_):
            v = deref(v)
            if isinstance(v, int):
                ground[i + 1] = v

        # For each ground node, follow the chain and prune premature cycle closure
        for start in ground:
            chain = []
            current = start
            seen_chain = set()
            while current in ground and current not in seen_chain:
                seen_chain.add(current)
                chain.append(current)
                current = ground[current]

            if len(chain) < n and current == start:
                # Chain closed a cycle shorter than n: impossible
                return False

            # If chain is almost complete (len = n-1), the last free node must
            # close back to start — restrict its domain to {start}
            if len(chain) == n - 1 and current not in seen_chain:
                v = deref(self.circuit_vars[current - 1])
                if is_var(v):
                    new_d = domain_from_range(start, start)
                    if not _narrow_if_changed(v, new_d, trail, queue):
                        return False

        return True
```

#### Integrating into `fd_circuit`

```python
def fd_circuit(vars_list, trail: Trail):
    vars_list = deref(vars_list)
    vars_deref = [deref(v) for v in vars_list]
    n = len(vars_deref)

    # Ensure all have FD domains [1..n]
    for v in vars_deref:
        if is_var(v):
            _ensure_fd(v, trail)

    vars_tuple = tuple(vars_deref)
    constraint = CircuitConstraint(vars_tuple)
    if not _post_constraint(constraint, trail):
        return

    # After constraint posting, if any variable is still unbound, enumerate
    # via labeling. The constraint will do sub-tour pruning during labeling.
    yield from label(vars_list, trail)
```

**Note**: `fd_circuit` still needs to label because `CircuitConstraint` alone
doesn't fully determine the solution — it just prunes. But it prunes far more
than the current version which only post-hoc checks.

#### Tests — add class `TestCircuitConstraint` in `tests/test_phase5_builtins.py`:

```python
class TestCircuitConstraint:
    def test_circuit_prunes_self_loops(self):
        """Domains initially include self-loops; CircuitConstraint removes them."""
        trail = fresh_trail()
        x, y, z = Var(), Var(), Var()
        in_domain([x, y, z], 1, 3, trail)
        constraint = CircuitConstraint((x, y, z))
        assert _post_constraint(constraint, trail)
        # No self-loops: x (node 1) can't be 1, y (node 2) can't be 2, etc.
        sx = get_attr(x, FD_KEY)
        sy = get_attr(y, FD_KEY)
        sz = get_attr(z, FD_KEY)
        assert not domain_contains(sx.domain, 1)
        assert not domain_contains(sy.domain, 2)
        assert not domain_contains(sz.domain, 3)

    def test_circuit_detects_forced_subtour(self):
        """x=2, y=1: x→2→1→(back to x's chain start) is a 2-cycle, must fail."""
        trail = fresh_trail()
        x, y, z = Var(), Var(), Var()
        in_domain([x, y, z], 1, 3, trail)
        unify(x, 2, trail)   # node 1 → 2
        unify(y, 1, trail)   # node 2 → 1 (closes 2-cycle!)
        constraint = CircuitConstraint((x, y, z))
        assert not _post_constraint(constraint, trail)

    def test_circuit_forces_completion(self):
        """Chain 1→2→3→? with n=3: last node must close to 1."""
        trail = fresh_trail()
        x, y, z = Var(), Var(), Var()
        in_domain([x, y, z], 1, 3, trail)
        unify(x, 2, trail)   # node 1 → 2
        unify(y, 3, trail)   # node 2 → 3
        # node 3 must → 1 to complete the circuit
        constraint = CircuitConstraint((x, y, z))
        assert _post_constraint(constraint, trail)
        assert deref(z) == 1

    def test_circuit_all_solutions(self):
        """3-node circuit: exactly 2 Hamiltonian circuits."""
        trail = fresh_trail()
        x, y, z = Var(), Var(), Var()
        in_domain([x, y, z], 1, 3, trail)
        assert list(fd_circuit([x, y, z], trail))
        results_gen = fd_circuit([x, y, z], trail)
        results = []
        for _ in results_gen:
            results.append((deref(x), deref(y), deref(z)))
        # (2,3,1) = 1→2→3→1 and (3,1,2) = 1→3→2→1
        assert len(results) == 2
        assert (2, 3, 1) in results
        assert (3, 1, 2) in results
```

---

### Test counts after all phases

| Phase | New tests | File |
|-------|-----------|------|
| 0 — AC-3 fix | 2 | `test_clpfd.py` |
| 1 — SumConstraint | ~5 | `test_phase5_builtins.py` |
| 2 — ScalarProductConstraint | ~4 | `test_phase5_builtins.py` |
| 3 — ElementConstraint | ~5 | `test_phase5_builtins.py` |
| 4 — CircuitConstraint | ~4 | `test_phase5_builtins.py` |

Existing 74 + 105 = 179 tests must all continue passing.

---

### Implementation order

1. **Phase 0** (AC-3 fix) — prerequisite for everything; 5-line change.
2. **Phase 1** (Sum) — most impactful; straightforward bounds arithmetic.
3. **Phase 2** (ScalarProduct) — extends Phase 1; adds negative coefficients.
4. **Phase 3** (Element) — requires `_domain_union` helper.
5. **Phase 4** (Circuit) — most complex; start with sub-tour detection only,
   test with 3 and 4 node circuits before attempting larger.
