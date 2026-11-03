"""unify_with_occurs_check through every term's ``__unify__`` hook.

A hook that binds its parts with plain ``unify`` built, inside an
occurs-checked unification, the cycle the check exists to refuse (ISO 8.2.2:
the unifier fails rather than bind a variable to a term containing it).  The
C unifier sets ``trail.unify_oc`` while a hook runs for an occurs-checked
unification, and each hook binds its parts with ``_hook_unifier(trail)``.

One case per hook.  Each binds X to a term holding X (``g(X)``) unless the
hook's part unification is occurs-checked; the control under plain ``unify``
shows the case does reach the hook and does bind (the rational tree).

The Seg* hooks are covered in tests/test_value_pattern_keeps_every_split.py.
``SetTerm`` compares ground elements with ``==``, and SegString/SegBytes bind
holes to ground text or bytes, so none of them binds a variable to a
variable-holding term.
"""

import pytest

from clausal.logic.variables import (
    Trail, Var, deref, unify, unify_with_occurs_check,
)
from clausal.pythonic_ast.nodes import Add, Negate, Predicate
from clausal.terms import DictTerm, Quantity, SegListView


def _dict_vs_dict():
    x = Var()
    return DictTerm({"k": x}), DictTerm({"k": ("g", x)}), x


def _dict_vs_plain_dict():
    x = Var()
    return DictTerm({"k": x}), {"k": ("g", x)}, x


def _plain_dict_vs_dict():
    # the hook on the RIGHT: the C unifier's second hook call
    x = Var()
    return {"k": ("g", x)}, DictTerm({"k": x}), x


def _dict_second_value():
    # the first pair binds, the second is cyclic: the first is undone too
    x, y = Var(), Var()
    return (DictTerm({"a": y, "k": x}),
            DictTerm({"a": 1, "k": ("g", x)}), x)


def _view_vs_view():
    x = Var()
    return (SegListView([0, x], 1, 2), SegListView([0, ("g", x)], 1, 2), x)


def _view_vs_list():
    x = Var()
    return SegListView([0, x], 1, 2), [("g", x)], x


def _quantity():
    x = Var()
    return Quantity(x, {"metre": 1}), Quantity(("g", x), {"metre": 1}), x


def _binop():
    x = Var()
    return Add(left=x, right=1), Add(left=("g", x), right=1), x


def _binop_right_operand():
    x = Var()
    return Add(left=1, right=x), Add(left=1, right=("g", x)), x


def _unaryop():
    x = Var()
    return Negate(operand=x), Negate(operand=("g", x)), x


def _predicate_head():
    x = Var()
    return (Predicate(head=x, body="true"),
            Predicate(head=("g", x), body="true"), x)


def _predicate_body():
    x = Var()
    return (Predicate(head="h", body=x),
            Predicate(head="h", body=("g", x)), x)


CASES = [
    _dict_vs_dict, _dict_vs_plain_dict, _plain_dict_vs_dict,
    _dict_second_value, _view_vs_view, _view_vs_list, _quantity, _binop,
    _binop_right_operand, _unaryop, _predicate_head, _predicate_body,
]
IDS = [f.__name__[1:] for f in CASES]


@pytest.mark.parametrize("make", CASES, ids=IDS)
def test_occurs_check_unify_through_the_hook_fails(make):
    t = Trail()
    left, right, x = make()
    assert unify_with_occurs_check(left, right, t) is False
    assert len(t) == 0
    assert deref(x) is x
    assert t.unify_oc is False


@pytest.mark.parametrize("make", CASES, ids=IDS)
def test_plain_unify_through_the_hook_builds_the_rational_tree(make):
    # The control: ``=``/2 has no occurs check, and the case reaches the hook.
    t = Trail()
    left, right, x = make()
    assert unify(left, right, t) is True
    bound = deref(x)
    assert isinstance(bound, tuple) and deref(bound[1]) is bound


def _acyclic_dict():
    x = Var()
    return DictTerm({"k": x}), DictTerm({"k": ("g", 1)}), x


def _acyclic_binop():
    x = Var()
    return Add(left=x, right=1), Add(left=("g", 1), right=1), x


def _acyclic_predicate():
    x = Var()
    return (Predicate(head=x, body="true"),
            Predicate(head=("g", 1), body="true"), x)


@pytest.mark.parametrize("make", [_acyclic_dict, _acyclic_binop,
                                  _acyclic_predicate],
                         ids=lambda f: f.__name__[1:])
def test_occurs_check_unify_through_the_hook_still_binds(make):
    t = Trail()
    left, right, x = make()
    assert unify_with_occurs_check(left, right, t) is True
    assert deref(x) == ("g", 1)
    assert t.unify_oc is False
