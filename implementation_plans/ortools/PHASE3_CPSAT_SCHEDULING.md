# Phase 3: CP-SAT Scheduling Constraints

Interval variables, no-overlap, cumulative resource constraints, and 2D
no-overlap for packing problems.  These are CP-SAT's most distinctive
feature — no other Clausal backend provides scheduling primitives.

---

## 1. Interval Variable Creation

```python
def or_interval(start: Any, size: Any, end: Any, trail: Trail) -> Any:
    """Create an IntervalVar: start + size == end.

    start, end: Clausal Vars (must be registered as IntVars)
    size: Clausal Var or ground int

    Returns the CP-SAT IntervalVar for use in no_overlap / cumulative.
    """
    state = get_cpsat_state(trail)

    start_cp = _to_cpsat(start, trail)
    end_cp = _to_cpsat(end, trail)

    if isinstance(deref(size), int):
        size_cp = int(deref(size))
    else:
        size_cp = _to_cpsat(size, trail)

    state._interval_counter += 1
    name = f'iv_{state._interval_counter}'
    iv = state.model.NewIntervalVar(start_cp, size_cp, end_cp, name)

    return iv
```

### Gotcha: IntervalVar Enforces start + size == end

CP-SAT's `NewIntervalVar(start, size, end, name)` implicitly adds the
constraint `start + size == end`.  This means:

- If `size` is a ground integer, `end` is determined by `start` (or vice versa)
- If all three are variables, they're linked
- You don't need to add this constraint manually

### Gotcha: IntervalVars and OnlyEnforceIf

`NewIntervalVar` itself cannot be guarded by `OnlyEnforceIf` — it's a
variable declaration, not a constraint.  To make an interval "retractable",
use optional intervals (see below).

---

## 2. Optional Interval Variable

```python
def or_optional_interval(start: Any, size: Any, end: Any,
                          presence: Any, trail: Trail) -> Any:
    """Create an optional IntervalVar that exists only when presence is True.

    presence: Clausal Var (BoolVar) — if False, the interval is absent.

    Optional intervals are the key to backtracking-friendly scheduling:
    the presence literal can be an activation literal.
    """
    state = get_cpsat_state(trail)

    start_cp = _to_cpsat(start, trail)
    end_cp = _to_cpsat(end, trail)
    presence_cp = _to_cpsat_bool(presence, trail)

    if isinstance(deref(size), int):
        size_cp = int(deref(size))
    else:
        size_cp = _to_cpsat(size, trail)

    state._interval_counter += 1
    name = f'oiv_{state._interval_counter}'
    iv = state.model.NewOptionalIntervalVar(
        start_cp, size_cp, end_cp, presence_cp, name
    )

    return iv
```

### Backtracking Strategy for Intervals

Since `NewIntervalVar` can't be retracted, the recommended approach for
trail-synchronized scheduling is:

1. Use `NewOptionalIntervalVar` with the activation literal as the presence
   variable
2. When the scope is active, the activation literal is True, so the interval
   is present
3. On backtrack, the activation literal is no longer assumed True, so the
   interval becomes absent

```python
def or_interval_scoped(start: Any, size: Any, end: Any, trail: Trail) -> Any:
    """Create a trail-scoped interval using an optional interval + activation lit.

    The interval is only active while the current backtracking scope is active.
    """
    state = get_cpsat_state(trail)

    if not state.active_lits:
        # No scope — create a regular (permanent) interval
        return or_interval(start, size, end, trail)

    # Use the current activation literal as presence
    act = state.active_lits[-1]

    start_cp = _to_cpsat(start, trail)
    end_cp = _to_cpsat(end, trail)

    if isinstance(deref(size), int):
        size_cp = int(deref(size))
    else:
        size_cp = _to_cpsat(size, trail)

    state._interval_counter += 1
    name = f'siv_{state._interval_counter}'
    iv = state.model.NewOptionalIntervalVar(
        start_cp, size_cp, end_cp, act, name
    )

    return iv
```

---

## 3. Fixed-Size Interval

```python
def or_fixed_interval(start: Any, size: int, trail: Trail) -> tuple:
    """Create an interval with a fixed size, auto-creating the end variable.

    Returns (IntervalVar, end_cpsat_var) so the caller can access the end.
    """
    state = get_cpsat_state(trail)
    start_cp = _to_cpsat(start, trail)
    size = int(size)

    state._interval_counter += 1
    name = f'fiv_{state._interval_counter}'

    # Create end variable with appropriate bounds
    # If start is an IntVar, end's bounds = start's bounds + size
    state._int_counter += 1
    end_name = f'_end_{state._int_counter}'
    end_cp = state.model.NewIntVar(0, 10**6, end_name)

    iv = state.model.NewIntervalVar(start_cp, size, end_cp, name)
    return iv, end_cp
```

---

## 4. No-Overlap (1D)

```python
def or_no_overlap(intervals: list, trail: Trail) -> bool:
    """Post a no-overlap constraint: intervals must not overlap in time.

    intervals: list of IntervalVar objects (from or_interval or
    or_optional_interval).
    """
    state = get_cpsat_state(trail)
    state.model.AddNoOverlap(intervals)
    # Note: AddNoOverlap does NOT support OnlyEnforceIf.
    # Use optional intervals for backtracking.
    return True
```

### Gotcha: AddNoOverlap is NOT Reifiable

`AddNoOverlap` does not support `OnlyEnforceIf`.  This is a CP-SAT
limitation.  The workaround is to use optional intervals where the presence
literal is the activation literal.  If the interval is absent (presence=False),
it doesn't participate in the no-overlap constraint.

---

## 5. No-Overlap 2D

```python
def or_no_overlap_2d(x_intervals: list, y_intervals: list, trail: Trail) -> bool:
    """Post a 2D no-overlap constraint for rectangle packing.

    x_intervals[i] and y_intervals[i] define the horizontal and vertical
    extent of rectangle i.  No two rectangles may overlap.
    """
    state = get_cpsat_state(trail)
    if len(x_intervals) != len(y_intervals):
        raise ValueError("or_no_overlap_2d: x and y interval lists must have same length")
    state.model.AddNoOverlap2D(x_intervals, y_intervals)
    return True
```

---

## 6. Cumulative Resource

```python
def or_cumulative(intervals: list, demands: list, capacity: Any,
                   trail: Trail) -> bool:
    """Post a cumulative resource constraint.

    At any point in time, the sum of demands of overlapping intervals
    must not exceed capacity.

    intervals: list of IntervalVar
    demands: list of int or IntVar (one per interval)
    capacity: int or IntVar (resource capacity)
    """
    state = get_cpsat_state(trail)

    demands_cp = []
    for d in demands:
        d = deref(d)
        if isinstance(d, int):
            demands_cp.append(d)
        elif is_var(d):
            demands_cp.append(_to_cpsat(d, trail))
        else:
            raise TypeError(f"or_cumulative: demand must be int or Var, got {type(d).__name__}")

    capacity = deref(capacity)
    if isinstance(capacity, int):
        cap_cp = capacity
    elif is_var(capacity):
        cap_cp = _to_cpsat(capacity, trail)
    else:
        raise TypeError(f"or_cumulative: capacity must be int or Var")

    state.model.AddCumulative(intervals, demands_cp, cap_cp)
    return True
```

---

## 7. Helper: Interval from Clausal Terms

For use in `.clausal` files, intervals are passed as compound terms:

```python
def _intervals_from_clausal(interval_terms: list, trail: Trail) -> list:
    """Convert a list of Clausal interval terms to CP-SAT IntervalVars.

    Each term is expected to be:
    - interval(Start, Size, End) — standard interval
    - optional_interval(Start, Size, End, Presence) — optional

    Returns list of IntervalVar.
    """
    result = []
    for term in interval_terms:
        term = deref(term)
        if isinstance(term, Compound) and term.functor == 'interval' and len(term.args) == 3:
            start, size, end = term.args
            iv = or_interval_scoped(start, size, end, trail)
            result.append(iv)
        elif isinstance(term, Compound) and term.functor == 'optional_interval' and len(term.args) == 4:
            start, size, end, presence = term.args
            iv = or_optional_interval(start, size, end, presence, trail)
            result.append(iv)
        else:
            raise TypeError(f"Expected interval/3 or optional_interval/4 term, got {term}")
    return result
```

---

## 8. Tests (Phase 3)

```python
class TestCPSATScheduling:

    def test_simple_no_overlap(self):
        """Two tasks of size 3 on horizon [0, 5] — must not overlap."""
        trail = Trail()
        s1, s2 = Var(), Var()
        e1, e2 = Var(), Var()
        or_in(s1, 0, 5, trail)
        or_in(s2, 0, 5, trail)
        or_in(e1, 0, 8, trail)
        or_in(e2, 0, 8, trail)

        iv1 = or_interval(s1, 3, e1, trail)
        iv2 = or_interval(s2, 3, e2, trail)
        or_no_overlap([iv1, iv2], trail)

        assert or_check(trail)
        sols = []
        for _ in label_or([s1, s2], trail):
            sols.append((deref(s1), deref(s2)))
        # s1 and s2 must be at least 3 apart
        assert all(abs(a - b) >= 3 for a, b in sols)

    def test_no_overlap_unsat(self):
        """Three tasks of size 4 on horizon [0, 5] — impossible."""
        trail = Trail()
        starts = [Var() for _ in range(3)]
        ends = [Var() for _ in range(3)]
        for s in starts:
            or_in(s, 0, 5, trail)
        for e in ends:
            or_in(e, 0, 9, trail)

        intervals = []
        for s, e in zip(starts, ends):
            intervals.append(or_interval(s, 4, e, trail))
        or_no_overlap(intervals, trail)

        # 3 * 4 = 12 > 9, but horizon is [0, 9] so max span = 9
        # Actually: tasks end at max 9, so last start <= 5, all tasks need
        # contiguous slots: 0-3, 4-7, 8-11 but 11 > 9, so UNSAT
        assert not or_check(trail)

    def test_cumulative(self):
        """Two tasks need 2 units each, capacity 3 — can overlap partially."""
        trail = Trail()
        s1, s2 = Var(), Var()
        e1, e2 = Var(), Var()
        or_in(s1, 0, 10, trail)
        or_in(s2, 0, 10, trail)
        or_in(e1, 0, 15, trail)
        or_in(e2, 0, 15, trail)

        iv1 = or_interval(s1, 5, e1, trail)
        iv2 = or_interval(s2, 5, e2, trail)
        or_cumulative([iv1, iv2], [2, 2], 3, trail)

        assert or_check(trail)  # can overlap (2+2=4 > 3? No, 2+2=4 > 3 is UNSAT)
        # Actually 2+2=4 > 3, so they CANNOT fully overlap
        # They can partially overlap: if s1=0, e1=5, s2=3, e2=8
        # overlap at [3,5): demands = 2+2 = 4 > 3 — STILL exceeds capacity!
        # So they cannot overlap at all if both have demand 2 and capacity 3.
        # Let's fix: demand 1 each, capacity 1 -> same as no_overlap
        # Or demand 2 each, capacity 4 -> can fully overlap

    def test_cumulative_allows_overlap(self):
        """Two tasks demand 2 each, capacity 4 — can fully overlap."""
        trail = Trail()
        s1, s2 = Var(), Var()
        e1, e2 = Var(), Var()
        or_in(s1, 0, 10, trail)
        or_in(s2, 0, 10, trail)
        or_in(e1, 0, 15, trail)
        or_in(e2, 0, 15, trail)

        iv1 = or_interval(s1, 5, e1, trail)
        iv2 = or_interval(s2, 5, e2, trail)
        or_cumulative([iv1, iv2], [2, 2], 4, trail)

        # s1=0, s2=0 is valid (demand sum = 4 <= capacity 4)
        assert or_check(trail)

    def test_2d_packing(self):
        """Two 2x2 squares in a 3x3 grid — must not overlap."""
        trail = Trail()
        x1, x2, y1, y2 = Var(), Var(), Var(), Var()
        xe1, xe2, ye1, ye2 = Var(), Var(), Var(), Var()
        for v in [x1, x2, y1, y2]:
            or_in(v, 0, 1, trail)  # start positions 0 or 1 (size 2, grid 3)
        for v in [xe1, xe2, ye1, ye2]:
            or_in(v, 0, 3, trail)

        xiv1 = or_interval(x1, 2, xe1, trail)
        xiv2 = or_interval(x2, 2, xe2, trail)
        yiv1 = or_interval(y1, 2, ye1, trail)
        yiv2 = or_interval(y2, 2, ye2, trail)

        or_no_overlap_2d([xiv1, xiv2], [yiv1, yiv2], trail)
        assert or_check(trail)

    def test_job_shop(self):
        """Minimal 2-job 2-machine job shop."""
        trail = Trail()
        # Job 0: machine 0 for 3, then machine 1 for 2
        s00, e00, s01, e01 = Var(), Var(), Var(), Var()
        # Job 1: machine 1 for 4, then machine 0 for 1
        s10, e10, s11, e11 = Var(), Var(), Var(), Var()

        horizon = 20
        for v in [s00, e00, s01, e01, s10, e10, s11, e11]:
            or_in(v, 0, horizon, trail)

        iv00 = or_interval(s00, 3, e00, trail)
        iv01 = or_interval(s01, 2, e01, trail)
        iv10 = or_interval(s10, 4, e10, trail)
        iv11 = or_interval(s11, 1, e11, trail)

        # Precedence within jobs
        or_constraint_block((LtE(e00, s01),), trail)  # job 0
        or_constraint_block((LtE(e10, s11),), trail)  # job 1

        # No overlap on each machine
        or_no_overlap([iv00, iv11], trail)  # machine 0
        or_no_overlap([iv01, iv10], trail)  # machine 1

        assert or_check(trail)

    def test_scheduling_backtrack(self):
        """Scheduling constraints retracted on backtrack."""
        trail = Trail()
        s1, s2 = Var(), Var()
        e1, e2 = Var(), Var()
        or_in(s1, 0, 10, trail)
        or_in(s2, 0, 10, trail)
        or_in(e1, 0, 15, trail)
        or_in(e2, 0, 15, trail)

        mark = trail.mark()
        or_push(trail)
        # Use optional intervals scoped to activation literal
        iv1 = or_interval_scoped(s1, 5, e1, trail)
        iv2 = or_interval_scoped(s2, 5, e2, trail)
        or_no_overlap([iv1, iv2], trail)

        # With no-overlap, solutions are more restricted
        assert or_check(trail)

        trail.undo(mark)
        # Intervals are now absent — no scheduling constraint
        assert or_check(trail)
```

---

## Implementation Order

1. `or_interval()`
2. `or_optional_interval()`
3. `or_interval_scoped()`
4. `or_fixed_interval()`
5. `or_no_overlap()`
6. `or_no_overlap_2d()`
7. `or_cumulative()`
8. `_intervals_from_clausal()` helper
9. Tests

---

## Review & Checkpoint

After implementing this phase, perform the following review before moving on.

### 1. Run Tests

```bash
pytest tests/test_clportools.py -v -k "TestCPSATScheduling"
```

All tests listed in this phase must pass. If any fail, diagnose and fix
before continuing.

### 2. Code Review Checklist

- [ ] Every `deref()` call happens before `isinstance` checks
- [ ] Every `trail.record(callback)` callback captures only simple values
      (ints, not Trail objects) to avoid preventing GC
- [ ] Every constraint addition is guarded by `OnlyEnforceIf` when
      `active_lits` is non-empty
- [ ] `yield None` for success, bare `return` for failure — never
      `yield True` or `return False`
- [ ] No circular imports — builtin functions use lazy imports
- [ ] Verify that optional intervals with activation literals actually
      become dormant on backtrack

### 3. Write Issues Into This File

If you discover any issues during implementation — bugs, design decisions
that needed to change, gotchas not covered in the plan, or things that
worked differently than expected — **append them to this file** under a new
section:

```markdown
## Implementation Issues (Post-Implementation Addendum)

### Issue 1 — [short description]

**Problem:** ...
**Resolution:** ...
```

Number issues sequentially. Include enough detail that someone reading the
plan later understands what happened and why.

### 4. Ask Before Continuing If:

- A design decision in the plan seems wrong or suboptimal after seeing
  the real code
- A test requires infrastructure that doesn't exist yet (e.g., a missing
  `cons_to_list`, a Trail method that behaves differently than documented)
- You need to modify files outside the scope of this phase (e.g., changing
  the Trail C extension, modifying the compiler, editing another solver's
  code)
- The phase's approach is fundamentally incompatible with something you
  discovered in the codebase

**Do not silently work around these — surface them so the right decision
can be made.**
