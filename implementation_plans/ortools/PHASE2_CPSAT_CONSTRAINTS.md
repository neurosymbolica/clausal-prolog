# Phase 2: CP-SAT Integer + Boolean Constraints

Domain declarations, arithmetic expression translation, comparison constraints,
global constraints (all_different, element), Boolean operations, and solution
enumeration (labeling).

---

## 1. Domain Declaration

```python
def or_in(var: Var, lo_or_values, hi=None, trail: Trail = None) -> bool:
    """Declare an integer variable with a domain.

    or_in(X, 1, 9)         -> IntVar [1, 9]
    or_in(X, [1, 3, 5])    -> IntVar with sparse domain {1, 3, 5}

    If the variable already exists, adds narrowing constraints instead.
    """
    var = deref(var)
    if not is_var(var):
        raise TypeError(f"or_in: expected unbound Var, got {type(var).__name__}")

    state = get_cpsat_state(trail)
    vid = id(var)

    if hi is not None:
        # Contiguous domain: or_in(X, Lo, Hi)
        lo, hi = int(lo_or_values), int(hi)
        existing = state.var_map.get(vid)
        if existing is not None:
            # Variable already registered — add narrowing constraints
            or_push(trail)
            or_add_constraint(existing >= lo, trail)
            or_add_constraint(existing <= hi, trail)
            return True
        or_var_for(var, lo, hi, trail)
        return True
    else:
        # Sparse domain: or_in(X, [1, 3, 5])
        values = [int(v) for v in lo_or_values]
        existing = state.var_map.get(vid)
        if existing is not None:
            # Add allowed-values constraint via table
            or_push(trail)
            ct = state.model.AddAllowedAssignments([existing], [[v] for v in values])
            if state.active_lits:
                ct.OnlyEnforceIf(state.active_lits[-1])
            return True
        or_var_from_domain(var, values, trail)
        return True
```

---

## 2. Boolean Variable Declaration

```python
def or_bool(var: Var, trail: Trail) -> bool:
    """Declare a Boolean variable (domain {0, 1})."""
    or_bool_for(var, trail)
    return True
```

---

## 3. Expression Translation

Translate Clausal arithmetic AST nodes to CP-SAT expressions.

```python
def clausal_to_cpsat(expr: Any, trail: Trail) -> Any:
    """Translate a Clausal expression to a CP-SAT IntVar / LinearExpr.

    Handles:
    - Var (unbound)     -> registered IntVar or BoolVar
    - int literal       -> constant
    - Add(left, right)  -> left + right
    - Sub(left, right)  -> left - right
    - Mult(left, right) -> left * right (one operand must be constant)
    - FloorDiv(left, right) -> left // right (CP-SAT integer division)
    - Mod(left, right)  -> left % right
    - Negate(operand)   -> -operand

    Raises TypeError for unsupported expression types.
    """
    expr = deref(expr)

    # Base cases
    if is_var(expr):
        state = get_cpsat_state(trail)
        vid = id(expr)
        cpsat_var = state.var_map.get(vid)
        if cpsat_var is not None:
            return cpsat_var
        # Auto-register with default bounds if not yet registered
        # This allows arithmetic expressions over unregistered vars
        raise ValueError(
            f"Variable not registered with CP-SAT. "
            f"Call ortools.cpsat.in(Var, Lo, Hi) first."
        )

    if isinstance(expr, (int, float)):
        return int(expr)

    # Arithmetic nodes
    if isinstance(expr, _Add):
        left = clausal_to_cpsat(expr.left, trail)
        right = clausal_to_cpsat(expr.right, trail)
        return left + right

    if isinstance(expr, _Sub):
        left = clausal_to_cpsat(expr.left, trail)
        right = clausal_to_cpsat(expr.right, trail)
        return left - right

    if isinstance(expr, _Mult):
        left = clausal_to_cpsat(expr.left, trail)
        right = clausal_to_cpsat(expr.right, trail)
        return left * right

    if isinstance(expr, _FloorDiv):
        left = clausal_to_cpsat(expr.left, trail)
        right = clausal_to_cpsat(expr.right, trail)
        # CP-SAT integer division requires a helper variable
        state = get_cpsat_state(trail)
        state._int_counter += 1
        lo = -10**9  # safe large bounds
        hi = 10**9
        quot = state.model.NewIntVar(lo, hi, f'_div_{state._int_counter}')
        state.model.AddDivisionEquality(quot, left, right)
        return quot

    if isinstance(expr, _Mod):
        left = clausal_to_cpsat(expr.left, trail)
        right = clausal_to_cpsat(expr.right, trail)
        state = get_cpsat_state(trail)
        state._int_counter += 1
        lo = 0
        hi = 10**9
        rem = state.model.NewIntVar(lo, hi, f'_mod_{state._int_counter}')
        state.model.AddModuloEquality(rem, left, right)
        return rem

    if isinstance(expr, _Negate):
        inner = clausal_to_cpsat(expr.operand, trail)
        return -inner

    raise TypeError(f"Cannot translate {type(expr).__name__} to CP-SAT expression")
```

### Gotcha: Nonlinear Expressions

CP-SAT supports `x * y` (product of two IntVars) via `AddMultiplicationEquality`,
not via direct operator overloading.  The `*` operator on `IntVar` only works
when one side is a constant.  For `Var * Var`, we need:

```python
if isinstance(expr, _Mult):
    left = clausal_to_cpsat(expr.left, trail)
    right = clausal_to_cpsat(expr.right, trail)
    if isinstance(left, int) or isinstance(right, int):
        return left * right  # linear: constant * var
    # Nonlinear: var * var — need auxiliary variable
    state = get_cpsat_state(trail)
    state._int_counter += 1
    prod = state.model.NewIntVar(-10**9, 10**9, f'_prod_{state._int_counter}')
    state.model.AddMultiplicationEquality(prod, [left, right])
    return prod
```

---

## 4. Comparison Translation

```python
def clausal_to_cpsat_constraint(expr: Any, trail: Trail) -> Any:
    """Translate a Clausal comparison expression to a CP-SAT BoundedLinearExpression.

    Returns something suitable for model.Add(...).
    """
    expr = deref(expr)

    if isinstance(expr, _ArithEq):
        left = clausal_to_cpsat(expr.left, trail)
        right = clausal_to_cpsat(expr.right, trail)
        return left == right

    if isinstance(expr, _ArithNeq):
        left = clausal_to_cpsat(expr.left, trail)
        right = clausal_to_cpsat(expr.right, trail)
        return left != right

    if isinstance(expr, _Lt):
        left = clausal_to_cpsat(expr.left, trail)
        right = clausal_to_cpsat(expr.right, trail)
        return left < right

    if isinstance(expr, _LtE):
        left = clausal_to_cpsat(expr.left, trail)
        right = clausal_to_cpsat(expr.right, trail)
        return left <= right

    if isinstance(expr, _Gt):
        left = clausal_to_cpsat(expr.left, trail)
        right = clausal_to_cpsat(expr.right, trail)
        return left > right

    if isinstance(expr, _GtE):
        left = clausal_to_cpsat(expr.left, trail)
        right = clausal_to_cpsat(expr.right, trail)
        return left >= right

    raise TypeError(f"Cannot translate {type(expr).__name__} to CP-SAT constraint")
```

---

## 5. Constraint Block

```python
def or_constraint_block(constraint_set: Any, trail: Trail) -> bool:
    """Walk constraint elements and post each as CP-SAT constraints.

    Each element in the tuple/list is a comparison expression that must
    hold (conjunction).  All constraints are guarded by a single
    activation literal for this block.

    Returns True on success.
    """
    if isinstance(constraint_set, (list, tuple)):
        elements = constraint_set
    else:
        elements = [constraint_set]

    or_push(trail)  # one activation scope for this block

    for elem in elements:
        elem = deref(elem)
        ct_expr = clausal_to_cpsat_constraint(elem, trail)
        or_add_constraint(ct_expr, trail)

    return True
```

Pattern: `clpsat.py:sat_constraint_block()`, `clpz3.py:z3_constraint_block()`.

---

## 6. All-Different

```python
def or_all_different(vars_list: Any, trail: Trail) -> bool:
    """Post an all-different constraint.

    All variables must have been previously registered via or_in().
    """
    state = get_cpsat_state(trail)
    items = _as_list(vars_list)
    cpsat_vars = []
    for v in items:
        v = deref(v)
        if is_var(v):
            cv = state.var_map.get(id(v))
            if cv is None:
                raise ValueError("or_all_different: variable not registered")
            cpsat_vars.append(cv)
        elif isinstance(v, int):
            cpsat_vars.append(v)
        else:
            raise TypeError(f"or_all_different: expected Var or int, got {type(v).__name__}")

    ct = state.model.AddAllDifferent(cpsat_vars)
    if state.active_lits:
        ct.OnlyEnforceIf(state.active_lits[-1])
    return True
```

### Gotcha: OnlyEnforceIf + AllDifferent

`AddAllDifferent` returns a `Constraint` object that supports `OnlyEnforceIf`.
This is a CP-SAT feature — most global constraints can be reified.  However,
some constraints (noted in CP-SAT docs) do **not** support `OnlyEnforceIf`:

- `AddCircuit` — **not reifiable** (Phase 4 handles this)
- `AddMultipleCircuit` — not reifiable
- `AddAutomaton` — not reifiable

For non-reifiable constraints, the workaround is to wrap the entire constraint
in a conditional model-building step.

---

## 7. Element Constraint

```python
def or_element(index: Any, array: Any, target: Any, trail: Trail) -> bool:
    """Post element constraint: array[index] == target.

    index, target are Clausal Vars or ground ints.
    array is a list of Clausal Vars or ground ints.
    """
    state = get_cpsat_state(trail)

    idx_cpsat = _to_cpsat(index, trail)
    tgt_cpsat = _to_cpsat(target, trail)
    arr_cpsat = [_to_cpsat(v, trail) for v in _as_list(array)]

    ct = state.model.AddElement(idx_cpsat, arr_cpsat, tgt_cpsat)
    if state.active_lits:
        ct.OnlyEnforceIf(state.active_lits[-1])
    return True

def _to_cpsat(expr: Any, trail: Trail) -> Any:
    """Convert a single Var or int to CP-SAT variable/constant."""
    expr = deref(expr)
    if is_var(expr):
        state = get_cpsat_state(trail)
        cv = state.var_map.get(id(expr))
        if cv is None:
            raise ValueError("Variable not registered with CP-SAT")
        return cv
    if isinstance(expr, int):
        return expr
    raise TypeError(f"Expected Var or int, got {type(expr).__name__}")
```

---

## 8. Boolean Constraints

```python
def or_bool_or(literals: Any, trail: Trail) -> bool:
    """Post Boolean OR: at least one literal is True."""
    state = get_cpsat_state(trail)
    cpsat_lits = [_to_cpsat_bool(lit, trail) for lit in _as_list(literals)]
    ct = state.model.AddBoolOr(cpsat_lits)
    if state.active_lits:
        ct.OnlyEnforceIf(state.active_lits[-1])
    return True

def or_bool_and(literals: Any, trail: Trail) -> bool:
    """Post Boolean AND: all literals are True."""
    state = get_cpsat_state(trail)
    cpsat_lits = [_to_cpsat_bool(lit, trail) for lit in _as_list(literals)]
    ct = state.model.AddBoolAnd(cpsat_lits)
    if state.active_lits:
        ct.OnlyEnforceIf(state.active_lits[-1])
    return True

def or_implication(a: Any, b: Any, trail: Trail) -> bool:
    """Post implication: a => b."""
    state = get_cpsat_state(trail)
    a_cpsat = _to_cpsat_bool(a, trail)
    b_cpsat = _to_cpsat_bool(b, trail)
    ct = state.model.AddImplication(a_cpsat, b_cpsat)
    if state.active_lits:
        ct.OnlyEnforceIf(state.active_lits[-1])
    return True

def or_exactly_one(literals: Any, trail: Trail) -> bool:
    """Post exactly-one constraint."""
    state = get_cpsat_state(trail)
    cpsat_lits = [_to_cpsat_bool(lit, trail) for lit in _as_list(literals)]
    ct = state.model.AddExactlyOne(cpsat_lits)
    if state.active_lits:
        ct.OnlyEnforceIf(state.active_lits[-1])
    return True

def or_at_most_one(literals: Any, trail: Trail) -> bool:
    """Post at-most-one constraint."""
    state = get_cpsat_state(trail)
    cpsat_lits = [_to_cpsat_bool(lit, trail) for lit in _as_list(literals)]
    ct = state.model.AddAtMostOne(cpsat_lits)
    if state.active_lits:
        ct.OnlyEnforceIf(state.active_lits[-1])
    return True

def or_at_least_one(literals: Any, trail: Trail) -> bool:
    """Post at-least-one constraint."""
    state = get_cpsat_state(trail)
    cpsat_lits = [_to_cpsat_bool(lit, trail) for lit in _as_list(literals)]
    ct = state.model.AddAtLeastOne(cpsat_lits)
    if state.active_lits:
        ct.OnlyEnforceIf(state.active_lits[-1])
    return True

def _to_cpsat_bool(expr: Any, trail: Trail) -> Any:
    """Convert a Var or literal to a CP-SAT BoolVar or its negation."""
    expr = deref(expr)
    if isinstance(expr, _Invert):
        inner = _to_cpsat_bool(expr.operand, trail)
        return inner.Not()
    if is_var(expr):
        return or_bool_for(expr, trail)
    if isinstance(expr, (bool, int)):
        # Ground Boolean — create a fixed BoolVar
        state = get_cpsat_state(trail)
        state._bool_counter += 1
        bv = state.model.NewBoolVar(f'_const_{state._bool_counter}')
        state.model.Add(bv == int(bool(expr)))
        return bv
    raise TypeError(f"Expected Boolean Var or literal, got {type(expr).__name__}")
```

---

## 9. Labeling (Solution Enumeration)

```python
def label_or(vars_list: Any, trail: Trail):
    """Enumerate satisfying integer assignments for CP-SAT constrained variables.

    Generator: yields None for each solution, with Clausal vars bound to
    integer values.  Bindings are undone between solutions.

    Pattern follows label_z3() in clpz3.py and label_sat() in clpsat.py.
    """
    state = get_cpsat_state(trail)
    items = _as_list(vars_list)

    cpsat_vars: list = []
    clausal_vars: list[Var] = []

    for v in items:
        v = deref(v)
        if is_var(v):
            cv = state.var_map.get(id(v))
            if cv is None:
                raise ValueError(
                    "label_or: variable not registered with CP-SAT. "
                    "Post a constraint first (ortools.cpsat.in)."
                )
            cpsat_vars.append(cv)
            clausal_vars.append(v)
        elif isinstance(v, int):
            pass  # already ground
        else:
            raise TypeError(f"label_or: expected int or Var, got {type(v).__name__}")

    if not cpsat_vars:
        if or_check(trail):
            yield None
        return

    while True:
        _apply_assumptions(state)
        status = state.solver.Solve(state.model)
        if status not in (_OPTIMAL, _FEASIBLE):
            return  # no more solutions

        # Extract values
        values = [state.solver.Value(cv) for cv in cpsat_vars]

        mark = trail.mark()
        ok = all(unify(cv, val, trail)
                 for cv, val in zip(clausal_vars, values))

        if ok:
            yield None  # solution

        trail.undo(mark)

        # Block this assignment: at least one variable must differ
        blocking_literals = []
        for cv, val in zip(cpsat_vars, values):
            state._bool_counter += 1
            b = state.model.NewBoolVar(f'_blk_{state._bool_counter}')
            state.model.Add(cv != val).OnlyEnforceIf(b)
            state.model.Add(cv == val).OnlyEnforceIf(b.Not())
            blocking_literals.append(b)
        state.model.AddBoolOr(blocking_literals)
```

### Gotcha: Blocking Clauses in CP-SAT

Unlike PySAT where blocking is a simple clause `[-v1, v2, -v3, ...]`, CP-SAT
requires an explicit encoding:

1. For each variable-value pair (x=v), create a BoolVar `b` that is True iff
   `x != v`
2. Require `OR(all b's)` — at least one variable must take a different value

This is more verbose but semantically identical.

**Alternative (simpler encoding)**: For solution enumeration, CP-SAT provides
`CpSolverSolutionCallback` which is invoked for each solution.  We can use
this for `or_count()`:

```python
class _SolutionCounter(_CpSolverSolutionCallback):
    def __init__(self):
        super().__init__()
        self.count = 0
    def on_solution_callback(self):
        self.count += 1

def or_count(vars_list: Any, trail: Trail) -> int:
    """Count solutions using CP-SAT's native callback."""
    state = get_cpsat_state(trail)
    _apply_assumptions(state)
    counter = _SolutionCounter()
    # Tell solver to enumerate all solutions
    state.solver.parameters.enumerate_all_solutions = True
    state.solver.Solve(state.model, counter)
    state.solver.parameters.enumerate_all_solutions = False
    return counter.count
```

---

## 10. Tests (Phase 2)

```python
class TestCPSATDomains:

    def test_in_contiguous(self):
        trail = Trail()
        x = Var()
        or_in(x, 1, 9, trail)
        state = get_cpsat_state(trail)
        assert id(x) in state.var_map

    def test_in_sparse(self):
        trail = Trail()
        x = Var()
        or_in(x, [2, 4, 6, 8], trail=trail)
        assert or_check(trail)

    def test_in_narrowing(self):
        """Second in() on same var narrows the domain."""
        trail = Trail()
        x = Var()
        or_in(x, 1, 100, trail)
        or_in(x, 50, 60, trail)
        or_add_constraint(get_cpsat_state(trail).var_map[id(x)] == 55, trail)
        assert or_check(trail)


class TestCPSATArithmetic:

    def test_sum_constraint(self):
        trail = Trail()
        x, y = Var(), Var()
        or_in(x, 0, 10, trail)
        or_in(y, 0, 10, trail)
        or_constraint_block((ArithEq(Add(x, y), 15),), trail)
        assert or_check(trail)

    def test_sum_unsat(self):
        trail = Trail()
        x, y = Var(), Var()
        or_in(x, 0, 10, trail)
        or_in(y, 0, 10, trail)
        or_constraint_block((ArithEq(Add(x, y), 25),), trail)
        assert not or_check(trail)  # max sum = 20


class TestCPSATAllDifferent:

    def test_all_different_sat(self):
        trail = Trail()
        x, y, z = Var(), Var(), Var()
        or_in(x, 1, 3, trail)
        or_in(y, 1, 3, trail)
        or_in(z, 1, 3, trail)
        or_all_different([x, y, z], trail)
        assert or_check(trail)

    def test_all_different_unsat(self):
        trail = Trail()
        x, y, z = Var(), Var(), Var()
        or_in(x, 1, 2, trail)
        or_in(y, 1, 2, trail)
        or_in(z, 1, 2, trail)
        or_all_different([x, y, z], trail)
        assert not or_check(trail)  # pigeonhole


class TestCPSATLabeling:

    def test_permutations(self):
        """3 vars in [1,3], all_different -> 6 solutions."""
        trail = Trail()
        x, y, z = Var(), Var(), Var()
        or_in(x, 1, 3, trail)
        or_in(y, 1, 3, trail)
        or_in(z, 1, 3, trail)
        or_all_different([x, y, z], trail)
        sols = []
        for _ in label_or([x, y, z], trail):
            sols.append((deref(x), deref(y), deref(z)))
        assert len(sols) == 6

    def test_label_bindings_undone(self):
        trail = Trail()
        x = Var()
        or_in(x, 1, 5, trail)
        for _ in label_or([x], trail):
            pass
        assert is_var(deref(x))

    def test_backtracking_retracts_and_relabels(self):
        trail = Trail()
        x = Var()
        or_in(x, 1, 10, trail)
        mark = trail.mark()
        or_push(trail)
        or_add_constraint(get_cpsat_state(trail).var_map[id(x)] <= 3, trail)
        count1 = sum(1 for _ in label_or([x], trail))
        assert count1 == 3

        trail.undo(mark)
        count2 = sum(1 for _ in label_or([x], trail))
        assert count2 == 10


class TestCPSATBoolean:

    def test_bool_or(self):
        trail = Trail()
        a, b = Var(), Var()
        or_bool(a, trail)
        or_bool(b, trail)
        or_bool_or([a, b], trail)
        assert or_check(trail)

    def test_exactly_one(self):
        trail = Trail()
        a, b, c = Var(), Var(), Var()
        or_bool(a, trail)
        or_bool(b, trail)
        or_bool(c, trail)
        or_exactly_one([a, b, c], trail)
        count = sum(1 for _ in label_or([a, b, c], trail))
        assert count == 3

    def test_implication(self):
        trail = Trail()
        a, b = Var(), Var()
        or_bool(a, trail)
        or_bool(b, trail)
        or_implication(a, b, trail)
        # a => b: solutions are (0,0), (0,1), (1,1) = 3
        count = sum(1 for _ in label_or([a, b], trail))
        assert count == 3
```

---

## Implementation Order

1. AST node imports (`_Add`, `_Sub`, `_Mult`, `_ArithEq`, `_Lt`, etc. — see Phase 0)
2. `or_in()` with narrowing support
3. `or_bool()`
4. `clausal_to_cpsat()` (expression translation)
5. `clausal_to_cpsat_constraint()` (comparison translation)
6. `or_constraint_block()`
7. `_to_cpsat()`, `_to_cpsat_bool()` helpers
8. `or_all_different()`
9. `or_element()`
10. Boolean constraints (`or_bool_or`, `or_bool_and`, `or_implication`, etc.)
11. `label_or()` with blocking clauses
12. `or_count()` with solution callback
13. `_as_list()` helper
14. Tests

---

## Review & Checkpoint

After implementing this phase, perform the following review before moving on.

### 1. Run Tests

```bash
pytest tests/test_clportools.py -v -k "TestCPSATDomains or TestCPSATArithmetic or TestCPSATAllDifferent or TestCPSATLabeling or TestCPSATBoolean"
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
- [ ] Verify `clausal_to_cpsat` handles `CompareChain` (chained
      comparisons like `1 < X < 10`) correctly

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
