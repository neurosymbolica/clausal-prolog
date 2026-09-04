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
        # nv
        t = Pt(x=1, y=2)
        assert _is_term_instance_py(t) == is_term_instance(t) == True

    def test_class_not_instance(self):
        # nv
        assert _is_term_instance_py(Pt) == is_term_instance(Pt) == False

    def test_int_not_instance(self):
        # nv
        assert _is_term_instance_py(42) == is_term_instance(42) == False

    def test_compound_is_dataclass(self):
        # nv
        c = Compound("f", (1,))
        assert _is_term_instance_py(c) == is_term_instance(c)

    def test_var_not_instance(self):
        # nv
        assert _is_term_instance_py(Var()) == is_term_instance(Var()) == False


class TestIsAtomFallback:

    def test_zero_arity(self):
        # nv
        assert _is_atom_py(Atom) == is_atom(Atom) == True

    def test_non_zero_arity(self):
        # nv
        assert _is_atom_py(Pt) == is_atom(Pt) == False

    def test_not_predicate_meta(self):
        # nv
        assert _is_atom_py(int) == is_atom(int) == False


class TestTermFieldNamesFallback:

    def test_predicate_instance(self):
        # nv
        t = Pt(x=1, y=2)
        assert _term_field_names_py(t) == term_field_names(t) == ("x", "y")

    def test_compound_dataclass(self):
        # nv
        c = Compound("f", (1, 2))
        py = _term_field_names_py(c)
        c_ver = term_field_names(c)
        assert py == c_ver

    def test_non_term_raises(self):
        # nv
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
        # nv
        c = Compound("f", (1, 2))
        assert _functor_name_py(c) == _functor_name(c) == "f"

    def test_kwterm(self):
        # nv
        t = KWTerm("rel", a=1)
        assert _functor_name_py(t) == _functor_name(t) == "rel"

    def test_predicate_instance(self):
        # nv
        t = Pt(x=1, y=2)
        assert _functor_name_py(t) == _functor_name(t) == "Pt"

    def test_list_empty(self):
        # nv
        assert _functor_name_py([]) == _functor_name([]) == "[]"

    def test_list_nonempty(self):
        # nv
        assert _functor_name_py([1]) == _functor_name([1]) == "."

    def test_int(self):
        # nv
        assert _functor_name_py(42) == _functor_name(42)

    def test_string_nonempty_is_its_own_atom_functor(self):
        # nv — P3-1 §1b/R2: the C str~char-list cons rule is RETIRED. A
        # str is now always an atom (runtime str = atom), so a non-empty
        # str is its own functor name (arity 0), exactly like any other
        # atomic constant — NOT the ISO cons-cell "." reading this test
        # pinned pre-pivot (formerly ``test_string_nonempty_cons_cell``,
        # asserting ``_functor_name_py("hello") == "."``).
        assert _functor_name_py("hello") == _functor_name("hello") == "hello"

    def test_string_empty_nil(self):
        # nv
        # F089 (audit 2026-06-13): empty str → "[]" (the nil atom) —
        # unaffected by the P3-1 §1b cons-rule retirement (the empty
        # string is the one str value that legitimately reads as the
        # list-shaped nil atom, matching the empty-list case above).
        assert _functor_name_py("") == _functor_name("") == "[]"


class TestArityFallback:

    def test_compound(self):
        # nv
        c = Compound("f", (1, 2, 3))
        assert _arity_py(c) == _arity(c) == 3

    def test_predicate_instance(self):
        # nv
        t = Pt(x=1, y=2)
        assert _arity_py(t) == _arity(t) == 2

    def test_int(self):
        # nv
        assert _arity_py(42) == _arity(42) == 0

    def test_atom(self):
        # nv
        assert _arity_py(Atom) == _arity(Atom) == 0

    def test_string_nonempty_is_arity_zero(self):
        # nv — P3-1 §1b/R2: cons-rule retirement — a non-empty str is
        # atomic (arity 0), not a "."/2 cons cell (arity 2).
        assert _arity_py("hello") == _arity("hello") == 0

    def test_string_empty_is_arity_zero(self):
        # nv — unaffected by the retirement (empty str was already 0).
        assert _arity_py("") == _arity("") == 0


class TestNthArgFallback:

    def test_compound_first(self):
        # nv
        c = Compound("f", (10, 20))
        assert _nth_arg_py(c, 1) == _nth_arg(c, 1) == 10

    def test_compound_second(self):
        # nv
        c = Compound("f", (10, 20))
        assert _nth_arg_py(c, 2) == _nth_arg(c, 2) == 20

    def test_out_of_range(self):
        # nv
        c = Compound("f", (10,))
        with pytest.raises(IndexError):
            _nth_arg_py(c, 5)
        with pytest.raises(IndexError):
            _nth_arg(c, 5)

    def test_string_has_no_args(self):
        # nv — P3-1 §1b/R2: cons-rule retirement — a non-empty str is
        # atomic (arity 0), so even index 1 (formerly the cons-cell
        # head) now raises IndexError, matching any other atom.
        with pytest.raises(IndexError):
            _nth_arg_py("hello", 1)
        with pytest.raises(IndexError):
            _nth_arg("hello", 1)


class TestArgsListFallback:

    def test_compound(self):
        # nv
        c = Compound("f", (1, 2, 3))
        assert _args_list_py(c) == _args_list(c) == [1, 2, 3]

    def test_predicate_instance(self):
        # nv
        t = Pt(x=10, y=20)
        assert _args_list_py(t) == _args_list(t) == [10, 20]

    def test_non_compound(self):
        # nv
        assert _args_list_py(42) == _args_list(42) == []

    def test_string_nonempty_has_no_args(self):
        # nv — P3-1 §1b/R2: cons-rule retirement — a non-empty str is
        # atomic, so its args list is empty (formerly ``["h", "ello"]``
        # under the ISO cons-cell reading).
        assert _args_list_py("hello") == _args_list("hello") == []


class TestIsCompoundFallback:

    def test_compound(self):
        # nv
        c = Compound("f", (1,))
        assert _is_compound_py(c) == _is_compound(c) == True

    def test_kwterm(self):
        # nv
        t = KWTerm("r", a=1)
        assert _is_compound_py(t) == _is_compound(t) == True

    def test_int(self):
        # nv
        assert _is_compound_py(42) == _is_compound(42) == False


class TestIsGroundFallback:

    def test_ground_int(self):
        # nv
        assert _is_ground_py(42) == _is_ground(42) == True

    def test_ground_list(self):
        # nv
        assert _is_ground_py([1, 2]) == _is_ground([1, 2]) == True

    def test_unbound_var(self):
        # nv
        v = Var()
        assert _is_ground_py(v) == _is_ground(v) == False

    def test_list_with_var(self):
        # nv
        v = Var()
        assert _is_ground_py([1, v]) == _is_ground([1, v]) == False

    def test_compound_with_var(self):
        # nv
        v = Var()
        c = Compound("f", (1, v))
        assert _is_ground_py(c) == _is_ground(c) == False

    def test_compound_ground(self):
        # nv
        c = Compound("f", (1, 2))
        assert _is_ground_py(c) == _is_ground(c) == True

    def test_kwterm_with_var(self):
        # nv
        v = Var()
        t = KWTerm("r", a=v)
        assert _is_ground_py(t) == _is_ground(t) == False

    def test_kwterm_ground(self):
        # nv
        t = KWTerm("r", a=1)
        assert _is_ground_py(t) == _is_ground(t) == True

    def test_predicate_instance_with_var(self):
        # nv
        v = Var()
        t = Pt(x=v, y=1)
        assert _is_ground_py(t) == _is_ground(t) == False

    def test_predicate_instance_ground(self):
        # nv
        t = Pt(x=1, y=2)
        assert _is_ground_py(t) == _is_ground(t) == True

    def test_bound_var_ground(self):
        # nv
        v = Var()
        trail = Trail()
        unify(v, 42, trail)
        assert _is_ground_py(v) == _is_ground(v) == True

    def test_atom_ground(self):
        # nv
        assert _is_ground_py(Atom) == _is_ground(Atom) == True


# ── inspection.py fallbacks ──────────────────────────────────────────────────

from clausal.logic.builtins.inspection import (
    _copy_term_py, _collect_vars_py,
    _copy_term_impl, _collect_vars_impl,
)


class TestCopyTermFallback:

    def test_ground_unchanged(self):
        # nv
        assert _copy_term_py(42, {}) == _copy_term_impl(42, {}) == 42

    def test_list_copied(self):
        # nv
        py = _copy_term_py([1, 2, 3], {})
        c = _copy_term_impl([1, 2, 3], {})
        assert py == c == [1, 2, 3]

    def test_var_freshened(self):
        # nv
        x = Var()
        py_result = _copy_term_py(x, {})
        c_result = _copy_term_impl(x, {})
        assert is_var(py_result) and py_result is not x
        assert is_var(c_result) and c_result is not x

    def test_compound_copied(self):
        # nv
        c = Compound("f", (1, Var()))
        py = _copy_term_py(c, {})
        assert isinstance(py, Compound)
        assert py.functor == "f"
        assert py.args[0] == 1
        assert is_var(py.args[1])

    def test_kwterm_functor_preserved(self):
        """KWTerm copy preserves functor (bug fix verification)."""
        # nv
        t = KWTerm("rel", a=1, b=2)
        py = _copy_term_py(t, {})
        c = _copy_term_impl(t, {})
        assert py.functor == "rel"
        assert c.functor == "rel"

    def test_kwterm_var_freshened(self):
        # nv
        x = Var()
        t = KWTerm("r", a=x)
        py = _copy_term_py(t, {})
        assert is_var(py._fields["a"])
        assert py._fields["a"] is not x

    def test_sharing_preserved(self):
        # nv
        x = Var()
        py = _copy_term_py([x, x], {})
        assert py[0] is py[1]  # same fresh var
        assert py[0] is not x


class TestCollectVarsFallback:

    def test_ground_no_vars(self):
        # nv
        py_result = []
        _collect_vars_py(42, py_result)
        c_result = []
        _collect_vars_impl(42, c_result)
        assert py_result == c_result == []

    def test_single_var(self):
        # nv
        x = Var()
        py_result = []
        _collect_vars_py(x, py_result)
        c_result = []
        _collect_vars_impl(x, c_result)
        assert len(py_result) == len(c_result) == 1

    def test_dedup(self):
        # nv
        x = Var()
        py_result = []
        _collect_vars_py([x, x, x], py_result)
        c_result = []
        _collect_vars_impl([x, x, x], c_result)
        assert len(py_result) == len(c_result) == 1

    def test_compound_vars(self):
        # nv
        x, y = Var(), Var()
        c = Compound("f", (x, 1, y))
        py_result = []
        _collect_vars_py(c, py_result)
        c_result = []
        _collect_vars_impl(c, c_result)
        assert len(py_result) == len(c_result) == 2
