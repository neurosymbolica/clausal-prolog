"""Phase-boundary invariant assertions.

Every invariant the compiler relies on between phases — documented in
``README.md`` §10 and the target architecture §8 — has a runtime
assertion here.  These run on every compile (no env-var gate) so any
future change that breaks an invariant fails loudly with a readable
error rather than producing wrong code that surfaces as an obscure
runtime exception in generated Python.

Each assertion is a pure inspection of compiler state at a phase
boundary; it adds no work that scales with predicate size beyond what
the phase already does.  Cost is negligible — a few dict lookups per
clause.

Slice F (post-D7b): the IR path is now source-of-truth, phase
boundaries are crisp, and these assertions lock in the invariants
that the parallel-implementation harness verified empirically through
D4–D7b.

D7c relies on these: once the legacy dispatcher is gone, the
parallel cross-check disappears with it, and the invariant
assertions become the primary detection mechanism for IR-side bugs.
"""

from __future__ import annotations

from typing import Any

from ._vars import _collect_vars


class InvariantError(AssertionError):
    """A phase-boundary invariant was violated.

    Distinct exception class so callers (or test assertions) can
    distinguish invariant failures from generic ``AssertionError`` —
    the latter still serves the IR/legacy AST-diff cross-checks (D4
    / D6) and the parallel-implementation harness.

    Inherits from ``AssertionError`` so existing
    ``pytest.raises(AssertionError)`` callers (if any) keep working,
    but new code should match on :class:`InvariantError` directly
    for clearer test intent.
    """


def assert_body_vars_preallocated(ctx: Any, goals: list) -> None:
    """README §10 invariant 1 — Phase 5 entry gate.

    Every :class:`~clausal.logic.variables.Var` reachable from any
    goal in *goals* must be present in ``ctx.var_context`` before the
    right-to-left body fold begins.  ``_preallocate_body_vars`` is
    responsible for satisfying this; this assertion verifies the
    result so a future preallocator change that misses a Var category
    fails immediately with a readable diagnostic instead of producing
    generated code that ``UnboundLocalError``s when an ITE / Or
    branch references the missed Var.

    The check walks ``_collect_vars`` over each goal and intersects
    with ``ctx.var_context`` keys.  ``_collect_vars`` deliberately
    skips :class:`~clausal.pythonic_ast.nodes.Lambda` bodies (their
    Vars are in a separate scope) — same convention the preallocator
    follows, so the two stay aligned.
    """
    var_context = ctx.var_context
    seen: set[int] = set()
    missing: list[tuple[int, str]] = []
    for goal_idx, goal in enumerate(goals):
        for var in _collect_vars(goal, seen):
            if var._id not in var_context:
                missing.append((goal_idx, repr(var)))
    if missing:
        sample = missing[:5]
        raise InvariantError(
            "Phase 5 entry: body-vars-preallocated invariant violated. "
            f"{len(missing)} Var(s) reachable from body goals are not "
            "registered in ctx.var_context — _preallocate_body_vars "
            "missed them.  Generated code would UnboundLocalError on "
            "any branch that references one.\n"
            f"  sample (goal_idx, var): {sample}"
        )


__all__ = ["InvariantError", "assert_body_vars_preallocated"]
