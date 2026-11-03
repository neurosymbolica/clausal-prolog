# tests/clpq_port/test_row_scans.py
"""The row scans and merges of linear_forms.py (store.pl), made cheaper
without changing what they answer (complexity survey R1 and R4,
implementation_plans/clpq/2026-11-03-port-complexity-survey.md).

- delete_factor_hom/4 finds a variable by identity after dereferencing
  each term's variable, the first such term, as the Python loop did; the
  scan now runs in C, comparing ids, so no term's __eq__ is consulted.
- add_linear_ffh/7 and add_linear_11h/5 compare by order keys looked up
  once a term (variable_ordering.order_key), as add_linear_f1h/6 does since
  the var-var fix: the same comparisons with the same outcomes.
"""
from functools import cmp_to_key

from clausal.logic.clpq import linear_forms
from clausal.logic.clpq import variable_ordering
from clausal.logic.clpq.arithmetic import ZERO
from clausal.logic.clpq.attributes import SolverState, put_state
from clausal.logic.clpq.linear_forms import (
    LinearForm, add_homogeneous_parts, add_homogeneous_parts_scaled,
    delete_factor, delete_factor_homogeneous)
from clausal.logic.clpq.variable_ordering import compare_variable_order
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


# ---------------------------------------------------------------- the merges

def _counting_lookups(monkeypatch):
    """Count the order lookups the merges make: compare_variable_order's
    state_of reads and order_key calls."""
    count = [0]

    def counted(function):
        def counting(argument):
            count[0] += 1
            return function(argument)
        return counting

    monkeypatch.setattr(variable_ordering, "state_of",
                        counted(variable_ordering.state_of))
    monkeypatch.setattr(linear_forms, "order_key",
                        counted(linear_forms.order_key))
    return count


def _interleaved(t, n):
    xs = _constrained(2 * n, t)
    xs.sort(key=cmp_to_key(compare_variable_order))
    a = [(x, (i + 1, 1)) for i, x in enumerate(xs) if i % 2 == 0]
    b = [(x, (i + 1, 1)) for i, x in enumerate(xs) if i % 2 == 1]
    return xs, a, b


def _reference_merge(terms_a, factor_a, terms_b, factor_b):
    """add_linear_ffh/7 by compare_variable_order at each step."""
    from clausal.logic.clpq.arithmetic import add, is_zero, multiply
    result = []
    i = j = 0
    while i < len(terms_a) and j < len(terms_b):
        relation = compare_variable_order(terms_a[i][0], terms_b[j][0])
        if relation == 0:
            k = add(multiply(terms_a[i][1], factor_a),
                    multiply(terms_b[j][1], factor_b))
            if not is_zero(k):
                result.append((terms_a[i][0], k))
            i += 1
            j += 1
        elif relation < 0:
            result.append((terms_a[i][0], multiply(terms_a[i][1], factor_a)))
            i += 1
        else:
            result.append((terms_b[j][0], multiply(terms_b[j][1], factor_b)))
            j += 1
    result += [(x, multiply(k, factor_a)) for x, k in terms_a[i:]]
    result += [(x, multiply(k, factor_b)) for x, k in terms_b[j:]]
    return result


def test_the_scaled_merge_looks_up_each_order_once(monkeypatch):
    t = Trail()
    _, a, b = _interleaved(t, 20)
    shared = a[3:8]                            # some variables in both
    b = sorted(b + [(x, (7, 1)) for x, _ in shared],
               key=lambda p: cmp_to_key(compare_variable_order)(p[0]))
    expected = _reference_merge(a, (2, 1), b, (-3, 1))
    count = _counting_lookups(monkeypatch)
    got = add_homogeneous_parts_scaled(a, (2, 1), b, (-3, 1))
    assert got == expected
    assert count[0] <= len(a) + len(b), (count[0], len(a) + len(b))


def test_the_plain_merge_looks_up_each_order_once(monkeypatch):
    t = Trail()
    _, a, b = _interleaved(t, 20)
    cancel = [(x, (-k[0], k[1])) for x, k in a[2:6]]   # sums to zero: dropped
    b = sorted(b + cancel,
               key=lambda p: cmp_to_key(compare_variable_order)(p[0]))
    expected = _reference_merge(a, (1, 1), b, (1, 1))
    count = _counting_lookups(monkeypatch)
    got = add_homogeneous_parts(a, b)
    assert got == expected
    assert count[0] <= len(a) + len(b), (count[0], len(a) + len(b))


def test_the_merges_fail_on_a_variable_without_an_order():
    t = Trail()
    x, y = _constrained(2, t)
    bare = Var()
    assert add_homogeneous_parts([(x, (1, 1))], [(bare, (1, 1))]) is None
    assert add_homogeneous_parts_scaled(
        [(x, (1, 1))], (1, 1), [(bare, (1, 1))], (1, 1)) is None
    # Never compared, so never failed: the rest of B is copied as it is.
    assert add_homogeneous_parts([], [(bare, (1, 1))]) == [(bare, (1, 1))]
