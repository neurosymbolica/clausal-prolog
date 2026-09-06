"""Ordering of date/datetime/time via the comparison operators and the
sort/collection predicates, plus the incomparable-comparison error path.

date/datetime/time are real Python objects; the comparison operators reach
clpfd.fd_lt/fd_le/fd_gt/fd_ge, which order any comparable ground values.
"""

from __future__ import annotations

import datetime as dt
from fractions import Fraction

import pytest

from clausal.logic.atoms import char_atom, mint
from clausal.logic.variables import Var, Trail, deref
from clausal.logic.clpfd import (
    fd_lt, fd_le, fd_gt, fd_ge, _incomparable_order_error,
)
from clausal.logic.builtins.lists import (
    _sort__2, _msort__2, _min_list__2, _max_list__2,
)
from clausal.logic.exceptions import LogicException
from clausal.logic.trampoline import DONE


# ── Helpers ──────────────────────────────────────────────────────────────

def _run_list_builtin(fn, in_list):
    """Drive a (this_generator, _proceed, _fail, _catcher, lst, out, trail)
    list builtin; return one dereferenced output list per solution.

    Assumes a single deterministic solution — appropriate for deterministic
    list builtins (sort, msort, min_list, max_list) which yield at most one
    solution for a ground input list.

    For builtins that unify *out* with a single scalar (min_list, max_list)
    the scalar is wrapped in a one-element list so callers always see a
    uniform ``[[value, ...], ...]`` shape.
    """
    trail = Trail()
    out = Var()
    results = []
    for _cont, val in fn(None, "proceed", "fail", None, in_list, out, trail):
        if val is DONE:
            break
        resolved = deref(out)
        try:
            results.append([deref(x) for x in resolved])
        except TypeError as exc:
            # out was unified to a scalar (e.g. min_list/max_list): the
            # iteration above raised "object is not iterable".  Any other
            # TypeError (e.g. from a bad deref of a malformed term) is an
            # unrelated failure and must propagate, not produce a false green.
            if "iterable" not in str(exc):
                raise
            results.append([resolved])
    return results


def _assert_orderable_error(exc_info, context):
    term = exc_info.value.term
    assert term.functor == "error"
    inner = term.args[0]
    assert inner.functor == "type_error"
    assert inner.args[0] == mint("orderable")
    assert term.args[1] == context


# ── Comparison operators order dates/datetimes/times ─────────────────────

class TestComparisonOperators:
    def test_date_lt(self):
        assert fd_lt(dt.date(2020, 1, 1), dt.date(2021, 1, 1), Trail()) is True
        assert fd_lt(dt.date(2021, 1, 1), dt.date(2020, 1, 1), Trail()) is False

    def test_date_le_equal(self):
        assert fd_le(dt.date(2021, 1, 1), dt.date(2021, 1, 1), Trail()) is True
        assert fd_lt(dt.date(2021, 1, 1), dt.date(2021, 1, 1), Trail()) is False

    def test_date_gt_ge(self):
        assert fd_gt(dt.date(2022, 1, 1), dt.date(2021, 1, 1), Trail()) is True
        assert fd_ge(dt.date(2021, 1, 1), dt.date(2021, 1, 1), Trail()) is True

    def test_datetime_lt(self):
        a = dt.datetime(2020, 1, 1, 10, 0, 0)
        b = dt.datetime(2020, 1, 1, 11, 0, 0)
        assert fd_lt(a, b, Trail()) is True

    def test_time_lt(self):
        assert fd_lt(dt.time(9, 0, 0), dt.time(17, 0, 0), Trail()) is True


# ── Sort / collection predicates order dates ─────────────────────────────

class TestCollectionOrdering:
    def test_msort_orders_dates(self):
        a, b, c = dt.date(2021, 1, 1), dt.date(2019, 5, 5), dt.date(2020, 3, 3)
        assert _run_list_builtin(_msort__2, [a, b, c]) == [[b, c, a]]

    def test_sort_dedups_and_orders_dates(self):
        a, b, a2 = dt.date(2021, 1, 1), dt.date(2019, 5, 5), dt.date(2021, 1, 1)
        assert _run_list_builtin(_sort__2, [a, b, a2]) == [[b, a]]

    def test_min_list_dates(self):
        a, b = dt.date(2021, 1, 1), dt.date(2019, 5, 5)
        assert _run_list_builtin(_min_list__2, [a, b]) == [[b]]

    def test_max_list_dates(self):
        a, b = dt.date(2021, 1, 1), dt.date(2019, 5, 5)
        assert _run_list_builtin(_max_list__2, [a, b]) == [[a]]


# ── Incomparable comparisons raise a catchable type_error ────────────────

class TestIncomparableRaises:
    def test_date_vs_datetime(self):
        with pytest.raises(LogicException) as ei:
            fd_lt(dt.date(2020, 1, 1), dt.datetime(2020, 1, 1, 0, 0, 0), Trail())
        _assert_orderable_error(ei, "(<)/2")

    def test_naive_vs_aware(self):
        naive = dt.datetime(2020, 1, 1)
        aware = dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc)
        with pytest.raises(LogicException) as ei:
            fd_le(naive, aware, Trail())
        _assert_orderable_error(ei, "(=<)/2")

    def test_date_vs_int(self):
        with pytest.raises(LogicException) as ei:
            fd_lt(dt.date(2020, 1, 1), 5, Trail())
        _assert_orderable_error(ei, "(<)/2")

    def test_gt_surfaces_lt_context(self):
        # fd_gt(l, r) delegates to fd_lt(r, l), so the context is (<)/2 and
        # the culprit is the original left operand (dt.date here).
        with pytest.raises(LogicException) as ei:
            fd_gt(dt.date(2020, 1, 1), dt.datetime(2020, 1, 1), Trail())
        _assert_orderable_error(ei, "(<)/2")

    def test_culprit_is_second_operand(self):
        target = dt.datetime(2020, 1, 1, 0, 0, 0)
        with pytest.raises(LogicException) as ei:
            fd_lt(dt.date(2020, 1, 1), target, Trail())
        assert ei.value.term.args[0].args[1] == target


class TestVarVsNonNumericOperand:
    """A ground non-numeric operand ordered against an unbound var used to
    succeed by posting an FD ordering constraint whose unification hook then
    rejected EVERY later binding — including ones satisfying the comparison
    (``X < "banana", X is "apple"`` had 0 solutions).  Same broken-var shape
    as A12-F002 for ``==``; the ordering comparators must raise the same
    catchable type_error(orderable, ...) the ground incomparable path uses.
    Filed: todo/nonnumeric-comparison-on-unbound-var-rejects-all-later-bindings.md
    """

    def test_var_lt_str(self):
        with pytest.raises(LogicException) as ei:
            fd_lt(Var(), "banana", Trail())
        _assert_orderable_error(ei, "(<)/2")
        assert ei.value.term.args[0].args[1] == "banana"

    def test_str_lt_var(self):
        # the offending ground side may also be the LEFT operand
        with pytest.raises(LogicException) as ei:
            fd_lt("apple", Var(), Trail())
        _assert_orderable_error(ei, "(<)/2")
        assert ei.value.term.args[0].args[1] == "apple"

    def test_var_le_str(self):
        with pytest.raises(LogicException) as ei:
            fd_le(Var(), "banana", Trail())
        _assert_orderable_error(ei, "(=<)/2")

    def test_var_gt_str_surfaces_lt_context(self):
        # fd_gt delegates to fd_lt with swapped args, like the ground path
        with pytest.raises(LogicException) as ei:
            fd_gt(Var(), "banana", Trail())
        _assert_orderable_error(ei, "(<)/2")

    def test_var_ge_str_surfaces_le_context(self):
        with pytest.raises(LogicException) as ei:
            fd_ge(Var(), "banana", Trail())
        _assert_orderable_error(ei, "(=<)/2")

    def test_var_lt_date(self):
        with pytest.raises(LogicException) as ei:
            fd_lt(Var(), dt.date(2026, 6, 1), Trail())
        _assert_orderable_error(ei, "(<)/2")

    def test_var_lt_datetime(self):
        with pytest.raises(LogicException) as ei:
            fd_lt(Var(), dt.datetime(2026, 6, 1, 12, 0), Trail())
        _assert_orderable_error(ei, "(<)/2")

    def test_var_lt_quantity(self):
        from clausal.terms import Quantity
        from clausal.modules.units import Metre
        with pytest.raises(LogicException) as ei:
            fd_lt(Var(), Quantity(5, {Metre: 1}), Trail())
        _assert_orderable_error(ei, "(<)/2")

    def test_var_lt_decimal(self):
        from decimal import Decimal
        with pytest.raises(LogicException) as ei:
            fd_lt(Var(), Decimal("2.5"), Trail())
        _assert_orderable_error(ei, "(<)/2")

    def test_real_attr_var_lt_str(self):
        # A var already carrying a CLP(R) attribute triggers the real
        # dispatch on its own; the guard must fire BEFORE that dispatch, or
        # real_lt posts RealLtConstraint(X, "banana") unchecked (roborev
        # job 266 on 4bbc85d8: the Python path guarded after dispatch and
        # diverged from the C wrappers).
        trail = Trail()
        x = Var()
        assert fd_lt(x, 2.5, trail)  # gives x a REAL attribute
        with pytest.raises(LogicException) as ei:
            fd_lt(x, "banana", trail)
        _assert_orderable_error(ei, "(<)/2")

    def test_rational_attr_var_le_str(self):
        trail = Trail()
        x = Var()
        assert fd_le(x, Fraction(5, 2), trail)  # gives x a CLP(Q) attribute
        with pytest.raises(LogicException) as ei:
            fd_le(x, "banana", trail)
        _assert_orderable_error(ei, "(=<)/2")

    # ── var inside an expr tree (same defect, one level down) ────────────

    def test_var_tree_lt_str(self):
        from clausal.terms import Add
        with pytest.raises(LogicException) as ei:
            fd_lt(Add(left=Var(), right=1), "banana", Trail())
        _assert_orderable_error(ei, "(<)/2")

    def test_var_tree_le_date(self):
        from clausal.terms import Add
        with pytest.raises(LogicException) as ei:
            fd_le(Add(left=Var(), right=1), dt.date(2026, 6, 1), Trail())
        _assert_orderable_error(ei, "(=<)/2")

    def test_var_tree_gt_str_surfaces_lt_context(self):
        from clausal.terms import Add
        with pytest.raises(LogicException) as ei:
            fd_gt(Add(left=Var(), right=1), "banana", Trail())
        _assert_orderable_error(ei, "(<)/2")

    def test_var_tree_lt_int_still_posts(self):
        from clausal.terms import Add
        assert fd_lt(Add(left=Var(), right=1), 10, Trail())

    def test_ground_tree_lt_str_still_incomparable_error(self):
        # A fully-ground tree resolves to a scalar; 5 < "banana" stays the
        # ground-incomparable orderable error, not a guard reclassification.
        from clausal.terms import Add
        with pytest.raises(LogicException) as ei:
            fd_lt(Add(left=2, right=3), "banana", Trail())
        _assert_orderable_error(ei, "(<)/2")

    def test_ground_tree_lt_int_still_python_compare(self):
        from clausal.terms import Add
        assert fd_lt(Add(left=2, right=3), 10, Trail())
        assert not fd_lt(Add(left=2, right=3), 4, Trail())

    # ── controls: everything numeric/residual stays legal ────────────────

    def test_var_lt_int_still_narrows(self):
        from clausal.logic.clpfd import FD_KEY, domain_max
        from clausal.logic.variables import get_attr
        trail = Trail()
        x = Var()
        assert fd_lt(x, 4, trail)
        state = get_attr(x, FD_KEY)
        assert state is not None and domain_max(state.domain) <= 3

    def test_var_lt_var_still_legal(self):
        assert fd_lt(Var(), Var(), Trail())

    def test_var_lt_float_still_dispatches_clpr(self):
        trail = Trail()
        x = Var()
        assert fd_lt(x, 2.5, trail)

    def test_var_lt_fraction_still_dispatches_clpq(self):
        trail = Trail()
        x = Var()
        assert fd_lt(x, Fraction(5, 2), trail)

    def test_var_lt_expr_tree_still_legal(self):
        from clausal.terms import Add
        trail = Trail()
        x, y = Var(), Var()
        # NB keyword construction: Node's first dataclass field is
        # ``position``, so positional Add(y, 1) built the malformed node
        # Add(position=y, left=1, right=None) — which only "posted" through
        # the pre-fix unguarded leaf fall-through (the None leaf now raises
        # the typed unknown-leaf error, as any garbage leaf must).
        assert fd_lt(x, Add(left=y, right=1), trail)

    def test_ground_str_lt_still_python_compare(self):
        trail = Trail()
        assert fd_lt("apple", "banana", trail)
        assert not fd_lt("banana", "apple", trail)

    def test_engine_repro_raises_instead_of_losing_solutions(self, tmp_path):
        # The reported repro: 0 solutions for a satisfiable query, silently.
        # It must now surface a catchable LogicException at the comparison.
        import os
        from clausal.import_hook import _load_module
        from clausal.logic.solve import solve
        src = 'strlt_ok(X) <- ( X < "banana", X is "apple" )\n'
        path = os.path.join(str(tmp_path), "strcmp_repro.clausal")
        with open(path, "w") as f:
            f.write(src)
        mod = _load_module("strcmp_repro", path)
        with pytest.raises(LogicException) as ei:
            list(solve(mod.strlt_ok(Var()), mod.__dict__["$module"]))
        _assert_orderable_error(ei, "(<)/2")


class TestLegitimateTypeErrorPreserved:
    def test_mixed_rational_real_not_swallowed(self):
        # This must stay a plain TypeError with its "cannot mix" message,
        # NOT be converted to a type_error(orderable, ...).
        with pytest.raises(TypeError) as ei:
            fd_lt(Fraction(1, 2), 0.9, Trail())
        assert "mix" in str(ei.value).lower()


class TestHelper:
    def test_incomparable_order_error(self):
        culprit = dt.datetime(2020, 1, 1)
        exc = _incomparable_order_error(culprit, "(<)/2")
        assert isinstance(exc, LogicException)
        assert exc.term.functor == "error"
        assert exc.term.args[0].functor == "type_error"
        assert exc.term.args[0].args[0] == mint("orderable")
        assert exc.term.args[0].args[1] == culprit
        assert exc.term.args[1] == "(<)/2"


class TestEndToEnd:
    def test_fixture_ordering(self):
        from clausal.testing import (
            load_clausal_module, collect_tests, run_test,
        )
        mod = load_clausal_module("tests/fixtures/date_time_ordering.clausal")
        descs = collect_tests(mod)
        assert descs, "fixture defined no Test/1 clauses"
        for desc in descs:
            result = run_test(mod, desc)
            assert result.passed, f"fixture test {desc!r} failed"
