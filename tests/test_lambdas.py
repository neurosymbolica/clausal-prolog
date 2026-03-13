"""Tests for V2-9 — Pythonic Lambdas (Goal Closures).

Phase 1: TermTransformer — implicit capture via shared seen_vars
Phase 2: Compiler — Lambda → simple-mode dispatch function
Phase 3: Runtime — call_goal builtins
Phase 4: Integration — lambdas in .clausal files
"""
from __future__ import annotations

import ast
import dataclasses

import pytest

from clausal.pythonic_ast import nodes as sa
from clausal.templating.term_rewriting import TermTransformer, _is_logic_var_name
from clausal.logic.compiler import (
    compile_predicate_trampoline as compile_predicate,
    compile_goal,
    compile_body,
    term_to_ast_expr,
    _compile_goal_lambda,
    _flatten_conjunction,
)
from clausal.logic.database import Clause, Database
from clausal.logic.trampoline import StepGenerator, DONE
from clausal.logic.variables import Var, Trail, deref, unify, is_var
from clausal.terms import (
    And, Or, Not,
    Unify, DoesNotUnify, Evaluate,
    Call, LoadName,
    Add, Compound,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _ns():
    """Namespace with all simple_ast names + real Var constructor."""
    ns = {name: getattr(sa, name) for name in sa.__all__}
    ns["Var"] = Var
    return ns


def term_eval(src: str, expected_type: type = None):
    """Parse an expression, run TermTransformer, evaluate → simple_ast node."""
    tree = ast.parse(src, mode="eval")
    ast.fix_missing_locations(tree)
    transformed = TermTransformer().visit(tree.body)
    expr_tree = ast.fix_missing_locations(ast.Expression(body=transformed))
    result = eval(compile(expr_tree, "<test>", "eval"), _ns())
    if expected_type is not None:
        assert isinstance(result, expected_type)
    return result


def term_eval_with_scope(src: str, seen_vars: set[str]):
    """Parse with pre-populated seen_vars to simulate enclosing scope."""
    tree = ast.parse(src, mode="eval")
    ast.fix_missing_locations(tree)
    tt = TermTransformer()
    tt.seen_vars = seen_vars.copy()
    transformed = tt.visit(tree.body)
    ns = _ns()
    # Pre-allocate Vars for seen_vars in the namespace
    for name in seen_vars:
        if _is_logic_var_name(name):
            ns[name] = Var()
    expr_tree = ast.fix_missing_locations(ast.Expression(body=transformed))
    result = eval(compile(expr_tree, "<test>", "eval"), ns)
    return result, ns


def _run_dispatch(fn, *args_and_trail):
    """Drive a trampoline-protocol fn, yield per solution."""
    root = StepGenerator(fn, None, *args_and_trail)
    gen, value = root.send(None)
    while True:
        if gen is None:
            if value is DONE:
                return
            yield value
            gen, value = root.send(None)
        else:
            gen, value = gen.send(value)


def _drive_simple(fn, *args):
    """Drive a simple-mode dispatch fn (yields None per solution)."""
    return list(fn(*args))


def _run_and_deref(fn, var, *args_and_trail):
    """Drive a trampoline fn, collect deref'd values of var at each solution."""
    results = []
    for _ in _run_dispatch(fn, *args_and_trail):
        results.append(deref(var))
    return results


# ── Phase 1: TermTransformer ────────────────────────────────────────────────


class TestTermTransformerCapture:
    """TermTransformer inherits seen_vars for lambda implicit capture."""

    def test_lambda_param_generates_loadname(self):
        """Lambda param reference in body is a LoadName (not a Var)."""
        node = term_eval("lambda X_: X_", sa.Lambda)
        # X_ in the body should be a LoadName, not a Var
        assert isinstance(node.body, sa.LoadName)
        assert node.body.name == "X_"

    def test_lambda_captures_enclosing_var(self):
        """Lambda body referencing enclosing var gets the same Var."""
        node, ns = term_eval_with_scope(
            "lambda X_: Z_", seen_vars={"Z_"}
        )
        assert isinstance(node, sa.Lambda)
        # Z_ in the body should be the same Var from the enclosing scope
        assert node.body is ns["Z_"]

    def test_lambda_body_only_var_does_not_leak(self):
        """Var introduced in lambda body does not appear in enclosing scope."""
        tree = ast.parse("lambda X_: X_", mode="eval")
        ast.fix_missing_locations(tree)
        tt = TermTransformer()
        original_seen = tt.seen_vars.copy()
        tt.visit(tree.body)
        # X_ should NOT have been added to the outer transformer's seen_vars
        assert tt.seen_vars == original_seen

    def test_lambda_captures_multiple_enclosing_vars(self):
        """Lambda can capture multiple enclosing scope vars."""
        node, ns = term_eval_with_scope(
            "lambda X_: X_", seen_vars={"A_", "B_"}
        )
        # The captured vars are accessible from the outer namespace
        assert isinstance(node, sa.Lambda)

    def test_nested_lambda_captures_outer(self):
        """Nested lambda captures from the outermost scope."""
        # Inner lambda should see the var from the outermost scope
        src = "lambda X_: (lambda Y_: Z_)"
        node, ns = term_eval_with_scope(src, seen_vars={"Z_"})
        assert isinstance(node, sa.Lambda)
        inner = node.body
        assert isinstance(inner, sa.Lambda)
        # Inner lambda body Z_ should be the enclosing scope's Z_
        assert inner.body is ns["Z_"]

    def test_anonymous_underscore_in_lambda(self):
        """_ in lambda body is a fresh Var (anonymous)."""
        node = term_eval("lambda X_: _", sa.Lambda)
        # Body should be a Var (fresh anonymous)
        assert is_var(node.body)

    def test_param_refs_are_loadname(self):
        """Lambda with logic var params produces LoadName refs in body."""
        node = term_eval("lambda X_, Y_: X_", sa.Lambda)
        # Body is a LoadName for param X_
        assert isinstance(node.body, sa.LoadName)
        assert node.body.name == "X_"
        # No _param_vars attribute needed
        assert not hasattr(node, "_param_vars")

    def test_non_logic_param_lambda(self):
        """Lambda with non-logic-var params has no _load_names behavior."""
        node = term_eval("lambda x, y: x + y", sa.Lambda)
        # Non-logic-var params are not LoadName'd
        assert not hasattr(node, "_param_vars")

    def test_nested_lambda_outer_param_is_loadname(self):
        """Inner lambda references outer param as LoadName (not Var)."""
        src = "lambda X_: (lambda Y_: X_)"
        node = term_eval(src, sa.Lambda)
        inner = node.body
        assert isinstance(inner, sa.Lambda)
        # X_ in inner body should be LoadName (inherited from outer _load_names)
        assert isinstance(inner.body, sa.LoadName)
        assert inner.body.name == "X_"


# ── Phase 2: Compiler ───────────────────────────────────────────────────────


class TestCompileLambda:
    """_compile_goal_lambda generates a simple-mode dispatch function."""

    def _make_lambda(self, params, body):
        """Helper: create a Lambda node with params and body."""
        param_nodes = [
            sa.PosOrKwParam(name=p) for p in params
        ]
        return sa.Lambda(
            params=sa.Params(params=param_nodes),
            body=body,
        )

    def test_compile_lambda_produces_funcdef(self):
        """_compile_goal_lambda returns a name and FunctionDef."""
        # Body: X_ := 1 — use LoadName for param ref
        lam = self._make_lambda(["X_"], Evaluate(left=LoadName(name="X_"), right=1))
        db = Database("test")
        name, fdef = _compile_goal_lambda(lam, {}, db, "trail")
        assert name.startswith("_lambda")
        assert isinstance(fdef, ast.FunctionDef)
        assert fdef.name == name

    def test_compile_lambda_param_is_func_arg(self):
        """Compiled lambda has params as function arguments."""
        lam = self._make_lambda(["X_"], Evaluate(left=LoadName(name="X_"), right=1))
        db = Database("test")
        name, fdef = _compile_goal_lambda(lam, {}, db, "trail")
        arg_names = [a.arg for a in fdef.args.args]
        assert "X_" in arg_names
        assert "trail" in arg_names
        assert "k" in arg_names

    def test_compile_lambda_captured_var_not_in_params(self):
        """Captured vars become closure references, not function args."""
        z = Var()  # captured
        # body: X_ := Z_ + 1 — X_ is LoadName (param), z is Var (captured)
        lam = self._make_lambda(
            ["X_"],
            Evaluate(left=LoadName(name="X_"), right=Add(left=z, right=1)),
        )
        enclosing_vc = {z._id: "_v_z"}
        db = Database("test")
        name, fdef = _compile_goal_lambda(lam, enclosing_vc, db, "trail")
        arg_names = [a.arg for a in fdef.args.args]
        assert "X_" in arg_names
        assert "_v_z" not in arg_names  # captured, not a param

    def test_flatten_conjunction(self):
        """_flatten_conjunction flattens And nodes."""
        a = Evaluate(left=Var(), right=1)
        b = Evaluate(left=Var(), right=2)
        c = Evaluate(left=Var(), right=3)
        goal = And(left=a, right=And(left=b, right=c))
        result = _flatten_conjunction(goal)
        assert result == [a, b, c]

    def test_flatten_single(self):
        """_flatten_conjunction with non-And returns singleton list."""
        a = Evaluate(left=Var(), right=1)
        assert _flatten_conjunction(a) == [a]


# ── Phase 3: Runtime — call_goal and lambda execution ────────────────────────


class TestLambdaRuntime:
    """Compiled lambdas can be called and produce solutions."""

    def _compile_and_run_predicate(self, clauses, functor, arity, db=None):
        """Compile clauses and return the dispatch function."""
        if db is None:
            db = Database("test")
        fn = compile_predicate(functor, arity, clauses, db)
        return fn, db

    def test_call_goal_1_with_zero_arg_lambda(self):
        """call_goal/1 calls a zero-arg goal closure."""
        from clausal.logic.builtins import _BUILTINS

        trail = Trail()
        fn = _BUILTINS[("call_goal", 1)]

        # Create a simple closure that succeeds once
        def my_goal(trail, k):
            yield None
            return; yield

        results = list(_run_dispatch(fn, my_goal, trail))
        assert len(results) == 1

    def test_call_goal_2_with_one_arg_lambda(self):
        """call_goal/2 passes an extra arg to the closure."""
        from clausal.logic.builtins import _BUILTINS

        trail = Trail()
        result_var = Var()

        def my_goal(arg1, trail, k):
            if unify(result_var, arg1, trail):
                yield None
            return; yield

        fn = _BUILTINS[("call_goal", 2)]
        results = list(_run_dispatch(fn, my_goal, 42, trail))
        assert len(results) == 1
        assert deref(result_var) == 42

    def test_call_goal_3_with_two_arg_lambda(self):
        """call_goal/3 passes two extra args to the closure."""
        from clausal.logic.builtins import _BUILTINS

        trail = Trail()
        result_var = Var()

        def my_goal(arg1, arg2, trail, k):
            if unify(result_var, arg1 + arg2, trail):
                yield None
            return; yield

        fn = _BUILTINS[("call_goal", 3)]
        results = list(_run_dispatch(fn, my_goal, 3, 4, trail))
        assert len(results) == 1
        assert deref(result_var) == 7

    def test_call_goal_with_failing_lambda(self):
        """call_goal with a failing closure produces no solutions."""
        from clausal.logic.builtins import _BUILTINS

        trail = Trail()

        def failing_goal(trail, k):
            return; yield

        fn = _BUILTINS[("call_goal", 1)]
        results = list(_run_dispatch(fn, failing_goal, trail))
        assert len(results) == 0

    def test_call_goal_with_multi_solution_lambda(self):
        """call_goal with a closure that yields multiple solutions."""
        from clausal.logic.builtins import _BUILTINS

        trail = Trail()
        result_var = Var()

        def multi_goal(arg1, trail, k):
            for val in [10, 20, 30]:
                mark = trail.mark()
                if unify(arg1, val, trail):
                    yield None
                trail.undo(mark)
            return; yield

        fn = _BUILTINS[("call_goal", 2)]
        results = list(_run_dispatch(fn, multi_goal, result_var, trail))
        assert len(results) == 3


# ── Phase 2+3 Integration: compiled lambda with call_goal ────────────────────


class TestCompiledLambdaExecution:
    """End-to-end: compile a predicate with a lambda arg, run it."""

    def test_lambda_arithmetic_body(self):
        """Lambda with := arithmetic body works end-to-end."""
        # Build: test(X_, Result_) <- call_goal(lambda Y_: Result_ := Y_ + 1, X_)
        x = Var()
        result = Var()

        lam = sa.Lambda(
            params=sa.Params(params=[sa.PosOrKwParam(name="Y_")]),
            body=Evaluate(left=result, right=Add(left=LoadName(name="Y_"), right=1)),
        )

        body = [Call(func=LoadName(name="call_goal"), args=[lam, x], kwargs=[])]
        clause = Clause(
            head=Compound("test", (x, result)),
            body=body,
        )
        db = Database("test")
        fn = compile_predicate("test", 2, [clause], db)

        trail = Trail()
        x_in = Var()
        r_out = Var()
        unify(x_in, 5, trail)
        results = _run_and_deref(fn, r_out, x_in, r_out, trail)
        assert results == [6]

    def test_lambda_captures_enclosing_var(self):
        """Lambda captures a variable from the enclosing clause."""
        # Build: test(Z_, Result_) <- call_goal(lambda X_: Result_ := X_ + Z_, 10)
        z = Var()
        result = Var()

        lam = sa.Lambda(
            params=sa.Params(params=[sa.PosOrKwParam(name="X_")]),
            body=Evaluate(left=result, right=Add(left=LoadName(name="X_"), right=z)),
        )

        body = [Call(func=LoadName(name="call_goal"), args=[lam, 10], kwargs=[])]
        clause = Clause(
            head=Compound("test", (z, result)),
            body=body,
        )
        db = Database("test")
        fn = compile_predicate("test", 2, [clause], db)

        trail = Trail()
        z_in = Var()
        r_out = Var()
        unify(z_in, 3, trail)
        results = _run_and_deref(fn, r_out, z_in, r_out, trail)
        assert results == [13]  # 10 + 3

    def test_lambda_with_unification_body(self):
        """Lambda body using 'is' (unification) works."""
        # test(R_) <- call_goal(lambda X_: X_ is 42, R_)
        r = Var()
        lam = sa.Lambda(
            params=sa.Params(params=[sa.PosOrKwParam(name="X_")]),
            body=Unify(left=LoadName(name="X_"), right=42),
        )

        body = [Call(func=LoadName(name="call_goal"), args=[lam, r], kwargs=[])]
        clause = Clause(
            head=Compound("test_unify", (r,)),
            body=body,
        )
        db = Database("test")
        fn = compile_predicate("test_unify", 1, [clause], db)

        trail = Trail()
        r_out = Var()
        results = _run_and_deref(fn, r_out, r_out, trail)
        assert results == [42]

    def test_lambda_body_fails(self):
        """Lambda with failing body produces no solutions."""
        # test() <- call_goal(lambda X_: X_ is not X_, 42)
        lam = sa.Lambda(
            params=sa.Params(params=[sa.PosOrKwParam(name="X_")]),
            body=DoesNotUnify(left=LoadName(name="X_"), right=LoadName(name="X_")),
        )

        body = [Call(func=LoadName(name="call_goal"), args=[lam, 42], kwargs=[])]
        clause = Clause(
            head=Compound("test_fail", ()),
            body=body,
        )
        db = Database("test")
        fn = compile_predicate("test_fail", 0, [clause], db)

        trail = Trail()
        results = list(_run_dispatch(fn, trail))
        assert len(results) == 0

    def test_lambda_body_conjunction(self):
        """Lambda body with And (conjunction) works."""
        # test(R_) <- call_goal(lambda X_, Y_: (T_ := X_ + 1 and Y_ := T_ * 2), 5, R_)
        t = Var()
        r = Var()
        lam = sa.Lambda(
            params=sa.Params(params=[
                sa.PosOrKwParam(name="X_"),
                sa.PosOrKwParam(name="Y_"),
            ]),
            body=And(
                left=Evaluate(left=t, right=Add(left=LoadName(name="X_"), right=1)),
                right=Evaluate(left=LoadName(name="Y_"), right=sa.Mult(left=t, right=2)),
            ),
        )

        body = [Call(func=LoadName(name="call_goal"), args=[lam, 5, r], kwargs=[])]
        clause = Clause(
            head=Compound("test_conj", (r,)),
            body=body,
        )
        db = Database("test")
        fn = compile_predicate("test_conj", 1, [clause], db)

        trail = Trail()
        r_out = Var()
        results = _run_and_deref(fn, r_out, r_out, trail)
        # T_ = 5 + 1 = 6, Y_ = 6 * 2 = 12
        assert results == [12]


# ── Phase 4: Integration with .clausal files ─────────────────────────────────


class TestLambdaImport:
    """Lambda in .clausal files: TermTransformer + compiler + import hook."""

    def _query(self, mod, goal_fn, *args):
        """Helper: build goal, query, return results."""
        from clausal.logic.solve import query
        r = Var()
        logic_mod = mod.__dict__["$module"]
        goal = Call(func=LoadName(name=goal_fn), args=list(args) + [r], kwargs=[])
        return [row["r"] for row in query(goal, {"r": r}, logic_mod)]

    def test_lambda_unify_in_clausal_file(self, tmp_path):
        """Lambda with unification body in a .clausal file."""
        clausal_file = tmp_path / "lambda_test.clausal"
        clausal_file.write_text(
            "-module(lambda_test, [apply_val/2])\n"
            "\n"
            "apply_val(Result_, Val_) <- call_goal((lambda X_: Result_ is X_), Val_)\n"
        )

        from clausal.import_hook import _load_module
        mod = _load_module("lambda_test", str(clausal_file))
        results = self._query(mod, "apply_val", 42)
        assert results == [42]

    def test_lambda_captures_head_var_in_clausal(self, tmp_path):
        """Lambda in .clausal captures a variable from the clause head."""
        clausal_file = tmp_path / "capture_test.clausal"
        clausal_file.write_text(
            "-module(capture_test, [bind_z/2])\n"
            "\n"
            "bind_z(Z_, Result_) <- call_goal((lambda X_: Result_ is X_), Z_)\n"
        )

        from clausal.import_hook import _load_module
        mod = _load_module("capture_test", str(clausal_file))
        results = self._query(mod, "bind_z", 99)
        assert results == [99]

    def test_lambda_with_conjunction_in_clausal(self, tmp_path):
        """Lambda with conjunction body in .clausal file."""
        clausal_file = tmp_path / "conj_test.clausal"
        clausal_file.write_text(
            "-module(conj_test, [bind_pair/3])\n"
            "\n"
            "bind_pair(A_, B_, Result_) <- call_goal((lambda X_, Y_: (X_ is A_ and Y_ is B_ and Result_ is [X_, Y_])), A_, B_)\n"
        )

        from clausal.import_hook import _load_module
        mod = _load_module("conj_test", str(clausal_file))
        results = self._query(mod, "bind_pair", 1, 2)
        assert results == [[1, 2]]

    def test_lambda_zero_arg_in_clausal(self, tmp_path):
        """Zero-arg lambda (goal closure) in .clausal file."""
        clausal_file = tmp_path / "zero_arg_test.clausal"
        clausal_file.write_text(
            "-module(zero_arg_test, [run_goal/1])\n"
            "\n"
            "run_goal(Result_) <- call_goal((lambda: Result_ is 42))\n"
        )

        from clausal.import_hook import _load_module
        mod = _load_module("zero_arg_test", str(clausal_file))
        from clausal.logic.solve import query
        r = Var()
        logic_mod = mod.__dict__["$module"]
        goal = Call(func=LoadName(name="run_goal"), args=[r], kwargs=[])
        results = [row["r"] for row in query(goal, {"r": r}, logic_mod)]
        assert results == [42]

    def test_lambda_calls_user_predicate(self, tmp_path):
        """Lambda body calling a user predicate via _tramp_call bridge."""
        clausal_file = tmp_path / "lambda_pred_call.clausal"
        clausal_file.write_text(
            "-module(lambda_pred_call, [double/2, apply_double/2])\n"
            "\n"
            "double(X_, Y_) <- (Y_ := X_ + X_)\n"
            "\n"
            "apply_double(Val_, Result_) <- call_goal((lambda X_: double(X_, Result_)), Val_)\n"
        )

        from clausal.import_hook import _load_module
        mod = _load_module("lambda_pred_call", str(clausal_file))
        results = self._query(mod, "apply_double", 7)
        assert results == [14]

    def test_lambda_calls_multi_solution_predicate(self, tmp_path):
        """Lambda body calling a multi-solution predicate collects all answers."""
        clausal_file = tmp_path / "lambda_multi.clausal"
        clausal_file.write_text(
            "-module(lambda_multi, [color/1, get_color/1])\n"
            "\n"
            'color("red"),\n'
            'color("green"),\n'
            'color("blue"),\n'
            "\n"
            "get_color(C_) <- call_goal((lambda X_: color(X_) and C_ is X_), _)\n"
        )

        from clausal.import_hook import _load_module
        mod = _load_module("lambda_multi", str(clausal_file))
        from clausal.logic.solve import query
        c = Var()
        logic_mod = mod.__dict__["$module"]
        goal = Call(func=LoadName(name="get_color"), args=[c], kwargs=[])
        results = [row["c"] for row in query(goal, {"c": c}, logic_mod)]
        assert sorted(results) == ["blue", "green", "red"]
