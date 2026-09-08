import operator as _op

import pytest


def test_harness_agrees_with_scryer_on_iso_is(scryer, run_clausal):
    """The oracle itself, proved against a predicate that ALREADY works, so a
    failure here means the harness is broken rather than the builtins."""
    assert scryer("X is 3 + 4, write(X), nl, halt.") == "7"
    got = run_clausal(
        "-module(_h1, [p(X)])\n-double_quotes(chars)\np(X) <- (X == 3 + 4)\n",
        ("p",))
    assert got == ["7"], "bare == already evaluates-and-binds; see the eq measurement"


# ---------------------------------------------------------------------------
# The comparison-operator test matrix.
#
# ROWS_BY_OPERATOR holds (a, b, expected) operand rows per ISO functor.  Rows
# are not hand-picked: test_the_matrix_discriminates_every_operator (below)
# is a machine-checked property every operator's row set must satisfy — no
# OTHER function in {eq, ne, lt, gt, le, ge} may agree with it across all its
# rows. The rows beyond the original engine-vs-Scryer set were found by a
# greedy search against that same property (fix round 2 on this task; see
# the task report for the derivation and a proof the check can actually
# fail). Notably that search found '>' still tied with 'ne' even after fix
# round 1's two rows — hand-picking a third row would likely have repeated
# the mistake.
# ---------------------------------------------------------------------------

_FUNCS = {"eq": _op.eq, "ne": _op.ne, "lt": _op.lt,
          "gt": _op.gt, "le": _op.le, "ge": _op.ge}

_INTENDED = {"=:=": "eq", "=\\=": "ne", "<": "lt",
             ">": "gt", "=<": "le", ">=": "ge"}

ROWS_BY_OPERATOR = {
    "=:=":  [(1, 1.0, True), (1, 2, False), (2, 1, False)],
    "=\\=": [(1, 2, True), (2, 1, True)],
    "<":    [(1, 2, True), (1, 1, False), (2, 1, False)],
    ">":    [(2, 2, False), (3, 2, True), (1, 2, False)],
    "=<":   [(2, 2, True), (1, 2, True)],
    ">=":   [(2, 3, False), (1, 1, True), (2, 1, True)],
}


def _clausal_call(sym, a, b):
    """`sym`, quoted, as clausal source text calling the ISO canonical functor.

    A literal backslash inside a quoted atom must itself be escaped for the
    reader, so the functor `=\\=` (one backslash) is written `=\\\\=` (two)
    in source text.
    """
    escaped = sym.replace("\\", "\\\\")
    return f"'{escaped}'({a}, {b})"


def _scryer_call(sym, a, b):
    return f"{a} {sym} {b}"


# The engine-vs-Scryer rows are DERIVED from ROWS_BY_OPERATOR, the same data
# the discrimination property checks, so the two can never drift apart.
ARITH_ROWS = [(_clausal_call(sym, a, b), _scryer_call(sym, a, b), expected)
              for sym, rows in ROWS_BY_OPERATOR.items()
              for a, b, expected in rows]


def test_the_matrix_discriminates_every_operator():
    """A row set that cannot tell `>` from `>=` does not test `>`.

    For each operator, no OTHER comparison function may produce the same
    result vector across that operator's rows.
    """
    for op_name, rows in ROWS_BY_OPERATOR.items():
        mine = [expected for _, _, expected in rows]
        for cand_name, cand in _FUNCS.items():
            if cand_name == _INTENDED[op_name]:
                continue
            theirs = [cand(a, b) for a, b, _ in rows]
            assert mine != theirs, (
                f"{op_name} rows cannot be distinguished from {cand_name}")


@pytest.mark.parametrize("clausal_goal, scryer_goal, expected", ARITH_ROWS)
def test_arithmetic_comparison_matches_scryer(scryer, run_clausal,
                                              clausal_goal, scryer_goal, expected):
    src = ("-module(_hN, [p(R), yes, no])\n-double_quotes(chars)\n"
           f"p(R) <- if_({clausal_goal}, R is yes, R is no)\n")
    got = run_clausal(src, ("p",))
    assert got == [repr(("yes",) if expected else ("no",))]
    ref = scryer(f"({scryer_goal} -> write(yes) ; write(no)), nl, halt.")
    assert ref == ("yes" if expected else "no"), "Scryer disagrees; Scryer is right"


# ---------------------------------------------------------------------------
# 'is'/2, '='/2, '\='/2, '=='/2, '\=='/2 under their ISO names.
# ---------------------------------------------------------------------------


def test_iso_is_evaluates_and_binds(scryer, run_clausal):
    """NOT the same as Clausal's infix `is`, which is unification: measured,
    `X is 3 + 4` in a clause body yields the TERM Add(3, 4). The canonical
    form is ISO's evaluate-and-bind."""
    got = run_clausal("-module(_hN, [p(X)])\n-double_quotes(chars)\n"
                      "p(X) <- 'is'(X, 3 + 4)\n", ("p",))
    assert got == ["7"]
    assert scryer("X is 3 + 4, write(X), nl, halt.") == "7"


def test_structural_identity_conflates_int_and_float_parked_iso_divergence(
        scryer, run_clausal):
    """ISO's ==/2 distinguishes 1 from 1.0 (different types) — Scryer says
    'no'. Clausal's `structural_eq`, which '==' /2 reuses unchanged per this
    task's brief, deliberately does NOT: cross-type numeric structural
    equality is PARKED
    (todo/audit-2026-07-05/done/fix-A05-structural-eq-asymmetry-consistency.md,
    A05-D001/A01-D001 — "do not change direction here, only keep it
    consistent with whatever unify does"). So `'=='(1, 1.0)` is 'yes' here,
    diverging from ISO. Recorded as a known gap, not silently papered over —
    see task-4-report.md concerns. This replaces the brief's Step-1 draft of
    this test, which assumed ISO's answer without checking the parked
    decision."""
    src = ("-module(_hN, [p(R), yes, no])\n-double_quotes(chars)\n"
           "p(R) <- if_('=='(1, 1.0), R is yes, R is no)\n")
    assert run_clausal(src, ("p",)) == [repr(("yes",))]
    assert scryer("(1 == 1.0 -> write(yes) ; write(no)), nl, halt.") == "no"


def test_iso_unify_binds(run_clausal):
    got = run_clausal("-module(_hN, [p(X)])\n-double_quotes(chars)\n"
                      "p(X) <- '='(X, 42)\n", ("p",))
    assert got == ["42"]


def test_iso_not_unifiable(run_clausal):
    src = ("-module(_hN, [p(R), yes, no])\n-double_quotes(chars)\n"
           "p(R) <- if_('\\\\='(1, 2), R is yes, R is no)\n")
    assert run_clausal(src, ("p",)) == [repr(("yes",))]


def test_iso_not_unifiable_fails_when_unifiable(run_clausal):
    src = ("-module(_hN, [p(R), yes, no])\n-double_quotes(chars)\n"
           "p(R) <- if_('\\\\='(X, X), R is yes, R is no)\n")
    assert run_clausal(src, ("p",)) == [repr(("no",))]


def test_iso_structural_ne(run_clausal):
    """'\\==' is the negation of '==': since '=='(1, 1.0) is 'yes' here (see
    test_structural_identity_conflates_int_and_float_parked_iso_divergence),
    '\\=='(1, 1.0) would be 'no' — not a useful positive-case row. A plain
    unequal integer pair exercises the true branch instead."""
    src = ("-module(_hN, [p(R), yes, no])\n-double_quotes(chars)\n"
           "p(R) <- if_('\\\\=='(1, 2), R is yes, R is no)\n")
    assert run_clausal(src, ("p",)) == [repr(("yes",))]


def test_infix_is_still_means_unification(run_clausal):
    """Global constraint: this plan must not change Clausal's infix `is`."""
    got = run_clausal("-module(_hN, [p(X)])\n-double_quotes(chars)\n"
                      "p(X) <- (X is 3 + 4)\n", ("p",))
    assert got == ["Add(left=3, right=4)"]


def test_infix_eqeq_still_evaluates_and_binds(run_clausal):
    """Global constraint: this plan must not change Clausal's infix `==`,
    which compiles to nodes.ArithEq (a CLP arithmetic constraint), not a
    predicate call."""
    got = run_clausal("-module(_hN, [p(X)])\n-double_quotes(chars)\n"
                      "p(X) <- (X == 3 + 4)\n", ("p",))
    assert got == ["7"]
