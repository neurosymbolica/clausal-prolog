"""clausal.logic.specialization — Meta-interpreter specialization via partial deduction.

Specializes a meta-interpreter (MI) with respect to a known object program,
producing residual clauses with MI overhead (MatchClause, Append, CopyTerm)
removed and extensions (counting, depth, proof trees) woven in.

Two entry points:

    analyze_mi(pred_cls) → MIPattern
        Inspect the clauses of a PredicateMeta MI and return a structured
        description of its pattern (base case, recursive case, style, etc.).

    specialize_mi(pattern, object_program, new_name, module_dict) → PredicateMeta
        Unfold the MI with respect to the object program and produce a new
        compiled predicate with the given name.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from clausal.logic.variables import Var, deref, is_var, unify, Trail
from clausal.logic.predicate import (
    PredicateMeta,
    make_predicate,
    is_term_instance,
    term_field_names,
)
from clausal.logic.database import Clause, head_key
from clausal.logic.builtins.inspection import _copy_term
from clausal.pythonic_ast.nodes import (
    Call,
    LoadName,
    StarUnpack,
    Unify,
    Evaluate,
    Gt,
    Lt,
    GtE,
    LtE,
)


class CannotSpecialize(Exception):
    """Raised when the MI pattern cannot be recognized or specialized."""
    pass


@dataclasses.dataclass
class MIPattern:
    """Recognized meta-interpreter structure."""

    name: str                       # e.g. "SolveCount"
    arity: int                      # e.g. 3
    goal_arg: int                   # index of goal-list field (0-indexed)
    program_arg: int                # index of program field (0-indexed)
    extra_args: list[int]           # indices of extra fields (count, depth, tree)
    base_clause: Clause             # the [] base case
    recursive_clause: Clause        # the [GOAL, *GOALS] case
    pre_match_goals: list           # goals before MatchClause
    post_match_goals: list          # goals after last MI-related call
    match_clause_index: int         # index of MatchClause call in recursive body
    append_index: int | None        # index of Append call (None for split style)
    recursive_call_indices: list[int]  # indices of recursive MI calls in body
    recursive_call_style: str       # "tail" or "split"

    # Variables from the recursive clause (populated during analysis)
    goal_var: Any = None            # GOAL variable from [GOAL, *GOALS]
    goals_var: Any = None           # GOALS variable from [GOAL, *GOALS]
    body_var: Any = None            # BODY variable from MatchClause
    all_goals_var: Any = None       # ALL_GOALS variable from Append (tail style)
    program_var: Any = None         # PROGRAM variable in recursive clause head


def analyze_mi(pred_cls: PredicateMeta, program_arg: int | None = None) -> MIPattern:
    """Analyze a meta-interpreter's clauses and return a structured pattern.

    Parameters
    ----------
    pred_cls : PredicateMeta
        The MI predicate class (e.g. ``SolveCount``).
    program_arg : int, optional
        Which field index carries the object program.  If None, auto-detected
        by looking for a field named ``PROGRAM`` or ``_PROGRAM``.

    Returns
    -------
    MIPattern

    Raises
    ------
    CannotSpecialize
        If the clauses don't match a recognized MI pattern.
    """
    clauses = pred_cls._clauses
    fields = pred_cls._fields
    name = pred_cls.__name__
    arity = len(fields)

    if len(clauses) < 2:
        raise CannotSpecialize(
            f"{name}: expected at least 2 clauses (base + recursive), "
            f"got {len(clauses)}"
        )

    # ── Identify the program argument ──────────────────────────────────────
    if program_arg is None:
        program_arg = _find_program_arg(fields)
    if program_arg < 0 or program_arg >= arity:
        raise CannotSpecialize(
            f"{name}: program_arg={program_arg} out of range for arity {arity}"
        )

    # ── Identify the goal-list argument ────────────────────────────────────
    goal_arg = _find_goal_arg(clauses, fields, program_arg)

    # ── Identify extra arguments ───────────────────────────────────────────
    extra_args = [i for i in range(arity) if i != goal_arg and i != program_arg]

    # ── Separate base and recursive clauses ────────────────────────────────
    base_clause = None
    recursive_clause = None
    for c in clauses:
        if _is_base_clause(c, fields, goal_arg):
            base_clause = c
        elif _is_recursive_clause(c, fields, goal_arg):
            recursive_clause = c

    if base_clause is None:
        raise CannotSpecialize(f"{name}: no base clause found (empty goal list)")
    if recursive_clause is None:
        raise CannotSpecialize(
            f"{name}: no recursive clause found ([GOAL, *GOALS] pattern)"
        )

    # ── Analyze the recursive clause body ──────────────────────────────────
    body = recursive_clause.body
    head = recursive_clause.head

    # Extract GOAL and GOALS variables from head's goal-list field.
    goal_field_name = fields[goal_arg]
    goal_list = getattr(head, goal_field_name)
    goal_var, goals_var = _extract_goal_goals(goal_list)

    # Extract PROGRAM variable from head.
    program_field_name = fields[program_arg]
    program_var = getattr(head, program_field_name)

    # Find MatchClause call in body.
    match_idx = _find_call(body, "MatchClause")
    if match_idx is None:
        raise CannotSpecialize(f"{name}: no MatchClause call in recursive body")

    match_call = body[match_idx]
    # MatchClause(GOAL, BODY, PROGRAM) — extract BODY variable.
    body_var = match_call.args[1]

    # Find Append call (for tail-recursive style).
    append_idx = _find_call(body, "Append")

    # Find recursive self-calls.
    recursive_indices = _find_all_calls(body, name)
    if not recursive_indices:
        raise CannotSpecialize(f"{name}: no recursive self-call in body")

    # Determine style.
    if len(recursive_indices) == 1 and append_idx is not None:
        style = "tail"
    elif len(recursive_indices) == 2 and append_idx is None:
        style = "split"
    elif len(recursive_indices) == 1 and append_idx is None:
        # Could be tail without Append (unusual) — treat as tail.
        style = "tail"
    else:
        raise CannotSpecialize(
            f"{name}: unrecognized pattern — {len(recursive_indices)} recursive "
            f"calls, append={'present' if append_idx is not None else 'absent'}"
        )

    # Extract ALL_GOALS variable for tail style.
    all_goals_var = None
    if style == "tail" and append_idx is not None:
        append_call = body[append_idx]
        all_goals_var = append_call.args[2]  # Append(BODY, GOALS, ALL_GOALS)

    # Classify pre-match and post-match goals.
    # Pre-match: goals before MatchClause that aren't MatchClause/Append/recursive.
    mi_indices = {match_idx}
    if append_idx is not None:
        mi_indices.add(append_idx)
    mi_indices.update(recursive_indices)

    pre_match_goals = [body[i] for i in range(match_idx) if i not in mi_indices]
    # Post-match: goals after the last MI-related index.
    last_mi_idx = max(mi_indices)
    post_match_goals = [body[i] for i in range(last_mi_idx + 1, len(body))
                        if i not in mi_indices]

    return MIPattern(
        name=name,
        arity=arity,
        goal_arg=goal_arg,
        program_arg=program_arg,
        extra_args=extra_args,
        base_clause=base_clause,
        recursive_clause=recursive_clause,
        pre_match_goals=pre_match_goals,
        post_match_goals=post_match_goals,
        match_clause_index=match_idx,
        append_index=append_idx,
        recursive_call_indices=recursive_indices,
        recursive_call_style=style,
        goal_var=goal_var,
        goals_var=goals_var,
        body_var=body_var,
        all_goals_var=all_goals_var,
        program_var=program_var,
    )


# ── Unfolder ──────────────────────────────────────────────────────────────────


def specialize_mi(
    pattern: MIPattern,
    object_program: list,
    new_name: str,
    module_dict: dict | None = None,
    pred_cls: PredicateMeta | None = None,
) -> PredicateMeta:
    """Specialize an MI with respect to an object program.

    Parameters
    ----------
    pattern : MIPattern
        The analyzed MI structure from ``analyze_mi()``.
    object_program : list
        The object program as a list of ``[head, body_goals]`` pairs,
        where head is ``["functor", arg1, ...]`` and body_goals is a list
        of such terms.
    new_name : str
        Name for the specialized predicate.
    module_dict : dict, optional
        Module dictionary for predicate resolution.  If provided, the new
        predicate class is installed here.
    pred_cls : PredicateMeta, optional
        Pre-existing predicate class to use instead of creating a new one.
        Used by the pipeline to reuse a class pre-registered at Step 1c.

    Returns
    -------
    PredicateMeta
        The specialized predicate class with clauses installed and compiled.
    """
    fields = _specialized_fields(pattern)
    if pred_cls is None:
        pred_cls = make_predicate(new_name, fields)

    clauses = _unfold(pattern, object_program, pred_cls)

    # Install clauses and compile.
    from clausal.logic.database import Database
    from clausal.logic.compiler import compile_predicate_trampoline

    db = Database(module_dict=module_dict)
    for clause in clauses:
        db.assertz(clause)
        pred_cls._assertz(clause)

    globals_ = module_dict or {}
    globals_[new_name] = pred_cls

    compile_predicate_trampoline(
        new_name, len(fields), clauses, db,
        globals_=globals_, pred_cls=pred_cls,
    )

    return pred_cls


def _specialized_fields(pattern: MIPattern) -> list[str]:
    """Compute field names for the specialized predicate.

    Drops the program argument; keeps goal-list and extra args in order.
    """
    orig_fields = list(pattern.recursive_clause.head.__class__._fields)
    result = []
    for i, f in enumerate(orig_fields):
        if i != pattern.program_arg:
            result.append(f)
    return result


def _unfold(
    pattern: MIPattern,
    object_program: list,
    pred_cls: PredicateMeta,
) -> list[Clause]:
    """Core unfolding: produce specialized clauses from MI pattern + object program."""
    clauses = []

    # ── Base clause ────────────────────────────────────────────────────────
    base = _make_base_clause(pattern, pred_cls)
    clauses.append(base)

    # ── One clause per object clause ───────────────────────────────────────
    if pattern.recursive_call_style == "tail":
        for obj_clause in object_program:
            clause = _unfold_tail(pattern, obj_clause, pred_cls)
            clauses.append(clause)
    elif pattern.recursive_call_style == "split":
        for obj_clause in object_program:
            clause = _unfold_split(pattern, obj_clause, pred_cls)
            clauses.append(clause)

    return clauses


def _make_base_clause(pattern: MIPattern, pred_cls: PredicateMeta) -> Clause:
    """Create the base clause for the specialized predicate.

    Original: MI([], _PROGRAM, ...extra_base_values)
    Specialized: NEW_NAME([], ...extra_base_values)
    """
    orig_base = pattern.base_clause
    orig_head = orig_base.head
    orig_fields = orig_head.__class__._fields

    # Build new head with fresh vars, but preserve the structure from the
    # base clause ([] for goal list, 0 for count, [] for tree, etc.)
    var_map = {}
    new_field_values = {}
    for i, fname in enumerate(orig_fields):
        if i == pattern.program_arg:
            continue
        val = getattr(orig_head, fname)
        new_field_values[fname] = _copy_term(val, var_map)

    new_head = pred_cls(**new_field_values)

    # Copy base clause body, substituting away any program-arg references.
    new_body = []
    for goal in orig_base.body:
        new_body.append(_copy_term(goal, var_map))

    return Clause(head=new_head, body=new_body)


def _unfold_tail(
    pattern: MIPattern,
    obj_clause: list,
    pred_cls: PredicateMeta,
) -> Clause:
    """Unfold one object clause for the tail-recursive MI pattern.

    MI recursive clause (conceptually):
        MI([GOAL, *GOALS], PROGRAM, ...extra) <- (
            ...pre_match,
            MatchClause(GOAL, BODY, PROGRAM),
            Append(BODY, GOALS, ALL_GOALS),
            ...post_match,
            MI(ALL_GOALS, PROGRAM, ...extra')
        )

    For object clause [Head_i, Body_i], the specialized clause is:
        NEW_NAME([Head_i, *GOALS], ...extra) <- (
            ...pre_match,
            ...post_match[ALL_GOALS ↦ [*Body_i, *GOALS]],
            NEW_NAME([*Body_i, *GOALS], ...extra')
        )

    For a fact (Body_i = []):
        NEW_NAME([Head_i, *GOALS], ...extra) <- (
            ...pre_match,
            ...post_match[ALL_GOALS ↦ GOALS],
            NEW_NAME(GOALS, ...extra')
        )
    """
    obj_head, obj_body = obj_clause[0], obj_clause[1]

    # Fresh variables for this object clause.
    var_map = {}
    fresh_obj_head = _copy_term(obj_head, var_map)
    fresh_obj_body = _copy_term(obj_body, var_map)

    # Create fresh variables for GOALS and extra args from the MI's recursive clause.
    mi_var_map = {}
    rc = pattern.recursive_clause
    rc_head = rc.head
    orig_fields = rc_head.__class__._fields

    # Fresh GOALS variable.
    fresh_goals = Var()
    mi_var_map[id(pattern.goals_var)] = fresh_goals

    # Fresh extra arg variables (mapped from MI recursive clause head).
    extra_field_vars = {}
    for i in pattern.extra_args:
        fname = orig_fields[i]
        orig_var = getattr(rc_head, fname)
        fresh = Var()
        mi_var_map[id(orig_var)] = fresh
        extra_field_vars[fname] = fresh

    # Build the specialized clause head.
    head_fields = {}
    goal_field = orig_fields[pattern.goal_arg]
    head_fields[goal_field] = [fresh_obj_head, StarUnpack(value=fresh_goals)]
    for fname, var in extra_field_vars.items():
        head_fields[fname] = var

    new_head = pred_cls(**head_fields)

    # Build the specialized clause body.
    new_body = []

    # Pre-match goals: copy with mi_var_map to freshen, but they reference
    # MI variables (like MAX from the head) — map those too.
    _map_mi_vars(pattern, rc, mi_var_map)

    for goal in pattern.pre_match_goals:
        new_body.append(_subst(goal, mi_var_map))

    # Post-match goals: substitute ALL_GOALS with [*Body_i, *GOALS].
    # Also need to handle the recursive call's extra args.
    if pattern.all_goals_var is not None:
        if fresh_obj_body:
            # ALL_GOALS = [*Body_i, *GOALS]
            substituted_all_goals = fresh_obj_body + [StarUnpack(value=fresh_goals)]
            mi_var_map[id(pattern.all_goals_var)] = substituted_all_goals
        else:
            # Fact: ALL_GOALS = GOALS
            mi_var_map[id(pattern.all_goals_var)] = fresh_goals

    # Recursive call: NEW_NAME([*Body_i, *GOALS] or GOALS, ...extra')
    # Find the recursive call to get the extra arg expressions.
    rc_body = rc.body
    rec_call = rc_body[pattern.recursive_call_indices[0]]

    if fresh_obj_body:
        new_goal_arg = fresh_obj_body + [StarUnpack(value=fresh_goals)]
    else:
        new_goal_arg = fresh_goals

    # Build recursive call with substituted extra args.
    rec_extra_args = _subst_recursive_call_extra_args(
        rec_call, pattern, mi_var_map, pred_cls, new_goal_arg,
    )
    new_body.append(rec_extra_args)

    # Post-match goals come after the recursive call (they may use its results).
    for goal in pattern.post_match_goals:
        new_body.append(_subst(goal, mi_var_map))

    return Clause(head=new_head, body=new_body)


def _unfold_split(
    pattern: MIPattern,
    obj_clause: list,
    pred_cls: PredicateMeta,
) -> Clause:
    """Unfold one object clause for the split (non-tail-recursive) MI pattern.

    This is for SolveTree-style MIs with two recursive calls:
        MI([GOAL, *GOALS], PROGRAM, [[GOAL, BODY_TREE], *GOALS_TREE]) <- (
            MatchClause(GOAL, BODY, PROGRAM),
            MI(BODY, PROGRAM, BODY_TREE),
            MI(GOALS, PROGRAM, GOALS_TREE)
        )

    For object clause [Head_i, Body_i], the specialized clause is:
        NEW_NAME([Head_i, *GOALS], [[Head_i, BODY_TREE], *GOALS_TREE]) <- (
            NEW_NAME(Body_i, BODY_TREE),
            NEW_NAME(GOALS, GOALS_TREE)
        )
    """
    obj_head, obj_body = obj_clause[0], obj_clause[1]

    var_map = {}
    fresh_obj_head = _copy_term(obj_head, var_map)
    fresh_obj_body = _copy_term(obj_body, var_map)

    mi_var_map = {}
    rc = pattern.recursive_clause
    rc_head = rc.head
    orig_fields = rc_head.__class__._fields

    # Fresh GOALS variable.
    fresh_goals = Var()
    mi_var_map[id(pattern.goals_var)] = fresh_goals

    # Map GOAL var → fresh_obj_head (for use in TREE field).
    mi_var_map[id(pattern.goal_var)] = fresh_obj_head

    # Map BODY var → fresh_obj_body.
    mi_var_map[id(pattern.body_var)] = fresh_obj_body

    # Map ALL remaining MI vars (body-internal like BODY_TREE, GOALS_TREE)
    # BEFORE substituting into the TREE field or recursive calls.
    _map_mi_vars(pattern, rc, mi_var_map)

    # Fresh extra arg variables — substitute with fully populated mi_var_map.
    extra_field_vars = {}
    for i in pattern.extra_args:
        fname = orig_fields[i]
        orig_val = getattr(rc_head, fname)
        # For split style, the extra arg (TREE) has structure that references
        # GOAL and other MI vars.  Substitute those.
        extra_field_vars[fname] = _subst(orig_val, mi_var_map)

    # Build head.
    head_fields = {}
    goal_field = orig_fields[pattern.goal_arg]
    head_fields[goal_field] = [fresh_obj_head, StarUnpack(value=fresh_goals)]
    for fname, val in extra_field_vars.items():
        head_fields[fname] = val

    new_head = pred_cls(**head_fields)

    # Build body.
    new_body = []
    for goal in pattern.pre_match_goals:
        new_body.append(_subst(goal, mi_var_map))

    # Two recursive calls: one for BODY, one for GOALS.
    rc_body = rc.body
    for idx in pattern.recursive_call_indices:
        rec_call = rc_body[idx]
        # Determine what goal arg this recursive call uses.
        orig_goal_arg_val = rec_call.args[pattern.goal_arg]

        # Is this the BODY call or the GOALS call?
        if _same_var(orig_goal_arg_val, pattern.body_var):
            new_goal_arg = fresh_obj_body
        elif _same_var(orig_goal_arg_val, pattern.goals_var):
            new_goal_arg = fresh_goals
        else:
            new_goal_arg = _subst(orig_goal_arg_val, mi_var_map)

        rec_clause = _subst_recursive_call_extra_args(
            rec_call, pattern, mi_var_map, pred_cls, new_goal_arg,
        )
        new_body.append(rec_clause)

    for goal in pattern.post_match_goals:
        new_body.append(_subst(goal, mi_var_map))

    return Clause(head=new_head, body=new_body)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _find_program_arg(fields: tuple[str, ...]) -> int:
    """Auto-detect the program argument by field name."""
    for i, f in enumerate(fields):
        upper = f.upper().lstrip("_")
        if upper == "PROGRAM":
            return i
    raise CannotSpecialize(
        f"Cannot auto-detect program argument from fields {fields}; "
        f"specify program_arg explicitly"
    )


def _find_goal_arg(
    clauses: list[Clause], fields: tuple[str, ...], program_arg: int,
) -> int:
    """Identify which field is the goal list by finding the [] base case."""
    for c in clauses:
        head = c.head
        for i, fname in enumerate(fields):
            if i == program_arg:
                continue
            val = getattr(head, fname)
            # Check if this field is [] in the base clause (via Unify in body).
            if isinstance(val, list) and val == []:
                return i
            # Also check if a Unify goal in the body unifies this field with [].
            if is_var(deref(val)):
                for goal in c.body:
                    if (isinstance(goal, Unify)
                            and _same_var(goal.left, val)
                            and isinstance(goal.right, list)
                            and goal.right == []):
                        return i
    # Fallback: first non-program field.
    for i in range(len(fields)):
        if i != program_arg:
            return i
    raise CannotSpecialize("Cannot find goal-list argument")


def _is_base_clause(clause: Clause, fields: tuple[str, ...], goal_arg: int) -> bool:
    """Check if this clause is the MI base case (goal list = [])."""
    head = clause.head
    val = getattr(head, fields[goal_arg])
    if isinstance(val, list) and val == []:
        return True
    if is_var(deref(val)):
        for goal in clause.body:
            if (isinstance(goal, Unify)
                    and _same_var(goal.left, val)
                    and isinstance(goal.right, list)
                    and goal.right == []):
                return True
    return False


def _is_recursive_clause(
    clause: Clause, fields: tuple[str, ...], goal_arg: int,
) -> bool:
    """Check if this clause has a [GOAL, *GOALS] pattern in the goal-list field."""
    head = clause.head
    val = getattr(head, fields[goal_arg])
    if not isinstance(val, list):
        return False
    if len(val) < 2:
        return False
    # Check for [GOAL, *GOALS] or [GOAL, StarUnpack(GOALS)].
    last = val[-1]
    return isinstance(last, StarUnpack)


def _extract_goal_goals(goal_list: list) -> tuple[Any, Any]:
    """Extract (GOAL, GOALS) variables from [GOAL, *GOALS] pattern."""
    if not isinstance(goal_list, list) or len(goal_list) < 2:
        raise CannotSpecialize("Expected [GOAL, *GOALS] pattern in goal list")
    goal_var = goal_list[0]
    star = goal_list[-1]
    if not isinstance(star, StarUnpack):
        raise CannotSpecialize("Expected StarUnpack as last element of goal list")
    return goal_var, star.value


def _find_call(body: list, name: str) -> int | None:
    """Find the index of the first Call to the given predicate name in a body."""
    for i, goal in enumerate(body):
        if isinstance(goal, Call) and isinstance(goal.func, LoadName):
            if goal.func.name == name:
                return i
    return None


def _find_all_calls(body: list, name: str) -> list[int]:
    """Find all indices of Calls to the given predicate name in a body."""
    return [
        i for i, goal in enumerate(body)
        if isinstance(goal, Call) and isinstance(goal.func, LoadName)
        and goal.func.name == name
    ]


def _same_var(a: Any, b: Any) -> bool:
    """Check if two terms refer to the same logic variable."""
    a = deref(a)
    b = deref(b)
    return is_var(a) and is_var(b) and a is b


def _map_mi_vars(pattern: MIPattern, rc: Clause, mi_var_map: dict) -> None:
    """Map MI internal variables (from body) to fresh copies.

    This handles variables that appear only in the MI body (like MAX1
    in SolveLimit) — they need fresh copies too.
    """
    rc_head = rc.head
    orig_fields = rc_head.__class__._fields

    # Map GOAL var if not already mapped.
    if id(pattern.goal_var) not in mi_var_map:
        mi_var_map[id(pattern.goal_var)] = Var()

    # Map BODY var if not already mapped.
    if id(pattern.body_var) not in mi_var_map:
        mi_var_map[id(pattern.body_var)] = Var()

    # Map PROGRAM var (it will be dropped).
    if id(pattern.program_var) not in mi_var_map:
        mi_var_map[id(pattern.program_var)] = Var()

    # Collect all vars from the body that aren't yet mapped.
    for goal in rc.body:
        _ensure_vars_mapped(goal, mi_var_map)


def _ensure_vars_mapped(term: Any, var_map: dict) -> None:
    """Walk a term and ensure every Var has a fresh mapping."""
    term = deref(term)
    if is_var(term):
        if id(term) not in var_map:
            var_map[id(term)] = Var()
        return
    if isinstance(term, list):
        for e in term:
            _ensure_vars_mapped(e, var_map)
    elif isinstance(term, StarUnpack):
        _ensure_vars_mapped(term.value, var_map)
    elif isinstance(term, (Call,)):
        for arg in term.args:
            _ensure_vars_mapped(arg, var_map)
    elif isinstance(term, (Unify, Evaluate, Gt, Lt, GtE, LtE)):
        _ensure_vars_mapped(term.left, var_map)
        _ensure_vars_mapped(term.right, var_map)
    elif hasattr(term, 'left') and hasattr(term, 'right'):
        # BinOp subclasses (Add, Sub, etc.)
        _ensure_vars_mapped(term.left, var_map)
        _ensure_vars_mapped(term.right, var_map)
    elif is_term_instance(term):
        for fname in term_field_names(term):
            _ensure_vars_mapped(getattr(term, fname), var_map)


def _subst(term: Any, var_map: dict) -> Any:
    """Substitute variables in a term using the var_map (id → replacement).

    Unlike _copy_term, this maps specific var IDs to possibly non-var
    replacements (e.g. ALL_GOALS → [*Body_i, *GOALS]).
    """
    term = deref(term)
    if is_var(term):
        vid = id(term)
        if vid in var_map:
            return var_map[vid]
        return term
    if isinstance(term, (bool, int, float, str, bytes)) or term is None:
        return term
    if isinstance(term, list):
        return [_subst(e, var_map) for e in term]
    if isinstance(term, StarUnpack):
        inner = _subst(term.value, var_map)
        if isinstance(inner, list):
            # StarUnpack of a list → inline the elements.
            return inner
        return StarUnpack(value=inner)
    if isinstance(term, Call):
        new_args = [_subst(a, var_map) for a in term.args]
        return Call(func=term.func, args=new_args, kwargs=term.kwargs)
    if isinstance(term, Unify):
        return Unify(left=_subst(term.left, var_map),
                     right=_subst(term.right, var_map))
    if isinstance(term, Evaluate):
        return Evaluate(left=_subst(term.left, var_map),
                        right=_subst(term.right, var_map))
    if isinstance(term, (Gt, Lt, GtE, LtE)):
        return type(term)(left=_subst(term.left, var_map),
                          right=_subst(term.right, var_map))
    if hasattr(term, 'left') and hasattr(term, 'right') and hasattr(term, 'op'):
        # BinOp subclasses (Add, Sub, etc.)
        return type(term)(left=_subst(term.left, var_map),
                          right=_subst(term.right, var_map))
    if is_term_instance(term):
        new_fields = {}
        for fname in term_field_names(term):
            new_fields[fname] = _subst(getattr(term, fname), var_map)
        return type(term)(**new_fields)
    return term


def _subst_recursive_call_extra_args(
    rec_call: Call,
    pattern: MIPattern,
    mi_var_map: dict,
    pred_cls: PredicateMeta,
    new_goal_arg: Any,
) -> Call:
    """Build a substituted recursive call to the specialized predicate.

    Drops the program argument, substitutes the goal argument with
    new_goal_arg, and substitutes extra args.
    """
    orig_fields = pattern.recursive_clause.head.__class__._fields
    new_fields = pred_cls._fields

    # Build the args list for the new Call, in field order.
    new_args = []
    new_field_idx = 0
    for i, fname in enumerate(orig_fields):
        if i == pattern.program_arg:
            continue  # Drop program arg.
        if i == pattern.goal_arg:
            new_args.append(new_goal_arg)
        else:
            # Extra arg — substitute from the recursive call.
            orig_val = rec_call.args[i]
            new_args.append(_subst(orig_val, mi_var_map))
        new_field_idx += 1

    return Call(func=LoadName(name=pred_cls.__name__), args=new_args, kwargs=[])
