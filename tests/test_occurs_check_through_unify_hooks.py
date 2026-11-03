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
from clausal.terms import ConcreteSeg, DictTerm, Quantity, SegList, SegListView


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


# The other direction: a variable bound to a term that holds it INSIDE a
# hooked term.  The occurs check reaches the hooked term's parts only through
# its ``__occurs_check__``; without one it saw an opaque leaf and let the
# binding through.

def _var_in_binop():
    y = Var()
    return y, ("f", Add(left=y, right=1))


def _var_in_binop_right():
    y = Var()
    return y, Add(left=1, right=("g", y))


def _var_in_unaryop():
    y = Var()
    return y, ("f", Negate(operand=y))


def _var_in_predicate_head():
    y = Var()
    return y, ("f", Predicate(head=y, body="true"))


def _var_in_predicate_body():
    y = Var()
    return y, Predicate(head="h", body=("g", y))


def _var_in_quantity():
    y = Var()
    return y, ("f", Quantity(y, {}))


def _var_in_dict():
    y = Var()
    return y, ("f", DictTerm({"k": y}))


CONTAINED = [_var_in_binop, _var_in_binop_right, _var_in_unaryop,
             _var_in_predicate_head, _var_in_predicate_body,
             _var_in_quantity, _var_in_dict]


@pytest.mark.parametrize("make", CONTAINED, ids=lambda f: f.__name__[1:])
def test_occurs_check_sees_a_var_inside_a_hooked_term(make):
    from clausal.logic.variables import occurs_check
    t = Trail()
    y, term = make()
    assert occurs_check(y, term) is True
    assert unify_with_occurs_check(y, term, t) is False
    assert len(t) == 0 and deref(y) is y


@pytest.mark.parametrize("make", CONTAINED, ids=lambda f: f.__name__[1:])
def test_occurs_check_of_another_var_in_a_hooked_term(make):
    from clausal.logic.variables import occurs_check
    _, term = make()
    z = Var()
    assert occurs_check(z, term) is False
    t = Trail()
    assert unify_with_occurs_check(z, term, t) is True
    assert deref(z) is term


# A hooked term on a cycle (built by plain ``=``/2).  Each hook restarted the
# occurs check from depth 0, below the C walker's cycle switch, so the check
# went round the cycle until RecursionError.  A hooked term already being
# searched for the same variable is not searched again.

def _cyclic_dict():
    x = Var()
    d = DictTerm({"k": x})
    assert unify(x, ("f", d), Trail())
    return d


def _cyclic_dict_direct():
    x = Var()
    d = DictTerm({"k": x})
    assert unify(x, d, Trail())
    return d


def _cyclic_seglist():
    a, b = Var(), Var()
    s = SegList([ConcreteSeg([a])])
    assert unify(b, ("f", s), Trail())
    assert unify(a, b, Trail())
    return s


def _cyclic_binop():
    x = Var()
    n = Add(left=x, right=1)
    assert unify(x, ("f", n), Trail())
    return n


def _cyclic_quantity():
    x = Var()
    q = Quantity(x, {})
    assert unify(x, ("f", q), Trail())
    return q


@pytest.mark.parametrize("make", [_cyclic_dict, _cyclic_dict_direct,
                                  _cyclic_seglist, _cyclic_binop,
                                  _cyclic_quantity],
                         ids=lambda f: f.__name__[1:])
def test_occurs_check_through_a_cyclic_hooked_term_terminates(make):
    from clausal.logic.variables import occurs_check
    term = make()
    z = Var()
    assert occurs_check(z, term) is False
    assert occurs_check(z, ("g", term, z)) is True
    t = Trail()
    assert unify_with_occurs_check(z, ("g", term), t) is True


def test_occurs_check_finds_a_var_beside_a_cycle():
    from clausal.logic.variables import occurs_check
    x, z = Var(), Var()
    d = DictTerm({"a": x, "b": z})
    assert unify(x, ("f", d), Trail())
    assert occurs_check(z, d) is True


def test_python_occurs_check_of_a_deep_term_without_the_var():
    # Past the C recursion's depth limit occurs_check answered its
    # "too deep" code, which read as True.
    from clausal.logic.variables import occurs_check
    deep = 1
    for _ in range(3000):
        deep = ("f", deep)
    z = Var()
    assert occurs_check(z, deep) is False
    assert occurs_check(z, ("f", deep, z)) is True
    assert occurs_check(z, DictTerm({"k": deep})) is False
