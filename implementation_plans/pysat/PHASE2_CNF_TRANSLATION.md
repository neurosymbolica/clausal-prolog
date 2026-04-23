# Phase 2: CNF Translation & Labeling

Translate Clausal Boolean AST nodes to CNF clauses via Tseitin transformation,
implement constraint blocks, and build the solution enumeration (labeling) loop.

---

## 1. Literal Translation

The simplest case: a single Clausal Var or ground value to a signed SAT literal.

```python
def clausal_to_literal(expr: Any, trail: Trail) -> int:
    """Translate a simple expression to a SAT literal (signed int).

    - Unbound Var   -> positive SAT variable number
    - Ground True/1 -> add unit clause [fresh], return fresh
    - Ground False/0 -> add unit clause [-fresh], return fresh
    - Invert(X)     -> negate the inner literal

    Raises TypeError for non-Boolean ground values.
    """
    expr = deref(expr)

    if is_var(expr):
        return sat_var_for(expr, trail)

    if isinstance(expr, int):
        if expr == 1:
            return _TRUE_LIT  # special constant
        elif expr == 0:
            return _FALSE_LIT
        raise TypeError(f"Expected Boolean (0/1), got {expr}")

    if isinstance(expr, _Invert):
        inner = clausal_to_literal(expr.operand, trail)
        return -inner

    raise TypeError(f"Cannot translate {type(expr).__name__} to SAT literal")
```

---

## 2. Tseitin Transformation

For arbitrary Boolean formulas that aren't already in CNF, the **Tseitin
transformation** introduces auxiliary variables to maintain equisatisfiability
while converting to CNF.  The key principle: each subexpression gets a fresh
variable `t`, and clauses encode `t <-> subexpr`.

```python
def clausal_to_cnf(expr: Any, trail: Trail) -> tuple[int, list[list[int]]]:
    """Translate a Boolean expression to CNF via Tseitin transformation.

    Returns (root_literal, aux_clauses) where:
    - root_literal is the SAT literal representing the whole expression
    - aux_clauses are the Tseitin auxiliary clauses that must be added

    The caller must add aux_clauses to the solver AND assert root_literal.
    """
    expr = deref(expr)
    state = get_sat_state(trail)
    aux: list[list[int]] = []

    def tseitin(e: Any) -> int:
        e = deref(e)

        # Base cases
        if is_var(e):
            return sat_var_for(e, trail)
        if isinstance(e, bool) or (isinstance(e, int) and e in (0, 1)):
            t = _fresh_sat_var(state)
            if e:
                aux.append([t])
            else:
                aux.append([-t])
            return t

        # NOT: ~A
        if isinstance(e, _Invert):
            return -tseitin(e.operand)

        # OR: A | B
        if isinstance(e, _BitOr):
            a = tseitin(e.left)
            b = tseitin(e.right)
            t = _fresh_sat_var(state)
            # t <-> (a | b)
            # Clauses: (~t | a | b), (t | ~a), (t | ~b)
            aux.append([-t, a, b])
            aux.append([t, -a])
            aux.append([t, -b])
            return t

        # AND: A & B
        if isinstance(e, _BitAnd):
            a = tseitin(e.left)
            b = tseitin(e.right)
            t = _fresh_sat_var(state)
            # t <-> (a & b)
            # Clauses: (t | ~a | ~b), (~t | a), (~t | b)
            aux.append([t, -a, -b])
            aux.append([-t, a])
            aux.append([-t, b])
            return t

        # XOR: A ^ B
        if isinstance(e, _BitXor):
            a = tseitin(e.left)
            b = tseitin(e.right)
            t = _fresh_sat_var(state)
            # t <-> (a ^ b)
            # Clauses: (~t | ~a | ~b), (~t | a | b), (t | ~a | b), (t | a | ~b)
            aux.append([-t, -a, -b])
            aux.append([-t, a, b])
            aux.append([t, -a, b])
            aux.append([t, a, -b])
            return t

        # ArithEq: A == B  (Boolean equality / XNOR)
        if isinstance(e, _ArithEq):
            a = tseitin(e.left)
            b = tseitin(e.right)
            t = _fresh_sat_var(state)
            # t <-> (a <-> b)  i.e. t <-> NOT(a XOR b)
            aux.append([-t, a, -b])
            aux.append([-t, -a, b])
            aux.append([t, a, b])
            aux.append([t, -a, -b])
            return t

        # ArithNeq: A != B  (XOR)
        if isinstance(e, _ArithNeq):
            a = tseitin(e.left)
            b = tseitin(e.right)
            t = _fresh_sat_var(state)
            # Same as XOR
            aux.append([-t, -a, -b])
            aux.append([-t, a, b])
            aux.append([t, -a, b])
            aux.append([t, a, -b])
            return t

        raise TypeError(f"Cannot translate {type(e).__name__} to SAT CNF")

    root = tseitin(expr)
    return root, aux
```

### Optimization: Simple Clauses

Most SAT constraints are already disjunctions (OR of literals).  We can detect
this common case and avoid Tseitin overhead:

```python
def _is_simple_clause(expr: Any) -> bool:
    """Check if expression is a disjunction of literals (no nesting)."""
    expr = deref(expr)
    if is_var(expr) or isinstance(expr, _Invert):
        return True
    if isinstance(expr, _BitOr):
        return _is_simple_clause(expr.left) and _is_simple_clause(expr.right)
    if isinstance(expr, (int, bool)):
        return True
    return False

def _collect_disjuncts(expr: Any, trail: Trail) -> list[int]:
    """Flatten a disjunction tree into a list of literals."""
    expr = deref(expr)
    if isinstance(expr, _BitOr):
        return _collect_disjuncts(expr.left, trail) + \
               _collect_disjuncts(expr.right, trail)
    return [clausal_to_literal(expr, trail)]
```

---

## 3. Constraint Block

```python
def sat_constraint_block(constraint_set: Any, solver_name: str, trail: Trail) -> bool:
    """Walk constraint elements and post each as CNF clauses.

    Each element in the tuple/list is treated as a Boolean formula that
    must hold (conjunction of all elements).  Simple disjunctions are
    added directly; complex expressions use Tseitin transformation.

    Returns True on success, False if immediately UNSAT after posting.
    """
    state = get_sat_state(trail, solver_name)

    if isinstance(constraint_set, (list, tuple)):
        elements = constraint_set
    else:
        elements = [constraint_set]

    sat_push(trail)  # one activation scope for this block

    for elem in elements:
        elem = deref(elem)

        if _is_simple_clause(elem):
            # Fast path: directly collect disjuncts
            lits = _collect_disjuncts(elem, trail)
            sat_add_clause(lits, trail)
        else:
            # Complex expression: Tseitin transform
            root, aux_clauses = clausal_to_cnf(elem, trail)
            for clause in aux_clauses:
                sat_add_clause(clause, trail)
            sat_add_clause([root], trail)  # assert root is true

    return True  # consistency checked lazily at label/check time
```

Pattern: `clpz3.py:2243-2261` (`z3_constraint_block`).

---

## 4. Labeling (Solution Enumeration)

```python
def label_sat(vars_list: Any, trail: Trail):
    """Enumerate satisfying Boolean assignments for SAT-constrained variables.

    Generator: yields None for each solution, with Clausal vars bound to
    0 or 1.  Bindings are undone between solutions.

    Pattern follows label_z3() in clpz3.py:478-543.
    """
    state = get_sat_state(trail)
    items = _as_list(vars_list)

    sat_vars: list[int] = []
    clausal_vars: list[Var] = []

    for v in items:
        v = deref(v)
        if is_var(v):
            sv = state.var_map.get(id(v))
            if sv is None:
                raise ValueError(
                    "label_sat: variable not registered with SAT solver. "
                    "Post a constraint first."
                )
            sat_vars.append(sv)
            clausal_vars.append(v)
        elif isinstance(v, int) and v in (0, 1):
            pass  # already ground
        else:
            raise TypeError(f"label_sat: expected 0/1 or Var, got {type(v).__name__}")

    if not sat_vars:
        if sat_check(trail):
            yield None
        return

    # Push scope for blocking clauses
    sat_push(trail)

    while state.solver.solve(assumptions=state.assumptions):
        model = state.solver.get_model()
        model_set = set(model)

        # Extract 0/1 values for our variables
        values = [1 if sv in model_set else 0 for sv in sat_vars]

        mark = trail.mark()
        ok = all(unify(cv, val, trail)
                 for cv, val in zip(clausal_vars, values))

        if ok:
            yield None  # solution

        trail.undo(mark)

        # Block this assignment
        blocking = [-sv if sv in model_set else sv for sv in sat_vars]
        state.solver.add_clause(blocking)  # no activation guard needed
        # (blocking clauses only exclude already-seen assignments)
```

### sat_count

```python
def sat_count(vars_list: Any, trail: Trail) -> int:
    """Count the number of satisfying assignments."""
    count = 0
    for _ in label_sat(vars_list, trail):
        count += 1
    return count
```

---

## 5. Tests (Phase 2)

```python
class TestCNFTranslation:

    def test_simple_disjunction(self):
        """X | Y is detected as simple clause."""
        trail = Trail()
        x, y = Var(), Var()
        expr = BitOr(left=x, right=y)
        assert _is_simple_clause(expr)

    def test_nested_and_needs_tseitin(self):
        """(X & Y) | Z is NOT a simple clause."""
        trail = Trail()
        x, y, z = Var(), Var(), Var()
        expr = BitOr(left=BitAnd(left=x, right=y), right=z)
        assert not _is_simple_clause(expr)

    def test_tseitin_and(self):
        trail = Trail()
        x, y = Var(), Var()
        root, aux = clausal_to_cnf(BitAnd(left=x, right=y), trail)
        # root, aux should encode t <-> (x & y)
        assert len(aux) == 3  # three clauses for AND

    def test_tseitin_xor(self):
        trail = Trail()
        x, y = Var(), Var()
        root, aux = clausal_to_cnf(BitXor(left=x, right=y), trail)
        assert len(aux) == 4  # four clauses for XOR


class TestConstraintBlock:

    def test_simple_clauses(self):
        """pysat.cadical((X | Y, ~X | Y)) -> Y must be True."""
        trail = Trail()
        x, y = Var(), Var()
        sat_constraint_block((
            BitOr(left=x, right=y),
            BitOr(left=Invert(operand=x), right=y),
        ), 'cadical195', trail)
        sols = []
        for _ in label_sat([x, y], trail):
            sols.append((deref(x), deref(y)))
        # Y=1 in all solutions: (0,1) and (1,1)
        assert all(s[1] == 1 for s in sols)
        assert len(sols) == 2

    def test_xor_constraint(self):
        """X ^ Y has exactly 2 solutions."""
        trail = Trail()
        x, y = Var(), Var()
        sat_constraint_block((BitXor(left=x, right=y),), 'cadical195', trail)
        sols = list(label_sat([x, y], trail))
        # Not using the generator value, just counting
        count = 0
        for _ in label_sat([x, y], trail):
            count += 1
        assert count == 2

    def test_unsat_constraint(self):
        """X & ~X is unsatisfiable."""
        trail = Trail()
        x = Var()
        sat_constraint_block((
            BitAnd(left=x, right=Invert(operand=x)),
        ), 'cadical195', trail)
        assert not sat_check(trail)

    def test_backtracking_retracts_block(self):
        trail = Trail()
        x, y = Var(), Var()
        mark = trail.mark()
        sat_constraint_block((
            BitOr(left=x, right=y),
            Invert(operand=x),    # forces x=0, so y=1
            Invert(operand=y),    # forces y=0 — contradicts!
        ), 'cadical195', trail)
        assert not sat_check(trail)

        trail.undo(mark)
        assert sat_check(trail)  # constraints retracted


class TestLabeling:

    def test_three_vars_all_solutions(self):
        """3 unconstrained vars -> 8 solutions."""
        trail = Trail()
        x, y, z = Var(), Var(), Var()
        # Trivial constraint just to register the variables
        sat_constraint_block((
            BitOr(left=x, right=Invert(operand=x)),  # tautology for x
            BitOr(left=y, right=Invert(operand=y)),   # tautology for y
            BitOr(left=z, right=Invert(operand=z)),   # tautology for z
        ), 'cadical195', trail)
        count = sum(1 for _ in label_sat([x, y, z], trail))
        assert count == 8

    def test_label_bindings_undone(self):
        """After labeling, vars are unbound again."""
        trail = Trail()
        x = Var()
        sat_constraint_block((
            BitOr(left=x, right=Invert(operand=x)),
        ), 'cadical195', trail)
        for _ in label_sat([x], trail):
            pass
        assert is_var(deref(x))

    def test_nested_search(self):
        """Inner labeling doesn't corrupt outer state."""
        trail = Trail()
        x, y = Var(), Var()
        sat_constraint_block((
            BitOr(left=x, right=y),
        ), 'cadical195', trail)

        outer_solutions = []
        for _ in label_sat([x], trail):
            inner_count = 0
            for _ in label_sat([y], trail):
                inner_count += 1
            outer_solutions.append((deref(x), inner_count))
        # x=0: y must be 1 (1 inner solution)
        # x=1: y can be 0 or 1 (2 inner solutions)
        assert len(outer_solutions) == 2
```

---

## Implementation Order

1. AST node imports (`_BitOr`, `_BitAnd`, `_BitXor`, `_Invert`, etc.)
2. `clausal_to_literal()`
3. `_is_simple_clause()` + `_collect_disjuncts()`
4. `clausal_to_cnf()` (Tseitin)
5. `sat_constraint_block()`
6. `_as_list()` helper (reuse from clpz3 or copy)
7. `label_sat()`
8. `sat_count()`
9. Tests
