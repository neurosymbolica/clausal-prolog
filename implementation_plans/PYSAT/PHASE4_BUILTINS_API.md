# Phase 4: Builtins & Module API

Register PySAT operations as Clausal builtins so they can be called from
`.clausal` files using the `pysat.solver_name((...))` constraint block syntax.

---

## 1. Builtin Registration File

**File**: `clausal/logic/builtins/sat_constraints.py`

```python
"""PySAT Boolean satisfiability builtins.

Provides pysat.cadical/1, pysat.glucose/1, pysat.minisat/1, etc. for posting
Boolean constraints, plus pysat.solve/1, pysat.check/0, pysat.at_most/2,
pysat.at_least/2, pysat.exactly/2 for querying and cardinality.
"""

from __future__ import annotations

from clausal.logic.builtins._registry import _builtin


# ── Constraint block builtins (one per solver) ──────────────────────────────

def _make_solver_builtin(solver_name: str, builtin_name: str):
    """Factory: create a builtin that posts constraints via the named solver."""

    @_builtin(builtin_name, 1)
    def _solver_constraint_block(constraints, trail, k):
        from clausal.logic.clpsat import sat_constraint_block
        if sat_constraint_block(constraints, solver_name, trail):
            yield None

    return _solver_constraint_block


# Register all supported solvers
_make_solver_builtin('cadical195', 'pysat.cadical')
_make_solver_builtin('cadical153', 'pysat.cadical153')
_make_solver_builtin('g421', 'pysat.glucose')
_make_solver_builtin('g3', 'pysat.glucose3')
_make_solver_builtin('m22', 'pysat.minisat')
_make_solver_builtin('kissat', 'pysat.kissat')
_make_solver_builtin('lgl', 'pysat.lingeling')
_make_solver_builtin('mpl', 'pysat.maplesat')
_make_solver_builtin('mcb', 'pysat.maplechrono')
_make_solver_builtin('mg3', 'pysat.mergesat')
_make_solver_builtin('mc', 'pysat.minicard')


# ── Labeling / query builtins ───────────────────────────────────────────────

@_builtin("pysat.solve", 1)
def _pysat_solve(vars_list, trail, k):
    """pysat.solve(Vars) — enumerate satisfying 0/1 assignments."""
    from clausal.logic.clpsat import label_sat
    yield from label_sat(vars_list, trail)


@_builtin("pysat.check", 0)
def _pysat_check(trail, k):
    """pysat.check — succeed iff current SAT constraints are satisfiable."""
    from clausal.logic.clpsat import sat_check
    if sat_check(trail):
        yield None


@_builtin("pysat.count", 2)
def _pysat_count(vars_list, n, trail, k):
    """pysat.count(Vars, N) — N is the number of satisfying assignments."""
    from clausal.logic.clpsat import sat_count
    from clausal.logic.variables import unify, deref
    count = sat_count(deref(vars_list), trail)
    if unify(n, count, trail):
        yield None


@_builtin("pysat.model", 2)
def _pysat_model(vars_list, model, trail, k):
    """pysat.model(Vars, Model) — Model is a list of 0/1 for first solution."""
    from clausal.logic.clpsat import label_sat
    from clausal.logic.variables import deref, unify
    items = deref(vars_list)
    for _ in label_sat(items, trail):
        vals = [deref(v) for v in (items if isinstance(items, list) else [items])]
        if unify(model, vals, trail):
            yield None
        return  # first solution only


# ── Cardinality builtins ────────────────────────────────────────────────────

@_builtin("pysat.at_most", 2)
def _pysat_at_most(vars_list, k_val, trail, k):
    """pysat.at_most(Vars, K) — at most K variables are 1."""
    from clausal.logic.clpsat import sat_at_most
    from clausal.logic.variables import deref
    if sat_at_most(vars_list, int(deref(k_val)), trail):
        yield None


@_builtin("pysat.at_least", 2)
def _pysat_at_least(vars_list, k_val, trail, k):
    """pysat.at_least(Vars, K) — at least K variables are 1."""
    from clausal.logic.clpsat import sat_at_least
    from clausal.logic.variables import deref
    if sat_at_least(vars_list, int(deref(k_val)), trail):
        yield None


@_builtin("pysat.exactly", 2)
def _pysat_exactly(vars_list, k_val, trail, k):
    """pysat.exactly(Vars, K) — exactly K variables are 1."""
    from clausal.logic.clpsat import sat_exactly
    from clausal.logic.variables import deref
    if sat_exactly(vars_list, int(deref(k_val)), trail):
        yield None
```

---

## 2. Registration in constraints.py

**File**: `clausal/logic/builtins/constraints.py`

Add at the end of the file:

```python
# ── PySAT builtins ──────────────────────────────────────────────────────────
# Import to register pysat.* builtins (cadical, glucose, minisat, etc.)
import clausal.logic.builtins.sat_constraints  # noqa: F401
```

Alternatively, if builtins are auto-discovered, ensure `sat_constraints.py` is
in the discovery path.

---

## 3. Integration Tests

### Python API tests (`tests/test_clpsat.py`, extending Phase 1-3 tests)

```python
class TestPySATIntegration:

    def test_builtin_cadical_registered(self):
        """The pysat.cadical/1 builtin is findable."""
        from clausal.logic.builtins._registry import find_builtin
        assert find_builtin("pysat.cadical", 1) is not None

    def test_builtin_solve_registered(self):
        from clausal.logic.builtins._registry import find_builtin
        assert find_builtin("pysat.solve", 1) is not None

    def test_builtin_at_most_registered(self):
        from clausal.logic.builtins._registry import find_builtin
        assert find_builtin("pysat.at_most", 2) is not None
```

### .clausal file integration test (`tests/test_clpsat_clausal.py`)

```python
"""Test PySAT integration from .clausal files."""

# tests/data/sat_example.clausal:
#
# -use_module(pysat).
#
# exclusive(X, Y) :-
#     pysat.cadical((X | Y, ~X | ~Y)),
#     pysat.solve([X, Y]).
#
# one_of_three(X, Y, Z) :-
#     pysat.cadical((X | Y | Z,)),
#     pysat.at_most([X, Y, Z], 1),
#     pysat.solve([X, Y, Z]).

class TestClausalFile:

    def test_exclusive(self):
        """X | Y, ~X | ~Y -> XOR: 2 solutions."""
        from clausal.logic.solve import call
        from clausal.logic.variables import Var, Trail, deref
        trail = Trail()
        x, y = Var(), Var()
        sols = []
        for _ in call("exclusive", x, y, module=sat_example, trail=trail):
            sols.append((deref(x), deref(y)))
        assert sorted(sols) == [(0, 1), (1, 0)]

    def test_one_of_three(self):
        """Exactly one of X, Y, Z is true."""
        trail = Trail()
        x, y, z = Var(), Var(), Var()
        sols = []
        for _ in call("one_of_three", x, y, z, module=sat_example, trail=trail):
            sols.append((deref(x), deref(y), deref(z)))
        assert len(sols) == 3
        assert all(sum(s) == 1 for s in sols)
```

---

## 4. Documentation Examples

### Graph 3-Coloring

```prolog
% graph_coloring.clausal
-use_module(pysat).

% Each node has exactly one color
node_color(R, G, B) :-
    pysat.exactly([R, G, B], 1).

% Adjacent nodes differ
edge(R1, G1, B1, R2, G2, B2) :-
    pysat.cadical((~R1 | ~R2, ~G1 | ~G2, ~B1 | ~B2)).

% Triangle graph: a-b, b-c, a-c
triangle(AR, AG, AB, BR, BG, BB, CR, CG, CB) :-
    node_color(AR, AG, AB),
    node_color(BR, BG, BB),
    node_color(CR, CG, CB),
    edge(AR, AG, AB, BR, BG, BB),
    edge(BR, BG, BB, CR, CG, CB),
    edge(AR, AG, AB, CR, CG, CB),
    pysat.solve([AR, AG, AB, BR, BG, BB, CR, CG, CB]).
```

### N-Queens (Boolean encoding)

```prolog
% queens.clausal — N-Queens via PySAT
-use_module(pysat).

% Q(i,j) = 1 iff queen at row i, column j
queens(N, Board) :-
    make_board(N, Board),
    row_constraints(N, Board),
    col_constraints(N, Board),
    diag_constraints(N, Board),
    flatten(Board, Flat),
    pysat.solve(Flat).

row_constraints(N, Board) :-
    maplist(exactly_one, Board).    % exactly one queen per row

exactly_one(Row) :-
    pysat.exactly(Row, 1).

col_constraints(N, Board) :-
    numlist(1, N, Cols),
    maplist(col_exactly_one(Board), Cols).

col_exactly_one(Board, J) :-
    maplist(nth1(J), Board, Col),
    pysat.exactly(Col, 1).
```

---

## Implementation Order

1. Create `clausal/logic/builtins/sat_constraints.py`
2. Add import to `clausal/logic/builtins/constraints.py`
3. Verify builtins are registered (unit tests)
4. Create `.clausal` test files
5. Run integration tests
6. Write documentation examples
