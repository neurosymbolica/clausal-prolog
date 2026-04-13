"""Lower a :class:`~clausal.logic.compiler.ir.GoalOp` tree to Python
``ast.stmt`` list — trampoline strategy.

Slice D3 prototype: covers the D2 subset (Unify, Dif, ArithEval,
FDCompare, StructuralEq, MemberIn, Sequence).  Output must be
byte-for-byte identical to what ``compile_goal_trampoline`` would emit
today for the same input; the D4 parallel-implementation harness will
enforce this via ``ast.dump`` diff.

The D2 subset is strategy-agnostic at the legacy dispatcher level
(``_compile_deterministic_goal`` / ``_compile_shared_membership_goal``
emit identical AST for both strategies), so this module currently
delegates to ``lower_python_shallow.lower``.  The two ``lower``
functions are expected to diverge in Slice D5 as strategy-specific
ops land (``Alternate``, ``Negate``, ``SubCall``, ``MetaCall``, …);
at that point the trampoline module grows its own dispatch and stops
delegating.

.. warning::
   **Do not add a strategy-specific case to ``lower_python_shallow``
   while this delegation is still live.**  Any op whose trampoline
   lowering is not identical to the shallow lowering must first trigger
   the fork: give each strategy module its own full match statement
   (or introduce a shared ``_lower_goalop_shared`` helper for the
   strategy-agnostic subset) and then add the divergent case.  The
   AST-diff harness (D4) will catch the mismatch, but the fix is a
   structural change, not a one-line patch.
"""

from __future__ import annotations

import ast

from clausal.logic.compiler.ir import GoalOp
from clausal.logic.compiler.compile_ctx import CompilationContext
from clausal.logic.compiler.lower_python_shallow import lower as _lower_shallow


def lower(
    ir: GoalOp,
    ctx: CompilationContext,
    k_stmts: list[ast.stmt],
) -> list[ast.stmt]:
    """Lower *ir* (trampoline strategy), threading *k_stmts* as continuation."""
    return _lower_shallow(ir, ctx, k_stmts)


__all__ = ["lower"]
