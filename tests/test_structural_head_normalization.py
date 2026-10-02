"""Unit tests for structural head-arg normalization (clausal.logic.database)."""

import os

import pytest

from clausal.logic.database import (
    _is_structural_head_value,
    _normalize_structural_head_args,
)
from clausal.terms import Call, LoadName, Unify
from clausal.logic.variables import Var, is_var
from tests.predicate_api_support import term_ctor
from clausal.import_hook import _load_module
from clausal.logic.solve import call


class TestIsStructuralHeadValue:
    def test_compound_is_structural(self):
        assert _is_structural_head_value(("point", 1, 2)) is True

    def test_loadname_call_is_structural(self):
        assert _is_structural_head_value(
            Call(func=LoadName(name="point"), args=[1, 2], kwargs=[])
        ) is True

    def test_atomics_are_not_structural(self):
        for v in (1, 1.5, True, False, None, "s", b"b", 3 + 2j):
            assert _is_structural_head_value(v) is False

    def test_var_and_list_not_structural(self):
        assert _is_structural_head_value(Var()) is False
        assert _is_structural_head_value([1, 2]) is False

    def test_non_loadname_call_not_structural(self):
        # A Call whose func is not a LoadName is not a data term to construct.
        assert _is_structural_head_value(
            Call(func=Var(), args=[], kwargs=[])
        ) is False


def _hf(head, cls, name):
    """The value of field *name* in a normalised head CELL.

    P2: ``_normalize_structural_head_args`` returns a cell -- a functor and
    POSITIONS -- so a field is read at the position the class declares it."""
    from clausal.logic.cells import cell_args
    return cell_args(head)[cls._fields.index(name)]


class TestNormalizeStructuralHeadArgs:
    def test_structural_field_hoisted_to_prepended_unify(self):
        pt = term_ctor("pt", ("a", "b"))
        compound = Call(func=LoadName(name="point"), args=[1, 2], kwargs=[])
        head = pt(a=Var(), b=compound)
        new_head, new_body = _normalize_structural_head_args(head, [True])
        # field b replaced by a Var
        new_b = _hf(new_head, pt, "b")
        assert is_var(new_b)
        # one Unify prepended, binding that Var to the original compound
        assert isinstance(new_body[0], Unify)
        assert new_body[0].left is new_b
        assert new_body[0].right is compound
        assert new_body[1] is True  # original body preserved after prepend

    def test_atomic_fields_left_alone(self):
        pt = term_ctor("pt", ("a", "b"))
        head = pt(a=Var(), b=20000)
        new_head, new_body = _normalize_structural_head_args(head, [True])
        assert _hf(new_head, pt, "b") == 20000      # untouched
        assert new_body == [True]       # no goals added

    def test_no_structural_fields_is_noop(self):
        pt = term_ctor("pt", ("a",))
        head = pt(a=Var())
        h2, b2 = _normalize_structural_head_args(head, [True])
        assert h2 is head and b2 == [True]


def _undeclared_mod():
    path = os.path.join(
        os.path.dirname(__file__), "clausal_modules", "undeclared_compound_head.seam"
    )
    return _load_module("undeclared_compound_head_mod", path).__dict__["$module"]


def _err_text(pred, *args, module):
    with pytest.raises(Exception) as exc:
        list(call(pred, *args, module=module))
    return str(exc.value)


def test_undeclared_rule_and_fact_raise_same_error_in_output_mode():
    mod = _undeclared_mod()
    rule_err = _err_text("ur", 5, Var(), module=mod)
    fact_err = _err_text("uf", 50, Var(), module=mod)
    assert "is not in scope: nothing declares the functor" in rule_err
    assert "is not in scope: nothing declares the functor" in fact_err
