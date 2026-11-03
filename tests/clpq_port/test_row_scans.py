# tests/clpq_port/test_row_scans.py
"""The row scans and merges of linear_forms.py (store.pl), made cheaper
without changing what they answer (complexity survey R1 and R4,
implementation_plans/clpq/2026-11-03-port-complexity-survey.md).

- delete_factor_hom/4 finds a variable by identity after dereferencing
  each term's variable, the first such term, as the Python loop did; the
  scan now runs in C, comparing ids, so no term's __eq__ is consulted.
"""
from clausal.logic.clpq.arithmetic import ZERO
from clausal.logic.clpq.attributes import SolverState, put_state
from clausal.logic.clpq.linear_forms import (
    LinearForm, delete_factor, delete_factor_homogeneous)
from clausal.logic.variables import Trail, Var, unify


def _constrained(count, trail):
    xs = []
    for _ in range(count):
        x = Var()
        put_state(x, SolverState(variable_order=Var()), trail)
        xs.append(x)
    return xs


def _reference_delete(variable, terms):
    """The Python loop the scan replaced, kept as the reference."""
    from clausal.logic.variables import deref
    variable = deref(variable)
    for i, term in enumerate(terms):
        if term[0] is variable or deref(term[0]) is variable:
            return terms[:i] + terms[i + 1:], term[1]
    return None


# ---------------------------------------------------------------- the scan

def test_the_scan_finds_a_term_whose_variable_is_bound_to_the_sought_one():
    t = Trail()
    x, y, z = _constrained(3, t)
    w = Var()
    terms = [(x, (1, 1)), (w, (5, 1)), (z, (3, 1))]
    assert unify(w, y, t)                    # w now dereferences to y
    got = delete_factor_homogeneous(y, terms)
    assert got == ([(x, (1, 1)), (z, (3, 1))], (5, 1))
    assert got == _reference_delete(y, terms)


def test_the_scan_takes_the_first_of_two_matching_terms():
    t = Trail()
    x, y = _constrained(2, t)
    w = Var()
    assert unify(w, y, t)
    terms = [(x, (1, 1)), (w, (2, 1)), (y, (3, 1))]
    assert delete_factor_homogeneous(y, terms) == _reference_delete(y, terms)
    assert delete_factor_homogeneous(y, terms)[1] == (2, 1)


def test_the_scan_dereferences_the_sought_variable():
    t = Trail()
    x, y = _constrained(2, t)
    alias = Var()
    assert unify(alias, y, t)
    terms = [(x, (1, 1)), (y, (2, 1))]
    assert delete_factor_homogeneous(alias, terms) == ([(x, (1, 1))], (2, 1))


class _EqualToEverything:
    def __eq__(self, other):
        return True

    __hash__ = object.__hash__


def test_the_scan_compares_identity_never_equality():
    # A term bound to a value whose __eq__ says yes to anything is not the
    # variable; 1.3.3's ==/2 on a variable is identity.
    t = Trail()
    x, y = _constrained(2, t)
    w = Var()
    assert unify(w, _EqualToEverything(), t)
    terms = [(w, (1, 1)), (x, (2, 1))]
    assert delete_factor_homogeneous(y, terms) is None
    assert delete_factor_homogeneous(x, terms) == ([(w, (1, 1))], (2, 1))


def test_the_scan_misses_a_variable_not_in_the_row():
    t = Trail()
    xs = _constrained(6, t)
    form = LinearForm((1, 1), ZERO, [(x, (i + 1, 1)) for i, x in
                                     enumerate(xs[:5])])
    assert delete_factor(xs[5], form) is None
    assert delete_factor(Var(), form) is None
    assert delete_factor_homogeneous(xs[5], []) is None
