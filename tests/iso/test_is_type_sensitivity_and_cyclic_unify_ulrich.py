"""Two Ciao `iso_tests` regressions, surfaced by a sweep ahead of the Ulrich
Neumerkel presentation (2026-10-15):

* Bug 1 — `is_test4` (``3 is 3.0``): ISO's implicit result-unification in
  `is`/2 is `=`/2's unification, which is type-sensitive between numeric
  kinds, so `3 is 3.0` must FAIL even though `3 =:= 3.0`.  Clausal's shared
  engine `unify` conflates int/float for its many other callers (an OPEN,
  deliberately deferred decision — todo/done/iso-unify-conflates-int-and-float-
  2026-09-09.md), so the fix lives in `is`/2's own builtin
  (`clausal/logic/builtins/iso_compare.py::_iso_is`), guarded by
  `_numeric_types_agree` (already used by `'=='`/2 for the same question),
  not in the shared `unify`.

* Bug 2 — `unify_test16` / `not_uni_test15`
  (``'='(f(X, Y, X, 1), f(a(X), a(Y), Y, 2))`` and its `'\\='`/2 twin): the
  third argument asks to unify X (bound to the self-containing `a(X)`)
  against Y (bound to the self-containing `a(Y)`); a naive recursive unify
  walk re-enters that pair forever and used to crash the engine with a raw
  ``RecursionError: unify: term nesting too deep`` instead of letting the
  FOURTH argument (`1` against `2`) decide the whole unification.  Fixed in
  `_cycle_unify` (same file), the SAME explicit-stack / seen-pairs pattern
  `==`/2 already uses for a cyclic term (`a480b5b8`, `51f4e844`).

Both the engine outcome AND Scryer's own answer are pinned (Ciao's asserted
outcome for `is_test4`/`unify_test16` is `fails`, `not_uni_test15` is
`not_fails`; treated as a cross-check hint, with Scryer as the oracle for
`is/2`'s cases).  Reuses the `run_clausal` fixture pattern from
`test_iso_answers_scryer.py`/`test_iso_compare_scryer.py`: `deref` is always
called INSIDE the `solve()` loop, never after draining the generator.
"""
from __future__ import annotations

import itertools

import pytest

from clausal.logic.exceptions import LogicException
from clausal.logic.solve import solve
from clausal.logic.variables import Trail, Var, deref


def _yesno_src(goal: str, implicit_functors: bool = False) -> str:
    header = "-module(_hN, [p(R), yes, no])\n-double_quotes(chars)\n"
    if implicit_functors:
        header += "-implicit_functors\n"
    return header + f"p(R) <- ((({goal}), R is yes) or (not ({goal}), R is no))\n"


def _engine_yesno(run_clausal, goal, implicit_functors=False):
    return run_clausal(_yesno_src(goal, implicit_functors), ("p",))


# ---------------------------------------------------------------------------
# Bug 1: is/2 must be type-sensitive between int and float.
# ---------------------------------------------------------------------------

def test_is_int_left_float_right_fails(run_clausal):
    """`3 is 3.0` — the Ciao `is_test4` case. ISO/Scryer: fails."""
    assert _engine_yesno(run_clausal, "'is'(3, 3.0)") == ["'no'"]


def test_is_int_left_float_right_fails_oracle(scryer):
    assert scryer("(3 is 3.0 -> write(yes) ; write(no)), nl, halt.") == "no"


def test_is_float_left_float_right_succeeds(run_clausal):
    """`3.0 is 3.0` — same numeric kind on both sides, must still succeed."""
    assert _engine_yesno(run_clausal, "'is'(3.0, 3.0)") == ["'yes'"]


def test_is_float_left_float_right_succeeds_oracle(scryer):
    assert scryer("(3.0 is 3.0 -> write(yes) ; write(no)), nl, halt.") == "yes"


def test_is_int_left_int_right_succeeds(run_clausal):
    """`3 is 3` — the common, overwhelmingly-hit case must be untouched."""
    assert _engine_yesno(run_clausal, "'is'(3, 3)") == ["'yes'"]


def test_is_unbound_left_binds_to_float(run_clausal):
    """`X is 3.0` with X UNBOUND must still succeed and bind X = 3.0 — the
    bug is about an already-bound left argument of a DIFFERENT numeric
    type, never about binding a fresh variable."""
    got = run_clausal(
        "-module(_h1, [p(X)])\n-double_quotes(chars)\np(X) <- 'is'(X, 3.0)\n",
        ("p",))
    assert got == ["3.0"]


def test_is_unbound_left_binds_to_int(run_clausal):
    got = run_clausal(
        "-module(_h1, [p(X)])\n-double_quotes(chars)\np(X) <- 'is'(X, 3)\n",
        ("p",))
    assert got == ["3"]


def test_is_float_left_int_expr_fails(run_clausal):
    """`7.0 is 7` — the mirror of `is_test4`: float literal against an
    integer-valued expression."""
    assert _engine_yesno(run_clausal, "'is'(7.0, 3 + 4)") == ["'no'"]


def test_is_float_left_int_expr_fails_oracle(scryer):
    assert scryer("(7.0 is 3 + 4 -> write(yes) ; write(no)), nl, halt.") == "no"


def test_is_int_left_int_expr_succeeds(run_clausal):
    """`7 is 3 + 4` — the int spelling is not in dispute; must stay green."""
    assert _engine_yesno(run_clausal, "'is'(7, 3 + 4)") == ["'yes'"]


def test_is_int_left_int_expr_succeeds_oracle(scryer):
    assert scryer("(7 is 3 + 4 -> write(yes) ; write(no)), nl, halt.") == "yes"


def test_is_float_left_float_expr_succeeds(run_clausal):
    """`7.0 is 3.0 + 4.0` — matching float kinds on both sides."""
    assert _engine_yesno(run_clausal, "'is'(7.0, 3.0 + 4.0)") == ["'yes'"]


def test_is_float_left_float_expr_succeeds_oracle(scryer):
    assert scryer(
        "(7.0 is 3.0 + 4.0 -> write(yes) ; write(no)), nl, halt."
    ) == "yes"


# ---------------------------------------------------------------------------
# Bug 2: unifying (or trial-unifying) two cyclic terms must terminate
# cleanly instead of raising RecursionError.
# ---------------------------------------------------------------------------

_CYCLIC_PAIR = "'=' (f(X, Y, X, 1), f(a(X), a(Y), Y, 2))".replace(" (", "(")


def test_unify_test16_cyclic_unify_fails_cleanly(run_clausal):
    """Ciao `unify_test16`: `'='(f(X, Y, X, 1), f(a(X), a(Y), Y, 2))`.

    X ends up bound to the self-containing `a(X)`, Y to the self-containing
    `a(Y)`; the third argument unifies those two cyclic terms (a
    rational-tree cycle, not a contradiction) and the FOURTH argument
    (`1` vs `2`) is what actually decides it. Ciao-asserted outcome: fails.
    Before the fix this raised `RecursionError: unify: term nesting too
    deep` instead of failing.
    """
    assert _engine_yesno(run_clausal, _CYCLIC_PAIR, implicit_functors=True) == ["'no'"]


def test_not_uni_test15_cyclic_unify_not_fails_cleanly(run_clausal):
    """Ciao `not_uni_test15`: `'\\='(f(X, Y, X, 1), f(a(X), a(Y), Y, 2))`,
    X and Y FRESH (unbound) at the call.  `\\=`/2's own trial unification
    hits the identical cyclic pair and the identical `1`-vs-`2` mismatch, so
    the underlying unify fails and the negation succeeds. Ciao-asserted
    outcome: not_fails (succeeds). Before the fix this raised the same
    RecursionError from inside `\\=`/2's trial unify.
    """
    goal = "'\\\\='(f(X, Y, X, 1), f(a(X), a(Y), Y, 2))"
    assert _engine_yesno(run_clausal, goal, implicit_functors=True) == ["'yes'"]


def test_cyclic_unify_does_not_raise_recursion_error(run_clausal):
    """Directly pins the ISO-required SHAPE of the outcome (a clean
    success/failure, never an uncaught Python exception) by driving
    `solve()` itself rather than going through the yes/no wrapper — a
    RecursionError escaping `solve()` would abort the harness, not report
    as a Prolog failure."""
    src = ("-module(_h2, [p(R), yes, no])\n-double_quotes(chars)\n-implicit_functors\n"
           "p(R) <- (('='(f(X, Y, X, 1), f(a(X), a(Y), Y, 2)), R is yes) "
           "or (not ('='(f(X, Y, X, 1), f(a(X), a(Y), Y, 2))), R is no))\n")
    import os
    import tempfile

    import clausal
    from clausal.import_hook import _load_module
    from tests._suffix import SEAM

    assert os.getcwd() in clausal.__file__, clausal.__file__
    d = tempfile.mkdtemp()
    path = os.path.join(d, f"_cyclicdirect{SEAM}")
    with open(path, "w") as fh:
        fh.write(src)
    mod = _load_module("_cyclicdirect", path)
    r = Var()
    trail = Trail()
    try:
        results = [
            repr(deref(r))
            for _ in itertools.islice(solve(("p", r), mod, trail), 3)
        ]
    except RecursionError:
        pytest.fail("cyclic unify raised a raw RecursionError instead of "
                    "a clean Prolog-level outcome")
    assert results == ["'no'"]


# ---------------------------------------------------------------------------
# Non-cyclic unify/is sanity: the existing, ordinary cases must stay green.
# ---------------------------------------------------------------------------

def test_plain_unify_still_succeeds(run_clausal):
    assert _engine_yesno(run_clausal, "'='(foo(1, 2), foo(1, 2))",
                         implicit_functors=True) == ["'yes'"]


def test_plain_unify_still_fails_on_mismatch(run_clausal):
    assert _engine_yesno(run_clausal, "'='(foo(1, 2), foo(1, 3))",
                         implicit_functors=True) == ["'no'"]


def test_plain_not_unifiable_still_works(run_clausal):
    assert _engine_yesno(run_clausal, "'\\\\='(foo(1, 2), foo(1, 3))",
                         implicit_functors=True) == ["'yes'"]
    assert _engine_yesno(run_clausal, "'\\\\='(foo(1, 2), foo(1, 2))",
                         implicit_functors=True) == ["'no'"]


def test_unify_still_binds_a_fresh_variable(run_clausal):
    got = run_clausal(
        "-module(_h1, [p(X)])\n-double_quotes(chars)\n-implicit_functors\n"
        "p(X) <- '='(X, foo(1, 2))\n",
        ("p",))
    assert got == ["('foo', 1, 2)"]


def test_unify_int_float_distinct_closed_2026_10_23(run_clausal):
    """Formerly `test_unify_int_float_conflation_still_open`: when the `is`/2
    half of todo/done/iso-unify-conflates-int-and-float-2026-09-09.md was
    fixed (2026-10-15), `'='`/2 itself was deliberately left conflating
    int/float, and this pinned that.  The operator ruling of 2026-10-23
    closed the `'='`/2 half too (ISO 7.3): the shared `unify` refuses a
    number against a number of another kind, so `'='(1, 1.0)` fails -- the
    `is`/2 guard below is now an early answer to the same question."""
    assert _engine_yesno(run_clausal, "'='(1, 1.0)") == ["'no'"]
