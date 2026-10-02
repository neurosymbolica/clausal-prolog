"""Proof that the head-fold's legality checks are load-bearing.

Every other test in this suite runs the CORRECT rule, so between them they
establish that it behaves -- and nothing about whether the battery could tell
if a legality condition went missing.  ``_broken_head_fold_control.seam`` is
head_fold with the "occurs nowhere else in the body" goal deleted and nothing
else changed.  These two tests say what that deletion costs, on the same input.

A guard clause is the case that matters.  ``S is met`` after ``acc(K, S)`` is a
check: it asks whether what ``acc`` bound is ``met``.  Fold it and the head
does the binding, ``S`` is left unbound in the body, and the check is not
merely relocated -- it is gone.

The wider version of this control -- rewriting a whole working rule base with
the broken rule and watching its own tests fail -- belongs wherever such a tree
lives.  What this file proves is the narrower thing it depends on: the two
batteries do not behave the same.
"""

from clausal.rewrite.driver import rewrite_source

GUARD = "r(K, S) <- (acc(K, S), S is met)\n"


def test_the_real_rule_refuses_the_guard(head_fold_rules):
    result = rewrite_source(GUARD, head_fold_rules)
    assert result.fired == []
    assert "S is met" in result.text


def test_the_broken_rule_folds_the_guard(broken_head_fold_rules):
    result = rewrite_source(GUARD, broken_head_fold_rules)
    assert result.fired != []  # the illegal fold fires...
    assert "is met" not in result.text  # ...and the check is gone
    assert "r(K, met)" in result.text  # bound by the head, not checked


def test_the_broken_control_is_not_in_the_default_rule_set():
    from clausal.rewrite.cli import default_rule_names

    assert "_broken_head_fold_control" not in default_rule_names()
