"""Tests for the IPython integration added to import_hook.py.

Simulates what IPython does: transform a cell's AST with _FreshEmbedTransformer,
then exec it in a namespace seeded with simple_ast names.  The --expr syntax
should produce simple_ast nodes as values.
"""

import ast
import pytest
from clausal.logic.atoms import char_atom, mint
from clausal.import_hook import (
    _FreshEmbedTransformer, _simple_ast_builtins,
    _star_query_input_transformer, _STAR_QUERY_SENTINEL,
    _StarQueryTransformer,
)
from clausal.pythonic_ast.nodes import (
    Call, LoadName, Add, TupleLiteral,
)
from clausal.templating.term_rewriting import EmbedTransformer


def run_cell(source):
    """Simulate an IPython cell: transform AST, fix locations, exec."""
    tree = ast.parse(source)
    transformed = _FreshEmbedTransformer().visit(tree)
    ast.fix_missing_locations(transformed)
    ns = dict(_simple_ast_builtins)
    exec(compile(transformed, "<cell>", "exec"), ns)
    return ns


# ── Basic term embedding ──────────────────────────────────────────────────────

def test_embed_name_produces_LoadName():
    # nv
    ns = run_cell("result = --foo")
    assert isinstance(ns["result"], LoadName)
    assert ns["result"].name == "foo"


def test_embed_integer_is_native_int():
    # nv
    ns = run_cell("result = --42")
    assert ns["result"] == 42
    assert isinstance(ns["result"], int)


def test_embed_float_is_native_float():
    # nv
    ns = run_cell("result = --3.14")
    assert ns["result"] == 3.14
    assert isinstance(ns["result"], float)


def test_embed_double_quoted_is_an_atom():
    # nv — THE FLIP (spec §7): ``"hello"`` is an ATOM under the default
    # ``-double_quotes(atom)`` mode the embed cell compiles under.
    ns = run_cell('result = --"hello"')
    assert ns["result"] == mint("hello")


def test_embed_bool_is_native_bool():
    # nv
    ns = run_cell("result = --True")
    assert ns["result"] is True


def test_embed_none_is_native_none():
    # nv
    ns = run_cell("result = --None")
    assert ns["result"] is None


# ── Call terms ────────────────────────────────────────────────────────────────

def test_embed_call_no_args():
    # nv
    ns = run_cell("result = --foo()")
    node = ns["result"]
    assert isinstance(node, Call)
    assert isinstance(node.func, LoadName)
    assert node.func.name == "foo"
    assert node.args == []
    assert node.kwargs == []


def test_embed_call_with_int_args():
    # nv
    ns = run_cell("result = --foo(1, 2)")
    node = ns["result"]
    assert isinstance(node, Call)
    assert node.func.name == "foo"
    assert len(node.args) == 2
    assert node.args[0] == 1   # plain int, not IntLiteral
    assert node.args[1] == 2


def test_embed_nested_call():
    # nv
    ns = run_cell("result = --foo(bar(1))")
    node = ns["result"]
    assert isinstance(node, Call)
    assert node.func.name == "foo"
    assert isinstance(node.args[0], Call)
    assert node.args[0].func.name == "bar"
    assert node.args[0].args[0] == 1   # plain int


# ── Arithmetic ────────────────────────────────────────────────────────────────

def test_embed_addition():
    # nv
    ns = run_cell("result = --(1 + 2)")
    node = ns["result"]
    assert isinstance(node, Add)
    assert node.left == 1    # plain int, not IntLiteral
    assert node.right == 2


# ── Transformer is fresh per cell ─────────────────────────────────────────────

def test_each_visit_gets_fresh_transformer():
    # nv
    t = _FreshEmbedTransformer()
    tree1 = ast.parse("result = --foo()")
    tree2 = ast.parse("result = --foo()")
    ast.fix_missing_locations(tree1)
    ast.fix_missing_locations(tree2)
    # Two calls should not share EmbedTransformer state
    t.visit(tree1)
    t.visit(tree2)  # must not raise due to stale _seen_functors or _scope_depth


# ── -constants is rejected interactively (roborev finding) ───────────────────
#
# ``-constants`` lowers to ``$check_constant_ground(...)`` calls, and a fresh
# EmbedTransformer per cell means ``_constants`` is forgotten between cells —
# a name declared in one cell would raise the undeclared-constant SyntaxError
# from the very next one. Rather than half-work, the directive is rejected
# outright in interactive sessions.

def test_constants_directive_rejected_interactively():
    # EmbedTransformer directly, at the actual interception point
    # (_handle_constants_directive consulting transformer._interactive) —
    # bypasses _FreshEmbedTransformer's catch-and-print wrapper so the
    # SyntaxError itself can be asserted on.
    # nv
    tree = ast.parse("-constants(_PI_ = 3.14)\n")
    with pytest.raises(SyntaxError, match="not supported interactively"):
        EmbedTransformer(implicit_atoms_default=True, interactive=True).visit(tree)


def test_constants_directive_still_works_in_module_compile():
    # A non-interactive EmbedTransformer (the .clausal module-compile path,
    # interactive=False by default) must be unaffected.
    # nv
    tree = ast.parse("-constants(_PI_ = 3.14)\n")
    transformed = EmbedTransformer().visit(tree)
    ast.fix_missing_locations(transformed)
    src = ast.unparse(transformed)
    assert "$check_constant_ground" in src


def test_constants_directive_rejection_surfaces_through_fresh_transformer(capsys):
    # End-to-end through the actual IPython call path: _FreshEmbedTransformer
    # catches and prints rather than propagating (so a bad cell does not
    # unregister the transformer) — confirm the printed traceback carries our
    # rejection message rather than the old bare NameError.
    # nv
    tree = ast.parse("-constants(_PI_ = 3.14)\nresult = _PI_\n")
    _FreshEmbedTransformer().visit(tree)
    err = capsys.readouterr().err
    assert "not supported interactively" in err
    assert "NameError" not in err


# ── Normal Python is unaffected ───────────────────────────────────────────────

def test_plain_python_unchanged():
    # nv
    ns = run_cell("result = 1 + 2")
    assert ns["result"] == 3


def test_simple_ast_names_in_scope():
    # After enable_ipython the names are available; _simple_ast_builtins covers them.
    # nv
    assert "LoadName" in _simple_ast_builtins
    assert "Call" in _simple_ast_builtins
    assert "IntLiteral" in _simple_ast_builtins


# ── Star-query input transformer (text-level) ────────────────────────────────

def test_star_query_input_transformer_single_goal():
    # nv
    lines = ["*(greeting(N))\n"]
    result = _star_query_input_transformer(lines)
    assert result == [f"{_STAR_QUERY_SENTINEL}(greeting(N))\n"]


def test_star_query_input_transformer_multi_goal():
    # nv
    lines = ["*(A(X), B(X, Y))\n"]
    result = _star_query_input_transformer(lines)
    assert result == [f"{_STAR_QUERY_SENTINEL}(A(X), B(X, Y))\n"]


def test_star_query_input_transformer_preserves_indent():
    # nv
    lines = ["  *(foo(X))\n"]
    result = _star_query_input_transformer(lines)
    assert result == [f"  {_STAR_QUERY_SENTINEL}(foo(X))\n"]


def test_star_query_input_transformer_ignores_non_star():
    # nv
    lines = ["x = 1 + 2\n", "print(x)\n"]
    result = _star_query_input_transformer(lines)
    assert result == lines


def test_star_query_input_transformer_ignores_star_not_paren():
    # nv
    lines = ["*x\n"]
    result = _star_query_input_transformer(lines)
    assert result == lines


# ── Sentinel form AST rewriting ──────────────────────────────────────────────

def _run_sentinel_cell(source):
    """Simulate IPython with the text transformer + AST transformer pipeline."""
    lines = source.splitlines(keepends=True)
    transformed_lines = _star_query_input_transformer(lines)
    transformed_source = "".join(transformed_lines)
    tree = ast.parse(transformed_source)
    tree = _FreshEmbedTransformer().visit(tree)
    ast.fix_missing_locations(tree)
    ns = dict(_simple_ast_builtins)
    exec(compile(tree, "<cell>", "exec"), ns)
    return ns


def test_sentinel_single_goal_compiles():
    """*(greeting(N)) should survive the full text→AST→compile pipeline."""
    # nv
    source = "*(greeting(N))\n"
    lines = source.splitlines(keepends=True)
    transformed = _star_query_input_transformer(lines)
    transformed_source = "".join(transformed)
    # Must parse and compile without error
    tree = ast.parse(transformed_source)
    tree = _StarQueryTransformer().visit(tree)
    ast.fix_missing_locations(tree)
    compile(tree, "<cell>", "exec")


def test_sentinel_multi_goal_compiles():
    """*(A(X), B(X, Y)) should survive the full pipeline."""
    # nv
    source = "*(A(X), B(X, Y))\n"
    lines = source.splitlines(keepends=True)
    transformed = _star_query_input_transformer(lines)
    transformed_source = "".join(transformed)
    tree = ast.parse(transformed_source)
    tree = _StarQueryTransformer().visit(tree)
    ast.fix_missing_locations(tree)
    compile(tree, "<cell>", "exec")
