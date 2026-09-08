"""ISO error shapes for the arithmetic comparisons (spec Task 3).

`_iso_eval` (clausal/logic/builtins/iso_compare.py) is the shared evaluator
behind all six comparisons; these tests pin its two error shapes — an
unbound operand (instantiation_error) and a non-numeric operand
(type_error(evaluable, Name/Arity)) — against Scryer, which both Task 2's
implementer and this task measured directly. See the module docstring in
`_iso_eval` and the task report for the divergence this task reconciles:
`clpfd._eval_ground` raises its OWN LogicException — type_error(integer,
Leaf, "clpfd expression") — for a non-numeric leaf, and that shape (and its
bare culprit) previously leaked through `_iso_eval` unchanged instead of
becoming ISO's type_error(evaluable, foo/0).
"""
import pytest
from clausal.logic.exceptions import LogicException


def _err(run_clausal, goal, extra_atoms=()):
    # strict_atoms (2026-07-29) requires every bare atom to be declared in
    # the module's export list; the brief's literal Step 1 snippet omits
    # `foo`, which fails to COMPILE (NameError) rather than exercising
    # `_iso_eval` at all. Declare whatever the goal needs.
    atoms = ", ".join(("ok",) + tuple(extra_atoms))
    src = (f"-module(_hN, [p(R), {atoms}])\n-double_quotes(chars)\n"
           f"p(R) <- ({goal}, R is ok)\n")
    with pytest.raises(LogicException) as e:
        run_clausal(src, ("p",))
    return str(e.value)


def test_unbound_operand_is_instantiation_error(scryer, run_clausal):
    got = _err(run_clausal, "'=:='(X, 1)")
    assert got, "the error text must be non-empty, or this assertion can never fail"
    assert "instantiation_error" in got
    assert "instantiation_error" in scryer("catch(_ =:= 1, E, (write(E), nl)), halt.")


def test_non_evaluable_operand_is_type_error_evaluable(scryer, run_clausal):
    got = _err(run_clausal, "'=:='(1, foo)", extra_atoms=("foo",))
    assert got, "the error text must be non-empty, or this assertion can never fail"
    assert "evaluable" in got
    # The culprit is Name/Arity, not the bare atom — Scryer says foo/0, and
    # a leaf error that merely renames the expected type without fixing the
    # culprit shape would still fail this line.
    assert "foo" in got and "/" in got and "0" in got, got
    ref = scryer("catch(_ is foo + 1, E, (write(E), nl)), halt.")
    assert "type_error(evaluable,foo/0)" in ref


def test_non_evaluable_operand_is_never_the_clpfd_integer_shape(run_clausal):
    """`_eval_ground`'s OWN leaf error — type_error(integer, ...) tagged
    "clpfd expression" — must not leak through `_iso_eval` unreconciled;
    that was the exact divergence Task 3 closes."""
    got = _err(run_clausal, "'=:='(1, foo)", extra_atoms=("foo",))
    assert "clpfd expression" not in got
    assert "type_error(integer" not in got.replace(" ", "")
