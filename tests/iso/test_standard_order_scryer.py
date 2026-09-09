"""Standard-order PREDICATES against the Scryer oracle.

Engine assertions live in tests SEPARATE from oracle assertions, so a missing
Scryer binary cannot retire engine coverage — 42 of 52 tests on the
predecessor branch skipped together because the two were fused.

Spec: docs/superpowers/specs/2026-09-09-standard-order-of-terms-design.md §6
"""
import pytest

from tests.iso.test_iso_compare_scryer import _engine_yesno, _YES, _NO

_ATOMS = ("a", "b", "f(X)", "g(X)", "h(X, Y)")

# (engine goal — quoted canonical form, scryer goal — native infix, expected)
ORDER_ROWS = [
    ("'@<'(1, a)",        "1 @< a",        "yes"),
    ("'@<'(a, 1)",        "a @< 1",        "no"),
    ("'@<'(a, b)",        "a @< b",        "yes"),
    ("'@<'(f(1), f(2))",  "f(1) @< f(2)",  "yes"),
    ("'@<'(g(1), f(1))",  "g(1) @< f(1)",  "no"),
    ("'@<'(1, 1)",        "1 @< 1",        "no"),
    ("'@>'(a, 1)",        "a @> 1",        "yes"),
    ("'@>'(1, a)",        "1 @> a",        "no"),
    ("'@=<'(1, 1)",       "1 @=< 1",       "yes"),
    ("'@=<'(2, 1)",       "2 @=< 1",       "no"),
    ("'@>='(1, 1)",       "1 @>= 1",       "yes"),
    ("'@>='(1, 2)",       "1 @>= 2",       "no"),
    ("'@<'(1.0, 1)",      "1.0 @< 1",      "yes"),   # ISO 7.2.1 tiebreak
]


@pytest.mark.parametrize("engine_goal,_scryer_goal,expected", ORDER_ROWS)
def test_order_operators_engine(engine_goal, _scryer_goal, expected, run_clausal):
    got = _engine_yesno(run_clausal, engine_goal, _ATOMS)
    assert got == [_YES if expected == "yes" else _NO]


@pytest.mark.parametrize("_engine_goal,scryer_goal,expected", ORDER_ROWS)
def test_order_operators_scryer(_engine_goal, scryer_goal, expected, scryer):
    assert scryer(f"({scryer_goal} -> write(yes) ; write(no)), nl, halt.") == expected


def test_no_two_order_operators_agree_on_every_row(run_clausal):
    """The predecessor branch shipped six comparison operators that were
    indistinguishable from one another for three review rounds. A hand-picked
    row set is exactly how that happened, so this is machine-checked: each
    operator must produce a DIFFERENT answer vector across the pairs."""
    ops = ["@<", "@>", "@=<", "@>="]
    pairs = [(1, 1), (1, 2), (2, 1)]
    sigs = {}
    for op in ops:
        sigs[op] = tuple(
            _engine_yesno(run_clausal, f"'{op}'({a}, {b})", _ATOMS)[0]
            for a, b in pairs)
    assert len(set(sigs.values())) == len(ops), sigs


COMPARE_ROWS = [("1", "2", "<"), ("2", "1", ">"), ("1", "1", "="),
                ("1.0", "1", "<"), ("a", "1", ">")]


def _engine_compare(run_clausal, a, b):
    atoms = ", ".join(("p(R)",) + _ATOMS)
    src = (f"-module(_hN, [{atoms}])\n-double_quotes(chars)\n"
           f"p(R) <- ('compare'(R, {a}, {b}))\n")
    return run_clausal(src, ("p",))


@pytest.mark.parametrize("a,b,expected", COMPARE_ROWS)
def test_compare_three_engine(a, b, expected, run_clausal):
    assert _engine_compare(run_clausal, a, b) == [repr((expected,))]


@pytest.mark.parametrize("a,b,expected", COMPARE_ROWS)
def test_compare_three_scryer(a, b, expected, scryer):
    assert scryer(f"compare(O, {a}, {b}), write(O), nl, halt.") == expected


def test_order_predicates_register_term_classes_of_the_right_arity():
    """The predecessor branch registered six comparison operators as /4 with
    two junk variables, because closure capture used DEFAULT ARGUMENTS and
    `_extract_fields_simple` takes params[:-2]. Nothing caught it."""
    from clausal.logic.builtins._registry import _BUILTIN_FIELDS
    for name, arity in (("@<", 2), ("@>", 2), ("@=<", 2), ("@>=", 2),
                        ("compare", 3)):
        assert len(_BUILTIN_FIELDS[(name, arity)]) == arity, name


# --- '=..' (univ) -----------------------------------------------------------
#
# The canonical spelling over the EXISTING `unpack/2`, so the two cannot drift
# apart. §6.4: the head of the univ list is an ATOM, not a bare spelling.

UNIV_DECON = [
    # (engine term, engine repr, scryer goal, scryer output)
    ("h(1, 2)", "[('h',), 1, 2]", "h(1, 2) =.. L", "[h,1,2]"),
    ("a",       "[('a',)]",       "a =.. L",       "[a]"),
]


@pytest.mark.parametrize("term,expected,_sg,_so", UNIV_DECON)
def test_univ_deconstructs_engine(term, expected, _sg, _so, run_clausal):
    atoms = ", ".join(("p(R)",) + _ATOMS)
    src = (f"-module(_hN, [{atoms}])\n-double_quotes(chars)\n"
           f"p(R) <- ('=..'({term}, R))\n")
    assert run_clausal(src, ("p",)) == [expected]


@pytest.mark.parametrize("_term,_expected,scryer_goal,scryer_out", UNIV_DECON)
def test_univ_deconstructs_scryer(_term, _expected, scryer_goal, scryer_out, scryer):
    assert scryer(f"{scryer_goal}, write(L), nl, halt.") == scryer_out


def test_univ_constructs_engine(run_clausal):
    """The other direction: build the term from the list."""
    atoms = ", ".join(("p(R)",) + _ATOMS)
    src = (f"-module(_hN, [{atoms}])\n-double_quotes(chars)\n"
           f"p(R) <- ('=..'(R, [h, 1, 2]))\n")
    assert run_clausal(src, ("p",)) == [repr(("h", 1, 2))]


def test_univ_constructs_scryer(scryer):
    assert scryer("T =.. [h, 1, 2], write(T), nl, halt.") == "h(1,2)"


def test_univ_matches_the_existing_unpack_spelling(run_clausal):
    """`'=..'` is an ALIAS, not a reimplementation: if the two ever disagree,
    one of them has grown logic of its own."""
    atoms = ", ".join(("p(R)",) + _ATOMS)
    a = run_clausal(f"-module(_hN, [{atoms}])\n-double_quotes(chars)\n"
                    f"p(R) <- ('=..'(h(1, 2), R))\n", ("p",))
    b = run_clausal(f"-module(_hN, [{atoms}])\n-double_quotes(chars)\n"
                    f"p(R) <- (unpack(h(1, 2), R))\n", ("p",))
    assert a == b and a != []
