"""Tests that Python fallback implementations match C versions.

These ensure the codebase works correctly even if C extensions fail to build.
Each test calls the _py fallback directly and verifies it produces the same
result as the C-accelerated version.
"""

from __future__ import annotations

import pytest

from clausal.logic.variables import Var, Trail, deref, unify, is_var
from clausal.logic.predicate import PredicateMeta
from clausal.terms import Compound, KWTerm


# ── predicate.py fallbacks ───────────────────────────────────────────────────

from clausal.logic.predicate import (
    _is_term_instance_py,
    _is_atom_py,
    _term_field_names_py,
    is_term_instance,
    is_atom,
    term_field_names,
)


class Pt(metaclass=PredicateMeta):
    _fields = ("x", "y")


class Atom(metaclass=PredicateMeta):
    _fields = ()


class TestIsTermInstanceFallback:

    def test_predicate_instance(self):
        t = Pt(x=1, y=2)
        assert _is_term_instance_py(t) == is_term_instance(t) == True

    def test_class_not_instance(self):
        assert _is_term_instance_py(Pt) == is_term_instance(Pt) == False

    def test_int_not_instance(self):
        assert _is_term_instance_py(42) == is_term_instance(42) == False

    def test_compound_is_dataclass(self):
        c = Compound("f", (1,))
        assert _is_term_instance_py(c) == is_term_instance(c)

    def test_var_not_instance(self):
        assert _is_term_instance_py(Var()) == is_term_instance(Var()) == False


class TestIsAtomFallback:

    def test_zero_arity(self):
        assert _is_atom_py(Atom) == is_atom(Atom) == True

    def test_non_zero_arity(self):
        assert _is_atom_py(Pt) == is_atom(Pt) == False

    def test_not_predicate_meta(self):
        assert _is_atom_py(int) == is_atom(int) == False


class TestTermFieldNamesFallback:

    def test_predicate_instance(self):
        t = Pt(x=1, y=2)
        assert _term_field_names_py(t) == term_field_names(t) == ("x", "y")

    def test_compound_dataclass(self):
        c = Compound("f", (1, 2))
        py = _term_field_names_py(c)
        c_ver = term_field_names(c)
        assert py == c_ver

    def test_non_term_raises(self):
        with pytest.raises(TypeError):
            _term_field_names_py(42)


# ── _helpers.py fallbacks ────────────────────────────────────────────────────

from clausal.logic.builtins._helpers import (
    _functor_name_py, _arity_py, _nth_arg_py, _args_list_py,
    _is_compound_py, _is_ground_py,
    _functor_name, _arity, _nth_arg, _args_list,
    _is_compound, _is_ground,
)


class TestFunctorNameFallback:

    def test_compound(self):
        c = Compound("f", (1, 2))
        assert _functor_name_py(c) == _functor_name(c) == "f"

    def test_kwterm(self):
        t = KWTerm("rel", a=1)
        assert _functor_name_py(t) == _functor_name(t) == "rel"

    def test_predicate_instance(self):
        t = Pt(x=1, y=2)
        assert _functor_name_py(t) == _functor_name(t) == "Pt"

    def test_list_empty(self):
        assert _functor_name_py([]) == _functor_name([]) == "[]"

    def test_list_nonempty(self):
        assert _functor_name_py([1]) == _functor_name([1]) == "."

    def test_int(self):
        assert _functor_name_py(42) == _functor_name(42)

    def test_string(self):
        assert _functor_name_py("hello") == _functor_name("hello") == "hello"


class TestArityFallback:

    def test_compound(self):
        c = Compound("f", (1, 2, 3))
        assert _arity_py(c) == _arity(c) == 3

    def test_predicate_instance(self):
        t = Pt(x=1, y=2)
        assert _arity_py(t) == _arity(t) == 2

    def test_int(self):
        assert _arity_py(42) == _arity(42) == 0

    def test_atom(self):
        assert _arity_py(Atom) == _arity(Atom) == 0


class TestNthArgFallback:

    def test_compound_first(self):
        c = Compound("f", (10, 20))
        assert _nth_arg_py(c, 1) == _nth_arg(c, 1) == 10

    def test_compound_second(self):
        c = Compound("f", (10, 20))
        assert _nth_arg_py(c, 2) == _nth_arg(c, 2) == 20

    def test_out_of_range(self):
        c = Compound("f", (10,))
        with pytest.raises(IndexError):
            _nth_arg_py(c, 5)
        with pytest.raises(IndexError):
            _nth_arg(c, 5)


class TestArgsListFallback:

    def test_compound(self):
        c = Compound("f", (1, 2, 3))
        assert _args_list_py(c) == _args_list(c) == [1, 2, 3]

    def test_predicate_instance(self):
        t = Pt(x=10, y=20)
        assert _args_list_py(t) == _args_list(t) == [10, 20]

    def test_non_compound(self):
        assert _args_list_py(42) == _args_list(42) == []


class TestIsCompoundFallback:

    def test_compound(self):
        c = Compound("f", (1,))
        assert _is_compound_py(c) == _is_compound(c) == True

    def test_kwterm(self):
        t = KWTerm("r", a=1)
        assert _is_compound_py(t) == _is_compound(t) == True

    def test_int(self):
        assert _is_compound_py(42) == _is_compound(42) == False


class TestIsGroundFallback:

    def test_ground_int(self):
        assert _is_ground_py(42) == _is_ground(42) == True

    def test_ground_list(self):
        assert _is_ground_py([1, 2]) == _is_ground([1, 2]) == True

    def test_unbound_var(self):
        v = Var()
        assert _is_ground_py(v) == _is_ground(v) == False

    def test_list_with_var(self):
        v = Var()
        assert _is_ground_py([1, v]) == _is_ground([1, v]) == False

    def test_compound_with_var(self):
        v = Var()
        c = Compound("f", (1, v))
        assert _is_ground_py(c) == _is_ground(c) == False

    def test_compound_ground(self):
        c = Compound("f", (1, 2))
        assert _is_ground_py(c) == _is_ground(c) == True

    def test_kwterm_with_var(self):
        v = Var()
        t = KWTerm("r", a=v)
        assert _is_ground_py(t) == _is_ground(t) == False

    def test_kwterm_ground(self):
        t = KWTerm("r", a=1)
        assert _is_ground_py(t) == _is_ground(t) == True

    def test_predicate_instance_with_var(self):
        v = Var()
        t = Pt(x=v, y=1)
        assert _is_ground_py(t) == _is_ground(t) == False

    def test_predicate_instance_ground(self):
        t = Pt(x=1, y=2)
        assert _is_ground_py(t) == _is_ground(t) == True

    def test_bound_var_ground(self):
        v = Var()
        trail = Trail()
        unify(v, 42, trail)
        assert _is_ground_py(v) == _is_ground(v) == True

    def test_atom_ground(self):
        assert _is_ground_py(Atom) == _is_ground(Atom) == True


# ── inspection.py fallbacks ──────────────────────────────────────────────────

from clausal.logic.builtins.inspection import (
    _copy_term_py, _collect_vars_py,
    _copy_term_impl, _collect_vars_impl,
)


class TestCopyTermFallback:

    def test_ground_unchanged(self):
        assert _copy_term_py(42, {}) == _copy_term_impl(42, {}) == 42

    def test_list_copied(self):
        py = _copy_term_py([1, 2, 3], {})
        c = _copy_term_impl([1, 2, 3], {})
        assert py == c == [1, 2, 3]

    def test_var_freshened(self):
        x = Var()
        py_result = _copy_term_py(x, {})
        c_result = _copy_term_impl(x, {})
        assert is_var(py_result) and py_result is not x
        assert is_var(c_result) and c_result is not x

    def test_compound_copied(self):
        c = Compound("f", (1, Var()))
        py = _copy_term_py(c, {})
        assert isinstance(py, Compound)
        assert py.functor == "f"
        assert py.args[0] == 1
        assert is_var(py.args[1])

    def test_kwterm_functor_preserved(self):
        """KWTerm copy preserves functor (bug fix verification)."""
        t = KWTerm("rel", a=1, b=2)
        py = _copy_term_py(t, {})
        c = _copy_term_impl(t, {})
        assert py.functor == "rel"
        assert c.functor == "rel"

    def test_kwterm_var_freshened(self):
        x = Var()
        t = KWTerm("r", a=x)
        py = _copy_term_py(t, {})
        assert is_var(py._fields["a"])
        assert py._fields["a"] is not x

    def test_sharing_preserved(self):
        x = Var()
        py = _copy_term_py([x, x], {})
        assert py[0] is py[1]  # same fresh var
        assert py[0] is not x


class TestCollectVarsFallback:

    def test_ground_no_vars(self):
        py_result = []
        _collect_vars_py(42, py_result)
        c_result = []
        _collect_vars_impl(42, c_result)
        assert py_result == c_result == []

    def test_single_var(self):
        x = Var()
        py_result = []
        _collect_vars_py(x, py_result)
        c_result = []
        _collect_vars_impl(x, c_result)
        assert len(py_result) == len(c_result) == 1

    def test_dedup(self):
        x = Var()
        py_result = []
        _collect_vars_py([x, x, x], py_result)
        c_result = []
        _collect_vars_impl([x, x, x], c_result)
        assert len(py_result) == len(c_result) == 1

    def test_compound_vars(self):
        x, y = Var(), Var()
        c = Compound("f", (x, 1, y))
        py_result = []
        _collect_vars_py(c, py_result)
        c_result = []
        _collect_vars_impl(c, c_result)
        assert len(py_result) == len(c_result) == 2
