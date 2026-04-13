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
    Call, LoadName,  # noqa: F401
    Unify,
)
from clausal.pythonic_ast.nodes import StarUnpack  # noqa: F401
from clausal.logic.predicate import is_term_instance, term_field_names
from clausal.logic.database import Clause

from ._ast_helpers import _name, _call, _assign, _if, _MARK_PREFIX  # noqa: F401
from .head_match import (
    head_to_match_pattern, compile_head_to_match_case, _head_arg_patterns,
    _wrap_yields_with_output_guards,
)
from .terms_to_ast import term_to_ast_expr  # noqa: F401


# ── Phase 5: deep structural indexing helpers ──────────────────────────────────


def _get_head_arg(clause: Clause, pos: int) -> Any:
    """Return the argument at position *pos* from the clause head (or None)."""
    head = clause.head
    if isinstance(head, Compound):
        return head.args[pos] if pos < len(head.args) else None
    if is_term_instance(head):
        fields = list(term_field_names(head))
        return getattr(head, fields[pos]) if pos < len(fields) else None
    return None


def _lift_clause_at_pos(clause: Clause, pos: int) -> Clause:
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
      contiguous run of ``Unify`` goals before the first non-``Unify`` goal).

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

    # Rebuild head with lift_term at pos
    if isinstance(head, Compound):
        new_args = list(head.args)
        new_args[pos] = lift_term
        new_head = Compound(head.functor, tuple(new_args))
    else:  # is_term_instance
        fields = list(term_field_names(head))
        new_kwargs = {f: getattr(head, f) for f in fields}
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

        if isinstance(_d_pos, list):
            if not _d_pos:          # nil branch
                <nil_clauses + var_clauses>
            else:                   # cons branch
                <cons_clauses + var_clauses>
        elif is_var(_d_pos):        # unbound — try all clauses
            <all clauses>
        # non-list, non-var → falls through to yield _DONE

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

    deref_name = f"_d{dispatch_pos}"

    # if not _d_pos: <nil> else: <cons>
    nil_vs_cons = ast.If(
        test=ast.UnaryOp(op=ast.Not(), operand=_name(deref_name)),
        body=nil_body,
        orelse=cons_body,
    )

    # elif is_var(_d_pos): <all>
    is_var_branch = ast.If(
        test=_call(_name("is_var"), _name(deref_name)),
        body=var_body,
        orelse=[],
    )

    # if isinstance(_d_pos, (list, str)): <nil_vs_cons> elif is_var(_d_pos): <all>
    # Strings are treated as lists of characters for head pattern matching.
    _list_or_str = ast.Tuple(
        elts=[_name("list"), _name("str")], ctx=ast.Load(),
    )
    return [
        ast.If(
            test=_call(_name("isinstance"), _name(deref_name), _list_or_str),
            body=[nil_vs_cons],
            orelse=[is_var_branch],
        )
    ]


