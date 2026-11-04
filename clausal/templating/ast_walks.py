"""``copy.deepcopy`` of an ``ast`` tree on an explicit stack, for the seam
compiler.

``copy.deepcopy`` spends about six Python frames per level of an AST, so a
seam clause body nested 170 deep (``('f', ('f', ...))``) ran out of the
recursion limit copying it in ``_lower_dict_reads`` and leaked a raw
``RecursionError``
(todo/done/seam-clause-body-nested-170-deep-raises-a-raw-recursion-error-2026-11-04.md).

:func:`copy_tree` gives the SAME result as ``copy.deepcopy`` -- the same node
types, field and attribute values, key order of each node's ``__dict__``
and sharing of sub-trees -- with no Python recursion over the depth.  It is
not ``clausal.codegen.copy_ast``: that one makes each node with
``__new__`` and copies ``__dict__`` in its own order, where ``deepcopy``
calls the node's constructor first (every ``_fields`` key, in field order,
then the rest); the seam compiler's output is kept byte-identical.
(``ast.fix_missing_locations`` has its explicit-stack twin in
``clausal.codegen.fix_missing_locations``.)
"""

from __future__ import annotations

import ast
import copy
import copyreg

__all__ = ["copy_tree"]


def _copied_like_an_ast(x) -> bool:
    """True when ``copy.deepcopy`` would copy *x* through the generic
    ``__reduce_ex__(4)`` path that :func:`copy_tree` reproduces: an AST node
    with no ``__deepcopy__`` and no ``copyreg`` override."""
    cls = type(x)
    return (isinstance(x, ast.AST)
            and cls not in copyreg.dispatch_table
            and getattr(x, "__deepcopy__", None) is None)


def copy_tree(root):
    """``copy.deepcopy(root)`` for an ``ast`` tree, on an explicit stack.

    AST nodes and plain lists -- the only containers that can nest deep in a
    parsed tree -- are copied here exactly as ``copy.deepcopy`` copies them
    (``__reduce_ex__(4)``, the constructor call it names, then the copied
    ``__dict__`` state); any other value (a constant, a marker attribute a
    pass set on a node) is handed to ``copy.deepcopy`` with the shared memo,
    so sharing is kept across both.
    """
    memo: dict = {}
    keep_alive: list = []
    memo[id(memo)] = keep_alive
    out = [None]
    stack = [(root, out, 0)]
    while stack:
        x, holder, key = stack.pop()
        found = memo.get(id(x), memo)
        if found is not memo:
            holder[key] = found
            continue
        if type(x) is list:
            y = [None] * len(x)
            memo[id(x)] = y
            keep_alive.append(x)
            holder[key] = y
            for i in range(len(x) - 1, -1, -1):
                stack.append((x[i], y, i))
            continue
        if _copied_like_an_ast(x):
            rv = x.__reduce_ex__(4)
            if (type(rv) is tuple and len(rv) == 3
                    and (rv[2] is None or type(rv[2]) is dict)):
                func, args, state = rv
                if args:
                    args = copy.deepcopy(args, memo)
                y = func(*args)
                memo[id(x)] = y
                keep_alive.append(x)
                holder[key] = y
                if state:
                    # ``deepcopy`` copies the state dict, then updates the
                    # new node's ``__dict__`` with it: the keys go in now
                    # (so their order is the same), the values as they are
                    # copied.
                    target = y.__dict__
                    target.update(dict.fromkeys(state))
                    items = list(state.items())
                    for k, v in reversed(items):
                        stack.append((v, target, k))
                continue
        holder[key] = copy.deepcopy(x, memo)
    return out[0]
