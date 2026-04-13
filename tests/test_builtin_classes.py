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
from clausal.logic.predicate import PredicateMeta, is_term_instance, term_field_names
from clausal.logic.variables import Var, deref


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
    """Test that single-arity builtin classes produce proper term instances."""

    def test_append_positional(self):
        # nv
        append = get_builtin_class("append")
        t = append([1, 2], [3], [1, 2, 3])
        assert is_term_instance(t)
        assert t.l1 == [1, 2]
        assert t.l2 == [3]
        assert t.l3 == [1, 2, 3]

    def test_append_keyword(self):
        # nv
        append = get_builtin_class("append")
        t = append(l1=[1], l2=[2])
        assert t.l1 == [1]
        assert t.l2 == [2]
        # l3 should be auto-filled with Var()
        assert isinstance(deref(t.l3), Var)

    def test_between_partial(self):
        # nv
        between = get_builtin_class("between")
        t = between(low=1, high=10)
        assert t.low == 1
        assert t.high == 10
        assert isinstance(deref(t.x), Var)

    def test_length_positional(self):
        # nv
        length = get_builtin_class("length")
        t = length([1, 2, 3], 3)
        assert t.lst == [1, 2, 3]
        assert t.n == 3

    def test_zero_arity(self):
        # nv
        nl = get_builtin_class("nl")
        assert isinstance(nl, PredicateMeta)
        assert nl._arity == 0

    def test_no_args_all_vars(self):
        # nv
        in_ = get_builtin_class("in_")
        t = in_()
        assert isinstance(deref(t.elem), Var)
        assert isinstance(deref(t.lst), Var)


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
        # nv
        append = get_builtin_class("append")
        t = append([1], [2], [1, 2])
        assert term_field_names(t) == ("l1", "l2", "l3")


# ── PredicateMeta protocol ────────────────────────────────────────────────────


class TestPredicateMetaProtocol:
    """Builtin classes should satisfy the PredicateMeta protocol."""

    def test_is_predicate_meta(self):
        # nv
        append = get_builtin_class("append")
        assert isinstance(append, PredicateMeta)

    def test_functor_property(self):
        # nv
        append = get_builtin_class("append")
        assert append._functor == "append"

    def test_arity_property(self):
        # nv
        append = get_builtin_class("append")
        assert append._arity == 3

    def test_locked(self):
        # nv
        append = get_builtin_class("append")
        assert append._locked is True

    def test_assertz_raises_on_locked(self):
        # nv
        append = get_builtin_class("append")
        with pytest.raises(RuntimeError, match="locked"):
            append._assertz("dummy")

    def test_dispatch_fn_set(self):
        # nv
        append = get_builtin_class("append")
        assert append._dispatch_fn is not None

    def test_get_dispatch(self):
        # nv
        append = get_builtin_class("append")
        fn = append._get_dispatch()
        assert callable(fn)

    def test_db_builtin_no_dispatch(self):
        """DB-dependent builtins should not have dispatch set (needs db)."""
        # nv
        assertz = get_builtin_class("assertz")
        assert assertz._dispatch_fn is None


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
        assert "between" in r
        assert "low=1" in r
        assert "high=10" in r
        assert "x=99" in r

    def test_match_args(self):
        # nv
        append = get_builtin_class("append")
        t = append([1], [2], [1, 2])
        match t:
            case append(a, b, c):  # type: ignore[misc]
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
        assert is_term_instance(t)
        assert type(t)._arity == 2

    def test_maplist_3_construction(self):
        # nv
        ml = get_builtin_class("maplist")
        t = ml("goal", [1, 2], [2, 4])
        assert is_term_instance(t)
        assert type(t)._arity == 3

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
        assert type(t)._arity == 2

    def test_phrase_3_construction(self):
        # nv
        p = get_builtin_class("phrase")
        t = p("rule", [1, 2], [])
        assert type(t)._arity == 3

    def test_multi_repr(self):
        # nv
        ml = get_builtin_class("maplist")
        assert "maplist" in repr(ml)
        assert "[2, 3]" in repr(ml)


# ── is_term_instance / term_field_names ───────────────────────────────────────


class TestTermHelpers:
    def test_is_term_instance_true(self):
        # nv
        append = get_builtin_class("append")
        t = append([1], [2], [1, 2])
        assert is_term_instance(t)

    def test_is_term_instance_false_on_class(self):
        # nv
        append = get_builtin_class("append")
        assert not is_term_instance(append)

    def test_term_field_names(self):
        # nv
        in_ = get_builtin_class("in_")
        t = in_(1, [1, 2])
        assert term_field_names(t) == ("elem", "lst")


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
            else cls_or_wrapper._dispatch_fn
        )
        trail = Trail()
        capture = capture_vars or []
        sg = StepGenerator(dispatch_fn, None, *args, trail)
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
        # unpack: the term's fields give us the args in the right order
        args = [getattr(term, f) for f in type(term)._fields]
        mod = self._module()
        results = []
        for _ in call(type(term)._functor, *args, module=mod):
            results.append(deref(Z_))
        assert results == [[1, 2]]
