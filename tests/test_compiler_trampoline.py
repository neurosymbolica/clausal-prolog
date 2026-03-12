"""Tests for compile_predicate_trampoline — stack-safe tuple-protocol compilation.

The trampoline execution model:
  - Every compiled predicate is a generator wrapped by ``StepGenerator``.
    ``StepGenerator`` passes itself as ``this_generator`` — no bootstrap needed.
  - At each solution: ``yield (parent, None)`` — suspends until parent
    resumes for more solutions.
  - When all clauses exhausted: ``yield (parent, DONE)`` — signals search end.
  - Sub-predicate calls use ``_st = (yield (_gen, None))`` in a while
    loop so Python call depth does not grow with recursion.

Driver contract
---------------
Create ``StepGenerator(dispatch_fn, None, *args)`` to drive a trampoline
predicate.  The search trampoline then interprets:
  - ``(None, None)``  → solution found; snapshot, then resume for more
  - ``(None, DONE)``  → search exhausted; stop
  - ``(child, v)``    → intermediate step; route through child and continue
"""

from __future__ import annotations

import dataclasses
import pytest

from clausal.logic.compiler import (
    DONE,
    compile_body_trampoline,
    compile_goal_trampoline,
    compile_predicate_trampoline,
)
from clausal.logic.database import Clause, Database
from clausal.logic.trampoline import StepGenerator
from clausal.logic.variables import Var, Trail, deref, unify
from clausal.terms import (
    And, Or, Not,
    Unify as Is, Evaluate, StructuralEq, StructuralNeq, Lt, Gt,
    In, NotIn,
    Call, LoadName,
    Compound,
    Add,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────


def fresh_trail() -> Trail:
    return Trail()


@dataclasses.dataclass
class point:
    _x: object = None
    _y: object = None


@dataclasses.dataclass
class pair:
    left: object = None
    right: object = None


# ── Search trampoline ──────────────────────────────────────────────────────────
#
# Drive a trampoline-compiled predicate with parent=None.
#
# Semantics of tuples from the predicate's perspective:
#   (None, None)   — predicate found a solution; pred is suspended (bindings active)
#   (None, DONE)   — predicate exhausted all clauses
#   (child, v)     — predicate delegated to a sub-predicate; route and continue
#
# Because the predicate is suspended at the yield point when (None, None) is
# returned, callers can safely call deref() on Var arguments to snapshot bindings
# before resuming.


def _search_trampoline(dispatch_fn, args, snapshot_fn):
    """Drive trampoline predicate and collect per-solution snapshots.

    ``args`` must NOT include the ``parent`` arg; that is supplied as ``None``
    internally.  ``snapshot_fn`` is called while pred is suspended (bindings live).
    """
    snapshots = []
    root = StepGenerator(dispatch_fn, None, *args)
    gen, value = root.send(None)

    while True:
        if gen is None:
            if value is DONE:
                break
            # Solution: generator is suspended, bindings live
            snapshots.append(snapshot_fn())
            gen, value = root.send(None)
        else:
            gen, value = gen.send(value)

    return snapshots


def _count_solutions(dispatch_fn, *args) -> int:
    return len(_search_trampoline(dispatch_fn, args, lambda: None))


def _snap(dispatch_fn, snapshot_fn, *args) -> list:
    return _search_trampoline(dispatch_fn, args, snapshot_fn)


# ── Helpers ────────────────────────────────────────────────────────────────────


def make_pred(functor, arity, clauses_data):
    """Build a Database with a trampoline-compiled predicate.

    ``clauses_data`` is a list of ``(head, body_goals)`` pairs.
    Returns ``(db, dispatch_fn)``.
    """
    db = Database()
    for head, body in clauses_data:
        db.assertz(Clause(head=head, body=body))
    fn = compile_predicate_trampoline(functor, arity, db.clauses_for(functor, arity), db)
    return db, fn


# ── Unit tests: generated structure ───────────────────────────────────────────


class TestCompileBodyTrampolineStructure:
    """compile_body_trampoline returns correct AST statement list."""

    def test_empty_body_yields_step_parent(self):
        """Empty body (fact) → single yield Step(parent, None)."""
        import ast
        db = Database()
        vc: dict = {}
        stmts = compile_body_trampoline([], db, vc, "trail")
        assert len(stmts) == 1
        stmt = stmts[0]
        assert isinstance(stmt, ast.Expr)
        assert isinstance(stmt.value, ast.Yield)

    def test_single_is_goal_wraps_step_parent(self):
        """Is(left=x, right=1) body → mark + if unify: [yield Step(parent, None)] + undo."""
        import ast
        db = Database()
        x = Var()
        vc: dict = {x._id: "_vx"}  # pre-register so no pre-allocation stmts
        stmts = compile_body_trampoline([Is(left=x, right=1)], db, vc, "trail")
        assert len(stmts) == 3  # mark, if, undo

    def test_two_is_goals_nest_correctly(self):
        """Two Is goals produce nested structure: outer wraps inner."""
        import ast
        db = Database()
        x, y = Var(), Var()
        vc: dict = {x._id: "_vx", y._id: "_vy"}  # pre-register so no pre-allocation stmts
        stmts = compile_body_trampoline([Is(left=x, right=1), Is(left=y, right=2)], db, vc, "trail")
        assert len(stmts) == 3  # mark, if, undo (outer Is wraps inner)


class TestCompileGoalTrampolineCallStructure:
    """compile_goal_trampoline generates while-loop pattern for Call nodes."""

    def test_call_generates_three_stmts(self):
        """Call to a predicate → gen_assign + step_assign + While."""
        import ast
        db = Database()
        db.assertz(Clause(head=Compound("foo", (1,)), body=[]))
        x = Var()
        vc = {x._id: "_v1"}
        goal = Call(func=LoadName(name="foo"), args=[x], kwargs=[])
        k_leaf = []  # placeholder
        stmts = compile_goal_trampoline(goal, db, vc, "trail", k_leaf)
        assert len(stmts) == 3
        assert isinstance(stmts[0], ast.Assign)   # _gen_N = dispatch(...)
        assert isinstance(stmts[1], ast.Assign)   # _st_N = (yield Step(...))
        assert isinstance(stmts[2], ast.While)    # while _st_N is not _DONE:

    def test_while_body_ends_with_step_assign(self):
        """The While body ends with _st = (yield Step(gen, None)) — ask for more."""
        import ast
        db = Database()
        db.assertz(Clause(head=Compound("bar", (42,)), body=[]))
        x = Var()
        vc = {x._id: "_vX"}
        goal = Call(func=LoadName(name="bar"), args=[x], kwargs=[])
        stmts = compile_goal_trampoline(goal, db, vc, "trail", [])
        while_node = stmts[2]
        last = while_node.body[-1]
        assert isinstance(last, ast.Assign)
        assert isinstance(last.value, ast.Yield)


# ── Integration: facts ─────────────────────────────────────────────────────────


class TestTrampolineIntegrationFacts:

    def test_no_clauses_zero_solutions(self):
        db = Database()
        fn = compile_predicate_trampoline("empty", 1, [], db)
        trail = fresh_trail()
        assert _count_solutions(fn, 42, trail) == 0

    def test_single_fact_matches(self):
        _, fn = make_pred("foo", 1, [(Compound("foo", (1,)), [])])
        trail = fresh_trail()
        assert _count_solutions(fn, 1, trail) == 1

    def test_single_fact_no_match(self):
        _, fn = make_pred("foo", 1, [(Compound("foo", (1,)), [])])
        trail = fresh_trail()
        assert _count_solutions(fn, 2, trail) == 0

    def test_two_facts_one_solution_each(self):
        db = Database()
        db.assertz(Clause(head=Compound("foo", (1,)), body=[]))
        db.assertz(Clause(head=Compound("foo", (2,)), body=[]))
        fn = compile_predicate_trampoline("foo", 1, db.clauses_for("foo", 1), db)
        trail1, trail2 = fresh_trail(), fresh_trail()
        assert _count_solutions(fn, 1, trail1) == 1
        assert _count_solutions(fn, 2, trail2) == 1

    def test_unbound_arg_yields_solutions_in_order(self):
        """Multiple clauses with Var heads and Is bodies enumerate solutions.

        The head uses MatchAs to capture any incoming arg (including a Var);
        the body's Is goal then unifies that Var with the concrete value.
        This is how Prolog-style enumeration works in the compiled model:
        literal-headed facts match only concrete args; for binding a Var,
        the clause head must itself be a Var.
        """
        a, b = Var(), Var()
        db = Database()
        db.assertz(Clause(head=Compound("digit", (a,)), body=[Is(left=a, right=1)]))
        db.assertz(Clause(head=Compound("digit", (b,)), body=[Is(left=b, right=2)]))
        fn = compile_predicate_trampoline("digit", 1, db.clauses_for("digit", 1), db)
        x = Var()
        trail = fresh_trail()
        results = _snap(fn, lambda: deref(x), x, trail)
        assert results == [1, 2]

    def test_fact_binds_var(self):
        """Clause with Var head and Is body can bind an incoming Var arg."""
        x = Var()
        db = Database()
        db.assertz(Clause(head=Compound("color", (x,)), body=[Is(left=x, right="red")]))
        fn = compile_predicate_trampoline("color", 1, db.clauses_for("color", 1), db)
        v = Var()
        trail = fresh_trail()
        results = _snap(fn, lambda: deref(v), v, trail)
        assert results == ["red"]

    def test_bindings_undone_after_exhaustion(self):
        """After search completes, trail undo restores Var to unbound."""
        x = Var()
        db = Database()
        db.assertz(Clause(head=Compound("val", (x,)), body=[Is(left=x, right=99)]))
        fn = compile_predicate_trampoline("val", 1, db.clauses_for("val", 1), db)
        v = Var()
        trail = fresh_trail()
        _count_solutions(fn, v, trail)
        assert deref(v) is v  # unbound after search


# ── Integration: unification bodies ───────────────────────────────────────────


class TestTrampolineIntegrationUnification:

    def test_is_goal_binds_var(self):
        x = Var()
        db = Database()
        db.assertz(Clause(head=Compound("is_x", (x,)), body=[Is(left=x, right=5)]))
        fn = compile_predicate_trampoline("is_x", 1, db.clauses_for("is_x", 1), db)
        v = Var()
        trail = fresh_trail()
        results = _snap(fn, lambda: deref(v), v, trail)
        assert results == [5]

    def test_failed_is_goal_zero_solutions(self):
        db = Database()
        db.assertz(Clause(head=Compound("bad", (2,)), body=[Is(left=2, right=3)]))
        fn = compile_predicate_trampoline("bad", 1, db.clauses_for("bad", 1), db)
        trail = fresh_trail()
        assert _count_solutions(fn, 2, trail) == 0

    def test_conjunction_body_both_bound(self):
        x, y = Var(), Var()
        db = Database()
        db.assertz(Clause(
            head=Compound("two_vals", (x, y)),
            body=[Is(left=x, right=1), Is(left=y, right=2)],
        ))
        fn = compile_predicate_trampoline("two_vals", 2, db.clauses_for("two_vals", 2), db)
        a, b = Var(), Var()
        trail = fresh_trail()
        results = _snap(fn, lambda: (deref(a), deref(b)), a, b, trail)
        assert results == [(1, 2)]


# ── Integration: predicate calls ───────────────────────────────────────────────


class TestTrampolineIntegrationPredicateCall:

    def test_chain_two_predicates(self):
        """wrap(X) :- inner(X). inner(X) :- X = 42. Calling wrap(V) binds V to 42.

        Note: head matching is structural, so inner's clause must use a Var
        head (not a literal) to accept an unbound Var argument from wrap's body.
        """
        db = Database()
        ix = Var()
        db.assertz(Clause(head=Compound("inner", (ix,)), body=[Is(left=ix, right=42)]))
        x = Var()
        db.assertz(Clause(
            head=Compound("wrap", (x,)),
            body=[Call(func=LoadName(name="inner"), args=[x], kwargs=[])],
        ))
        compile_predicate_trampoline("inner", 1, db.clauses_for("inner", 1), db)
        fn = compile_predicate_trampoline("wrap", 1, db.clauses_for("wrap", 1), db)

        v = Var()
        trail = fresh_trail()
        results = _snap(fn, lambda: deref(v), v, trail)
        assert results == [42]

    def test_chain_multiplies_solutions(self):
        """combo(X, Y) :- color(X), size(Y). 2 × 2 = 4 solutions.

        color and size use Var heads + Is bodies so they accept unbound Var args.
        """
        db = Database()
        c1, c2 = Var(), Var()
        s1, s2 = Var(), Var()
        db.assertz(Clause(head=Compound("color", (c1,)), body=[Is(left=c1, right="red")]))
        db.assertz(Clause(head=Compound("color", (c2,)), body=[Is(left=c2, right="blue")]))
        db.assertz(Clause(head=Compound("size", (s1,)), body=[Is(left=s1, right="big")]))
        db.assertz(Clause(head=Compound("size", (s2,)), body=[Is(left=s2, right="small")]))

        cx, sy = Var(), Var()
        db.assertz(Clause(
            head=Compound("combo", (cx, sy)),
            body=[
                Call(func=LoadName(name="color"), args=[cx], kwargs=[]),
                Call(func=LoadName(name="size"), args=[sy], kwargs=[]),
            ],
        ))

        compile_predicate_trampoline("color", 1, db.clauses_for("color", 1), db)
        compile_predicate_trampoline("size", 1, db.clauses_for("size", 1), db)
        fn = compile_predicate_trampoline("combo", 2, db.clauses_for("combo", 2), db)

        a, b = Var(), Var()
        trail = fresh_trail()
        results = _snap(fn, lambda: (deref(a), deref(b)), a, b, trail)
        assert len(results) == 4
        assert ("red", "big") in results
        assert ("blue", "small") in results

    def test_many_facts_no_stack_overflow(self):
        """5000 Var-headed clauses with Is bodies enumerate without stack overflow.

        Each clause: step(V) :- V = i.  Calling step(v) with unbound v yields
        N solutions (v bound to 0, 1, ..., N-1 in turn).  This verifies the
        trampoline drives through thousands of clauses without growing the stack.
        """
        N = 5000
        db = Database()
        for i in range(N):
            hv = Var()
            db.assertz(Clause(head=Compound("step", (hv,)), body=[Is(left=hv, right=i)]))
        fn = compile_predicate_trampoline("step", 1, db.clauses_for("step", 1), db)
        v = Var()
        trail = fresh_trail()
        count = _count_solutions(fn, v, trail)
        assert count == N

    def test_wrap_many_facts_via_call(self):
        """chain(X) :- step2(X). step2 has N clauses. No stack overflow via Step."""
        N = 1000
        db = Database()
        for i in range(N):
            hv = Var()
            db.assertz(Clause(head=Compound("step2", (hv,)), body=[Is(left=hv, right=i)]))

        x = Var()
        db.assertz(Clause(
            head=Compound("chain2", (x,)),
            body=[Call(func=LoadName(name="step2"), args=[x], kwargs=[])],
        ))
        compile_predicate_trampoline("step2", 1, db.clauses_for("step2", 1), db)
        fn = compile_predicate_trampoline("chain2", 1, db.clauses_for("chain2", 1), db)
        v = Var()
        trail = fresh_trail()
        assert _count_solutions(fn, v, trail) == N


# ── Integration: disjunction ───────────────────────────────────────────────────


class TestTrampolineIntegrationDisjunction:

    def test_or_two_branches(self):
        x = Var()
        db = Database()
        db.assertz(Clause(
            head=Compound("or_pred", (x,)),
            body=[Or(left=Is(left=x, right=1), right=Is(left=x, right=2))],
        ))
        fn = compile_predicate_trampoline("or_pred", 1, db.clauses_for("or_pred", 1), db)
        v = Var()
        trail = fresh_trail()
        results = _snap(fn, lambda: deref(v), v, trail)
        assert results == [1, 2]

    def test_or_left_fails_right_succeeds(self):
        x = Var()
        db = Database()
        db.assertz(Clause(
            head=Compound("or2", (x,)),
            body=[Or(left=Is(left=x, right=99), right=Is(left=x, right=7))],  # 99 != bound 5; 7 succeeds only if x free
        ))
        fn = compile_predicate_trampoline("or2", 1, db.clauses_for("or2", 1), db)
        v = Var()
        trail = fresh_trail()
        results = _snap(fn, lambda: deref(v), v, trail)
        assert set(results) == {99, 7}


# ── Integration: negation-as-failure ──────────────────────────────────────────


class TestTrampolineIntegrationNegation:
    """NAF inner goal uses trampoline-mode dispatch."""

    def test_naf_succeeds_when_inner_fails(self):
        """not(fail_pred(X)) where fail_pred has no clauses → 1 solution."""
        x = Var()
        db = Database()
        compile_predicate_trampoline("fail_pred", 1, [], db)
        db.assertz(Clause(
            head=Compound("naf_test", (x,)),
            body=[Not(operand=Call(func=LoadName(name="fail_pred"), args=[x], kwargs=[]))],
        ))
        fn = compile_predicate_trampoline("naf_test", 1, db.clauses_for("naf_test", 1), db)
        trail = fresh_trail()
        assert _count_solutions(fn, 42, trail) == 1

    def test_naf_fails_when_inner_succeeds(self):
        """not(succeed_pred(42)) where succeed_pred(42) is a fact → 0 solutions."""
        x = Var()
        db = Database()
        db.assertz(Clause(head=Compound("succeed_pred", (42,)), body=[]))
        compile_predicate_trampoline("succeed_pred", 1, db.clauses_for("succeed_pred", 1), db)
        db.assertz(Clause(
            head=Compound("naf_test2", (x,)),
            body=[Not(operand=Call(func=LoadName(name="succeed_pred"), args=[x], kwargs=[]))],
        ))
        fn = compile_predicate_trampoline(
            "naf_test2", 1, db.clauses_for("naf_test2", 1), db
        )
        trail = fresh_trail()
        assert _count_solutions(fn, 42, trail) == 0


# ── Integration: membership ────────────────────────────────────────────────────


class TestTrampolineIntegrationMembership:

    def test_in_enumerates_list(self):
        x = Var()
        db = Database()
        db.assertz(Clause(
            head=Compound("member_t", (x,)),
            body=[In(left=x, right=[1, 2, 3])],
        ))
        fn = compile_predicate_trampoline("member_t", 1, db.clauses_for("member_t", 1), db)
        v = Var()
        trail = fresh_trail()
        results = _snap(fn, lambda: deref(v), v, trail)
        assert results == [1, 2, 3]

    def test_not_in_succeeds_when_absent(self):
        x = Var()
        db = Database()
        db.assertz(Clause(
            head=Compound("not_mem", (x,)),
            body=[NotIn(left=x, right=[1, 2])],
        ))
        fn = compile_predicate_trampoline("not_mem", 1, db.clauses_for("not_mem", 1), db)
        trail = fresh_trail()
        assert _count_solutions(fn, 3, trail) == 1

    def test_not_in_fails_when_present(self):
        x = Var()
        db = Database()
        db.assertz(Clause(
            head=Compound("not_mem2", (x,)),
            body=[NotIn(left=x, right=[1, 2])],
        ))
        fn = compile_predicate_trampoline("not_mem2", 1, db.clauses_for("not_mem2", 1), db)
        trail = fresh_trail()
        assert _count_solutions(fn, 1, trail) == 0


# ── Integration: comparisons and arithmetic ────────────────────────────────────


class TestTrampolineIntegrationComparisons:

    def test_gt_succeeds(self):
        x = Var()
        db = Database()
        db.assertz(Clause(head=Compound("big", (x,)), body=[Gt(left=x, right=10)]))
        fn = compile_predicate_trampoline("big", 1, db.clauses_for("big", 1), db)
        trail = fresh_trail()
        assert _count_solutions(fn, 15, trail) == 1

    def test_gt_fails(self):
        x = Var()
        db = Database()
        db.assertz(Clause(head=Compound("big2", (x,)), body=[Gt(left=x, right=10)]))
        fn = compile_predicate_trampoline("big2", 1, db.clauses_for("big2", 1), db)
        trail = fresh_trail()
        assert _count_solutions(fn, 5, trail) == 0

    def test_eq_structural_match(self):
        """same(X, Y) :- X == Y. Succeeds when both args are structurally equal."""
        # Use two separate Vars so match patterns don't have duplicate capture names.
        x1, x2 = Var(), Var()
        db = Database()
        db.assertz(Clause(
            head=Compound("same", (x1, x2)),
            body=[StructuralEq(left=x1, right=x2)],
        ))
        fn = compile_predicate_trampoline("same", 2, db.clauses_for("same", 2), db)
        trail = fresh_trail()
        assert _count_solutions(fn, 7, 7, trail) == 1
        trail2 = fresh_trail()
        assert _count_solutions(fn, 7, 8, trail2) == 0

    def test_arith_add_one(self):
        """add_one(X, Y) :- Y := X + 1."""
        x, y = Var(), Var()
        db = Database()
        db.assertz(Clause(
            head=Compound("add_one", (x, y)),
            body=[Evaluate(left=y, right=Add(left=x, right=1))],
        ))
        fn = compile_predicate_trampoline("add_one", 2, db.clauses_for("add_one", 2), db)
        result = Var()
        trail = fresh_trail()
        results = _snap(fn, lambda: deref(result), 5, result, trail)
        assert results == [6]


# ── Always-fail / DONE sentinel ────────────────────────────────────────────────


class TestTrampolineAlwaysFail:

    def test_always_fail_zero_solutions(self):
        db = Database()
        fn = compile_predicate_trampoline("undef", 2, [], db)
        trail = fresh_trail()
        assert _count_solutions(fn, 1, 2, trail) == 0

    def test_always_fail_yields_tuple_none_done(self):
        """The always-fail generator's first yield is (parent=None, DONE)."""
        db = Database()
        fn = compile_predicate_trampoline("undef2", 1, [], db)
        trail = fresh_trail()
        root = StepGenerator(fn, None, 42, trail)
        gen, value = root.send(None)
        assert gen is None
        assert value is DONE


class TestDONESentinel:

    def test_done_is_singleton(self):
        from clausal.logic.compiler import DONE as D1, DONE as D2
        assert D1 is D2

    def test_done_is_not_none(self):
        assert DONE is not None

    def test_done_distinct_from_false(self):
        assert DONE is not False


# ── WK-LAZY: lazy recompile after dynamic clause addition ──────────────────────


class TestLazyRecompile:
    """After compile_predicate_trampoline, new assertz → lazy recompile on next call."""

    def test_lazy_recompile_fires_after_assertz(self):
        """Adding a clause after compilation triggers recompile on next dispatch."""
        db = Database()
        hv = Var()
        db.assertz(Clause(head=Compound("dyn", (hv,)), body=[Is(left=hv, right=1)]))
        fn = compile_predicate_trampoline("dyn", 1, db.clauses_for("dyn", 1), db)
        v = Var()
        trail = fresh_trail()
        assert _count_solutions(fn, v, trail) == 1

        # Add a second clause at runtime
        hv2 = Var()
        db.assertz(Clause(head=Compound("dyn", (hv2,)), body=[Is(left=hv2, right=2)]))
        # dispatch is now None; get_dispatch() should lazy-recompile
        v2 = Var()
        trail2 = fresh_trail()
        new_fn = db.get_dispatch("dyn", 1)
        results = _snap(new_fn, lambda: deref(v2), v2, trail2)
        assert results == [1, 2]

    def test_lazy_recompile_via_db_dispatch(self):
        """Lazy recompile works when driving dispatch from db.get_dispatch()."""
        db = Database()
        hv = Var()
        db.assertz(Clause(head=Compound("sdyn", (hv,)), body=[Is(left=hv, right=10)]))
        compile_predicate_trampoline("sdyn", 1, db.clauses_for("sdyn", 1), db)

        hv2 = Var()
        db.assertz(Clause(head=Compound("sdyn", (hv2,)), body=[Is(left=hv2, right=20)]))
        fn = db.get_dispatch("sdyn", 1)
        v = Var()
        trail = fresh_trail()
        results = _snap(fn, lambda: deref(v), v, trail)
        assert results == [10, 20]
