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


def assert_call_targets_resolved(
    targets: set, base_globals: dict, db: Any = None,
) -> None:
    """README §10 invariant 2 — Phase 1 exit gate.

    When ``db`` is provided, every ``(fname, arity)`` collected by
    ``_collect_globals_info`` must have an entry in ``base_globals``
    after ``_inject_resolved_targets`` runs — either a real
    :class:`PredicateMeta`, a :class:`BuiltinPredicate`, a
    :class:`_DbDispatchAdapter` shim, or an imported Python value.
    With a db available, the shim is the catch-all floor: anything
    that survives without an entry indicates a resolution-path bug
    that would generate ``NameError`` at runtime.

    When ``db is None`` the invariant is **advisory only** — there
    is no shim floor, the existing contract is "best-effort
    resolution; missing entries cause runtime NameError if called",
    and doc-snippet compilation paths legitimately rely on this for
    placeholder targets.  The check skips silently in that case.

    **Dotted-name targets are also best-effort.**  The shim floor
    in ``_inject_resolved_targets`` only catches *non-dotted*
    names; dotted names like ``mod.Submod.Pred`` rely on
    ``globals_`` ambient resolution or ``sys.modules`` lookup with
    no shim fallback.  Doc snippets that reference placeholder
    qualified names (``myapp.graphs.utils.Reachable``) compile
    successfully today and only fail at runtime if invoked — the
    assertion preserves that behaviour by skipping dotted names.
    """
    if db is None:
        return
    missing: list[tuple[str, int]] = []
    for target_name, target_arity in targets:
        if target_name in base_globals:
            continue
        # Dotted names: best-effort, no shim floor (see docstring).
        if "." in target_name:
            continue
        missing.append((target_name, target_arity))
    if missing:
        sample = missing[:5]
        raise InvariantError(
            "Phase 1 exit: call-targets-resolved invariant violated. "
            f"{len(missing)} call target(s) collected from clause "
            "bodies have no entry in base_globals despite db being "
            "available — generated code would NameError at runtime "
            "when invoking them.  _inject_resolved_targets is "
            "responsible for injecting either a real predicate, a "
            "BuiltinPredicate, a _DbDispatchAdapter shim, or an "
            "imported Python value for every collected target when "
            "a db is available.\n"
            f"  sample (fname, arity): {sample}"
        )


__all__ = [
    "InvariantError",
    "assert_body_vars_preallocated",
    "assert_call_targets_resolved",
]
