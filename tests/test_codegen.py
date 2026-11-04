"""Tests for codegen._infer_args and stmts_to_function argument inference."""

import ast
import inspect

import pytest

from clausal.codegen import _infer_args, stmts_to_function


def params(src: str, globals_: dict | None = None) -> list[str]:
    """Parse src as a statement list and return the inferred parameter names."""
    stmts = ast.parse(src).body
    args = _infer_args(stmts, globals_)
    return [a.arg for a in args.args]


def fn(src: str, globals_: dict | None = None):
    """Parse src as a statement list, infer args, compile and return the function."""
    stmts = ast.parse(src).body
    return stmts_to_function(stmts, "f", globals_=globals_)


# ── basic load / store ────────────────────────────────────────────────────────

def test_load_only_is_param():
    # nv
    assert params("x") == ["x"]

def test_assigned_before_load_is_local():
    # nv
    assert params("x = 1\ny = x") == []

def test_load_before_assign_is_param():
    # y is loaded (RHS) before x is stored
    # nv
    assert params("x = y + 1") == ["y"]

def test_multiple_params_in_load_order():
    # nv
    assert params("z = a + b + c") == ["a", "b", "c"]

def test_same_name_used_twice_appears_once():
    # nv
    assert params("y = x + x") == ["x"]

def test_param_then_reassigned():
    # x is a param (first use is load), then reassigned
    # nv
    assert params("y = x\nx = 1") == ["x"]


# ── augmented assignment ──────────────────────────────────────────────────────

def test_augassign_makes_param():
    # x += 1 implicitly reads x before writing it
    # nv
    assert params("x += 1") == ["x"]

def test_augassign_on_subscript_object_is_param():
    # lst[i] += 1 → lst and i are loaded, they become params
    # nv
    assert set(params("lst[i] += 1")) == {"lst", "i"}

def test_augassign_on_attribute_object_is_param():
    # nv
    assert params("obj.attr += 1") == ["obj"]


# ── for loops ─────────────────────────────────────────────────────────────────

def test_for_iterable_is_param():
    # nv
    assert params("for x in items:\n    pass") == ["items"]

def test_for_target_is_local():
    # nv
    assert "x" not in params("for x in items:\n    pass")

def test_for_body_load_is_param():
    # nv
    assert params("for x in items:\n    result = x + offset") == ["items", "offset"]

def test_for_target_used_after_loop_is_not_param():
    # x is the loop variable (stored), so using x after is not a param
    # nv
    assert params("for x in items:\n    pass\ny = x") == ["items"]


# ── comprehensions ────────────────────────────────────────────────────────────

def test_listcomp_outermost_iter_is_param():
    # The outermost iterable (items) is evaluated in the enclosing scope
    # nv
    assert params("result = [x for x in items]") == ["items"]

def test_listcomp_element_name_not_param():
    # x is inside the comprehension scope
    # nv
    assert "x" not in params("result = [x*2 for x in items]")

def test_listcomp_inner_iter_not_param():
    # The inner iterable of a nested comprehension is inside the comp scope
    # nv
    assert "inner" not in params("result = [x for row in outer for x in inner]")
    assert params("result = [x for row in outer for x in inner]") == ["outer"]

def test_setcomp_outermost_iter_is_param():
    # nv
    assert params("result = {x for x in items}") == ["items"]

def test_dictcomp_outermost_iter_is_param():
    # nv
    assert params("result = {k: v for k, v in pairs}") == ["pairs"]

def test_genexpr_outermost_iter_is_param():
    # nv
    assert params("result = sum(x for x in items)") == ["items"]


# ── nested scopes ─────────────────────────────────────────────────────────────

def test_nested_function_names_not_params():
    # nv
    src = "def f():\n    return inner_var"
    assert params(src) == []

def test_nested_function_name_is_local():
    # The function name 'f' is stored in the enclosing scope
    # nv
    src = "def f():\n    pass\ny = f()"
    assert params(src) == []

def test_nested_class_body_names_not_params():
    # nv
    src = "class C:\n    x = outer"
    assert params(src) == []

def test_lambda_body_not_scanned():
    # nv
    src = "f = lambda: free_var"
    assert params(src) == []


# ── builtins excluded ─────────────────────────────────────────────────────────

def test_builtin_not_a_param():
    # nv
    assert "len" not in params("n = len(items)")
    assert "print" not in params("print(x)")
    assert "range" not in params("for i in range(10):\n    pass")

def test_only_non_builtin_becomes_param():
    # nv
    assert params("n = len(items)") == ["items"]


# ── globals_ exclusion ────────────────────────────────────────────────────────

def test_global_name_not_a_param():
    # nv
    assert params("result = helper(x)", globals_={"helper": None}) == ["x"]

def test_all_globals_excluded():
    # nv
    assert params("y = a + b", globals_={"a": 1, "b": 2}) == []

def test_global_name_still_accessible_at_runtime():
    # nv
    f = fn("return helper(x)", globals_={"helper": lambda v: v * 2})
    sig = inspect.signature(f)
    assert list(sig.parameters) == ["x"]
    assert f(5) == 10


# ── global / nonlocal statements ──────────────────────────────────────────────

def test_global_stmt_excludes_name():
    # nv
    src = "global g\ng = 1"
    assert params(src) == []

def test_global_stmt_load_not_param():
    # nv
    src = "global g\ny = g"
    assert "g" not in params(src)


# ── ordering ──────────────────────────────────────────────────────────────────

def test_param_order_matches_first_load():
    # nv
    assert params("z = b + a") == ["b", "a"]

def test_param_order_across_statements():
    # nv
    assert params("x = a\ny = b\nz = c") == ["a", "b", "c"]


# ── end-to-end stmts_to_function ─────────────────────────────────────────────

def test_inferred_function_works():
    # nv
    f = fn("return x + y")
    assert f(3, 4) == 7

def test_inferred_function_signature():
    # nv
    f = fn("return a * b + c")
    assert list(inspect.signature(f).parameters) == ["a", "b", "c"]

def test_no_params_when_all_assigned():
    # nv
    f = fn("x = 1\ny = x + 1\nreturn y")
    assert list(inspect.signature(f).parameters) == []
    assert f() == 2

def test_explicit_args_not_overridden():
    # when args is passed explicitly, _infer_args is not called
    # nv
    explicit = ast.arguments(
        posonlyargs=[], args=[ast.arg(arg="z")],
        vararg=None, kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[],
    )
    f = stmts_to_function(ast.parse("return z * 2").body, "f", args=explicit)
    assert f(6) == 12


def _nested_deep_functions(depth, loops=24):
    """``def f0`` holding 24 nested ``for`` loops, the innermost holding
    ``def f1`` with the same, and so on *depth* deep: every function nests
    past CPython's block limit, so the outliner splits each of them."""
    inner = [ast.Pass()]
    for k in reversed(range(depth)):
        body = [ast.parse(f"a{k} += 1").body[0],
                ast.parse(f"out.append(a{k})").body[0]] + inner
        if k + 1 < depth:
            body.append(ast.parse(f"f{k + 1}(xs, out)").body[0])
        for j in reversed(range(loops)):
            body = [ast.For(target=ast.Name(f"i{k}_{j}", ast.Store()),
                            iter=ast.Name("xs", ast.Load()), body=body, orelse=[])]
        fd = ast.parse(f"def f{k}(xs, out):\n    a{k} = 0").body[0]
        fd.body += body
        inner = [fd]
    module = ast.Module(inner, [])
    ast.fix_missing_locations(module)
    return module


def test_outlining_nested_functions_is_linear(monkeypatch):
    # Each function's outliner walked the bodies of all the functions
    # nested in it again, quadratic in the nesting
    # (todo/done/load-time-doubles-per-nested-negation-mark-undo-invariant-2026-10-16.md).
    from clausal.codegen import split_deep_nesting
    real = ast.iter_child_nodes
    for depth in (8, 32):
        module = _nested_deep_functions(depth)
        n_nodes = sum(1 for _ in ast.walk(module))
        visits = 0

        def counting(node):
            nonlocal visits
            visits += 1
            return real(node)

        monkeypatch.setattr(ast, "iter_child_nodes", counting)
        try:
            assert split_deep_nesting(module.body[0], force=True)
        finally:
            monkeypatch.setattr(ast, "iter_child_nodes", real)
        assert visits <= 10 * n_nodes, (depth, visits, n_nodes)   # was 21x at 32
        ns: dict = {}
        exec(compile(ast.fix_missing_locations(module), "<test>", "exec"), ns)
        out: list = []
        ns["f0"]([1], out)
        assert out == [1] * depth
