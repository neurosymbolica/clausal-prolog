# tests/clpq_port/test_row_scans.py
"""The row scans and merges of linear_forms.py (store.pl), made cheaper
without changing what they answer (complexity survey R1 and R4,
implementation_plans/clpq/2026-11-03-port-complexity-survey.md).

- delete_factor_hom/4 finds a variable by identity after dereferencing
  each term's variable, the first such term; no term's __eq__ is
  consulted.  (A C scan was tried and measured no faster; these tests
  pin the scan's answers whatever runs it.)
- add_linear_ffh/7 and add_linear_11h/5 compare by order keys looked up
  once a term (variable_ordering.order_key), as add_linear_f1h/6 does since
  the var-var fix: the same comparisons with the same outcomes.
- delete_factor/4 skips a row whose index (the ids of its variables)
  does not hold the variable, without scanning it (survey R1b);
  CLAUSAL_CLPQ_CHECK_ROW_INDEX=1 checks every skip against the scan.
"""
from functools import cmp_to_key

import pytest

from clausal.logic.clpq import linear_forms
from clausal.logic.clpq import variable_ordering
from clausal.logic.clpq.arithmetic import ZERO
from clausal.logic.clpq.attributes import SolverState, put_state
from clausal.logic.clpq.linear_forms import (
    LinearForm, add_homogeneous_parts, add_homogeneous_parts_scaled,
    delete_factor, delete_factor_homogeneous, row_variable_ids)
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


# ---------------------------------------------------------------- the row index

def _row(t, n):
    xs = _constrained(n, t)
    return xs, LinearForm((1, 1), ZERO, [(x, (i + 1, 1))
                                         for i, x in enumerate(xs)])


def test_a_miss_reads_no_term_once_the_row_is_indexed(monkeypatch):
    # The second scan of a row builds its index; after that a variable not
    # in the row is answered without dereferencing the row's terms (the
    # check mode scans, so it is off here).
    monkeypatch.setattr(linear_forms, "CHECK_ROW_INDEX", False)
    t = Trail()
    xs, form = _row(t, 50)
    absent = _constrained(1, t)[0]
    assert delete_factor(absent, form) is None        # marks the row
    assert delete_factor(absent, form) is None        # indexes it
    calls = [0]
    real = linear_forms.deref

    def counting(term):
        calls[0] += 1
        return real(term)

    monkeypatch.setattr(linear_forms, "deref", counting)
    for _ in range(3):
        assert delete_factor(absent, form) is None
    assert calls[0] <= 3, calls[0]            # the sought variable, once a call
    rest, coefficient = delete_factor(xs[17], form)
    assert coefficient == (18, 1)
    assert rest.terms == form.terms[:17] + form.terms[18:]


def test_a_row_is_indexed_at_its_second_scan_not_its_first():
    t = Trail()
    xs, form = _row(t, 4)
    assert form.variable_ids is None
    assert delete_factor(xs[0], form)[1] == (1, 1)
    assert form.variable_ids is False
    assert delete_factor(xs[0], form)[1] == (1, 1)
    assert form.variable_ids == {id(x) for x in xs}


def test_the_index_answers_as_the_scan_does():
    t = Trail()
    xs, form = _row(t, 12)
    others = _constrained(4, t)
    for v in xs + others + [Var()]:
        got = delete_factor(v, form)
        expected = _reference_delete(v, form.terms)
        if expected is None:
            assert got is None
        else:
            assert (got[0].terms, got[1]) == expected


def test_a_sought_variable_bound_to_a_number_is_scanned_as_before():
    # Not a variable, so the index is not asked: the scan compares the
    # number by identity with the dereferenced terms, as 1.3.3's ==/2.
    t = Trail()
    xs, form = _row(t, 3)
    assert delete_factor(Var(), form) is None
    row_variable_ids(form)                              # indexed
    five = 10 ** 30                                     # one object
    assert unify(xs[1], five, t)
    got = delete_factor(xs[1], form)
    assert (got[0].terms, got[1]) == _reference_delete(xs[1], form.terms)


def test_a_variable_unbound_by_undo_is_found_through_the_index():
    # A row built while X was bound to Y, then X unbound by the trail:
    # the index holds X itself as well as what it dereferenced to.
    t = Trail()
    x, y, z = _constrained(3, t)
    mark = t.mark()
    assert unify(x, y, t)
    form = LinearForm(ZERO, ZERO, [(x, (1, 1)), (z, (2, 1))])
    assert delete_factor(y, form)[1] == (1, 1)
    row_variable_ids(form)                              # indexed
    t.undo(mark)
    assert delete_factor(x, form)[1] == (1, 1)
    assert delete_factor(y, form) is None


def test_a_renamed_row_has_its_own_index():
    from clausal.logic.clpq.attribute_hooks import _rename_in_form
    t = Trail()
    xs, form = _row(t, 5)
    stand_in = _constrained(1, t)[0]
    assert delete_factor(stand_in, form) is None
    row_variable_ids(form)                              # indexed
    renamed = _rename_in_form(form, {id(xs[2]): stand_in})
    assert renamed is not form
    assert delete_factor(stand_in, renamed)[1] == (3, 1)
    assert delete_factor(xs[2], renamed) is None


def test_the_check_mode_catches_a_stale_index(monkeypatch):
    from clausal.logic.variables import deref
    # A row variable bound to another variable after the row was indexed
    # makes the index stale.  The solver never leaves a bound variable in
    # a row (DEVIATIONS.md D3: the hook replaces it by a stand-in first);
    # CLAUSAL_CLPQ_CHECK_ROW_INDEX=1 checks every miss against the scan.
    monkeypatch.setattr(linear_forms, "CHECK_ROW_INDEX", True)
    # Plain variables, so no hook runs; the younger one, in the row, is
    # bound to the older.
    t = Trail()
    y = Var()
    w = Var()
    form = LinearForm(ZERO, ZERO, [(w, (1, 1))])
    assert delete_factor(y, form) is None
    row_variable_ids(form)                              # indexed
    assert unify(w, y, t) and deref(w) is y
    with pytest.raises(AssertionError, match="row index"):
        delete_factor(y, form)


def test_the_store_keeps_its_indexes_right_through_bindings_and_undo(
        monkeypatch):
    from clausal.logic.clpq import holzbaur as h
    from clausal.logic.pending import drain
    from clausal.logic.variables import deref
    monkeypatch.setattr(linear_forms, "CHECK_ROW_INDEX", True)
    t = Trail()
    n = 12
    xs = [Var() for _ in range(n)]
    ys = [Var() for _ in range(n)]
    for a, b in zip(xs, xs[1:]):
        assert h.q_le(a, b, t)
    for y in ys:
        assert h.q_ge(y, 0, t)
    mark = t.mark()
    assert unify(xs, ys, t)
    assert any(True for _ in drain(t))
    s = Var()
    assert h.inf(xs[-1], s, t) and deref(s) == 0
    t.undo(mark)
    mark = t.mark()
    assert unify(xs, list(range(n)), t)
    assert any(True for _ in drain(t))
    t.undo(mark)
    assert h.q_ge(xs[0], 3, t)
    s = Var()
    assert h.inf(xs[-1], s, t) and deref(s) == 3


# ------------------------------------------ deleting the first term (R2)
#
# store.pl's delete_factor_hom/4 deletes the first term of [T|Ts] by
# answering Ts itself: the rest of the row is shared, not copied.  A
# binding that substitutes into every row of a chain deletes the first
# term of almost every row, and the trail keeps every row it replaced, so
# a copy there kept n^3 terms alive (survey R2).  delete_factor shares the
# rest of a long row the same way; reading the terms gives the same list
# as a copy would.

def _long_row(trail, count=40):
    xs = _constrained(count, trail)
    return xs, LinearForm(ZERO, ZERO, [(x, (i + 1, 1)) for i, x in enumerate(xs)])


def test_deleting_the_first_term_of_a_long_row_shares_the_rest():
    t = Trail()
    xs, form = _long_row(t)
    original = list(form.terms)
    got, coefficient = delete_factor(xs[0], form)
    assert coefficient == (1, 1)
    assert linear_forms.shares_terms(got, form.terms)       # no copy made
    again, coefficient = delete_factor(xs[1], got)
    assert coefficient == (2, 1)
    assert linear_forms.shares_terms(again, form.terms)
    assert again.terms == original[2:]
    assert form.terms == original                            # left alone


def test_a_shared_row_answers_every_reader_as_a_copy_would():
    t = Trail()
    xs, form = _long_row(t)
    got, _ = delete_factor(xs[0], form)
    assert linear_forms.term_count(got) == 39
    assert not linear_forms.has_no_terms(got)
    assert row_variable_ids(got) == {id(x) for x in xs[1:]}
    middle, coefficient = delete_factor(xs[20], got)          # not the first
    assert coefficient == (21, 1)
    assert middle.terms == form.terms[1:20] + form.terms[21:]
    assert got.terms == form.terms[1:]
    assert delete_factor(xs[0], got) is None


def test_a_short_row_is_copied_as_before():
    t = Trail()
    xs, form = _long_row(t, count=3)
    got, _ = delete_factor(xs[0], form)
    assert not linear_forms.shares_terms(got, form.terms)
    assert got.terms == form.terms[1:]


def test_substituting_a_number_keeps_the_shared_rest():
    from clausal.logic.clpq.linear_forms import normal_form_substitute
    t = Trail()
    xs, form = _long_row(t)
    number = LinearForm((7, 1), ZERO, [])
    got = normal_form_substitute(xs[0], number, form)
    assert got.constant == (7, 1)
    assert linear_forms.shares_terms(got, form.terms)
    assert got.terms == form.terms[1:]
