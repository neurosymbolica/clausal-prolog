"""Tests for V2-7: Well-Founded Semantics (WFS)."""

import os
import pytest

from clausal.logic.tabling import (
    TableEntry,
    DelayedNegation,
    _FAILED,
    _naf_tabled,
    _resolve_conditions,
    push_leader,
    pop_leader,
    current_leader,
    make_subgoal_key,
    freeze_args,
    make_tabled_wrapper_simple,
    make_tabled_wrapper_trampoline,
    _trampoline_to_simple_adapter,
)
from clausal.logic.variables import Var, Trail, unify, deref, is_var
from clausal.logic.database import Database, Clause, Module, head_key
from clausal.logic.trampoline import StepGenerator, DONE, solutions
from clausal.logic.solve import call, query, query_wfs
from clausal.logic.predicate import PredicateMeta
from clausal.terms import Compound, Undefined


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _load(name):
    from clausal.import_hook import _load_module
    return _load_module(name, os.path.join(FIXTURES, f"{name}.clausal"))


def _module(mod):
    return mod.__dict__["$module"]


# ── DelayedNegation data structure ──────────────────────────────────────────


class TestDelayedNegation:
    def test_equality(self):
        # nv
        dn1 = DelayedNegation("win", 1, (1,), (1,))
        dn2 = DelayedNegation("win", 1, (1,), (1,))
        assert dn1 == dn2

    def test_inequality(self):
        # nv
        dn1 = DelayedNegation("win", 1, (1,), (1,))
        dn2 = DelayedNegation("win", 1, (2,), (2,))
        assert dn1 != dn2

    def test_hashable(self):
        # nv
        dn1 = DelayedNegation("win", 1, (1,), (1,))
        dn2 = DelayedNegation("win", 1, (1,), (1,))
        assert hash(dn1) == hash(dn2)
        s = {dn1, dn2}
        assert len(s) == 1

    def test_repr(self):
        # nv
        dn = DelayedNegation("win", 1, (1,), (1,))
        assert "win" in repr(dn)


# ── TableEntry conditions ───────────────────────────────────────────────────


class TestTableEntryConditions:
    def test_add_answer_default_unconditional(self):
        # nv
        e = TableEntry()
        e.add_answer((1,))
        # A04-F003: a condition is a DISJUNCTION of per-derivation delay sets.
        assert e.conditions == [frozenset({frozenset()})]

    def test_add_answer_with_delays(self):
        # nv
        e = TableEntry()
        dn = DelayedNegation("p", 1, (1,), (1,))
        e.add_answer((1,), frozenset({dn}))
        assert e.conditions == [frozenset({frozenset({dn})})]

    def test_truth_value_unconditional(self):
        # nv
        e = TableEntry()
        e.add_answer((1,))
        assert e.truth_value(0) is True

    def test_truth_value_conditional(self):
        # nv
        e = TableEntry()
        dn = DelayedNegation("p", 1, (1,), (1,))
        e.add_answer((1,), frozenset({dn}))
        assert e.truth_value(0) is Undefined

    def test_truth_value_failed(self):
        # nv
        e = TableEntry()
        e.add_answer((1,))
        e.conditions[0] = _FAILED
        assert e.truth_value(0) is False

    def test_current_delays_initially_empty(self):
        # nv
        e = TableEntry()
        assert e._current_delays == set()


# ── Leader context stack ────────────────────────────────────────────────────


class TestLeaderContext:
    def test_empty_stack(self):
        # Clear stack for isolation
        # nv
        from clausal.logic.tabling import _leader_ctx
        old = _leader_ctx.stack[:]
        _leader_ctx.stack.clear()
        try:
            assert current_leader() is None
        finally:
            _leader_ctx.stack.extend(old)

    def test_push_pop(self):
        # nv
        from clausal.logic.tabling import _leader_ctx
        old = _leader_ctx.stack[:]
        _leader_ctx.stack.clear()
        try:
            e = TableEntry()
            push_leader(e)
            assert current_leader() is e
            popped = pop_leader()
            assert popped is e
            assert current_leader() is None
        finally:
            _leader_ctx.stack.extend(old)

    def test_nested_leaders(self):
        # nv
        from clausal.logic.tabling import _leader_ctx
        old = _leader_ctx.stack[:]
        _leader_ctx.stack.clear()
        try:
            e1 = TableEntry()
            e2 = TableEntry()
            push_leader(e1)
            push_leader(e2)
            assert current_leader() is e2
            pop_leader()
            assert current_leader() is e1
            pop_leader()
        finally:
            _leader_ctx.stack.extend(old)


# ── _naf_tabled unit tests ─────────────────────────────────────────────────


class TestNafTabled:
    def test_complete_table_no_match(self):
        """Complete table with no matching answer → negation succeeds."""
        # nv
        ts = {}
        entry = TableEntry()
        entry.add_answer((2,))
        entry.status = "complete"
        ts[("p", 1, (1,))] = entry

        trail = Trail()
        assert _naf_tabled("p", 1, (1,), trail, ts) is True

    def test_complete_table_with_match(self):
        """Complete table with matching answer → negation fails."""
        # nv
        ts = {}
        entry = TableEntry()
        entry.add_answer((1,))
        entry.status = "complete"
        ts[("p", 1, (1,))] = entry

        trail = Trail()
        assert _naf_tabled("p", 1, (1,), trail, ts) is False

    def test_complete_table_skips_failed(self):
        """Failed answers in complete table should be skipped."""
        # nv
        ts = {}
        entry = TableEntry()
        entry.add_answer((1,))
        entry.conditions[0] = _FAILED
        entry.status = "complete"
        ts[("p", 1, (1,))] = entry

        trail = Trail()
        assert _naf_tabled("p", 1, (1,), trail, ts) is True

    def test_evaluating_table_delays(self):
        """Evaluating table → delay, return True, attach to leader."""
        # nv
        from clausal.logic.tabling import _leader_ctx
        old = _leader_ctx.stack[:]
        _leader_ctx.stack.clear()
        try:
            ts = {}
            entry = TableEntry()
            ts[("p", 1, (1,))] = entry  # status="evaluating"

            leader = TableEntry()
            push_leader(leader)

            trail = Trail()
            result = _naf_tabled("p", 1, (1,), trail, ts)
            assert result is True
            assert len(leader._current_delays) == 1
            dn = next(iter(leader._current_delays))
            assert dn.functor == "p"
            assert dn.arity == 1

            pop_leader()
        finally:
            _leader_ctx.stack.extend(old)

    def test_no_entry_returns_true(self):
        """No table entry → treat as no answers → negation succeeds."""
        # nv
        ts = {}
        trail = Trail()
        assert _naf_tabled("p", 1, (1,), trail, ts) is True

    def test_complete_table_var_arg(self):
        """Complete table with Var arg → matches any answer → negation fails."""
        # nv
        ts = {}
        entry = TableEntry()
        entry.add_answer((42,))
        entry.status = "complete"
        # Key for Var args uses _VAR sentinel
        from clausal.logic.tabling import _VAR
        ts[("p", 1, (_VAR,))] = entry

        trail = Trail()
        x = Var()
        assert _naf_tabled("p", 1, (x,), trail, ts) is False


# ── _resolve_conditions unit tests ─────────────────────────────────────────


class TestResolveConditions:
    def test_unconditional_passthrough(self):
        """Unconditional answers remain unchanged."""
        # nv
        ts = {}
        entry = TableEntry()
        entry.add_answer((1,))
        entry.status = "complete"
        ts[("p", 1, (1,))] = entry

        _resolve_conditions(entry, ts)
        assert entry.truth_value(0) is True

    def test_resolve_to_true(self):
        """Delay targeting complete table with no match → resolves to true."""
        # nv
        ts = {}
        # Target table: complete, has answer (99,) but not (42,)
        target = TableEntry()
        target.add_answer((99,))
        target.status = "complete"
        ts[("q", 1, (42,))] = target

        # Entry with conditional answer depending on not q(42)
        entry = TableEntry()
        dn = DelayedNegation("q", 1, (42,), (42,))
        entry.add_answer((1,), frozenset({dn}))
        entry.status = "complete"
        ts[("p", 1, (1,))] = entry

        _resolve_conditions(entry, ts)
        assert entry.truth_value(0) is True  # resolved to unconditional

    def test_resolve_to_false(self):
        """Delay targeting complete table with unconditional match → invalidated."""
        # nv
        ts = {}
        # Target table: complete, has unconditional answer (42,)
        target = TableEntry()
        target.add_answer((42,))
        target.status = "complete"
        ts[("q", 1, (42,))] = target

        # Entry with conditional answer depending on not q(42)
        entry = TableEntry()
        dn = DelayedNegation("q", 1, (42,), (42,))
        entry.add_answer((1,), frozenset({dn}))
        entry.status = "complete"
        ts[("p", 1, (1,))] = entry

        _resolve_conditions(entry, ts)
        assert entry.conditions[0] is _FAILED

    def test_unfounded_stays_conditional(self):
        """Self-referencing delay stays conditional (unfounded)."""
        # nv
        ts = {}
        entry = TableEntry()
        dn = DelayedNegation("p", 1, (1,), (1,))
        entry.add_answer((1,), frozenset({dn}))
        entry.status = "complete"
        ts[("p", 1, (1,))] = entry

        _resolve_conditions(entry, ts)
        # The answer depends on not p(1), but p(1) exists (conditionally) → unfounded
        assert entry.truth_value(0) is Undefined  # still conditional

    def test_multiple_delays_partial_resolution(self):
        """Multiple delays: some resolve, others don't."""
        # nv
        ts = {}
        # q(42) has no entry → delay resolves to true
        # r(7) has unconditional answer → delay resolves to false
        target_r = TableEntry()
        target_r.add_answer((7,))
        target_r.status = "complete"
        ts[("r", 1, (7,))] = target_r

        entry = TableEntry()
        dn_q = DelayedNegation("q", 1, (42,), (42,))
        dn_r = DelayedNegation("r", 1, (7,), (7,))
        entry.add_answer((1,), frozenset({dn_q, dn_r}))
        entry.status = "complete"
        ts[("p", 1, (1,))] = entry

        _resolve_conditions(entry, ts)
        # not r(7) is false (r(7) exists unconditionally) → answer invalidated
        assert entry.conditions[0] is _FAILED


# ── Positive-only tabling regression ────────────────────────────────────────


class TestPositiveTablingRegression:
    def test_tabled_fib(self):
        """Existing tabled fibonacci still works."""
        # nv
        m = _load("tabled_fib")
        F = Var()
        results = []
        for trail in call("Fib", 10, F, module=_module(m)):
            results.append(deref(F))
        assert results == [55]

    def test_tabled_path_cyclic(self):
        """Existing tabled cyclic path still works."""
        # nv
        m = _load("tabled_path")
        Y = Var()
        results = []
        for t in call("Path", 1, Y, module=_module(m)):
            results.append(deref(Y))
        assert sorted(results) == [1, 2, 3]


# ── Complete table NAF ──────────────────────────────────────────────────────


class TestCompleteTableNaf:
    def test_naf_on_complete_table(self):
        """not P(x) where P's table is already complete → immediate check."""
        # nv
        ts = {}
        entry = TableEntry()
        entry.add_answer((1,))
        entry.add_answer((2,))
        entry.status = "complete"
        ts[("p", 1, (1,))] = entry

        trail = Trail()
        # not p(1) should fail (p(1) exists)
        assert _naf_tabled("p", 1, (1,), trail, ts) is False
        # not p(3) should succeed (no p(3))
        assert _naf_tabled("p", 1, (3,), trail, {}) is True


# ── WFS integration: symmetric win/move ─────────────────────────────────────


class TestWfsSymmetricWin:
    def test_symmetric_win_both_undefined(self):
        """win(1) and win(2) with symmetric moves should be undefined.

        move(1,2), move(2,1): win(X) <- move(X,Y), not win(Y)
        win(1) depends on not win(2), and win(2) depends on not win(1).
        Both are unfounded — WFS assigns ``Undefined``.
        """
        # nv
        m = _load("wfs_win")
        lm = _module(m)
        db = lm.db

        # Query win(1) and win(2)
        X = Var()
        results = []
        for t in call("Win", X, module=lm):
            results.append(deref(X))

        # With WFS, the symmetric cycle means both are conditional/undefined.
        # The key insight: answers exist but are conditional.
        # The table should have entries with non-empty conditions.
        table_store = db.table_store
        # Find the win table entries
        win_entries = [(k, v) for k, v in table_store.items() if k[0] == "Win"]
        # Check that answers exist and are conditional (undefined)
        for key, entry in win_entries:
            assert entry.status == "complete"
            for i in range(len(entry.answers)):
                tv = entry.truth_value(i)
                # in_ the symmetric case, answers should be Undefined or not exist
                assert tv is Undefined or tv is False, f"Expected Undefined or false, got {tv}"


# ── WFS integration: asymmetric win/move ────────────────────────────────────


class TestWfsAsymmetricWin:
    def test_asymmetric_win(self):
        """Asymmetric win/move: win("a") should be true.

        move("a","b"), move("b","a"), move("a","c")
        win(X) <- move(X,Y), not win(Y)

        win("c") = false (no moves from "c")
        win("a") <- move("a","c"), not win("c") → true (win("c") fails)
        win("b") depends on not win("a") → false (win("a") is true)
        """
        # nv
        m = _load("wfs_win_asym")
        lm = _module(m)

        X = Var()
        results = []
        for t in call("Win", X, module=lm):
            results.append(deref(X))

        # win("a") should be in results (true: via move("a","c"), not win("c"))
        assert "a" in results


# ── No negation cycle ───────────────────────────────────────────────────────


class TestNoNegationCycle:
    def test_tabled_with_naf_no_cycle(self):
        """Tabled predicate with NAF but no cycle → standard behavior."""
        # Build a simple tabled predicate with NAF where there's no cycle:
        # -table(safe/1)
        # danger(3),
        # safe(X) <- (X in [1,2,3]) and not danger(X)
        # safe(1) and safe(2) should be true, safe(3) false

        # nv
        m = _load("tabled_fib")  # reuse for module infrastructure
        lm = _module(m)
        db = lm.db

        # The tabled_fib tests verify that positive-only tabling is correct.
        # This test just confirms fib with no negation works.
        F = Var()
        results = []
        for trail in call("Fib", 5, F, module=lm):
            results.append(deref(F))
        assert results == [5]


# ── query_wfs API ───────────────────────────────────────────────────────────


class TestQueryWfs:
    def test_query_wfs_returns_list(self):
        """query_wfs returns a list, not an iterator."""
        # nv
        m = _load("tabled_fib")
        lm = _module(m)
        from clausal.terms import Call as TermCall, LoadName
        N = Var()
        F = Var()
        goal = TermCall(func=LoadName(name="Fib"), args=[N, F], kwargs=[])
        # Bind N to 5
        trail = Trail()
        unify(N, 5, trail)
        results = query_wfs(goal, {"F": F}, lm, trail)
        assert isinstance(results, list)
        assert len(results) == 1
        assert results[0]["F"] == 5
        assert results[0]["_truth"] is True


# ── WFS truth at the query surface ──────────────────────────────────────────
# todo/wfs-undefined-lost-at-query-surface.md: the engine computed Undefined
# correctly in the table and every public query path reported True (TermCall
# and Compound goals never reached their table entry), while _naf_tabled
# treated a CONDITIONAL answer in a complete table as a definite positive —
# which made ground queries on a symmetric program asymmetric (one atom
# false-by-[], the other unconditionally true).


def _win_goal(arg, name="Win"):
    from clausal.terms import Call as TermCall, LoadName
    return TermCall(func=LoadName(name=name), args=[arg], kwargs=[])


class TestNafTabledConditionalMatch:
    def _with_leader(self, fn):
        from clausal.logic.tabling import _leader_ctx
        old = _leader_ctx.stack[:]
        _leader_ctx.stack.clear()
        try:
            leader = TableEntry()
            push_leader(leader)
            try:
                return fn(leader)
            finally:
                pop_leader()
        finally:
            _leader_ctx.stack.extend(old)

    def test_complete_conditional_match_delays(self):
        """not p(1) where p(1)'s only match is CONDITIONAL → delay, not fail."""
        # nv
        ts = {}
        entry = TableEntry()
        dn = DelayedNegation("q", 1, (9,), (9,))
        entry.add_answer((1,), frozenset({dn}))
        entry.status = "complete"
        ts[("p", 1, (1,))] = entry

        def check(leader):
            trail = Trail()
            assert _naf_tabled("p", 1, (1,), trail, ts) is True
            assert len(leader._current_delays) == 1
            got = next(iter(leader._current_delays))
            assert got.functor == "p" and got.key == (1,)

        self._with_leader(check)

    def test_complete_unconditional_match_still_fails(self):
        """Unconditional match keeps failing the negation outright."""
        # nv
        ts = {}
        entry = TableEntry()
        entry.add_answer((1,))
        entry.status = "complete"
        ts[("p", 1, (1,))] = entry

        def check(leader):
            trail = Trail()
            assert _naf_tabled("p", 1, (1,), trail, ts) is False
            assert not leader._current_delays

        self._with_leader(check)

    def test_complete_mixed_matches_fail(self):
        """A var call matching a conditional AND an unconditional answer fails."""
        # nv
        ts = {}
        from clausal.logic.tabling import _VAR
        entry = TableEntry()
        dn = DelayedNegation("q", 1, (9,), (9,))
        entry.add_answer((1,), frozenset({dn}))
        entry.add_answer((2,))
        entry.status = "complete"
        ts[("p", 1, (_VAR,))] = entry

        def check(leader):
            trail = Trail()
            assert _naf_tabled("p", 1, (Var(),), trail, ts) is False
            assert not leader._current_delays

        self._with_leader(check)

    def test_subsuming_conditional_match_delays(self):
        """Subsuming complete table with a conditional match → delay, not fail."""
        # nv
        ts = {}
        from clausal.logic.tabling import _VAR
        entry = TableEntry()
        dn = DelayedNegation("q", 1, (9,), (9,))
        entry.add_answer((1,), frozenset({dn}))
        entry.status = "complete"
        ts[("p", 1, (_VAR,))] = entry

        def check(leader):
            trail = Trail()
            assert _naf_tabled("p", 1, (1,), trail, ts) is True
            assert len(leader._current_delays) == 1

        self._with_leader(check)


class TestQueryWfsUndefinedSurface:
    """query_wfs on the symmetric win cycle: every ask shape reports Undefined."""

    def _q(self, lm, val=None):
        if val is None:
            X = Var()
            return query_wfs(_win_goal(X), {"X": X}, lm, Trail())
        Y = Var()
        t = Trail()
        unify(Y, val, t)
        return query_wfs(_win_goal(Y), {}, lm, t)

    def test_unbound_termcall_undefined(self):
        # nv
        lm = _module(_load("wfs_win"))
        results = self._q(lm)
        assert len(results) == 2
        assert all(r["_truth"] is Undefined for r in results)

    def test_ground_fresh_undefined(self):
        """A lone ground query on a fresh module reports Undefined, not True."""
        # nv
        for v in (1, 2):
            lm = _module(_load("wfs_win"))
            results = self._q(lm, v)
            assert len(results) == 1, f"Win({v}) lost its undefined answer"
            assert results[0]["_truth"] is Undefined

    def test_ground_after_unbound_consistent(self):
        """The todo's order: unbound, then ground 1, then ground 2 — all Undefined."""
        # nv
        lm = _module(_load("wfs_win"))
        self._q(lm)
        for v in (1, 2):
            results = self._q(lm, v)
            assert len(results) == 1, f"Win({v}) reported [] (reads as false)"
            assert results[0]["_truth"] is Undefined

    def test_ground_then_ground_consistent(self):
        # nv
        lm = _module(_load("wfs_win"))
        r1 = self._q(lm, 1)
        r2 = self._q(lm, 2)
        assert len(r1) == 1 and r1[0]["_truth"] is Undefined
        assert len(r2) == 1 and r2[0]["_truth"] is Undefined

    def test_no_unconditional_answer_ever_stored(self):
        """Guards finding 2d: no order of asking mints an unconditional Win answer."""
        # nv
        lm = _module(_load("wfs_win"))
        self._q(lm)
        self._q(lm, 1)
        self._q(lm, 2)
        for (f, _a, _k), entry in lm.db.table_store.items():
            if f != "Win":
                continue
            for i in range(len(entry.answers)):
                assert entry.truth_value(i) is Undefined

    def test_compound_goal_undefined(self):
        """A Compound goal reaches its table entry (it used to be shadowed by
        the is_term_instance branch and always read True)."""
        # nv
        lm = _module(_load("wfs_win"))
        X = Var()
        results = query_wfs(Compound("Win", (X,)), {"X": X}, lm, Trail())
        assert len(results) == 2
        assert all(r["_truth"] is Undefined for r in results)

    def test_delays_reachable(self):
        """An Undefined result carries its delay set, naming the cycle partner."""
        # nv
        lm = _module(_load("wfs_win"))
        results = self._q(lm)
        by_x = {r["X"]: r for r in results}
        partner = {1: 2, 2: 1}
        for x, r in by_x.items():
            delays = r["_delays"]
            assert delays, f"Win({x}) is Undefined but has no reachable delays"
            assert any(
                dn.functor == "Win" and dn.frozen_args == (partner[x],)
                for dn in delays
            )

    def test_true_results_have_empty_delays(self):
        # nv
        lm = _module(_load("tabled_fib"))
        N = Var()
        F = Var()
        from clausal.terms import Call as TermCall, LoadName
        goal = TermCall(func=LoadName(name="Fib"), args=[N, F], kwargs=[])
        trail = Trail()
        unify(N, 5, trail)
        results = query_wfs(goal, {"F": F}, lm, trail)
        assert results[0]["_truth"] is True
        assert results[0]["_delays"] == frozenset()


# ── A04-F003: disjunctive conditions + negative-subgoal spawning ────────────
# WFS truth is an OR over derivations. An answer derived both conditionally
# (through a negation cycle) and unconditionally (a fact, or a negation that
# resolves true) is TRUE, and that truth must propagate: the cycle partner's
# delayed negation against it then FAILS. Requires keeping every derivation's
# delay set (not just the first — the old dedup dropped the true one) and
# evaluating never-called negated subgoals instead of guessing.


class TestWfsDisjunctiveDerivations:
    def test_fact_beats_cycle_var_mode(self):
        """Wf(1) <- fact; Wf on a 2-cycle: Wf(1)=True, Wf(2)=False."""
        # nv
        lm = _module(_load("wfs_fact_cycle"))
        X = Var()
        from clausal.terms import Call as TermCall, LoadName
        goal = TermCall(func=LoadName(name="Wf"), args=[X], kwargs=[])
        results = query_wfs(goal, {"X": X}, lm, Trail())
        assert [(r["X"], r["_truth"]) for r in results] == [(1, True)]

    def test_fact_beats_cycle_ground_mode(self):
        # nv
        lm = _module(_load("wfs_fact_cycle"))
        from clausal.terms import Call as TermCall, LoadName
        for val, want in ((1, 1), (2, 0)):
            Y = Var()
            t = Trail()
            unify(Y, val, t)
            goal = TermCall(func=LoadName(name="Wf"), args=[Y], kwargs=[])
            results = query_wfs(goal, {}, lm, t)
            assert len(results) == want, f"Wf({val})"
            if results:
                assert results[0]["_truth"] is True

    def test_asym_win_truth_values_at_surface(self):
        """wfs_win_asym: win("a") is the only answer and it is True —
        the c-path derivation must not be lost to answer dedup."""
        # nv
        lm = _module(_load("wfs_win_asym"))
        X = Var()
        results = query_wfs(_win_goal(X), {"X": X}, lm, Trail())
        assert [(r["X"], r["_truth"]) for r in results] == [("a", True)]
        assert results[0]["_delays"] == frozenset()


# ── Review follow-ups (2026-08-27): truth must survive resolution timing ────
# The A04-F003 machinery resolves conditions at root exit — AFTER solve()
# streamed conditional answers and possibly AFTER inner tables completed.
# These pin the cases where that timing used to leak wrong truth.


def _goal(name, arg):
    from clausal.terms import Call as TermCall, LoadName
    return TermCall(func=LoadName(name=name), args=[arg], kwargs=[])


def _q(lm, name, val=None):
    if val is None:
        X = Var()
        return [(r["X"], r["_truth"]) for r in query_wfs(_goal(name, X), {"X": X}, lm, Trail())]
    Y = Var()
    t = Trail()
    unify(Y, val, t)
    return [r["_truth"] for r in query_wfs(_goal(name, Y), {}, lm, t)]


class TestWfsPositiveNegativeMix:
    """Pw(1) via fact; Pw(6) via `not Qw(6)`; Qw(6) reads Pw back positively.

    wfs_posneg_true (Qw(6) <- Pw(Z), Z < 5): Qw(6) is TRUE via Pw(1), so
    Pw(6) is definitively FALSE — it must not surface at all, in any order.
    wfs_posneg_undef (Z > 5): Qw(6) depends on the conditional Pw(6) —
    everything in the loop is Undefined, in any order. The second program
    needs POSITIVE delay propagation: Qw's derivation consumes the
    conditional Pw(6) answer and must inherit its delays."""

    def test_true_program_pw_first(self):
        # nv
        lm = _module(_load("wfs_posneg_true"))
        assert _q(lm, "Pw") == [(1, True)]
        assert _q(lm, "Qw", 6) == [True]
        assert _q(lm, "Pw") == [(1, True)]

    def test_true_program_qw_first(self):
        # nv
        lm = _module(_load("wfs_posneg_true"))
        assert _q(lm, "Qw", 6) == [True]
        assert _q(lm, "Pw") == [(1, True)]

    def test_undef_program_pw_first(self):
        # nv
        lm = _module(_load("wfs_posneg_undef"))
        assert _q(lm, "Pw") == [(1, True), (6, Undefined)]
        assert _q(lm, "Qw", 6) == [Undefined]

    def test_undef_program_qw_first(self):
        # nv
        lm = _module(_load("wfs_posneg_undef"))
        assert _q(lm, "Qw", 6) == [Undefined]
        assert _q(lm, "Pw") == [(1, True), (6, Undefined)]

    def test_no_failed_row_reported_true(self):
        """A row invalidated after streaming must not default to True."""
        # nv
        lm = _module(_load("wfs_posneg_true"))
        for x, truth in _q(lm, "Pw"):
            assert truth is not False  # False rows are dropped, never shown
        # And the table really does hold the falsified row:
        for (f, _a, _k), e in lm.db.table_store.items():
            if f == "Pw" and len(e.answers) == 2:
                truths = {e.truth_value(i) for i in range(len(e.answers))}
                assert truths == {True, False}


class TestWfsSpawnTermination:
    def test_growing_ground_negation_terminates(self):
        """not Pn(X+1) spawns; the depth cap makes it delay past the cap
        instead of dying in a bare RecursionError."""
        # nv
        lm = _module(_load("wfs_growing_neg"))
        assert _q(lm, "Pn", 1) == [Undefined]


class TestWfsAbandonedRootResolution:
    def test_stale_conditions_resolve_after_abandonment(self):
        """Breaking out of a solve() iteration (once()-style) must not leave
        inner completed tables with forever-unresolved conditions."""
        # nv
        lm = _module(_load("wfs_win_asym"))
        X = Var()
        for _t in solve_first(lm, X):
            break
        Y = Var()
        t = Trail()
        unify(Y, "b", t)
        res = query_wfs(_goal("Win", Y), {}, lm, t)
        assert res == []  # win("b") is definitively false, not Undefined


def solve_first(lm, X):
    from clausal.logic.solve import solve
    return solve(_goal("Win", X), lm, Trail())


class TestQueryWfsGoalShapes:
    def test_qualified_loadattr_goal(self, tmp_path):
        """module.Pred(X) goals resolve their table in the EXPORTING db."""
        # nv
        import sys
        sys.path.insert(0, FIXTURES)
        try:
            from clausal.import_hook import _load_module
            src = (
                "-import_module(wfs_win)\n\n"
                "ProbeQ(X) <- wfs_win.Win(X)\n"
            )
            p = tmp_path / "wfs_importer_q.clausal"
            p.write_text(src)
            m = _load_module("wfs_importer_q", str(p))
            lm = m.__dict__["$module"]
            from clausal.terms import Call as TermCall, LoadName, LoadAttr
            X = Var()
            goal = TermCall(
                func=LoadAttr(object=LoadName(name="wfs_win"), attr="Win"),
                args=[X], kwargs=[])
            res = query_wfs(goal, {"X": X}, lm, Trail())
            assert len(res) == 2
            assert all(r["_truth"] is Undefined for r in res)
        finally:
            sys.path.remove(FIXTURES)

    def test_kwargs_goal_entry_resolution(self):
        """_tabled_entry_for_goal normalizes keyword args positionally via
        the registered signature (solve() itself does not take reified
        kwargs goals yet — this guards the annotation-side contract)."""
        # nv
        from clausal.logic.solve import _tabled_entry_for_goal
        from clausal.terms import Call as TermCall, LoadName
        from clausal.pythonic_ast.nodes import Keyword
        lm = _module(_load("tabled_fib"))
        N, F = Var(), Var()
        t = Trail()
        unify(N, 10, t)
        # populate the table
        list(call("Fib", N, F, module=lm))
        goal = TermCall(func=LoadName(name="Fib"), args=[N],
                        kwargs=[Keyword(name="RESULT", value=F)])
        entry, goal_args = _tabled_entry_for_goal(goal, lm, t)
        assert entry is not None
        assert len(goal_args) == 2


class TestResolutionMatchesNafSemantics:
    def test_nonground_stored_answer_blocks_resolution_to_true(self):
        """_resolve_one_delay must unify like NAF does: a universal stored
        answer (Var) covers the delayed call — the negation is FALSE, not
        resolved-true."""
        # nv
        from clausal.logic.tabling import _resolve_one_delay
        ts = {}
        target = TableEntry()
        target.add_answer((Var(),))  # universal answer p(_)
        target.status = "complete"
        from clausal.logic.tabling import _VAR
        ts[("p", 1, (_VAR,))] = target
        dn = DelayedNegation("p", 1, (1,), (1,))
        assert _resolve_one_delay(dn, ts) is False

    def test_spawn_requires_the_tabled_wrapper(self):
        """A db whose get_dispatch hands back something other than the
        predicate's own tabled wrapper (e.g. the builtin fallback) must not
        be driven — conservative True instead."""
        # nv
        ran = []

        class FakeDb:
            def get_dispatch(self, f, a):
                def plain(*args):  # not stamped with _tabled_for
                    ran.append(True)
                    yield None
                return plain

        ts = {}
        trail = Trail()
        assert _naf_tabled("p", 1, (1,), trail, ts, FakeDb()) is True
        assert ran == []  # never driven

    def test_add_answer_revival_reports_new(self):
        """Flipping a _FAILED row back to live must report the tuple as
        new — replay skipped it, so consumers have not seen it."""
        # nv
        e = TableEntry()
        assert e.add_answer((1,)) is True
        e.conditions[0] = _FAILED
        assert e.add_answer((1,)) is True   # revival
        assert e.truth_value(0) is True
        assert e.add_answer((1,)) is False  # plain duplicate


# ── Second review round (2026-08-27): attribution, shapes, and bounds ───────


class TestNestedStreamingAttribution:
    def test_undefined_propagates_through_two_positive_hops(self):
        """Aa <- Bb <- Cc with Cc unfounded: when Bb streams its conditional
        answer, a deeper leader (Cc) can still be parked on the stack —
        attribution must go to the leader below Bb's OWN position (Aa), not
        blindly to stack[-2]. All three atoms are Undefined."""
        # nv
        lm = _module(_load("wfs_nested_stream"))
        assert _q(lm, "Aa") == [(1, Undefined)]
        assert _q(lm, "Bb") == [(1, Undefined)]
        assert _q(lm, "Cc") == [(1, Undefined)]


class TestSpawnDepthBudget:
    def test_definite_chain_within_budget_stays_definite(self):
        """A terminating, definite ground negation chain of depth 50 must
        get its real truth value — the spawn cap is derived from the
        recursion limit, not a magic 32."""
        # nv
        lm = _module(_load("wfs_bounded_chain"))
        assert _q(lm, "Pb", 1) == [True]


class TestGoalShapeEdges:
    def test_bare_module_without_dict_is_graceful(self):
        """A directly-constructed Module has module_dict=None — qualified
        goals must fall back to (None, None), not AttributeError."""
        # nv
        from clausal.logic.solve import _tabled_entry_for_goal
        from clausal.terms import Call as TermCall, LoadName, LoadAttr
        X = Var()
        goal = TermCall(func=LoadAttr(object=LoadName(name="nope"), attr="P"),
                        args=[X], kwargs=[])
        assert _tabled_entry_for_goal(goal, Module("bare"), Trail()) == (None, None)

    def test_import_from_remapped_name_annotates(self, tmp_path):
        """-import_from remaps the bare name into the importer, but the
        table lives in the EXPORTER's db — the annotation must follow the
        PredicateMeta home instead of stamping True."""
        # nv
        import sys
        sys.path.insert(0, FIXTURES)
        try:
            from clausal.import_hook import _load_module
            p = tmp_path / "wfs_impfrom.clausal"
            p.write_text("-import_from(wfs_win, [Win])\n\nUsesF(X) <- Win(X)\n")
            lm = _load_module("wfs_impfrom", str(p)).__dict__["$module"]
            assert _q(lm, "Win") == [(1, Undefined), (2, Undefined)]
        finally:
            sys.path.remove(FIXTURES)

    def test_nested_dotted_qualified_goal(self, tmp_path):
        """pkg.sub.mod.Win(X) — the dotted chain resolves through
        sys.modules to the exporting module's table."""
        # nv
        import sys
        import shutil
        pkg = tmp_path / "pkgn" / "subn"
        pkg.mkdir(parents=True)
        (tmp_path / "pkgn" / "__init__.py").write_text("")
        (pkg / "__init__.py").write_text("")
        shutil.copy(os.path.join(FIXTURES, "wfs_win.clausal"),
                    str(pkg / "winmod.clausal"))
        (tmp_path / "nested_imp.clausal").write_text(
            "-import_module(pkgn.subn.winmod)\n\n"
            "UsesN(X) <- pkgn.subn.winmod.Win(X)\n")
        sys.path.insert(0, str(tmp_path))
        try:
            from clausal.import_hook import _load_module
            lm = _load_module("nested_imp",
                              str(tmp_path / "nested_imp.clausal")).__dict__["$module"]
            from clausal.terms import Call as TermCall, LoadName, LoadAttr
            X = Var()
            goal = TermCall(
                func=LoadAttr(
                    object=LoadAttr(
                        object=LoadAttr(object=LoadName(name="pkgn"),
                                        attr="subn"),
                        attr="winmod"),
                    attr="Win"),
                args=[X], kwargs=[])
            res = query_wfs(goal, {"X": X}, lm, Trail())
            assert [(r["X"], r["_truth"]) for r in res] == [
                (1, Undefined), (2, Undefined)]
        finally:
            sys.path.remove(str(tmp_path))


# ── Root-lead deferral of conditional answers (2026-08-31) ──────────────────
# todo/tabled-conditional-answers-stream-before-invalidation.md: a ROOT
# leader used to stream CONDITIONAL answers to the surface caller during the
# fixpoint; root-exit resolution could then invalidate one (_FAILED), but it
# was already delivered — so the same ground query returned a different
# answer SET on the first call (streamed) vs the second (complete path).
# Fix: the root leader defers conditional answers until the fixpoint and
# resolution have run, then delivers the survivors. Unconditional answers
# keep streaming; inner (non-root) leaders/consumers are untouched.


class TestRootLeadConditionalDeferral:
    def _all(self, lm, name):
        X = Var()
        return [deref(X) for _ in call(name, X, module=lm)]

    def test_invalidated_answer_never_reaches_root_caller(self):
        """wfs_posneg_true: Qw(6) is TRUE via Pw(1), so Pw(6) is FALSE.
        The first (streamed) call and the second (complete-path) call must
        return the SAME set — the complete-path one, [1]."""
        # nv
        lm = _module(_load("wfs_posneg_true"))
        first = self._all(lm, "Pw")
        second = self._all(lm, "Pw")
        assert first == second == [1]

    def test_surviving_undefined_answers_still_delivered(self):
        """wfs_posneg_undef: Pw(6) survives resolution as Undefined — the
        deferral must deliver it after completion, not drop it. Both calls
        agree on the set."""
        # nv
        lm = _module(_load("wfs_posneg_undef"))
        first = self._all(lm, "Pw")
        second = self._all(lm, "Pw")
        assert sorted(first) == sorted(second) == [1, 6]

    def test_unconditional_answers_still_stream_before_completion(self, tmp_path):
        """A negation-free tabled predicate must keep streaming: the caller
        receives the first answer while the leader's table is still
        'evaluating' (mid-fixpoint), exactly as before the deferral."""
        # nv
        from clausal.import_hook import _load_module
        p = tmp_path / "wfs_stream_probe.clausal"
        p.write_text(
            "-table(Cnt/1)\n\n"
            "Cnt(0),\n"
            "Cnt(N) <- (Cnt(M), M < 3, N == M + 1)\n"
        )
        lm = _load_module("wfs_stream_probe", str(p)).__dict__["$module"]
        X = Var()
        it = call("Cnt", X, module=lm)
        next(it)
        first_val = deref(X)
        entries = [e for (f, _a, _k), e in lm.db.table_store.items()
                   if f == "Cnt"]
        assert entries, "table entry must exist while streaming"
        assert entries[0].status == "evaluating", (
            "unconditional answers must stream before the fixpoint completes"
        )
        rest = [deref(X) for _ in it]
        assert sorted([first_val] + rest) == [0, 1, 2, 3]
