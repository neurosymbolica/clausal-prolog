"""Engine + oracle coverage for the ISO canonical comparison builtins.

EVERY test here comes in one of two shapes, and the split is load-bearing:

  * an ENGINE test, which asks only `run_clausal` and therefore runs on any
    box, oracle or no oracle;
  * an ORACLE test, which asks only `scryer` and records what the binding
    reference answers for the same row.

They used to be one function each, and 42 of the 52 tests requested the
`scryer` fixture, which skipped on a missing binary — taking the engine
assertions down with it, so breaking `'=<'` into `ge` on a box without Scryer
left the suite green. `tests/iso/conftest.py` now FAILS on a missing oracle
unless `CLAUSAL_ISO_ALLOW_NO_SCRYER` is set; the split is what makes that
opt-out safe to use, because the engine half still runs.
"""
import operator as _op

import pytest


_YES = repr(("yes",))
_NO = repr(("no",))


def _yesno_src(goal, extra_atoms=()):
    """A one-clause module whose `p(R)` answers `yes`/`no` for *goal*."""
    atoms = ", ".join(("p(R)", "yes", "no") + tuple(extra_atoms))
    return (f"-module(_hN, [{atoms}])\n-double_quotes(chars)\n"
            f"p(R) <- if_({goal}, R is yes, R is no)\n")


def _engine_yesno(run_clausal, goal, extra_atoms=()):
    return run_clausal(_yesno_src(goal, extra_atoms), ("p",))


def test_harness_engine_side(run_clausal):
    """The harness itself, proved against a construct that ALREADY works, so a
    failure here means the harness is broken rather than the builtins."""
    got = run_clausal(
        "-module(_h1, [p(X)])\n-double_quotes(chars)\np(X) <- (X == 3 + 4)\n",
        ("p",))
    assert got == ["7"], "bare == already evaluates-and-binds; see the eq measurement"


def test_harness_oracle_side(scryer):
    assert scryer("X is 3 + 4, write(X), nl, halt.") == "7"


# ---------------------------------------------------------------------------
# The comparison-operator test matrix.
#
# ROWS_BY_OPERATOR holds (a, b, expected) operand rows per ISO functor.  Rows
# are not hand-picked: test_the_matrix_discriminates_every_operator (below)
# is a machine-checked property every operator's row set must satisfy — no
# OTHER function in {eq, ne, lt, gt, le, ge} may agree with it across all its
# rows. The rows beyond the original engine-vs-Scryer set were found by a
# greedy search against that same property. Notably that search found '>'
# still tied with 'ne' even after the first two added rows — hand-picking a
# third row would likely have repeated the mistake.
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


# The engine and oracle rows are both DERIVED from ROWS_BY_OPERATOR, the same
# data the discrimination property checks, so the three can never drift apart.
ARITH_ROWS = [(sym, _clausal_call(sym, a, b), _scryer_call(sym, a, b), expected)
              for sym, rows in ROWS_BY_OPERATOR.items()
              for a, b, expected in rows]

_ARITH_IDS = [f"{sym} {a} {b}" for sym, rows in ROWS_BY_OPERATOR.items()
              for a, b, _ in rows]


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


@pytest.mark.parametrize("sym, clausal_goal, scryer_goal, expected",
                         ARITH_ROWS, ids=_ARITH_IDS)
def test_arithmetic_comparison_engine(run_clausal, sym, clausal_goal,
                                      scryer_goal, expected):
    assert _engine_yesno(run_clausal, clausal_goal) == [_YES if expected else _NO]


@pytest.mark.parametrize("sym, clausal_goal, scryer_goal, expected",
                         ARITH_ROWS, ids=_ARITH_IDS)
def test_arithmetic_comparison_oracle(scryer, sym, clausal_goal,
                                      scryer_goal, expected):
    ref = scryer(f"({scryer_goal} -> write(yes) ; write(no)), nl, halt.")
    assert ref == ("yes" if expected else "no"), "Scryer disagrees; Scryer is right"


# ---------------------------------------------------------------------------
# 'is'/2, '='/2, '\='/2, '=='/2, '\=='/2 under their ISO names.
# ---------------------------------------------------------------------------


def test_iso_is_evaluates_and_binds(run_clausal):
    """NOT the same as Clausal's infix `is`, which is unification: measured,
    `X is 3 + 4` in a clause body yields the TERM Add(3, 4). The canonical
    form is ISO's evaluate-and-bind."""
    got = run_clausal("-module(_hN, [p(X)])\n-double_quotes(chars)\n"
                      "p(X) <- 'is'(X, 3 + 4)\n", ("p",))
    assert got == ["7"]


def test_iso_is_evaluates_and_binds_oracle(scryer):
    assert scryer("X is 3 + 4, write(X), nl, halt.") == "7"


def test_structural_identity_distinguishes_int_from_float(run_clausal):
    """ISO's ==/2 distinguishes 1 from 1.0 (different types).

    `'=='`/2 does NOT delegate straight to `structural_eq`/2, which DOES
    conflate 1 and 1.0 — a separate, deliberately PARKED decision
    (A05-D001/A01-D001) governing `structural_eq`'s existing callers and NOT
    touched here. `'=='`/2 is a brand new predicate with no existing callers,
    so `_iso_identical` in iso_compare.py adds a narrow, numbers-only strict
    check on top of `structural_eq`."""
    assert _engine_yesno(run_clausal, "'=='(1, 1.0)") == [_NO]


def test_structural_identity_distinguishes_int_from_float_oracle(scryer):
    assert scryer("(1 == 1.0 -> write(yes) ; write(no)), nl, halt.") == "no"


def test_structural_identity_still_holds_for_same_type_and_shape(run_clausal):
    """Tightening '==' for cross-type numerics must not make it reject
    same-type numbers or identical compound-shaped terms."""
    assert _engine_yesno(run_clausal, "'=='(1, 1)") == [_YES]
    assert _engine_yesno(run_clausal, "'=='([1, 2], [1, 2])") == [_YES]


def test_structural_identity_still_holds_for_same_type_and_shape_oracle(scryer):
    assert scryer("(1 == 1 -> write(yes) ; write(no)), nl, halt.") == "yes"
    assert scryer("([1, 2] == [1, 2] -> write(yes) ; write(no)), "
                  "nl, halt.") == "yes"


# ---------------------------------------------------------------------------
# A string and its char list are ONE term, so `'=='` must say so.
#
# Every other `'=='` row in this file writes the SAME literal syntax on both
# sides, which is why a whole-term key comparison inside `_iso_identical`
# could reject a difference of pure REPRESENTATION without any test noticing.
# These rows write the two sides differently on purpose.
# ---------------------------------------------------------------------------


def test_structural_identity_of_a_string_and_its_char_list(run_clausal):
    """Under `-double_quotes(chars)` a string IS its char list — one term.

    Spec §3.3, verbatim: "under `-double_quotes(chars)` a string IS its char
    list, one term, so `'=='("ab", [a, b])` is true". Three authorities agree
    on yes: the spec, Scryer (see the oracle test below) and Clausal's own
    `'='`/2 and `structural_eq`/2, both of which already answer yes for this
    pair. `'=='` disagreeing with `'='` on a GROUND pair is impossible in ISO
    — for ground terms `=` and `==` coincide.

    Measured 2026-09-09 BEFORE the fix, with `_iso_identical`'s second
    conjunct still a whole-term `_normalize_for_key(_deref_walk(…))` key
    comparison (`_deref_walk` does not materialize a `str` into its char
    list, so the keys were `'ab'` against `[('a',), ('b',)]`):

        '=='("ab", [a, b])        Clausal: no    Scryer: YES
        '\\=='("ab", [a, b])      Clausal: yes   Scryer: no
        '='("ab", [a, b])         Clausal: yes   Scryer: yes
        structural_eq("ab", [a, b])  Clausal: yes (pre-existing)
    """
    assert _engine_yesno(run_clausal, "'=='(\"ab\", [a, b])", ("a", "b")) == [_YES]
    assert _engine_yesno(run_clausal, "'\\\\=='(\"ab\", [a, b])", ("a", "b")) == [_NO]


def test_structural_identity_of_a_string_and_its_char_list_agrees_with_unify(
        run_clausal):
    """The consistency half: `'='` and `'=='` may not disagree on a ground
    pair, and `structural_eq`/2 (untouched by this branch, parked decision
    A05-D001) is the third witness."""
    assert _engine_yesno(run_clausal, "'='(\"ab\", [a, b])", ("a", "b")) == [_YES]
    assert _engine_yesno(run_clausal, "structural_eq(\"ab\", [a, b])",
                         ("a", "b")) == [_YES]


def test_structural_identity_of_a_string_and_its_char_list_oracle(scryer):
    chars = ":- set_prolog_flag(double_quotes, chars).\n"
    assert scryer('("ab" == [a, b] -> write(yes) ; write(no)), nl, halt.',
                  chars) == "yes"
    assert scryer('("ab" \\== [a, b] -> write(yes) ; write(no)), nl, halt.',
                  chars) == "no"
    assert scryer('("ab" = [a, b] -> write(yes) ; write(no)), nl, halt.',
                  chars) == "yes"


def test_structural_identity_is_still_strict_inside_a_compound(run_clausal):
    """The narrow numeric check must survive nesting: `[1]` and `[1.0]` are
    not identical, and neither are two same-shaped terms differing only in an
    inner number's type. This is what a blunt "both sides are numbers" gate
    would have lost."""
    assert _engine_yesno(run_clausal, "'=='([1], [1.0])") == [_NO]
    assert _engine_yesno(run_clausal, "'=='([1, 2], [1, 2.0])") == [_NO]


def test_structural_identity_is_still_strict_inside_a_compound_oracle(scryer):
    assert scryer("([1] == [1.0] -> write(yes) ; write(no)), nl, halt.") == "no"
    assert scryer("([1, 2] == [1, 2.0] -> write(yes) ; write(no)), "
                  "nl, halt.") == "no"


def test_iso_unify_binds(run_clausal):
    got = run_clausal("-module(_hN, [p(X)])\n-double_quotes(chars)\n"
                      "p(X) <- '='(X, 42)\n", ("p",))
    assert got == ["42"]


def test_iso_unify_conflates_int_and_float_OPEN_iso_divergence(run_clausal):
    """OPEN, UNFIXED divergence from ISO. Documents, does not bless.

    ISO unification of `1` and `1.0` FAILS (different types are never
    unifiable): measured directly, Scryer answers 'no' for `1 = 1.0` (see the
    oracle half below). Clausal's `'='`/2 is
    `clausal.logic.variables.unify` verbatim, and `unify` — unlike `'=='`/2
    — was NOT given a type-strict wrapper: it has a huge number of existing
    callers throughout the engine (every clause-head match, every
    `is`-as-unification site, `'\\='`/2's own trial-unify, …), so narrowing
    its cross-type numeric behaviour is an engine-wide change and is the
    operator's call, not this branch's.

    Deferred deliberately; the durable record is
    todo/iso-unify-conflates-int-and-float-2026-09-09.md, which covers this
    pin AND its `'is'` twin below."""
    assert _engine_yesno(run_clausal, "'='(1, 1.0)") == [_YES], \
        "current (diverging) Clausal behavior: '='(1, 1.0) succeeds"


def test_iso_unify_conflates_int_and_float_OPEN_iso_divergence_oracle(scryer):
    assert scryer("(1 = 1.0 -> write(yes) ; write(no)), nl, halt.") == "no", \
        "ISO/Scryer: 1 = 1.0 fails"


def test_iso_is_conflates_int_and_float_OPEN_iso_divergence(run_clausal):
    """The SAME open divergence as `'='`/2 above, through the hotter
    spelling. Documents, does not bless.

    `'is'`/2 ends in the same `unify`, so it inherits the same int/float
    conflation: measured 2026-09-09, `'is'(7.0, 3 + 4)` SUCCEEDS in Clausal
    while Scryer answers no (oracle half below). Spec §2 records that the
    `'is'` role is where ~826 corpus goal positions are heading, against a
    handful for `'='` — so this, not the `'='` pin, is the instance that
    will actually be hit. Same deferral and same record:
    todo/iso-unify-conflates-int-and-float-2026-09-09.md."""
    assert _engine_yesno(run_clausal, "'is'(7.0, 3 + 4)") == [_YES], \
        "current (diverging) Clausal behavior: 'is'(7.0, 3 + 4) succeeds"
    # The int spelling is not in dispute in either engine.
    assert _engine_yesno(run_clausal, "'is'(7, 3 + 4)") == [_YES]


def test_iso_is_conflates_int_and_float_OPEN_iso_divergence_oracle(scryer):
    assert scryer("(7.0 is 3 + 4 -> write(yes) ; write(no)), nl, halt.") == "no", \
        "ISO/Scryer: 7.0 is 3 + 4 fails"
    assert scryer("(7 is 3 + 4 -> write(yes) ; write(no)), nl, halt.") == "yes"


def test_iso_not_unifiable(run_clausal):
    src = ("-module(_hN, [p(R), yes, no])\n-double_quotes(chars)\n"
           "p(R) <- if_('\\\\='(1, 2), R is yes, R is no)\n")
    assert run_clausal(src, ("p",)) == [_YES]


def test_iso_not_unifiable_fails_when_unifiable(run_clausal):
    src = ("-module(_hN, [p(R), yes, no])\n-double_quotes(chars)\n"
           "p(R) <- if_('\\\\='(X, X), R is yes, R is no)\n")
    assert run_clausal(src, ("p",)) == [_NO]


def test_iso_structural_ne(run_clausal):
    """'\\==' distinguishes 1 from 1.0 too — it is the direct negation of
    '=='."""
    src = ("-module(_hN, [p(R), yes, no])\n-double_quotes(chars)\n"
           "p(R) <- if_('\\\\=='(1, 1.0), R is yes, R is no)\n")
    assert run_clausal(src, ("p",)) == [_YES]


def test_iso_structural_ne_oracle(scryer):
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


def test_hash_eq_is_valid_in_every_mode(run_clausal):
    """The 33 FORCED sites from the eq measurement take {BIND, TEST}: the same
    site binds on one call and tests on another. `#=` is the only spelling
    valid in both, which is why it is in the spec at all."""
    # BIND mode: the right side is ground, so X is bound.
    got = run_clausal("-module(_hN, [p(X)])\n-double_quotes(chars)\n"
                      "p(X) <- '#='(X, 2 + 1)\n", ("p",))
    assert got == ["3"]


def test_hash_eq_is_valid_in_every_mode_oracle(scryer):
    assert scryer("X #= 2 + 1, write(X), nl, halt.",
                  ":- use_module(library(clpz)).\n") == "3"


def test_hash_eq_also_TESTS_two_ground_values(run_clausal):
    """The other half of the {BIND, TEST} pair. Both must work through the
    SAME spelling or `#=` does not solve the forced sites."""
    assert _engine_yesno(run_clausal, "'#='(3, 2 + 1)") == [_YES]
    assert _engine_yesno(run_clausal, "'#='(4, 2 + 1)") == [_NO]


def test_hash_eq_int_float_OPEN_iso_divergence(run_clausal):
    """OPEN, UNFIXED divergence from ISO/Scryer's clpz. Documents, does not
    bless.

    Clausal's CLP spans both R and Z: `fd_eq` (clausal/logic/clpfd.py) routes
    a float operand to CLP(R) rather than rejecting it, so `'#='(1, 1.0)`
    succeeds — and this is the SAME `fd_eq` that Clausal's own infix `==`
    already compiles to (nodes.ArithEq), so making `'#='` reject floats would
    make it disagree with infix `==` on identical inputs, which is worse
    than `'#='` being broader than Scryer's clpz. Same reasoning that
    deferred `'='(1, 1.0)` above.

    Scryer's clpz is INTEGER-only: `1 #= 1.0` is not merely false, it is a
    domain error (see the oracle half) because 1.0 is not a valid clpz
    expression at all."""
    assert _engine_yesno(run_clausal, "'#='(1, 1.0)") == [_YES], \
        "current (diverging) Clausal behavior: '#='(1, 1.0) succeeds via CLP(R)"


def test_hash_eq_int_float_OPEN_iso_divergence_oracle(scryer):
    ref = scryer("(1 #= 1.0 -> write(yes) ; write(no)), nl, halt.",
                 ":- use_module(library(clpz)).\n")
    assert ref == "error(domain_error(clpz_expression,1.0),unknown(1.0)-1).", \
        f"ISO/Scryer clpz: 1 #= 1.0 is a domain error, not yes/no; got {ref!r}"


# The remaining five family members ('#\=', '#<', '#>', '#=<', '#>=') get
# their own discriminating matrix, on the same machine-checked property as
# the arithmetic-comparison matrix above (test_the_matrix_discriminates_
# every_operator): no OTHER comparison function may reproduce an operator's
# result vector across its own rows. The row VALUES are COPIED from
# ROWS_BY_OPERATOR where possible -- ground-integer '#=' etc. reduce to the
# same fast-path Python comparison as '=:=' et al. (clausal/logic/clpfd.py's
# `type(l) is int and type(r) is int` fast path), so the discrimination
# already proven for those rows carries over. They are COPIES, not aliases:
# sharing the list objects meant adding a float row for '<' would silently
# propagate into '#<', where a float is a clpz domain error rather than a
# comparison.
#
# This is a separate structure (not a merge into ROWS_BY_OPERATOR/ARITH_ROWS)
# for two reasons: the constraint family needs `library(clpz)` loaded in
# Scryer, unlike plain '=:=' et al.; and clpz is INTEGER-only, while the
# ENGINE is not -- probed directly, `1 #= 1.0` raises
# `domain_error(clpz_expression, 1.0)` in Scryer but SUCCEEDS in Clausal
# (`fd_eq` routes the float operand to CLP(R)). That is a real, PINNED
# engine/Scryer divergence -- see test_hash_eq_int_float_OPEN_iso_divergence
# above. Here it just means '=:='s float row `(1, 1.0, True)` can't be
# reused for a Scryer-comparison row (Scryer errors, it doesn't answer
# yes/no), so this matrix's '#=' row is swapped for an all-integer row with
# the same boolean shape (T, F, F), which the discrimination proof only
# ever depended on.

_HASH_INTENDED = {"#=": "eq", "#\\=": "ne", "#<": "lt",
                  "#>": "gt", "#=<": "le", "#>=": "ge"}

_CLPZ_PROGRAM = ":- use_module(library(clpz)).\n"

HASH_ROWS_BY_OPERATOR = {
    "#=":   [(1, 1, True), (1, 2, False), (2, 1, False)],
    "#\\=": list(ROWS_BY_OPERATOR["=\\="]),
    "#<":   list(ROWS_BY_OPERATOR["<"]),
    "#>":   list(ROWS_BY_OPERATOR[">"]),
    "#=<":  list(ROWS_BY_OPERATOR["=<"]),
    "#>=":  list(ROWS_BY_OPERATOR[">="]),
}

HASH_ROWS = [(sym, _clausal_call(sym, a, b), _scryer_call(sym, a, b), expected)
             for sym, rows in HASH_ROWS_BY_OPERATOR.items()
             for a, b, expected in rows]

_HASH_IDS = [f"{sym} {a} {b}" for sym, rows in HASH_ROWS_BY_OPERATOR.items()
             for a, b, _ in rows]


def test_the_hash_row_lists_are_copies_not_aliases():
    """The two matrices must not share list objects: a float row added for
    '<' would otherwise appear under '#<', where a float is a clpz domain
    error rather than a comparison."""
    for hash_sym, plain_sym in (("#\\=", "=\\="), ("#<", "<"), ("#>", ">"),
                                ("#=<", "=<"), ("#>=", ">=")):
        assert HASH_ROWS_BY_OPERATOR[hash_sym] is not ROWS_BY_OPERATOR[plain_sym]


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


@pytest.mark.parametrize("sym, clausal_goal, scryer_goal, expected",
                         HASH_ROWS, ids=_HASH_IDS)
def test_hash_constraint_engine(run_clausal, sym, clausal_goal,
                                scryer_goal, expected):
    assert _engine_yesno(run_clausal, clausal_goal) == [_YES if expected else _NO]


@pytest.mark.parametrize("sym, clausal_goal, scryer_goal, expected",
                         HASH_ROWS, ids=_HASH_IDS)
def test_hash_constraint_oracle(scryer, sym, clausal_goal,
                                scryer_goal, expected):
    ref = scryer(f"({scryer_goal} -> write(yes) ; write(no)), nl, halt.",
                 _CLPZ_PROGRAM)
    assert ref == ("yes" if expected else "no"), "Scryer disagrees; Scryer is right"


# ---------------------------------------------------------------------------
# `_iso_identical` at the Python level: the full representation table.
#
# The `.clausal` tests above cover what a source file can spell. This table
# covers the shapes only Python can build, and states the design property of
# `_numeric_types_agree` directly: it objects ONLY to a pair of corresponding
# tagged numbers of different type, never to a difference of representation
# that `structural_eq` blesses. Each row also carries `structural_eq`'s own
# answer, so a change to `structural_eq` (a PARKED decision this branch does
# not touch) shows up here as a failure rather than as a silent shift.
# ---------------------------------------------------------------------------


def _identity_table():
    from decimal import Decimal
    from clausal.terms import Compound
    return [
        # (a, b, structural_eq, iso '==')
        (1, 1.0, True, False),                 # the ISO case
        (1, 1, True, True),
        (1.0, 1.0, True, True),
        (True, 1, True, False),                # bool is type-distinguished
        ([1], [1.0], True, False),             # strictness survives nesting
        ([1, 2], [1, 2], True, True),
        ((1, 2), (1, 2.0), True, False),
        (Compound("f", (1,)), Compound("f", (1.0,)), True, False),
        ({"a": 1}, {"a": 1.0}, True, False),
        ({1}, {1.0}, True, False),
        # Representation, not type: these must stay identical.
        ("ab", [("a",), ("b",)], True, True),  # a string IS its char list
        (b"ab", [97, 98], True, True),         # bytes IS the code list
        # Decimal is NOT tagged, here or in `_normalize_for_key` (a
        # documented residual under A01-D001), so this branch opens no new
        # front on the decimal-currency values.
        (Decimal(1), 1, True, True),
    ]


def test_iso_identical_representation_table():
    from clausal.logic.builtins.iso_compare import _iso_identical
    from clausal.logic.constraints import structural_eq

    rows = _identity_table()
    assert rows, "an empty table would make this test vacuous"
    for a, b, expect_structural, expect_iso in rows:
        assert structural_eq(a, b) is expect_structural, (a, b)
        assert _iso_identical(a, b) is expect_iso, (a, b)
        # `'\=='` is the exact negation, in both directions.
        assert _iso_identical(b, a) is expect_iso, ("symmetry", a, b)
