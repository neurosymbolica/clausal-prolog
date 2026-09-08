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


def test_structural_identity_distinguishes_int_from_float(scryer, run_clausal):
    """ISO's ==/2 distinguishes 1 from 1.0 (different types); Scryer says
    'no' (spec §3.1, "structural identity, `1 == 1.0` is false"). Restored
    to the brief's original (correct) assertion per fix round 1: `'=='`/2
    does NOT delegate straight to `structural_eq`/2 (which itself DOES
    conflate 1 and 1.0 — a separate, deliberately PARKED decision,
    A05-D001/A01-D001, governing `structural_eq`'s existing callers, and NOT
    touched by this fix). `'=='`/2 is a brand new predicate with no existing
    callers, so `_iso_identical` in iso_compare.py adds a stricter,
    type-aware check on top of `structural_eq` — see its docstring, and
    task-4-report.md, for the derivation and the before/after evidence."""
    src = ("-module(_hN, [p(R), yes, no])\n-double_quotes(chars)\n"
           "p(R) <- if_('=='(1, 1.0), R is yes, R is no)\n")
    assert run_clausal(src, ("p",)) == [repr(("no",))]
    assert scryer("(1 == 1.0 -> write(yes) ; write(no)), nl, halt.") == "no"


def test_structural_identity_still_holds_for_same_type_and_shape(
        scryer, run_clausal):
    """The other direction of the fix-round-1 ruling (item 3): tightening
    '==' for cross-type numerics must not make it reject same-type numbers
    or identical compound-shaped terms. `1 == 1` and two independently
    built, identical `[1, 2]` structures must both still read 'yes'."""
    src = ("-module(_hN, [p(R), yes, no])\n-double_quotes(chars)\n"
           "p(R) <- if_('=='(1, 1), R is yes, R is no)\n")
    assert run_clausal(src, ("p",)) == [repr(("yes",))]
    assert scryer("(1 == 1 -> write(yes) ; write(no)), nl, halt.") == "yes"

    src2 = ("-module(_hN, [p(R), yes, no])\n-double_quotes(chars)\n"
            "p(R) <- if_('=='([1, 2], [1, 2]), R is yes, R is no)\n")
    assert run_clausal(src2, ("p",)) == [repr(("yes",))]
    assert scryer("([1, 2] == [1, 2] -> write(yes) ; write(no)), "
                  "nl, halt.") == "yes"


def test_iso_unify_binds(run_clausal):
    got = run_clausal("-module(_hN, [p(X)])\n-double_quotes(chars)\n"
                      "p(X) <- '='(X, 42)\n", ("p",))
    assert got == ["42"]


def test_iso_unify_conflates_int_and_float_OPEN_iso_divergence(
        scryer, run_clausal):
    """OPEN, UNFIXED divergence from ISO — reported per fix round 1 item 4,
    not fixed this round.

    ISO unification of `1` and `1.0` FAILS (different types are never
    unifiable): measured directly, Scryer answers 'no' for `1 = 1.0`.
    Clausal's `'='`/2 is `clausal.logic.variables.unify` verbatim (per the
    brief), and `unify` — unlike `'=='`/2 above — was NOT given a
    type-strict wrapper this round: `unify` has a huge number of existing
    callers throughout the engine (every clause-head match, every `is`-as-
    unification site, `'\\='`/2's own trial-unify, …), so narrowing its
    cross-type numeric behavior is a much larger-blast-radius change than
    `'=='`/2's brand-new-predicate fix was, and is explicitly OUT OF SCOPE
    for this round (see task-4-report.md, "Finding on '='"). This test
    pins the CURRENT (ISO-diverging) behavior so a future change is a
    visible, deliberate decision rather than a silent regression in
    either direction."""
    src = ("-module(_hN, [p(R), yes, no])\n-double_quotes(chars)\n"
           "p(R) <- if_('='(1, 1.0), R is yes, R is no)\n")
    assert run_clausal(src, ("p",)) == [repr(("yes",))], \
        "current (diverging) Clausal behavior: '='(1, 1.0) succeeds"
    assert scryer("(1 = 1.0 -> write(yes) ; write(no)), nl, halt.") == "no", \
        "ISO/Scryer: 1 = 1.0 fails"


def test_iso_not_unifiable(run_clausal):
    src = ("-module(_hN, [p(R), yes, no])\n-double_quotes(chars)\n"
           "p(R) <- if_('\\\\='(1, 2), R is yes, R is no)\n")
    assert run_clausal(src, ("p",)) == [repr(("yes",))]


def test_iso_not_unifiable_fails_when_unifiable(run_clausal):
    src = ("-module(_hN, [p(R), yes, no])\n-double_quotes(chars)\n"
           "p(R) <- if_('\\\\='(X, X), R is yes, R is no)\n")
    assert run_clausal(src, ("p",)) == [repr(("no",))]


def test_iso_structural_ne(scryer, run_clausal):
    """'\\==' distinguishes 1 from 1.0 too — it's the direct negation of
    '==', which was fixed in fix round 1 to be ISO-correct on cross-type
    numerics (see test_structural_identity_distinguishes_int_from_float)."""
    src = ("-module(_hN, [p(R), yes, no])\n-double_quotes(chars)\n"
           "p(R) <- if_('\\\\=='(1, 1.0), R is yes, R is no)\n")
    assert run_clausal(src, ("p",)) == [repr(("yes",))]
    assert scryer("(1 \\== 1.0 -> write(yes) ; write(no)), nl, halt.") == "yes"


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


# ---------------------------------------------------------------------------
# The CLP constraint family: '#=', '#\=', '#<', '#>', '#=<', '#>='.
#
# `#=` is why this plan exists at all: infix `==` already compiles to
# nodes.ArithEq, a CLP arithmetic constraint that BINDS and PROPAGATES. A
# runtime measurement over 1933 corpus call sites (430,945 executions) found
# 33 sites that take TWO arithmetic modes — the same site binds on one call
# and tests on another. `'=:='` raises instantiation_error on the binding
# call; `'is'` is wrong for the testing one. `#=` is the only spelling valid
# in EVERY mode. The two tests below prove BOTH modes work through the SAME
# spelling — one-mode coverage does not discharge the requirement.
# ---------------------------------------------------------------------------


def test_hash_eq_is_valid_in_every_mode(scryer, run_clausal):
    """The 33 FORCED sites from the eq measurement take {BIND, TEST}: the same
    site binds on one call and tests on another. `#=` is the only spelling
    valid in both, which is why it is in the spec at all."""
    # BIND mode: the right side is ground, so X is bound.
    got = run_clausal("-module(_hN, [p(X)])\n-double_quotes(chars)\n"
                      "p(X) <- '#='(X, 2 + 1)\n", ("p",))
    assert got == ["3"]
    assert scryer("X #= 2 + 1, write(X), nl, halt.",
                  ":- use_module(library(clpz)).\n") == "3"


def test_hash_eq_also_TESTS_two_ground_values(run_clausal):
    """The other half of the {BIND, TEST} pair. Both must work through the
    SAME spelling or `#=` does not solve the forced sites."""
    src = ("-module(_hN, [p(R), yes, no])\n-double_quotes(chars)\n"
           "p(R) <- if_('#='(3, 2 + 1), R is yes, R is no)\n")
    assert run_clausal(src, ("p",)) == [repr(("yes",))]
    src_f = ("-module(_hN, [p(R), yes, no])\n-double_quotes(chars)\n"
             "p(R) <- if_('#='(4, 2 + 1), R is yes, R is no)\n")
    assert run_clausal(src_f, ("p",)) == [repr(("no",))]


# The remaining five family members ('#\=', '#<', '#>', '#=<', '#>=') get
# their own discriminating matrix, on the same machine-checked property as
# the arithmetic-comparison matrix above (test_the_matrix_discriminates_
# every_operator): no OTHER comparison function may reproduce an operator's
# result vector across its own rows. The row VALUES are reused verbatim from
# ROWS_BY_OPERATOR where possible -- ground-integer '#=' etc. reduce to the
# same fast-path Python comparison as '=:=' et al. (clausal/logic/clpfd.py's
# `type(l) is int and type(r) is int` fast path), so the discrimination
# already proven for those rows carries over. This is a separate structure
# (not a merge into ROWS_BY_OPERATOR/ARITH_ROWS) for two reasons: the
# constraint family needs `library(clpz)` loaded in Scryer, unlike plain
# '=:=' et al.; and clpz is INTEGER-only -- probed directly, `1 #= 1.0` in
# Scryer raises `domain_error(clpz_expression, 1.0)`, not a yes/no answer --
# so '=:='s float row `(1, 1.0, True)` cannot be reused for '#=' and is
# swapped for an all-integer row with the same boolean shape (T, F, F),
# which the discrimination proof only ever depended on.

_HASH_INTENDED = {"#=": "eq", "#\\=": "ne", "#<": "lt",
                  "#>": "gt", "#=<": "le", "#>=": "ge"}

_CLPZ_PROGRAM = ":- use_module(library(clpz)).\n"

HASH_ROWS_BY_OPERATOR = {
    "#=":   [(1, 1, True), (1, 2, False), (2, 1, False)],
    "#\\=": ROWS_BY_OPERATOR["=\\="],
    "#<":   ROWS_BY_OPERATOR["<"],
    "#>":   ROWS_BY_OPERATOR[">"],
    "#=<":  ROWS_BY_OPERATOR["=<"],
    "#>=":  ROWS_BY_OPERATOR[">="],
}

HASH_ROWS = [(_clausal_call(sym, a, b), _scryer_call(sym, a, b), expected)
             for sym, rows in HASH_ROWS_BY_OPERATOR.items()
             for a, b, expected in rows]


def test_the_hash_matrix_discriminates_every_operator():
    """Same property as test_the_matrix_discriminates_every_operator, run
    against the CLP constraint family's own row set — added rows must
    discriminate, and this is how that gets checked rather than assumed."""
    for op_name, rows in HASH_ROWS_BY_OPERATOR.items():
        mine = [expected for _, _, expected in rows]
        for cand_name, cand in _FUNCS.items():
            if cand_name == _HASH_INTENDED[op_name]:
                continue
            theirs = [cand(a, b) for a, b, _ in rows]
            assert mine != theirs, (
                f"{op_name} rows cannot be distinguished from {cand_name}")


@pytest.mark.parametrize("clausal_goal, scryer_goal, expected", HASH_ROWS)
def test_hash_constraint_matches_scryer_clpz(scryer, run_clausal,
                                             clausal_goal, scryer_goal, expected):
    src = ("-module(_hN, [p(R), yes, no])\n-double_quotes(chars)\n"
           f"p(R) <- if_({clausal_goal}, R is yes, R is no)\n")
    got = run_clausal(src, ("p",))
    assert got == [repr(("yes",) if expected else ("no",))]
    ref = scryer(f"({scryer_goal} -> write(yes) ; write(no)), nl, halt.",
                 _CLPZ_PROGRAM)
    assert ref == ("yes" if expected else "no"), "Scryer disagrees; Scryer is right"
