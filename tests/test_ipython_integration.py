"""Tests for the IPython integration added to import_hook.py.

Simulates what IPython does: transform a cell's AST with _FreshEmbedTransformer,
then exec it in a namespace seeded with simple_ast names.  The --expr syntax
should produce simple_ast nodes as values.
"""

import ast
import pytest
from clausal.import_hook import _FreshEmbedTransformer, _simple_ast_builtins
from clausal.simple_ast import (
    Call, LoadName, IntLiteral, FloatLiteral, StringLiteral,
    BoolLiteral, NoneLiteral, Add, TupleLiteral,
)


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
    ns = run_cell("result = --foo")
    assert isinstance(ns["result"], LoadName)
    assert ns["result"].name == "foo"


def test_embed_integer_produces_IntLiteral():
    ns = run_cell("result = --42")
    assert isinstance(ns["result"], IntLiteral)
    assert ns["result"].value == 42


def test_embed_float_produces_FloatLiteral():
    ns = run_cell("result = --3.14")
    assert isinstance(ns["result"], FloatLiteral)
    assert ns["result"].value == 3.14


def test_embed_string_produces_StringLiteral():
    ns = run_cell('result = --"hello"')
    assert isinstance(ns["result"], StringLiteral)
    assert ns["result"].value == "hello"


def test_embed_bool_produces_BoolLiteral():
    ns = run_cell("result = --True")
    assert isinstance(ns["result"], BoolLiteral)
    assert ns["result"].value is True


def test_embed_none_produces_NoneLiteral():
    ns = run_cell("result = --None")
    assert isinstance(ns["result"], NoneLiteral)


# ── Call terms ────────────────────────────────────────────────────────────────

def test_embed_call_no_args():
    ns = run_cell("result = --foo()")
    node = ns["result"]
    assert isinstance(node, Call)
    assert isinstance(node.func, LoadName)
    assert node.func.name == "foo"
    assert node.args == []
    assert node.kwargs == []


def test_embed_call_with_int_args():
    ns = run_cell("result = --foo(1, 2)")
    node = ns["result"]
    assert isinstance(node, Call)
    assert node.func.name == "foo"
    assert len(node.args) == 2
    assert isinstance(node.args[0], IntLiteral)
    assert node.args[0].value == 1
    assert isinstance(node.args[1], IntLiteral)
    assert node.args[1].value == 2


def test_embed_nested_call():
    ns = run_cell("result = --foo(bar(1))")
    node = ns["result"]
    assert isinstance(node, Call)
    assert node.func.name == "foo"
    assert isinstance(node.args[0], Call)
    assert node.args[0].func.name == "bar"
    assert node.args[0].args[0].value == 1


# ── Arithmetic ────────────────────────────────────────────────────────────────

def test_embed_addition():
    ns = run_cell("result = --(1 + 2)")
    node = ns["result"]
    assert isinstance(node, Add)
    assert isinstance(node.left, IntLiteral)
    assert isinstance(node.right, IntLiteral)


# ── Transformer is fresh per cell ─────────────────────────────────────────────

def test_each_visit_gets_fresh_transformer():
    t = _FreshEmbedTransformer()
    tree1 = ast.parse("result = --foo()")
    tree2 = ast.parse("result = --foo()")
    ast.fix_missing_locations(tree1)
    ast.fix_missing_locations(tree2)
    # Two calls should not share EmbedTransformer state
    t.visit(tree1)
    t.visit(tree2)  # must not raise due to stale _seen_functors or _scope_depth


# ── Normal Python is unaffected ───────────────────────────────────────────────

def test_plain_python_unchanged():
    ns = run_cell("result = 1 + 2")
    assert ns["result"] == 3


def test_simple_ast_names_in_scope():
    # After enable_ipython the names are available; _simple_ast_builtins covers them.
    assert "LoadName" in _simple_ast_builtins
    assert "Call" in _simple_ast_builtins
    assert "IntLiteral" in _simple_ast_builtins
