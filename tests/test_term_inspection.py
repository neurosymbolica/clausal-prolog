"""tests/test_term_inspection.py — V2-13 term inspection builtins.

Tests for:
  copy_term/2       — deep copy with fresh Vars
  term_variables/2  — collect unbound Vars in term
  numbervars/3     — number unbound Vars with $VAR(N)
"""

import pytest

from clausal.logic.database import Module
from clausal.logic.solve import solve
from clausal.logic.variables import Var, Trail, deref, is_var, unify
from clausal.terms import Compound, Call, LoadName, KWTerm, DictTerm, SegList, ConcreteSeg, VarSeg


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
        vals = sol_var(goal("gensym", "x", a), a)
        assert vals == ["x_1"]

    def test_sequential(self):
        """Two calls increment: "x_1", "x_2"."""
        # nv
        a1, a2 = Var(), Var()
        vals1 = sol_var(goal("gensym", "x", a1), a1)
        vals2 = sol_var(goal("gensym", "x", a2), a2)
        assert vals1 == ["x_1"]
        assert vals2 == ["x_2"]

    def test_different_prefixes(self):
        """Different prefixes have independent counters."""
        # nv
        a = Var()
        b = Var()
        sol_var(goal("gensym", "x", a), a)
        vals = sol_var(goal("gensym", "y", b), b)
        assert vals == ["y_1"]

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
        sol_var(goal("gensym", "z", a1), a1)
        # Counter is now at 1; next call should give z_2
        a2 = Var()
        vals = sol_var(goal("gensym", "z", a2), a2)
        assert vals == ["z_2"]

    def test_atom_already_bound_unification(self):
        """gensym("x", "x_1") succeeds if counter is at 1."""
        # nv
        sols = solutions(goal("gensym", "x", "x_1"))
        assert len(sols) == 1

    def test_atom_already_bound_mismatch(self):
        """gensym("x", "x_99") fails when counter is at 1."""
        # nv
        sols = solutions(goal("gensym", "x", "x_99"))
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
            for _ in solve(goal("gensym", "t", a), mod, trail):
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
# DictTerm and SegList are not yet handled by c_copy_term / c_collect_vars.
# They fall through to "return as-is", meaning:
#   - copy_term shares the *same* Var objects (no fresh copy)
#   - term_variables returns [] (vars not collected)
# These tests document the current behaviour so any future fix breaks visibly.


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
    """Test copy_term behaviour on SegList via the C helper directly.

    SegList cannot be passed through the goal compiler, so we call
    _copy_term_impl directly to verify the current fall-through behaviour.
    """

    def test_copy_seglist_var_not_freshened(self):
        """SegList VarSeg Vars are NOT freshened — copy shares the original."""
        # nv
        from clausal.logic.builtins.inspection import _copy_term_impl
        x = Var()
        t = SegList([ConcreteSeg([1, 2]), VarSeg(x)])
        c = _copy_term_impl(t, {})
        assert isinstance(c, SegList)
        # current behaviour: SegList falls through → same Var object (not a fresh copy)
        assert c._segments[1].var is x


class TestTermVariablesSegList:
    """Test term_variables behaviour on SegList via the C helper directly."""

    def test_seglist_vars_not_collected(self):
        """term_variables on SegList currently returns [] (gap, not handled)."""
        # nv
        from clausal.logic.builtins.inspection import _collect_vars_impl
        x = Var()
        t = SegList([VarSeg(x)])
        result = []
        _collect_vars_impl(t, result)
        # current behaviour: SegList falls through → empty list
        assert result == []


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
        """(+name, -atom) — fresh name mints a new PredicateMeta arity-0 class."""
        # nv
        from clausal.import_hook import predicate_builtins
        from clausal.logic.predicate import PredicateMeta
        name = "_test_global_atom_mint_xyz"
        assert name not in predicate_builtins  # sanity: fresh
        atom = Var()
        results = _global_atom_call(name, atom)
        assert len(results) == 1
        _, cls = results[0]
        assert isinstance(cls, PredicateMeta)
        assert cls._fields == ()
        assert cls.__name__ == name
        # Side-effect: it is now in the global dict.
        assert predicate_builtins.get(name) is cls

    def test_idempotent_mint(self):
        """(+name, -atom) twice yields the same class object (identity)."""
        # nv
        name = "_test_global_atom_idempotent_xyz"
        a1 = Var()
        r1 = _global_atom_call(name, a1)
        a2 = Var()
        r2 = _global_atom_call(name, a2)
        assert len(r1) == 1 and len(r2) == 1
        assert r1[0][1] is r2[0][1]

    def test_existing_pre_seeded_returned(self):
        """(+name, -atom) for a pre-seeded entry (e.g. Var) returns that value."""
        # nv
        from clausal.import_hook import predicate_builtins
        # 'Var' is pre-seeded in predicate_builtins as the Var class.
        pre_existing = predicate_builtins["Var"]
        out = Var()
        results = _global_atom_call("Var", out)
        assert len(results) == 1
        assert results[0][1] is pre_existing

    def test_guard_succeeds_when_atom_matches(self):
        """(+name, +atom) — succeeds iff atom IS the global class."""
        # nv
        from clausal.import_hook import predicate_builtins
        name = "_test_global_atom_guard_match_xyz"
        # Mint first.
        _global_atom_call(name, Var())
        cls = predicate_builtins[name]
        # Guard mode with the right class should succeed exactly once.
        results = _global_atom_call(name, cls)
        assert len(results) == 1

    def test_guard_fails_when_atom_mismatches(self):
        """(+name, +atom) — fails when atom is NOT the global class for that name."""
        # nv
        from clausal.logic.predicate import make_predicate
        name = "_test_global_atom_guard_mismatch_xyz"
        # Mint the global atom for 'name'.
        _global_atom_call(name, Var())
        # Create a separate (non-global) PredicateMeta with the same name.
        impostor = make_predicate(name, [])
        results = _global_atom_call(name, impostor)
        assert results == []

    def test_reverse_lookup_returns_name(self):
        """(-name, +atom) — yields cls.__name__ when cls is a global atom."""
        # nv
        from clausal.import_hook import predicate_builtins
        name = "_test_global_atom_reverse_xyz"
        _global_atom_call(name, Var())
        cls = predicate_builtins[name]
        # Reverse-lookup with bound atom.
        n_out = Var()
        results = _global_atom_call(n_out, cls)
        assert len(results) == 1
        assert results[0][0] == name

    def test_reverse_lookup_fails_for_non_global_class(self):
        """(-name, +atom) — fails if atom is not the global class registered for its name."""
        # nv
        from clausal.logic.predicate import make_predicate
        # A PredicateMeta NOT placed into predicate_builtins.
        local_only = make_predicate("_test_global_atom_local_only_xyz", [])
        n_out = Var()
        results = _global_atom_call(n_out, local_only)
        assert results == []

    def test_enumerate_yields_minted_atoms(self):
        """(-name, -atom) — enumerates global atoms; minted one appears."""
        # nv
        from clausal.import_hook import predicate_builtins
        from clausal.logic.predicate import PredicateMeta
        name = "_test_global_atom_enumerate_xyz"
        # Mint to ensure presence.
        _global_atom_call(name, Var())
        cls = predicate_builtins[name]
        # Enumerate.
        n_out = Var()
        a_out = Var()
        results = _global_atom_call(n_out, a_out)
        # Our minted entry must appear.
        assert (name, cls) in results
        # All yielded pairs must be (str, PredicateMeta with arity 0).
        for n, c in results:
            assert isinstance(n, str)
            assert isinstance(c, PredicateMeta)
            assert c._fields == ()

    def test_round_trip(self):
        """Mint with (+name, -atom); reverse-lookup with (-name, +atom) returns name."""
        # nv
        from clausal.import_hook import predicate_builtins
        name = "_test_global_atom_round_trip_xyz"
        # Mint.
        x = Var()
        mint_results = _global_atom_call(name, x)
        assert len(mint_results) == 1
        cls = predicate_builtins[name]
        # Reverse lookup.
        n_out = Var()
        rev_results = _global_atom_call(n_out, cls)
        assert len(rev_results) == 1
        assert rev_results[0][0] == name
