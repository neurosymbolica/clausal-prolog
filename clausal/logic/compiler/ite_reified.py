"""Reified if-then-else helpers shared across shallow and trampoline.

Slice D7c-β3 reduced this module to two primitives that the IR lowering
pipeline (``_lower_goalop_shared._lower_reified_branch``) consults:

- :func:`_is_reifiable` — gate used by :mod:`.terms_to_goalop` to tag a
  :class:`~clausal.logic.compiler.ir.Branch` as reifiable so the
  lowering picks the three-way reified form over the general-ITE form.
- :func:`_three_way_reif_branch` — the shared three-way-branch AST
  assembly, used by ``_lower_reified_branch`` for both strategies.

Pre-β3 this module also carried ``_compile_reified_ite*`` and
``_compile_general_ite*`` helpers driven by the retired
``_dispatch_goal[_trampoline]`` dispatchers; they moved to
``_lower_goalop_shared`` / ``lower_python_{shallow,trampoline}`` as
pure IR ops during slice D5 and retired alongside the dispatchers.
"""

from __future__ import annotations

import ast

from clausal.terms import (
    Unify, DoesNotUnify, ArithEq, ArithNeq, Lt, LtE, Gt, GtE,
)

from ._ast_helpers import _name, _assign


_REIFIABLE_TYPES = (Unify, DoesNotUnify, ArithEq, ArithNeq, Lt, LtE, Gt, GtE)


def _is_reifiable(test) -> bool:
    """Return True if *test* can be compiled as a reified three-way branch."""
    return isinstance(test, _REIFIABLE_TYPES)


def _three_way_reif_branch(
    reif_var: str,
    reif_call: ast.expr,
    true_stmts: list[ast.stmt],
    false_stmts: list[ast.stmt],
    undetermined: list[ast.stmt],
) -> list[ast.stmt]:
    """Assemble the three-way branch."""
    reif_assign = _assign(reif_var, reif_call)
    branch = ast.If(
        test=ast.Compare(left=_name(reif_var), ops=[ast.Is()], comparators=[ast.Constant(True)]),
        body=true_stmts or [ast.Pass()],
        orelse=[
            ast.If(
                test=ast.Compare(left=_name(reif_var), ops=[ast.Is()], comparators=[ast.Constant(False)]),
                body=false_stmts or [ast.Pass()],
                orelse=undetermined,
            ),
        ],
    )
    return [reif_assign, branch]


