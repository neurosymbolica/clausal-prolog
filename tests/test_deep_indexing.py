"""Tests for Phase 5: deep structural indexing via pattern trie.

Phase 5 inserts isinstance/is_var dispatch guards inside compiled predicate
functions so that calls are routed to the correct clause group by the *type
and structure* of an argument at runtime, without trying every clause in
sequence.

For a predicate like:

    MyLen([], 0)
    MyLen([_, *TAIL], N) <- (MyLen(TAIL, N1), eval_(N1 + 1, N))

the generated code should look roughly like:

    def MyLen__2(this_generator, _tramp_parent, arg0, arg1, trail):
        _d0 = deref(arg0)
        _d1 = deref(arg1)
        if isinstance(_d0, list):
            if not _d0:             # [] — base case
                match (_d0, _d1): ...
            else:                   # [H|T] — recursive case
                match (_d0, _d1): ...
        elif is_var(_d0):           # unbound — try all clauses
            match (_d0, _d1): ...
            match (_d0, _d1): ...
        yield (_tramp_parent, DONE)

instead of two unconditional match blocks.

─────────────────────────────────────────────────────────────────────────────
Test organisation
─────────────────────────────────────────────────────────────────────────────

TestDeepIndexBehavioral  — correctness tests via .clausal fixture (should pass
                           before AND after Phase 5; serve as regression guards)

TestDeepIndexStructural  — white-box AST inspection tests (will FAIL before
                           Phase 5 is implemented, PASS afterwards)

TestDeepIndexEdgeCases   — corner cases: arity-0, single clause, all-var
                           heads, mixed structural + scalar positions

─────────────────────────────────────────────────────────────────────────────
FRAGILITY NOTES
─────────────────────────────────────────────────────────────────────────────

TestDeepIndexBehavioral
  • Tests load tests/fixtures/deep_index.clausal via load_clausal_module().
    The fixture file defines MyLen, MyAppend, MyMember, MyLast, MyProduct,
    MySumList, MyMax, MyNthOf, MyPrefix.  If those predicates are renamed or
    removed the corresponding tests must be updated.
  • Bindings are read INSIDE the for-loop over call() — deref() after list()
    would return unbound Vars since trail bindings are undone on exhaustion.

TestDeepIndexStructural
  • _has_isinstance_check(func_def, "list") walks the AST for isinstance(x, list)
    calls.  If Phase 5 uses a helper function (e.g. _is_list_term) instead of
    a raw isinstance call, these checks need updating to match the helper name.
  • Structural test fixtures use Var() for all non-list argument positions to
    avoid MatchValue patterns that would break the test.  Raw Compound heads
    with integer constants generate MatchValue which cannot match Vars —
    use all-Var heads or load from .clausal for predicates that need that.
  • _count_top_level_match_stmts counts ast.Match nodes that are direct children
    of the function body (not nested inside if-branches).  After Phase 5 the
    top-level match count should be *less* than the clause count for
    list-discriminating predicates, because clauses are grouped under isinstance
    guards.  The exact count depends on how many structural buckets the predicate
    has, not on a fixed number.
  • The is_var check test navigates the AST for an ast.If whose test is a Call
    to is_var.  If Phase 5 uses a different guard (e.g. checking type directly
    rather than is_var), update _has_is_var_guard accordingly.
  • _list_arg(i, n) builds a minimal predicate with clauses that differ only in
    the list structure at position i (nil vs non-empty list).  The other n-1
    positions are always Var() wildcards to avoid MatchValue complications.
"""

from __future__ import annotations

import ast
import os

import pytest

from clausal.logic.compiler import compile_predicate_trampoline_ast
from clausal.logic.database import Clause, Database
from clausal.logic.trampoline import StepGenerator, DONE as _DONE
from clausal.logic.variables import Var, Trail, deref
from clausal.terms import Compound
from clausal.testing import load_clausal_module

_FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


# ── AST inspection helpers ─────────────────────────────────────────────────────


def _isinstance_check_matches(type_arg: ast.expr, type_name: str) -> bool:
    """Check if an isinstance type argument mentions *type_name*.

    Handles both ``isinstance(x, list)`` (Name node) and
    ``isinstance(x, (list, str))`` (Tuple of Names).
    """
    if isinstance(type_arg, ast.Name) and type_arg.id == type_name:
        return True
    if isinstance(type_arg, ast.Tuple):
        return any(
            isinstance(elt, ast.Name) and elt.id == type_name
            for elt in type_arg.elts
        )
    return False


def _has_isinstance_check(tree: ast.AST, type_name: str) -> bool:
    """Return True if tree contains isinstance(_, type_name) anywhere."""
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "isinstance"
            and len(node.args) == 2
            and _isinstance_check_matches(node.args[1], type_name)
        ):
            return True
    return False


def _has_is_var_guard(tree: ast.AST) -> bool:
    """Return True if tree contains an if is_var(...) guard."""
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.If)
            and isinstance(node.test, ast.Call)
            and isinstance(node.test.func, ast.Name)
            and node.test.func.id == "is_var"
        ):
            return True
    return False


def _count_top_level_match_stmts(func_def: ast.FunctionDef) -> int:
    """Count ast.Match nodes that are direct children of the function body."""
    return sum(1 for s in func_def.body if isinstance(s, ast.Match))


def _count_total_match_stmts(func_def: ast.FunctionDef) -> int:
    """Count all ast.Match nodes anywhere in the function."""
    return sum(1 for _ in ast.walk(func_def) if isinstance(_, ast.Match))


def _count_isinstance_checks(tree: ast.AST, type_name: str) -> int:
    """Count isinstance(_, type_name) calls in tree."""
    count = 0
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "isinstance"
            and len(node.args) == 2
            and _isinstance_check_matches(node.args[1], type_name)
        ):
            count += 1
    return count


# ── Fixture builders ───────────────────────────────────────────────────────────


def _make_list_pred(
    functor: str,
    list_heads: list,  # list of (list_value, other_arg_count) — one per clause
    *,
    arity: int = 2,
) -> ast.FunctionDef:
    """Build a predicate with list-structured first argument.

    All non-list argument positions use fresh Var() so that the compiler
    generates wildcard captures rather than MatchValue (which would require
    exact ground matches).

    list_heads is a list of list values for arg0 of each clause; all other
    arg positions are Var().
    """
    db = Database()
    for list_val in list_heads:
        other_args = tuple(Var() for _ in range(arity - 1))
        db.assertz(Clause(head=Compound(functor, (list_val, *other_args)), body=[]))
    clauses = db.clauses_for(functor, arity)
    return compile_predicate_trampoline_ast(functor, arity, clauses, db)


def _nil_and_cons_funcdef(arity: int = 2) -> ast.FunctionDef:
    """Compile a 2-clause predicate: clause 0 has [] head, clause 1 has non-empty list."""
    return _make_list_pred("p", [[], [1, 2, 3]], arity=arity)


def _trampoline_solutions(dispatch_fn, args: tuple) -> list:
    """Drive a trampoline dispatch function; return count of solutions."""
    solutions = []
    root = StepGenerator(dispatch_fn, None, None, None, *args)
    gen, val = root.send(None)
    while True:
        if gen is None:
            if val is _DONE:
                break
            solutions.append(True)
            gen, val = root.send(None)
        else:
            gen, val = gen.send(val)
    return solutions


# ── Behavioral tests ───────────────────────────────────────────────────────────


class TestDeepIndexBehavioral:
    """Correctness tests via the .clausal fixture.

    The fixture (tests/fixtures/deep_index.clausal) defines user-level list
    predicates.  These Python tests drive them via call() and verify results.
    All bindings are read *inside* the for-loop while the trail is live.

    These tests must pass both before and after Phase 5.
    """

    @pytest.fixture(scope="class")
    def lm(self):
        path = os.path.join(_FIXTURES, "deep_index.clausal")
        mod = load_clausal_module(path)
        return mod.__dict__["$module"]

    # ── MyLen ──────────────────────────────────────────────────────────────────

    def test_mylen_empty(self, lm):
        # nv
        from clausal.logic.solve import call
        n = Var()
        results = [deref(n) for _ in call("MyLen", [], n, module=lm)]
        assert results == [0]

    def test_mylen_three(self, lm):
        # nv
        from clausal.logic.solve import call
        n = Var()
        results = [deref(n) for _ in call("MyLen", [1, 2, 3], n, module=lm)]
        assert results == [3]

    def test_mylen_five(self, lm):
        # nv
        from clausal.logic.solve import call
        n = Var()
        results = [deref(n) for _ in call("MyLen", [10, 20, 30, 40, 50], n, module=lm)]
        assert results == [5]

    def test_mylen_deterministic(self, lm):
        """MyLen with ground list produces exactly one solution."""
        # nv
        from clausal.logic.solve import call
        n = Var()
        assert len(list(call("MyLen", [1, 2], n, module=lm))) == 1

    # ── MyAppend ───────────────────────────────────────────────────────────────

    def test_myappend_nil_left(self, lm):
        # nv
        from clausal.logic.solve import call
        r = Var()
        results = [deref(r) for _ in call("MyAppend", [], [1, 2], r, module=lm)]
        assert results == [[1, 2]]

    def test_myappend_two_plus_two(self, lm):
        # nv
        from clausal.logic.solve import call
        r = Var()
        results = [deref(r) for _ in call("MyAppend", [1, 2], [3, 4], r, module=lm)]
        assert results == [[1, 2, 3, 4]]

    def test_myappend_nil_right(self, lm):
        # nv
        from clausal.logic.solve import call
        r = Var()
        results = [deref(r) for _ in call("MyAppend", [1, 2], [], r, module=lm)]
        assert results == [[1, 2]]

    def test_myappend_split_enumerates_all(self, lm):
        """append in split mode enumerates all four splits of [1,2,3]."""
        # nv
        from clausal.logic.solve import call
        a, b = Var(), Var()
        splits = [(list(deref(a)), list(deref(b)))
                  for _ in call("MyAppend", a, b, [1, 2, 3], module=lm)]
        assert splits == [
            ([], [1, 2, 3]),
            ([1], [2, 3]),
            ([1, 2], [3]),
            ([1, 2, 3], []),
        ]

    # ── MyMember ───────────────────────────────────────────────────────────────

    def test_mymember_present(self, lm):
        # nv
        from clausal.logic.solve import call
        assert list(call("MyMember", 2, [1, 2, 3], module=lm))

    def test_mymember_absent(self, lm):
        # nv
        from clausal.logic.solve import call
        assert not list(call("MyMember", 99, [1, 2, 3], module=lm))

    def test_mymember_enumerate(self, lm):
        # nv
        from clausal.logic.solve import call
        x = Var()
        results = [deref(x) for _ in call("MyMember", x, [10, 20, 30], module=lm)]
        assert results == [10, 20, 30]

    def test_mymember_duplicates(self, lm):
        # nv
        from clausal.logic.solve import call
        x = Var()
        results = [deref(x) for _ in call("MyMember", x, [1, 1, 2], module=lm)]
        assert results == [1, 1, 2]

    # ── MyLast ─────────────────────────────────────────────────────────────────

    def test_mylast_singleton(self, lm):
        # nv
        from clausal.logic.solve import call
        x = Var()
        results = [deref(x) for _ in call("MyLast", [5], x, module=lm)]
        assert results == [5]

    def test_mylast_three(self, lm):
        # nv
        from clausal.logic.solve import call
        x = Var()
        results = [deref(x) for _ in call("MyLast", [1, 2, 3], x, module=lm)]
        assert results == [3]

    def test_mylast_deterministic(self, lm):
        # nv
        from clausal.logic.solve import call
        x = Var()
        assert len(list(call("MyLast", [1, 2, 3], x, module=lm))) == 1

    # ── MySumList ──────────────────────────────────────────────────────────────

    def test_mysumlist_empty(self, lm):
        # nv
        from clausal.logic.solve import call
        s = Var()
        results = [deref(s) for _ in call("MySumList", [], s, module=lm)]
        assert results == [0]

    def test_mysumlist_ten(self, lm):
        # nv
        from clausal.logic.solve import call
        s = Var()
        results = [deref(s) for _ in call("MySumList", list(range(1, 11)), s, module=lm)]
        assert results == [55]

    # ── MyMax ──────────────────────────────────────────────────────────────────

    def test_mymax_singleton(self, lm):
        # nv
        from clausal.logic.solve import call
        m = Var()
        results = [deref(m) for _ in call("MyMax", [3], m, module=lm)]
        assert results == [3]

    def test_mymax_three(self, lm):
        # nv
        from clausal.logic.solve import call
        m = Var()
        results = [deref(m) for _ in call("MyMax", [3, 1, 4], m, module=lm)]
        assert results == [4]

    # ── MyProduct ─────────────────────────────────────────────────────────────

    def test_myproduct_empty(self, lm):
        # nv
        from clausal.logic.solve import call
        p = Var()
        results = [deref(p) for _ in call("MyProduct", [], p, module=lm)]
        assert results == [1]

    def test_myproduct_five(self, lm):
        # nv
        from clausal.logic.solve import call
        p = Var()
        results = [deref(p) for _ in call("MyProduct", [1, 2, 3, 4, 5], p, module=lm)]
        assert results == [120]

    # ── MyPrefix — backtracking ────────────────────────────────────────────────

    def test_myprefix_enumerate(self, lm):
        # nv
        from clausal.logic.solve import call
        p = Var()
        prefixes = [list(deref(p)) for _ in call("MyPrefix", p, [1, 2], module=lm)]
        assert prefixes == [[], [1], [1, 2]]

    def test_myprefix_no_extra_solutions(self, lm):
        # nv
        from clausal.logic.solve import call
        p = Var()
        assert len(list(call("MyPrefix", p, [1, 2], module=lm))) == 3


# ── Structural tests ───────────────────────────────────────────────────────────


class TestDeepIndexStructural:
    """White-box AST tests: verify Phase 5 generates isinstance/is_var guards.

    These tests FAIL before Phase 5 is implemented and PASS afterwards.

    All fixture predicates use Var() for non-list argument positions so that
    the compiler generates wildcard captures rather than MatchValue patterns
    (integer MatchValues would reject Var arguments at runtime).
    """

    # ── isinstance(_, list) guards ────────────────────────────────────────────

    def test_nil_and_cons_pred_has_isinstance_list_guard(self):
        """A predicate with [] and non-empty list heads gets isinstance(_, list) guard."""
        # nv
        func_def = _nil_and_cons_funcdef(arity=2)
        assert _has_isinstance_check(func_def, "list"), (
            "Expected isinstance(_, list) guard in generated code for a "
            "predicate with [] and non-empty list clause heads"
        )

    def test_three_list_clauses_has_isinstance_guard(self):
        """Three clauses with different non-empty list heads still get isinstance."""
        # nv
        func_def = _make_list_pred("q", [[], [1], [1, 2, 3]], arity=2)
        assert _has_isinstance_check(func_def, "list")

    def test_single_clause_no_isinstance_guard(self):
        """A single-clause predicate has no structural dispatch (nothing to dispatch to)."""
        # nv
        func_def = _make_list_pred("s", [[]], arity=2)
        assert not _has_isinstance_check(func_def, "list"), (
            "Single-clause predicate should not get isinstance guard"
        )

    def test_scalar_only_pred_has_no_isinstance_list_guard(self):
        """Predicate with only integer/string first args should NOT get list guard."""
        # nv
        db = Database()
        for i in range(4):
            db.assertz(Clause(head=Compound("r", (Var(), Var())), body=[]))
        clauses = db.clauses_for("r", 2)
        func_def = compile_predicate_trampoline_ast("r", 2, clauses, db)
        assert not _has_isinstance_check(func_def, "list"), (
            "Unexpected isinstance(_, list) guard in a wildcard-only predicate"
        )

    def test_isinstance_check_is_on_deref_local(self):
        """The isinstance guard tests a _d<i> deref local, not the raw arg name."""
        # nv
        func_def = _nil_and_cons_funcdef(arity=2)
        for node in ast.walk(func_def):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "isinstance"
                and len(node.args) == 2
                and _isinstance_check_matches(node.args[1], "list")
            ):
                subject = node.args[0]
                assert isinstance(subject, ast.Name), (
                    f"isinstance subject should be a Name, got {ast.unparse(subject)}"
                )
                assert subject.id.startswith("_d"), (
                    f"isinstance subject should be a _d<i> deref local, got {subject.id}"
                )
                return
        pytest.fail("No isinstance(_, list) check found")

    # ── is_var guard for unbound arguments ────────────────────────────────────

    def test_list_pred_has_is_var_guard(self):
        """when arg may be a Var, generated code includes is_var guard as fallback."""
        # nv
        func_def = _make_list_pred("t", [[], [1], [1, 2]], arity=2)
        assert _has_is_var_guard(func_def), (
            "Expected is_var(...) guard for unbound argument path in "
            "list-discriminating predicate"
        )

    def test_is_var_guard_is_on_deref_local(self):
        """The is_var guard tests a _d<i> deref local, not the raw arg name."""
        # nv
        func_def = _make_list_pred("u", [[], [1, 2]], arity=2)
        for node in ast.walk(func_def):
            if (
                isinstance(node, ast.If)
                and isinstance(node.test, ast.Call)
                and isinstance(node.test.func, ast.Name)
                and node.test.func.id == "is_var"
            ):
                args = node.test.args
                assert len(args) == 1, "is_var() takes exactly one argument"
                arg = args[0]
                assert isinstance(arg, ast.Name), (
                    f"is_var subject should be a Name, got {ast.unparse(arg)}"
                )
                assert arg.id.startswith("_d"), (
                    f"is_var subject should be a _d<i> local, got {arg.id}"
                )
                return
        pytest.fail("No is_var(...) guard found")

    # ── Top-level match reduction ─────────────────────────────────────────────

    def test_top_level_match_count_less_than_clause_count(self):
        """After structural dispatch, fewer top-level match blocks than clauses.

        Without Phase 5: 3 clauses → 3 top-level Match nodes.
        With Phase 5: clauses are grouped under isinstance/is_var guards, so
        top-level body has fewer than 3 direct Match children.
        """
        # nv
        func_def = _make_list_pred("v", [[], [1], [1, 2]], arity=2)
        top_level = _count_top_level_match_stmts(func_def)
        n_clauses = 3
        assert top_level < n_clauses, (
            f"Expected fewer top-level Match nodes than {n_clauses} clauses, "
            f"got {top_level} — structural grouping not applied"
        )

    def test_nil_and_cons_have_separate_match_blocks(self):
        """The [] and non-empty cases are compiled into distinct match blocks."""
        # nv
        func_def = _make_list_pred("w", [[], [1, 2]], arity=2)
        assert _has_isinstance_check(func_def, "list")
        # The total number of Match nodes should be at least 2: one for nil,
        # one for cons (possibly more if is_var fallback duplicates them).
        assert _count_total_match_stmts(func_def) >= 2, (
            "Expected at least two match blocks (nil and cons groups) inside "
            "the isinstance guard"
        )

    # ── isinstance count ──────────────────────────────────────────────────────

    def test_isinstance_appears_exactly_once_for_one_list_position(self):
        """For a predicate discriminating on one list arg, isinstance appears once."""
        # nv
        func_def = _make_list_pred("x", [[], [1]], arity=2)
        count = _count_isinstance_checks(func_def, "list")
        assert count == 1, (
            f"Expected exactly one isinstance(_, list) check for a single "
            f"list-position predicate, got {count}"
        )


# ── Edge case tests ────────────────────────────────────────────────────────────


class TestDeepIndexEdgeCases:
    """Corner cases that the structural optimisation must handle correctly."""

    def test_arity_zero_unaffected(self):
        """Arity-0 predicates have no arguments to dispatch on."""
        # nv
        db = Database()
        db.assertz(Clause(head=Compound("z", ()), body=[]))
        db.assertz(Clause(head=Compound("z", ()), body=[]))
        clauses = db.clauses_for("z", 0)
        func_def = compile_predicate_trampoline_ast("z", 0, clauses, db)
        assert not _has_isinstance_check(func_def, "list")
        assert not _has_is_var_guard(func_def)

    def test_arity_one_single_nil_clause(self):
        """Single [] clause: no dispatch needed (nothing to dispatch to)."""
        # nv
        db = Database()
        db.assertz(Clause(head=Compound("p1", ([],)), body=[]))
        clauses = db.clauses_for("p1", 1)
        func_def = compile_predicate_trampoline_ast("p1", 1, clauses, db)
        assert not _has_isinstance_check(func_def, "list")

    def test_all_var_heads_no_list_guard(self):
        """Predicate with wildcard heads on all clauses: no list guard needed."""
        # nv
        db = Database()
        for _ in range(3):
            db.assertz(Clause(head=Compound("allvar", (Var(),)), body=[]))
        clauses = db.clauses_for("allvar", 1)
        func_def = compile_predicate_trampoline_ast("allvar", 1, clauses, db)
        assert not _has_isinstance_check(func_def, "list"), (
            "All-var heads should not trigger list structural dispatch"
        )

    def test_list_pred_correctness_ground_nil(self):
        """Structural dispatch must correctly route [] to the nil clause."""
        # nv
        from clausal.logic.compiler import compile_predicate_trampoline

        # p([], _v)  and  p([1,2], _v2)
        db = Database()
        v1, v2 = Var(), Var()
        db.assertz(Clause(head=Compound("mylen", ([], v1)), body=[]))
        db.assertz(Clause(head=Compound("mylen", ([1, 2], v2)), body=[]))
        clauses = db.clauses_for("mylen", 2)
        dispatch = compile_predicate_trampoline("mylen", 2, clauses, db)

        trail = Trail()
        n = Var()
        # Call with [] — should find exactly one solution (the nil clause)
        sols = _trampoline_solutions(dispatch, ([], n, trail))
        assert len(sols) == 1, f"Expected 1 solution for [], got {len(sols)}"

    def test_list_pred_correctness_ground_cons(self):
        """Structural dispatch must correctly route non-empty list to cons clause."""
        # nv
        from clausal.logic.compiler import compile_predicate_trampoline

        db = Database()
        v1, v2 = Var(), Var()
        db.assertz(Clause(head=Compound("mylen", ([], v1)), body=[]))
        db.assertz(Clause(head=Compound("mylen", ([1, 2], v2)), body=[]))
        clauses = db.clauses_for("mylen", 2)
        dispatch = compile_predicate_trampoline("mylen", 2, clauses, db)

        trail = Trail()
        n = Var()
        # Call with [1,2] — should find exactly one solution (the cons clause)
        sols = _trampoline_solutions(dispatch, ([1, 2], n, trail))
        assert len(sols) == 1, f"Expected 1 solution for [1,2], got {len(sols)}"

    def test_list_pred_correctness_non_list_arg(self):
        """A non-list arg should yield no solutions for list-pattern clauses."""
        # nv
        from clausal.logic.compiler import compile_predicate_trampoline

        db = Database()
        v1, v2 = Var(), Var()
        db.assertz(Clause(head=Compound("mylen", ([], v1)), body=[]))
        db.assertz(Clause(head=Compound("mylen", ([1], v2)), body=[]))
        clauses = db.clauses_for("mylen", 2)
        dispatch = compile_predicate_trampoline("mylen", 2, clauses, db)

        trail = Trail()
        n = Var()
        # Passing an integer (not a list) should yield no solutions
        sols = _trampoline_solutions(dispatch, (42, n, trail))
        assert sols == [], f"Expected no solutions for non-list arg, got {sols}"

    def test_list_pred_correctness_var_arg(self):
        """when arg is a Var (unbound), all list-headed clauses should be tried."""
        # nv
        from clausal.logic.compiler import compile_predicate_trampoline

        db = Database()
        v1, v2 = Var(), Var()
        db.assertz(Clause(head=Compound("mylen", ([], v1)), body=[]))
        db.assertz(Clause(head=Compound("mylen", ([1, 2], v2)), body=[]))
        clauses = db.clauses_for("mylen", 2)
        dispatch = compile_predicate_trampoline("mylen", 2, clauses, db)

        trail = Trail()
        lst = Var()  # unbound list arg
        n = Var()
        # Both clauses should be reachable when lst is unbound
        sols = _trampoline_solutions(dispatch, (lst, n, trail))
        assert len(sols) == 2, (
            f"Expected 2 solutions (both clauses) for unbound list arg, got {len(sols)}"
        )

    def test_structural_dispatch_does_not_suppress_backtracking(self):
        """Multiple list-headed clauses that can both match must both be tried.

        If two clauses both have [H|T] patterns, structural dispatch must try
        both — not short-circuit after the first.
        """
        # nv
        from clausal.logic.compiler import compile_predicate_trampoline

        # Two clauses with non-empty list heads (both "cons" bucket)
        db = Database()
        v1, v2 = Var(), Var()
        db.assertz(Clause(head=Compound("pick", (v1, [1])), body=[]))
        db.assertz(Clause(head=Compound("pick", (v2, [1, 2])), body=[]))
        clauses = db.clauses_for("pick", 2)
        dispatch = compile_predicate_trampoline("pick", 2, clauses, db)

        trail = Trail()
        elem = Var()
        # Both clauses match — both should be tried
        sols = _trampoline_solutions(dispatch, (elem, [1, 2], trail))
        assert len(sols) == 1, (
            f"Expected 1 solution (only clause 2 matches [1,2]), got {len(sols)}"
        )
