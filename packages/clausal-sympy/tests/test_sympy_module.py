"""Tests for clausal.modules.py.sympy — SymPy integration."""

from __future__ import annotations

import pytest
import sympy as sp

from clausal.logic.variables import Var, Trail, deref, unify
from clausal.logic.trampoline import DONE
from clausal.terms import Add, Sub, Mult, Div, Pow, Negate, Compound
from clausal.modules.py.sympy import (
    to_sympy, from_sympy, _ConversionContext,
    Sym, ToSympy, FromSympy,
    Simplify, Expand, Factor, Solve, SolveAll,
    Diff, Integrate, Limit, Series, Subs, FreeVars,
)


# ── Helpers ─────────────────────────────────────────────────────────────────


def _collect_solutions(predicate, *args):
    """Run a trampoline predicate and collect all solutions."""
    trail = Trail()
    dispatch = predicate._get_dispatch()

    class _FakeGen:
        pass

    parent = _FakeGen()
    results = []
    # Phase 2: dispatch takes (this_gen, _proceed, _fail, _catcher, *args).
    gen = dispatch(None, parent, parent, parent, *args, trail)
    for pair in gen:
        g, val = pair
        if val is DONE:
            break
        if val is None and g is parent:
            # Solution found — snapshot the deref'd args
            results.append(tuple(deref(a) for a in args))
    return results


def _first_solution(predicate, *args):
    """Run predicate, return first solution's deref'd args or None."""
    sols = _collect_solutions(predicate, *args)
    return sols[0] if sols else None


# ── Conversion tests ────────────────────────────────────────────────────────


class TestToSympy:
    def test_int(self):
        # nv
        assert to_sympy(42) == sp.Integer(42)

    def test_float(self):
        # nv
        assert to_sympy(3.14) == sp.Float(3.14)

    def test_free_var(self):
        # nv
        v = Var()
        ctx = _ConversionContext()
        result = to_sympy(v, ctx)
        assert isinstance(result, sp.Symbol)

    def test_bound_var_derefs(self):
        # nv
        v = Var()
        trail = Trail()
        unify(v, 5, trail)
        assert to_sympy(v) == sp.Integer(5)

    def test_add(self):
        # nv
        x = sp.Symbol("x")
        ctx = _ConversionContext()
        v = Var()
        ctx._var_to_sym[v._id] = x
        ctx._sym_to_var["x"] = v
        result = to_sympy(Add(left=v, right=1), ctx)
        assert result == x + 1

    def test_sub(self):
        # nv
        x = sp.Symbol("x")
        ctx = _ConversionContext()
        v = Var()
        ctx._var_to_sym[v._id] = x
        ctx._sym_to_var["x"] = v
        result = to_sympy(Sub(left=v, right=1), ctx)
        assert result == x - 1

    def test_mult(self):
        # nv
        result = to_sympy(Mult(left=3, right=7))
        assert result == sp.Integer(21)

    def test_pow(self):
        # nv
        x = sp.Symbol("x")
        ctx = _ConversionContext()
        v = Var()
        ctx._var_to_sym[v._id] = x
        ctx._sym_to_var["x"] = v
        result = to_sympy(Pow(left=v, right=2), ctx)
        assert result == x**2

    def test_negate(self):
        # nv
        result = to_sympy(Negate(operand=5))
        assert result == sp.Integer(-5)

    def test_compound_sin(self):
        # nv
        x = sp.Symbol("x")
        ctx = _ConversionContext()
        v = Var()
        ctx._var_to_sym[v._id] = x
        ctx._sym_to_var["x"] = v
        result = to_sympy(Compound("sin", (v,)), ctx)
        assert result == sp.sin(x)

    def test_compound_unknown(self):
        # nv
        result = to_sympy(Compound("foo", (1, 2)))
        assert str(result) == "foo(1, 2)"

    def test_nested(self):
        # x**2 + 2*x + 1
        # nv
        x = sp.Symbol("x")
        ctx = _ConversionContext()
        v = Var()
        ctx._var_to_sym[v._id] = x
        ctx._sym_to_var["x"] = v
        term = Add(
            left=Add(left=Pow(left=v, right=2), right=Mult(left=2, right=v)),
            right=1,
        )
        result = to_sympy(term, ctx)
        assert sp.expand(result - (x**2 + 2 * x + 1)) == 0

    def test_string_becomes_symbol(self):
        # nv
        result = to_sympy("x")
        assert result == sp.Symbol("x")

    def test_sympy_passthrough(self):
        # nv
        expr = sp.sin(sp.Symbol("x"))
        assert to_sympy(expr) is expr

    def test_div(self):
        # nv
        result = to_sympy(Div(left=1, right=2))
        assert result == sp.Rational(1, 2)


class TestFromSympy:
    def test_integer(self):
        # nv
        assert from_sympy(sp.Integer(42)) == 42

    def test_symbol_passthrough(self):
        # nv
        ctx = _ConversionContext()
        result = from_sympy(sp.Symbol("x"), ctx)
        # Symbols without a Var mapping pass through as ground values
        assert isinstance(result, sp.Symbol)
        assert result == sp.Symbol("x")

    def test_symbol_roundtrip(self):
        # nv
        v = Var()
        ctx = _ConversionContext()
        sym = ctx.var_to_symbol(v)
        result = from_sympy(sym, ctx)
        assert result is v

    def test_add(self):
        # nv
        x = sp.Symbol("x")
        ctx = _ConversionContext()
        result = from_sympy(x + 1, ctx)
        assert isinstance(result, Add)

    def test_mul(self):
        # nv
        x = sp.Symbol("x")
        ctx = _ConversionContext()
        result = from_sympy(3 * x, ctx)
        assert isinstance(result, Mult)

    def test_pow(self):
        # nv
        x = sp.Symbol("x")
        ctx = _ConversionContext()
        result = from_sympy(x**2, ctx)
        assert isinstance(result, Pow)

    def test_negation(self):
        # nv
        x = sp.Symbol("x")
        ctx = _ConversionContext()
        result = from_sympy(-x, ctx)
        assert isinstance(result, Negate)

    def test_rational(self):
        # nv
        result = from_sympy(sp.Rational(3, 4))
        assert isinstance(result, Div)
        assert result.left == 3
        assert result.right == 4

    def test_rational_integer(self):
        # nv
        result = from_sympy(sp.Rational(6, 2))
        assert result == 3

    def test_sin(self):
        # nv
        x = sp.Symbol("x")
        ctx = _ConversionContext()
        result = from_sympy(sp.sin(x), ctx)
        assert isinstance(result, Compound)
        assert result.functor == "sin"

    def test_float(self):
        # nv
        result = from_sympy(sp.Float(2.5))
        assert result == 2.5

    def test_inverse_to_div(self):
        # nv
        x = sp.Symbol("x")
        ctx = _ConversionContext()
        result = from_sympy(1 / x, ctx)
        # 1/x = x**(-1) → Div(1, x)
        assert isinstance(result, Div)


class TestRoundTrip:
    """Test that to_sympy → simplify → from_sympy preserves variable identity."""

    def test_var_preserved(self):
        # nv
        v = Var()
        ctx = _ConversionContext()
        expr = to_sympy(Add(left=v, right=1), ctx)
        back = from_sympy(expr, ctx)
        # The Var in the result should be the same object
        assert isinstance(back, Add)
        # Find the var in the result tree
        found = _find_var(back)
        assert found is v

    def test_simplify_roundtrip(self):
        # nv
        v = Var()
        ctx = _ConversionContext()
        # (x+1)^2 → expand → x^2 + 2x + 1
        term = Pow(left=Add(left=v, right=1), right=2)
        expr = to_sympy(term, ctx)
        expanded = sp.expand(expr)
        back = from_sympy(expanded, ctx)
        # Should contain the original Var
        found = _find_var(back)
        assert found is v


def _find_var(term):
    """Recursively find the first Var in a term tree."""
    if isinstance(term, Var):
        return term
    for attr in ("left", "right", "operand"):
        child = getattr(term, attr, None)
        if child is not None:
            v = _find_var(child)
            if v is not None:
                return v
    if isinstance(term, Compound):
        for a in term.args:
            v = _find_var(a)
            if v is not None:
                return v
    return None


# ── Predicate tests ─────────────────────────────────────────────────────────


class TestSym:
    def test_create_symbol(self):
        # nv
        result = Var()
        sol = _first_solution(Sym, "x", result)
        assert sol is not None
        assert isinstance(deref(result), sp.Symbol)
        assert str(deref(result)) == "x"


class TestSimplify:
    def test_simplify_polynomial(self):
        # (x+1)^2 - x^2 - 2x → simplify → 1
        # nv
        v = Var()
        trail = Trail()
        unify(v, sp.Symbol("x"), trail)
        term = Sub(
            left=Sub(
                left=Pow(left=Add(left=v, right=1), right=2),
                right=Pow(left=v, right=2),
            ),
            right=Mult(left=2, right=v),
        )
        result = Var()
        sol = _first_solution(Simplify, term, result)
        assert sol is not None
        assert deref(result) == 1

    def test_simplify_trig(self):
        # nv
        x = sp.Symbol("x")
        # sin(x)^2 + cos(x)^2 → 1
        term = Add(
            left=Pow(left=Compound("sin", (x,)), right=2),
            right=Pow(left=Compound("cos", (x,)), right=2),
        )
        result = Var()
        sol = _first_solution(Simplify, term, result)
        assert sol is not None
        assert deref(result) == 1


class TestExpand:
    def test_expand_square(self):
        # nv
        x = sp.Symbol("x")
        term = Pow(left=Add(left=x, right=1), right=2)
        result = Var()
        sol = _first_solution(Expand, term, result)
        assert sol is not None
        r = deref(result)
        # Result is a SymExpr wrapper around a SymPy expression
        from clausal.modules.py.sympy import SymExpr
        assert isinstance(r, SymExpr)
        assert r == x**2 + 2 * x + 1


class TestFactor:
    def test_factor_diff_of_squares(self):
        # nv
        x = sp.Symbol("x")
        term = Sub(left=Pow(left=x, right=2), right=1)
        result = Var()
        sol = _first_solution(Factor, term, result)
        assert sol is not None
        r = deref(result)
        assert sp.expand(r - (x - 1) * (x + 1)) == 0


class TestSolve:
    def test_solve_linear(self):
        # nv
        x = sp.Symbol("x")
        # 2x - 6 = 0 → x = 3
        eq = Sub(left=Mult(left=2, right=x), right=6)
        solution = Var()
        sols = _collect_solutions(Solve, eq, x, solution)
        assert len(sols) == 1
        # Check the snapshot (solution Var is unbound after trail.undo)
        assert sols[0][2] == 3

    def test_solve_quadratic(self):
        # nv
        x = sp.Symbol("x")
        # x^2 - 4 = 0 → x = -2, 2
        eq = Sub(left=Pow(left=x, right=2), right=4)
        solution = Var()
        sols = _collect_solutions(Solve, eq, x, solution)
        values = sorted(s[2] for s in sols)  # 3rd arg is solution
        assert values == [-2, 2]

    def test_solve_no_solution(self):
        # nv
        x = sp.Symbol("x")
        # x^2 + 1 = 0 has no real solutions — SymPy gives complex
        eq = Add(left=Pow(left=x, right=2), right=1)
        solution = Var()
        sols = _collect_solutions(Solve, eq, x, solution)
        # SymPy returns complex solutions: ±i
        assert len(sols) == 2


class TestSolveAll:
    def test_solve_all_quadratic(self):
        # nv
        x = sp.Symbol("x")
        eq = Sub(left=Pow(left=x, right=2), right=9)
        solutions = Var()
        sol = _first_solution(SolveAll, eq, x, solutions)
        assert sol is not None
        result = deref(solutions)
        assert sorted(result) == [-3, 3]


class TestDiff:
    def test_diff_auto_var(self):
        # nv
        x = sp.Symbol("x")
        # d/dx(x^3) = 3x^2
        term = Pow(left=x, right=3)
        result = Var()
        sol = _first_solution(Diff, term, result)
        assert sol is not None
        r = deref(result)
        assert sp.expand(r - 3 * x**2) == 0

    def test_diff_explicit_var(self):
        # nv
        x = sp.Symbol("x")
        term = Compound("sin", (x,))
        result = Var()
        sol = _first_solution(Diff, term, x, result)
        assert sol is not None
        r = deref(result)
        assert r == sp.cos(x)

    def test_diff_multivar(self):
        # nv
        x, y = sp.Symbol("x"), sp.Symbol("y")
        # d/dx(x*y + x^2)
        term = Add(left=Mult(left=x, right=y), right=Pow(left=x, right=2))
        result = Var()
        sol = _first_solution(Diff, term, x, result)
        assert sol is not None
        r = deref(result)
        assert sp.expand(r - (y + 2 * x)) == 0


class TestIntegrate:
    def test_integrate_poly(self):
        # nv
        x = sp.Symbol("x")
        # ∫ x^2 dx = x^3/3
        term = Pow(left=x, right=2)
        result = Var()
        sol = _first_solution(Integrate, term, result)
        assert sol is not None
        r = deref(result)
        assert sp.simplify(r - x**3 / 3) == 0

    def test_integrate_explicit_var(self):
        # nv
        x = sp.Symbol("x")
        result = Var()
        sol = _first_solution(Integrate, Compound("cos", (x,)), x, result)
        assert sol is not None
        r = deref(result)
        assert r == sp.sin(x)


class TestLimit:
    def test_limit_sinx_over_x(self):
        # nv
        x = sp.Symbol("x")
        # lim x→0 sin(x)/x = 1
        term = Div(left=Compound("sin", (x,)), right=x)
        result = Var()
        sol = _first_solution(Limit, term, x, 0, result)
        assert sol is not None
        assert deref(result) == 1


class TestSeries:
    def test_series_exp(self):
        # nv
        x = sp.Symbol("x")
        # exp(x) around 0 to 4 terms: 1 + x + x^2/2 + x^3/6
        term = Compound("exp", (x,))
        result = Var()
        sol = _first_solution(Series, term, x, 4, result)
        assert sol is not None
        r = deref(result)
        expected = 1 + x + x**2 / 2 + x**3 / 6
        assert sp.simplify(r - expected) == 0


class TestSubs:
    def test_subs_dict(self):
        # nv
        x = sp.Symbol("x")
        term = Add(left=Pow(left=x, right=2), right=1)
        result = Var()
        sol = _first_solution(Subs, term, {"x": 3}, result)
        assert sol is not None
        assert deref(result) == 10  # 3^2 + 1

    def test_subs_list(self):
        # nv
        x, y = sp.Symbol("x"), sp.Symbol("y")
        term = Add(left=x, right=y)
        result = Var()
        sol = _first_solution(Subs, term, [("x", 2), ("y", 3)], result)
        assert sol is not None
        assert deref(result) == 5


class TestFreeVars:
    def test_free_vars(self):
        # nv
        x, y = sp.Symbol("x"), sp.Symbol("y")
        term = Add(left=Mult(left=x, right=y), right=1)
        result = Var()
        sol = _first_solution(FreeVars, term, result)
        assert sol is not None
        assert deref(result) == ["x", "y"]


# ── Integration: full pipeline ──────────────────────────────────────────────


class TestIntegration:
    """Tests that verify the module works end-to-end with the trampoline."""

    def test_solve_and_verify(self):
        """Solve x^2 = 9, verify each solution by substitution."""
        # nv
        x = sp.Symbol("x")
        eq = Sub(left=Pow(left=x, right=2), right=9)
        solution = Var()
        sols = _collect_solutions(Solve, eq, x, solution)
        values = sorted(s[2] for s in sols)
        for val in values:
            # val^2 should be 9
            assert val**2 == 9

    def test_differentiate_then_integrate(self):
        """Diff then integrate should give back (up to constant)."""
        # nv
        x = sp.Symbol("x")
        original = Pow(left=x, right=3)

        # Differentiate: 3x^2
        deriv = Var()
        _first_solution(Diff, original, deriv)
        d = deref(deriv)

        # Integrate the derivative: should get x^3 back
        integral = Var()
        _first_solution(Integrate, d, integral)
        i = deref(integral)

        assert sp.simplify(i - x**3) == 0
