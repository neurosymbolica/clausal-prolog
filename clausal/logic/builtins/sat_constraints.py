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
    def _solver_block(constraints, trail, k):
        from clausal.logic.clpsat import sat_constraint_block
        if sat_constraint_block(constraints, solver_name, trail):
            yield None

    return _solver_block


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
    """pysat.model(Vars, Model) — Model is list of 0/1 for first solution."""
    from clausal.logic.clpsat import label_sat, _as_list
    from clausal.logic.variables import deref, unify
    items = _as_list(deref(vars_list))
    for _ in label_sat(items, trail):
        vals = [deref(v) for v in items]
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
