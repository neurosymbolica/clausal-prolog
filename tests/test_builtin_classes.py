"""Tests for builtin predicate classes (Phase 1).

Every built-in predicate should have a constructable PredicateMeta class
so that users can build canonical term trees in Python:

    append(X_, [1, 2], Z_)   instead of   Call(func=LoadName('append'), ...)
"""

from __future__ import annotations

import pytest

from clausal.logic.builtins import (
    _BUILTIN_CLASSES,
    _BUILTIN_FIELDS,
    MultiArityBuiltin,
    get_builtin_class,
)
from clausal.logic.cells import is_cell, cell_functor, cell_args, cell_arity
from clausal.logic.predicate import is_term_instance
from clausal.logic.variables import Var, deref


def _field(term, name):
    """The value of the field *name* in a builtin CELL.

    P2: constructing a builtin class yields a cell -- a functor and
    POSITIONS -- so a field name is no longer carried by the term and is
    resolved through the registry that declares it.  The tests keep naming
    fields because the names are the thing worth pinning; what changed is
    where the name lives."""
    fields = _BUILTIN_FIELDS[(cell_functor(term), cell_arity(term))]
    return cell_args(term)[fields.index(name)]


# ── Registry completeness ─────────────────────────────────────────────────────


class TestRegistry:
    """Every registered builtin should have a class entry."""

    def test_all_builtins_have_fields(self):
        # nv
        from clausal.logic.builtins import _BUILTINS, _DB_BUILTINS
        all_keys = set(_BUILTINS) | set(_DB_BUILTINS)
        for key in all_keys:
            assert key in _BUILTIN_FIELDS, f"Missing fields for {key}"

    def test_all_builtins_have_classes(self):
        # nv
        functors_with_fields = {f for f, _ in _BUILTIN_FIELDS}
        for f in functors_with_fields:
            assert f in _BUILTIN_CLASSES, f"Missing class for {f}"

    def test_class_count(self):
        # nv
        assert len(_BUILTIN_CLASSES) >= 70  # we have ~75 unique functor names

    def test_get_builtin_class_found(self):
        # nv
        cls = get_builtin_class("append")
        assert cls is not None

    def test_get_builtin_class_not_found(self):
        # nv
        assert get_builtin_class("NonExistentPredicate") is None


# ── Single-arity term construction ────────────────────────────────────────────


class TestSingleArityConstruction:
    """Single-arity builtins build cells (W4b-3 slice 3), at the written
    arity (no padding)."""

    def test_append_positional(self):
        # nv
        append = get_builtin_class("append")
        t = append([1, 2], [3], [1, 2, 3])
        assert is_cell(t)
        assert cell_functor(t) == "append"
        assert _field(t, "l1") == [1, 2]
        assert _field(t, "l2") == [3]
        assert _field(t, "l3") == [1, 2, 3]

    def test_append_keyword(self):
        """Keywords naming EVERY field of the registered arity place them."""
        # nv
        append = get_builtin_class("append")
        t = append(l3=[1, 2], l1=[1], l2=[2])
        assert t == ("append", [1], [2], [1, 2])

    def test_keywords_at_an_unregistered_count_are_refused(self):
        """No padding (operator ruling 2026-09-25): keywords name the slots
        of a registered arity, so ``append(l1=..., l2=...)`` -- 2 arguments,
        append is append/3 -- is refused, where it used to pad ``l3`` with a
        fresh Var."""
        # nv
        from clausal.logic.predicate import ClausalTermConstructionError
        append = get_builtin_class("append")
        with pytest.raises(ClausalTermConstructionError,
                           match="registered only at append/3"):
            append(l1=[1], l2=[2])
        with pytest.raises(ClausalTermConstructionError,
                           match="registered only at between/3"):
            get_builtin_class("between")(low=1, high=10)

    def test_positional_at_an_unregistered_count_builds_the_written_arity(self):
        """``between(1, 2)`` is between/2 -- the cell as WRITTEN, never
        padded to between/3 (it used to raise too-few); as a goal it is an
        existence_error.  Too many is written too."""
        # nv
        between = get_builtin_class("between")
        assert between(1, 2) == ("between", 1, 2)
        assert between(1, 2, 3, 4) == ("between", 1, 2, 3, 4)
        assert get_builtin_class("maplist")("f") == ("maplist", "f")

    def test_a_goal_at_an_unregistered_arity_is_an_existence_error(self):
        # nv
        import clausal
        from clausal.logic.exceptions import LogicException
        from clausal.predicate_diagnostics import PredicateNotFoundError
        with pytest.raises((PredicateNotFoundError, LogicException)) as e:
            list(clausal.solve(get_builtin_class("between")(1, 2),
                               module=clausal.Module("_w4b3_nopad")))
        assert "between/2" in str(e.value)

    def test_length_positional(self):
        # nv
        length = get_builtin_class("length")
        t = length([1, 2, 3], 3)
        assert _field(t, "lst") == [1, 2, 3]
        assert _field(t, "n") == 3

    def test_zero_arity(self):
        """A 0-arity builtin builds its 0-arity cell, the ATOM (W4b-3 slice
        3; the class era handed back the class itself, which is no term)."""
        # nv
        nl = get_builtin_class("nl")
        assert not isinstance(nl, type)
        assert nl.arities == (0,)
        assert nl() == "nl"

    def test_no_args_is_the_atom(self):
        """No arguments is the WRITTEN arity 0: the atom, never an all-Var
        cell of a registered arity (operator ruling 2026-09-25)."""
        # nv
        assert get_builtin_class("in_")() == "in_"
        assert get_builtin_class("between")() == "between"


# ── Field names ───────────────────────────────────────────────────────────────


class TestFieldNames:
    """Verify field names are meaningful (extracted from implementation params)."""

    def test_append_fields(self):
        # nv
        assert _BUILTIN_FIELDS[("append", 3)] == ("l1", "l2", "l3")

    def test_between_fields(self):
        # nv
        assert _BUILTIN_FIELDS[("between", 3)] == ("low", "high", "x")

    def test_length_fields(self):
        # nv
        assert _BUILTIN_FIELDS[("length", 2)] == ("lst", "n")

    def test_functor_fields(self):
        # nv
        assert _BUILTIN_FIELDS[("functor", 3)] == ("term", "name", "arity")

    def test_in_fields(self):
        # nv
        assert _BUILTIN_FIELDS[("in_", 2)] == ("elem", "lst")

    def test_db_builtin_fields(self):
        # nv
        assert _BUILTIN_FIELDS[("assertz", 1)] == ("term",)
        assert _BUILTIN_FIELDS[("retract", 1)] == ("term",)
        assert _BUILTIN_FIELDS[("abolish_table", 2)] == ("functor", "arity")

    def test_term_field_names_on_instance(self):
        """P2: the REGISTRY names a cell's fields -- the term does not."""
        # nv
        append = get_builtin_class("append")
        t = append([1], [2], [1, 2])
        assert _BUILTIN_FIELDS[(cell_functor(t), cell_arity(t))] == ("l1", "l2", "l3")


# ── The builtin object: not a class (W4b-3 slice 3) ──────────────────────────


class TestBuiltinObjectProtocol:
    """A builtin's object is a ``BuiltinTerm``: a term constructor that
    speaks the duck-typed ``_get_dispatch()`` protocol.  It was a
    ``PredicateMeta`` class, whose private row held the dispatch and a
    lock; it is no class and carries no predicate state now."""

    def test_is_not_a_predicate_class(self):
        # nv
        from clausal.logic.builtins import BuiltinTerm
        append = get_builtin_class("append")
        assert isinstance(append, BuiltinTerm)
        assert not isinstance(append, type)

    def test_functor_property(self):
        # nv
        append = get_builtin_class("append")
        assert append._functor == "append"

    def test_arities(self):
        # nv
        assert get_builtin_class("append").arities == (3,)
        assert get_builtin_class("maplist").arities[:2] == (2, 3)

    def test_carries_no_predicate_state(self):
        """No row, no clause store: nothing to lock or assert into."""
        # nv
        append = get_builtin_class("append")
        for attr in ("_row", "_state_row", "_assertz", "_lock"):
            assert not hasattr(append, attr), attr

    def test_get_dispatch(self):
        # nv
        from clausal.logic.builtins._registry import _stateless_dispatch
        append = get_builtin_class("append")
        fn = append._get_dispatch()
        assert callable(fn)
        assert fn is append._dispatch_by_arity[3]
        assert _stateless_dispatch("append", 3) is not None

    def test_db_builtin_no_dispatch(self):
        """DB-dependent builtins have no db-free dispatch; asking for it is
        the class era's NotImplementedError."""
        # nv
        assertz = get_builtin_class("assertz")
        assert 1 not in assertz._dispatch_by_arity
        with pytest.raises(NotImplementedError, match="assertz/1"):
            assertz._get_dispatch()


# ── __eq__ / __repr__ / __match_args__ ────────────────────────────────────────


class TestInstanceProtocols:
    def test_eq(self):
        # nv
        in_ = get_builtin_class("in_")
        assert in_(elem=1, lst=[1, 2]) == in_(elem=1, lst=[1, 2])

    def test_neq(self):
        # nv
        in_ = get_builtin_class("in_")
        assert in_(elem=1, lst=[1]) != in_(elem=2, lst=[1])

    def test_repr(self):
        # nv
        between = get_builtin_class("between")
        t = between(low=1, high=10, x=99)
        r = repr(t)
        # P2: a cell's repr is the TUPLE's -- functor first, then positions.
        # The field names moved to the registry, so they are not in the repr.
        assert "between" in r
        assert r == repr(("between", 1, 10, 99))

    def test_match_args(self):
        # nv
        append = get_builtin_class("append")
        t = append([1], [2], [1, 2])
        # P2: a cell matches as the SEQUENCE it is -- functor then arguments.
        # A class pattern needed an instance to destructure; this needs none.
        match t:
            case ("append", a, b, c):
                assert a == [1]
                assert b == [2]
                assert c == [1, 2]
            case _:
                pytest.fail("match failed")


# ── Multi-arity builtins ─────────────────────────────────────────────────────


class TestMultiArity:
    def test_maplist_is_multi(self):
        # nv
        ml = get_builtin_class("maplist")
        assert isinstance(ml, MultiArityBuiltin)

    def test_maplist_2_construction(self):
        # nv
        ml = get_builtin_class("maplist")
        t = ml("goal", [1, 2])
        assert is_cell(t)
        assert cell_arity(t) == 2

    def test_maplist_3_construction(self):
        # nv
        ml = get_builtin_class("maplist")
        t = ml("goal", [1, 2], [2, 4])
        assert is_cell(t)
        assert cell_arity(t) == 3

    def test_maplist_dispatch(self):
        # nv
        ml = get_builtin_class("maplist")
        fn = ml._get_dispatch()
        assert callable(fn)

    def test_phrase_is_multi(self):
        # nv
        p = get_builtin_class("phrase")
        assert isinstance(p, MultiArityBuiltin)

    def test_phrase_2_construction(self):
        # nv
        p = get_builtin_class("phrase")
        t = p("rule", [1, 2])
        assert cell_arity(t) == 2

    def test_phrase_3_construction(self):
        # nv
        p = get_builtin_class("phrase")
        t = p("rule", [1, 2], [])
        assert cell_arity(t) == 3

    def test_multi_repr(self):
        # nv
        ml = get_builtin_class("maplist")
        assert "maplist" in repr(ml)
        assert "[2, 3, 4, 5, 6, 7, 8]" in repr(ml)   # maplist/2..8


# ── is_term_instance / term_field_names ───────────────────────────────────────


class TestTermHelpers:
    def test_is_term_instance_true(self):
        # nv
        append = get_builtin_class("append")
        t = append([1], [2], [1, 2])
        assert is_cell(t)

    def test_is_term_instance_false_on_class(self):
        # nv
        append = get_builtin_class("append")
        assert not is_term_instance(append)

    def test_term_field_names(self):
        # nv
        in_ = get_builtin_class("in_")
        t = in_(1, [1, 2])
        assert _BUILTIN_FIELDS[(cell_functor(t), cell_arity(t))] == ("elem", "lst")


# ── Execution: dispatch from class ───────────────────────────────────────────


class TestExecution:
    """Drive builtin dispatch functions obtained from the predicate classes."""

    def _collect(self, cls_or_wrapper, *args, capture_vars=None):
        """Drive a builtin class's dispatch; return list of captured binding snapshots.

        capture_vars: list of Var objects whose deref'd values to snapshot per solution.
        Returns list of tuples (one per solution), each containing deref'd values.
        """
        from clausal.logic.trampoline import StepGenerator, DONE as _DONE
        from clausal.logic.variables import Trail

        dispatch_fn = (
            cls_or_wrapper._get_dispatch()
            if hasattr(cls_or_wrapper, '_get_dispatch')
            else cls_or_wrapper._state_row().dispatch_fn
        )
        trail = Trail()
        capture = capture_vars or []
        sg = StepGenerator(dispatch_fn, None, None, None, *args, trail)
        gen, value = sg.send(None)
        results = []
        while True:
            if gen is None:
                if value is _DONE:
                    break
                results.append(tuple(deref(v) for v in capture))
                gen, value = sg.send(None)
            else:
                gen, value = gen.send(value)
        return results

    def test_append_concat(self):
        """append([1,2], [3,4], Z_) → Z_ = [1,2,3,4]."""
        # nv
        append = get_builtin_class("append")
        Z_ = Var()
        results = self._collect(append, [1, 2], [3, 4], Z_, capture_vars=[Z_])
        assert results == [([1, 2, 3, 4],)]

    def test_append_split(self):
        """append(X_, Y_, [1, 2, 3]) → enumerate all splits."""
        # nv
        append = get_builtin_class("append")
        X_ = Var()
        Y_ = Var()
        results = self._collect(append, X_, Y_, [1, 2, 3], capture_vars=[X_, Y_])
        assert len(results) == 4
        assert results[0] == ([], [1, 2, 3])
        assert results[-1] == ([1, 2, 3], [])

    def test_between_enumerate(self):
        """between(1, 5, X_) → yields 1,2,3,4,5."""
        # nv
        between = get_builtin_class("between")
        X_ = Var()
        results = self._collect(between, 1, 5, X_, capture_vars=[X_])
        assert [r[0] for r in results] == [1, 2, 3, 4, 5]

    def test_length_check(self):
        """length([a, b, c], N_) → N_ = 3."""
        # nv
        length = get_builtin_class("length")
        N_ = Var()
        results = self._collect(length, [10, 20, 30], N_, capture_vars=[N_])
        assert results == [(3,)]

    def test_in_member(self):
        """in_(X_, [a, b, c]) → yields a, b, c."""
        # nv
        in_ = get_builtin_class("in_")
        X_ = Var()
        results = self._collect(in_, X_, ["a", "b", "c"], capture_vars=[X_])
        assert [r[0] for r in results] == ["a", "b", "c"]

    def test_reverse(self):
        """reverse([1,2,3], R_) → R_ = [3,2,1]."""
        # nv
        reverse = get_builtin_class("reverse")
        R_ = Var()
        results = self._collect(reverse, [1, 2, 3], R_, capture_vars=[R_])
        assert results == [([3, 2, 1],)]

    def test_sort(self):
        """sort([3,1,2,1], S_) → S_ = [1,2,3]."""
        # nv
        sort = get_builtin_class("sort")
        S_ = Var()
        results = self._collect(sort, [3, 1, 2, 1], S_, capture_vars=[S_])
        assert results == [([1, 2, 3],)]

    def test_plus_relational(self):
        """plus(3, 4, Z_) → Z_ = 7."""
        # nv
        plus = get_builtin_class("plus")
        Z_ = Var()
        results = self._collect(plus, 3, 4, Z_, capture_vars=[Z_])
        assert results == [(7,)]

    def test_succ_forward(self):
        """succ(5, Y_) → Y_ = 6."""
        # nv
        succ = get_builtin_class("succ")
        Y_ = Var()
        results = self._collect(succ, 5, Y_, capture_vars=[Y_])
        assert results == [(6,)]

    def test_succ_backward(self):
        """succ(X_, 6) → X_ = 5."""
        # nv
        succ = get_builtin_class("succ")
        X_ = Var()
        results = self._collect(succ, X_, 6, capture_vars=[X_])
        assert results == [(5,)]


# ── Execution via call() API ──────────────────────────────────────────────────


class TestCallAPI:
    """Use the builtin classes with the call() solve API."""

    def _module(self):
        from clausal.logic.database import Module
        return Module("test")

    def test_call_append(self):
        """call('append', ...) using class field info to understand the args."""
        # nv
        from clausal.logic.solve import call
        append = get_builtin_class("append")
        Z_ = Var()
        mod = self._module()
        results = []
        for _ in call(append._functor, [1, 2], [3], Z_, module=mod):
            results.append(deref(Z_))
        assert results == [[1, 2, 3]]

    def test_call_between(self):
        # nv
        from clausal.logic.solve import call
        between = get_builtin_class("between")
        X_ = Var()
        mod = self._module()
        values = []
        for _ in call(between._functor, 1, 3, X_, module=mod):
            values.append(deref(X_))
        assert values == [1, 2, 3]

    def test_call_length(self):
        # nv
        from clausal.logic.solve import call
        N_ = Var()
        mod = self._module()
        results = []
        for _ in call("length", [10, 20], N_, module=mod):
            results.append(deref(N_))
        assert results == [2]

    def test_construct_then_unpack_for_call(self):
        """Construct a term, then unpack its fields into call() args."""
        # nv
        from clausal.logic.solve import call
        append = get_builtin_class("append")
        Z_ = Var()
        term = append([1], [2], Z_)
        # P2: unpacking IS the cell -- the functor and the arguments in
        # order, with no field-name round trip to get them back.
        args = list(cell_args(term))
        mod = self._module()
        results = []
        for _ in call(cell_functor(term), *args, module=mod):
            results.append(deref(Z_))
        assert results == [[1, 2]]
