"""AST-construction leaf helpers used throughout the compiler.

Pure functions that build small ``ast`` fragments plus the
per-compilation ``FreshNames`` unique-name generator.  No
compiler-internal dependencies beyond
``clausal.pythonic_ast.nodes.TupleLiteral`` (used by ``_in_iter_expr``
to detect ``in`` goals that destructure pairs).
"""

from __future__ import annotations

import ast
from typing import Any

from clausal.pythonic_ast.nodes import TupleLiteral


# ── Source-position helpers (Slice G) ─────────────────────────────────────────
#
# Position tuples are (start_line, start_col, end_line, end_col) — the same
# shape ``pythonic_ast.nodes.Node.position`` carries.
#
# A module-level stack — pushed/popped by
# :meth:`CompilationContext.at_position` — holds the "currently emitting"
# position.  ``_locate`` reads the top non-``None`` entry and stamps the
# four ``ast.AST`` location fields on a node.  The module-level design
# (rather than threading a compile-context handle through every helper
# call) keeps the lowerer match arms readable: a single
# ``with ctx.at_position(ir.position):`` at the top scopes every
# emission inside, no per-call plumbing.
#
# Explicit overrides (``_locate(node, pos)`` with a tuple) still work —
# useful for one-off stamps outside the normal scope flow.


_POSITION_STACK: list = []


def _push_position(pos) -> None:
    _POSITION_STACK.append(pos)


def _pop_position() -> None:
    _POSITION_STACK.pop()


def _current_position():
    for pos in reversed(_POSITION_STACK):
        if pos is not None:
            return pos
    return None


def assert_all_nodes_located(
    tree: ast.AST,
    *,
    allow_synthetic: bool = False,
) -> None:
    """Walk *tree* and raise ``AssertionError`` on any node missing a
    non-zero ``lineno`` / ``col_offset``.

    Slice G closer: replaces :func:`ast.fix_missing_locations` as
    the "every node is located" guarantee before ``compile()``.  That
    stdlib helper silences the question *"what source position should
    this node carry?"* by inheriting from a parent; this walker
    surfaces every un-located node as a loud failure the compiler
    must fix (or explicitly opt out of via *allow_synthetic*).

    Gated by ``CLAUSAL_ASSERT_LOCATIONS=0`` in :func:`maybe_assert_located`
    for emergencies.  Default is always-on.

    *allow_synthetic* accepts nodes marked ``_g_synthetic=True``
    (stamped by :func:`propagate_synthetic_positions` or emitted
    with :data:`SYNTHETIC_POSITION`) — genuine compiler scaffolding
    with no finer source origin than the enclosing ``FunctionDef``.
    """
    bad: list[tuple[str, ast.AST]] = []
    for node in ast.walk(tree):
        # Node types that don't take location fields in Python's AST.
        # ``match_case`` is excluded because Python's AST does not
        # expose location fields on it (it walks into its pattern /
        # body / guard children, which do get located).
        if isinstance(node, (ast.Load, ast.Store, ast.Del,
                             ast.arguments, ast.keyword,
                             ast.withitem, ast.alias,
                             ast.comprehension, ast.match_case)):
            continue
        # Operator leaves (And/Or/Add/...) carry no location fields.
        if isinstance(node, (ast.boolop, ast.operator,
                             ast.unaryop, ast.cmpop,
                             ast.expr_context)):
            continue
        lineno = getattr(node, "lineno", None)
        if lineno is None or lineno == 0:
            if allow_synthetic and getattr(node, "_g_synthetic", False):
                continue
            bad.append((ast.dump(node)[:140], node))
    if bad:
        lines = [f"  {dump}" for dump, _ in bad[:10]]
        more = "" if len(bad) <= 10 else f"\n  ...and {len(bad) - 10} more"
        raise AssertionError(
            f"assert_all_nodes_located: {len(bad)} node(s) missing lineno "
            f"in {getattr(tree, 'name', '<tree>')!r}:\n"
            + "\n".join(lines) + more
        )


# Sentinel used by ``_build_predicate_funcdef`` and similar emitters to
# mark genuinely synthesised scaffolding with no source origin.  The
# walker accepts these when ``allow_synthetic=True``.
SYNTHETIC_POSITION: "tuple[int,int,int,int]" = (1, 0, 1, 0)


def propagate_synthetic_positions(tree: ast.AST) -> None:
    """Stamp the enclosing ``FunctionDef``'s position onto every
    un-located descendant and mark them ``_g_synthetic=True``.

    Slice G7 replacement for :func:`ast.fix_missing_locations`.  The
    distinction is intentional: ``fix_missing_locations`` silently
    inherits from the nearest parent, hiding the question of *where*
    a node came from.  This helper is the explicit opt-in: un-located
    descendants of a stamped ``FunctionDef`` are treated as synthetic
    compiler scaffolding (arg nodes, dispatch ``Match`` boilerplate,
    trampoline exhaustion yield, bucket selectors) that legitimately
    has no finer source origin than "the predicate as a whole".  The
    ``_g_synthetic`` marker lets :func:`assert_all_nodes_located`
    accept these nodes under ``allow_synthetic=True`` while still
    catching real emitter bugs (nodes inside a source-bearing
    construct that forgot to open an ``at_position`` scope).
    """
    pos_line = getattr(tree, "lineno", None)
    if pos_line is None:
        return
    pos_col = getattr(tree, "col_offset", 0)
    pos_end_line = getattr(tree, "end_lineno", pos_line)
    pos_end_col = getattr(tree, "end_col_offset", pos_col)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Load, ast.Store, ast.Del,
                             ast.arguments, ast.keyword,
                             ast.withitem, ast.alias,
                             ast.comprehension, ast.match_case,
                             ast.boolop, ast.operator,
                             ast.unaryop, ast.cmpop,
                             ast.expr_context)):
            continue
        if getattr(node, "lineno", None):
            continue
        node.lineno = pos_line
        node.col_offset = pos_col
        node.end_lineno = pos_end_line
        node.end_col_offset = pos_end_col
        node._g_synthetic = True


def maybe_assert_located(tree: ast.AST) -> None:
    """Propagate synthetic positions then assert every node is located
    (Slice G4/G7).

    Called on every compiled predicate ``FunctionDef``.  First walks
    the tree stamping un-located descendants with the enclosing
    ``FunctionDef``'s position and marking them ``_g_synthetic=True``
    (see :func:`propagate_synthetic_positions`), then runs
    :func:`assert_all_nodes_located` which accepts synthetic-marked
    nodes under ``allow_synthetic=True``.

    Set ``CLAUSAL_ASSERT_LOCATIONS=0`` to skip the assert (the
    propagation still runs — downstream code relies on nodes being
    located for ``compile()`` / traceback purposes).
    """
    propagate_synthetic_positions(tree)
    import os
    if os.environ.get("CLAUSAL_ASSERT_LOCATIONS") == "0":
        return
    assert_all_nodes_located(tree, allow_synthetic=True)


def stamp_predicate_funcdef(
    func_def: ast.FunctionDef,
    clauses,
) -> None:
    """Stamp *func_def* with a predicate-level source position (Slice G5).

    Uses the first clause's ``position`` as the FunctionDef's own
    location.  When no clause carries a position — empty predicate or
    runtime-asserted only — falls back to :data:`SYNTHETIC_POSITION`
    so the strict walker (G4) accepts the node under
    ``allow_synthetic=True``.

    :func:`propagate_synthetic_positions` downstream of this call
    inherits this position onto any un-stamped scaffolding inside
    the FunctionDef, giving synthesised nodes (bucket selectors,
    dispatch fallbacks, no-clause-trampoline exhaustion yield) a
    predicate-level line marked ``_g_synthetic=True``.
    """
    pos = None
    for cl in clauses or ():
        p = getattr(cl, "position", None)
        if p is not None:
            pos = p
            break
    if pos is None:
        pos = SYNTHETIC_POSITION
    sl, sc, el, ec = pos
    func_def.lineno = sl
    func_def.col_offset = sc
    func_def.end_lineno = el
    func_def.end_col_offset = ec


def _locate(node: ast.AST, pos=None) -> ast.AST:
    """Stamp ``lineno``/``col_offset``/``end_*`` on *node*.

    When *pos* is ``None`` (default) the current top-of-stack position
    is used.  Passing an explicit 4-tuple overrides the stack.  Either
    way, ``None`` ⇒ no-op.  Returns the node for chaining.
    """
    if pos is None:
        pos = _current_position()
    if pos is None:
        return node
    sl, sc, el, ec = pos
    node.lineno = sl
    node.col_offset = sc
    node.end_lineno = el
    node.end_col_offset = ec
    return node


# ── Compiled-code naming constants ────────────────────────────────────────────
# Names emitted into generated function signatures and locals.  Centralised
# here (in the deepest-leaf submodule) so any other submodule can import them
# without creating a cycle back through _monolith.
_MARK_PREFIX = "_m"            # fresh mark variable prefix (ctx.fresh(_MARK_PREFIX))
_TRAIL_PARAM_NAME = "trail"    # compiled-function trail parameter
_K_PARAM_NAME = "k"            # shallow-strategy continuation parameter
_DISP_PREFIX = "$disp_"        # locked-dispatch globals-key prefix
# Phase 2: split-continuation protocol — the old single ``_tramp_parent``
# parameter is replaced by three named slots.  See
# ``implementation_plans/compiler/CONTINUATION_TCO_PLAN.md`` §3.
_PROCEED_PARAM_NAME = "_proceed"       # trampoline: solution target
_FAIL_PARAM_NAME    = "_fail"          # trampoline: exhaustion target
_CATCHER_PARAM_NAME = "_catcher"       # trampoline: exception handler chain
_THIS_GEN_NAME = "this_generator"      # trampoline self-reference parameter


# Python 3.12+ added type_params to FunctionDef.  Spread into ast.FunctionDef
# kwargs so the compiler stays compatible with both 3.11 and 3.12+.
_EXTRA_FUNCDEF: dict = (
    {"type_params": []} if "type_params" in ast.FunctionDef._fields else {}
)


# ── ast helpers ────────────────────────────────────────────────────────────────


def _name(id_: str, expr_ctx=None) -> ast.Name:
    return _locate(ast.Name(id=id_, ctx=expr_ctx or ast.Load()))


def _attr(obj_name: str, attr: str) -> ast.Attribute:
    return _locate(
        ast.Attribute(value=_name(obj_name), attr=attr, ctx=ast.Load())
    )


def _call(func: ast.expr, *args: ast.expr, **kwargs_: ast.expr) -> ast.Call:
    kws = [ast.keyword(arg=k, value=v) for k, v in kwargs_.items()]
    return _locate(ast.Call(func=func, args=list(args), keywords=kws))


# ── Unique-name counter ────────────────────────────────────────────────────────


class FreshNames:
    """Per-compilation fresh-name generator.

    One instance lives on ``CompilationContext.fresh`` and is shared
    across all ``ctx.replace()`` forks of a single compilation, so each
    invocation of ``compile_predicate_*`` sees a monotonic counter that
    starts at 1.  Two separate compilations get two separate counters —
    the AST output of one compilation no longer depends on how many
    predicates were compiled earlier in the process.
    """

    __slots__ = ("_n",)

    def __init__(self, starting_at: int = 0) -> None:
        # ``starting_at`` lets the Slice D4 harness clone a counter at
        # the same point as the legacy run so the IR shadow emits
        # identical fresh names without poking ``_n`` directly.
        self._n = starting_at

    def __call__(self, prefix: str = "_t") -> str:
        self._n += 1
        return f"{prefix}{self._n}"


# ── Misc AST-building helpers ──────────────────────────────────────────────────


def _drained(k_stmts: list[ast.stmt], trail_name: str) -> list[ast.stmt]:
    """*k_stmts* behind a goal boundary: ``for _ in $pending(trail): k``.

    A unification may wake goals (``freeze/2``, ``when/2``) that queue on the
    trail; the rest of the clause must see their bindings, once per answer.
    With nothing queued ``$pending`` is ``(None,)`` and *k* runs once.
    """
    if not k_stmts or _is_trampoline_leaf(k_stmts):
        return k_stmts
    return [ast.For(
        target=_name("_", ast.Store()),
        iter=_call(_name("$pending"), _name(trail_name)),
        body=k_stmts,           # the same list: compiled once, never copied
        orelse=[],
    )]


def _is_trampoline_leaf(k_stmts: list[ast.stmt]) -> bool:
    """``[yield (_proceed, None)]``: a trampoline solution step, whose own
    goal boundary (``StepGenerator.send``) runs the queued goals."""
    if len(k_stmts) != 1:
        return False
    s = k_stmts[0]
    if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Yield)):
        return False
    v = s.value.value
    return (isinstance(v, ast.Tuple) and len(v.elts) == 2
            and isinstance(v.elts[0], ast.Name) and v.elts[0].id == "_proceed"
            and isinstance(v.elts[1], ast.Constant) and v.elts[1].value is None)


def _unify_drained(l_expr: ast.expr, r_expr: ast.expr, trail_name: str,
                   k_stmts: list[ast.stmt]) -> ast.stmt:
    """``for _ in $unify_iter(l, r, trail): k`` -- unify, then *k* behind a
    goal boundary: not at all on failure, once per answer of the goals the
    unification woke, once when it woke none.  One call."""
    return ast.For(
        target=_name("_", ast.Store()),
        iter=_call(_name("$unify_iter"), l_expr, r_expr, _name(trail_name)),
        body=k_stmts or [ast.Pass()],
        orelse=[],
    )


def _yield_none_stmt() -> ast.stmt:
    return _locate(
        ast.Expr(value=_locate(ast.Yield(value=_locate(ast.Constant(value=None)))))
    )


def _assign(target: str, value: ast.expr) -> ast.stmt:
    pos = _current_position()
    if pos is not None:
        sl, sc, el, ec = pos
        return ast.Assign(
            targets=[_name(target, ast.Store())],
            value=value,
            lineno=sl, col_offset=sc,
            end_lineno=el, end_col_offset=ec,
        )
    # No active scope: leave location fields unset so
    # ``propagate_synthetic_positions`` can stamp them from the
    # enclosing FunctionDef and mark them ``_g_synthetic=True``.
    return ast.Assign(
        targets=[_name(target, ast.Store())],
        value=value,
    )


def _assign_mark(mark_name: str, trail_name: str) -> ast.stmt:
    return _assign(mark_name, _call(_attr(trail_name, "mark")))


def _undo_stmt(mark_name: str, trail_name: str) -> ast.stmt:
    return _locate(ast.Expr(value=_call(_attr(trail_name, "undo"), _name(mark_name))))


def _if(test: ast.expr, body: list[ast.stmt]) -> ast.If:
    return _locate(
        ast.If(test=test, body=body or [_locate(ast.Pass())], orelse=[])
    )


def _in_iter_expr(elem: Any, coll_expr: ast.expr,
                  trail_expr: "ast.expr | None" = None) -> ast.expr:
    """Build the iterator expression for an ``in`` goal.

    Always ``_in_iter(deref(coll), <pair_mode>)``; *elem* being a TupleLiteral
    is what makes it pair mode, so a DictTerm yields (key, value) pairs
    instead of keys.

    KEY mode used to emit a bare ``deref(coll)`` and let the ``for`` loop use
    Python's own iteration, which reads a caller's PLAIN dict raw: ``K in
    {"": 1}`` enumerated the key ``""`` while ``gen_dict/3``/``dict_keys/2``
    over the same term yield the canonical ``()`` (Task 15 fix round 5, item
    1).  Both modes go through the one funnel now, so the nil fold — and
    ``_in_iter``'s other term-level readings, notably THE FLIP's char atoms
    for a ``str`` collection — apply to both.
    """
    args = [_call(_name("$deref"), coll_expr),
            _locate(ast.Constant(value=isinstance(elem, TupleLiteral)))]
    if trail_expr is not None:
        # the positive ``in`` goal: an OPEN list enumerates member/2's
        # candidates, binding (and undoing) the tail through this trail
        args.append(trail_expr)
    return _call(_name("$in_iter"), *args)
