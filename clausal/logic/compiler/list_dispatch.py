"""List-structure dispatch helpers.

Helpers used by the predicate-compilation entrypoints to detect whether
the same head-argument position always destructures to a list in every
clause (``_find_list_dispatch_pos``), and to emit wildcard captures +
list-guard checks for those positions (``_build_list_dispatch_guard``).

``_lift_clause_at_pos`` rewrites a clause so the given position is a
wildcard capture whose structure is checked at runtime instead of in
the match pattern — used together with ``_build_list_dispatch_guard``.
"""

from __future__ import annotations

import ast
from typing import Any

from clausal.logic.variables import is_var, deref  # noqa: F401
from clausal.terms import (
    Compound,
    Call, LoadName, LoadAttr,  # noqa: F401
    PyThunk, Unify,
)
from clausal.pythonic_ast.nodes import StarUnpack  # noqa: F401
from clausal.logic.predicate import is_term_instance, term_field_names, term_field_dict
from clausal.logic.database import Clause

from ._ast_helpers import _name, _call, _assign, _if, _MARK_PREFIX  # noqa: F401
from .head_match import (
    head_to_match_pattern, compile_head_to_match_case, _head_arg_patterns,
    _wrap_yields_with_output_guards,
)
from .terms_to_ast import (  # noqa: F401
    term_to_ast_expr, cell_signature_for_name, _is_opaque_head_literal,
)
from clausal.logic.cells import TUPLE_TAG


# ── Phase 5: deep structural indexing helpers ──────────────────────────────────


def _get_head_arg(clause: Clause, pos: int) -> Any:
    """Return the argument at position *pos* from the clause head (or None).

    No cell branch, deliberately (P3-2 Task 3, plan claim verified rather than
    assumed): this reads the HEAD TERM, and in P3-2 a head is still a predicate
    instance or a ``Compound`` — never a cell.  ``database.head_key`` raises on
    a tuple head and ``database_ops._reject_cell_head`` turns an ``assertz`` of
    one into ``permission_error(modify, static_procedure, f/N)``, so no cell
    can reach here as a *head*.  Cell head ARGUMENTS are a different question
    and are handled by the callers below.  Cell heads are P3-3.
    """
    head = clause.head
    if isinstance(head, Compound):
        return head.args[pos] if pos < len(head.args) else None
    if is_term_instance(head):
        fields = list(term_field_names(head))
        return getattr(head, fields[pos]) if pos < len(fields) else None
    return None


def _carries_an_uninjected_head_literal(term: Any) -> bool:
    """True if lifting *term* into a head would emit a pattern naming a
    ``$headlit_<id>`` global that nothing injected.

    P3-2 Task 3, found by driving a lifted bucket rather than by reading it.
    ``_collect_globals_info`` walks the PRE-lift clauses, and only its HEAD
    walker records ``$headlit_<id>`` entries — a body walk records call
    targets and ``_pyt_<id>`` thunks instead.  So a value that
    ``head_to_match_pattern`` compiles to an opaque-literal capture is
    reachable from a body ``Unify`` but has no global if the lift moves it
    into the head afterwards, and the bucket raises ``NameError`` the first
    time it is entered.

    A nested ``PyThunk`` (a quantity/currency literal, an f-string, a ``++()``
    escape) is the reachable case from ``.clausal`` source, and it is also
    WRONG on its own terms — the same reason the top-level ``PyThunk`` skip
    above exists: nothing on the head-match path evaluates a thunk, so the
    pattern would guard against the thunk OBJECT and the clause could never
    fire.  This is that skip, applied one level down.

    Deliberately scoped to the ``Call`` branch that Task 3 opened.  The same
    hazard exists in principle for a lifted ``Compound`` carrying a nested
    ``date``, but that lift predates this task and changing it would change
    answers outside Task 3's remit; it is recorded in the report instead.

    A CELL nested inside the reference is recursed INTO rather than treated
    as a leaf: the live-cell branch of ``head_to_match_pattern`` matches it
    structurally, above the opaque-literal capture, so it needs no injected
    global of its own (the tuple-DATA tag names ``$cells``, which the
    compilation injects unconditionally).
    """
    if isinstance(term, PyThunk):
        return True
    if isinstance(term, Call):
        return (
            any(_carries_an_uninjected_head_literal(a) for a in term.args)
            or any(_carries_an_uninjected_head_literal(kw.value)
                   for kw in (term.kwargs or []))
        )
    if isinstance(term, Compound):
        return any(_carries_an_uninjected_head_literal(a) for a in term.args)
    if isinstance(term, list):
        return any(_carries_an_uninjected_head_literal(e) for e in term)
    if type(term) is tuple and term and (
            isinstance(term[0], str) or term[0] is TUPLE_TAG):
        return any(_carries_an_uninjected_head_literal(e) for e in term[1:])
    return _is_opaque_head_literal(term)


def _lift_clause_at_pos(clause: Clause, pos: int,
                        globals_: dict | None = None) -> Clause:
    """Phase 8: lift the body Unify for head position *pos* into the head.

    in_ bucket compilation contexts the indexed argument is already guaranteed
    ground by the dispatch layer.  Any leading body ``Unify(Var_at_pos, val)``
    is therefore redundant and can be absorbed into the head, letting
    ``head_to_match_pattern`` emit a ``MatchValue``/``MatchClass`` pattern
    rather than a wildcard capture.  This eliminates one ``trail.mark()`` +
    ``unify(...)`` + ``trail.undo()`` triple per clause per invocation.

    The transformation is a no-op when:
    - the head arg at *pos* is already a concrete term (not a Var), or
    - no matching ``Unify`` is found in the body's clean prefix (the
      contiguous run of ``Unify`` goals before the first non-``Unify`` goal), or
    - the lifted term is a ``str``/``bytes`` literal (Phase 2 Task 8 / F095):
      lifting would emit a ``MatchValue`` pattern that uses ``==`` for the
      head match, which fails the strings-as-lists contract when the caller
      arrives via a coalesced str/charlist bucket (e.g. a caller passing
      ``['a','b','c']`` reaching a bucket containing a clause originally
      keyed under ``"abc"``).  Leaving str/bytes unlifted keeps the body
      ``Unify`` in place where runtime ``unify`` correctly handles the
      str↔list duality.

    *globals_* is the namespace the lifted head will be MATCHED against —
    pass the same dict ``head_to_match_pattern`` will get (the compilation's
    ``base_globals``), so the two halves cannot disagree about what a name
    means.  It is what decides the ``Call(LoadName)`` case below.

    Only called from the indexed bucket path — the fallback function always
    uses the original unlifted clauses.
    """
    head = clause.head
    # Extract the head arg at pos
    if isinstance(head, Compound):
        if pos >= len(head.args):
            return clause
        head_arg = deref(head.args[pos])
    elif is_term_instance(head):
        fields = list(term_field_names(head))
        if pos >= len(fields):
            return clause
        head_arg = deref(getattr(head, fields[pos]))
    else:
        return clause

    # Only lift when the head arg is an unbound Var
    if not is_var(head_arg):
        return clause
    vid = head_arg._id

    # Scan the body clean prefix for Unify(Var_vid, term) or Unify(term, Var_vid)
    # Stop at the first non-Unify goal (that is the clean-prefix boundary).
    unify_idx = None
    lift_term = None
    for i, goal in enumerate(clause.body):
        if not isinstance(goal, Unify):
            break  # end of clean prefix
        left_d = deref(goal.left)
        right_d = deref(goal.right)
        if is_var(left_d) and left_d._id == vid and not is_var(right_d):
            unify_idx = i
            lift_term = goal.right   # use original (not deref'd) for nested Vars
            break
        if is_var(right_d) and right_d._id == vid and not is_var(left_d):
            unify_idx = i
            lift_term = goal.left
            break
        # Other Unify for a different var — keep scanning

    if unify_idx is None:
        return clause  # no liftable unification found

    # Phase 2 Task 8 (F095): skip the lift when the lifted term is a str
    # or bytes literal.  See docstring above for the strings-as-lists
    # rationale — lifting a str would emit a ``MatchValue`` head pattern
    # that breaks list callers reaching this clause via the coalesced
    # str/charlist bucket built by ``arg_index._arg_to_index_key``.
    if isinstance(lift_term, (str, bytes)):
        return clause

    # Skip the lift when the lifted term is a PyThunk (quantity/currency
    # literal, f-string, ``++()`` escape) — the Unify being lifted is the one
    # ``_normalize_structural_head_args`` created precisely to keep the thunk
    # out of the head: ``head_to_match_pattern`` has no branch that evaluates
    # a thunk, so lifting it back re-creates the dead-clause capture that the
    # hoist fixed.  The body ``Unify`` evaluates the thunk at runtime instead.
    if isinstance(lift_term, PyThunk):
        return clause

    # Skip the lift when the lifted term is a bare name reference
    # (``LoadName('Red')`` / ``LoadAttr(mod, 'Red')``) — an unresolved 0-arity
    # atom, e.g. the RHS of the ``Unify`` that a keyword-atom fact
    # ``Color(C=Red)`` compiles to.  ``head_to_match_pattern`` would emit a
    # ``MatchClass(LoadName, ...)`` pattern that no runtime value matches (the
    # reference resolves to a ``PredicateMeta`` atom, never a ``LoadName``
    # node), so the bucket would yield nothing.  Leaving the body ``Unify`` in
    # place lets the runtime resolve the reference to the atom and unify it.
    if isinstance(lift_term, (LoadName, LoadAttr)):
        return clause

    # A compound reference (``Call(LoadName('point'), …)`` — the shape every
    # compound written in ``.clausal`` source has).  Whether it may be lifted
    # is decided HERE, once, by asking what the name means.
    #
    # P3-2 Task 3.  Pre-flip this was an unconditional refusal, and the reason
    # given was about the bucket's globals: ``_collect_globals_info`` ran on
    # the pre-lift clauses, where the functor lived in a body ``Unify`` and was
    # recorded as a call *target*, not as a head term *class*, so
    # ``head_to_match_pattern`` could not resolve the ``LoadName`` and fell
    # back to ``MatchClass(Call, …)`` — a pattern no runtime term matches, so
    # the bucket yielded nothing.
    #
    # A DATA functor reference dissolves that reason entirely: it compiles to
    # a cell, and a cell pattern is a plain sequence LITERAL —
    # ``case ('point', x, y)`` resolves nothing at match time.  The only
    # resolution left is the one done right here, at LIFT time, and it reads
    # the full module namespace rather than the bucket's collected globals.
    #
    # Still refused, for the same reason as before:
    # * a name bound to a ``PredicateMeta`` (R6b: a ``name/arity`` export
    #   declares a predicate, and a predicate reference has no cell pattern),
    # * a name nothing resolves — no namespace, no registry entry, no class,
    # * a ``Call(LoadAttr(...))`` chain: ``head_to_match_pattern`` has a
    #   ``Call(LoadName)`` branch and no ``LoadAttr`` one, so lifting one would
    #   re-create exactly the dead ``MatchClass(Call, …)`` this refusal
    #   existed to avoid.  (A module-qualified reference reaches the term world
    #   as a single DOTTED ``LoadName`` — see ``_resolve_functor_binding`` —
    #   so R5's cross-module case goes through the branch above, not here.)
    # * a reference with an OPAQUE value nested anywhere inside it — see
    #   ``_carries_an_uninjected_head_literal``.
    #
    # In every refused case the body ``Unify`` stays where it is and the
    # runtime resolves the reference, exactly as the non-indexed fallback path
    # does; bucket SELECTION still keys the clause correctly via
    # ``arg_index._arg_to_index_key``.
    if isinstance(lift_term, Call) and isinstance(
        lift_term.func, (LoadName, LoadAttr)
    ):
        if not isinstance(lift_term.func, LoadName):
            return clause
        if cell_signature_for_name(lift_term.func.name, globals_) is None:
            return clause
        if _carries_an_uninjected_head_literal(lift_term):
            return clause

    # Rebuild head with lift_term at pos
    if isinstance(head, Compound):
        new_args = list(head.args)
        new_args[pos] = lift_term
        new_head = Compound(head.functor, tuple(new_args))
    else:  # is_term_instance
        fields = list(term_field_names(head))
        new_kwargs = term_field_dict(head)
        new_kwargs[fields[pos]] = lift_term
        new_head = type(head)(**new_kwargs)

    # Remove the matched Unify from the body
    new_body = clause.body[:unify_idx] + clause.body[unify_idx + 1:]
    return Clause(head=new_head, body=new_body)


def _classify_list_key(arg: Any) -> str:
    """Classify a head argument as ``"nil"``, ``"cons"``, ``"var"``, or ``"other"``.

    - ``"nil"``  — argument is the empty list ``[]``
    - ``"cons"`` — argument is a non-empty Python list (may contain Vars)
    - ``"var"``  — argument is an unbound Var (wildcard, matches anything)
    - ``"other"``— anything else (integer, string, Compound, …)
    """
    arg = deref(arg)
    if is_var(arg):
        return "var"
    if isinstance(arg, list):
        return "nil" if not arg else "cons"
    return "other"


def _find_list_dispatch_pos(clauses: list[Clause], arity: int) -> int | None:
    """Find the best argument position for list structural dispatch.

    Returns the position index when ALL clauses have nil/cons/var heads at that
    position (no scalars or compound terms) AND both ``"nil"`` and ``"cons"``
    appear in the clause set — guaranteeing the dispatch saves work.

    Returns ``None`` if no suitable position is found.
    """
    if arity == 0 or len(clauses) < 2:
        return None
    best_pos = None
    best_score = 0
    for pos in range(arity):
        keys = [_classify_list_key(_get_head_arg(c, pos)) for c in clauses]
        if "other" in keys:
            continue  # mixed list + non-list types at this position
        list_keys = {k for k in keys if k != "var"}
        score = len(list_keys)  # 0 (all var), 1 (only nil or only cons), or 2
        if score >= 2 and score > best_score:
            best_pos = pos
            best_score = score
    return best_pos


def _build_list_dispatch_guard(
    clauses: list[Clause],
    dispatch_pos: int,
    arity: int,
    subject: ast.expr,
    body_compiler: Callable[[Clause, dict[int, str]], list[ast.stmt]],
) -> list[ast.stmt]:
    """Build the isinstance/is_var structural dispatch guard for list predicates.

    Generates:

        if isinstance(_d_pos, (list, str, bytes)):
            if not _d_pos:          # nil branch
                <nil_clauses + var_clauses>
            else:                   # cons branch
                <cons_clauses + var_clauses>
        elif is_var(_d_pos):        # unbound — try all clauses
            <all clauses>
        else:                       # int/tuple/SegList/… → all-clauses scan
            <all clauses>           # (nil/cons arms fail their list guards)

    ``var_clauses`` (wildcard heads) appear in both the nil and cons branches
    because a wildcard matches any list.  They also appear in the is_var
    fallback because the variable might be bound to any list at call time.
    """
    nil_clauses: list[Clause] = []
    cons_clauses: list[Clause] = []
    var_clauses: list[Clause] = []
    for c in clauses:
        key = _classify_list_key(_get_head_arg(c, dispatch_pos))
        if key == "nil":
            nil_clauses.append(c)
        elif key == "cons":
            cons_clauses.append(c)
        else:  # "var"
            var_clauses.append(c)

    def _match_stmts(subset: list[Clause]) -> list[ast.stmt]:
        stmts: list[ast.stmt] = []
        for clause in subset:
            vc: dict[int, str] = {}
            _head_arg_patterns(clause.head, vc, arity)
            body_stmts = body_compiler(clause, vc)
            case_arm = compile_head_to_match_case(
                head=clause.head,
                body_stmts=body_stmts,
                var_context=vc,
                arity=arity,
            )
            stmts.append(ast.Match(subject=subject, cases=[case_arm]))
        return stmts or [ast.Pass()]

    nil_body = _match_stmts(nil_clauses + var_clauses)
    cons_body = _match_stmts(cons_clauses + var_clauses)
    var_body = _match_stmts(nil_clauses + cons_clauses + var_clauses)
    # A02-F002: callers that are neither list/str/bytes nor an unbound Var
    # (int, tuple, a non-ground SegList, …) previously fell through to DONE,
    # silently losing every clause the arg would unify with. Run all clauses
    # through their match arms — the nil/cons arms fail their list guards on a
    # non-list, and the cons guard routes SegLists through
    # ``$head_list_unify_input`` — so this matches the un-dispatched compile.
    other_body = _match_stmts(nil_clauses + cons_clauses + var_clauses)

    deref_name = f"_d{dispatch_pos}"

    # if not _d_pos: <nil> else: <cons>
    nil_vs_cons = ast.If(
        test=ast.UnaryOp(op=ast.Not(), operand=_name(deref_name)),
        body=nil_body,
        orelse=cons_body,
    )

    # elif is_var(_d_pos): <all>  else: <all-clauses fallback>
    is_var_branch = ast.If(
        test=_call(_name("is_var"), _name(deref_name)),
        body=var_body,
        orelse=other_body,
    )

    # if isinstance(_d_pos, (list, str, bytes)): <nil_vs_cons>
    # elif is_var: <all>  else: <all-clauses fallback>
    # Strings/bytes are treated as lists (of chars / codes) for head matching.
    _list_str_bytes = ast.Tuple(
        elts=[_name("list"), _name("str"), _name("bytes")], ctx=ast.Load(),
    )
    return [
        ast.If(
            test=_call(_name("isinstance"), _name(deref_name), _list_str_bytes),
            body=[nil_vs_cons],
            orelse=[is_var_branch],
        )
    ]


