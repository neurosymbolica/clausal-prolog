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
# `#=` NAMES AN EXISTING BEHAVIOUR — infix `==` compiles to nodes.ArithEq and
# `'#='` dispatches to the very same `fd_eq` — so its error surface is infix
# `==`'s error surface, and changing it would change infix `==`, which this
# branch may not do. It is therefore PINNED here, not fixed: three different
# behaviours across one family, none of them Scryer's.
# ---------------------------------------------------------------------------


def test_hash_family_error_surface_OPEN_iso_divergence(run_clausal):
    """Four rows with a non-numeric ground operand, measured 2026-09-09.
    Documents, does not bless.

        '#='(1, foo)    Clausal: FAILS SILENTLY
        '#\\='(1, foo)  Clausal: SUCCEEDS
        '#<'(1, foo)    Clausal: type_error(orderable, foo), context '(<)/2'
        '#='(X, foo)    Clausal: type_error(evaluable, foo), context '(==)/2'

    Scryer's clpz answers ONE thing for all four:
    `error(domain_error(clpz_expression,foo),unknown(foo)-1)` (see the oracle
    test below).

    Two warts are pinned deliberately rather than fixed. First, the family is
    not internally consistent: `'#='` fails where `'#\\='` succeeds where
    `'#<'` raises. Second, the last row's error INDICATOR names `(==)/2` for a
    goal written `'#='` — the context string comes from the shared ArithEq
    implementation, which knows only its Clausal spelling. Both follow from
    `#=` being a NAME for `==`'s existing behaviour; correcting either means
    changing infix `==`."""
    yes = repr("yes")
    no = repr("no")

    def yesno(goal, extra_atoms=("foo",)):
        atoms = ", ".join(("p(R)", "yes", "no") + tuple(extra_atoms))
        src = (f"-module(_hN, [{atoms}])\n-double_quotes(chars)\n"
               f"p(R) <- if_({goal}, R is yes, R is no)\n")
        return run_clausal(src, ("p",))

    assert yesno("'#='(1, foo)") == [no], "'#='(1, foo) fails silently"
    assert yesno("'#\\\\='(1, foo)") == [yes], "'#\\\\='(1, foo) succeeds"

    lt = _err_term(run_clausal, "'#<'(1, foo)", extra_atoms=("foo",))
    assert type(lt) is tuple and cell_functor(lt) == "error", lt
    assert spelling(cell_args(cell_args(lt)[0])[0]) == "orderable", lt
    assert spelling(cell_args(cell_args(lt)[0])[1]) == "foo", lt
    assert cell_args(lt)[1] == ("/", "<", 2), lt

    eq = _err_term(run_clausal, "'#='(X_UNUSED, foo)", extra_atoms=("foo",))
    assert type(eq) is tuple and cell_functor(eq) == "error", eq
    assert spelling(cell_args(cell_args(eq)[0])[0]) == "evaluable", eq
    assert spelling(cell_args(cell_args(eq)[0])[1]) == "foo", eq
    # The wart: a '#=' call reports its indicator as (==)/2.
    assert cell_args(eq)[1] == ("/", "==", 2), eq


def test_hash_family_error_surface_OPEN_iso_divergence_oracle(scryer):
    program = ":- use_module(library(clpz)).\n"
    expected = "error(domain_error(clpz_expression,foo),unknown(foo)-1)"
    for goal in ("1 #= foo", "1 #\\= foo", "1 #< foo", "X #= foo"):
        ref = scryer(
            f"catch(({goal} -> write(yes) ; write(no)), E, (write(E), nl)), halt.",
            program)
        assert ref == expected, f"{goal}: {ref!r}"
