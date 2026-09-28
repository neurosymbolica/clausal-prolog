"""Units side channel around CLP: dimension analysis, shadows, reattachment.

Spec: docs/superpowers/specs/2026-09-12-clp-units-side-channel-design.md
"""
from decimal import (Decimal, ROUND_HALF_UP, ROUND_HALF_EVEN, ROUND_HALF_DOWN,
                     ROUND_UP, ROUND_DOWN, ROUND_CEILING, ROUND_FLOOR)
from fractions import Fraction

import pytest

from clausal.logic.atoms import mint
from clausal.logic.cells import chars
from clausal import cell_args, cell_functor
from clausal.logic.exceptions import LogicException, error_prose
from clausal.terms import Quantity
from clausal.modules.countries.european_union import euro
from clausal.modules.countries.japan import yen
from clausal.modules.countries.kuwait import kwd


def _assert_system_error(ei, code):
    term = ei.value.term
    assert type(term) is tuple and cell_functor(term) == "error"
    inner = cell_args(term)[0]
    assert type(inner) is tuple and cell_functor(inner) == "system_error"
    assert cell_args(inner)[0] == mint(code)


class TestSystemErrorHelper:
    def test_builds_iso_shape(self):
        from clausal.logic.exceptions import system_error
        term = system_error("units_mismatch", "(==)/2: metre vs second")
        assert cell_functor(term) == "error"
        assert cell_functor(cell_args(term)[0]) == "system_error"
        assert cell_args(cell_args(term)[0]) == (mint("units_mismatch"),)
        assert cell_args(term)[1] == ("/", "==", 2)
        assert error_prose(term) == "metre vs second"


_MODES = [ROUND_HALF_UP, ROUND_HALF_EVEN, ROUND_HALF_DOWN, ROUND_UP,
          ROUND_DOWN, ROUND_CEILING, ROUND_FLOOR]


class TestExactNumberCurrency:
    def test_currency_quantity_keeps_fraction(self):
        q = Quantity(Fraction(1, 3), {euro: 1})
        assert type(q.value) is Fraction and q.value == Fraction(1, 3)

    def test_decimal_and_fraction_quantities_compare_equal(self):
        assert Quantity(Decimal("1500.00"), {euro: 1}) == Quantity(Fraction(1500), {euro: 1})
        assert hash(Quantity(Decimal("1500.00"), {euro: 1})) == hash(Quantity(Fraction(1500), {euro: 1}))

    def test_tagging_terminating_fraction_passes_precision_check(self):
        q = Quantity(Fraction(3, 2), euro)          # 1.50, within scale 2
        assert q.value == Fraction(3, 2)

    def test_tagging_non_terminating_fraction_fails_precision_check(self):
        from clausal.terms import CurrencyPrecisionError
        with pytest.raises(CurrencyPrecisionError):
            Quantity(Fraction(1, 3), euro)

    @pytest.mark.parametrize("mode", _MODES)
    @pytest.mark.parametrize("num", [-27, -25, -23, -5, -1, 0, 1, 5, 23, 25, 27, 125, 135])
    def test_fraction_rounding_agrees_with_decimal_rounding(self, mode, num):
        """Positive control: on terminating fractions the Fraction rounder and
        Decimal.quantize must give the same integer for every mode."""
        from clausal.terms import _round_fraction_to_int
        fr = Fraction(num, 10)                       # x.5 ties and non-ties, both signs
        expected = int(Decimal(num).scaleb(-1).quantize(Decimal(1), rounding=mode))
        assert _round_fraction_to_int(fr, mode) == expected

    def test_quantize_fraction_third_of_a_yen(self):
        from clausal.terms import _quantize_to_scale
        assert _quantize_to_scale(Fraction(1000, 3), 0, "half_even") == Decimal("333")
        assert _quantize_to_scale(Fraction(1, 3), 3, "half_even") == Decimal("0.333")

    def test_money_round_on_fraction_quantity(self):
        from clausal.logic.variables import Trail, Var, deref
        from clausal.modules.currency import _money_round_impl
        q = Quantity(Fraction(1000, 3), {yen: 1})
        out = Var()
        assert list(_money_round_impl(q, chars("half_even"), out, Trail())) == [None]
        assert deref(out) == Quantity(Decimal("333"), {yen: 1})


import random

from clausal.logic.variables import Trail, Var, deref, get_attr, put_attr, unify
from clausal.logic.units_constraint import UNITS_KEY, UnitState
from clausal.modules.py.units import metre, second, ampere, volt, ohm, watt, kilogram
from clausal.terms import Add, Sub, Mult, Div, FloorDiv, Mod, Pow, Negate, UnitsMismatch

M = {"metre": 1}


def _bin(cls, left, right):
    """Nodes carry a leading ``position`` field: operands go by keyword."""
    return cls(left=left, right=right)


def _neg(operand):
    return Negate(operand=operand)

S = {"second": 1}


def _dims_of_value(v):
    return dict(v.dims) if isinstance(v, Quantity) else {}


def _eval_with_quantity_arithmetic(t):
    """Fold a ground tree with Quantity's own operators — the oracle."""
    if isinstance(t, Add):
        return _eval_with_quantity_arithmetic(t.left) + _eval_with_quantity_arithmetic(t.right)
    if isinstance(t, Sub):
        return _eval_with_quantity_arithmetic(t.left) - _eval_with_quantity_arithmetic(t.right)
    if isinstance(t, Mult):
        return _eval_with_quantity_arithmetic(t.left) * _eval_with_quantity_arithmetic(t.right)
    if isinstance(t, Div):
        l, r = _eval_with_quantity_arithmetic(t.left), _eval_with_quantity_arithmetic(t.right)
        if type(l) is int and type(r) is int:
            return Fraction(l, r)      # the engine's own rule: int / int is rational, never a float
        return l / r
    if isinstance(t, Pow):
        return _eval_with_quantity_arithmetic(t.left) ** _eval_with_quantity_arithmetic(t.right)
    if isinstance(t, FloorDiv):
        return _eval_with_quantity_arithmetic(t.left) // _eval_with_quantity_arithmetic(t.right)
    if isinstance(t, Mod):
        return _eval_with_quantity_arithmetic(t.left) % _eval_with_quantity_arithmetic(t.right)
    if isinstance(t, Negate):
        return -_eval_with_quantity_arithmetic(t.operand)
    return t


_LEAVES = [2, 3, Quantity(3, M), Quantity(5, M), Quantity(4, S), Quantity(7, {}),
           Quantity(2, {kilogram: 1}), Quantity(Decimal("1.50"), {euro: 1}),
           Quantity(Fraction(1, 3), {euro: 1})]


def _random_tree(rng, depth):
    if depth == 0 or rng.random() < 0.3:
        return rng.choice(_LEAVES)
    op = rng.choice(["add", "sub", "mult", "div", "pow", "neg", "floordiv", "mod"])
    if op == "neg":
        return _neg(_random_tree(rng, depth - 1))
    if op == "pow":
        return _bin(Pow, _random_tree(rng, depth - 1), rng.choice([2, 3]))
    cls = {"add": Add, "sub": Sub, "mult": Mult, "div": Div,
           "floordiv": FloorDiv, "mod": Mod}[op]
    return _bin(cls, _random_tree(rng, depth - 1), _random_tree(rng, depth - 1))


class TestRuleTablePositiveControl:
    def test_ground_dims_agree_with_quantity_arithmetic(self):
        from clausal.logic.units_clp import ground_dims
        rng = random.Random(20260912)
        seen_ok = seen_err = 0
        for _ in range(3000):
            tree = _random_tree(rng, 3)
            try:
                expected = _dims_of_value(_eval_with_quantity_arithmetic(tree))
            except UnitsMismatch:
                with pytest.raises(LogicException) as ei:
                    ground_dims(tree)
                _assert_system_error(ei, "units_mismatch")
                seen_err += 1
                continue
            except (ZeroDivisionError, TypeError, OverflowError):
                continue          # arithmetic accident, not a units question
            assert ground_dims(tree) == expected, tree
            seen_ok += 1
        assert seen_ok > 500 and seen_err > 100   # the control actually exercised both arms

    def test_floordiv_and_mod_follow_divmod_rules(self):
        from clausal.logic.units_clp import ground_dims
        assert ground_dims(_bin(FloorDiv, Quantity(7, M), Quantity(2, M))) == {}
        assert ground_dims(_bin(Mod, Quantity(7, M), Quantity(2, M))) == M
        with pytest.raises(LogicException) as ei:
            ground_dims(_bin(FloorDiv, Quantity(7, M), 2))
        _assert_system_error(ei, "units_mismatch")


class TestInference:
    def test_fresh_var_beside_metre_in_sub_is_metre(self):
        from clausal.logic.units_clp import analyse
        x, y = Var(), Var()
        dl, dr, env = analyse(x, _bin(Sub, Quantity(3, M), y), "(==)/2")
        assert dl == M and dr == M
        assert env[x._id] == M and env[y._id] == M

    def test_product_with_one_unknown_factor_defaults_the_factor(self):
        from clausal.logic.units_clp import analyse
        total, qty = Var(), Var()
        dl, dr, env = analyse(total, _bin(Mult, Quantity(Decimal("2.00"), {euro: 1}), qty), "(==)/2")
        assert env[total._id] == {"euro": 1} and env[qty._id] == {}

    def test_ohms_law_infers_volt(self):
        from clausal.logic.units_clp import analyse
        v = Var()
        _, _, env = analyse(v, _bin(Mult, Quantity(2, {ampere: 1}), Quantity(3, ohm)), "(==)/2")
        assert env[v._id] == dict(volt._dims)

    def test_product_with_two_unknown_factors_is_undetermined(self):
        from clausal.logic.units_clp import analyse
        x, y, z = Var(), Var(), Var()
        put_attr(x, UNITS_KEY, UnitState(M), Trail())
        with pytest.raises(LogicException) as ei:
            analyse(x, _bin(Mult, y, z), "(==)/2")
        _assert_system_error(ei, "units_undetermined")

    def test_plain_number_beside_dimensioned_in_add_mismatches(self):
        from clausal.logic.units_clp import analyse
        with pytest.raises(LogicException) as ei:
            analyse(Var(), _bin(Add, Quantity(3, M), 1), "(==)/2")
        _assert_system_error(ei, "units_mismatch")

    def test_mixed_currencies_mismatch_and_name_both(self):
        from clausal.logic.units_clp import analyse
        from clausal.modules.countries.united_states import usd
        with pytest.raises(LogicException) as ei:
            analyse(Var(), _bin(Add, Quantity(Decimal("1.00"), {euro: 1}), Quantity(Decimal("1.00"), {usd: 1})), "(==)/2")
        _assert_system_error(ei, "units_mismatch")
        # `usd`, not `dollar`: the renderer names the BOUND identifier since
        # 2026-09-12, and `dollar` has not resolved since the ISO-code rename.
        # The property this asserts — the message names BOTH currencies — is
        # unchanged, and is now unambiguous by construction.
        assert ("euro" in ei.value.message
                and "usd" in ei.value.message)

    def test_declared_units_var_disagreeing_with_operand_mismatches(self):
        from clausal.logic.units_clp import analyse
        x = Var()
        put_attr(x, UNITS_KEY, UnitState(S), Trail())
        with pytest.raises(LogicException) as ei:
            analyse(x, Quantity(3, M), "(==)/2")
        _assert_system_error(ei, "units_mismatch")

    def test_solver_var_without_units_is_a_bare_number(self):
        from clausal.logic.units_clp import analyse
        from clausal.logic.clpfd import in_domain
        y = Var()
        assert in_domain(y, 1, 5, Trail())
        with pytest.raises(LogicException) as ei:
            analyse(Var(), _bin(Sub, Quantity(3, M), y), "(==)/2")
        _assert_system_error(ei, "units_mismatch")

    def test_dimensionless_result_is_bare(self):
        from clausal.logic.units_clp import analyse
        r = Var()
        _, _, env = analyse(r, _bin(Div, Quantity(6, M), Quantity(3, M)), "(==)/2")
        assert env[r._id] == {}

    def test_no_material_is_not_engaged(self):
        from clausal.logic.units_clp import _scan
        assert _scan(_bin(Add, Var(), 3)) is False
        assert _scan(_bin(Add, Var(), Quantity(3, M))) is True

    def test_non_numeric_leaf_is_not_engaged(self):
        from clausal.logic.units_clp import _scan, _FOREIGN
        assert _scan(_bin(Add, Quantity(3, M), "banana")) is _FOREIGN


def is_var_unbound(v):
    from clausal.logic.variables import is_var
    return is_var(deref(v))


class TestShadowLink:
    def test_shadow_created_once_and_trailed(self):
        from clausal.logic.units_clp import shadow_for, LINK_KEY
        t = Trail()
        x = Var()
        mark = t.mark()
        s = shadow_for(x, M, t)
        assert shadow_for(x, M, t) is s
        assert get_attr(x, UNITS_KEY).shadow is s
        assert get_attr(s, LINK_KEY).user is x
        t.undo(mark)
        assert get_attr(x, UNITS_KEY) is None and get_attr(s, LINK_KEY) is None

    def test_binding_shadow_binds_user_to_quantity(self):
        from clausal.logic.units_clp import shadow_for
        t = Trail()
        x = Var()
        s = shadow_for(x, M, t)
        assert unify(s, 5, t)
        assert deref(x) == Quantity(5, M)

    def test_binding_shadow_to_fraction_gives_exact_currency(self):
        from clausal.logic.units_clp import shadow_for
        t = Trail()
        x = Var()
        s = shadow_for(x, {euro: 1}, t)
        assert unify(s, Fraction(1, 3), t)
        v = deref(x)
        assert v.dims == {"euro": 1} and type(v.value) is Fraction and v.value == Fraction(1, 3)

    def test_binding_user_to_quantity_binds_shadow(self):
        from clausal.logic.units_clp import shadow_for
        t = Trail()
        x = Var()
        s = shadow_for(x, {euro: 1}, t)
        assert unify(x, Quantity(Decimal("1550.00"), {euro: 1}), t)
        assert deref(s) == 1550 and type(deref(s)) is int

    def test_binding_user_to_wrong_dims_fails_whole_unification(self):
        from clausal.logic.units_clp import shadow_for
        t = Trail()
        x = Var()
        s = shadow_for(x, M, t)
        assert not unify(x, Quantity(5, S), t)
        assert is_var_unbound(x) and is_var_unbound(s)

    def test_two_united_vars_unify_merges_shadows(self):
        from clausal.logic.units_clp import shadow_for
        t = Trail()
        x, y = Var(), Var()
        sx, sy = shadow_for(x, M, t), shadow_for(y, M, t)
        assert unify(x, y, t)
        assert unify(sx, 7, t)
        assert deref(y) == Quantity(7, M) and deref(sy) == 7

    def test_shadow_bound_to_foreign_var_transfers_link(self):
        from clausal.logic.units_clp import shadow_for, LINK_KEY
        t = Trail()
        x, w = Var(), Var()
        s = shadow_for(x, M, t)
        assert unify(s, w, t)
        assert get_attr(w, LINK_KEY).user is x
        assert unify(w, 9, t)
        assert deref(x) == Quantity(9, M)

    def test_strip_replaces_quantities_and_united_vars(self):
        from clausal.logic.units_clp import analyse, strip
        t = Trail()
        x = Var()
        tree = _bin(Sub, Quantity(Decimal("1550.00"), {euro: 1}), Quantity(Decimal("0.01"), {euro: 1}))
        _, _, env = analyse(x, tree, "(==)/2")
        l2, r2 = strip(x, env, t), strip(tree, env, t)
        assert get_attr(x, UNITS_KEY).shadow is l2
        assert isinstance(r2, Sub) and r2.left == 1550 and type(r2.left) is int
        assert r2.right == Fraction(1, 100) and type(r2.right) is Fraction

    def test_backtracking_undoes_shadow_binding(self):
        from clausal.logic.units_clp import shadow_for
        t = Trail()
        x = Var()
        s = shadow_for(x, M, t)
        mark = t.mark()
        assert unify(s, 5, t)
        t.undo(mark)
        assert is_var_unbound(x) and is_var_unbound(s)


class TestComparatorsEngine:
    """Through the module-level fd_* (the C wrappers when loaded)."""

    def _fd(self):
        import clausal.logic.clpfd as clpfd
        return clpfd

    def test_eq_var_against_quantity_binds(self):
        clpfd = self._fd()
        t, x = Trail(), Var()
        assert clpfd.fd_eq(x, Quantity(5, M), t)
        assert deref(x) == Quantity(5, M)

    def test_money_subtraction_binds_exact_euro(self):
        clpfd = self._fd()
        t, x = Trail(), Var()
        tree = _bin(Sub, Quantity(Decimal("1550.00"), {euro: 1}), Quantity(Decimal("50.00"), {euro: 1}))
        assert clpfd.fd_eq(x, tree, t)
        v = deref(x)
        assert v == Quantity(Decimal("1500.00"), {euro: 1})
        assert not isinstance(v.value, float)

    def test_money_division_by_three_is_exact_fraction(self):
        clpfd = self._fd()
        t, x = Trail(), Var()
        assert clpfd.fd_eq(x, _bin(Div, Quantity(Decimal("1000"), {yen: 1}), 3), t)
        v = deref(x)
        assert type(v.value) is Fraction and v.value == Fraction(1000, 3)

    def test_lt_then_bind(self):
        clpfd = self._fd()
        t, x = Trail(), Var()
        assert clpfd.fd_lt(x, Quantity(Decimal("1550.00"), {euro: 1}), t)
        assert unify(x, Quantity(Decimal("3.00"), {euro: 1}), t)
        t2, y = Trail(), Var()
        assert clpfd.fd_lt(y, Quantity(Decimal("1550.00"), {euro: 1}), t2)
        assert not unify(y, Quantity(Decimal("2000.00"), {euro: 1}), t2)

    def test_ne_then_bind(self):
        clpfd = self._fd()
        t, x = Trail(), Var()
        assert clpfd.fd_ne(x, Quantity(3, M), t)
        assert not unify(x, Quantity(3, M), t)
        assert unify(x, Quantity(4, M), t)

    def test_mixed_currencies_throw_before_any_solver_runs(self):
        clpfd = self._fd()
        from clausal.modules.countries.united_states import usd
        t, x = Trail(), Var()
        with pytest.raises(LogicException) as ei:
            clpfd.fd_eq(x, _bin(Add, Quantity(Decimal("1.00"), {euro: 1}), Quantity(Decimal("1.00"), {usd: 1})), t)
        _assert_system_error(ei, "units_mismatch")
        assert get_attr(x, UNITS_KEY) is None      # nothing was posted

    def test_metre_minus_second_throws(self):
        clpfd = self._fd()
        with pytest.raises(LogicException) as ei:
            clpfd.fd_eq(Var(), _bin(Sub, Quantity(3, M), Quantity(2, S)), Trail())
        _assert_system_error(ei, "units_mismatch")

    def test_ground_both_sides(self):
        clpfd = self._fd()
        t = Trail()
        assert clpfd.fd_eq(_bin(Sub, Quantity(Decimal("1550.00"), {euro: 1}), Quantity(Decimal("50.00"), {euro: 1})),
                           Quantity(Decimal("1500.00"), {euro: 1}), t)
        assert not clpfd.fd_lt(Quantity(5, M), Quantity(3, M), t)

    def test_declared_var_then_constraint(self):
        clpfd = self._fd()
        from clausal.logic.units_constraint import constrain_var_dims
        t, x = Trail(), Var()
        assert constrain_var_dims(x, M, t)
        assert clpfd.fd_eq(x, _bin(Add, Quantity(3, M), Quantity(1, M)), t)
        assert deref(x) == Quantity(4, M)

    def test_inferred_var_in_sub_then_bind_other(self):
        clpfd = self._fd()
        t, x, y = Trail(), Var(), Var()
        assert clpfd.fd_eq(x, _bin(Sub, Quantity(Decimal("1550.00"), {euro: 1}), y), t)
        assert unify(y, Quantity(Decimal("50.00"), {euro: 1}), t)
        assert deref(x) == Quantity(Decimal("1500.00"), {euro: 1})

    def test_dimensionless_result_is_plain_number(self):
        clpfd = self._fd()
        t, r = Trail(), Var()
        assert clpfd.fd_eq(r, _bin(Div, Quantity(6, M), Quantity(3, M)), t)
        assert deref(r) == 2 and not isinstance(deref(r), Quantity)

    def test_units_var_against_atom_keeps_the_clpz_expression_error(self):
        clpfd = self._fd()
        from clausal.logic.units_constraint import constrain_var_dims
        t, x = Trail(), Var()
        assert constrain_var_dims(x, M, t)
        with pytest.raises(LogicException) as ei:
            clpfd.fd_eq(x, mint("banana"), t)
        # the same error as without units: Scryer's clpz formal since Q3
        # (2026-09-28), type_error(evaluable, banana) before
        assert cell_functor(cell_args(ei.value.term)[0]) == "domain_error"

    def test_plain_constraints_untouched(self):
        clpfd = self._fd()
        t, x = Trail(), Var()
        assert clpfd.fd_eq(x, _bin(Add, 2, 3), t)
        assert deref(x) == 5 and get_attr(x, UNITS_KEY) is None

    def test_attr_key_spellings_agree(self):
        from clausal.logic.clpfd import FD_KEY
        from clausal.logic.clpq import Q_KEY
        from clausal.logic.clpr import REAL_KEY
        assert (FD_KEY, Q_KEY, REAL_KEY) == ("fd", "clpq", "real")


class TestDomainAndLabel:
    def test_in_domain_with_money_bounds_then_label(self):
        import clausal.logic.clpfd as clpfd
        t, x = Trail(), Var()
        assert clpfd.in_domain([x], Quantity(Decimal("1"), {yen: 1}), Quantity(Decimal("3"), {yen: 1}), t)
        seen = []
        for _ in clpfd.label([x], t):
            seen.append(deref(x))
        assert seen == [Quantity(1, {yen: 1}), Quantity(2, {yen: 1}), Quantity(3, {yen: 1})]
        assert all(not isinstance(q.value, float) for q in seen)

    def test_in_domain_with_metre_bounds_and_constraint(self):
        import clausal.logic.clpfd as clpfd
        t, w, h = Trail(), Var(), Var()
        assert clpfd.in_domain([w, h], Quantity(1, M), Quantity(6, M), t)
        area = Var()
        assert clpfd.fd_eq(area, _bin(Mult, w, h), t)
        assert clpfd.fd_eq(area, Quantity(12, {metre: 2}), t)
        assert clpfd.fd_eq(w, Quantity(3, M), t)
        for _ in clpfd.label([w, h], t):
            assert deref(h) == Quantity(4, M)
            break
        else:
            pytest.fail("no solution")

    def test_in_domain_plain_bound_beside_quantity_bound_throws(self):
        import clausal.logic.clpfd as clpfd
        with pytest.raises(LogicException) as ei:
            clpfd.in_domain([Var()], 1, Quantity(3, M), Trail())
        _assert_system_error(ei, "units_mismatch")

    def test_in_domain_bounds_disagreeing_throws(self):
        import clausal.logic.clpfd as clpfd
        with pytest.raises(LogicException) as ei:
            clpfd.in_domain([Var()], Quantity(1, M), Quantity(3, S), Trail())
        _assert_system_error(ei, "units_mismatch")

    def test_in_domain_on_declared_var_with_other_dims_throws(self):
        import clausal.logic.clpfd as clpfd
        from clausal.logic.units_constraint import constrain_var_dims
        t, x = Trail(), Var()
        assert constrain_var_dims(x, S, t)
        with pytest.raises(LogicException) as ei:
            clpfd.in_domain([x], Quantity(1, M), Quantity(3, M), t)
        _assert_system_error(ei, "units_mismatch")

    def test_plain_in_domain_and_label_untouched(self):
        import clausal.logic.clpfd as clpfd
        t, x = Trail(), Var()
        assert clpfd.in_domain([x], 1, 2, t)
        assert [deref(x) for _ in clpfd.label([x], t)] == [1, 2]


import os


class TestSurfaceFixture:
    def test_fixture_passes_every_test_clause(self):
        from clausal.testing import run_file
        path = os.path.join(os.path.dirname(__file__), "fixtures", "units_clp_side_channel.clausal")
        results = run_file(path)
        failed = [(r.name, r.error) for r in results.results if not r.passed]
        assert not failed, failed
        assert len(results.results) >= 20      # the runner actually collected the clauses


class TestReviewRoundOne:
    """Findings of the 2026-09-12 branch review, each reproduced then fixed."""

    # F1: FD builtins beyond the comparators must not post on the user's var
    def test_all_different_on_united_vars_labels(self):
        import clausal.logic.clpfd as clpfd
        t, x, y = Trail(), Var(), Var()
        assert clpfd.in_domain([x, y], Quantity(1, M), Quantity(2, M), t)
        assert clpfd.all_different([x, y], t)
        sols = sorted((deref(x).value, deref(y).value) for _ in clpfd.label([x, y], t))
        assert sols == [(1, 2), (2, 1)]
        assert all(isinstance(deref(v), Quantity) or is_var_unbound(v) for v in (x, y))

    def test_sum_of_money_vars_binds_total_with_unit(self):
        import clausal.logic.clpfd as clpfd
        t, a, b, total = Trail(), Var(), Var(), Var()
        assert clpfd.in_domain([a, b], Quantity(1, {yen: 1}), Quantity(3, {yen: 1}), t)
        assert list(clpfd.fd_sum([a, b], mint("#="), total, t)) == [None]
        assert unify(a, Quantity(1, {yen: 1}), t) and unify(b, Quantity(3, {yen: 1}), t)
        assert deref(total) == Quantity(4, {yen: 1})

    def test_sum_mixing_dims_throws(self):
        import clausal.logic.clpfd as clpfd
        t, a, b = Trail(), Var(), Var()
        assert clpfd.in_domain([a], Quantity(1, M), Quantity(3, M), t)
        assert clpfd.in_domain([b], Quantity(1, S), Quantity(3, S), t)
        with pytest.raises(LogicException) as ei:
            list(clpfd.fd_sum([a, b], mint("#="), Var(), t))
        _assert_system_error(ei, "units_mismatch")

    def test_scalar_product_with_plain_coefficients(self):
        import clausal.logic.clpfd as clpfd
        t, a, b, total = Trail(), Var(), Var(), Var()
        assert clpfd.in_domain([a, b], Quantity(1, M), Quantity(3, M), t)
        assert list(clpfd.fd_scalar_product([2, 3], [a, b], mint("#="), total, t)) == [None]
        assert unify(a, Quantity(1, M), t) and unify(b, Quantity(2, M), t)
        assert deref(total) == Quantity(8, M)

    def test_chain_on_united_vars(self):
        import clausal.logic.clpfd as clpfd
        t, a, b = Trail(), Var(), Var()
        assert clpfd.in_domain([a, b], Quantity(1, M), Quantity(2, M), t)
        assert clpfd.chain([a, b], "lt", t)
        sols = [(deref(a).value, deref(b).value) for _ in clpfd.label([a, b], t)]
        assert sols == [(1, 2)]

    def test_element_on_united_list(self):
        import clausal.logic.clpfd as clpfd
        t, i, v = Trail(), Var(), Var()
        assert clpfd.in_domain([i], 1, 3, t)
        # element/3 with a Var index enumerates the index itself.
        sols = [(deref(i), deref(v)) for _ in
                clpfd.fd_element(i, [Quantity(5, M), Quantity(7, M), Quantity(9, M)], v, t)]
        assert sols == [(1, Quantity(5, M)), (2, Quantity(7, M)), (3, Quantity(9, M))]

    def test_direct_solver_post_on_united_var_is_loud(self):
        """The safety net: a builtin that bypasses the side channel leaves FD
        state on the user's var; reattachment then throws instead of failing."""
        import clausal.logic.clpfd as clpfd
        from clausal.logic.units_constraint import constrain_var_dims
        t, x = Trail(), Var()
        assert constrain_var_dims(x, M, t)
        clpfd._ensure_fd(x, t)                      # what a bypassing builtin does
        with pytest.raises(LogicException) as ei:
            clpfd.fd_eq(x, Quantity(5, M), t)
        _assert_system_error(ei, "units_unsupported")

    # F2: Fraction-valued money must interoperate with Decimal-valued money
    def test_fraction_and_decimal_money_arithmetic(self):
        a = Quantity(Fraction(1000, 3), {yen: 1})
        b = Quantity(Decimal("1"), {yen: 1})
        assert (a + b).value == Fraction(1003, 3)
        assert (b - a).value == Fraction(-997, 3)
        assert (a * Decimal("3")).value == 1000
        assert (b / a).value == Fraction(3, 1000)
        assert type((a + b).value) is Fraction

    # F3: exponent errors are type/instantiation errors, not units mismatches
    def test_unbound_exponent_is_instantiation_error(self):
        from clausal.logic.units_clp import analyse
        with pytest.raises(LogicException) as ei:
            analyse(Var(), _bin(Pow, Quantity(2, M), Var()), "(==)/2")
        assert cell_args(ei.value.term)[0] == mint("instantiation_error")

    def test_fractional_exponent_is_type_error(self):
        from clausal.logic.units_clp import analyse
        with pytest.raises(LogicException) as ei:
            analyse(Var(), _bin(Pow, Quantity(2, M), 2.5), "(==)/2")
        assert cell_functor(cell_args(ei.value.term)[0]) == "type_error"

    def test_not_a_power_reads_sensibly(self):
        from clausal.logic.units_clp import analyse
        with pytest.raises(LogicException) as ei:
            analyse(_bin(Pow, Var(), 2), Quantity(3, M), "(==)/2")
        _assert_system_error(ei, "units_mismatch")
        assert "share a name" not in ei.value.message

    # F4: non-integral quantity bounds are rejected like non-integer plain ones
    def test_in_domain_non_integral_money_bounds_rejected(self):
        import clausal.logic.clpfd as clpfd
        with pytest.raises(LogicException) as ei:
            clpfd.in_domain([Var()], Quantity(Decimal("0.01"), {euro: 1}), Quantity(Decimal("0.05"), {euro: 1}), Trail())
        _assert_system_error(ei, "units_unsupported")

    # F5: > and >= name themselves in the error
    def test_gt_context_names_gt(self):
        import clausal.logic.clpfd as clpfd
        with pytest.raises(LogicException) as ei:
            clpfd.fd_gt(Quantity(5, M), Quantity(3, S), Trail())
        assert cell_args(ei.value.term)[1] == ("/", ">", 2)
        with pytest.raises(LogicException) as ei:
            clpfd.fd_ge(Quantity(5, M), Quantity(3, S), Trail())
        assert cell_args(ei.value.term)[1] == ("/", ">=", 2)

    # F6: ground arithmetic has // and % on quantities, matching divmod_/4
    def test_quantity_floordiv_and_mod(self):
        assert Quantity(7, M) // Quantity(2, M) == Quantity(3, {})
        assert Quantity(7, M) % Quantity(2, M) == Quantity(1, M)
        with pytest.raises(UnitsMismatch):
            Quantity(7, M) // 2
        assert Quantity(7, {}) // 2 == Quantity(3, {})


class TestReviewRoundTwo:
    def test_tuples_in_on_united_var_is_loud_not_silent(self):
        import clausal.logic.clpfd as clpfd
        t, x, y = Trail(), Var(), Var()
        assert clpfd.in_domain([x], Quantity(1, S), Quantity(2, S), t)
        assert clpfd.in_domain([y], Quantity(1, M), Quantity(2, M), t)
        # round 18: refused up front at posting (earlier than the reattachment net)
        with pytest.raises(LogicException) as ei:
            clpfd.tuples_in([[x, y]], [(1, 2), (2, 1)], t)
        _assert_system_error(ei, "units_unsupported")

    def test_global_cardinality_keys_share_the_dimension(self):
        import clausal.logic.clpfd as clpfd
        t, x, y = Trail(), Var(), Var()
        assert clpfd.in_domain([x, y], Quantity(1, M), Quantity(2, M), t)
        assert clpfd.global_cardinality([x, y], [(Quantity(1, M), 1), (Quantity(2, M), 1)], t)
        sols = sorted((deref(x).value, deref(y).value) for _ in clpfd.label([x, y], t))
        assert sols == [(1, 2), (2, 1)]
        with pytest.raises(LogicException) as ei:
            clpfd.global_cardinality([x, y], [(Quantity(1, S), 2)], Trail())
        _assert_system_error(ei, "units_mismatch")

    def test_dimensionless_quantity_bounds_take_the_plain_path(self):
        import clausal.logic.clpfd as clpfd
        t, x = Trail(), Var()
        assert clpfd.in_domain([x], Quantity(1, {}), Quantity(3, {}), t)
        assert get_attr(x, UNITS_KEY) is None
        assert not unify(x, 99, t)
        assert [deref(x) for _ in clpfd.label([x], t)] == [1, 2, 3]

    def test_scalar_product_dimensionless_quantity_coefficient_is_stripped(self):
        import clausal.logic.clpfd as clpfd
        t, a, total = Trail(), Var(), Var()
        assert clpfd.in_domain([a], Quantity(1, M), Quantity(3, M), t)
        assert list(clpfd.fd_scalar_product([Quantity(2, {})], [a], mint("#="), total, t)) == [None]
        assert unify(a, Quantity(3, M), t)
        assert deref(total) == Quantity(6, M)

    def test_fraction_money_times_float_RAISES(self):
        """Until 2026-09-18 this pinned the shortest-repr bridge (1.5 read as
        Decimal('1.5'), exact).  RULED Q5/Q6 option C: at run time a float
        beside a Fraction is refused; the written-literal case belongs at
        construction/declaration.  Exact operands still multiply exactly."""
        from clausal.logic.exceptions import LogicException
        with pytest.raises(LogicException) as ei:
            Quantity(Fraction(1000, 3), {yen: 1}) * 1.5
        assert "exact_number" in str(ei.value)
        q = Quantity(Fraction(1000, 3), {yen: 1}) * Fraction(3, 2)
        assert not isinstance(q.value, float) and q.value == 500
        assert isinstance(q.value, Decimal)     # integral → int → currency Decimal (round 7)

    def test_strip_keeps_source_position(self):
        from clausal.logic.units_clp import analyse, strip
        t, x = Trail(), Var()
        tree = Sub(left=Quantity(3, M), right=x, position=(1, 2, 3, 4))
        _, _, env = analyse(Var(), tree, "(==)/2")
        assert strip(tree, env, t).position == (1, 2, 3, 4)

    def test_zcompare_bad_order_wins_over_units(self):
        import clausal.logic.clpfd as clpfd
        with pytest.raises(LogicException) as ei:
            clpfd.zcompare(chars("<"), Quantity(1, M), Quantity(1, S), Trail())
        assert cell_functor(cell_args(ei.value.term)[0]) == "type_error"
        with pytest.raises(LogicException) as ei:
            clpfd.zcompare(mint("<"), Quantity(1, M), Quantity(1, S), Trail())
        _assert_system_error(ei, "units_mismatch")


class TestReviewRoundThree:
    def test_dimensionless_quantity_with_bare_fraction(self):
        assert (Quantity(7, {}) + Fraction(1, 3)).value == Fraction(22, 3)
        assert (Fraction(1, 3) + Quantity(7, {})).value == Fraction(22, 3)
        assert (Quantity(7, {}) - Fraction(1, 3)).value == Fraction(20, 3)
        assert (Fraction(1, 3) - Quantity(7, {})).value == Fraction(-20, 3)
        assert (Quantity(7, {}) // Fraction(2)).value == 3
        assert (Quantity(7, {}) % Fraction(2)).value == 1

    def test_declared_var_with_plain_bounds_is_a_mismatch(self):
        import clausal.logic.clpfd as clpfd
        from clausal.logic.units_constraint import constrain_var_dims
        t, x = Trail(), Var()
        assert constrain_var_dims(x, M, t)
        with pytest.raises(LogicException) as ei:
            clpfd.in_domain([x], 1, 3, t)
        _assert_system_error(ei, "units_mismatch")

    def test_declared_var_given_solver_state_directly_is_loud_at_label(self):
        import clausal.logic.clpfd as clpfd
        from clausal.logic.units_constraint import constrain_var_dims
        t, x = Trail(), Var()
        assert constrain_var_dims(x, M, t)
        clpfd._ensure_fd(x, t)                       # a bypassing builtin
        with pytest.raises(LogicException) as ei:
            list(clpfd.label([x], t))
        _assert_system_error(ei, "units_unsupported")

    def test_dimensionless_declared_var_binds_exact_rational(self):
        from clausal.logic.units_constraint import constrain_var_dims
        t, x = Trail(), Var()
        assert constrain_var_dims(x, {}, t)
        assert unify(x, Fraction(4, 3), t)
        assert deref(x) == Fraction(4, 3)

    def test_plain_bound_beside_quantity_bound_message(self):
        import clausal.logic.clpfd as clpfd
        with pytest.raises(LogicException) as ei:
            clpfd.in_domain([Var()], 1, Quantity(3, {}), Trail())
        assert "share a name" not in ei.value.message

    def test_sum_bad_operator_wins_over_units(self):
        import clausal.logic.clpfd as clpfd
        t = Trail()
        with pytest.raises(LogicException) as ei:
            list(clpfd.fd_sum([Quantity(1, M), Quantity(1, S)], chars("#="), Var(), t))
        assert cell_functor(cell_args(ei.value.term)[0]) == "type_error"

    def test_circuit_refuses_united_vars(self):
        import clausal.logic.clpfd as clpfd
        t, x, y = Trail(), Var(), Var()
        assert clpfd.in_domain([x, y], Quantity(1, M), Quantity(2, M), t)
        with pytest.raises(LogicException) as ei:
            list(clpfd.fd_circuit([x, y], t))
        _assert_system_error(ei, "units_unsupported")


class TestReviewRoundFour:
    def test_zero_exponent_in_push_position(self):
        from clausal.logic.units_clp import analyse
        dl, dr, env = analyse(Quantity(3, {}), _bin(Pow, Var(), 0), "(==)/2")
        assert dl == {} and dr == {}
        with pytest.raises(LogicException) as ei:
            analyse(Quantity(3, M), _bin(Pow, Var(), 0), "(==)/2")
        _assert_system_error(ei, "units_mismatch")

    def test_sum_with_sub_unit_money_is_loud(self):
        import clausal.logic.clpfd as clpfd
        t, x, total = Trail(), Var(), Var()
        with pytest.raises(LogicException) as ei:
            list(clpfd.fd_sum([Quantity(Decimal("10.50"), {euro: 1}), x], mint("#="), total, t))
        _assert_system_error(ei, "units_unsupported")
        with pytest.raises(LogicException) as ei:
            list(clpfd.fd_scalar_product([1], [Quantity(Decimal("10.50"), {euro: 1})], mint("#="), total, t))
        _assert_system_error(ei, "units_unsupported")

    def test_reflected_floordiv_and_mod(self):
        assert (7 // Quantity(2, {})).value == 3
        assert (7 % Quantity(2, {})).value == 1
        with pytest.raises(UnitsMismatch):
            7 // Quantity(2, M)
        with pytest.raises(UnitsMismatch):
            7 % Quantity(2, M)

    def test_chain_bad_relation_wins_over_units(self):
        import clausal.logic.clpfd as clpfd
        assert clpfd.chain([Quantity(1, M), Quantity(2, S)], "bogus", Trail()) is False

    def test_circuit_accepts_dimensionless_quantities(self):
        import clausal.logic.clpfd as clpfd
        t, a = Trail(), Var()
        assert clpfd.in_domain([a], 1, 2, t)
        sols = [deref(a) for _ in clpfd.fd_circuit([a, Quantity(1, {})], t)]
        assert sols == [2]        # node 2's successor is node 1, so node 1's is node 2


class TestReviewRoundFive:
    def test_sub_unit_money_is_loud_in_every_list_builtin(self):
        import clausal.logic.clpfd as clpfd
        cents = Quantity(Decimal("10.50"), {euro: 1})
        with pytest.raises(LogicException) as ei:
            clpfd.all_different([cents, Var()], Trail())
        _assert_system_error(ei, "units_unsupported")
        with pytest.raises(LogicException) as ei:
            list(clpfd.fd_element(Var(), [cents], Var(), Trail()))
        _assert_system_error(ei, "units_unsupported")
        with pytest.raises(LogicException) as ei:
            clpfd.global_cardinality([Var()], [(cents, 1)], Trail())
        _assert_system_error(ei, "units_unsupported")

    @pytest.mark.parametrize("neg7", [-7, Decimal("-7"), Fraction(-7)])
    def test_floordiv_and_mod_floor_regardless_of_storage(self, neg7):
        assert (Quantity(neg7, {}) // 2).value == -4
        assert (Quantity(neg7, {}) % 2).value == 1
        assert (Quantity(neg7, M) // Quantity(2, M)).value == -4
        assert (Quantity(neg7, M) % Quantity(2, M)).value == 1
        assert (7 // Quantity(neg7, {})).value == -1
        assert (7 % Quantity(neg7, {})).value == -0 and (7 % Quantity(neg7, {})).value == 0

    def test_money_mod_keeps_decimal_and_floors(self):
        q = Quantity(Decimal("-7.50"), {euro: 1}) % Quantity(Decimal("2.00"), {euro: 1})
        assert q.value == Decimal("0.50") and isinstance(q.value, Decimal)

    def test_c_wrapper_integer_fast_path(self):
        import clausal.logic.clpfd as clpfd
        assert clpfd.fd_eq(3, 3, Trail()) and not clpfd.fd_ne(3, 3, Trail())
        assert clpfd.fd_lt(2, 3, Trail()) and clpfd.fd_le(3, 3, Trail())


class TestReviewRoundSix:
    def test_sub_unit_dimensionless_in_scalar_product_and_circuit_is_loud(self):
        import clausal.logic.clpfd as clpfd
        with pytest.raises(LogicException) as ei:
            list(clpfd.fd_scalar_product([Quantity(Decimal("2.50"), {})], [Var()], mint("#="), Var(), Trail()))
        _assert_system_error(ei, "units_unsupported")
        with pytest.raises(LogicException) as ei:
            list(clpfd.fd_circuit([Quantity(Decimal("1.5"), {})], Trail()))
        _assert_system_error(ei, "units_unsupported")

    def test_ground_money_division_is_exact_and_agrees_with_clp(self):
        import clausal.logic.clpfd as clpfd
        ground = Quantity(Decimal("1000"), {yen: 1}) / 3
        assert type(ground.value) is Fraction and ground.value == Fraction(1000, 3)
        t, x = Trail(), Var()
        assert clpfd.fd_eq(x, _bin(Div, Quantity(Decimal("1000"), {yen: 1}), 3), t)
        assert deref(x) == ground
        half = Quantity(Decimal("1550.00"), {euro: 1}) / 2
        assert isinstance(half.value, Decimal) and half.value == Decimal("775")
        third = Quantity(10, M) / Quantity(3, S)
        assert type(third.value) is Fraction and third.value == Fraction(10, 3)   # exact, as `is` folds 10/3
        assert type((Quantity(3, M) / 2).value) is Fraction
        assert type((Quantity(4, M) / 2).value) is int and (Quantity(4, M) / 2).value == 2
        assert (Quantity(3, M) / 2.0).value == 1.5         # a float operand keeps float semantics

    def test_fraction_to_decimal_if_terminating(self):
        from clausal.terms import _fraction_to_decimal_if_terminating as f
        assert f(Fraction(775)) == Decimal("775")
        assert f(Fraction(1, 8)) == Decimal("0.125")
        assert f(Fraction(3, 20)) == Decimal("0.15")
        assert f(Fraction(1, 3)) is None

    def test_scan_returns_foreign_without_raising(self):
        from clausal.logic.units_clp import _scan, _FOREIGN
        assert _scan(_bin(Add, Quantity(3, M), mint("banana"))) is _FOREIGN

    def test_units_flag_is_set_by_quantity_and_declaration(self):
        from clausal.logic import _units_flag
        assert _units_flag.active       # this test module built quantities at import


class TestReviewRoundSeven:
    def test_integral_fraction_presents_as_int_on_the_ground_path(self):
        x = Quantity(Fraction(1000, 3), {yen: 1}) * 3
        assert not isinstance(x.value, Fraction) and x.value == 1000
        m = Quantity(Fraction(3, 2), M) * 2
        assert type(m.value) is int and m.value == 3
        assert type(Quantity(Fraction(4, 2), M).value) is int
        assert type(Quantity(Fraction(4, 2), {yen: 1}).value) is Decimal   # currency coerces int

    def test_units_flag_negative_control_in_a_fresh_process(self):
        import subprocess, sys
        code = ("import clausal.logic.clpfd, clausal.logic.units_clp\n"
                "from clausal.logic import _units_flag\n"
                "print(_units_flag.active)\n"
                "from clausal.modules.units import kilometre\n"
                "from clausal.terms import Quantity\n"
                "Quantity(5, kilometre)\n"
                "print(_units_flag.active)\n")
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                             cwd=os.path.dirname(os.path.dirname(__file__)))
        assert out.returncode == 0, out.stderr
        lines = out.stdout.split()
        assert lines[0] == "False" and lines[-1] == "True", out.stdout

    def test_exact_decimal_beyond_context_precision(self):
        from clausal.terms import _fraction_to_decimal_if_terminating as f, _quantize_to_scale
        big = 10 ** 30 + 1
        assert f(Fraction(big)) == Decimal(big) and str(f(Fraction(big))) == str(big)
        assert f(Fraction(big, 100)) == Decimal(f"{big}E-2")
        assert _quantize_to_scale(Fraction(big, 3), 2, "half_even") == Decimal(f"{(big * 100 + 1) // 3}E-2")

    def test_reified_comparison_with_units(self):
        import clausal.logic.clpfd as clpfd
        with pytest.raises(LogicException) as ei:
            clpfd.reify_fd("lt", Quantity(1, M), Quantity(2, S), Trail())
        _assert_system_error(ei, "units_mismatch")
        assert ei.value.message.startswith("reify(lt)/3")
        assert clpfd.reify_fd("lt", Quantity(1, M), Quantity(2, M), Trail()) is True
        t, x = Trail(), Var()
        assert clpfd.reify_fd("eq", x, Quantity(2, M), t) is None
        assert get_attr(x, UNITS_KEY) is None      # round 21: a None answer declares nothing


class TestReviewRoundEight:
    def test_ground_int_division_agrees_with_clp(self):
        import clausal.logic.clpfd as clpfd
        ground = Quantity(10, M) / Quantity(3, S)
        t, x = Trail(), Var()
        assert clpfd.fd_eq(x, _bin(Div, Quantity(10, M), Quantity(3, S)), t)
        assert deref(x) == ground and type(deref(x).value) is Fraction

    def test_plain_non_integer_operand_is_the_builtins_business(self):
        import clausal.logic.clpfd as clpfd
        # a plain 1.5 beside a dimensionless quantity: the builtin's own integer
        # guard decides (quiet failure, as before), not the whole-units guard
        assert list(clpfd.fd_sum([1.5, Quantity(5, {})], mint("#="), Var(), Trail())) == []

    def test_expression_element_beside_units_is_loud(self):
        import clausal.logic.clpfd as clpfd
        with pytest.raises(LogicException) as ei:
            clpfd.all_different([Quantity(1, M), _bin(Add, Var(), 1)], Trail())
        _assert_system_error(ei, "units_unsupported")

    def test_label_targets_is_flag_gated(self):
        from clausal.logic.units_clp import label_targets
        from clausal.logic import _units_flag
        saved = _units_flag.active
        try:
            _units_flag.active = False
            v = [Var()]
            assert label_targets(v) == v
        finally:
            _units_flag.active = saved


class TestReviewRoundNine:
    def test_float_spelled_whole_metres_are_whole_units(self):
        import clausal.logic.clpfd as clpfd
        t, x = Trail(), Var()
        assert clpfd.in_domain([x], Quantity(1.0, M), Quantity(3.0, M), t)
        assert clpfd.all_different([Quantity(2.0, M), x], t)
        assert sorted(deref(x).value for _ in clpfd.label([x], t)) == [1, 3]
        with pytest.raises(LogicException) as ei:
            clpfd.all_different([Quantity(2.5, M), Var()], Trail())
        _assert_system_error(ei, "units_unsupported")

    def test_as_whole(self):
        from clausal.logic.units_clp import _as_whole
        assert _as_whole(2.0) == 2 and _as_whole(Decimal("2.00")) == 2 and _as_whole(Fraction(4, 2)) == 2
        assert _as_whole(2.5) is None and _as_whole(Fraction(1, 3)) is None and _as_whole(True) is None

    def test_quantity_target_beside_plain_bounds_is_loud(self):
        import clausal.logic.clpfd as clpfd
        with pytest.raises(LogicException) as ei:
            clpfd.in_domain([Quantity(3, M)], 1, 5, Trail())
        _assert_system_error(ei, "units_mismatch")

    def test_gt_strips_once(self, monkeypatch):
        import clausal.logic.clpfd as clpfd
        import clausal.logic.units_clp as uc
        calls = []
        real = uc.strip_for_solver
        monkeypatch.setattr(clpfd, "_strip_for_solver", lambda *a: (calls.append(a[2]), real(*a))[1])
        t, x = Trail(), Var()
        assert clpfd.fd_gt(x, Quantity(1, M), t)
        assert calls == ["(>)/2"]


class TestReviewRoundTen:
    def test_remainder_is_exact_beyond_the_decimal_context(self):
        big = Quantity(Decimal("1E+30"), M) % Quantity(Decimal("7"), M)
        assert big.value == 1 and isinstance(big.value, Decimal)
        q = Quantity(Decimal("1E+30"), M) // Quantity(Decimal("7"), M)
        assert q.value == 10 ** 30 // 7
        assert (Quantity(10 ** 30, M) % Quantity(7, M)).value == 1

    def test_ground_dims_on_a_non_ground_tree_is_the_iso_term(self):
        from clausal.logic.units_clp import ground_dims
        with pytest.raises(LogicException) as ei:
            ground_dims(_bin(Mult, Var(), Quantity(2, M)))
        _assert_system_error(ei, "units_undetermined")


class TestReviewRoundEleven:
    def test_ground_quantity_target_in_domain_whole_and_not(self):
        import clausal.logic.clpfd as clpfd
        assert clpfd.in_domain([Quantity(2.0, M)], Quantity(1, M), Quantity(3, M), Trail())
        assert not clpfd.in_domain([Quantity(5, M)], Quantity(1, M), Quantity(3, M), Trail())
        with pytest.raises(LogicException) as ei:
            clpfd.in_domain([Quantity(Decimal("2.5"), M)], Quantity(1, M), Quantity(3, M), Trail())
        _assert_system_error(ei, "units_unsupported")

    def test_ground_dims_rejects_a_free_var_in_additive_position(self):
        from clausal.logic.units_clp import ground_dims
        with pytest.raises(LogicException) as ei:
            ground_dims(_bin(Add, Var(), Quantity(2, M)))
        _assert_system_error(ei, "units_undetermined")


class TestReviewRoundTwelve:
    def test_negative_power_is_exact_and_agrees_with_division(self):
        assert (Quantity(3, M) ** -1).value == Fraction(1, 3)
        assert (Quantity(3, M) ** -1) == 1 / Quantity(3, M)
        m = Quantity(Decimal("3.00"), {euro: 1}) ** -1
        assert type(m.value) is Fraction and m.value == Fraction(1, 3)
        assert (Quantity(2, M) ** -2).value == Fraction(1, 4) and (Quantity(2, M) ** -2).dims == {"metre": -2}
        assert (Quantity(2.0, M) ** -1).value == 0.5            # float stays float

    def test_chain_has_no_whole_units_guard(self):
        # chain/2 feeds the comparators, so the whole-units guard does not
        # apply. A sub-unit money operand still overflows today in chain's
        # own FD-to-CLP(Q) promotion — pre-existing and unit-independent
        # (chain([X, Fraction(21, 2)], "lt") overflows on the baseline too);
        # todo/chain-rational-operand-fd-promotion-overflow-2026-09-12.md.
        import clausal.logic.clpfd as clpfd
        t, x = Trail(), Var()
        assert clpfd.chain([x, Quantity(Decimal("11.00"), {euro: 1})], "lt", t)
        assert unify(x, Quantity(Decimal("3.00"), {euro: 1}), t)
        t2, y = Trail(), Var()
        assert clpfd.chain([y, Quantity(Decimal("11.00"), {euro: 1})], "lt", t2)
        assert not unify(y, Quantity(Decimal("12.00"), {euro: 1}), t2)

    def test_as_whole_rejects_non_finite_decimal_quietly(self):
        from clausal.logic.units_clp import _as_whole
        assert _as_whole(Decimal("Infinity")) is None and _as_whole(Decimal("NaN")) is None


class TestReviewRoundThirteen:
    def test_cumulative_refuses_units_material_loudly(self):
        import clausal.logic.clpfd as clpfd
        t, s1 = Trail(), Var()
        assert clpfd.in_domain([s1], 0, 5, t)
        with pytest.raises(LogicException) as ei:
            clpfd.cumulative([(s1, Quantity(2, S), 1)], 1, t)
        _assert_system_error(ei, "units_unsupported")
        u = Var()
        assert clpfd.in_domain([u], Quantity(0, S), Quantity(5, S), t)
        with pytest.raises(LogicException) as ei:
            clpfd.cumulative([(u, 2, 1)], 1, t)
        _assert_system_error(ei, "units_unsupported")
        assert clpfd.cumulative([(s1, 2, 1)], 1, t) is True      # plain case untouched

    def test_zcompare_unbound_order_needs_whole_units(self):
        import clausal.logic.clpfd as clpfd
        t, x, order = Trail(), Var(), Var()
        with pytest.raises(LogicException) as ei:
            clpfd.zcompare(order, x, Quantity(Decimal("10.50"), {euro: 1}), t)
        _assert_system_error(ei, "units_unsupported")
        t2, y, order2 = Trail(), Var(), Var()
        assert clpfd.zcompare(order2, y, Quantity(3, M), t2)
        assert unify(y, Quantity(1, M), t2)
        assert deref(order2) == mint("<")
        # A ground Order delegates to the comparators, but zcompare pre-ensures
        # FD state first, so a rational operand overflows in the promotion —
        # the same pre-existing defect as chain/2 (filed todo).

    def test_two_shadows_with_distinct_links_unify(self):
        from clausal.logic.units_clp import shadow_for
        t, x, y = Trail(), Var(), Var()
        sx, sy = shadow_for(x, M, t), shadow_for(y, M, t)
        assert unify(sx, sy, t)
        assert unify(sy, 4, t)
        assert deref(x) == Quantity(4, M) and deref(y) == Quantity(4, M)
        t2, a, b, w = Trail(), Var(), Var(), Var()
        sa, sb = shadow_for(a, M, t2), shadow_for(b, M, t2)
        assert unify(sa, w, t2) and unify(w, sb, t2)
        assert unify(sa, 9, t2)
        assert deref(a) == Quantity(9, M) and deref(b) == Quantity(9, M)


class TestReviewRoundFourteen:
    def test_cumulative_first_in_a_fresh_process(self):
        import subprocess, sys
        code = ("from clausal.modules.units import metre   # sets the units flag at import\n"
                "import clausal.logic.clpfd as clpfd\n"
                "from clausal.logic.variables import Trail, Var\n"
                "t, s1 = Trail(), Var()\n"
                "assert clpfd.in_domain([s1], 0, 5, t)\n"
                "print(clpfd.cumulative([(s1, 2, 1)], 1, t))\n")
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                             cwd=os.path.dirname(os.path.dirname(__file__)))
        assert out.returncode == 0 and out.stdout.strip() == "True", out.stderr

    def test_scan_primes_its_own_imports_in_a_fresh_process(self):
        import subprocess, sys
        code = ("from clausal.logic.units_clp import _scan\n"
                "from clausal.terms import Quantity\n"
                "from clausal.modules.units import metre\n"
                "print(_scan(Quantity(1, metre)))\n")
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                             cwd=os.path.dirname(os.path.dirname(__file__)))
        assert out.returncode == 0 and out.stdout.strip() == "True", out.stderr

    def test_powers_of_a_decimal_are_exact_past_the_context(self):
        base = Quantity(Decimal("1.1"), M)
        assert (base ** 30).value == Fraction(11, 10) ** 30           # 31 significant digits, exact
        assert isinstance((base ** 30).value, Decimal)
        assert (base ** -30).value == Fraction(1, Fraction(11, 10) ** 30)
        assert (base ** -30) == 1 / (base ** 30)
        assert (Quantity(2, M) ** -2).value == Fraction(1, 4)

    def test_dimensionless_quantity_target_with_dimensionless_bounds(self):
        import clausal.logic.clpfd as clpfd
        assert clpfd.in_domain([Quantity(2, {})], Quantity(1, {}), Quantity(3, {}), Trail())
        assert not clpfd.in_domain([Quantity(5, {})], Quantity(1, {}), Quantity(3, {}), Trail())
        with pytest.raises(LogicException) as ei:
            clpfd.in_domain([Quantity(Decimal("2.5"), {})], Quantity(1, {}), Quantity(3, {}), Trail())
        _assert_system_error(ei, "units_unsupported")


class TestReviewRoundFifteen:
    def test_declared_and_directly_posted_var_is_refused_even_when_shadowed(self):
        import clausal.logic.clpfd as clpfd
        from clausal.logic.units_constraint import constrain_var_dims
        t, x = Trail(), Var()
        assert constrain_var_dims(x, M, t)
        clpfd._ensure_fd(x, t)                 # a bypassing builtin
        for goal in (lambda: clpfd.in_domain([x], Quantity(1, M), Quantity(3, M), t),
                     lambda: clpfd.all_different([x, Var()], t),
                     lambda: clpfd.fd_eq(x, _bin(Add, Quantity(1, M), Var()), t),
                     lambda: list(clpfd.label([x], t))):
            with pytest.raises(LogicException) as ei:
                goal()
            _assert_system_error(ei, "units_unsupported")

    def test_dimensionless_quantity_target_with_plain_bounds(self):
        import clausal.logic.clpfd as clpfd
        assert clpfd.in_domain([Quantity(2, {})], 1, 3, Trail())
        assert not clpfd.in_domain([Quantity(5, {})], 1, 3, Trail())

    def test_cumulative_takes_dimensionless_quantities(self):
        import clausal.logic.clpfd as clpfd
        t, s1 = Trail(), Var()
        assert clpfd.in_domain([s1], 0, 5, t)
        assert clpfd.cumulative([(s1, Quantity(3, {}), Quantity(1, {}))], Quantity(2, {}), t) is True

    def test_gt_and_zcompare_scan_once(self, monkeypatch):
        import clausal.logic.clpfd as clpfd
        import clausal.logic.units_clp as uc
        calls = []
        real = uc.strip_for_solver
        monkeypatch.setattr(clpfd, "_strip_for_solver", lambda *a: (calls.append(a[2]), real(*a))[1])
        t, x = Trail(), Var()
        assert clpfd.fd_gt(x, _bin(Add, Var(), 1), t)          # not engaged, still scanned once
        assert calls == ["(>)/2"]
        calls.clear()
        t2, y = Trail(), Var()
        assert clpfd.zcompare(mint("<"), y, Quantity(3, M), t2)
        assert calls == ["zcompare/3"]


class TestReviewRoundSixteen:
    def test_chain_and_zcompare_take_sub_unit_money_and_plain_rationals(self):
        import clausal.logic.clpfd as clpfd
        t, x = Trail(), Var()
        assert clpfd.chain([x, Quantity(Decimal("10.50"), {euro: 1})], "lt", t)
        assert unify(x, Quantity(Decimal("3.25"), {euro: 1}), t)
        t2, y = Trail(), Var()
        assert clpfd.chain([y, Quantity(Decimal("10.50"), {euro: 1})], "lt", t2)
        assert not unify(y, Quantity(Decimal("12.00"), {euro: 1}), t2)
        t3, z = Trail(), Var()
        assert clpfd.chain([z, Fraction(21, 2)], "lt", t3)        # the plain shape, once an OverflowError
        assert unify(z, Fraction(1, 2), t3)
        t4, w = Trail(), Var()
        assert clpfd.zcompare(mint("<"), w, Quantity(Decimal("10.50"), {euro: 1}), t4)
        assert unify(w, Quantity(Decimal("1.25"), {euro: 1}), t4)

    def test_chain_and_zcompare_still_post_fd_for_integers(self):
        import clausal.logic.clpfd as clpfd
        t, a, b = Trail(), Var(), Var()
        assert clpfd.in_domain([a, b], 1, 2, t)
        assert clpfd.chain([a, b], "lt", t)
        assert [(deref(a), deref(b)) for _ in clpfd.label([a, b], t)] == [(1, 2)]
        t2, p, q, order = Trail(), Var(), Var(), Var()
        assert clpfd.in_domain([p, q], 1, 2, t2)
        assert clpfd.zcompare(order, p, q, t2)
        assert unify(p, 1, t2) and unify(q, 2, t2)
        assert deref(order) == mint("<")


class TestReviewRoundSeventeen:
    def test_zcompare_unbound_order_over_ground_sub_unit_money(self):
        import clausal.logic.clpfd as clpfd
        t, order = Trail(), Var()
        assert clpfd.zcompare(order, Quantity(Decimal("1.50"), {euro: 1}), Quantity(Decimal("2.50"), {euro: 1}), t)
        assert deref(order) == mint("<")
        t2, order2 = Trail(), Var()
        assert clpfd.zcompare(order2, Quantity(Decimal("2.50"), {euro: 1}), Quantity(Decimal("2.50"), {euro: 1}), t2)
        assert deref(order2) == mint("=")

    def test_cumulative_malformed_task_fails_the_same_way_with_units_on(self):
        import clausal.logic.clpfd as clpfd
        from clausal.logic import _units_flag
        assert _units_flag.active
        t, s1 = Trail(), Var()
        assert clpfd.in_domain([s1], 0, 5, t)
        with pytest.raises(ValueError):
            clpfd.cumulative([(s1, 2)], 1, t)


class TestReviewRoundEighteen:
    def test_tuples_in_ground_quantity_is_refused_not_dropped(self):
        import clausal.logic.clpfd as clpfd
        t, y = Trail(), Var()
        assert clpfd.in_domain([y], 1, 2, t)
        with pytest.raises(LogicException) as ei:
            clpfd.tuples_in([[Quantity(1, M), y]], [(1, 2), (2, 1)], t)
        _assert_system_error(ei, "units_unsupported")
        with pytest.raises(LogicException) as ei:
            clpfd.tuples_in([[1, y]], [(Quantity(1, M), 2)], t)
        _assert_system_error(ei, "units_unsupported")
        # dimensionless quantities are plain numbers: the column constrains
        assert clpfd.tuples_in([[Quantity(1, {}), y]], [(1, 2), (2, 1)], t)
        assert deref(y) == 2


class TestReviewRoundNineteen:
    def test_non_finite_currency_value_is_refused_catchably(self):
        import clausal.logic.clpfd as clpfd
        from clausal.logic.units_constraint import to_solver_number
        inf = Decimal("Infinity")
        assert to_solver_number(inf) is inf
        bad = Quantity(inf, {euro: 1})
        with pytest.raises(LogicException):
            clpfd.fd_eq(Var(), bad, Trail())


class TestReviewRoundTwenty:
    def test_non_finite_decimal_ground_arithmetic_does_not_raise_python_errors(self):
        inf = Quantity(Decimal("Infinity"), {euro: 1})
        assert (inf / 2).value == Decimal("Infinity")
        assert (inf * Quantity(Decimal("2"), {})).value == Decimal("Infinity")
        assert (inf ** 2).value == Decimal("Infinity")
        assert (Quantity(Decimal("7"), {}) // Quantity(Decimal("Infinity"), {})).value == 0
        nan = Quantity(Decimal("NaN"), {euro: 1}) + Quantity(Fraction(1, 2), {euro: 1})
        assert nan.value.is_nan()

    def test_global_cardinality_counts_are_cardinalities(self):
        import clausal.logic.clpfd as clpfd
        t, x, y = Trail(), Var(), Var()
        assert clpfd.in_domain([x, y], 1, 2, t)
        assert clpfd.global_cardinality([x, y], [(1, Quantity(1, {})), (2, Quantity(1, {}))], t)
        sols = sorted((deref(x), deref(y)) for _ in clpfd.label([x, y], t))
        assert sols == [(1, 2), (2, 1)]
        with pytest.raises(LogicException) as ei:
            clpfd.global_cardinality([Var()], [(1, Quantity(1, M))], Trail())
        _assert_system_error(ei, "units_unsupported")

    def test_ground_dims_rejects_declared_and_solver_vars(self):
        from clausal.logic.units_clp import ground_dims
        from clausal.logic.units_constraint import constrain_var_dims
        import clausal.logic.clpfd as clpfd
        t, x, y = Trail(), Var(), Var()
        assert constrain_var_dims(x, M, t)
        assert clpfd.in_domain([y], 1, 3, t)
        with pytest.raises(LogicException) as ei:
            ground_dims(_bin(Add, x, Quantity(2, M)))
        _assert_system_error(ei, "units_undetermined")
        with pytest.raises(LogicException) as ei:            # a bare solver var is dimensionless:
            ground_dims(_bin(Add, y, Quantity(2, M)))         # the mismatch is met first
        assert cell_args(cell_args(ei.value.term)[0])[0] in (mint("units_undetermined"), mint("units_mismatch"))

    def test_zcompare_equals_branch_scans_once(self, monkeypatch):
        import clausal.logic.clpfd as clpfd
        import clausal.logic.units_clp as uc
        calls = []
        real = uc.strip_for_solver
        monkeypatch.setattr(clpfd, "_strip_for_solver", lambda *a: (calls.append(a[2]), real(*a))[1])
        t, y = Trail(), Var()
        assert clpfd.zcompare(mint("="), y, Quantity(3, M), t)
        assert calls == ["zcompare/3"] and deref(y) == Quantity(3, M)


class TestReviewRoundTwentyOne:
    def test_circuit_refuses_before_any_strip_with_one_code(self):
        import clausal.logic.clpfd as clpfd
        t, x, y = Trail(), Var(), Var()
        assert clpfd.in_domain([x], Quantity(1, M), Quantity(2, M), t)
        assert clpfd.in_domain([y], Quantity(1, S), Quantity(2, S), t)
        with pytest.raises(LogicException) as ei:
            list(clpfd.fd_circuit([x, y], t))          # disagreeing dims: still units_unsupported
        _assert_system_error(ei, "units_unsupported")
        z = Var()
        with pytest.raises(LogicException):
            list(clpfd.fd_circuit([z, Quantity(1, M)], t))
        assert get_attr(z, UNITS_KEY) is None            # no shadow created on the refusal path

    def test_reify_does_not_declare_a_dimension_on_none(self):
        import clausal.logic.clpfd as clpfd
        t, x = Trail(), Var()
        assert clpfd.reify_fd("lt", x, Quantity(5, M), t) is None
        assert get_attr(x, UNITS_KEY) is None
        assert unify(x, Quantity(3, S), t)               # still free to be anything
        with pytest.raises(LogicException) as ei:
            clpfd.reify_fd("lt", Quantity(1, M), Quantity(2, S), Trail())
        _assert_system_error(ei, "units_mismatch")

    def test_united_var_unified_with_bare_solver_var_fails_at_unification(self):
        import clausal.logic.clpfd as clpfd
        from clausal.logic.units_constraint import constrain_var_dims
        for order in ("vw", "wv"):
            t, v, w = Trail(), Var(), Var()
            assert constrain_var_dims(v, M, t)
            assert clpfd.in_domain([w], 1, 3, t)
            ok = unify(v, w, t) if order == "vw" else unify(w, v, t)
            if ok:
                # the bare var's own hook fired instead of the units hook
                # (which side binds is the unifier's choice): the conflict
                # is still loud at the first units-channel use
                with pytest.raises(LogicException) as ei:
                    clpfd.fd_eq(v, Quantity(2, M), t)
                _assert_system_error(ei, "units_unsupported")
            else:
                assert is_var_unbound(v) and is_var_unbound(w)
        t, d, w = Trail(), Var(), Var()
        assert clpfd.in_domain([w], 1, 3, t)
        assert constrain_var_dims(d, {}, t)                # dimensionless may
        assert unify(d, w, t)

    def test_foreign_leaf_beside_units_material_in_a_list_is_loud(self):
        import clausal.logic.clpfd as clpfd
        with pytest.raises(LogicException) as ei:
            list(clpfd.fd_sum([Quantity(3, M), mint("foo")], mint("#="), Var(), Trail()))
        _assert_system_error(ei, "units_unsupported")
        assert list(clpfd.fd_sum([3, mint("foo")], mint("#="), Var(), Trail())) == []   # no material: as before

    def test_result_type_through_strip_units_is_documented(self):
        from clausal.modules.units import _strip_dimensions_impl
        q = Quantity(10, M) / Quantity(4, M)
        out = Var()
        assert list(_strip_dimensions_impl(q, out, Trail())) == [None]
        v = deref(out)
        assert type(v) is Fraction and v == Fraction(5, 2)
        assert v == 2.5                                  # unify-equal to the float; a rational term
