"""Structural tests for compiler optimizations (phases 1, 2, 3).

These tests inspect the generated AST or source code to confirm that
the optimizations were actually applied — not just that behavior is
correct.  Behavioral correctness is already covered by the existing
test suites (test_compiler_trampoline.py, test_reified_ite.py, etc.).

Phase 1 — Deref-once:
    For any predicate with N≥2 clauses and arity≥1, the generated function
    should contain exactly K deref() calls (one per argument), not N*K.

Phase 2 — ITE duplicate compilation:
    The then/else branches of a reified if-then-else should each appear
    exactly once in the generated AST, not twice.

Phase 3 — Redundant Or mark:
    A compiled disjunction should contain exactly one trail.mark() call,
    not two.
"""

from __future__ import annotations

import ast

import pytest

from clausal.logic.compiler import (
    compile_predicate_trampoline_ast,
    compile_goal_trampoline,
)
from clausal.logic.database import Clause, Database
from clausal.logic.variables import Var, Trail, deref, unify
from clausal.terms import Compound
from clausal.pythonic_ast.nodes import (
    Or, Unify as Is, IfExpr, Gt,
    Call, LoadName,
)


# ── AST walking helpers ────────────────────────────────────────────────────────


def _count_calls_to(func_name: str, tree: ast.AST) -> int:
    """Count how many times a bare function name is called in *tree*."""
    count = 0
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == func_name
        ):
            count += 1
    return count


def _count_method_calls(obj_name: str, method_name: str, tree: ast.AST) -> int:
    """Count calls of the form obj_name.method_name(...) in *tree*."""
    count = 0
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == obj_name
            and node.func.attr == method_name
        ):
            count += 1
    return count


def _count_assignments_to(target_name: str, tree: ast.AST) -> int:
    """Count simple assignments whose first target is *target_name*."""
    count = 0
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and node.targets
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == target_name
        ):
            count += 1
    return count


def _count_ast_nodes(node_type: type, tree: ast.AST) -> int:
    return sum(1 for _ in ast.walk(tree) if isinstance(_, node_type))


def _names_in_match_subjects(tree: ast.FunctionDef) -> list[str]:
    """Return all Name ids that appear as direct elements of Match subjects."""
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Match):
            subj = node.subject
            # subject is typically a Tuple
            elts = subj.elts if isinstance(subj, ast.Tuple) else [subj]
            for elt in elts:
                if isinstance(elt, ast.Name):
                    names.append(elt.id)
    return names


# ── Fixtures ───────────────────────────────────────────────────────────────────


def _make_multi_clause_predicate(n_clauses: int, arity: int = 2) -> tuple:
    """Build a predicate with n_clauses fact clauses and compile its AST."""
    db = Database()
    for i in range(n_clauses):
        args = tuple(range(i * arity, i * arity + arity))
        db.assertz(Clause(head=Compound("foo", args), body=[]))
    clauses = db.clauses_for("foo", arity)
    func_def = compile_predicate_trampoline_ast("foo", arity, clauses, db)
    return db, clauses, func_def


# ── Phase 1: Deref-once ────────────────────────────────────────────────────────


class TestDerefOnce:
    """The generated function calls deref() exactly arity times, not N*arity."""

    def test_single_clause_one_deref_per_arg(self):
        _, _, func_def = _make_multi_clause_predicate(1, arity=2)
        assert _count_calls_to("deref", func_def) == 2

    def test_two_clauses_still_one_deref_per_arg(self):
        _, _, func_def = _make_multi_clause_predicate(2, arity=2)
        # Would be 4 without the optimization; should be 2.
        assert _count_calls_to("deref", func_def) == 2

    def test_three_clauses_still_one_deref_per_arg(self):
        _, _, func_def = _make_multi_clause_predicate(3, arity=2)
        # Would be 6 without the optimization; should be 2.
        assert _count_calls_to("deref", func_def) == 2

    def test_five_clauses_arity3_one_deref_per_arg(self):
        _, _, func_def = _make_multi_clause_predicate(5, arity=3)
        # Would be 15 without the optimization; should be 3.
        assert _count_calls_to("deref", func_def) == 3

    def test_match_subjects_use_deref_locals(self):
        """Match subjects reference _d0, _d1 locals, not raw arg names."""
        _, _, func_def = _make_multi_clause_predicate(3, arity=2)
        subject_names = _names_in_match_subjects(func_def)
        # Every element of every match subject should be a _d<i> local.
        assert all(n.startswith("_d") for n in subject_names), \
            f"Expected _d<i> in match subjects, got: {subject_names}"

    def test_deref_locals_assigned_before_first_match(self):
        """The _d0 assignment must come before the first Match statement."""
        _, _, func_def = _make_multi_clause_predicate(2, arity=1)
        body = func_def.body
        # Find index of first _d0 assign and first Match
        assign_idx = next(
            (i for i, s in enumerate(body)
             if isinstance(s, ast.Assign)
             and isinstance(s.targets[0], ast.Name)
             and s.targets[0].id == "_d0"),
            None,
        )
        match_idx = next(
            (i for i, s in enumerate(body) if isinstance(s, ast.Match)),
            None,
        )
        assert assign_idx is not None, "_d0 assignment not found"
        assert match_idx is not None, "No Match statement found"
        assert assign_idx < match_idx, \
            f"_d0 assigned at {assign_idx} but first Match at {match_idx}"

    def test_arity_zero_no_deref_assigns(self):
        """Arity-0 predicates have no arguments to deref."""
        db = Database()
        db.assertz(Clause(head=Compound("fact0", ()), body=[]))
        db.assertz(Clause(head=Compound("fact0", ()), body=[]))
        clauses = db.clauses_for("fact0", 0)
        func_def = compile_predicate_trampoline_ast("fact0", 0, clauses, db)
        # Should have zero deref calls
        assert _count_calls_to("deref", func_def) == 0

    def test_deref_count_scales_with_arity_not_clauses(self):
        """Verify the scaling property: deref count == arity, not n_clauses * arity."""
        for n in range(1, 6):
            _, _, func_def = _make_multi_clause_predicate(n, arity=2)
            n_derefs = _count_calls_to("deref", func_def)
            assert n_derefs == 2, \
                f"{n} clauses, arity 2: expected 2 deref calls, got {n_derefs}"


# ── Phase 2: ITE duplicate compilation ────────────────────────────────────────


class TestITENoDuplication:
    """Reified ITE compiles then/else branches exactly once each.

    The key invariant: after Phase 2, `then_stmts` is computed once and the
    same Python list object is used for both the `_reif is True` branch body
    and the `unify_branch` inside the undetermined block.  We test this with
    AST object-identity checks on the raw statement lists returned by
    compile_goal_trampoline.

    Generated AST structure for reified-eq ITE:
        stmts[0]  = _reif = _reify_eq(...)
        stmts[1]  = ast.If(_reif is True, body=then_stmts,
                        orelse=[ast.If(_reif is False, body=else_stmts,
                                    orelse=undetermined)])
    where undetermined = [mark, If(unify, unify_branch), undo, If(dif, dif_branch)]
    and after Phase 2: unify_branch is then_stmts, dif_branch is else_stmts.

    For reified-fd ITE the undetermined block differs slightly (two mark/undo
    pairs) but the then/else identity invariant is the same.
    """

    def _compile_ite(self, test_goal, then_goal, else_goal):
        """Compile an IfExpr body goal to a list of AST statements."""
        db = Database()
        x, y = Var(), Var()
        vc = {x._id: "_vx", y._id: "_vy"}
        ite = IfExpr(test=test_goal, body=then_goal, orelse=else_goal)
        k = []  # no continuation
        stmts = compile_goal_trampoline(ite, db, vc, "trail", k)
        return stmts

    # ── Helpers to navigate the generated AST ─────────────────────────────────

    def _outer_if(self, stmts):
        """stmts[1]: the If node whose body is true_stmts."""
        assert len(stmts) == 2, f"Expected [reif_assign, If], got {len(stmts)} stmts"
        assert isinstance(stmts[1], ast.If)
        return stmts[1]

    def _true_branch(self, stmts):
        """The body of 'if _reif is True' — should be then_stmts."""
        return self._outer_if(stmts).body

    def _false_branch(self, stmts):
        """The body of 'elif _reif is False' — should be else_stmts."""
        outer = self._outer_if(stmts)
        assert len(outer.orelse) == 1 and isinstance(outer.orelse[0], ast.If)
        return outer.orelse[0].body

    def _undetermined_block(self, stmts):
        """The else: block (undetermined) of the nested If chain."""
        outer = self._outer_if(stmts)
        inner = outer.orelse[0]
        return inner.orelse  # list of stmts: [mark, if unify, undo, ...]

    # ── Reified equality ITE ──────────────────────────────────────────────────

    def test_reified_eq_true_branch_is_unify_branch(self):
        """true_stmts and unify_branch are the same Python list object."""
        x, y = Var(), Var()
        test = Is(left=x, right=1)
        then = Is(left=y, right=99991)
        else_ = Is(left=y, right=88881)
        stmts = self._compile_ite(test, then, else_)
        true_branch = self._true_branch(stmts)
        # undetermined[1] is If(unify, body=unify_branch)
        undetermined = self._undetermined_block(stmts)
        unify_if = undetermined[1]
        assert isinstance(unify_if, ast.If)
        assert true_branch is unify_if.body, (
            "then_stmts and unify_branch should be the same list object "
            "(compiled once, reused)"
        )

    def test_reified_eq_false_branch_is_dif_branch(self):
        """false_stmts and dif_branch are the same Python list object."""
        x, y = Var(), Var()
        test = Is(left=x, right=1)
        then = Is(left=y, right=99991)
        else_ = Is(left=y, right=88881)
        stmts = self._compile_ite(test, then, else_)
        false_branch = self._false_branch(stmts)
        undetermined = self._undetermined_block(stmts)
        # undetermined[3] is If(_dif, body=dif_branch)
        dif_if = undetermined[3]
        assert isinstance(dif_if, ast.If)
        assert false_branch is dif_if.body, (
            "else_stmts and dif_branch should be the same list object "
            "(compiled once, reused)"
        )

    def test_reified_eq_only_two_compilations(self):
        """_reify_eq is called exactly once; only two goal compilations occur."""
        x, y = Var(), Var()
        test = Is(left=x, right=1)
        then = Is(left=y, right=1)
        else_ = Is(left=y, right=2)
        stmts = self._compile_ite(test, then, else_)
        module = ast.Module(body=stmts, type_ignores=[])
        ast.fix_missing_locations(module)
        assert _count_calls_to("_reify_eq", module) == 1
        # unify from the undetermined block (one for the test, one per Is branch)
        # The key: only 1 '_dif' call (else compiled once)
        assert _count_calls_to("_dif", module) == 1

    # ── Reified FD ITE ────────────────────────────────────────────────────────

    def _fd_true_branch(self, stmts):
        return self._outer_if(stmts).body

    def _fd_false_branch(self, stmts):
        return self._outer_if(stmts).orelse[0].body

    def _fd_undetermined_block(self, stmts):
        return self._outer_if(stmts).orelse[0].orelse

    def test_reified_fd_true_branch_is_fd_then_stmts(self):
        """then_stmts used for 'if _reif is True' is the same object as the fd_true branch."""
        x, y = Var(), Var()
        test = Gt(left=x, right=5)
        then = Is(left=y, right=99992)
        else_ = Is(left=y, right=88882)
        stmts = self._compile_ite(test, then, else_)
        true_branch = self._fd_true_branch(stmts)
        undetermined = self._fd_undetermined_block(stmts)
        # FD undetermined: [mark, if fd_true → then_stmts, undo, mark, if fd_false → else_stmts, undo]
        fd_true_if = undetermined[1]
        assert isinstance(fd_true_if, ast.If)
        assert true_branch is fd_true_if.body, (
            "then_stmts for 'if _reif is True' and fd_then_stmts should be the same object"
        )

    def test_reified_fd_false_branch_is_fd_else_stmts(self):
        """else_stmts used for 'elif _reif is False' is the same as the fd_false branch."""
        x, y = Var(), Var()
        test = Gt(left=x, right=5)
        then = Is(left=y, right=99992)
        else_ = Is(left=y, right=88882)
        stmts = self._compile_ite(test, then, else_)
        false_branch = self._fd_false_branch(stmts)
        undetermined = self._fd_undetermined_block(stmts)
        fd_false_if = undetermined[4]
        assert isinstance(fd_false_if, ast.If)
        assert false_branch is fd_false_if.body, (
            "else_stmts for 'elif _reif is False' and fd_else_stmts should be the same object"
        )

    def test_reified_fd_only_one_reify_call(self):
        x, y = Var(), Var()
        test = Gt(left=x, right=5)
        then = Is(left=y, right=1)
        else_ = Is(left=y, right=2)
        stmts = self._compile_ite(test, then, else_)
        module = ast.Module(body=stmts, type_ignores=[])
        ast.fix_missing_locations(module)
        assert _count_calls_to("_reify_fd", module) == 1


# ── Phase 3: Or mark elimination ──────────────────────────────────────────────


class TestOrMarkElimination:
    """Compiled disjunction emits exactly one trail.mark() call.

    To isolate the Or's own mark from marks introduced by body goals, we use
    True (the always-succeed goal) as branches.  True compiles to k_stmts
    directly — no trail.mark() of its own — so every mark/undo we see comes
    from the Or itself.
    """

    def _compile_or_true(self, k_stmts=None):
        """Compile Or(True, True) with an optional continuation."""
        db = Database()
        goal = Or(left=True, right=True)
        stmts = compile_goal_trampoline(goal, db, {}, "trail", k_stmts or [])
        return stmts

    def _compile_or_nested_true(self):
        """Compile Or(Or(True, True), True) — two nested disjunctions."""
        db = Database()
        inner = Or(left=True, right=True)
        outer = Or(left=inner, right=True)
        stmts = compile_goal_trampoline(outer, db, {}, "trail", [])
        return stmts

    def test_or_has_exactly_one_mark_call(self):
        """Or(True, True): single trail.mark() before the left branch."""
        stmts = self._compile_or_true()
        module = ast.Module(body=stmts, type_ignores=[])
        ast.fix_missing_locations(module)
        n_marks = _count_method_calls("trail", "mark", module)
        assert n_marks == 1, \
            f"Expected 1 trail.mark() call in Or(True,True), got {n_marks}"

    def test_or_has_exactly_two_undo_calls(self):
        """Or(True, True): two trail.undo() calls, one after each branch."""
        stmts = self._compile_or_true()
        module = ast.Module(body=stmts, type_ignores=[])
        ast.fix_missing_locations(module)
        n_undos = _count_method_calls("trail", "undo", module)
        assert n_undos == 2, \
            f"Expected 2 trail.undo() calls in Or(True,True), got {n_undos}"

    def test_or_mark_is_first_statement(self):
        """The single trail.mark() is the very first statement emitted."""
        stmts = self._compile_or_true()
        first = stmts[0]
        assert isinstance(first, ast.Assign), \
            f"Expected first stmt to be mark assign, got {type(first).__name__}"
        rhs = first.value
        assert (
            isinstance(rhs, ast.Call)
            and isinstance(rhs.func, ast.Attribute)
            and rhs.func.attr == "mark"
        ), f"Expected trail.mark() on RHS of first stmt, got {ast.unparse(rhs)}"

    def test_or_mark_variable_not_reassigned(self):
        """The mark variable is assigned exactly once (not reassigned mid-Or)."""
        stmts = self._compile_or_true()
        # The first stmt assigns the mark variable; get its name.
        mark_name = stmts[0].targets[0].id
        # Count how many times this specific variable is assigned in the stmts.
        count = _count_assignments_to(mark_name, ast.Module(body=stmts, type_ignores=[]))
        assert count == 1, \
            f"Mark variable '{mark_name}' assigned {count} times, expected 1"

    def test_nested_or_has_two_marks(self):
        """Or(Or(True,True), True): exactly 2 marks — one per disjunction level."""
        stmts = self._compile_or_nested_true()
        module = ast.Module(body=stmts, type_ignores=[])
        ast.fix_missing_locations(module)
        n_marks = _count_method_calls("trail", "mark", module)
        assert n_marks == 2, \
            f"Expected 2 trail.mark() calls for Or(Or(T,T),T), got {n_marks}"

    def test_or_correctness_still_holds(self):
        """Behavioral sanity: disjunction still yields both solutions."""
        from clausal.logic.trampoline import StepGenerator, DONE as _DONE
        from clausal.logic.compiler import compile_predicate_trampoline

        db = Database()
        x = Var()
        clauses = [
            Clause(
                head=Compound("choose", (x,)),
                body=[Or(left=Is(left=x, right=1), right=Is(left=x, right=2))],
            )
        ]
        fn = compile_predicate_trampoline("choose", 1, clauses, db)
        trail = Trail()
        v = Var()
        results = []
        root = StepGenerator(fn, None, v, trail)
        gen, val = root.send(None)
        while True:
            if gen is None:
                if val is _DONE:
                    break
                results.append(deref(v))
                gen, val = root.send(None)
            else:
                gen, val = gen.send(val)
        assert results == [1, 2], f"Expected [1, 2], got {results}"
