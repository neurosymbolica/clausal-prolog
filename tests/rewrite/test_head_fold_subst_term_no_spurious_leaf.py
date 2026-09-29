"""head_fold's subst_term/4 answers ONCE for a Variable or Goal cell.

todo/done/head-fold-structured-guard-never-excluded-a-vocabulary-cell-
2026-09-22.md: the leaf clause's guard tested ``isinstance(X, list)`` only,
so it also answered for a Variable/Goal CELL (there is no cut), leaving the
variable UNSUBSTITUTED as a second answer:
``subst_term(Variable(1), 1, T, R)`` gave ``R = T`` and then
``R = Variable(1)``.  Measured before the fix: 2 answers, and 3 for a Goal
holding the variable.
"""
import importlib

import pytest

from clausal.logic.solve import _deref_walk, solve
from clausal.logic.variables import Var


@pytest.mark.parametrize("rules", ["head_fold", "_broken_head_fold_control"])
def test_one_answer_per_vocabulary_cell(rules):
    m = importlib.import_module(f"clausal.rewrite.rules.{rules}")

    def answers(term):
        R = Var()
        return [_deref_walk(R) for _ in solve(("subst_term", term, 1, "t", R), m)]
    assert answers(("Variable", 1)) == ["t"]
    assert answers(("Variable", 2)) == [("Variable", 2)]
    assert len(answers(("Goal", "f", [("Variable", 1)], []))) == 1
    assert answers(5) == [5]
