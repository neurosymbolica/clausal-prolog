import pytest


def test_harness_agrees_with_scryer_on_iso_is(scryer, run_clausal):
    """The oracle itself, proved against a predicate that ALREADY works, so a
    failure here means the harness is broken rather than the builtins."""
    assert scryer("X is 3 + 4, write(X), nl, halt.") == "7"
    got = run_clausal(
        "-module(_h1, [p(X)])\n-double_quotes(chars)\np(X) <- (X == 3 + 4)\n",
        ("p",))
    assert got == ["7"], "bare == already evaluates-and-binds; see the eq measurement"


ARITH_ROWS = [("'=:='(1, 1.0)", "1 =:= 1.0", True),
              ("'=:='(1, 2)",   "1 =:= 2",   False),
              ("'=\\\\='(1, 2)", "1 =\\= 2",  True),
              ("'<'(1, 2)",     "1 < 2",     True),
              ("'=<'(2, 2)",    "2 =< 2",    True),
              ("'>='(2, 3)",    "2 >= 3",    False)]


@pytest.mark.parametrize("clausal_goal, scryer_goal, expected", ARITH_ROWS)
def test_arithmetic_comparison_matches_scryer(scryer, run_clausal,
                                              clausal_goal, scryer_goal, expected):
    src = ("-module(_hN, [p(R), yes, no])\n-double_quotes(chars)\n"
           f"p(R) <- if_({clausal_goal}, R is yes, R is no)\n")
    got = run_clausal(src, ("p",))
    assert got == [repr(("yes",) if expected else ("no",))]
    ref = scryer(f"({scryer_goal} -> write(yes) ; write(no)), nl, halt.")
    assert ref == ("yes" if expected else "no"), "Scryer disagrees; Scryer is right"
