"""
Tests for the clausal.logic.variables C extension.

Covers:
  - Var creation and properties
  - Trail mark / undo
  - unify: success, failure, var-var, var-term, compound, atomic
  - Backtracking (partial unification rollback)
  - deref and walk
  - is_var
  - occurs_check
  - unify_with_occurs_check
  - Chained bindings (multi-step deref)
  - Trail length / repr
  - GC / refcount sanity (via gc module)
"""

import gc
import sys
import unittest

import clausal.logic.variables as logicvars
from clausal.logic.variables import Var, Trail, unify, unify_with_occurs_check, deref, walk, is_var, occurs_check


class TestVarBasics(unittest.TestCase):

    def test_new_var_is_unbound(self):
        # nv
        x = Var()
        self.assertFalse(x.is_bound)

    def test_unbound_value_is_self(self):
        # nv
        x = Var()
        self.assertIs(x.value, x)

    def test_is_var_on_unbound(self):
        # nv
        self.assertTrue(is_var(Var()))

    def test_is_var_on_int(self):
        # nv
        self.assertFalse(is_var(42))

    def test_is_var_on_string(self):
        # nv
        self.assertFalse(is_var("hello"))

    def test_var_has_id(self):
        # nv
        x = Var()
        y = Var()
        self.assertIsInstance(x._id, int)
        self.assertLess(x._id, y._id)  # monotonically increasing

    def test_repr_unbound(self):
        # nv
        x = Var()
        r = repr(x)
        self.assertIn("Var(", r)
        self.assertIn(str(x._id), r)

    def test_repr_bound(self):
        # nv
        x = Var()
        t = Trail()
        unify(x, 99, t)
        r = repr(x)
        self.assertIn("99", r)

    def test_distinct_vars(self):
        # nv
        x = Var()
        y = Var()
        self.assertIsNot(x, y)

    def test_var_hashable(self):
        # nv
        x = Var()
        y = Var()
        d = {x: 1, y: 2}
        self.assertEqual(d[x], 1)
        self.assertEqual(d[y], 2)


class TestTrailBasics(unittest.TestCase):

    def test_new_trail_length_zero(self):
        # nv
        t = Trail()
        self.assertEqual(len(t), 0)

    def test_mark_on_empty(self):
        # nv
        t = Trail()
        self.assertEqual(t.mark(), 0)

    def test_repr(self):
        # nv
        t = Trail()
        self.assertIn("Trail", repr(t))

    def test_mark_advances_after_bind(self):
        # nv
        x = Var()
        t = Trail()
        unify(x, 1, t)
        self.assertEqual(len(t), 1)
        self.assertEqual(t.mark(), 1)

    def test_undo_empty_is_noop(self):
        # nv
        t = Trail()
        t.undo(0)   # should not raise

    def test_undo_bad_mark_raises(self):
        # nv
        t = Trail()
        with self.assertRaises(ValueError):
            t.undo(-1)
        # undo() past the current trail length is a no-op (the outer context
        # already rewound past this mark — common when generators with
        # try/finally are abandoned during NAF/forall/find_all).
        t.undo(999)  # should not raise

    def test_reset(self):
        # nv
        x = Var()
        t = Trail()
        unify(x, 42, t)
        self.assertTrue(x.is_bound)
        t.reset()
        self.assertEqual(len(t), 0)
        self.assertFalse(x.is_bound)


class TestUnifyVarTerm(unittest.TestCase):

    def setUp(self):
        self.t = Trail()

    def test_var_int(self):
        # nv
        x = Var()
        self.assertTrue(unify(x, 42, self.t))
        self.assertTrue(x.is_bound)
        self.assertEqual(deref(x), 42)

    def test_var_string(self):
        # nv
        x = Var()
        self.assertTrue(unify(x, "hello", self.t))
        self.assertEqual(deref(x), "hello")

    def test_var_float(self):
        # nv
        x = Var()
        self.assertTrue(unify(x, 3.14, self.t))
        self.assertAlmostEqual(deref(x), 3.14)

    def test_var_none(self):
        # nv
        x = Var()
        self.assertTrue(unify(x, None, self.t))
        self.assertIsNone(deref(x))

    def test_reversed_order_works(self):
        # nv
        x = Var()
        self.assertTrue(unify(42, x, self.t))
        self.assertEqual(deref(x), 42)

    def test_var_already_bound_same_value(self):
        # nv
        x = Var()
        unify(x, 7, self.t)
        self.assertTrue(unify(x, 7, self.t))

    def test_var_already_bound_different_value_fails(self):
        # nv
        x = Var()
        unify(x, 7, self.t)
        self.assertFalse(unify(x, 8, self.t))

    def test_var_is_bound_after_unify(self):
        # nv
        x = Var()
        unify(x, "foo", self.t)
        self.assertFalse(is_var(x))


class TestUnifyVarVar(unittest.TestCase):

    def setUp(self):
        self.t = Trail()

    def test_same_var_trivially_unifies(self):
        # nv
        x = Var()
        self.assertTrue(unify(x, x, self.t))
        self.assertFalse(x.is_bound)   # self-unify doesn't bind

    def test_two_vars_bind(self):
        # nv
        x = Var()
        y = Var()
        self.assertTrue(unify(x, y, self.t))
        # One of them is bound; the pair should deref to the same root
        self.assertIs(deref(x), deref(y))

    def test_binding_direction(self):
        """Newer var (larger _id) should be bound to older (smaller _id)."""
        # nv
        x = Var()
        y = Var()
        # y has larger _id
        self.assertGreater(y._id, x._id)
        unify(x, y, self.t)
        # y should be bound, x should be the root
        self.assertFalse(x.is_bound)
        self.assertTrue(y.is_bound)
        self.assertIs(deref(y), x)

    def test_var_var_then_bind_one(self):
        # nv
        x = Var()
        y = Var()
        unify(x, y, self.t)
        unify(x, 99, self.t)
        # Both should deref to 99
        self.assertEqual(deref(x), 99)
        self.assertEqual(deref(y), 99)

    def test_three_vars(self):
        # nv
        x, y, z = Var(), Var(), Var()
        t = self.t
        unify(x, y, t)
        unify(y, z, t)
        unify(z, "end", t)
        self.assertEqual(deref(x), "end")
        self.assertEqual(deref(y), "end")
        self.assertEqual(deref(z), "end")


class TestUnifyAtomics(unittest.TestCase):

    def setUp(self):
        self.t = Trail()

    def test_int_int_equal(self):
        # nv
        self.assertTrue(unify(1, 1, self.t))

    def test_int_int_unequal(self):
        # nv
        self.assertFalse(unify(1, 2, self.t))

    def test_string_string_equal(self):
        # nv
        self.assertTrue(unify("foo", "foo", self.t))

    def test_string_string_unequal(self):
        # nv
        self.assertFalse(unify("foo", "bar", self.t))

    def test_int_string_fails(self):
        # nv
        self.assertFalse(unify(1, "1", self.t))

    def test_none_none(self):
        # nv
        self.assertTrue(unify(None, None, self.t))

    def test_bool_int(self):
        # True == 1 in Python
        # nv
        self.assertTrue(unify(True, 1, self.t))


class TestUnifyCompound(unittest.TestCase):

    def setUp(self):
        self.t = Trail()

    def test_tuples_equal(self):
        # nv
        self.assertTrue(unify(("f", 1, 2), ("f", 1, 2), self.t))

    def test_tuples_unequal_functor(self):
        # nv
        self.assertFalse(unify(("f", 1), ("g", 1), self.t))

    def test_tuples_unequal_arity(self):
        # nv
        self.assertFalse(unify(("f", 1), ("f", 1, 2), self.t))

    def test_tuples_with_var(self):
        # nv
        x = Var()
        self.assertTrue(unify(("f", x, 2), ("f", 1, 2), self.t))
        self.assertEqual(deref(x), 1)

    def test_tuples_nested(self):
        # nv
        x = Var()
        self.assertTrue(unify(("f", ("g", x)), ("f", ("g", 42)), self.t))
        self.assertEqual(deref(x), 42)

    def test_empty_tuples(self):
        # nv
        self.assertTrue(unify((), (), self.t))

    def test_tuple_vs_list_fails(self):
        # nv
        self.assertFalse(unify((1, 2), [1, 2], self.t))

    def test_lists_equal(self):
        # nv
        self.assertTrue(unify([1, 2, 3], [1, 2, 3], self.t))

    def test_lists_with_var(self):
        # nv
        x = Var()
        self.assertTrue(unify([1, x, 3], [1, 2, 3], self.t))
        self.assertEqual(deref(x), 2)

    def test_lists_unequal_length(self):
        # nv
        self.assertFalse(unify([1, 2], [1, 2, 3], self.t))


class TestBacktracking(unittest.TestCase):

    def test_undo_single_binding(self):
        # nv
        x = Var()
        t = Trail()
        mark = t.mark()
        unify(x, 42, t)
        self.assertEqual(deref(x), 42)
        t.undo(mark)
        self.assertFalse(x.is_bound)
        self.assertTrue(is_var(x))

    def test_undo_multiple_bindings(self):
        # nv
        x, y, z = Var(), Var(), Var()
        t = Trail()
        mark = t.mark()
        unify(x, 1, t)
        unify(y, 2, t)
        unify(z, 3, t)
        t.undo(mark)
        self.assertFalse(x.is_bound)
        self.assertFalse(y.is_bound)
        self.assertFalse(z.is_bound)

    def test_partial_undo(self):
        # nv
        x, y = Var(), Var()
        t = Trail()
        unify(x, 1, t)
        mark = t.mark()
        unify(y, 2, t)
        t.undo(mark)
        self.assertTrue(x.is_bound)
        self.assertFalse(y.is_bound)

    def test_failure_auto_rollback(self):
        """unify() must roll back partial bindings on failure."""
        # nv
        x, y = Var(), Var()
        t = Trail()
        mark = t.mark()
        # ("f", X, Y) vs ("f", 1, 1) — first subterm succeeds (X=1),
        # second fails if Y has already been bound differently.
        unify(y, 99, t)
        result = unify(("f", x, y), ("f", 1, 2), t)
        self.assertFalse(result)
        # x must be rolled back: the compound unify failed
        self.assertFalse(x.is_bound)
        # y was bound before the unify attempt; that's a separate trail entry
        self.assertEqual(deref(y), 99)

    def test_nested_choice_points(self):
        # nv
        x = Var()
        t = Trail()

        outer = t.mark()
        unify(x, "a", t)

        inner = t.mark()
        # try another value — but x is already "a", so this fails
        result = unify(x, "b", t)
        self.assertFalse(result)
        # inner undo not needed (already done by unify on failure)
        self.assertEqual(deref(x), "a")   # outer binding survives

        t.undo(outer)
        self.assertFalse(x.is_bound)

    def test_var_var_undo(self):
        # nv
        x = Var()
        y = Var()
        t = Trail()
        mark = t.mark()
        unify(x, y, t)
        # one of x,y is bound to the other
        self.assertIs(deref(x), deref(y))
        t.undo(mark)
        # both should be unbound again
        self.assertFalse(x.is_bound)
        self.assertFalse(y.is_bound)

    def test_reuse_var_after_undo(self):
        # nv
        x = Var()
        t = Trail()

        mark = t.mark()
        unify(x, 1, t)
        self.assertEqual(deref(x), 1)
        t.undo(mark)

        unify(x, 2, t)
        self.assertEqual(deref(x), 2)


class TestDeref(unittest.TestCase):

    def test_deref_unbound(self):
        # nv
        x = Var()
        self.assertIs(deref(x), x)

    def test_deref_int(self):
        # nv
        self.assertEqual(deref(42), 42)

    def test_deref_bound_var(self):
        # nv
        x = Var()
        t = Trail()
        unify(x, "hi", t)
        self.assertEqual(deref(x), "hi")

    def test_deref_chain(self):
        # nv
        x, y, z = Var(), Var(), Var()
        t = Trail()
        unify(x, y, t)  # y binds to x (older)
        unify(x, z, t)  # z binds to x (older)
        unify(x, 7, t)
        self.assertEqual(deref(y), 7)
        self.assertEqual(deref(z), 7)


class TestWalk(unittest.TestCase):

    def test_walk_atomic(self):
        # nv
        self.assertEqual(walk(42), 42)
        self.assertEqual(walk("hi"), "hi")

    def test_walk_unbound(self):
        # nv
        x = Var()
        self.assertIs(walk(x), x)

    def test_walk_bound(self):
        # nv
        x = Var()
        t = Trail()
        unify(x, 99, t)
        self.assertEqual(walk(x), 99)

    def test_walk_tuple(self):
        # nv
        x = Var()
        t = Trail()
        unify(x, 5, t)
        result = walk(("f", x, 2))
        self.assertEqual(result, ("f", 5, 2))

    def test_walk_nested(self):
        # nv
        x, y = Var(), Var()
        t = Trail()
        unify(x, 1, t)
        unify(y, 2, t)
        result = walk(("f", ("g", x), y))
        self.assertEqual(result, ("f", ("g", 1), 2))

    def test_walk_list(self):
        # nv
        x = Var()
        t = Trail()
        unify(x, "z", t)
        result = walk([1, x, 3])
        self.assertEqual(result, [1, "z", 3])

    def test_walk_unbound_in_compound(self):
        # nv
        x = Var()
        result = walk(("f", x, 2))
        # x is unbound — should remain in the result
        self.assertIsInstance(result, tuple)
        self.assertIs(result[1], x)

    def test_walk_returns_new_object(self):
        # nv
        x = Var()
        t = Trail()
        unify(x, 1, t)
        original = ("f", x)
        walked = walk(original)
        self.assertIsNot(walked, original)


class TestOccursCheck(unittest.TestCase):

    def test_var_not_in_atomic(self):
        # nv
        x = Var()
        self.assertFalse(occurs_check(x, 42))

    def test_var_in_itself(self):
        # nv
        x = Var()
        self.assertTrue(occurs_check(x, x))

    def test_var_in_tuple(self):
        # nv
        x = Var()
        self.assertTrue(occurs_check(x, ("f", 1, x)))

    def test_var_not_in_tuple(self):
        # nv
        x = Var()
        y = Var()
        self.assertFalse(occurs_check(x, ("f", y, 1)))

    def test_var_in_nested(self):
        # nv
        x = Var()
        self.assertTrue(occurs_check(x, ("f", ("g", x))))

    def test_var_in_list(self):
        # nv
        x = Var()
        self.assertTrue(occurs_check(x, [1, 2, x]))

    def test_bound_var_not_treated_as_var(self):
        # nv
        x = Var()
        t = Trail()
        unify(x, 99, t)
        # x is now bound; occurs_check should deref x before searching
        self.assertFalse(occurs_check(x, ("f", 1)))

    def test_var_found_through_binding(self):
        """occurs_check(x, term) should follow bindings in term."""
        # nv
        x = Var()
        y = Var()
        t = Trail()
        unify(y, x, t)   # y → x
        # x appears in (f, y) because y→x
        self.assertTrue(occurs_check(x, ("f", y)))


class TestUnifyWithOccursCheck(unittest.TestCase):

    def test_simple_success(self):
        # nv
        x = Var()
        t = Trail()
        self.assertTrue(unify_with_occurs_check(x, 42, t))
        self.assertEqual(deref(x), 42)

    def test_circular_fails(self):
        """X = f(X) must fail with the occurs check."""
        # nv
        x = Var()
        t = Trail()
        result = unify_with_occurs_check(x, ("f", x), t)
        self.assertFalse(result)
        self.assertFalse(x.is_bound)   # rolled back

    def test_non_circular_succeeds(self):
        # nv
        x = Var()
        y = Var()
        t = Trail()
        self.assertTrue(unify_with_occurs_check(("f", x), ("f", y), t))

    def test_nested_circular_fails(self):
        # nv
        x = Var()
        t = Trail()
        result = unify_with_occurs_check(x, ("f", ("g", x)), t)
        self.assertFalse(result)
        self.assertFalse(x.is_bound)

    def test_without_occurs_check_allows_cycle(self):
        """Without OC, X = f(X) succeeds (Prolog rational tree)."""
        # nv
        x = Var()
        t = Trail()
        result = unify(x, ("f", x), t)
        self.assertTrue(result)


class TestEdgeCases(unittest.TestCase):

    def test_wrong_trail_type_raises(self):
        # nv
        with self.assertRaises(TypeError):
            unify(1, 1, "not a trail")

    def test_wrong_trail_type_occ(self):
        # nv
        with self.assertRaises(TypeError):
            unify_with_occurs_check(1, 1, [])

    def test_unify_many_vars(self):
        """Stress test with a large chain of variables."""
        # nv
        t = Trail()
        vars_ = [Var() for _ in range(1000)]
        for i in range(len(vars_) - 1):
            self.assertTrue(unify(vars_[i], vars_[i + 1], t))
        unify(vars_[-1], "end", t)
        self.assertEqual(deref(vars_[0]), "end")

    def test_mark_undo_repeated(self):
        # nv
        x = Var()
        t = Trail()
        for i in range(100):
            mark = t.mark()
            unify(x, i, t)
            self.assertEqual(deref(x), i)
            t.undo(mark)
            self.assertFalse(x.is_bound)

    def test_gc_collects_trail(self):
        """Trails and Vars should be garbage-collected without leaks."""
        # nv
        gc.collect()
        before = len(gc.get_objects())
        for _ in range(50):
            t = Trail()
            x = Var()
            unify(x, 1, t)
        gc.collect()
        # We don't assert a specific count, but this should not raise.

    def test_walk_deeply_nested(self):
        # nv
        t = Trail()
        x = Var()
        unify(x, 42, t)
        term = x
        for _ in range(100):
            term = ("f", term)
        result = walk(term)
        # Walk the result to confirm it's fully substituted
        def depth_check(v, depth=0):
            if isinstance(v, tuple):
                return depth_check(v[1], depth + 1)
            return v
        self.assertEqual(depth_check(result), 42)

    def test_trail_undo_type_error(self):
        # nv
        t = Trail()
        with self.assertRaises((TypeError, ValueError)):
            t.undo("not an int")

    def test_deref_non_var(self):
        # nv
        self.assertEqual(deref(None), None)
        self.assertEqual(deref([1, 2, 3]), [1, 2, 3])

    def test_is_var_on_var(self):
        # nv
        x = Var()
        self.assertTrue(is_var(x))
        t = Trail()
        unify(x, 1, t)
        self.assertFalse(is_var(x))


if __name__ == "__main__":
    unittest.main(verbosity=2)
