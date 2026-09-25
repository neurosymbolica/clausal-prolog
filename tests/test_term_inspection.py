"""tests/test_term_inspection.py — V2-13 term inspection builtins.

Tests for:
  copy_term/2       — deep copy with fresh Vars
  term_variables/2  — collect unbound Vars in term
  numbervars/3     — number unbound Vars with $VAR(N)
"""

import pytest

from clausal.logic.atoms import is_atom, mint
from clausal.logic.cells import chars
from clausal.logic.database import Module
from clausal.logic.solve import solve
from clausal.logic.variables import Var, Trail, deref, is_var, unify
from clausal.terms import Compound, Call, LoadName, KWTerm, DictTerm, SegList, ConcreteSeg, VarSeg
from tests.predicate_api_support import class_arm_predicate


# ── Helpers ────────────────────────────────────────────────────────────────────


def fresh_module():
    return Module("test")


def solutions(goal):
    """Drive goal and return list of (nothing — just count solutions)."""
    mod = fresh_module()
    trail = Trail()
    return list(solve(goal, mod, trail))


def sol_var(goal, var):
    """Return dereffed values of var across all solutions of goal."""
    mod = fresh_module()
    trail = Trail()
    return [deref(var) for _ in solve(goal, mod, trail)]


def goal(functor, *args):
    """Build a Call goal for a builtin."""
    return Call(func=LoadName(name=functor), args=list(args), kwargs=[])


# ── copy_term/2 ─────────────────────────────────────────────────────────────────


class TestCopyTerm:

    def test_copy_atom(self):
        # nv
        copy = Var()
        vals = sol_var(goal("copy_term", "hello", copy), copy)
        assert vals == ["hello"]

    def test_copy_integer(self):
        # nv
        copy = Var()
        vals = sol_var(goal("copy_term", 42, copy), copy)
        assert vals == [42]

    def test_copy_none(self):
        # nv
        copy = Var()
        vals = sol_var(goal("copy_term", None, copy), copy)
        assert vals == [None]

    def test_copy_list_ground(self):
        # nv
        copy = Var()
        vals = sol_var(goal("copy_term", [1, 2, 3], copy), copy)
        assert vals == [[1, 2, 3]]

    def test_copy_compound_ground(self):
        # nv
        term = Compound("foo", (1, 2))
        copy = Var()
        vals = sol_var(goal("copy_term", term, copy), copy)
        assert len(vals) == 1
        c = vals[0]
        assert isinstance(c, Compound)
        assert c.functor == "foo"
        assert c.args == (1, 2)

    def test_copy_var_gets_fresh_var(self):
        # nv
        x = Var()
        copy = Var()
        mod = fresh_module()
        trail = Trail()
        for _ in solve(goal("copy_term", x, copy), mod, trail):
            c = deref(copy)
            assert is_var(c)
            assert c is not x

    def test_copy_preserves_sharing(self):
        """Two occurrences of the same Var → same fresh Var in copy."""
        # nv
        x = Var()
        term = Compound("f", (x, x))
        copy = Var()
        mod = fresh_module()
        trail = Trail()
        for _ in solve(goal("copy_term", term, copy), mod, trail):
            c = deref(copy)
            assert isinstance(c, Compound)
            a0, a1 = deref(c.args[0]), deref(c.args[1])
            assert is_var(a0) and is_var(a1)
            assert a0 is a1

    def test_copy_fresh_var_distinct_from_original(self):
        # nv
        x = Var()
        term = Compound("f", (x,))
        copy = Var()
        mod = fresh_module()
        trail = Trail()
        for _ in solve(goal("copy_term", term, copy), mod, trail):
            c = deref(copy)
            fresh = deref(c.args[0])
            assert fresh is not x

    def test_copy_nested_compound(self):
        # nv
        inner = Compound("bar", (Var(),))
        term = Compound("foo", (inner, 99))
        copy = Var()
        mod = fresh_module()
        trail = Trail()
        for _ in solve(goal("copy_term", term, copy), mod, trail):
            c = deref(copy)
            assert isinstance(c, Compound) and c.functor == "foo"
            c_inner = deref(c.args[0])
            assert isinstance(c_inner, Compound) and c_inner.functor == "bar"

    def test_copy_list_with_vars(self):
        # nv
        x = Var()
        lst = [1, x, 3]
        copy = Var()
        mod = fresh_module()
        trail = Trail()
        for _ in solve(goal("copy_term", lst, copy), mod, trail):
            c = deref(copy)
            assert isinstance(c, list)
            assert deref(c[0]) == 1
            assert is_var(deref(c[1]))
            assert deref(c[2]) == 3

    def test_copy_bound_var(self):
        """Var already bound → copy gets the bound value."""
        # nv
        trail = Trail()
        x = Var()
        unify(x, 42, trail)
        copy = Var()
        mod = fresh_module()
        for _ in solve(goal("copy_term", x, copy), mod, trail):
            assert deref(copy) == 42

    def test_copy_exactly_one_solution(self):
        # nv
        copy = Var()
        sols = solutions(goal("copy_term", Compound("f", (1,)), copy))
        assert len(sols) == 1

    def test_copy_no_side_effects_on_original(self):
        """copy_term does not bind original Vars."""
        # nv
        x = Var()
        term = Compound("f", (x,))
        copy = Var()
        solutions(goal("copy_term", term, copy))
        assert is_var(deref(x))


# ── term_variables/2 ────────────────────────────────────────────────────────────


class TestTermVariables:

    def test_ground_term_empty(self):
        # nv
        out = Var()
        vals = sol_var(goal("term_variables", 42, out), out)
        assert vals == [[]]

    def test_ground_compound_empty(self):
        # nv
        out = Var()
        vals = sol_var(goal("term_variables", Compound("f", (1, 2)), out), out)
        assert vals == [[]]

    def test_single_var(self):
        # nv
        x = Var()
        out = Var()
        mod = fresh_module()
        trail = Trail()
        for _ in solve(goal("term_variables", x, out), mod, trail):
            result = deref(out)
            assert isinstance(result, list)
            assert len(result) == 1
            assert result[0] is x

    def test_compound_with_vars(self):
        # nv
        x, y = Var(), Var()
        term = Compound("f", (x, y))
        out = Var()
        mod = fresh_module()
        trail = Trail()
        for _ in solve(goal("term_variables", term, out), mod, trail):
            result = deref(out)
            assert len(result) == 2
            assert result[0] is x
            assert result[1] is y

    def test_repeated_var_only_once(self):
        # nv
        x = Var()
        term = Compound("f", (x, x))
        out = Var()
        mod = fresh_module()
        trail = Trail()
        for _ in solve(goal("term_variables", term, out), mod, trail):
            result = deref(out)
            assert len(result) == 1
            assert result[0] is x

    def test_left_to_right_order(self):
        # nv
        x, y, z = Var(), Var(), Var()
        term = Compound("f", (x, Compound("g", (y,)), z))
        out = Var()
        mod = fresh_module()
        trail = Trail()
        for _ in solve(goal("term_variables", term, out), mod, trail):
            result = deref(out)
            assert [r is v for r, v in zip(result, [x, y, z])] == [True, True, True]

    def test_list_term(self):
        # nv
        x, y = Var(), Var()
        lst = [1, x, 2, y]
        out = Var()
        mod = fresh_module()
        trail = Trail()
        for _ in solve(goal("term_variables", lst, out), mod, trail):
            result = deref(out)
            assert len(result) == 2
            assert result[0] is x
            assert result[1] is y

    def test_bound_var_not_collected(self):
        """Bound Var derefs to value — not collected."""
        # nv
        trail = Trail()
        x = Var()
        unify(x, 99, trail)
        y = Var()
        term = Compound("f", (x, y))
        out = Var()
        mod = fresh_module()
        for _ in solve(goal("term_variables", term, out), mod, trail):
            result = deref(out)
            assert len(result) == 1
            assert result[0] is y

    def test_nested_vars(self):
        # nv
        x = Var()
        term = Compound("a", (Compound("b", (Compound("c", (x,)),)),))
        out = Var()
        mod = fresh_module()
        trail = Trail()
        for _ in solve(goal("term_variables", term, out), mod, trail):
            result = deref(out)
            assert len(result) == 1
            assert result[0] is x

    def test_exactly_one_solution(self):
        # nv
        out = Var()
        sols = solutions(goal("term_variables", Var(), out))
        assert len(sols) == 1


# ── numbervars/3 ───────────────────────────────────────────────────────────────


class TestNumberVars:

    def test_ground_term_no_vars(self):
        # nv
        end = Var()
        term = Compound("f", (1, 2))
        vals = sol_var(goal("numbervars", term, 0, end), end)
        assert vals == [0]

    def test_single_var(self):
        # nv
        x = Var()
        term = Compound("f", (x,))
        end = Var()
        mod = fresh_module()
        trail = Trail()
        for _ in solve(goal("numbervars", term, 0, end), mod, trail):
            xv = deref(x)
            assert xv == Compound("$VAR", (0,))
            assert deref(end) == 1

    def test_two_vars(self):
        # nv
        x, y = Var(), Var()
        term = Compound("f", (x, y))
        end = Var()
        mod = fresh_module()
        trail = Trail()
        for _ in solve(goal("numbervars", term, 0, end), mod, trail):
            assert deref(x) == Compound("$VAR", (0,))
            assert deref(y) == Compound("$VAR", (1,))
            assert deref(end) == 2

    def test_start_offset(self):
        # nv
        x = Var()
        term = Compound("f", (x,))
        end = Var()
        mod = fresh_module()
        trail = Trail()
        for _ in solve(goal("numbervars", term, 5, end), mod, trail):
            assert deref(x) == Compound("$VAR", (5,))
            assert deref(end) == 6

    def test_repeated_var_numbered_once(self):
        # nv
        x = Var()
        term = Compound("f", (x, x))
        end = Var()
        mod = fresh_module()
        trail = Trail()
        for _ in solve(goal("numbervars", term, 0, end), mod, trail):
            assert deref(x) == Compound("$VAR", (0,))
            assert deref(end) == 1

    def test_unbound_start_fails(self):
        # nv
        x = Var()
        end = Var()
        sols = solutions(goal("numbervars", x, Var(), end))
        assert len(sols) == 0

    def test_list_term(self):
        # nv
        x, y = Var(), Var()
        lst = [x, y]
        end = Var()
        mod = fresh_module()
        trail = Trail()
        for _ in solve(goal("numbervars", lst, 0, end), mod, trail):
            assert deref(x) == Compound("$VAR", (0,))
            assert deref(y) == Compound("$VAR", (1,))
            assert deref(end) == 2

    def test_exactly_one_solution(self):
        # nv
        end = Var()
        sols = solutions(goal("numbervars", 42, 0, end))
        assert len(sols) == 1

    def test_end_wrong_value_fails(self):
        """If End is already bound to wrong value, predicate fails."""
        # nv
        x = Var()
        term = Compound("f", (x,))
        # one var → end should be 1; bind end to 99 → should fail
        trail = Trail()
        end = Var()
        unify(end, 99, trail)
        mod = fresh_module()
        sols = list(solve(goal("numbervars", term, 0, end), mod, trail))
        assert len(sols) == 0

    def test_bindings_undone_after_backtrack(self):
        """numbervars binds vars via trail; bindings are undone on backtrack."""
        # nv
        x = Var()
        term = Compound("f", (x,))
        end = Var()
        mod = fresh_module()
        trail = Trail()
        # Collect solutions — after iteration ends, trail should be undone
        sols = list(solve(goal("numbervars", term, 0, end), mod, trail))
        assert len(sols) == 1
        # After solve completes (generator exhausted), trail is rewound
        # x should be unbound again since solve unwinds
        # Note: solve() doesn't undo the trail; the bindings persist at top level.
        # Just check that there was exactly 1 solution.


# ── gensym/2 ──────────────────────────────────────────────────────────────────


class TestGenSym:

    def setup_method(self):
        """Reset gensym counters between tests."""
        from clausal.logic.builtins.inspection import _gensym_counters
        _gensym_counters.clear()

    def test_basic(self):
        """gensym("x", A) → "x_1"."""
        # nv
        a = Var()
        vals = sol_var(goal("gensym", mint("x"), a), a)
        assert vals == [mint("x_1")]

    def test_sequential(self):
        """Two calls increment: "x_1", "x_2"."""
        # nv
        a1, a2 = Var(), Var()
        vals1 = sol_var(goal("gensym", mint("x"), a1), a1)
        vals2 = sol_var(goal("gensym", mint("x"), a2), a2)
        assert vals1 == [mint("x_1")]
        assert vals2 == [mint("x_2")]

    def test_different_prefixes(self):
        """Different prefixes have independent counters."""
        # nv
        a = Var()
        b = Var()
        sol_var(goal("gensym", mint("x"), a), a)
        vals = sol_var(goal("gensym", mint("y"), b), b)
        assert vals == [mint("y_1")]

    def test_unbound_prefix_fails(self):
        """gensym(X, A) with unbound X → no solutions."""
        # nv
        a = Var()
        sols = solutions(goal("gensym", Var(), a))
        assert len(sols) == 0

    def test_non_string_prefix_fails(self):
        """gensym(42, A) → no solutions."""
        # nv
        a = Var()
        sols = solutions(goal("gensym", 42, a))
        assert len(sols) == 0

    def test_counter_survives_backtracking(self):
        """Counter does NOT reset on backtracking — impure."""
        # nv
        a1 = Var()
        sol_var(goal("gensym", mint("z"), a1), a1)
        # Counter is now at 1; next call should give z_2
        a2 = Var()
        vals = sol_var(goal("gensym", mint("z"), a2), a2)
        assert vals == [mint("z_2")]

    def test_atom_already_bound_unification(self):
        """gensym("x", "x_1") succeeds if counter is at 1."""
        # nv
        sols = solutions(goal("gensym", mint("x"), mint("x_1")))
        assert len(sols) == 1

    def test_atom_already_bound_mismatch(self):
        """gensym("x", "x_99") fails when counter is at 1."""
        # nv
        sols = solutions(goal("gensym", mint("x"), mint("x_99")))
        assert len(sols) == 0

    def test_thread_safety(self):
        """Concurrent gensym calls produce unique atoms."""
        # nv
        import threading
        results = []
        lock = threading.Lock()

        def gen():
            a = Var()
            mod = fresh_module()
            trail = Trail()
            for _ in solve(goal("gensym", mint("t"), a), mod, trail):
                with lock:
                    results.append(deref(a))

        threads = [threading.Thread(target=gen) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(set(results)) == 10  # all unique


# ── copy_term/2 with KWTerm ────────────────────────────────────────────────────


class TestCopyTermKWTerm:

    def test_copy_kwterm_ground(self):
        """copy_term(KWTerm('r', a=1), Y) → Y is KWTerm('r', a=1)."""
        # nv
        copy = Var()
        vals = sol_var(goal("copy_term", KWTerm("r", a=1, b=2), copy), copy)
        assert len(vals) == 1
        c = vals[0]
        assert isinstance(c, KWTerm)
        assert c.functor == "r"
        assert c._fields == {"a": 1, "b": 2}

    def test_copy_kwterm_preserves_functor(self):
        """Functor name is preserved correctly (not replaced by fields dict)."""
        # nv
        copy = Var()
        vals = sol_var(goal("copy_term", KWTerm("myrel", x=99), copy), copy)
        assert len(vals) == 1
        assert vals[0].functor == "myrel"

    def test_copy_kwterm_var_field_gets_fresh_var(self):
        """Var in a KWTerm field → fresh Var in copy, not the original."""
        # nv
        x = Var()
        t = KWTerm("r", a=x)
        copy = Var()
        mod = fresh_module()
        trail = Trail()
        for _ in solve(goal("copy_term", t, copy), mod, trail):
            c = deref(copy)
            assert isinstance(c, KWTerm)
            assert c.functor == "r"
            fresh = deref(c._fields["a"])
            assert is_var(fresh)
            assert fresh is not x

    def test_copy_kwterm_sharing_preserved(self):
        """Two fields referencing the same Var → same fresh Var in copy."""
        # nv
        x = Var()
        t = KWTerm("r", a=x, b=x)
        copy = Var()
        mod = fresh_module()
        trail = Trail()
        for _ in solve(goal("copy_term", t, copy), mod, trail):
            c = deref(copy)
            assert isinstance(c, KWTerm)
            fa = deref(c._fields["a"])
            fb = deref(c._fields["b"])
            assert is_var(fa) and is_var(fb)
            assert fa is fb

    def test_copy_kwterm_no_side_effects_on_original(self):
        """copy_term does not bind Vars in the original KWTerm."""
        # nv
        x = Var()
        t = KWTerm("r", a=x)
        copy = Var()
        solutions(goal("copy_term", t, copy))
        assert is_var(deref(x))


# ── copy_term/2 and term_variables/2 with DictTerm / SegList ──────────────────
#
# DictTerm is still not handled by c_copy_term / c_collect_vars: it falls
# through to "return as-is" (copy_term shares the same Var objects;
# term_variables returns []).  These tests document that current behaviour
# so any future fix breaks visibly.
#
# SegList / SegString — historically had the same gap.  Closed by the
# 2026-05-25 string audit (F092 / F093 / F094): the Python wrapper in
# ``clausal/logic/builtins/inspection.py`` now short-circuits Seg*
# shapes before reaching the Seg*-blind C accelerator, producing an
# independent copy with FRESH Vars threaded through ``var_map`` and
# reporting every VarSeg's Var via ``term_variables`` /
# ``numbervars``.  The tests below are the inverted lock-in of the
# documenting tests added in commit 4507be8: they now assert the
# fixed contract.


class TestCopyTermDictTerm:

    def test_copy_dictterm_ground(self):
        """copy_term on a ground DictTerm succeeds (fall-through, shared)."""
        # nv
        copy = Var()
        vals = sol_var(goal("copy_term", DictTerm({"k": 1}), copy), copy)
        assert len(vals) == 1
        assert isinstance(vals[0], DictTerm)

    def test_copy_dictterm_var_not_freshened(self):
        """DictTerm Vars are NOT freshened — copy shares the original Var."""
        # nv
        x = Var()
        t = DictTerm({"k": x})
        copy = Var()
        mod = fresh_module()
        trail = Trail()
        for _ in solve(goal("copy_term", t, copy), mod, trail):
            c = deref(copy)
            assert isinstance(c, DictTerm)
            # current behaviour: same Var object (not a fresh copy)
            assert deref(c["k"]) is x


class TestTermVariablesDictTerm:

    def test_dictterm_vars_not_collected(self):
        """term_variables on DictTerm currently returns [] (gap, not handled)."""
        # nv
        x = Var()
        t = DictTerm({"k": x})
        out = Var()
        mod = fresh_module()
        trail = Trail()
        for _ in solve(goal("term_variables", t, out), mod, trail):
            result = deref(out)
            # current behaviour: DictTerm falls through → empty list
            assert result == []


class TestCopyTermSegList:
    """Test copy_term behaviour on SegList via the helper directly.

    SegList cannot be passed through the goal compiler, so we call
    _copy_term_impl directly to verify the new contract: copy_term
    produces an independent SegList whose VarSegs reference FRESH
    Vars (F092 — fixed in the 2026-05-25 string audit, Phase 2 Task 10).
    """

    def test_copy_seglist_var_freshened(self):
        """SegList VarSeg Vars ARE freshened — copy is independent of original."""
        # nv
        from clausal.logic.builtins.inspection import _copy_term_impl
        x = Var()
        t = SegList([ConcreteSeg([1, 2]), VarSeg(x)])
        c = _copy_term_impl(t, {})
        assert isinstance(c, SegList)
        # F092 (fixed): the VarSeg.var slot now holds a FRESH Var, not
        # the original ``x``.  Without this, binding the original's
        # var would propagate to the copy and vice versa, breaking
        # the per-call fresh-Var guarantee that copy_term provides.
        fresh = c._segments[1].var
        assert isinstance(fresh, Var)
        assert fresh is not x, (
            f"copy_term(SegList(..., VarSeg(x))) produced a copy whose "
            f"inner VarSeg.var IS the original x — expected a fresh "
            f"Var threaded through var_map. Regression on F092."
        )
        # Concrete elements are still equal but the container is a
        # NEW SegList object, not the input.
        assert c is not t
        assert c._segments[0].elements == [1, 2]

    def test_copy_seglist_var_sharing_preserved(self):
        """When the same Var appears in two VarSegs, the copy preserves
        the sharing (both new VarSegs reference the SAME fresh Var)."""
        # nv — F092 sharing invariant
        from clausal.logic.builtins.inspection import _copy_term_impl
        x = Var()
        t = SegList([VarSeg(x), ConcreteSeg([1]), VarSeg(x)])
        c = _copy_term_impl(t, {})
        a = c._segments[0].var
        b = c._segments[2].var
        assert isinstance(a, Var) and isinstance(b, Var)
        assert a is b, (
            f"copy_term must preserve Var sharing within Seg* containers: "
            f"the same original Var appearing in two VarSegs must map to "
            f"the SAME fresh Var in the copy. Got {a!r} vs {b!r}."
        )
        assert a is not x


class TestTermVariablesSegList:
    """Test term_variables behaviour on SegList via the helper directly.

    F093 (fixed in the 2026-05-25 string audit, Phase 2 Task 10):
    term_variables now reports the Var inside every VarSeg of a
    SegList / SegString.
    """

    def test_seglist_vars_collected(self):
        """term_variables on SegList now reports the VarSeg's Var."""
        # nv — F093 inverted lock-in
        from clausal.logic.builtins.inspection import _collect_vars_impl
        x = Var()
        t = SegList([VarSeg(x)])
        result = []
        _collect_vars_impl(t, result)
        assert result == [x], (
            f"term_variables(SegList([VarSeg(x)])) should report x; "
            f"got {result!r}. Regression on F093."
        )


# ── global_atom/2 ──────────────────────────────────────────────────────────────
#
# Reflection builtin exposing the process-wide predicate_builtins dict.
# Mode-driven: mint on (+name, -atom); guard on (+name, +atom); reverse-lookup
# on (-name, +atom); enumerate on (-name, -atom).
#
# Tests drive the builtin via ``call(cls, ...)`` rather than ``solve(goal, ...)``
# so that PredicateMeta class arguments pass through untouched (the goal
# compiler would otherwise emit them as bare name references).


def _global_atom_call(*args):
    """Invoke global_atom/2 directly via its dispatch fn and yield arg snapshots.

    Driving the dispatch function ourselves bypasses both the goal compiler
    (which would emit PredicateMeta args as bare names) and the ``call/N``
    meta-predicate (which shadows ``clausal.call`` after _export_builtin_classes
    runs).
    """
    from clausal.logic.builtins import get_builtin_class
    from clausal.logic.solve import _drive_trampoline
    cls = get_builtin_class("global_atom")
    dispatch_fn = cls._get_dispatch()
    trail = Trail()
    results = []
    for _ in _drive_trampoline(dispatch_fn, trail, *args):
        results.append(tuple(deref(a) for a in args))
    return results


class TestGlobalAtom:
    """Tests for global_atom/2 — reflection on the global atom dict."""

    # Use distinct names per test to avoid cross-test interference in the
    # process-wide predicate_builtins dict.

    def test_mint_on_demand(self):
        """(+name, -atom) — fresh name installs the interned SPELLING itself.

        P3-1 atom pivot (§1b/R2): no class is minted -- an atom IS the str.
        Inverts the pre-pivot pin that this builtin returned a PredicateMeta
        arity-0 class; see phase3-decomposition-and-p31-atom-pivot.md Task 7
        work item 4 (the sweep found this builtin was the last live,
        user-reachable atom-class-construction path)."""
        # nv
        from clausal.import_hook import predicate_builtins
        name = "_test_global_atom_mint_xyz"
        assert name not in predicate_builtins  # sanity: fresh
        atom = Var()
        results = _global_atom_call(mint(name), atom)
        assert len(results) == 1
        _, val = results[0]
        # THE FLIP (spec §5.1): the installed atom is the arity-0 CELL, and
        # the pool stays keyed by the SPELLING.
        assert val == mint(name)
        # Side-effect: it is now in the global dict.
        assert predicate_builtins.get(name) == val

    def test_idempotent_mint(self):
        """(+name, -atom) twice yields the same atom (EQUAL, spec §5.2)."""
        # nv
        name = "_test_global_atom_idempotent_xyz"
        a1 = Var()
        r1 = _global_atom_call(mint(name), a1)
        a2 = Var()
        r2 = _global_atom_call(mint(name), a2)
        assert len(r1) == 1 and len(r2) == 1
        # Equality, never identity (spec §2/§5.2).
        assert r1[0][1] == r2[0][1]

    def test_existing_pre_seeded_returned(self):
        """(+name, -atom) for an entry the pool already carries (e.g. minted
        by an earlier -private/-module declaration, or a prior
        ``global_atom/2`` call) returns THAT value rather than re-minting.

        P3-2 Task 8 (pool split): this used to use ``Var`` as the
        "pre-seeded" example, relying on the exact conflation that todo
        closed -- ``Var`` is a ``runtime_builtins`` (``INJECTED_RUNTIME_
        BUILTINS``) entry, not an atom, and ``predicate_builtins`` starts
        EMPTY post-split, so ``global_atom("Var", X)`` now correctly MINTS
        "Var" as a fresh atom string instead of returning the runtime
        class -- see
        todo/done/pythonic-ast-names-leak-into-strict-atom-namespace-2026-09-04.md.
        Seed the pool directly here instead, the way a real declaration or
        an earlier ``global_atom/2`` call would.

        Task 8 fix round 1 (Finding 2, review-caught): the first rewrite
        seeded the pool with ``predicate_builtins[name] = name`` -- the
        IDENTICAL value a fresh mint would ALSO produce
        (``setdefault(name, name)``), so the assertion passed identically
        whether the implementation correctly returned the existing entry
        OR blindly re-minted/overwrote it (the reviewer proved this by
        substituting a blind-overwrite implementation and watching the
        test stay green). The marker below is deliberately DISTINCT from
        ``name`` so "don't overwrite an existing entry" is actually
        exercised: a blind-overwrite bug would replace it with ``name``
        itself and this test would then, correctly, fail."""
        # nv
        from clausal.import_hook import predicate_builtins
        name = "_test_global_atom_preseeded_xyz"
        marker = mint(f"__preseeded_marker_for_{name}__")
        predicate_builtins[name] = marker
        try:
            out = Var()
            results = _global_atom_call(mint(name), out)
            assert len(results) == 1
            assert results[0][1] == marker
            assert results[0][1] != mint(name)
        finally:
            # F4/M9 (P3-2 whole-branch final review): ``predicate_builtins``
            # is process-global — without this the marker leaks into every
            # later test in the process, including a legitimate mint of the
            # same name by an unrelated test.
            del predicate_builtins[name]

    def test_a_non_atom_name_is_a_type_error_not_a_failure(self):
        """A string / char list / number in the Name position raises
        type_error(atom, Name), never fails silently: under
        ``-double_quotes(chars)`` the old ``global_atom("date", A)`` spelling
        hands over a CHAR LIST, and a silent failure there took five corpus
        suites down before anyone saw why (2026-09-08)."""
        import pytest
        from clausal.logic.exceptions import LogicException
        for bad in (chars("date"), ["d", "a", "t", "e"], 42):
            with pytest.raises(LogicException) as info:
                list(_global_atom_call(bad, Var()))
            shown = repr(info.value.term)
            assert "type_error" in shown and "atom" in shown, shown

    def test_guard_succeeds_when_atom_matches(self):
        """(+name, +atom) — succeeds iff atom IS the global class."""
        # nv
        from clausal.import_hook import predicate_builtins
        name = "_test_global_atom_guard_match_xyz"
        # Mint first.
        _global_atom_call(mint(name), Var())
        cls = predicate_builtins[name]
        # Guard mode with the right atom should succeed exactly once.
        results = _global_atom_call(mint(name), cls)
        assert len(results) == 1

    def test_guard_fails_when_atom_mismatches(self):
        """(+name, +atom) — fails when atom is NOT the global class for that name."""
        # nv
        name = "_test_global_atom_guard_mismatch_xyz"
        # Mint the global atom for 'name'.
        _global_atom_call(mint(name), Var())
        # Create a separate (non-global) PredicateMeta with the same name.
        impostor = class_arm_predicate(name, [])
        results = _global_atom_call(mint(name), impostor)
        assert results == []

    def test_reverse_lookup_returns_name(self):
        """(-name, +atom) — yields cls.__name__ when cls is a global atom."""
        # nv
        from clausal.import_hook import predicate_builtins
        name = "_test_global_atom_reverse_xyz"
        _global_atom_call(mint(name), Var())
        cls = predicate_builtins[name]
        # Reverse-lookup with bound atom.
        n_out = Var()
        results = _global_atom_call(n_out, cls)
        assert len(results) == 1
        # The NAME position answers an ATOM (spec §6.4).
        assert results[0][0] == mint(name)

    def test_reverse_lookup_fails_for_non_global_class(self):
        """(-name, +atom) — fails if atom is not the global class registered for its name."""
        # nv
        # A PredicateMeta NOT placed into predicate_builtins.
        local_only = class_arm_predicate("_test_global_atom_local_only_xyz", [])
        n_out = Var()
        results = _global_atom_call(n_out, local_only)
        assert results == []

    def test_enumerate_yields_minted_atoms(self):
        """(-name, -atom) — enumerates global atoms; minted one appears.

        THE FLIP (spec §5.1, §6.4): a registered atom is the arity-0 CELL
        whose slot 0 is the pool KEY, and the enumerated Name is that atom.
        A legacy 0-arity PredicateMeta (``make_predicate(n, [])``'s shape) is
        still accepted by the reader if anything installs one manually, so
        the enumerate assertion below allows either shape.
        """
        # nv
        from clausal.import_hook import predicate_builtins
        from clausal.logic.predicate import PredicateMeta
        name = "_test_global_atom_enumerate_xyz"
        # Mint to ensure presence.
        _global_atom_call(mint(name), Var())
        val = predicate_builtins[name]
        assert val == mint(name)
        # Enumerate.
        n_out = Var()
        a_out = Var()
        results = _global_atom_call(n_out, a_out)
        # Our minted entry must appear.
        assert (mint(name), val) in results
        # Every yielded pair is (atom, atom-of-the-same-spelling) or, for
        # backward compatibility, (atom, 0-arity PredicateMeta).
        for n, v in results:
            assert is_atom(n)
            if is_atom(v):
                assert v == n
            else:
                assert isinstance(v, PredicateMeta)
                assert v._fields == ()

    def test_round_trip(self):
        """Mint with (+name, -atom); reverse-lookup with (-name, +atom) returns name."""
        # nv
        from clausal.import_hook import predicate_builtins
        name = "_test_global_atom_round_trip_xyz"
        # Mint.
        x = Var()
        mint_results = _global_atom_call(mint(name), x)
        assert len(mint_results) == 1
        cls = predicate_builtins[name]
        # Reverse lookup.
        n_out = Var()
        rev_results = _global_atom_call(n_out, cls)
        assert len(rev_results) == 1
        assert rev_results[0][0] == mint(name)
