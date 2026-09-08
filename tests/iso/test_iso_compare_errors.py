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
from clausal.logic.exceptions import LogicException
from clausal.terms import Compound


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
