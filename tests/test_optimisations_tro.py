"""Slice E2: TRO as ``analyse → apply``.

Same three-property contract as E1's destructive-reuse pass —
round-trip (idempotence), no-op (ineligible clauses), correctness
(deferred to end-to-end `test_tail_recursion.py` until
lowering-reads-hints lands in a later E sub-slice).
"""

from __future__ import annotations

from clausal.logic.database import Clause
from tests.predicate_api_support import term_ctor
from clausal.logic.variables import Var
from clausal.terms import (
    Sub,
    Evaluate,
    Gt,
    Call, LoadName,
)


def _pred(name: str, fields: tuple[str, ...]):
    # Head builder only: the analysis reads the head CELL (W4b-3 slice 7;
    # it was a PredicateMeta class, which built the same cell).
    return term_ctor(name, fields)


def _clause_tro_eligible():
    Fact = _pred("Fact", ("n", "result"))
    n, n1, result = Var(), Var(), Var()
    head = Fact(n, result)
    body = [
        Gt(left=n, right=0),
        Evaluate(left=n1, right=Sub(left=n, right=1)),
        Call(func=LoadName(name="Fact"), args=[n1, result], kwargs=[]),
    ]
    return head, "Fact", 2, body


def _clause_tro_ineligible_different_functor():
    S = _pred("S", ("x",))
    x = Var()
    head = S(x)
    body = [Call(func=LoadName(name="Other"), args=[x], kwargs=[])]
    return head, "S", 1, body


def _clause_tro_ineligible_empty_body():
    P = _pred("P", ("x",))
    head = P(Var())
    body = []
    return head, "P", 1, body


def test_tro_pass_analyse_eligible_clause():
    from clausal.logic.compiler.optimisations import tro
    from clausal.logic.compiler.terms_to_goalop import terms_to_goalop
    head, functor, arity, body = _clause_tro_eligible()
    ir = terms_to_goalop(body, db=None)
    plan = tro.analyse(ir, head, functor, arity)
    assert isinstance(plan, tro.TROPlan)
    assert plan.eligible
    # check_indices can be empty when the tail args are all
    # passthrough/bound; for this clause n1 was Evaluate-bound,
    # result is passthrough — no runtime check needed.
    assert isinstance(plan.check_indices, frozenset)


def test_tro_pass_apply_sets_hint_on_tail_subcall():
    from clausal.logic.compiler.optimisations import tro
    from clausal.logic.compiler.terms_to_goalop import terms_to_goalop
    from clausal.logic.compiler.ir import SubCall
    head, functor, arity, body = _clause_tro_eligible()
    ir = terms_to_goalop(body, db=None)
    plan = tro.analyse(ir, head, functor, arity)
    new_ir = tro.apply(ir, plan)
    tail = new_ir.ops[-1]
    assert isinstance(tail, SubCall)
    assert tail.tail_recursive is True
    assert tail.fname == "Fact"


def test_tro_pass_apply_is_idempotent():
    from clausal.logic.compiler.optimisations import tro
    from clausal.logic.compiler.terms_to_goalop import terms_to_goalop
    head, functor, arity, body = _clause_tro_eligible()
    ir = terms_to_goalop(body, db=None)
    plan = tro.analyse(ir, head, functor, arity)
    once = tro.apply(ir, plan)
    twice_plan = tro.analyse(once, head, functor, arity)
    twice = tro.apply(once, twice_plan)
    assert once == twice


def test_tro_pass_apply_ineligible_is_ref_equal_noop():
    from clausal.logic.compiler.optimisations import tro
    from clausal.logic.compiler.terms_to_goalop import terms_to_goalop
    head, functor, arity, body = _clause_tro_ineligible_different_functor()
    ir = terms_to_goalop(body, db=None)
    plan = tro.analyse(ir, head, functor, arity)
    assert not plan.eligible
    new_ir = tro.apply(ir, plan)
    assert new_ir is ir


def test_tro_pass_apply_empty_body_is_noop():
    from clausal.logic.compiler.optimisations import tro
    from clausal.logic.compiler.terms_to_goalop import terms_to_goalop
    head, functor, arity, body = _clause_tro_ineligible_empty_body()
    ir = terms_to_goalop(body, db=None)
    plan = tro.analyse(ir, head, functor, arity)
    assert not plan.eligible
    new_ir = tro.apply(ir, plan)
    assert new_ir is ir


def test_tro_plan_is_hashable():
    from clausal.logic.compiler.optimisations import tro
    p1 = tro.TROPlan(eligible=True, check_indices=frozenset({0}))
    p2 = tro.TROPlan(eligible=True, check_indices=frozenset({0}))
    assert p1 == p2
    assert hash(p1) == hash(p2)
    assert {p1, p2} == {p1}
