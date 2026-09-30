"""ISO error shapes for the canonical comparison builtins.

`_iso_eval` (clausal/logic/builtins/iso_compare.py) is the shared evaluator
behind all six arithmetic comparisons; these tests pin its two error shapes —
an unbound operand (instantiation_error) and a non-numeric operand
(type_error(evaluable, Name/Arity)) — against Scryer, measured directly.
`clpfd._eval_ground` raises its OWN LogicException — type_error(integer, Leaf,
"clpfd expression") — for a non-numeric leaf, and that shape (and its bare
culprit) used to leak through `_iso_eval` unchanged instead of becoming ISO's
type_error(evaluable, foo/0).

Engine assertions and oracle assertions live in SEPARATE test functions here,
for the reason given at the top of tests/iso/test_iso_compare_scryer.py: an
oracle-less box must still run the engine half.
"""
import pytest

from clausal.logic.atoms import is_atom, spelling
from clausal import cell_args, cell_functor
from clausal.logic.exceptions import LogicException


def _src(goal, extra_atoms=()):
    # strict_atoms (2026-07-29) requires every bare atom to be declared in
    # the module's export list, so declare whatever the goal needs or the
    # module fails to COMPILE (NameError) without exercising `_iso_eval` at
    # all.
    atoms = ", ".join(("ok",) + tuple(extra_atoms))
    return (f"-module(_hN, [p(R), {atoms}])\n-double_quotes(chars)\n"
            f"p(R) <- ({goal}, R is ok)\n")


def _err(run_clausal, goal, extra_atoms=()):
    with pytest.raises(LogicException) as e:
        run_clausal(_src(goal, extra_atoms), ("p",))
    return str(e.value)


def _err_term(run_clausal, goal, extra_atoms=()):
    with pytest.raises(LogicException) as e:
        run_clausal(_src(goal, extra_atoms), ("p",))
    return e.value.term


def test_unbound_operand_is_instantiation_error(run_clausal):
    got = _err(run_clausal, "'=:='(X_UNUSED, 1)")
    assert got, "the error text must be non-empty, or this assertion can never fail"
    assert "instantiation_error" in got


def test_unbound_operand_is_instantiation_error_oracle(scryer):
    assert "instantiation_error" in scryer(
        "catch(_ =:= 1, E, (write(E), nl)), halt.")


def test_non_evaluable_operand_is_type_error_evaluable(run_clausal):
    got = _err(run_clausal, "'=:='(1, foo)", extra_atoms=("foo",))
    assert got, "the error text must be non-empty, or this assertion can never fail"
    assert "evaluable" in got
    # The culprit is Name/Arity, not the bare atom — Scryer says foo/0, and
    # a leaf error that merely renames the expected type without fixing the
    # culprit shape would still fail this line.
    assert "foo" in got and "/" in got and "0" in got, got


def test_non_evaluable_operand_is_type_error_evaluable_oracle(scryer):
    ref = scryer("catch(_ is foo + 1, E, (write(E), nl)), halt.")
    assert "type_error(evaluable,foo/0)" in ref


def test_non_evaluable_operand_is_never_the_clpfd_integer_shape(run_clausal):
    """`_eval_ground`'s OWN leaf error — type_error(integer, ...) tagged
    "clpfd expression" — must not leak through `_iso_eval` unreconciled."""
    got = _err(run_clausal, "'=:='(1, foo)", extra_atoms=("foo",))
    assert "clpfd expression" not in got
    assert "type_error(integer" not in got.replace(" ", "")


def _evaluable_culprit_of(term):
    """The culprit out of `error(type_error(evaluable, Culprit), Context)`."""
    assert type(term) is tuple and cell_functor(term) == "error", term
    inner = cell_args(term)[0]
    assert type(inner) is tuple and cell_functor(inner) == "type_error", inner
    assert spelling(cell_args(inner)[0]) == "evaluable", inner
    return cell_args(inner)[1]


def test_compound_evaluable_culprit_is_a_name_arity_indicator_OPEN_iso_divergence(
        run_clausal):
    """ISO's `type_error(evaluable, …)` culprit is a Name/Arity INDICATOR.

    A COMPOUND operand used to leak the raw term instead. Measured
    2026-09-09 before the fix:

        '=:='(1, foo(bar))
            Clausal: error(type_error(evaluable, foo(bar)), 'is/2')
            Scryer:  error(type_error(evaluable, bar/0), (is)/2)

    `_evaluable_culprit`'s `isinstance(leaf, Compound)` branch was DEAD: an
    engine compound reaching it from `.clausal` source is a cell tuple
    (`('foo', ('bar',))`), not a `clausal.terms.Compound`, so the term fell
    through the branch untouched.

    This test pins the INDICATOR SHAPE, which is now correct, and RECORDS
    that the indicator's IDENTITY still diverges: Scryer evaluates arguments
    first and names the innermost non-evaluable leaf (`bar/0`), while
    `clpfd._eval_ground` reports the whole offending subterm, so Clausal
    names `foo/1`. Reproducing Scryer's descent would mean re-deriving its
    evaluation order from measurements, i.e. guessing, so it is NOT
    attempted — the divergence is documented here, not blessed. The Scryer
    rows are in the oracle test below."""
    culprit = _evaluable_culprit_of(
        _err_term(run_clausal, "'=:='(1, foo(bar))",
                  extra_atoms=("foo(a)", "bar")))
    assert type(culprit) is tuple and cell_functor(culprit) == "/", culprit
    name, arity = cell_args(culprit)
    assert is_atom(name) and spelling(name) == "foo", culprit
    assert arity == 1, culprit


def test_compound_evaluable_culprit_OPEN_iso_divergence_oracle(scryer):
    """Scryer's rule, measured: evaluate the arguments first, so the culprit
    is the innermost non-evaluable leaf. Four rows, because one row does not
    show a rule."""
    def culprit(goal):
        return scryer(f"catch({goal}, E, (write(E), nl)), halt.")

    assert culprit("1 =:= foo(bar)") == "error(type_error(evaluable,bar/0),(is)/2)"
    assert culprit("1 =:= f(g(h))") == "error(type_error(evaluable,h/0),(is)/2)"
    assert culprit("1 =:= foo(1)") == "error(type_error(evaluable,foo/1),(is)/2)"
    assert culprit("1 =:= foo") == "error(type_error(evaluable,foo/0),(is)/2)"


# ---------------------------------------------------------------------------
# The '#…' family's error surface.
#
# `'#='` and the rest are their OWN builtins (iso_compare.py), not infix
# `==`, so they can take clpz's error surface without touching `==`.  Ruled
# 2026-09-30: they refuse a non-arithmetic operand with Scryer's clpz formal.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("goal", [
    "'#='(1, foo)", "'#\\\\='(1, foo)", "'#<'(1, foo)", "'#>'(foo, 1)",
    "'#=<'(1, foo)", "'#>='(1, foo)", "'#='(X_UNUSED, foo)",
    "'#='(X_UNUSED, foo + 1)", "'#='(foo, foo)",
])
def test_hash_family_refuses_a_non_numeric_operand(run_clausal, goal):
    """Scryer answers `error(domain_error(clpz_expression,foo),_)` for every
    row (see the oracle test below).  Measured 2026-09-09 the family had
    three behaviours: `'#='(1, foo)` FAILED silently, `'#\\='(1, foo)` (and
    `'#='(foo, foo)`) SUCCEEDED, `'#<'(1, foo)` raised type_error(orderable,
    foo), and only a variable beside `foo` gave the clpz formal, naming
    `(==)/2` as its indicator.  The indicator is now the goal's own."""
    eq = _err_term(run_clausal, goal, extra_atoms=("foo",))
    assert type(eq) is tuple and cell_functor(eq) == "error", eq
    formal = cell_args(eq)[0]
    assert cell_functor(formal) == "domain_error", eq
    assert spelling(cell_args(formal)[0]) == "clpz_expression", eq
    assert spelling(cell_args(formal)[1]) == "foo", eq
    op = goal.split("'")[1].replace("\\\\", "\\")
    assert cell_args(eq)[1] == ("/", op, 2), eq


@pytest.mark.parametrize("goal", ["'#='(X_UNUSED, True)", "'#='(1, True)",
                                  "'#<'(0, False + 1)"])
def test_hash_family_refuses_a_boolean_operand(run_clausal, goal):
    """Ruled 2026-09-30: a boolean in arithmetic is an error.  Scryer's clpz
    refuses the atom `true` with domain_error(clpz_expression, true); a
    Python bool gets the same formal (culprit the bool).  `'#='(X, True)`
    used to bind X to 1."""
    eq = _err_term(run_clausal, goal)
    formal = cell_args(eq)[0]
    assert cell_functor(formal) == "domain_error", eq
    assert spelling(cell_args(formal)[0]) == "clpz_expression", eq
    assert type(cell_args(formal)[1]) is bool, eq


def test_hash_family_refuses_a_non_numeric_operand_oracle(scryer):
    program = ":- use_module(library(clpz)).\n"
    expected = "error(domain_error(clpz_expression,foo),unknown(foo)-1)"
    for goal in ("1 #= foo", "1 #\\= foo", "1 #< foo", "foo #> 1", "1 #=< foo",
                 "1 #>= foo", "X #= foo", "X #= foo + 1", "foo #= foo"):
        ref = scryer(
            f"catch(({goal} -> write(yes) ; write(no)), E, (write(E), nl)), halt.",
            program)
        assert ref == expected, f"{goal}: {ref!r}"
    ref = scryer("catch((X #= true -> write(yes) ; write(no)), E, "
                 "(write(E), nl)), halt.", program)
    assert ref == ("error(domain_error(clpz_expression,true),"
                   "unknown(true)-1)"), ref
