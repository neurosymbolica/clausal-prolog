# Phase 3: Cardinality & Pseudo-Boolean Constraints

Expose PySAT's `pysat.card.CardEnc` and `pysat.pb.PBEnc` for cardinality
and weighted linear constraints over Boolean variables.

---

## 1. Cardinality Constraints

PySAT's `CardEnc` generates CNF encodings for constraints of the form:

    sum(x_i for i in lits) <op> k

where `<op>` is `<=` (at-most), `>=` (at-least), or `=` (exactly).

### API

```python
def sat_at_most(vars_list: Any, k: int, trail: Trail) -> bool:
    """At most k of the variables are True (1).

    Uses pysat.card.CardEnc.atmost with sequential counter encoding.
    Auxiliary variables from the encoding are tracked in SATState._counter.
    """
    state = get_sat_state(trail)
    items = _as_list(vars_list)
    lits = [sat_var_for(deref(v), trail) for v in items if is_var(deref(v))]

    # CardEnc needs to know the current max variable ID to avoid collisions
    cnf = _CardEnc.atmost(lits=lits, bound=k, top_id=state._counter,
                          encoding=_EncType.seqcounter)

    # Update counter to account for auxiliary variables
    if cnf.nv > state._counter:
        state._counter = cnf.nv

    # Add all generated clauses under current activation scope
    sat_push(trail)
    for clause in cnf.clauses:
        sat_add_clause(clause, trail)

    return True


def sat_at_least(vars_list: Any, k: int, trail: Trail) -> bool:
    """At least k of the variables are True (1)."""
    state = get_sat_state(trail)
    items = _as_list(vars_list)
    lits = [sat_var_for(deref(v), trail) for v in items if is_var(deref(v))]

    cnf = _CardEnc.atleast(lits=lits, bound=k, top_id=state._counter,
                           encoding=_EncType.seqcounter)
    if cnf.nv > state._counter:
        state._counter = cnf.nv

    sat_push(trail)
    for clause in cnf.clauses:
        sat_add_clause(clause, trail)

    return True


def sat_exactly(vars_list: Any, k: int, trail: Trail) -> bool:
    """Exactly k of the variables are True (1)."""
    state = get_sat_state(trail)
    items = _as_list(vars_list)
    lits = [sat_var_for(deref(v), trail) for v in items if is_var(deref(v))]

    cnf = _CardEnc.equals(lits=lits, bound=k, top_id=state._counter,
                          encoding=_EncType.seqcounter)
    if cnf.nv > state._counter:
        state._counter = cnf.nv

    sat_push(trail)
    for clause in cnf.clauses:
        sat_add_clause(clause, trail)

    return True
```

### Gotcha: top_id

PySAT's `CardEnc` creates auxiliary variables starting from `top_id + 1`.
We must pass `state._counter` as `top_id` and then update `_counter` to
`cnf.nv` (the highest variable ID used by the encoding).  Otherwise,
subsequent `sat_var_for()` or `_fresh_sat_var()` calls could collide with
the encoding's auxiliary variables.

---

## 2. Pseudo-Boolean Constraints (Optional)

PySAT's `PBEnc` handles weighted sums: `sum(w_i * x_i) <op> k`.

```python
def sat_pb_at_most(vars_list: Any, weights: Any, k: int, trail: Trail) -> bool:
    """Weighted sum at most k: sum(w_i * x_i) <= k."""
    from pysat.pb import PBEnc as _PBEnc

    state = get_sat_state(trail)
    items = _as_list(vars_list)
    ws = _as_list(weights)
    lits = [sat_var_for(deref(v), trail) for v in items if is_var(deref(v))]

    cnf = _PBEnc.leq(lits=lits, weights=[int(w) for w in ws],
                      bound=k, top_id=state._counter)
    if cnf.nv > state._counter:
        state._counter = cnf.nv

    sat_push(trail)
    for clause in cnf.clauses:
        sat_add_clause(clause, trail)

    return True
```

Similar for `sat_pb_at_least` and `sat_pb_equals`.

---

## 3. Tests (Phase 3)

```python
class TestCardinality:

    def test_at_most_one(self):
        """at_most([X, Y, Z], 1): 4 solutions (000, 100, 010, 001)."""
        trail = Trail()
        x, y, z = Var(), Var(), Var()
        # Register vars by posting a trivial constraint
        for v in [x, y, z]:
            sat_var_for(v, trail)
        sat_at_most([x, y, z], 1, trail)
        count = sum(1 for _ in label_sat([x, y, z], trail))
        assert count == 4

    def test_at_least_two(self):
        """at_least([X, Y, Z], 2): 4 solutions (110, 101, 011, 111)."""
        trail = Trail()
        x, y, z = Var(), Var(), Var()
        for v in [x, y, z]:
            sat_var_for(v, trail)
        sat_at_least([x, y, z], 2, trail)
        count = sum(1 for _ in label_sat([x, y, z], trail))
        assert count == 4

    def test_exactly_two(self):
        """exactly([X, Y, Z], 2): 3 solutions (110, 101, 011)."""
        trail = Trail()
        x, y, z = Var(), Var(), Var()
        for v in [x, y, z]:
            sat_var_for(v, trail)
        sat_exactly([x, y, z], 2, trail)
        count = sum(1 for _ in label_sat([x, y, z], trail))
        assert count == 3

    def test_pigeonhole_unsat(self):
        """3 pigeons, 2 holes: UNSAT with at-most-one per hole."""
        trail = Trail()
        # p_ij = pigeon i in hole j
        p = [[Var() for _ in range(2)] for _ in range(3)]
        for row in p:
            for v in row:
                sat_var_for(v, trail)

        # Each pigeon in at least one hole
        for i in range(3):
            sat_at_least(p[i], 1, trail)

        # Each hole has at most one pigeon
        for j in range(2):
            sat_at_most([p[i][j] for i in range(3)], 1, trail)

        assert not sat_check(trail)

    def test_cardinality_backtracks(self):
        """Cardinality constraints retracted on backtrack."""
        trail = Trail()
        x, y, z = Var(), Var(), Var()
        for v in [x, y, z]:
            sat_var_for(v, trail)

        mark = trail.mark()
        sat_exactly([x, y, z], 0, trail)  # all must be 0
        count = sum(1 for _ in label_sat([x, y, z], trail))
        assert count == 1

        trail.undo(mark)  # retract
        # Now unconstrained: 8 solutions
        count = sum(1 for _ in label_sat([x, y, z], trail))
        assert count == 8
```

---

## Implementation Order

1. `sat_at_most()` with `top_id` tracking
2. `sat_at_least()`
3. `sat_exactly()`
4. Tests for cardinality
5. (Optional) `sat_pb_at_most/at_least/equals`
6. (Optional) PB tests
