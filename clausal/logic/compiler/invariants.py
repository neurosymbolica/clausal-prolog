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


def assert_mark_undo_paired(funcdef: Any) -> None:
    """README §10 invariant 3 — Phase 6 post.

    Every ``<name> = trail.mark()`` assignment in the generated
    funcdef must have at least one matching ``trail.undo(<name>)``
    call.  This is a balance check, not a flow-sensitive proof: it
    catches "mark assigned but never undone" but not "mark not
    undone on every code path."  The emitting helpers
    (``_assign_mark`` + ``_undo_stmt``) emit pairs by construction;
    the assertion locks in that they are paired *somewhere* and
    catches any future emitter that allocates a mark without ever
    consuming it.

    The opposite direction (``trail.undo`` of a name that was never
    marked) is also checked — that would indicate an emitter using
    a stale name.

    Walks the funcdef body recursively because marks may live inside
    nested ``If``, ``For``, ``While``, ``Try``, ``FunctionDef``
    (NAF mini-generators), etc.  Marks defined inside an inner
    funcdef are paired *within* that inner scope, so the walk
    accumulates per-scope.
    """
    import ast as _ast
    issues = _check_mark_undo_pairing(funcdef.body)
    if issues:
        sample = issues[:5]
        raise InvariantError(
            "Phase 6 post: mark/undo-paired invariant violated. "
            f"{len(issues)} mark/undo imbalance(s) in funcdef "
            f"{funcdef.name!r}.  Marks emitted via ``_assign_mark`` "
            "must be consumed by ``_undo_stmt`` in the same scope; "
            "any miss would leak trail entries on backtracking and "
            "produce wrong solutions silently.\n"
            f"  sample: {sample}"
        )


def _check_mark_undo_pairing(stmts: list) -> list[str]:
    """Recursively check mark/undo balance per lexical scope.

    Returns a list of human-readable issue descriptions; empty list
    means OK.  Each :class:`ast.FunctionDef` introduces a new scope
    (NAF mini-generators emit funcdefs whose marks are local).
    """
    import ast as _ast
    marks: set[str] = set()
    undos: set[str] = set()
    nested_issues: list[str] = []

    for node in _ast.walk(_make_module(stmts)):
        if isinstance(node, _ast.FunctionDef) and node.body is not stmts:
            # Recurse into nested funcdef as a separate scope.
            nested_issues.extend(_check_mark_undo_pairing(node.body))
            continue
        if isinstance(node, _ast.Assign):
            if (
                len(node.targets) == 1
                and isinstance(node.targets[0], _ast.Name)
                and isinstance(node.value, _ast.Call)
                and isinstance(node.value.func, _ast.Attribute)
                and node.value.func.attr == "mark"
            ):
                marks.add(node.targets[0].id)
        elif isinstance(node, _ast.Call):
            if (
                isinstance(node.func, _ast.Attribute)
                and node.func.attr == "undo"
                and len(node.args) == 1
                and isinstance(node.args[0], _ast.Name)
            ):
                undos.add(node.args[0].id)
            elif (
                # TRO's activation mark is consumed by
                # ``trail.commit_fresh(mark, floor)``: it drops the entries
                # since the mark only when all are on variables born after
                # it, and otherwise leaves them to the clause arm's own
                # mark/undo -- nothing is leaked either way.
                isinstance(node.func, _ast.Attribute)
                and node.func.attr == "commit_fresh"
                and len(node.args) == 2
                and isinstance(node.args[0], _ast.Name)
                and node.args[0].id == "_tro_mark"   # tro._TRO_MARK_NAME
            ):
                undos.add(node.args[0].id)

    issues = list(nested_issues)
    for m in marks - undos:
        issues.append(f"mark {m!r} assigned but never undone")
    for u in undos - marks:
        issues.append(f"undo({u!r}) called but name was never marked")
    return issues


def _make_module(stmts: list):
    """Wrap *stmts* in a synthetic Module so ``ast.walk`` has a root."""
    import ast as _ast
    return _ast.Module(body=stmts, type_ignores=[])


def assert_head_pattern_unify_safe(pattern: Any, head: Any = None) -> None:
    """Equality-vs-unification invariant — ``head_match.py`` (Phase 6).

    A compiled clause-head ``match`` pattern must never contain a bare
    :class:`ast.MatchValue` (``==`` match) or :class:`ast.MatchSingleton`
    (identity match).  Both succeed only when the deref'd caller argument
    *already equals* the literal (input mode); an unbound ``Var`` caller
    (output / var-query mode) silently fails the match and never *binds* the
    literal, yielding no solution.  Every atomic head literal must instead be
    captured (``MatchAs``) and routed through a ``unify()`` guard in the arm
    body (which binds a Var and rejects a mismatch) — the invariant established
    by the equality-vs-unification audit (``todo/equality-vs-unification-audit``).

    This locks that audit in: the numeric / bool / None / str / bytes head-
    literal bug class cannot silently regress, because any pattern path that
    re-introduces a bare ``MatchValue`` / ``MatchSingleton`` for a head arg
    fails loudly here at compile time.

    Scope: only **top-level argument** patterns are checked — the direct
    children of the head's outer ``MatchSequence``.  A ``MatchValue`` nested
    *inside* a ``MatchClass`` is the structural-type discriminant (e.g. the
    functor name of ``circle(R)`` in a compound-key-indexed head ``Shape(circle(R),
    R)``): a ``Var`` caller fails the enclosing ``MatchClass`` type-check before
    that inner pattern is ever reached, so it is input-mode-only *by
    construction* and not the bug class.  Likewise first-argument indexing lifts
    a ground-position ``MatchValue`` that is safe by dispatch.  The bug class is
    precisely a bare ``MatchValue`` / ``MatchSingleton`` standing directly at an
    argument slot (``case [_v0, 20000]:``), where the caller arg itself may be an
    unbound Var.
    """
    import ast as _ast
    # Inspect only the direct argument patterns (children of the outer
    # MatchSequence), not nested structural sub-patterns.
    if isinstance(pattern, _ast.MatchSequence):
        arg_patterns = pattern.patterns
    elif isinstance(pattern, (list, tuple)):
        arg_patterns = pattern
    else:
        arg_patterns = [pattern]
    offenders = [
        type(p).__name__
        for p in arg_patterns
        if isinstance(p, (_ast.MatchValue, _ast.MatchSingleton))
    ]
    if offenders:
        raise InvariantError(
            "Phase 6: head-pattern-unify-safe invariant violated. "
            f"A clause-head match pattern emitted {len(offenders)} bare "
            f"{', '.join(sorted(set(offenders)))} node(s) — these match by "
            "``==`` / identity (input mode only) and never bind an unbound Var "
            "caller, so an output / var-query call silently yields no solution. "
            "Atomic head literals must capture the arg and route through a "
            "``unify()`` guard instead (equality-vs-unification audit).\n"
            f"  head: {head!r}"
        )


def assert_trampoline_done_yield_present(funcdef: Any) -> None:
    """README §10 invariant 4 — Phase 6 post (trampoline only).

    Every trampoline-protocol funcdef built with ``emit_done=True``
    must contain at least one ``yield (X, DONE)`` expression.  The
    runtime contract is: a trampoline generator yields
    ``(parent, DONE)`` exactly once after exhausting all
    solutions, which the calling generator detects to terminate
    its ``while _st is not DONE`` loop.

    Bucket sub-functions (``emit_done=False``) are consumed via
    ``yield from`` by an outer wrapper that emits its own DONE,
    and so legitimately have no terminal DONE yield — the caller
    is responsible for invoking this assertion only when
    ``emit_done`` was True.
    """
    import ast as _ast
    found = False
    for node in _ast.walk(funcdef):
        if not isinstance(node, _ast.Yield):
            continue
        v = node.value
        if (
            isinstance(v, _ast.Tuple)
            and len(v.elts) == 2
            and isinstance(v.elts[1], _ast.Name)
            and v.elts[1].id == "$DONE"
        ):
            found = True
            break
    if not found:
        raise InvariantError(
            "Phase 6 post: trampoline-DONE-yield invariant violated. "
            f"Funcdef {funcdef.name!r} was built with emit_done=True "
            "but contains no ``yield (..., DONE)`` expression. "
            "Without it the trampoline driver loop never sees the "
            "termination signal and hangs."
        )


__all__ = [
    "InvariantError",
    "assert_body_vars_preallocated",
    "assert_call_targets_resolved",
    "assert_head_pattern_unify_safe",
    "assert_mark_undo_paired",
    "assert_trampoline_done_yield_present",
]
