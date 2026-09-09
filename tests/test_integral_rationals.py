"""An integral rational is presented as an ``int``.

``int/int`` evaluates to an exact rational (``docs/clpq.md``): ``3/2`` is
``Fraction(3, 2)``, never ``1.5``. When the quotient IS an integer, though,
``4/2`` must present as ``int 2`` and not ``Fraction(2, 1)`` — the two are
distinct terms in the ISO standard order (``'=='`` and ``compare/3`` tag every
numeric type as its own kind) while the engine's ``unify`` conflates them, so
an integral ``Fraction`` made ``'is'(X, 4/2), '=='(X, 2)`` FALSE while
``'='(X, 2)`` succeeded: two surfaces disagreeing about one term.

Every binder that hands a rational to a logic variable is covered here:

* ``_eval_ground`` (behind ``is/2``, the six ISO comparisons, ``between/3``
  and the constraint-side ``_resolve``);
* the CLP(Q) binders in ``clpq.py`` (the ``q_eq`` fast paths re-wrapped the
  value as ``Fraction(r)`` before ``unify``, so ``X == TOTAL / 4`` in a
  clause body still bound a Fraction after the evaluator was fixed);
* ``z3_to_python``.

Type assertions are ``type(x) is int``: ``Fraction(2, 1) == 2`` is True in
Python, so an ``==`` assertion passes while the defect is live.
"""
from fractions import Fraction

import pytest

from clausal.logic.atoms import spelling
from clausal.logic.solve import call
from clausal.logic.variables import Trail, Var, deref
from clausal.logic.variables._variables import (
    unify, unify_census, unify_census_start, unify_census_stop,
)
from clausal.terms import Add, Div, Mult, Sub
from clausal.testing import load_clausal_module


_HEADER = "-double_quotes(chars)\n"


def _module(tmp_path, src):
    path = tmp_path / "integral.clausal"
    path.write_text(_HEADER + src)
    return load_clausal_module(path)


def _first(tmp_path, src, name, *args):
    """Run ``name(*args)`` to its first solution; return the deref'd args.

    Read INSIDE the ``call`` loop: draining the generator undoes the trail.
    """
    mod = _module(tmp_path, src)
    for _ in call(name, *args, module=mod):
        return tuple(deref(a) for a in args)
    pytest.fail(f"{name} had no solution")


def _bind(tmp_path, body):
    """The value ``X`` takes after the goal *body* (which mentions ``X``)."""
    x = Var()
    return _first(tmp_path, f"p(X) <- ({body})\n", "p", x)[0]


def _holds(tmp_path, body):
    mod = _module(tmp_path, f"p() <- ({body})\n")
    for _ in call("p", module=mod):
        return True
    return False


# ── is/2 through the surface ───────────────────────────────────────────────


class TestIsPresentsIntegralQuotientsAsInt:

    @pytest.mark.parametrize("expr, want", [
        ("4 / 2", 2),
        ("6 / 3", 2),
        ("4 // 2", 2),             # unchanged: floor division was already int
        ("(4 / 2) * 3", 6),        # the property holds for the whole tree,
        ("(1 / 2) + (1 / 2)", 1),  # not only for a Div at the root
        ("(7 / 2) - (3 / 2)", 2),
        ("-(4 / 2)", -2),
    ])
    def test_integral_result_is_int(self, tmp_path, expr, want):
        got = _bind(tmp_path, f"'is'(X, {expr})")
        assert got == want
        assert type(got) is int, (expr, got)

    @pytest.mark.parametrize("expr, want", [
        ("3 / 2", Fraction(3, 2)),
        ("1 / 3", Fraction(1, 3)),
        ("(1 / 2) + (1 / 3)", Fraction(5, 6)),
    ])
    def test_non_integral_result_stays_exact(self, tmp_path, expr, want):
        got = _bind(tmp_path, f"'is'(X, {expr})")
        assert got == want
        assert type(got) is Fraction, (expr, got)

    def test_float_division_is_untouched(self, tmp_path):
        got = _bind(tmp_path, "'is'(X, 4.0 / 2)")
        assert got == 2.0 and type(got) is float


class TestTheTwoSurfacesAgree:
    """``'=='``/``compare/3`` and ``'='`` must say the same thing."""

    def test_structural_equality_after_is(self, tmp_path):
        assert _holds(tmp_path, "'is'(X, 4 / 2), '=='(X, 2)")

    def test_compare_says_equal(self, tmp_path):
        x, o = Var(), Var()
        _, order = _first(tmp_path,
                          "p(X, O) <- ('is'(X, 4 / 2), compare(O, X, 2))\n",
                          "p", x, o)
        assert spelling(order) == "="

    def test_arithmetic_equality(self, tmp_path):
        assert _holds(tmp_path, "'=:='(4 / 2, 2)")
        assert _holds(tmp_path, "'=:='(4 / 2, 6 / 3)")
        assert not _holds(tmp_path, "'=:='(3 / 2, 1)")

    def test_between_accepts_an_integral_quotient_bound(self, tmp_path):
        mod = _module(tmp_path, "p(X) <- between(1, 4 / 2, X)\n")
        x = Var()
        got = [deref(x) for _ in call("p", x, module=mod)]
        assert got == [1, 2]
        assert all(type(v) is int for v in got)


# ── the constraint-side binder (fd_eq -> q_eq) ─────────────────────────────

_QUARTER_SRC = """\
quarter_of(TOTAL, QUARTER) <- (QUARTER == TOTAL / 4)
check(TOTAL, EXPECTED) <- (quarter_of(TOTAL, QUARTER), QUARTER is EXPECTED)
"""


class TestConstraintEqualityBindsInt:
    """``QUARTER == TOTAL / 4`` in a clause body is CLP(Q)'s ``q_eq``, whose
    fast path hands the value to ``unify`` itself — a second binder, after
    the evaluator, that must present an integral rational as int."""

    def test_check_succeeds(self, tmp_path):
        mod = _module(tmp_path, _QUARTER_SRC)
        assert any(True for _ in call("check", 700000, 175000, module=mod))

    def test_quarter_is_bound_to_an_int(self, tmp_path):
        q = Var()
        _, got = _first(tmp_path, _QUARTER_SRC, "quarter_of", 700000, q)
        assert got == 175000
        assert type(got) is int, got

    def test_non_integral_quarter_stays_exact(self, tmp_path):
        q = Var()
        _, got = _first(tmp_path, _QUARTER_SRC, "quarter_of", 10, q)
        assert got == Fraction(5, 2) and type(got) is Fraction

    def test_no_int_fraction_conflation_under_the_census(self, tmp_path):
        """The unify census sees ``unify(int, Fraction)`` succeed only while
        the defect is live. Positive control first — ``unify(1, 1.0)`` must
        count one — so a silent census cannot pass this."""
        mod = _module(tmp_path, _QUARTER_SRC)
        unify_census_start()
        try:
            assert unify(1, 1.0, Trail())
            control = unify_census()
            assert control["conflations"] == 1, control
            assert control["by_type_pair"] == {"int/float": 1}, control
            for _ in call("check", 700000, 175000, module=mod):
                break
            else:
                pytest.fail("check had no solution")
            report = unify_census()
        finally:
            unify_census_stop()
        assert report["conflations"] == 1, report   # the control only
        assert report["by_type_pair"] == {"int/float": 1}, report


class TestClpqBinders:

    def test_rational_var_integral_quotient(self, tmp_path):
        got = _bind(tmp_path, "rational(X), X == 4 / 2")
        assert got == 2 and type(got) is int

    def test_rational_var_non_integral_quotient(self, tmp_path):
        got = _bind(tmp_path, "rational(X), X == 3 / 2")
        assert got == Fraction(3, 2) and type(got) is Fraction

    def test_rational_var_accepts_an_int_binding(self, tmp_path):
        """Ints are rationals: a var declared ``rational`` unifies with 2."""
        assert _holds(tmp_path, "rational(X), X == 4 / 2, X == 2")
        assert _holds(tmp_path, "rational(X), '='(X, 2)")

    def test_solver_decided_integral_values_are_int(self, tmp_path):
        x, y = Var(), Var()
        gx, gy = _first(
            tmp_path,
            "p(X, Y) <- (rational([X, Y]), X + Y == 10, X - Y == 4)\n",
            "p", x, y)
        assert (gx, gy) == (7, 3)
        assert type(gx) is int and type(gy) is int, (gx, gy)

    def test_solver_decided_non_integral_values_stay_exact(self, tmp_path):
        x, y = Var(), Var()
        gx, gy = _first(
            tmp_path,
            "p(X, Y) <- (rational([X, Y]), X + Y == 10, X - Y == 3)\n",
            "p", x, y)
        assert (gx, gy) == (Fraction(13, 2), Fraction(7, 2))
        assert type(gx) is Fraction and type(gy) is Fraction

    def test_python_api_q_eq_and_bounds(self):
        from clausal.logic.clpq import in_q, q_eq, _tableaux, _last_snapshot
        _tableaux.clear(); _last_snapshot.clear()
        try:
            trail = Trail()
            x, y, z = Var(), Var(), Var()
            in_q([x, y], -100, 100, trail)
            assert q_eq(Add(left=x, right=y), 10, trail)
            assert q_eq(Sub(left=x, right=y), 4, trail)
            assert (deref(x), deref(y)) == (7, 3)
            assert type(deref(x)) is int and type(deref(y)) is int
            # a pinched interval binds through _post_q_domain
            assert in_q(z, 5, 5, trail)
            assert deref(z) == 5 and type(deref(z)) is int
            # the q_eq fast path
            w = Var()
            assert q_eq(w, Fraction(6, 3), trail)
            assert type(deref(w)) is int
        finally:
            _tableaux.clear(); _last_snapshot.clear()

    def test_python_api_optimum_is_int(self):
        from clausal.logic.clpq import (in_q, q_le, maximize, sup,
                                        _tableaux, _last_snapshot)
        _tableaux.clear(); _last_snapshot.clear()
        try:
            trail = Trail()
            x, s, m = Var(), Var(), Var()
            in_q(x, 0, 10, trail)
            assert q_le(Mult(left=2, right=x), 8, trail)
            assert sup(x, s, trail)
            assert deref(s) == 4 and type(deref(s)) is int
            assert maximize(x, m, trail)
            assert deref(m) == 4 and type(deref(m)) is int
            assert deref(x) == 4 and type(deref(x)) is int
        finally:
            _tableaux.clear(); _last_snapshot.clear()


# ── the evaluator itself ───────────────────────────────────────────────────


class TestEvalGround:

    def test_div_of_ints(self):
        from clausal.logic.clpfd import _eval_ground
        got = _eval_ground(Div(left=4, right=2))
        assert got == 2 and type(got) is int
        got = _eval_ground(Div(left=3, right=2))
        assert got == Fraction(3, 2) and type(got) is Fraction

    def test_fraction_leaf_with_denominator_one(self):
        """The invariant is about what the evaluator RETURNS, whatever the
        node: an integral Fraction leaf comes back as int too."""
        from clausal.logic.clpfd import _eval_ground
        got = _eval_ground(Add(left=Fraction(2, 1), right=0))
        assert type(got) is int
        got = _eval_ground(Fraction(4, 2))
        assert got == 2 and type(got) is int

    def test_bool_is_not_a_number_here(self):
        from clausal.logic.clpfd import _eval_ground
        assert _eval_ground(True) is None


class TestZ3Conversion:

    def test_whole_real_presents_as_int(self):
        z3 = pytest.importorskip("z3")
        from clausal.logic.clpz3 import z3_to_python
        got = z3_to_python(z3.RealVal("5"))
        assert got == 5 and type(got) is int
        got = z3_to_python(z3.RealVal("10/2"))
        assert got == 5 and type(got) is int
        got = z3_to_python(z3.RealVal("3/7"))
        assert got == Fraction(3, 7) and type(got) is Fraction


# ── the compiled binder (eval_/2 -> ArithEval -> $unify) and the seam ──────


class TestCompiledArithmetic:
    """``eval_(E, X)`` never touches ``_eval_ground``: the compiler emits a
    native Python expression (``$exact_div(l, r)`` for a literal int/int Div,
    the whole tree wrapped in ``$present``) whose value goes to ``$unify``.
    The seam's value arithmetic reuses the same emitter. Both must present
    an integral rational as int."""

    @pytest.mark.parametrize("expr, want", [
        ("4 / 2", 2),
        ("(1 / 2) + (1 / 2)", 1),
        ("(4 / 2) * 3", 6),
    ])
    def test_eval_integral_result_is_int(self, tmp_path, expr, want):
        got = _bind(tmp_path, f"eval_({expr}, X)")
        assert got == want
        assert type(got) is int, (expr, got)

    def test_eval_non_integral_result_stays_exact(self, tmp_path):
        got = _bind(tmp_path, "eval_(3 / 2, X)")
        assert got == Fraction(3, 2) and type(got) is Fraction

    def test_eval_float_division_is_untouched(self, tmp_path):
        got = _bind(tmp_path, "eval_(4.0 / 2, X)")
        assert got == 2.0 and type(got) is float

    def test_pass_through_of_a_fraction_bound_operand_is_presented(self, tmp_path):
        """PIN of chosen behaviour: an operand ALREADY bound to
        ``Fraction(2, 1)`` (from Python, say) is presented when it passes
        through a binder — ``eval_(X, Y)`` binds ``Y`` to int 2 while ``X``
        keeps its Fraction, so ``'=='(X, Y)`` is false afterwards. That
        matches ``_eval_ground``'s leaf rule; the two binders must agree."""
        src = ("p(X, Y) <- eval_(X, Y)\n"
               "q(X, Y) <- 'is'(Y, X)\n")
        mod = _module(tmp_path, src)
        for name in ("p", "q"):
            y = Var()
            for _ in call(name, Fraction(2, 1), y, module=mod):
                got = deref(y)
                break
            else:
                pytest.fail(f"{name} had no solution")
            assert got == 2 and type(got) is int, (name, got)

    def test_seam_value_arithmetic(self, tmp_path):
        from clausal.import_hook import _load_module
        path = tmp_path / "_seam_integral.clausal"
        path.write_text(
            "-module(_seam_integral, [verdict(A, B, C)])\n"
            "-double_quotes(chars)\n"
            "def build():\n"
            "    return --verdict(4 / 2, (1 / 2) + (1 / 2), 3 / 2)\n")
        mod = _load_module("_seam_integral", str(path))
        got = mod.build()
        assert got == ("verdict", 2, 1, Fraction(3, 2))
        assert type(got[1]) is int and type(got[2]) is int, got
        assert type(got[3]) is Fraction, got


# ── ABSENCE: no path binds an integral Fraction at the unify boundary ──────
#
# The presence tests above each pin one producer we know about. This test
# drives a SPREAD of paths through one assertion — every value a logic
# variable ends up bound to is an int — so a producer nobody enumerated
# fails here instead of escaping. Each runner reads its values INSIDE the
# solve loop (draining the generator undoes the trail) and returns them.
#
# The unify census is enabled around every runner with a positive control
# first (unify(1, 1.0) must count exactly one), and the query must add
# nothing. The census sees ground-vs-ground compares only — a Fraction bound
# to a FRESH variable is invisible to it, which is why the type assertion,
# not the census, is the load-bearing check here (see the census-counter
# todo).


def _clausal_runner(src, name, nargs, ground=()):
    def run(tmp_path):
        mod = _module(tmp_path, src)
        outs = tuple(Var() for _ in range(nargs))
        for _ in call(name, *ground, *outs, module=mod):
            return [deref(v) for v in outs]
        pytest.fail(f"{name} had no solution")
    return run


def _seam_runner(tmp_path):
    from clausal.import_hook import _load_module
    path = tmp_path / "_seam_absence.clausal"
    path.write_text(
        "-module(_seam_absence, [verdict(A, B)])\n"
        "-double_quotes(chars)\n"
        "def build():\n"
        "    return --verdict(4 / 2, (1 / 2) + (1 / 2))\n")
    mod = _load_module("_seam_absence", str(path))
    _, a, b = mod.build()
    # and across the unify boundary, as a clause would consume them
    trail, x, y = Trail(), Var(), Var()
    assert unify(x, a, trail) and unify(y, b, trail)
    return [deref(x), deref(y)]


def _q_eq_fast_path_runner(tmp_path):
    from clausal.logic.clpq import q_eq, _tableaux, _last_snapshot
    _tableaux.clear(); _last_snapshot.clear()
    try:
        trail, w = Trail(), Var()
        assert q_eq(w, Fraction(6, 3), trail)
        return [deref(w)]
    finally:
        _tableaux.clear(); _last_snapshot.clear()


def _z3_runner(tmp_path):
    z3 = pytest.importorskip("z3")
    from clausal.logic.clpz3 import z3_to_python
    s = z3.Solver()
    r = z3.Real("r")
    s.add(r * 2 == 10)
    assert s.check() == z3.sat
    val = z3_to_python(s.model().eval(r, model_completion=True))
    trail, x = Trail(), Var()
    assert unify(x, val, trail)
    return [deref(x)]


ABSENCE_PATHS = {
    "quoted is/2": (_clausal_runner(
        "p(X) <- 'is'(X, 4 / 2)\n", "p", 1), [2]),
    "== through fd_eq/q_eq": (_clausal_runner(
        "p(X) <- (X == 4 / 2)\n", "p", 1), [2]),
    "== with a runtime operand": (_clausal_runner(
        "p(T, X) <- (X == T / 4)\n", "p", 1, ground=(700000,)), [175000]),
    "eval_ literal": (_clausal_runner(
        "p(X) <- eval_(4 / 2, X)\n", "p", 1), [2]),
    "eval_ sum of halves": (_clausal_runner(
        "p(X) <- eval_((1 / 2) + (1 / 2), X)\n", "p", 1), [1]),
    "seam value arithmetic": (_seam_runner, [2, 1]),
    "rational then ==": (_clausal_runner(
        "p(X) <- (rational(X), X == 4 / 2)\n", "p", 1), [2]),
    "solver-decided": (_clausal_runner(
        "p(X, Y) <- (rational([X, Y]), X + Y == 10, X - Y == 4)\n", "p", 2),
        [7, 3]),
    "sup/inf on a bounded rational": (_clausal_runner(
        "p(S, I) <- (rational(X), 0 <= X, X <= 4, sup(X, S), inf(X, I))\n",
        "p", 2), [4, 0]),
    "between with a quotient bound": (_clausal_runner(
        "p(X) <- between(2, 4 / 2, X)\n", "p", 1), [2]),
    "q_eq fast path (Python API)": (_q_eq_fast_path_runner, [2]),
    "z3 whole Real": (_z3_runner, [5]),
}


@pytest.mark.parametrize("path", list(ABSENCE_PATHS), ids=list(ABSENCE_PATHS))
def test_no_path_binds_an_integral_fraction(tmp_path, path):
    runner, want = ABSENCE_PATHS[path]
    unify_census_start()
    try:
        assert unify(1, 1.0, Trail())
        control = unify_census()
        assert control["conflations"] == 1, control       # the census is live
        assert control["by_type_pair"] == {"int/float": 1}, control
        got = runner(tmp_path)
        report = unify_census()
    finally:
        unify_census_stop()
    assert got == want, (path, got)
    assert all(type(v) is int for v in got), (path, got)
    assert report["conflations"] == 1, (path, report)     # the control only
    assert report["by_type_pair"] == {"int/float": 1}, (path, report)
