"""The entry points that rewrite seam syntax outside module loading -- the
REPL star query, ``clausal.reflection`` and the transformed-code dumper --
load a deep input or refuse it by name (``resource_error(stack)``), as
module loading does (tests/test_seam_deep_nesting.py); none leaks a raw
RecursionError."""
from __future__ import annotations

import ast
import io
import sys
import warnings

import pytest

from clausal.import_hook import (
    _FreshEmbedTransformer, _star_query_input_transformer,
)
from clausal.reflection import ReifyError, reify_ast, reify_source


# The depths here are sized against CPython's default recursion limit, which
# importing IPython raises (tests/conftest.py).
pytestmark = pytest.mark.usefixtures("default_recursion_limit")


def _chain(n, op, leaf="1"):
    return f" {op} ".join([leaf] * n)


def _nested_tuple(n):
    t = "'a'"
    for _ in range(n):
        t = f"('f', {t})"
    return t


def _cell(query):
    lines = _star_query_input_transformer([f"*({query})\n"])
    return lines, ast.parse("".join(lines))


def _transform_cell(query, **kwargs):
    """The transformed cell and what the transformer printed."""
    lines, tree = _cell(query)
    err = io.StringIO()
    old, sys.stderr = sys.stderr, err
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            out = _FreshEmbedTransformer(lines, **kwargs).visit(tree)
    finally:
        sys.stderr = old
    return out, err.getvalue()


def _is_solutions_call(tree):
    stmt = tree.body[0]
    return (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)
            and getattr(stmt.value.func, "id", None) == "Solutions")


# ── the star query ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("n", [400, 600, 1000, 3000])
def test_a_deep_star_query_is_refused_by_name(n):
    # The term rewriter recurses per level of ``1 + 1 + ...``: past a few
    # hundred the query was a raw RecursionError traceback.
    _, printed = _transform_cell(f"X == {_chain(n, '+')}")
    assert "RecursionError" not in printed, printed
    assert "resource_error(stack)" in printed, printed


@pytest.mark.parametrize("query", [
    _chain(1000, "and", "true"),
    ", ".join(["true"] * 1000),
])
def test_a_long_star_query_conjunction_is_transformed(query):
    # Rewritten fine, then ast.fix_missing_locations (recursive) overflowed
    # on the result: the cell ran untransformed after a raw traceback.
    out, printed = _transform_cell(query)
    assert printed == ""
    assert _is_solutions_call(out)
    compile(out, "<cell>", "exec")


def test_a_star_query_too_deep_for_ipython_is_rejected_by_name():
    # IPython's transform_ast runs its own recursive fix_missing_locations
    # after the transformers; a cell it cannot walk is rejected (the cell
    # does not run) with the named refusal, not IPython's raw traceback.
    error = pytest.importorskip("IPython.core.error")
    lines, tree = _cell(", ".join(["true"] * 3000))
    with pytest.raises(error.InputRejected) as info:
        _FreshEmbedTransformer(lines, ipython=True).visit(tree)
    assert "resource_error(stack)" in str(info.value)


def test_a_rewrite_refusal_under_ipython_rejects_the_cell():
    error = pytest.importorskip("IPython.core.error")
    lines, tree = _cell(f"X == {_chain(3000, '+')}")
    with pytest.raises(error.InputRejected) as info:
        _FreshEmbedTransformer(lines, ipython=True).visit(tree)
    assert "resource_error(stack)" in str(info.value)


def test_the_console_refuses_a_query_too_deep_to_compile_by_name():
    from clausal.python_repl import ClausalConsole
    console = ClausalConsole(filename="<test>")
    buf = io.StringIO()
    old = sys.stdout, sys.stderr
    sys.stdout = sys.stderr = buf
    try:
        console.runsource("*(" + ", ".join(["true"] * 20000) + ")",
                          filename="<test>", symbol="single")
    finally:
        sys.stdout, sys.stderr = old
    printed = buf.getvalue()
    assert "RecursionError" not in printed, printed[-2000:]
    assert "resource_error(stack)" in printed, printed[-2000:]


# ── clausal.reflection ──────────────────────────────────────────────────────


def _reify_expr(text):
    return reify_ast(ast.parse(text, mode="eval"), source=text)


@pytest.mark.parametrize("text", [
    _chain(1000, "+"),
    _chain(1000, "and", "true"),
    _chain(3000, "or", "true"),
], ids=["plus", "and", "or"])
def test_reify_ast_refuses_a_deep_expression_by_name(text):
    with pytest.raises(ReifyError) as info:
        _reify_expr(text)
    assert "resource_error(stack)" in str(info.value)
    assert "<reflected>:1:" in str(info.value)


def test_reify_ast_of_a_deep_bracketed_term_reifies():
    term = _reify_expr(_nested_tuple(180))
    assert term is not None


def test_reify_ast_refuses_a_deep_statement_without_source_by_name():
    # Without *source* the statement is unparsed first, and ast.unparse
    # recurses per level.
    tree = ast.parse(f"t <- (X == {_chain(1000, '+')}, X == 1)")
    with pytest.raises(ReifyError) as info:
        reify_ast(tree)
    assert "resource_error(stack)" in str(info.value)


@pytest.mark.parametrize("body", [
    f"X == {_chain(1000, '+')}",
    _chain(1000, "and", "true"),
    _chain(3000, "or", "true"),
], ids=["plus", "and", "or"])
def test_reify_source_refuses_a_deep_clause_with_its_line(body):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with pytest.raises(ReifyError) as info:
            reify_source(f"p(1),\nt <- ({body})\n")
    assert "resource_error(stack)" in str(info.value)
    assert "<reflected>:2:" in str(info.value)


def test_reify_source_refuses_a_chain_too_long_to_parse_by_name():
    with pytest.raises(ReifyError) as info:
        reify_source(f"t <- (X == {_chain(20000, '+')})\n")
    assert "resource_error(stack)" in str(info.value)


# ── the transformed-code dumper ─────────────────────────────────────────────


@pytest.mark.parametrize("body", [
    f"t <- (X is {_nested_tuple(180)}, X is X)",
    f"t <- (X == {_chain(20000, '+')}, X == 1)",
], ids=["tuple", "parse"])
def test_dump_transformed_refuses_by_name(tmp_path, body):
    from clausal.tools.dump_transformed import dump_source
    path = tmp_path / "deepdump.seam"
    path.write_text(f"-module(deepdump, [t])\n{body}\n")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with pytest.raises(SyntaxError) as info:
            dump_source(str(path))
    assert "resource_error(stack)" in str(info.value)
    assert "deepdump.seam" in str(info.value)
