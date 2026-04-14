"""Slice D6b parallel-implementation harness for destructive-reuse analysis.

For each clause shape exercised by ``tests/test_destructive_reuse.py``'s
``TestFindDestructiveReuseGoals``, run both:

- legacy :func:`_find_destructive_reuse_goals` (operates on raw flattened
  body terms, the source of truth today), and
- IR-side :func:`destructive_reuse.analyse_ir` (operates on the
  :class:`Sequence` produced by :func:`terms_to_goalop`).

…and assert the two agree on the canonical eligible-call set.  Index
sets aren't directly comparable (legacy indexes the post-flatten body,
IR indexes ``Sequence.ops``) so both sides project to the
``(fname, arity, occurrence#)`` form before comparison.

This is the D6 option-1 verification gate.  The wider cross-check in
``_find_destructive_reuse_goals`` (gated by ``CLAUSAL_IR_PATH=1``) runs
the same agreement check on every real predicate compilation across
the suite.
"""

from __future__ import annotations

import pytest

from clausal.logic.database import Clause
from clausal.logic.variables import Var
from clausal.terms import (
    Compound,
    Unify, Evaluate,
    Call, LoadName,
    DictTerm, SetTerm,
)


def _append_call(l1, l2, l3):
    return Call(func=LoadName(name="append"), args=[l1, l2, l3], kwargs=[])


def _dict_put_call(key, value, old, new):
    return Call(func=LoadName(name="dict_put"),
                args=[key, value, old, new], kwargs=[])


def _set_union_call(s1, s2, union):
    return Call(func=LoadName(name="set_union"),
                args=[s1, s2, union], kwargs=[])


def _case_eligible_with_evaluate():
    Temp, Extra, Out = Var(), Var(), Var()
    return ("eligible_with_evaluate", Clause(
        head=Compound("process", (Out,)),
        body=[
            Evaluate(left=Temp, right=[1, 2, 3]),
            _append_call(Temp, Extra, Out),
        ],
    ))


def _case_alias_through_unify():
    In, Temp, Extra, Out = Var(), Var(), Var(), Var()
    return ("alias_through_unify", Clause(
        head=Compound("process", (In, Out)),
        body=[
            Unify(left=Temp, right=In),
            _append_call(Temp, Extra, Out),
        ],
    ))


def _case_transitive_alias():
    In, Temp, Temp2, Extra, Out = Var(), Var(), Var(), Var(), Var()
    return ("transitive_alias", Clause(
        head=Compound("process", (In, Out)),
        body=[
            Unify(left=Temp, right=In),
            Unify(left=Temp2, right=Temp),
            _append_call(Temp2, Extra, Out),
        ],
    ))


def _case_head_var_source():
    Old, Extra, Out = Var(), Var(), Var()
    return ("head_var_source", Clause(
        head=Compound("process", (Old, Out)),
        body=[_append_call(Old, Extra, Out)],
    ))


def _case_live_var():
    Temp, Extra, Mid, Out = Var(), Var(), Var(), Var()
    return ("live_var", Clause(
        head=Compound("process", (Out,)),
        body=[
            _append_call(Temp, Extra, Mid),
            _append_call(Temp, Mid, Out),
        ],
    ))


def _case_deterministic_builtin_prefix():
    T, Len, Out = Var(), Var(), Var()
    return ("det_builtin_prefix", Clause(
        head=Compound("process", (Out,)),
        body=[
            Evaluate(left=T, right=[1, 2, 3]),
            Call(func=LoadName(name="length"), args=[T, Len], kwargs=[]),
            _append_call(T, [4], Out),
        ],
    ))


def _case_dict_put_eligible():
    Temp, Key, Value, Out = Var(), Var(), Var(), Var()
    return ("dict_put_eligible", Clause(
        head=Compound("update", (Out,)),
        body=[
            Evaluate(left=Temp, right=DictTerm({"a": 1})),
            _dict_put_call(Key, Value, Temp, Out),
        ],
    ))


def _case_set_union_eligible():
    Temp, S2, Out = Var(), Var(), Var()
    return ("set_union_eligible", Clause(
        head=Compound("merge", (Out,)),
        body=[
            Evaluate(left=Temp, right=SetTerm([1, 2])),
            _set_union_call(Temp, S2, Out),
        ],
    ))


def _case_source_literal():
    Extra, Out = Var(), Var()
    return ("source_literal", Clause(
        head=Compound("process", (Out,)),
        body=[_append_call([1, 2, 3], Extra, Out)],
    ))


def _case_empty_body():
    return ("empty_body", Clause(head=Compound("fact", (1,)), body=[]))


def _case_unify_body_only_vars():
    T1, T2, Out = Var(), Var(), Var()
    return ("unify_body_only_vars", Clause(
        head=Compound("process", (Out,)),
        body=[
            Evaluate(left=T1, right=[1, 2]),
            Unify(left=T2, right=T1),
            _append_call(T2, [3], Out),
        ],
    ))


_CASES = [
    _case_eligible_with_evaluate(),
    _case_alias_through_unify(),
    _case_transitive_alias(),
    _case_head_var_source(),
    _case_live_var(),
    _case_deterministic_builtin_prefix(),
    _case_dict_put_eligible(),
    _case_set_union_eligible(),
    _case_source_literal(),
    _case_empty_body(),
    _case_unify_body_only_vars(),
]


@pytest.mark.parametrize(
    "name,clause",
    _CASES,
    ids=[c[0] for c in _CASES],
)
def test_dr_analyse_ir_agrees_with_legacy(name, clause):
    # Function-local imports survive the sys.modules scrub performed
    # by ``test_runtime_compiler_boundary`` earlier in the session
    # (see Slice D6a commit message for the full hazard write-up).
    from clausal.logic.compiler import _find_destructive_reuse_goals
    from clausal.logic.compiler.destructive_reuse import (
        analyse_ir, _canonicalise_legacy, _canonicalise_ir,
    )
    from clausal.logic.compiler.terms_to_goalop import terms_to_goalop

    legacy_eligible = _find_destructive_reuse_goals(clause)
    legacy_canon = _canonicalise_legacy(clause.body, legacy_eligible)

    ir = terms_to_goalop(clause.body, db=None)
    ir_eligible = analyse_ir(ir, clause.head)
    ir_canon = _canonicalise_ir(ir, ir_eligible)

    assert ir_canon == legacy_canon, (
        f"{name}: eligible-call disagreement — "
        f"legacy={sorted(legacy_canon)}, ir={sorted(ir_canon)}"
    )
