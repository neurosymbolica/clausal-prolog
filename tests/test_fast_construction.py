"""Tests for the `_clausal_new` generated fast constructor (Phase 0, Task 1).

``PredicateMeta.__call__`` (the slow path) is unchanged.  ``_clausal_new`` is
an ADDITIVE, per-class, exec-generated classmethod: positional-only, no
missing-field backfill, no arity checking.  It exists so a later compiler
task can emit it for statically-saturated construction.
"""

import pytest

from clausal.logic.predicate import make_predicate


class TestFastConstructorBasics:
    def test_fast_new_matches_slow_path(self):
        # nv
        foo = make_predicate("foo", ["x", "y"])
        fast = foo._clausal_new(1, 2)
        slow = foo(1, 2)
        assert type(fast) is foo
        assert fast.x == 1
        assert fast.y == 2
        assert fast == slow
        assert fast is not slow

    def test_fast_new_single_field(self):
        # nv
        bar = make_predicate("bar", ["a"])
        fast = bar._clausal_new(42)
        assert fast.a == 42
        assert fast == bar(42)


class TestAtomsGetNoFastConstructor:
    def test_atom_class_has_no_clausal_new(self):
        # nv
        red = make_predicate("red", [])
        assert "_clausal_new" not in vars(red)


class TestFieldNamedClausalNew:
    def test_field_named_clausal_new_uses_slow_path_only(self):
        # nv
        weird = make_predicate("weird", ["_clausal_new"])
        # class creation must not raise, and the slow path still works
        t = weird(_clausal_new=5)
        assert t._clausal_new == 5

    def test_field_named_clausal_new_gets_no_fast_constructor(self):
        # nv
        weird = make_predicate("weird2", ["_clausal_new"])
        # "_clausal_new" is a field name here, so __slots__ owns the class
        # attribute (a member descriptor) at that name. The fast-new factory
        # must not clobber it with a classmethod.
        assert "_clausal_new" in weird.__slots__
        assert not isinstance(vars(weird)["_clausal_new"], classmethod)


class TestCacheShareByFieldTuple:
    def test_two_same_named_classes_each_get_working_fast_new(self):
        # nv
        foo1 = make_predicate("foo", ["x"])
        foo2 = make_predicate("foo", ["x"])
        assert foo1 is not foo2
        f1 = foo1._clausal_new(10)
        f2 = foo2._clausal_new(20)
        assert type(f1) is foo1
        assert type(f2) is foo2
        assert f1.x == 10
        assert f2.x == 20


class TestStructuralParity:
    def test_fast_path_instances_unhashable(self):
        # nv
        baz = make_predicate("baz", ["x"])
        fast = baz._clausal_new(1)
        assert baz.__hash__ is None
        with pytest.raises(TypeError):
            hash(fast)

    def test_fast_path_equal_to_slow_path(self):
        # nv
        qux = make_predicate("qux", ["x", "y"])
        fast = qux._clausal_new(1, 2)
        slow = qux(x=1, y=2)
        assert fast == slow
        assert slow == fast

    def test_fast_path_match_args_pattern_matching(self):
        # nv
        quux = make_predicate("quux", ["x", "y"])
        fast = quux._clausal_new(1, 2)
        match fast:
            case quux(x=vx, y=vy):
                assert vx == 1
                assert vy == 2
            case _:
                pytest.fail("pattern match against fast-path instance failed")
