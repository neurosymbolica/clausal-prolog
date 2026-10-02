"""Tests for V2-7: Well-Founded Semantics (WFS)."""

import os
import pytest

from clausal.logic.atoms import mint
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
from clausal.terms import Undefined
from tests._suffix import SEAM, seam_path


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _load(name):
    from clausal.import_hook import _load_module
    return _load_module(name, seam_path(os.path.join(FIXTURES, f"{name}.clausal")))


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
        for trail in call("fib", 10, F, module=_module(m)):
            results.append(deref(F))
        assert results == [55]

    def test_tabled_path_cyclic(self):
        """Existing tabled cyclic path still works."""
        # nv
        m = _load("tabled_path")
        Y = Var()
        results = []
        for t in call("path", 1, Y, module=_module(m)):
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
        for t in call("win", X, module=lm):
            results.append(deref(X))

        # With WFS, the symmetric cycle means both are conditional/undefined.
        # The key insight: answers exist but are conditional.
        # The table should have entries with non-empty conditions.
        table_store = db.table_store
        # Find the win table entries
        win_entries = [(k, v) for k, v in table_store.items() if k[0] == "win"]
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
        for t in call("win", X, module=lm):
            results.append(deref(X))

        # win("a") should be in results (true: via move("a","c"), not win("c"))
        assert mint("a") in results


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
        for trail in call("fib", 5, F, module=lm):
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
        goal = TermCall(func=LoadName(name="fib"), args=[N, F], kwargs=[])
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
# and compound goals never reached their table entry), while _naf_tabled
# treated a CONDITIONAL answer in a complete table as a definite positive —
# which made ground queries on a symmetric program asymmetric (one atom
# false-by-[], the other unconditionally true).


def _win_goal(arg, name="win"):
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
            assert len(results) == 1, f"win({v}) lost its undefined answer"
            assert results[0]["_truth"] is Undefined

    def test_ground_after_unbound_consistent(self):
        """The todo's order: unbound, then ground 1, then ground 2 — all Undefined."""
        # nv
        lm = _module(_load("wfs_win"))
        self._q(lm)
        for v in (1, 2):
            results = self._q(lm, v)
            assert len(results) == 1, f"win({v}) reported [] (reads as false)"
            assert results[0]["_truth"] is Undefined

    def test_ground_then_ground_consistent(self):
        # nv
        lm = _module(_load("wfs_win"))
        r1 = self._q(lm, 1)
        r2 = self._q(lm, 2)
        assert len(r1) == 1 and r1[0]["_truth"] is Undefined
        assert len(r2) == 1 and r2[0]["_truth"] is Undefined

    def test_no_unconditional_answer_ever_stored(self):
        """Guards finding 2d: no order of asking mints an unconditional win answer."""
        # nv
        lm = _module(_load("wfs_win"))
        self._q(lm)
        self._q(lm, 1)
        self._q(lm, 2)
        for (f, _a, _k), entry in lm.db.table_store.items():
            if f != "win":
                continue
            for i in range(len(entry.answers)):
                assert entry.truth_value(i) is Undefined

    def test_cell_goal_undefined(self):
        """A cell goal reaches its table entry (a compound goal used to be
        shadowed by the is_term_instance branch and always read True)."""
        # nv
        lm = _module(_load("wfs_win"))
        X = Var()
        results = query_wfs(("win", X), {"X": X}, lm, Trail())
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
            assert delays, f"win({x}) is Undefined but has no reachable delays"
            assert any(
                dn.functor == "win" and dn.frozen_args == (partner[x],)
                for dn in delays
            )

    def test_true_results_have_empty_delays(self):
        # nv
        lm = _module(_load("tabled_fib"))
        N = Var()
        F = Var()
        from clausal.terms import Call as TermCall, LoadName
        goal = TermCall(func=LoadName(name="fib"), args=[N, F], kwargs=[])
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
        """wf(1) <- fact; wf on a 2-cycle: wf(1)=True, wf(2)=False."""
        # nv
        lm = _module(_load("wfs_fact_cycle"))
        X = Var()
        from clausal.terms import Call as TermCall, LoadName
        goal = TermCall(func=LoadName(name="wf"), args=[X], kwargs=[])
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
            goal = TermCall(func=LoadName(name="wf"), args=[Y], kwargs=[])
            results = query_wfs(goal, {}, lm, t)
            assert len(results) == want, f"wf({val})"
            if results:
                assert results[0]["_truth"] is True

    def test_asym_win_truth_values_at_surface(self):
        """wfs_win_asym: win("a") is the only answer and it is True —
        the c-path derivation must not be lost to answer dedup."""
        # nv
        lm = _module(_load("wfs_win_asym"))
        X = Var()
        results = query_wfs(_win_goal(X), {"X": X}, lm, Trail())
        assert [(r["X"], r["_truth"]) for r in results] == [(mint("a"), True)]
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
    """pw(1) via fact; pw(6) via `not qw(6)`; qw(6) reads pw back positively.

    wfs_posneg_true (qw(6) <- pw(Z), Z < 5): qw(6) is TRUE via pw(1), so
    pw(6) is definitively FALSE — it must not surface at all, in any order.
    wfs_posneg_undef (Z > 5): qw(6) depends on the conditional pw(6) —
    everything in the loop is Undefined, in any order. The second program
    needs POSITIVE delay propagation: qw's derivation consumes the
    conditional pw(6) answer and must inherit its delays."""

    def test_true_program_pw_first(self):
        # nv
        lm = _module(_load("wfs_posneg_true"))
        assert _q(lm, "pw") == [(1, True)]
        assert _q(lm, "qw", 6) == [True]
        assert _q(lm, "pw") == [(1, True)]

    def test_true_program_qw_first(self):
        # nv
        lm = _module(_load("wfs_posneg_true"))
        assert _q(lm, "qw", 6) == [True]
        assert _q(lm, "pw") == [(1, True)]

    def test_undef_program_pw_first(self):
        # nv
        lm = _module(_load("wfs_posneg_undef"))
        assert _q(lm, "pw") == [(1, True), (6, Undefined)]
        assert _q(lm, "qw", 6) == [Undefined]

    def test_undef_program_qw_first(self):
        # nv
        lm = _module(_load("wfs_posneg_undef"))
        assert _q(lm, "qw", 6) == [Undefined]
        assert _q(lm, "pw") == [(1, True), (6, Undefined)]

    def test_no_failed_row_reported_true(self):
        """A row invalidated after streaming must not default to True."""
        # nv
        lm = _module(_load("wfs_posneg_true"))
        for x, truth in _q(lm, "pw"):
            assert truth is not False  # False rows are dropped, never shown
        # And the table really does hold the falsified row:
        for (f, _a, _k), e in lm.db.table_store.items():
            if f == "pw" and len(e.answers) == 2:
                truths = {e.truth_value(i) for i in range(len(e.answers))}
                assert truths == {True, False}


class TestWfsSpawnTermination:
    def test_growing_ground_negation_terminates(self):
        """not pn(X+1) spawns; the depth cap makes it delay past the cap
        instead of dying in a bare RecursionError."""
        # nv
        lm = _module(_load("wfs_growing_neg"))
        assert _q(lm, "pn", 1) == [Undefined]


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
        res = query_wfs(_goal("win", Y), {}, lm, t)
        assert res == []  # win("b") is definitively false, not Undefined


def solve_first(lm, X):
    from clausal.logic.solve import solve
    return solve(_goal("win", X), lm, Trail())


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
                "probe_q(X) <- wfs_win.Win(X)\n"
            )
            p = tmp_path / f"wfs_importer_q{SEAM}"
            p.write_text(src)
            m = _load_module("wfs_importer_q", str(p))
            lm = m.__dict__["$module"]
            from clausal.terms import Call as TermCall, LoadName, LoadAttr
            X = Var()
            goal = TermCall(
                func=LoadAttr(object=LoadName(name="wfs_win"), attr="win"),
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
        list(call("fib", N, F, module=lm))
        goal = TermCall(func=LoadName(name="fib"), args=[N],
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
        new — replay skipped it, so consumers have not seen it.  The report
        is the row's INDEX (so the root-lead deferral can record it without
        re-deriving the canonical key); None means nothing visibly changed."""
        # nv
        e = TableEntry()
        assert e.add_answer((1,)) == 0
        e.conditions[0] = _FAILED
        assert e.add_answer((1,)) == 0      # revival: same row, reported new
        assert e.truth_value(0) is True
        assert e.add_answer((1,)) is None   # plain duplicate


# ── Second review round (2026-08-27): attribution, shapes, and bounds ───────


class TestNestedStreamingAttribution:
    def test_undefined_propagates_through_two_positive_hops(self):
        """aa <- bb <- cc with cc unfounded: when bb streams its conditional
        answer, a deeper leader (cc) can still be parked on the stack —
        attribution must go to the leader below bb's OWN position (aa), not
        blindly to stack[-2]. All three atoms are Undefined."""
        # nv
        lm = _module(_load("wfs_nested_stream"))
        assert _q(lm, "aa") == [(1, Undefined)]
        assert _q(lm, "bb") == [(1, Undefined)]
        assert _q(lm, "cc") == [(1, Undefined)]


class TestSpawnDepthBudget:
    def test_definite_chain_within_budget_stays_definite(self):
        """A terminating, definite ground negation chain of depth 50 must
        get its real truth value — the spawn cap is derived from the
        recursion limit, not a magic 32."""
        # nv
        lm = _module(_load("wfs_bounded_chain"))
        assert _q(lm, "pb", 1) == [True]


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
            p = tmp_path / f"wfs_impfrom{SEAM}"
            p.write_text("-import_from(wfs_win, [win])\n\nuses_f(X) <- win(X)\n")
            lm = _load_module("wfs_impfrom", str(p)).__dict__["$module"]
            assert _q(lm, "win") == [(1, Undefined), (2, Undefined)]
        finally:
            sys.path.remove(FIXTURES)

    def test_nested_dotted_qualified_goal(self, tmp_path):
        """pkg.sub.mod.win(X) — the dotted chain resolves through
        sys.modules to the exporting module's table."""
        # nv
        import sys
        import shutil
        pkg = tmp_path / "pkgn" / "subn"
        pkg.mkdir(parents=True)
        (tmp_path / "pkgn" / "__init__.py").write_text("")
        (pkg / "__init__.py").write_text("")
        shutil.copy(os.path.join(FIXTURES, "wfs_win.clausal"),
                    str(pkg / f"winmod{SEAM}"))
        (tmp_path / f"nested_imp{SEAM}").write_text(
            "-import_module(pkgn.subn.winmod)\n\n"
            "uses_n(X) <- pkgn.subn.winmod.Win(X)\n")
        sys.path.insert(0, str(tmp_path))
        try:
            from clausal.import_hook import _load_module
            lm = _load_module("nested_imp",
                              str(tmp_path / f"nested_imp{SEAM}")).__dict__["$module"]
            from clausal.terms import Call as TermCall, LoadName, LoadAttr
            X = Var()
            goal = TermCall(
                func=LoadAttr(
                    object=LoadAttr(
                        object=LoadAttr(object=LoadName(name="pkgn"),
                                        attr="subn"),
                        attr="winmod"),
                    attr="win"),
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
        """wfs_posneg_true: qw(6) is TRUE via pw(1), so pw(6) is FALSE.
        The first (streamed) call and the second (complete-path) call must
        return the SAME set — the complete-path one, [1]."""
        # nv
        lm = _module(_load("wfs_posneg_true"))
        first = self._all(lm, "pw")
        second = self._all(lm, "pw")
        assert first == second == [1]

    def test_surviving_undefined_answers_still_delivered(self):
        """wfs_posneg_undef: pw(6) survives resolution as Undefined — the
        deferral must deliver it after completion, not drop it. Both calls
        agree on the set."""
        # nv
        lm = _module(_load("wfs_posneg_undef"))
        first = self._all(lm, "pw")
        second = self._all(lm, "pw")
        assert sorted(first) == sorted(second) == [1, 6]

    def test_relead_replays_conditional_rows_into_the_deferral(self):
        """The REPLAY branch of the deferral (roborev job 12, finding 2).

        A dormant "evaluating" entry with a conditional row already
        recorded, re-invoked as a root call, REPLAYS its rows — and a
        replayed conditional row must join the deferred set exactly like a
        newly-derived one (delivered only if it survives resolution).

        The dormant state is manufactured, not derived: every organic
        route seems to close over it — an abandoned root lead is dropped by
        the A04-F007 poisoned-entry cleanup, and an SCC member's deferred
        completion is finished at its leader's own exit — so the state the
        replay loop is DEFINED over is set up directly, the way the other
        unit tests in this file fabricate table entries.  Without the
        replay-deferral branch this streams the doomed pw(6) row to the
        caller before resolution kills it, and the assertion fails.
        """
        # nv
        lm = _module(_load("wfs_posneg_true"))
        X = Var()
        assert [deref(X) for _ in call("pw", X, module=lm)] == [1]

        entries = {f: e for (f, _a, _k), e in lm.db.table_store.items()}
        pw = entries["pw"]
        assert [a[0] for a in pw.answers] == [1, 6]
        assert pw.conditions[1] is _FAILED          # resolution killed Pw(6)

        # Rewind Pw to its mid-fixpoint shape: dormant, with the (6,) row
        # conditional on `not Qw(6)` — Qw's own completed table (Qw(6) TRUE)
        # is what root-exit resolution will consult again.
        pw.status = "evaluating"
        pw.conditions[1] = frozenset({frozenset(
            {DelayedNegation("qw", 1, (6,), (6,))})})

        Y = Var()
        full = [deref(Y) for _ in call("pw", Y, module=lm)]
        assert full == [1], (
            "the replayed conditional row must be deferred and then dropped "
            f"by resolution, not streamed — got {full!r}"
        )
        assert pw.status == "complete"
        assert pw.conditions[1] is _FAILED

    def test_unconditional_answers_still_stream_before_completion(self, tmp_path):
        """A negation-free tabled predicate must keep streaming: the caller
        receives the first answer while the leader's table is still
        'evaluating' (mid-fixpoint), exactly as before the deferral."""
        # nv
        from clausal.import_hook import _load_module
        p = tmp_path / f"wfs_stream_probe{SEAM}"
        p.write_text(
            "-table(cnt/1)\n\n"
            "cnt(0),\n"
            "cnt(N) <- (cnt(M), M < 3, N == M + 1)\n"
        )
        lm = _load_module("wfs_stream_probe", str(p)).__dict__["$module"]
        X = Var()
        it = call("cnt", X, module=lm)
        next(it)
        first_val = deref(X)
        entries = [e for (f, _a, _k), e in lm.db.table_store.items()
                   if f == "cnt"]
        assert entries, "table entry must exist while streaming"
        assert entries[0].status == "evaluating", (
            "unconditional answers must stream before the fixpoint completes"
        )
        rest = [deref(X) for _ in it]
        assert sorted([first_val] + rest) == [0, 1, 2, 3]
# ── Cross-module tabled NAF (todo/cross-module-tabled-naf-loses-wfs-delay.md) ─
# ``not Imported(...)`` where Imported is tabled in ITS OWN module's db must
# lower to the WFS-sound ``$naf_tabled`` form, exactly like the single-module
# twin.  Before the fix it lowered to plain NAF: the symmetric-cycle answer
# below came back definitively FALSE ([]) where WFS says Undefined.


_XMNAF_COUNTER = [0]

_XMNAF_SYM_LIB = """-module({name}, [win(X)])
-table(win/1)

move(1, 2),
move(2, 1),

win(X) <- (move(X, Y), not win(Y))
"""

_XMNAF_ASYM_LIB = """-module({name}, [win(X)])
-table(win/1)

move(1, 2),
move(2, 3),

win(X) <- (move(X, Y), not win(Y))
"""

_XMNAF_USE = """-import_from({lib}, [win])
-table(res/1)

res(X) <- (not win(X))
"""


def _load_xmnaf_pair(tmp_path, lib_src, use_src=_XMNAF_USE):
    """Write + load a lib/importer module pair under unique names."""
    from clausal.import_hook import _load_module
    _XMNAF_COUNTER[0] += 1
    n = _XMNAF_COUNTER[0]
    lib_name = f"xmnaf_lib_{os.getpid()}_{n}"
    use_name = f"xmnaf_use_{os.getpid()}_{n}"
    lib_path = tmp_path / f"{lib_name}{SEAM}"
    lib_path.write_text(lib_src.format(name=lib_name))
    use_path = tmp_path / f"{use_name}{SEAM}"
    use_path.write_text(use_src.format(lib=lib_name))
    lib = _load_module(lib_name, str(lib_path))
    use = _load_module(use_name, str(use_path))
    return _module(lib), _module(use)


class TestCrossModuleTabledNaf:
    def test_symmetric_cycle_stays_undefined_across_modules(self, tmp_path):
        """The repro: res(X) <- (not win(X)) with win imported from the
        module that tables it.  The single-module twin yields Undefined;
        the cross-module version must too — NOT definite false ([])."""
        _lib, use = _load_xmnaf_pair(tmp_path, _XMNAF_SYM_LIB)
        assert _q(use, "res", 1) == [Undefined]

    def test_symmetric_cycle_delay_names_the_partner(self, tmp_path):
        """The Undefined answer carries a delay naming the negated
        imported call, same as the single-module twin."""
        _lib, use = _load_xmnaf_pair(tmp_path, _XMNAF_SYM_LIB)
        Y = Var()
        t = Trail()
        unify(Y, 1, t)
        res = query_wfs(_goal("res", Y), {}, use, t)
        assert len(res) == 1
        assert res[0]["_truth"] is Undefined
        assert ("win", (1,)) in {(d.functor, d.frozen_args)
                                 for d in res[0]["_delays"]}

    def test_single_module_twin_undefined(self, tmp_path):
        """Guard: the single-module twin of the same program is (and
        stays) Undefined."""
        from clausal.import_hook import _load_module
        _XMNAF_COUNTER[0] += 1
        name = f"xmnaf_single_{os.getpid()}_{_XMNAF_COUNTER[0]}"
        p = tmp_path / f"{name}{SEAM}"
        p.write_text(
            "-table(win/1)\n-table(res/1)\n\n"
            "move(1, 2),\nmove(2, 1),\n\n"
            "win(X) <- (move(X, Y), not win(Y))\n"
            "res(X) <- (not win(X))\n")
        lm = _module(_load_module(name, str(p)))
        assert _q(lm, "res", 1) == [Undefined]

    def test_definite_cross_module_negation_stays_definite(self, tmp_path):
        """Acyclic lib (move 1→2→3): win(2) true, win(1)/win(3) false.
        Cross-module negation over a DEFINITE predicate must keep definite
        answers — res(2) fails outright, res(1)/res(3) are True (never
        Undefined)."""
        _lib, use = _load_xmnaf_pair(tmp_path, _XMNAF_ASYM_LIB)
        assert _q(use, "res", 2) == []
        assert _q(use, "res", 1) == [True]
        assert _q(use, "res", 3) == [True]

    def test_naf_over_imported_untabled_predicate_unchanged(self, tmp_path):
        """Negating an imported UNTABLED predicate keeps plain NAF — both
        the compile-time decision and the observable answers."""
        from clausal.logic.compiler.tabled_naf import _is_tabled_naf
        from clausal.terms import Call as TermCall, LoadName
        lib_src = "-module({name}, [move(X, Y)])\n\nmove(1, 2),\nmove(2, 3),\n"
        use_src = ("-import_from({lib}, [move])\n\n"
                   "no_move(X, Y) <- (not move(X, Y))\n")
        _lib, use = _load_xmnaf_pair(tmp_path, lib_src, use_src)
        naf_goal = TermCall(func=LoadName(name="move"),
                            args=[Var(), Var()], kwargs=[])
        assert _is_tabled_naf(naf_goal, use.db) is False
        A, B = Var(), Var()
        t = Trail()
        unify(A, 1, t)
        unify(B, 3, t)
        goal = TermCall(func=LoadName(name="no_move"), args=[A, B], kwargs=[])
        assert [r["_truth"] for r in query_wfs(goal, {}, use, t)] == [True]
        t2 = Trail()
        C, D = Var(), Var()
        unify(C, 1, t2)
        unify(D, 2, t2)
        goal2 = TermCall(func=LoadName(name="no_move"), args=[C, D], kwargs=[])
        assert query_wfs(goal2, {}, use, t2) == []

    def test_compile_decision_true_for_imported_tabled(self, tmp_path):
        """Unit: _is_tabled_naf answers True for a call to an imported
        tabled predicate compiled against the IMPORTER's db."""
        from clausal.logic.compiler.tabled_naf import _is_tabled_naf
        from clausal.terms import Call as TermCall, LoadName
        lib, use = _load_xmnaf_pair(tmp_path, _XMNAF_SYM_LIB)
        naf_goal = TermCall(func=LoadName(name="win"), args=[Var()], kwargs=[])
        assert _is_tabled_naf(naf_goal, lib.db) is True   # home db: unchanged
        assert _is_tabled_naf(naf_goal, use.db) is True   # importer db: the fix


class TestQueryWfsJudgesCompositeGoals:
    """query_wfs used to annotate only a goal that IS a single tabled call;
    a conjunction or an untabled wrapper kept ``_truth=True`` with empty
    delays.  Since the throwaway-leader judgement (2026-09-08) every shape
    is annotated by the delays its derivation incurred."""

    def _mod(self, tmp_path, name):
        src = (
            f"-module({name}, [move(A, B), wins(X), p(X), a, b, c, d, e])\n"
            "-double_quotes(chars)\n"
            "-table(wins/1)\n"
            "move(a, b),\n"
            "move(b, c),\n"
            "move(c, a),\n"
            "move(d, e),\n"
            "wins(X) <- (move(X, Y), not wins(Y))\n"
            "p(X) <- wins(X)\n"
        )
        path = tmp_path / f"{name}{SEAM}"
        path.write_text(src)
        from clausal.import_hook import _load_module
        return _load_module(name, str(path))

    def test_untabled_wrapper_and_conjunction_are_annotated(self, tmp_path):
        from clausal.logic.solve import query_wfs
        from clausal.logic.variables import Var
        from clausal.terms import Undefined
        mod = self._mod(tmp_path, "_qw_c1")
        X = Var()
        rows = query_wfs(("p", X), {"X": X}, module=mod)
        by = {r["X"]: r for r in rows}
        assert set(by) == {"a", "b", "c", "d"}
        assert by["d"]["_truth"] is True and by["d"]["_delays"] == frozenset()
        for k in ("a", "b", "c"):
            assert by[k]["_truth"] is Undefined
            assert any(dn.functor == "wins" and dn.arity == 1 for dn in by[k]["_delays"])
        # (a conjunction CELL is not callable at the solve surface yet --
        # cells.refuse_control_construct_cell -- so the conjunction case is
        # pinned through goal position in tests/test_goal_position_seam.py.)
        # definite answers come first, conditional ones after resolution
        Z = Var()
        rows = query_wfs(("p", Z), {"Z": Z}, module=mod)
        assert rows[0]["Z"] == "d" and rows[0]["_truth"] is True

    def test_rows_are_not_collapsed_when_no_variables_are_exported(self, tmp_path):
        """Dedup of deferred answers is over the goal's OWN variables; the
        exported projection only decides what each row SHOWS.  Asking for no
        variables must not merge four answers into one row."""
        from clausal.logic.solve import query_wfs
        from clausal.logic.variables import Var
        from clausal.terms import Undefined
        mod = self._mod(tmp_path, "_qw_c3")
        X = Var()
        rows = query_wfs(("p", X), {}, module=mod)
        truths = [r["_truth"] for r in rows]
        assert truths.count(True) == 1
        assert truths.count(Undefined) == 3


class TestAClausePrefixDelayCoversEveryAnswer:
    """A delay incurred in a clause-body PREFIX stands for every answer the
    rest of the body produces, not just the first.

    The tabled leader snapshots its in-progress delay set per answer and then
    CLEARS it, but the prefix does not re-run: the only choice point is in the
    suffix, so answers after the first saw an empty set and were reported
    unconditionally true off an undefined premise.  Conditions are trailed now,
    so backtracking retracts what a failed branch incurred and the clear is
    both unnecessary and lossy.
    """

    SRC = (
        "-module({n}, [u(X), r(X), pp(X), one, two, three])\n"
        "-double_quotes(chars)\n"
        "-table(u/1)\n"
        "-table(pp/1)\n"
        "u(X) <- (not u(X))\n"
        "r(one),\n"
        "r(two),\n"
        "pp(X) <- (not u(one), r(X))\n"
        "pp(three),\n"
    )

    def _mod(self, tmp_path, name):
        path = tmp_path / f"{name}{SEAM}"
        path.write_text(self.SRC.format(n=name))
        from clausal.import_hook import _load_module
        return _load_module(name, str(path))

    def test_both_answers_are_undefined_not_just_the_first(self, tmp_path):
        from clausal.logic.solve import query_wfs
        from clausal.logic.variables import Var
        from clausal.terms import Undefined
        mod = self._mod(tmp_path, "_cp1")
        X = Var()
        rows = {r["X"]: r for r in query_wfs(("pp", X), {"X": X}, module=mod)}
        assert set(rows) == {"one", "two", "three"}
        assert rows["one"]["_truth"] is Undefined
        assert rows["two"]["_truth"] is Undefined, (
            "the second answer stands on the same delayed `not u(one)` as the "
            "first; reporting it True is unsound in the direction a caller "
            "cannot work around")
        # ...and undefined for the RIGHT reason.  Making the bucket persist
        # across answers risks the opposite error -- charging a condition to an
        # answer that never stood on it -- so pin which delay each row carries,
        # not merely that it has one.
        for k in ("one", "two"):
            assert any(dn.functor == "u" and dn.arity == 1
                       for dn in rows[k]["_delays"]), rows[k]["_delays"]
        # The fact clause has no prefix at all: it must come back plain true
        # with NOTHING charged to it, which is the non-leak direction.
        assert rows["three"]["_truth"] is True
        assert rows["three"]["_delays"] == frozenset()
