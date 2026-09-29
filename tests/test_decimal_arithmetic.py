"""Step 2 of the rdiv/decimal design (2026-09-17): the evaluator accepts a
Decimal leaf, division is RATIONAL, and the compiled and interpreted paths
agree.

RULED 2026-09-17: numbers are Python number objects in the engine (Q1);
``10.01`` in source stays a float (Q4); a float beside a Decimal RAISES
rather than coerce, because coercion risks loss of precision (Q5).  And the
standing ruling that arithmetic IS RATIONAL: ``/`` over exact operands yields
a Fraction, never a Decimal -- Python's Decimal division is inexact (context
precision), so ``Decimal('1') / 3`` must not silently round.

PARITY is the load-bearing property.  Every case runs through BOTH
``'is'(R, E)`` (the interpreted ``_eval_ground``) and ``eval_(E, R)`` (the
compiled ``arith_to_ast_expr`` tree) and the two must agree on value, TYPE
and error -- measured before this change the compiled path returned a float
for a runtime ``7 / 2`` where the interpreted one returned ``Fraction(7, 2)``,
computed ``Decimal / 7`` inexactly, and crashed with a raw Python TypeError on
``Decimal + Fraction`` where the interpreted path raised a logic error.

A Decimal is produced INSIDE the module (a declared decimal constant,
``strip_units``): a Python Decimal at a goal argument is refused by ruling.
"""
from __future__ import annotations

from decimal import Decimal
from fractions import Fraction

import pytest

from clausal.logic.exceptions import LogicException
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from clausal.testing import load_clausal_module

_HEADER = """-double_quotes(chars)
-private([yes, no])
-import_from(py.units, [metre, strip_units])
-constant_number_units(d150, "1.50", metre)
-constant_number_units(d1, "1", metre)
-constant_number_units(dbig, "1.1111111111111111111111111111", metre)
-constant_number_units(d200, "2.00", metre)
dec(D) <- strip_units(++d150, D)
one(D) <- strip_units(++d1, D)
big(D) <- strip_units(++dbig, D)
two(D) <- strip_units(++d200, D)
third(F) <- (F == 1 / 3)    # a CLP post: / is rational there (Q15)
"""


def _module(tmp_path, body):
    path = tmp_path / "decarith.clausal"
    path.write_text(_HEADER + body)
    return load_clausal_module(path)


def _both(tmp_path, binders, expr, header=""):
    """Evaluate *expr* (over the names *binders* introduce) through is/2 and
    eval_/2; return ``(interpreted, compiled)`` where each is the bound value
    or the LogicException raised."""
    src = (header +
           f"p_is(R) <- ({binders}, 'is'(R, {expr}))\n"
           f"p_ev(R) <- ({binders}, eval_({expr}, R))\n")
    mod = _module(tmp_path, src)
    out = []
    for name in ("p_is", "p_ev"):
        r = Var()
        try:
            for _ in call(name, r, module=mod):
                out.append(deref(r))
                break
            else:
                out.append("NO SOLUTION")
        except LogicException as e:
            out.append(e)
    return out


def _same(a, b):
    if isinstance(a, LogicException) or isinstance(b, LogicException):
        assert isinstance(a, LogicException) and isinstance(b, LogicException), (a, b)
        return
    assert type(a) is type(b), (a, b)
    assert a == b and str(a) == str(b), (a, b)     # str: scale-visible for Decimals


class TestParityAndValues:
    @pytest.mark.parametrize("binders, expr, want", [
        # runtime ints: a bare / in EVALUATION is Python's true division on
        # both paths (ruling Q15, 2026-09-28; it was the exact rational --
        # rdiv is the exact spelling now)
        ("X is 7, Y is 2", "X / Y", 3.5),
        ("X is 4, Y is 2", "X / Y", 2.0),
        ("X is 7, Y is 2", "X + Y", 9),
        # Decimal +, -, * with an int: exact, scale kept
        ("dec(D)", "D + 1", Decimal("2.50")),
        ("dec(D)", "D - 1", Decimal("0.50")),
        ("dec(D)", "D * 2", Decimal("3.00")),
        ("dec(D)", "D * D", Decimal("2.2500")),
        ("dec(D), two(T)", "D + T", Decimal("3.50")),
        # Decimal ⊕ Fraction: exact, as a Fraction
        ("dec(D), third(F)", "D + F", Fraction(11, 6)),
        ("dec(D), third(F)", "D * F", Fraction(1, 2)),
        # a bare / over a Decimal is Python's Decimal quotient (Q15); a
        # Decimal beside a Fraction (no Python answer) divides exactly
        ("dec(D)", "D / 3", Decimal("0.50")),
        ("one(D)", "D / 3", Decimal("0.3333333333333333333333333333")),
        ("dec(D)", "D / D", 1),
        ("dec(D), third(F)", "D / F", Fraction(9, 2)),
        ("dec(D)", "-D", Decimal("-1.50")),
        ("dec(D)", "(D + 1) * 2 - D", Decimal("3.50")),
    ])
    def test_value_and_parity(self, tmp_path, binders, expr, want):
        got_is, got_ev = _both(tmp_path, binders, expr)
        _same(got_is, got_ev)
        assert type(got_is) is type(want), (expr, got_is)
        assert got_is == want and str(got_is) == str(want), (expr, got_is)

    def test_a_scale_less_decimal_presents_as_an_int(self, tmp_path):
        """The transfer form's choke point (a decimal with no decimal places
        is an int) applied at the BINDER too, so engine and transfer agree."""
        got_is, got_ev = _both(tmp_path, "one(D)", "D + 1")
        _same(got_is, got_ev)
        assert type(got_is) is int and got_is == 2

    def test_RULED_Q5_a_float_beside_a_decimal_raises_on_both_paths(self, tmp_path):
        got_is, got_ev = _both(tmp_path, "dec(D)", "D + 0.5")
        assert isinstance(got_is, LogicException) and isinstance(got_ev, LogicException)
        assert "exact_number" in str(got_is) and "exact_number" in str(got_ev)
        got_is, got_ev = _both(tmp_path, "dec(D)", "D / 0.5")
        assert isinstance(got_is, LogicException) and isinstance(got_ev, LogicException)

    def test_a_float_beside_an_int_is_untouched(self, tmp_path):
        got_is, got_ev = _both(tmp_path, "X is 3", "X / 0.5")
        _same(got_is, got_ev)
        assert type(got_is) is float and got_is == 6.0

    def test_a_decimal_leaf_compares_in_the_interpreted_path(self, tmp_path):
        mod = _module(tmp_path, "p(R) <- (dec(D), if_('<'(1, D), R is yes, R is no))\n")
        r = Var()
        for _ in call("p", r, module=mod):
            assert deref(r) == "yes"
            break
        else:
            pytest.fail("no solution")


class TestExactnessBeyondNativeDecimal:
    """Python's Decimal ops round to the context precision (28 digits).  The
    engine's arithmetic is exact: these would FAIL on native Decimal ops."""

    def test_product_of_two_28_digit_decimals_is_exact(self, tmp_path):
        got_is, got_ev = _both(tmp_path, "big(B)", "B * B")
        _same(got_is, got_ev)
        exact = Decimal("1.1111111111111111111111111111") * Decimal("1.1111111111111111111111111111")
        assert str(exact) != str(got_is)            # the native op ROUNDS
        assert got_is == Fraction(11111111111111111111111111111, 10**28) ** 2
        assert str(got_is) == "1.23456790123456790123456790120987654320987654320987654321"

    def test_rdiv_never_rounds(self, tmp_path):
        """rdiv, the exact spelling, never rounds; a bare / over a Decimal is
        Python's Decimal quotient (ruling Q15, 2026-09-28), which does."""
        hdr = "-private([rdiv(A, B)])\n"
        got_is, got_ev = _both(tmp_path, "one(D)", "rdiv(D, 7)", header=hdr)
        _same(got_is, got_ev)
        assert got_is == Fraction(1, 7)
        for binders, expr, want in (("X is 7, Y is 2", "rdiv(X, Y)", Fraction(7, 2)),
                                    ("X is 4, Y is 2", "rdiv(X, Y)", 2),
                                    ("dec(D)", "rdiv(D, 3)", Fraction(1, 2))):
            got_is, got_ev = _both(tmp_path, binders, expr, header=hdr)
            _same(got_is, got_ev)
            assert got_is == want and type(got_is) is type(want), (expr, got_is)
        got_is, got_ev = _both(tmp_path, "one(D)", "D / 7")
        _same(got_is, got_ev)
        assert got_is == Decimal(1) / 7


class TestEvaluatorUnit:
    def test_decimal_leaf(self):
        from clausal.logic.clpfd import _eval_ground
        assert _eval_ground(Decimal("1.5")) == Decimal("1.5")

    def test_non_finite_decimal_is_refused(self):
        from clausal.logic.clpfd import _eval_ground
        with pytest.raises(LogicException):
            _eval_ground(Decimal("NaN"))
        with pytest.raises(LogicException):
            _eval_ground(Decimal("Infinity"))

    def test_decimal_cell_now_evaluates(self):
        """The guard pinned this as LOUD until step 2; step 2 is here."""
        from clausal.logic.clpfd import _eval_ground
        assert _eval_ground(("decimal", 99, 1)) == Decimal("9.9")

    def test_present_number_scale_zero_decimal(self):
        from clausal.logic.variables import present_number
        assert present_number(Decimal("2")) == 2 and type(present_number(Decimal("2"))) is int
        assert present_number(Decimal("1E+2")) == 100 and type(present_number(Decimal("1E+2"))) is int
        assert type(present_number(Decimal("2.0"))) is Decimal


class TestReifiedComparisonOnAnExactLeaf:
    def test_expr_tree_has_var_before_any_node_was_imported(self, monkeypatch):
        """Latent crash exposed by step 2: with the lazily-imported node
        classes still None, a ground Fraction leaf raised a raw TypeError
        from isinstance.  Pinned by resetting the lazy slot."""
        from clausal.logic import clpfd
        monkeypatch.setattr(clpfd, "_Add", None)
        assert clpfd._expr_tree_has_var(Fraction(1, 2)) is False
        assert clpfd._expr_tree_has_var(Decimal("1.5")) is False

    def test_a_runtime_reciprocal_compares_equal_to_its_float(self, tmp_path):
        """The suite's own ``safe reciprocal of 2``: ``eval_(1 / N, R)`` now
        binds ``Fraction(1, 2)`` (rational division on the compiled path) and
        the reified ``R == 0.5`` must still hold -- equal VALUE."""
        mod = _module(tmp_path, "p(N, R) <- (eval_(1 / N, F), if_(F == 0.5, R is yes, R is no))\n")
        r = Var()
        for _ in call("p", 2, r, module=mod):
            assert deref(r) == "yes"
            break
        else:
            pytest.fail("no solution")

    @pytest.mark.parametrize("goal, want", [
        ("F == 0.5", "yes"), ("F != 0.5", "no"), ("F < 0.75", "yes"), ("F <= 0.5", "yes"),
        ("F > 0.5", "no"), ("F >= 0.5", "yes"), ("F == 0.4", "no"),
    ])
    def test_ground_fraction_against_float_at_the_constraint_level(self, tmp_path, goal, want):
        """Not reified: the constraint entries themselves (fd_eq & co.).  A
        ground Fraction beside a ground float is a VALUE comparison, not a
        CLP(Q)/CLP(R) mixing error."""
        mod = _module(tmp_path, f"p(R) <- (eval_(1 / 2, F), if_({goal}, R is yes, R is no))\n"
                                f"q() <- (eval_(1 / 2, F), {goal})\n")
        r = Var()
        for _ in call("p", r, module=mod):
            assert deref(r) == want; break
        else:
            pytest.fail("no solution")
        held = any(True for _ in call("q", module=mod))
        assert held == (want == "yes")

    @pytest.mark.parametrize("goal, want", [
        ("X / Y == 3.5", "yes"), ("X / Y == 3.4", "no"), ("X / Y != 3.5", "no"),
        ("X / Y < 4", "yes"), ("X / Y <= 3.5", "yes"), ("X / Y > 3.5", "no"), ("X / Y >= 3.5", "yes"),
    ])
    def test_a_ground_expression_tree_against_a_float(self, tmp_path, goal, want):
        """the harness lane's probe (2026-09-17): the TREE ``X / Y`` with
        runtime ints on the left of ``==`` against a float.  The Python
        comparison twins fold a ground tree before comparing; the C-backed
        wrappers did not, and went to the mixing refusal -- so the first fix
        closed only the already-numeric shape."""
        mod = _module(tmp_path, f"p(X, Y, R) <- if_({goal}, R is yes, R is no)\n"
                                f"q(X, Y) <- ({goal})\n")
        r = Var()
        for _ in call("p", 7, 2, r, module=mod):
            assert deref(r) == want; break
        else:
            pytest.fail("no solution")
        assert any(True for _ in call("q", 7, 2, module=mod)) == (want == "yes")

    def test_a_decimal_expression_tree_against_a_float(self, tmp_path):
        mod = _module(tmp_path, "q() <- (dec(D), D / 3 == 0.5)\nq2() <- (dec(D), D * 2 == 3.0)\n")
        assert any(True for _ in call("q", module=mod))
        assert any(True for _ in call("q2", module=mod))


class TestWrittenSpellingsInCompiledArithmetic:
    """A cell written in source (``decimal(1001, 2)``, ``rdiv(1, 3)``, declared
    with -private until step 3 makes the spellings known) reaches the
    COMPILED tree as a tuple.  Found 2026-09-18: ``eval_(decimal(1001, 2) * 2,
    R)`` answered ``('decimal', 1001, 2, 'decimal', 1001, 2)`` -- Python's
    tuple repetition, silent -- while ``is/2`` converted the leaf.  The
    helpers now convert a CANONICAL cell and refuse any other tuple loudly,
    on both paths, so a cell can never reach a native tuple operator."""

    _HDR = "-private([decimal(A, B), rdiv(A, B)])\n"

    @pytest.mark.parametrize("expr, want", [
        ("decimal(1001, 2) * 2", Decimal("20.02")),
        ("decimal(1001, 2) + 1", Decimal("11.01")),
        ("rdiv(1, 3) + 1", Fraction(4, 3)),
        ("decimal(1001, 2) + rdiv(1, 3)", Fraction(3103, 300)),
        ("2 * rdiv(1, 4)", Fraction(1, 2)),
        ("decimal(150, 2) / 3", Decimal("0.50")),    # bare /: Python (Q15)
        ("rdiv(2, 4) + 1", Fraction(3, 2)),         # rdiv evaluates (Q15)
        ("decimal(100, 2) - 1", Decimal("0.00")),   # scale is information: 1.00 - 1 is 0.00
    ])
    def test_written_cells_evaluate_on_both_paths(self, tmp_path, expr, want):
        got_is, got_ev = _both(tmp_path, "true", expr, header=self._HDR)
        _same(got_is, got_ev)
        assert type(got_is) is type(want) and got_is == want and str(got_is) == str(want), (expr, got_is)

    # 2026-09-25, ruling C / operator Q1 ("a data functor refuses too few
    # args"): a functor name holds ONE declared arity, so the old shared header
    # (rdiv/2 THEN rdiv/3) left rdiv at /3, and ``rdiv(2, 4)`` only passed here
    # because it was silently padded to ``rdiv(2, 4, _)``.  It is now a load
    # SyntaxError, so each case declares the arity it writes: ``rdiv(2, 4)``
    # is a non-canonical rdiv/2 cell, ``rdiv(1, 3, 5)`` an rdiv/3 look-alike.
    @pytest.mark.parametrize("expr, hdr", [
        ("decimal(1, 0) * 2", "-private([decimal(A, B), rdiv(A, B)])\n"),
        ("rdiv(1, 3, 5) * 2", "-private([decimal(A, B), rdiv(A, B, C)])\n"),
    ], ids=["decimal(1, 0) * 2", "rdiv(1, 3, 5) * 2"])
    def test_a_look_alike_cell_is_refused_loudly_on_both_paths(self, tmp_path, expr, hdr):
        got_is, got_ev = _both(tmp_path, "true", expr, header=hdr)
        assert isinstance(got_is, LogicException) and isinstance(got_ev, LogicException), (got_is, got_ev)

    def test_a_short_construction_of_a_data_functor_is_refused_at_load(self, tmp_path):
        """Ruling C / Q1 (2026-09-25): the name's only declaration is rdiv/3,
        so ``rdiv(2, 4)`` is too few arguments -- refused at load, not padded
        to the look-alike ``rdiv(2, 4, _)``."""
        with pytest.raises(SyntaxError, match=r"rdiv/3 was constructed with 2 positional"):
            _both(tmp_path, "true", "rdiv(2, 4) + 1",
                  header="-private([rdiv(A, B, C)])\n")

    def test_a_construction_at_either_declared_arity_builds(self, tmp_path):
        """Declared field names are per (name, arity) (operator ruling
        2026-09-29): with rdiv/2 AND rdiv/3 declared, ``rdiv(2, 4)`` is the
        declared rdiv/2.  (While the registry was keyed by name, the later
        declaration, rdiv/3, replaced the earlier and this was refused.)"""
        got_is, got_ev = _both(tmp_path, "true", "rdiv(2, 4) + 1",
                               header=self._HDR + "-private([rdiv(A, B, C)])\n")
        assert got_is == got_ev == Fraction(3, 2)

    def test_an_atom_times_two_is_refused_not_repeated(self, tmp_path):
        got_is, got_ev = _both(tmp_path, "true", "yes * 2")
        assert isinstance(got_is, LogicException) and isinstance(got_ev, LogicException), (got_is, got_ev)
