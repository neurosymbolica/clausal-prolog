"""A deep seam clause body loads, or is refused by name and position --
never a raw RecursionError out of the seam compiler
(todo/done/seam-clause-body-nested-170-deep-raises-a-raw-recursion-error-2026-11-04.md).

A bracketed term ``('f', ('f', ...))`` loads up to CPython's own parser
limit (about 197 levels: past it ``MemoryError: Parser stack overflowed``,
which is CPython's, not ours).  An operator chain parses flat but is a
left-nested ``BinOp`` as deep as it is long; past a few hundred it is
refused with ISO's ``resource_error(stack)`` and the item's line."""
from __future__ import annotations

import ast
import copy
import itertools
import pathlib
import warnings

import pytest

from clausal.import_hook import _load_module
from clausal.logic.solve import call as pcall
from clausal.templating.ast_walks import copy_tree

_names = itertools.count()
_REPO = pathlib.Path(__file__).resolve().parent.parent


def _load(tmp_path, body):
    mod = f"seamdeep{next(_names)}"
    path = tmp_path / f"{mod}.seam"
    path.write_text(f"-module({mod}, [t])\n{body}\n")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return _load_module(mod, str(path)).__dict__["$module"], path


def _nested_tuple(n):
    t = "'a'"
    for _ in range(n):
        t = f"('f', {t})"
    return t


def test_a_seam_body_nested_180_deep_loads_and_runs(tmp_path):
    # 170 levels raised RecursionError from copy.deepcopy in
    # _lower_dict_reads; the copy is now made on an explicit stack.
    m, _ = _load(tmp_path, f"t <- (X is {_nested_tuple(180)}, X is X)")
    assert sum(1 for _ in pcall("t", module=m)) == 1


def _chain(n, op, leaf):
    return f" {op} ".join([leaf] * n)


#: name -> clause; each nests past what the seam can rewrite or compile.
_TOO_DEEP = {
    "plus_chain": f"t <- (X == {_chain(1000, '+', '1')}, X == 1000)",
    "term_chain": f"t <- (X is {_chain(1000, '+', repr('a'))}, X is X)",
    "minus_chain": f"t <- (X == {'-' * 1000}1, X == 1)",
    "not_chain": f"t <- ({'not ' * 1000}true)",
    "and_chain": f"t <- ({_chain(1000, 'and', 'true')})",
    "and_chain_long": f"t <- ({_chain(5000, 'and', 'true')})",
    "or_chain": f"t <- ({_chain(5000, 'or', 'true')})",
    "fact": f"p({_chain(1000, '+', repr('a'))}),\nt <- p(_)",
    "dcg": f"g >> [{_chain(1000, '+', repr('a'))}]\nt <- phrase(g, [_])",
    "python_def": f"def f():\n    return --({_chain(1000, '+', repr('a'))})\nt <- true",
}


@pytest.mark.parametrize("name", sorted(_TOO_DEEP))
def test_a_seam_item_nested_too_deep_is_refused_with_its_line(tmp_path, name):
    with pytest.raises(SyntaxError) as info:
        _load(tmp_path, _TOO_DEEP[name])
    msg = str(info.value)
    assert "resource_error(stack)" in msg
    line = 3 if name == "python_def" else 2
    assert f".seam:{line}:" in msg, msg


def test_a_chain_too_long_for_pythons_parser_is_refused_by_name(tmp_path):
    # CPython's own parser raises RecursionError ("during ast construction")
    # for a flat chain this long; it gives no line, the file is named.
    with pytest.raises(SyntaxError) as info:
        _load(tmp_path, f"t <- (X == {_chain(20000, '+', '1')}, X == 1)")
    assert "resource_error(stack)" in str(info.value)
    assert ".seam" in str(info.value)


def _seam_sources():
    return sorted((_REPO / "clausal").rglob("*.seam"))[:40] + sorted(
        (_REPO / "tests" / "fixtures").glob("*.seam"))[:40]


def _shape(tree):
    """Every node's type, ``__dict__`` keys in order and non-node values,
    walked without recursion."""
    out, stack = [], [tree]
    while stack:
        x = stack.pop()
        if isinstance(x, ast.AST):
            out.append((type(x).__name__, tuple(x.__dict__)))
            stack.extend(reversed(list(x.__dict__.values())))
        elif type(x) is list:
            out.append(("list", len(x)))
            stack.extend(reversed(x))
        else:
            out.append(("value", type(x).__name__, repr(x)))
    return out


def test_copy_tree_is_deepcopy_on_seam_sources():
    paths = _seam_sources()
    assert paths
    for path in paths:
        tree = ast.parse(path.read_text(), filename=str(path))
        # A marker attribute a pass sets survives, as under deepcopy.
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                node._clausal_marker = True
        assert _shape(copy_tree(tree)) == _shape(copy.deepcopy(tree)), path


def test_copy_tree_keeps_sharing_and_copies_deep_trees():
    leaf = ast.Name(id="x", ctx=ast.Load())
    tree = ast.BinOp(left=leaf, op=ast.Add(), right=leaf)
    out = copy_tree(tree)
    assert out.left is out.right and out.left is not leaf
    deep = ast.parse(" + ".join(["1"] * 5000), mode="eval")
    out = copy_tree(deep)
    depth, node = 0, out.body
    while isinstance(node, ast.BinOp):
        depth, node = depth + 1, node.left
    assert depth == 4999 and out.body is not deep.body
