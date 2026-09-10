"""clausal.logic.specialization — Meta-interpreter specialization via partial deduction.

Specializes a meta-interpreter (MI) with respect to a known object program,
producing residual clauses with MI overhead (match_clause, append, copy_term)
removed and extensions (counting, depth, proof trees) woven in.

Two entry points:

    analyze_mi(pred_cls) → MIPattern
        Inspect the clauses of a PredicateMeta MI and return a structured
        description of its pattern (base case, recursive case, style, etc.).

    specialize_mi(pattern, object_program, new_name, module_dict, db=...)
        Unfold the MI with respect to the object program and produce a new
        compiled predicate with the given name, registered as a ROW in the
        defining module's Database (P3-3 Task 7).
"""

from __future__ import annotations

import dataclasses
from typing import Any

from clausal.logic.atoms import (
    is_atom as _term_is_atom, spelling as _atom_spelling,
)
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
    pre_match_goals: list           # goals before match_clause
    post_match_goals: list          # goals after last MI-related call
    match_clause_index: int         # index of match_clause call in recursive body
    append_index: int | None        # index of append call (None for split style)
    recursive_call_indices: list[int]  # indices of recursive MI calls in body
    recursive_call_style: str       # "tail" or "split"

    # Variables from the recursive clause (populated during analysis)
    goal_var: Any = None            # GOAL variable from [GOAL, *GOALS]
    goals_var: Any = None           # GOALS variable from [GOAL, *GOALS]
    body_var: Any = None            # BODY variable from match_clause
    all_goals_var: Any = None       # ALL_GOALS variable from append (tail style)
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

    # Find match_clause call in body.
    match_idx = _find_call(body, "match_clause")
    if match_idx is None:
        raise CannotSpecialize(f"{name}: no match_clause call in recursive body")

    match_call = body[match_idx]
    # match_clause(GOAL, BODY, PROGRAM) — extract BODY variable.
    body_var = match_call.args[1]

    # Find append call (for tail-recursive style).
    append_idx = _find_call(body, "append")

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
        # Could be tail without append (unusual) — treat as tail.
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
        all_goals_var = append_call.args[2]  # append(BODY, GOALS, ALL_GOALS)

    # Classify pre-match and post-match goals.
    # Pre-match: goals before match_clause that aren't match_clause/append/recursive.
    mi_indices = {match_idx}
    if append_idx is not None:
        mi_indices.add(append_idx)
    mi_indices.update(recursive_indices)

    pre_match_goals = [body[i] for i in range(match_idx) if i not in mi_indices]
    # Post-match: goals after the last MI-related index.
    last_mi_idx = max(mi_indices)
    post_match_goals = [body[i] for i in range(last_mi_idx + 1, len(body))
                        if i not in mi_indices]

    # A03-F007: goals sitting BETWEEN match_clause and the last MI-related goal
    # (the recursive call) that are not themselves MI-related fall into neither
    # pre_match nor post_match — they would be silently dropped from every
    # specialized clause (e.g. the ``LIM > 0`` depth guard in a bounded
    # meta-interpreter). Refuse loudly (A03-D003) rather than degrade; support
    # for threading mid-body goals is future work.
    mid_dropped = [i for i in range(match_idx + 1, last_mi_idx)
                   if i not in mi_indices]
    if mid_dropped:
        raise CannotSpecialize(
            f"{name}/{arity}: goal at body position {mid_dropped[0]} "
            f"({body[mid_dropped[0]]!r}) sits between match_clause and the "
            f"recursive call but is not MI-related; specialization would "
            f"silently drop it. Mid-body goals are not yet supported — move it "
            f"before match_clause or after the recursive call, or specialize a "
            f"variant without it."
        )

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


# The author string a specialization writes under.  Third alongside
# ``Database.load_author`` (a module's own load, spelled as its source path)
# and ``Database.runtime_author`` (``runtime-assert:<module>``): a
# specialization is neither.  It is derived from the load author rather than
# being a bare constant so the stamp still says WHICH load's specializer wrote
# the row -- an author string is provenance, and "specialization" alone names
# no one -- and so that re-running the same module's specializer writes as the
# same author and is permitted by rule 1 of the ownership policy.
SPECIALIZE_AUTHOR_PREFIX = "specialize:"


def _specialization_author(db: "Database") -> str:
    """The author a specialization's writes to *db* are stamped with."""
    return f"{SPECIALIZE_AUTHOR_PREFIX}{db.load_author()}"


def _defining_db(db: "Database | None",
                 module_dict: dict | None) -> "Database":
    """The Database the specialized predicate is a row OF.

    P3-3 Task 7.  A specialized predicate is a predicate: it belongs in the
    database of the module that defines it, which is the module whose
    namespace it is installed into.  ``compiler_v2._run_specialization`` holds
    that database and hands it over, so a ``-specialize`` target now lands
    beside the module's own predicates instead of in a ``Database`` the
    specializer built and dropped on the floor.

    The direct Python API (``specialize_mi`` called from a test or a script
    with a pattern, a program and a name) has no module and therefore no
    defining module database.  It keeps a Database of its own -- one per
    specialization call, over the caller's ``module_dict`` when there is one --
    and that is NOT the free-floating shape this task removed: the returned
    class READS that database's row, so the predicate is registered, signed,
    stamped and dispatched out of a real row rather than out of class
    attributes, and the database is reachable from the handle the caller holds
    (``pred_cls._row.db``).  A single process-wide "specialization module"
    database would be the free-floating shape wearing a name, and is
    deliberately not what happens here.
    """
    if db is not None:
        return db
    from clausal.logic.database import Database
    return Database(module_dict=module_dict)


def _install_specialized(
    pred_cls: PredicateMeta,
    new_name: str,
    fields: list[str],
    clauses: list,
    db: "Database",
    module_dict: dict | None,
    solve_goal_name: str | None = None,
    goal_map: dict | None = None,
) -> PredicateMeta:
    """Install a specialized predicate as a ROW in *db*, through the gate.

    P3-3 Task 7, and the single copy of what the three ``specialize_mi*``
    entry points each used to spell for themselves.  Before it, all three
    minted a class with ``make_predicate``, built a throwaway
    ``Database(module_dict=module_dict)``, asserted the clauses into it and
    left the module's own database not knowing the predicate existed:
    ``db.row(new_name, arity)`` answered ``None`` while the class answered
    queries out of a store nothing else could reach.  That is also the
    database the ``-table`` refusal for a ``-specialize`` alias used to name
    (``compiler_v2._refuse_untablable_target``).

    What happens here, in one transaction -- ALL of it inside, so that a
    refused write (the gate asks on entry) leaves the caller's namespace
    untouched rather than holding an uninstalled class:

    * the alias name, and the residual-goal dispatcher when there is one, are
      bound in the compile namespace;
    * the class is BOUND to *db*'s row for ``(new_name, arity)`` -- so
      ``pred_cls._clauses`` IS ``db._clauses[key]`` from this point, and the
      mirror-the-clauses-onto-the-class dance the old block needed (a
      ``module_dict`` write so ``db.assertz`` could resolve through it, plus a
      ``pred_cls._assertz`` fallback when there was no ``module_dict``) is
      gone with the second store it existed to keep in step;
    * the clause list is written and the keyword signature registered;
    * the row's ``source`` is claimed for the specialization author when
      nobody owns it yet, which is what makes a LATER write by the same author
      (re-running the specializer over the same name and database) permitted
      by rule 1 rather than refused as a clause clobber by rule 3;
    * the dispatch is compiled and installed, nested inside this transaction,
      so the exit does not invalidate what the compile just installed.

    ``through=pred_cls`` puts the class's CURRENT row in the write's blast
    radius: a ``pred_cls`` handed in from outside may already be somebody
    else's predicate, and binding it here would hand them these clauses.  The
    gate asks about that row too, and only a bind it has cleared is
    ``authorized``.

    ``detail="-specialize"`` names the DIRECTIVE, because ``detail`` is what
    ``refusal_error`` leads the message with when it is a str -- the slot that
    holds ``assertz/1`` and ``retract/1`` for the other channels.  Spelling it
    ``"specialize"`` made the refusal read "specialize: specialize:<path> may
    not write ..." (fix round 1, F3): the channel and the author prefix are
    different facts and should not be the same word.
    """
    from clausal.logic.compiler import compile_predicate_trampoline
    from clausal.logic.database import WRITE_LOAD_CLAUSES

    arity = len(fields)
    author = _specialization_author(db)
    globals_ = module_dict if module_dict is not None else {}

    # EVERYTHING, the namespace writes included, inside the transaction (fix
    # round 1, F5).  The gate asks the ownership policy on ENTRY, so a
    # refusal fires before any of this runs: binding the alias name to the
    # class first would leave the caller's module_dict holding a predicate
    # that was never installed anywhere -- a detached class under a name the
    # module cannot write, which is the free-floating shape this task exists
    # to remove, re-created on the failure path.
    with db.mutate(new_name, arity, author=author, kind=WRITE_LOAD_CLAUSES,
                   detail="-specialize", through=pred_cls) as row:
        globals_[new_name] = pred_cls
        # Residual goal dispatcher, if the object program left goals this
        # specialization cannot unfold.  Resolved by NAME out of the compile
        # namespace, exactly as before -- and it is also the ONE route by
        # which one specialized predicate calls another, since the unfolder
        # emits no alias-to-alias code reference: the goal survives as a term
        # and ``_make_solve_goal_predicate``'s ``module_dict`` fallback takes
        # it to the callee's ``_get_dispatch()``, hence to the callee's row.
        if solve_goal_name is not None:
            globals_[solve_goal_name] = _make_solve_goal_predicate(
                solve_goal_name, goal_map, module_dict,
            )
        pred_cls._bind_row(db, new_name, arity, authorized=True)
        # ``_ensure_clauses``, not a plain read: a read mints nothing (P3-3
        # Task 2 fix round 1) and this IS the clause-install site, so the
        # write has to land where ``db.clauses_for``/``is_defined`` can see it.
        pred_cls._ensure_clauses()[:] = clauses
        db.register_signature(new_name, arity, tuple(fields))
        if row.source is None:
            row.source = (db.module_name(), author)
        compile_predicate_trampoline(
            new_name, arity, clauses, db,
            globals_=globals_, pred_cls=pred_cls,
        )

    return pred_cls


def specialize_mi(
    pattern: MIPattern,
    object_program: list,
    new_name: str,
    module_dict: dict | None = None,
    pred_cls: PredicateMeta | None = None,
    goal_map: dict | None = None,
    db: "Database | None" = None,
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
    db : Database, optional
        The DEFINING module's database — where the specialized predicate is
        registered as a row (P3-3 Task 7).  ``compiler_v2`` passes the module
        it is compiling.  Without one there is no defining module and the
        specialization keeps a database of its own; see ``_defining_db``.

    Returns
    -------
    PredicateMeta
        The specialized predicate class with clauses installed and compiled.
    """
    fields = _specialized_fields(pattern)
    if pred_cls is None:
        pred_cls = make_predicate(new_name, fields)

    # Detect whether the object program has residual goals (builtins/external).
    known_functors = _known_functors(object_program)
    has_residual = _has_residual_goals(object_program, known_functors)

    clauses = _unfold(pattern, object_program, pred_cls)

    # If residual goals exist, add a catch-all clause that dispatches
    # unknown goals through _SolveGoal.
    solve_goal_name = f"_SolveGoal_{new_name}"
    if has_residual:
        catchall = _make_residual_clause(pattern, pred_cls, solve_goal_name)
        clauses.append(catchall)

    # Install as a row in the defining module's database, through the gate.
    return _install_specialized(
        pred_cls, new_name, fields, clauses,
        _defining_db(db, module_dict), module_dict,
        solve_goal_name=solve_goal_name if has_residual else None,
        goal_map=goal_map,
    )


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
            match_clause(GOAL, BODY, PROGRAM),
            append(BODY, GOALS, ALL_GOALS),
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
            match_clause(GOAL, BODY, PROGRAM),
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
            continue  # drop program arg.
        if i == pattern.goal_arg:
            new_args.append(new_goal_arg)
        else:
            # Extra arg — substitute from the recursive call.
            orig_val = rec_call.args[i]
            new_args.append(_subst(orig_val, mi_var_map))
        new_field_idx += 1

    return Call(func=LoadName(name=pred_cls.__name__), args=new_args, kwargs=[])


# ── Phase 3: Residual goal support ────────────────────────────────────────────


def _known_functors(object_program: list) -> set[str]:
    """Extract the set of functor names that appear as heads in the object program."""
    functors = set()
    for clause in object_program:
        head = clause[0]
        if isinstance(head, list) and head:
            functors.add(head[0])
    return functors


def _has_residual_goals(object_program: list, known_functors: set[str]) -> bool:
    """Check if any body goal in the object program has a functor not in known_functors."""
    for clause in object_program:
        body = clause[1]
        for goal in body:
            if isinstance(goal, list) and goal:
                if goal[0] not in known_functors:
                    return True
    return False


def _make_residual_clause(
    pattern: MIPattern,
    pred_cls: PredicateMeta,
    solve_goal_name: str,
) -> Clause:
    """Create a catch-all clause that dispatches unrecognized goals via _SolveGoal.

    For the tail-recursive MI pattern, this produces:
        SpecPred([GOAL, *GOALS], ...extra) <- (
            ...pre_match,
            _SolveGoal(GOAL),
            SpecPred(GOALS, ...extra'),
            ...post_match
        )

    This clause is appended AFTER the per-object-clause specialized clauses,
    so known-head goals are matched first (by first-argument indexing).
    Unknown goals fall through to this catch-all.
    """
    rc = pattern.recursive_clause
    rc_head = rc.head
    orig_fields = rc_head.__class__._fields

    # Fresh variables for the catch-all.
    mi_var_map = {}
    fresh_goal = Var()
    fresh_goals = Var()
    mi_var_map[id(pattern.goal_var)] = fresh_goal
    mi_var_map[id(pattern.goals_var)] = fresh_goals

    # Fresh extra arg variables.
    extra_field_vars = {}
    for i in pattern.extra_args:
        fname = orig_fields[i]
        orig_var = getattr(rc_head, fname)
        fresh = Var()
        mi_var_map[id(orig_var)] = fresh
        extra_field_vars[fname] = fresh

    # Map remaining MI body vars.
    _map_mi_vars(pattern, rc, mi_var_map)

    # Build head: [GOAL, *GOALS] for goal-list, fresh vars for extras.
    head_fields = {}
    goal_field = orig_fields[pattern.goal_arg]
    head_fields[goal_field] = [fresh_goal, StarUnpack(value=fresh_goals)]
    for fname, var in extra_field_vars.items():
        head_fields[fname] = var
    new_head = pred_cls(**head_fields)

    # Build body.
    new_body = []

    # Pre-match goals (e.g. MAX > 0, MAX1 == MAX - 1 for SolveLimit).
    for goal in pattern.pre_match_goals:
        new_body.append(_subst(goal, mi_var_map))

    # _SolveGoal(GOAL) — dispatch the unknown goal.
    new_body.append(Call(
        func=LoadName(name=solve_goal_name),
        args=[fresh_goal],
        kwargs=[],
    ))

    # For ALL_GOALS, it's just GOALS (the goal was handled by _SolveGoal,
    # no body goals to prepend).
    if pattern.all_goals_var is not None:
        mi_var_map[id(pattern.all_goals_var)] = fresh_goals

    # Recursive call to specialized predicate with GOALS (not ALL_GOALS).
    rc_body = rc.body
    rec_call = rc_body[pattern.recursive_call_indices[0]]
    rec_extra_call = _subst_recursive_call_extra_args(
        rec_call, pattern, mi_var_map, pred_cls, fresh_goals,
    )
    new_body.append(rec_extra_call)

    # Post-match goals (e.g. COUNT == SUB_COUNT + 1 for SolveCount).
    for goal in pattern.post_match_goals:
        new_body.append(_subst(goal, mi_var_map))

    return Clause(head=new_head, body=new_body)


# ── Default goal handlers ─────────────────────────────────────────────────────
#
# Each handler is a simple-mode generator: takes (args, trail) and yields
# None for each solution.  The args list contains already-deref'd values
# from the goal's argument positions.


def _is_ground(x):
    """Check if a term is ground (not an unbound logic variable)."""
    return not is_var(x)


def _handle_gt(args, trail):
    """["gt", A, B] → A > B."""
    from clausal.logic.variables import deref, walk
    a, b = walk(deref(args[0])), walk(deref(args[1]))
    if _is_ground(a) and _is_ground(b) and a > b:
        yield None


def _handle_gte(args, trail):
    """["gte", A, B] → A >= B."""
    from clausal.logic.variables import deref, walk
    a, b = walk(deref(args[0])), walk(deref(args[1]))
    if _is_ground(a) and _is_ground(b) and a >= b:
        yield None


def _handle_lt(args, trail):
    """["lt", A, B] → A < B."""
    from clausal.logic.variables import deref, walk
    a, b = walk(deref(args[0])), walk(deref(args[1]))
    if _is_ground(a) and _is_ground(b) and a < b:
        yield None


def _handle_lte(args, trail):
    """["lte", A, B] → A <= B."""
    from clausal.logic.variables import deref, walk
    a, b = walk(deref(args[0])), walk(deref(args[1]))
    if _is_ground(a) and _is_ground(b) and a <= b:
        yield None


def _handle_eq(args, trail):
    """["eq", A, B] → unify A with B."""
    from clausal.logic.variables import deref
    a, b = deref(args[0]), deref(args[1])
    mark = trail.mark()
    if unify(a, b, trail):
        yield None
    trail.undo(mark)


def _handle_neq(args, trail):
    """["neq", A, B] → A \\= B (disequality check)."""
    from clausal.logic.variables import deref, walk
    a, b = walk(deref(args[0])), walk(deref(args[1]))
    if _is_ground(a) and _is_ground(b) and a != b:
        yield None


def _handle_add(args, trail):
    """["add", A, B, C] → C is A + B."""
    from clausal.logic.variables import deref, walk
    a, b = walk(deref(args[0])), walk(deref(args[1]))
    if not (_is_ground(a) and _is_ground(b)):
        return
    result = a + b
    mark = trail.mark()
    if unify(args[2], result, trail):
        yield None
    trail.undo(mark)


def _handle_sub(args, trail):
    """["sub", A, B, C] → C is A - B."""
    from clausal.logic.variables import deref, walk
    a, b = walk(deref(args[0])), walk(deref(args[1]))
    if not (_is_ground(a) and _is_ground(b)):
        return
    result = a - b
    mark = trail.mark()
    if unify(args[2], result, trail):
        yield None
    trail.undo(mark)


def _handle_mul(args, trail):
    """["mul", A, B, C] → C is A * B."""
    from clausal.logic.variables import deref, walk
    a, b = walk(deref(args[0])), walk(deref(args[1]))
    if not (_is_ground(a) and _is_ground(b)):
        return
    result = a * b
    mark = trail.mark()
    if unify(args[2], result, trail):
        yield None
    trail.undo(mark)


def _handle_div(args, trail):
    """["div", A, B, C] → C is A // B."""
    from clausal.logic.variables import deref, walk
    a, b = walk(deref(args[0])), walk(deref(args[1]))
    if not (_is_ground(a) and _is_ground(b)):
        return
    result = a // b
    mark = trail.mark()
    if unify(args[2], result, trail):
        yield None
    trail.undo(mark)


def _handle_mod(args, trail):
    """["mod", A, B, C] → C is A % B."""
    from clausal.logic.variables import deref, walk
    a, b = walk(deref(args[0])), walk(deref(args[1]))
    if not (_is_ground(a) and _is_ground(b)):
        return
    result = a % b
    mark = trail.mark()
    if unify(args[2], result, trail):
        yield None
    trail.undo(mark)


def _handle_true(args, trail):
    """["true"] → always succeeds."""
    yield None


_DEFAULT_GOAL_MAP = {
    "gt": _handle_gt,
    "gte": _handle_gte,
    "lt": _handle_lt,
    "lte": _handle_lte,
    "eq": _handle_eq,
    "neq": _handle_neq,
    "add": _handle_add,
    "sub": _handle_sub,
    "mul": _handle_mul,
    "div": _handle_div,
    "mod": _handle_mod,
    "true": _handle_true,
}


def _make_solve_goal_predicate(
    name: str,
    goal_map: dict | None,
    module_dict: dict | None,
):
    """Create a BuiltinPredicate adapter for the _SolveGoal dispatcher.

    The dispatcher takes a single argument (a list-form goal) and routes it
    through the goal_map handlers or module_dict predicates.
    """
    from clausal.logic.builtins._registry import BuiltinPredicate
    from clausal.logic.trampoline import DONE
    from clausal.logic.variables import deref, walk

    handlers = dict(_DEFAULT_GOAL_MAP)
    if goal_map:
        handlers.update(goal_map)

    def _solve_goal_dispatch(this_generator, _proceed, _fail, _catcher, goal, trail):
        goal = walk(deref(goal))
        if not isinstance(goal, list) or not goal:
            yield (_fail, DONE)
            return

        functor = goal[0]
        args = goal[1:]

        # THE FLIP (2026-09-06-atoms-as-cells-strings §6.4): a list-form
        # goal written in source names its predicate with an ATOM, so the
        # NAME read out of slot 0 is a cell.  The handler map and the module
        # namespace are both keyed by the SPELLING (identifier ``str``s —
        # §6.4's "compiler-side name consumers" row), so read it.
        if _term_is_atom(functor):
            functor = _atom_spelling(functor)

        handler = handlers.get(functor)
        if handler is not None:
            for _ in handler(args, trail):
                yield (_proceed, None)
            yield (_fail, DONE)
            return

        # Fallback: try module_dict for user-defined predicates.
        if module_dict:
            pred = module_dict.get(functor)
            if pred is not None and hasattr(pred, '_get_dispatch'):
                from clausal.logic.trampoline import StepGenerator
                dispatch_fn = pred._get_dispatch()
                sg = StepGenerator(dispatch_fn, this_generator, this_generator, this_generator, *args, trail)
                st = yield (sg, None)
                while st is not DONE:
                    yield (_proceed, None)
                    st = yield (sg, None)
                yield (_fail, DONE)
                return

        # Unknown goal — fail silently.
        yield (_fail, DONE)

    return BuiltinPredicate(name, 1, dispatch_fn=_solve_goal_dispatch)


# ── Phase 4: Termination control ──────────────────────────────────────────────


def embeds(s, t) -> bool:
    """Homeomorphic embedding test: does term *s* embed into term *t*?

    If ``embeds(s, t)`` is True, *t* is "at least as complex" as *s* — it
    contains *s* as a structural sub-pattern.  Used as an online termination
    criterion: if a newly generated atom embeds an ancestor in the unfolding
    tree, further unfolding risks divergence and should stop.

    Works on list-form terms (``["functor", arg1, ...]``) and plain values.
    Logic variables are treated as equal to any other variable (they embed
    each other) but never embed non-variable terms.

    The relation is defined inductively (Leuschel 1998):

    1. **Diving**: ``s`` embeds ``t`` if ``s`` embeds some sub-term of ``t``.
    2. **Coupling**: ``f(s1,...,sn)`` embeds ``f(t1,...,tn)`` if each ``si``
       embeds ``ti``.
    3. **Variable**: any variable embeds any variable.
    """
    s = deref(s)
    t = deref(t)

    # Both variables — always embed each other.
    if is_var(s) and is_var(t):
        return True

    # Variable vs non-variable — no embedding.
    if is_var(s) or is_var(t):
        return False

    # Ground atoms / constants.
    if not isinstance(s, list) and not isinstance(t, list):
        return s == t

    # s is a non-list constant, t is a list — check diving.
    if not isinstance(s, list) and isinstance(t, list):
        return any(embeds(s, sub) for sub in t[1:] if not isinstance(sub, StarUnpack))

    # s is a list, t is not — cannot embed.
    if isinstance(s, list) and not isinstance(t, list):
        return False

    # Both lists (compound terms).
    # Coupling: same functor and each arg embeds.
    if (s and t and s[0] == t[0]
            and _args_len(s) == _args_len(t)
            and all(embeds(si, ti) for si, ti in zip(_args(s), _args(t)))):
        return True

    # Diving: s embeds some sub-term of t.
    return any(embeds(s, sub) for sub in _args(t))


def _args(term: list) -> list:
    """Extract argument sub-terms from a list-form compound, skipping StarUnpack."""
    return [x for x in term[1:] if not isinstance(x, StarUnpack)]


def _args_len(term: list) -> int:
    """Count argument sub-terms excluding StarUnpack."""
    return sum(1 for x in term[1:] if not isinstance(x, StarUnpack))


class MemoTable:
    """Tracks (functor, generalized_pattern) pairs already specialized.

    when the deep unfolder encounters a goal that matches an already-
    specialized pattern, it emits a call to the existing predicate instead
    of re-unfolding.  This prevents duplicate work and, together with the
    homeomorphic embedding test, ensures termination.
    """

    def __init__(self):
        # functor → list of (pattern, pred_cls_name) pairs.
        self._entries: dict[str, list[tuple[list, str]]] = {}

    def lookup(self, goal: list) -> str | None:
        """Check if a goal matches an already-specialized pattern.

        Returns the specialized predicate name if found, None otherwise.
        """
        if not isinstance(goal, list) or not goal:
            return None
        functor = goal[0]
        entries = self._entries.get(functor, [])
        for pattern, pred_name in entries:
            if _pattern_matches(pattern, goal):
                return pred_name
        return None

    def register(self, goal: list, pred_name: str) -> None:
        """Register a goal pattern as having been specialized."""
        if not isinstance(goal, list) or not goal:
            return
        functor = goal[0]
        if functor not in self._entries:
            self._entries[functor] = []
        generalized = _generalize(goal)
        self._entries[functor].append((generalized, pred_name))

    @property
    def entries(self) -> dict[str, list[tuple[list, str]]]:
        """Read-only access to the memo entries for testing."""
        return dict(self._entries)


def _generalize(term):
    """Replace all Var instances with a sentinel for pattern comparison."""
    term = deref(term)
    if is_var(term):
        return "_VAR_"
    if isinstance(term, list):
        return [_generalize(x) for x in term if not isinstance(x, StarUnpack)]
    if isinstance(term, StarUnpack):
        return "_VAR_"
    return term


def _pattern_matches(pattern, goal) -> bool:
    """Check if a generalized pattern matches a goal (structurally)."""
    goal_gen = _generalize(goal)
    return pattern == goal_gen


def specialize_mi_deep(
    pattern: MIPattern,
    object_program: list,
    new_name: str,
    module_dict: dict | None = None,
    pred_cls: PredicateMeta | None = None,
    goal_map: dict | None = None,
    max_depth: int = 10,
    db: "Database | None" = None,
) -> PredicateMeta:
    """Specialize an MI with depth-bounded unfolding.

    Like ``specialize_mi()`` but recursively unfolds body goals that match
    object-program heads, up to *max_depth* levels.  Uses homeomorphic
    embedding and a memoization table for termination.

    Parameters
    ----------
    pattern : MIPattern
        The analyzed MI structure from ``analyze_mi()``.
    object_program : list
        The object program as ``[head, body_goals]`` pairs.
    new_name : str
        Name for the top-level specialized predicate.
    module_dict : dict, optional
        Module dictionary for predicate resolution.
    pred_cls : PredicateMeta, optional
        Pre-existing predicate class to reuse.
    goal_map : dict, optional
        Custom goal handlers for residual dispatch.
    max_depth : int
        Maximum unfolding depth (default 10).
    db : Database, optional
        The DEFINING module's database (P3-3 Task 7); see ``specialize_mi``.

    Returns
    -------
    PredicateMeta
        The specialized predicate class.
    """
    fields = _specialized_fields(pattern)
    if pred_cls is None:
        pred_cls = make_predicate(new_name, fields)

    known_functors = _known_functors(object_program)
    has_residual = _has_residual_goals(object_program, known_functors)

    memo = MemoTable()
    memo.register(["_top_"], new_name)

    # Build an index: functor → list of object clauses.
    obj_index = _build_object_index(object_program)

    # Perform depth-bounded unfolding.
    clauses = _unfold_deep(
        pattern, object_program, pred_cls,
        obj_index, known_functors, memo,
        ancestors=[], depth=0, max_depth=max_depth,
    )

    # Residual clause if needed.
    solve_goal_name = f"_SolveGoal_{new_name}"
    if has_residual:
        catchall = _make_residual_clause(pattern, pred_cls, solve_goal_name)
        clauses.append(catchall)

    # Install as a row in the defining module's database, through the gate.
    return _install_specialized(
        pred_cls, new_name, fields, clauses,
        _defining_db(db, module_dict), module_dict,
        solve_goal_name=solve_goal_name if has_residual else None,
        goal_map=goal_map,
    )


def _build_object_index(object_program: list) -> dict[str, list]:
    """Build an index from functor name to object clauses."""
    index: dict[str, list] = {}
    for clause in object_program:
        head = clause[0]
        if isinstance(head, list) and head:
            functor = head[0]
            if functor not in index:
                index[functor] = []
            index[functor].append(clause)
    return index


def _unfold_deep(
    pattern: MIPattern,
    object_program: list,
    pred_cls: PredicateMeta,
    obj_index: dict[str, list],
    known_functors: set[str],
    memo: MemoTable,
    ancestors: list,
    depth: int,
    max_depth: int,
) -> list[Clause]:
    """Depth-bounded unfolding with homeomorphic embedding checks.

    At depth 0, produces the standard Phase 1 clauses.  At depth > 0,
    additionally unfolds body goals that match object-program heads,
    provided the embedding and depth checks pass.

    The *ancestors* list tracks goal atoms along the current unfolding
    path.  If a new goal embeds an ancestor, unfolding stops for that
    branch (the goal is left as a recursive call).
    """
    # Base unfolding — same as Phase 1.
    clauses = _unfold(pattern, object_program, pred_cls)

    if depth >= max_depth:
        return clauses

    # Try to deepen: for each specialized clause, check body goals.
    deepened_clauses = []
    for clause in clauses:
        deepened = _deepen_clause(
            clause, pattern, pred_cls, obj_index, known_functors,
            memo, ancestors, depth, max_depth,
        )
        deepened_clauses.append(deepened)

    return deepened_clauses


def _deepen_clause(
    clause: Clause,
    pattern: MIPattern,
    pred_cls: PredicateMeta,
    obj_index: dict[str, list],
    known_functors: set[str],
    memo: MemoTable,
    ancestors: list,
    depth: int,
    max_depth: int,
) -> Clause:
    """Attempt to deepen a single specialized clause by inlining body goals.

    For each body goal that is a recursive call to the specialized predicate
    and whose first argument is a list with a known-functor goal at the head,
    check if it can be inlined.  If the embedding test passes and depth allows,
    inline the object clause body directly.

    Goals that fail the embedding test or exceed depth are left unchanged.
    """
    if not clause.body:
        return clause

    new_body = []
    changed = False
    for goal in clause.body:
        inlined = _try_inline_goal(
            goal, pattern, pred_cls, obj_index, known_functors,
            memo, ancestors, depth, max_depth,
        )
        if inlined is not None:
            new_body.extend(inlined)
            changed = True
        else:
            new_body.append(goal)

    if changed:
        return Clause(head=clause.head, body=new_body)
    return clause


def _try_inline_goal(
    goal,
    pattern: MIPattern,
    pred_cls: PredicateMeta,
    obj_index: dict[str, list],
    known_functors: set[str],
    memo: MemoTable,
    ancestors: list,
    depth: int,
    max_depth: int,
) -> list | None:
    """Try to inline a single goal.  Returns a list of replacement goals,
    or None if the goal should be kept as-is.

    Only inlines calls to the specialized predicate where the goal-list
    argument starts with a known-functor goal whose pattern hasn't been
    seen before (or passes the embedding test).
    """
    if not isinstance(goal, Call):
        return None
    if not isinstance(goal.func, LoadName):
        return None
    if goal.func.name != pred_cls.__name__:
        return None

    # This is a recursive call to the specialized predicate.
    # Check if the goal-list arg starts with a known functor.
    spec_fields = pred_cls._fields
    goal_field_idx = None
    for i, fname in enumerate(spec_fields):
        if fname == pattern.recursive_clause.head.__class__._fields[pattern.goal_arg]:
            goal_field_idx = i
            break

    if goal_field_idx is None:
        return None

    goal_list_arg = goal.args[goal_field_idx]

    # Goal list must be a Python list with at least one element.
    if not isinstance(goal_list_arg, list) or not goal_list_arg:
        return None

    first_goal = goal_list_arg[0]
    if not isinstance(first_goal, list) or not first_goal:
        return None

    functor = first_goal[0]
    if functor not in known_functors:
        return None

    # Embedding check: does the new goal embed any ancestor?
    for ancestor in ancestors:
        if embeds(ancestor, first_goal):
            return None  # Would diverge — stop.

    # Depth check.
    if depth + 1 >= max_depth:
        return None

    # Memo check: already specialized this pattern?
    existing = memo.lookup(first_goal)
    if existing is not None:
        # Already handled by the specialized predicate dispatch — leave as-is.
        return None

    # Register this pattern.
    memo.register(first_goal, pred_cls.__name__)

    # Inline: match first_goal against object clauses for this functor.
    matching_clauses = obj_index.get(functor, [])
    if not matching_clauses:
        return None

    # For now, we only inline when there's exactly one matching object clause
    # (deterministic inlining).  Multiple matches would require disjunction
    # or multiple clause alternatives, which is complex.
    # Non-deterministic inlining is handled by Phase 5 (CPD).
    if len(matching_clauses) > 1:
        return None

    obj_clause = matching_clauses[0]
    obj_head, obj_body = obj_clause[0], obj_clause[1]

    # Create fresh copies.
    var_map = {}
    fresh_head = _copy_term(obj_head, var_map)
    fresh_body = _copy_term(obj_body, var_map)

    # A03-F008: unify the whole goal against the fresh head with _ast_unify,
    # which compares CONSTANT head args (f(2) goal vs f(1) head fails) and
    # binds goal-side vars to head constants — not just var head args. The old
    # code checked arity only and built a substitution for var head args
    # exclusively, so it inlined f(2) against f(1)'s empty body and dropped the
    # X=const constraint. Abandon inlining when unification fails.
    raw_subst = _ast_unify(first_goal, fresh_head)
    if raw_subst is None:
        return None
    # Flatten chains so _subst's single-level lookup resolves to final values.
    subst_map = {vid: _ast_apply(val, raw_subst) for vid, val in raw_subst.items()}

    # A03-F008 (goal-side bindings): _ast_unify may also bind GOAL-side vars
    # (a var in first_goal against a constant/compound in the inlined head).
    # Those vars are shared with the enclosing specialized clause's head and
    # sibling goals, but there is no channel from here back to that clause —
    # _deepen_clause re-emits ``clause.head`` verbatim, so a purely textual
    # substitution drops the constraint (gv(GV) surfaces GV unbound and
    # gv(2) wrongly succeeds).  Emit an explicit runtime Unify goal per
    # bound goal-side var instead: the Var objects ARE the clause-head vars,
    # so head unification at call time sees the binding, and repeated /
    # aliased vars fall out of ordinary runtime unification.  Fresh vars
    # (the inlined clause's own copies) are fully handled by substitution
    # and need no Unify.
    fresh_ids = {id(v) for v in var_map.values()}
    unify_goals = []
    seen_goal_vars = set()
    for v in _ast_vars(first_goal):
        vid = id(v)
        if vid in raw_subst and vid not in fresh_ids and vid not in seen_goal_vars:
            seen_goal_vars.add(vid)
            unify_goals.append(
                Unify(left=v, right=_ast_deep_apply(v, raw_subst))
            )

    # Substitute into fresh body goals.
    inlined_goals = [_subst(body_goal, subst_map) for body_goal in fresh_body]

    # Build the remaining goal list (tail after first_goal). Goal-side vars may
    # now be bound by the head unification, so substitute into them too.
    remaining = [_subst(g, subst_map) for g in goal_list_arg[1:]]

    # Build the continuation: goal-side Unify goals + inlined body goals +
    # recursive call with remaining goals.  The Unify goals come first so
    # every later goal already sees the bindings.
    result = unify_goals + list(inlined_goals)

    # If there are remaining goals, add a recursive call.
    if remaining:
        # Build remaining-goals list, handling StarUnpack.
        remaining_goal_list = remaining
        rec_args = [_subst(a, subst_map) for a in goal.args]
        rec_args[goal_field_idx] = remaining_goal_list
        result.append(Call(
            func=LoadName(name=pred_cls.__name__),
            args=rec_args,
            kwargs=goal.kwargs if hasattr(goal, 'kwargs') else [],
        ))

    # Recurse deeper on the inlined goals.
    new_ancestors = ancestors + [first_goal]
    final_result = []
    for g in result:
        deeper = _try_inline_goal(
            g, pattern, pred_cls, obj_index, known_functors,
            memo, new_ancestors, depth + 1, max_depth,
        )
        if deeper is not None:
            final_result.extend(deeper)
        else:
            final_result.append(g)

    return final_result


# ── Phase 5: Conjunctive partial deduction (deforestation) ─────────────────────


def specialize_mi_cpd(
    pattern: MIPattern,
    object_program: list,
    new_name: str,
    module_dict: dict | None = None,
    pred_cls: PredicateMeta | None = None,
    goal_map: dict | None = None,
    max_depth: int = 10,
    db: "Database | None" = None,
) -> PredicateMeta:
    """Specialize an MI with conjunctive partial deduction (deforestation).

    Extends Phase 1 unfolding by deforesting intermediate goal-list
    constructions.  when a specialized clause's body contains a recursive
    call with a constructed goal-list ``[g1, g2, ..., *GOALS]``, the first
    goal ``g1`` is unfolded against ALL matching object clauses (not just
    deterministic ones as in Phase 4), producing one output clause per
    match.  This eliminates intermediate list allocations.

    Parameters
    ----------
    pattern : MIPattern
        The analyzed MI structure from ``analyze_mi()``.
    object_program : list
        The object program as ``[head, body_goals]`` pairs.
    new_name : str
        Name for the specialized predicate.
    module_dict : dict, optional
        Module dictionary for predicate resolution.
    pred_cls : PredicateMeta, optional
        Pre-existing predicate class to reuse.
    goal_map : dict, optional
        Custom goal handlers for residual dispatch.
    max_depth : int
        Maximum deforestation depth (default 10).
    db : Database, optional
        The DEFINING module's database (P3-3 Task 7); see ``specialize_mi``.

    Returns
    -------
    PredicateMeta
        The specialized predicate class.
    """
    fields = _specialized_fields(pattern)
    if pred_cls is None:
        pred_cls = make_predicate(new_name, fields)

    known_functors = _known_functors(object_program)
    has_residual = _has_residual_goals(object_program, known_functors)
    obj_index = _build_object_index(object_program)

    # Phase 1: shallow unfold.
    clauses = _unfold(pattern, object_program, pred_cls)

    # Phase 5: deforestation pass.
    conj_memo = ConjunctionMemoTable()
    deforested = _deforest_pass(
        clauses, pattern, pred_cls, obj_index, known_functors,
        conj_memo, max_depth,
    )

    # Residual clause if needed.
    solve_goal_name = f"_SolveGoal_{new_name}"
    if has_residual:
        catchall = _make_residual_clause(pattern, pred_cls, solve_goal_name)
        deforested.append(catchall)

    # Install as a row in the defining module's database, through the gate.
    return _install_specialized(
        pred_cls, new_name, fields, deforested,
        _defining_db(db, module_dict), module_dict,
        solve_goal_name=solve_goal_name if has_residual else None,
        goal_map=goal_map,
    )


class ConjunctionMemoTable:
    """Tracks conjunction patterns that have been deforested.

    Prevents infinite deforestation by recognizing when a conjunction
    pattern has already been processed.  Keys are tuples of generalized
    goal functors.
    """

    def __init__(self):
        self._seen: set[tuple] = set()

    def has_seen(self, goals: list) -> bool:
        """Check if this conjunction pattern has been processed."""
        key = self._key(goals)
        return key in self._seen

    def register(self, goals: list) -> None:
        """Mark a conjunction pattern as processed."""
        key = self._key(goals)
        self._seen.add(key)

    @staticmethod
    def _key(goals: list) -> tuple:
        """Generalize a goal list to a tuple of functor names."""
        result = []
        for g in goals:
            if isinstance(g, list) and g:
                result.append(g[0])
            elif isinstance(g, StarUnpack):
                result.append("*")
            else:
                result.append("?")
        return tuple(result)

    @property
    def entries(self) -> set[tuple]:
        return set(self._seen)


def _deforest_pass(
    clauses: list[Clause],
    pattern: MIPattern,
    pred_cls: PredicateMeta,
    obj_index: dict[str, list],
    known_functors: set[str],
    conj_memo: ConjunctionMemoTable,
    max_depth: int,
) -> list[Clause]:
    """Apply deforestation to a list of Phase 1 clauses.

    Each clause may be expanded into multiple clauses when the body
    contains a recursive call with a constructed goal-list whose first
    goal matches multiple object clauses.
    """
    result = []
    for clause in clauses:
        deforested = _deforest_clause(
            clause, pattern, pred_cls, obj_index, known_functors,
            conj_memo, ancestors=[], depth=0, max_depth=max_depth,
        )
        result.extend(deforested)
    return result


def _deforest_clause(
    clause: Clause,
    pattern: MIPattern,
    pred_cls: PredicateMeta,
    obj_index: dict[str, list],
    known_functors: set[str],
    conj_memo: ConjunctionMemoTable,
    ancestors: list,
    depth: int,
    max_depth: int,
) -> list[Clause]:
    """Deforest a single clause.

    Looks for body goals that are recursive calls to pred_cls with a
    constructed goal-list.  For the first such goal found, unfolds the
    first element of the goal-list against all matching object clauses,
    producing one output clause per match.

    Returns a list of clauses (possibly just [clause] if no deforestation
    is possible).
    """
    if not clause.body or depth >= max_depth:
        return [clause]

    for i, goal in enumerate(clause.body):
        if not isinstance(goal, Call):
            continue
        if not isinstance(goal.func, LoadName):
            continue
        if goal.func.name != pred_cls.__name__:
            continue

        # This is a recursive call to the specialized predicate.
        goal_list_arg = _get_goal_list_arg(goal, pattern, pred_cls)
        if goal_list_arg is None:
            continue
        if not isinstance(goal_list_arg, list) or not goal_list_arg:
            continue

        # Find the first concrete goal in the goal list.
        first_goal = goal_list_arg[0]
        if not isinstance(first_goal, list) or not first_goal:
            continue

        functor = first_goal[0]
        if functor not in known_functors:
            continue

        # Embedding check: would deforesting diverge?
        for anc in ancestors:
            if embeds(anc, first_goal):
                return [clause]

        # Conjunction memo check.
        if conj_memo.has_seen(goal_list_arg):
            return [clause]
        conj_memo.register(goal_list_arg)

        # Find matching object clauses.
        matching = obj_index.get(functor, [])
        if not matching:
            continue

        # Unfold: generate one clause per matching object clause.
        result = []
        for obj_clause in matching:
            unfolded = _unfold_body_goal(
                clause, i, goal, goal_list_arg, first_goal, obj_clause,
                pattern, pred_cls, obj_index, known_functors,
                conj_memo, ancestors + [first_goal], depth + 1, max_depth,
            )
            if unfolded is not None:
                result.extend(unfolded)

        if result:
            return result
        # If no unfolding succeeded, keep the original.
        return [clause]

    return [clause]


def _get_goal_list_arg(
    goal: Call,
    pattern: MIPattern,
    pred_cls: PredicateMeta,
) -> Any:
    """Extract the goal-list argument from a recursive call."""
    spec_fields = pred_cls._fields
    orig_fields = pattern.recursive_clause.head.__class__._fields
    goal_field_name = orig_fields[pattern.goal_arg]

    for i, fname in enumerate(spec_fields):
        if fname == goal_field_name:
            if i < len(goal.args):
                return goal.args[i]
    return None


def _unfold_body_goal(
    clause: Clause,
    goal_idx: int,
    goal: Call,
    goal_list_arg: list,
    first_goal: list,
    obj_clause: list,
    pattern: MIPattern,
    pred_cls: PredicateMeta,
    obj_index: dict[str, list],
    known_functors: set[str],
    conj_memo: ConjunctionMemoTable,
    ancestors: list,
    depth: int,
    max_depth: int,
) -> list[Clause] | None:
    """Unfold a single body goal against one object clause.

    Produces a new clause (or list of clauses if further deforestation
    is applied) where:
    - The clause head is specialized by the unification bindings
    - The body goal is replaced with the object clause's body goals
      prepended to the remaining goal-list

    Returns None if unification fails.
    """
    obj_head, obj_body = obj_clause[0], obj_clause[1]

    # Create fresh copies of the object clause.
    fresh_map = {}
    fresh_head = _copy_term(obj_head, fresh_map)
    fresh_body = _copy_term(obj_body, fresh_map)

    # AST-level unification: first_goal ↔ fresh_head.
    subst = _ast_unify(first_goal, fresh_head)
    if subst is None:
        return None

    # Apply the substitution to the original clause head.
    new_clause_head = _subst(clause.head, subst)
    # Reconstruct as a proper pred_cls instance if needed.
    if is_term_instance(new_clause_head):
        field_vals = {}
        for fname in term_field_names(new_clause_head):
            field_vals[fname] = getattr(new_clause_head, fname)
        new_clause_head = pred_cls(**field_vals)

    # Compute the remaining goal list (after the first goal).
    remaining = goal_list_arg[1:]

    # New goal list: [*fresh_body, *remaining].
    if fresh_body:
        new_goal_list = [_subst(g, subst) for g in fresh_body] + remaining
    else:
        # Fact: no body goals, remaining is just the rest.
        # If remaining is [StarUnpack(v)], the new arg is just v.
        if (len(remaining) == 1
                and isinstance(remaining[0], StarUnpack)):
            new_goal_list = _subst(remaining[0].value, subst)
        else:
            new_goal_list = remaining

    # Build new body: replace the recursive call at goal_idx.
    goal_field_idx = _get_goal_field_idx(pattern, pred_cls)

    # A03-F009: splice the inlined step's extra-arg (count/limit) goals as a
    # SINGLE telescoping link per deforestation level. The per-step goals come
    # from the CONSTANT pattern template (pattern.pre/post_match_goals) — NOT the
    # growing clause body. The previous code re-chained the accumulated body
    # goals every level, which at depth ≥2 both duplicated links (off-by-one
    # count) and reused a var as an Evaluate LHS twice (the `:=` then always
    # failed, so every deep clause failed and deep solutions were lost).
    #
    # Instead, keep the already-accumulated body goals untouched and add exactly
    # one remapped copy of the template, telescoped at the recursive-call
    # boundary: the pattern's head-role extra var maps to the current recursive
    # call's extra var R, the pattern's rec-role extra var maps to a fresh F, and
    # the new recursive call's extra arg becomes F. This grows the chain by one
    # link (F → R → … → head) with every LHS distinct and previously unbound.
    spliced_pre: list = []
    spliced_post: list = []
    rec_extra_replace: dict = {}   # id(current rec-call extra) -> fresh F
    needs_chain = bool(
        goal_field_idx is not None
        and pattern.extra_args
        and (pattern.pre_match_goals or pattern.post_match_goals)
    )

    if needs_chain:
        spec_fields = pred_cls._fields
        orig_fields = pattern.recursive_clause.head.__class__._fields
        orig_name_to_idx = {fn: i for i, fn in enumerate(orig_fields)}
        rec_call_pat = pattern.recursive_clause.body[
            pattern.recursive_call_indices[0]]

        # boundary_map remaps the pattern template into the current clause's
        # variable space: head-role -> R (current rec extra), rec-role -> fresh.
        boundary_map: dict = {}
        extra_indices = [k for k in range(len(goal.args)) if k != goal_field_idx]
        for k in extra_indices:
            e = orig_name_to_idx.get(spec_fields[k])
            if e is None or e >= len(rec_call_pat.args):
                continue
            head_role = deref(getattr(pattern.recursive_clause.head,
                                      orig_fields[e]))
            rec_role = deref(rec_call_pat.args[e])
            if not is_var(rec_role):
                continue                     # pass-through extra: no chaining
            R = deref(goal.args[k])          # current recursive-call extra arg
            F = Var()
            boundary_map[id(rec_role)] = F
            if is_var(head_role) and id(head_role) != id(rec_role):
                boundary_map[id(head_role)] = R
            if is_var(R):
                rec_extra_replace[id(R)] = F

        # Freshen any remaining template vars so successive levels never alias.
        for g in (*pattern.pre_match_goals, *pattern.post_match_goals):
            _ensure_vars_mapped(g, boundary_map)

        spliced_pre = [_subst(g, boundary_map) for g in pattern.pre_match_goals]
        spliced_post = [_subst(g, boundary_map) for g in pattern.post_match_goals]

    new_body = []
    for j, body_goal in enumerate(clause.body):
        if j < goal_idx:
            # Accumulated pre-match goals — kept as-is (telescope tail).
            new_body.append(_subst(body_goal, subst))
        elif j == goal_idx:
            # The inlined step's own pre-match goals (one copy).
            new_body.extend(spliced_pre)

            # Build the replacement recursive call with the new goal list; its
            # extra arg becomes the fresh boundary var so the chain telescopes.
            new_args = list(goal.args)
            if goal_field_idx is not None:
                new_args[goal_field_idx] = _subst(new_goal_list, subst)
            final_args = []
            for k, a in enumerate(new_args):
                if k == goal_field_idx:
                    final_args.append(new_args[k])
                else:
                    final_args.append(_subst(_subst(a, subst), rec_extra_replace))
            new_call = Call(
                func=goal.func,
                args=final_args,
                kwargs=goal.kwargs if hasattr(goal, 'kwargs') else [],
            )
            new_body.append(new_call)

            # The inlined step's own post-match goals (one copy).
            new_body.extend(spliced_post)
        else:
            # Accumulated post-match goals — kept as-is (telescope tail).
            new_body.append(_subst(body_goal, subst))

    new_clause = Clause(head=new_clause_head, body=new_body)

    # Recursively try to deforest further.
    return _deforest_clause(
        new_clause, pattern, pred_cls, obj_index, known_functors,
        conj_memo, ancestors, depth, max_depth,
    )


def _get_goal_field_idx(pattern: MIPattern, pred_cls: PredicateMeta) -> int | None:
    """Get the index of the goal-list field in the specialized predicate."""
    orig_fields = pattern.recursive_clause.head.__class__._fields
    goal_field_name = orig_fields[pattern.goal_arg]
    for i, fname in enumerate(pred_cls._fields):
        if fname == goal_field_name:
            return i
    return None


def _ast_unify(t1, t2) -> dict | None:
    """Attempt AST-level unification of two terms.

    Works on list-form terms (``["functor", arg1, ...]``), ground values,
    and ``Var`` instances.  Returns a substitution dict (``id(Var) → value``)
    or None if unification fails.

    Unlike runtime unification, this operates purely on AST structures
    without side effects (no trail, no mutation).
    """
    subst: dict = {}
    if _ast_unify_impl(t1, t2, subst):
        return subst
    return None


def _ast_unify_impl(t1, t2, subst: dict) -> bool:
    """Recursive implementation of AST-level unification."""
    t1 = _ast_apply(t1, subst)
    t2 = _ast_apply(t2, subst)

    # Both are the same variable.
    if is_var(t1) and is_var(t2) and t1 is t2:
        return True

    # One is a variable — bind it.
    if is_var(t1):
        subst[id(t1)] = t2
        return True
    if is_var(t2):
        subst[id(t2)] = t1
        return True

    # Both are lists (compound terms).
    if isinstance(t1, list) and isinstance(t2, list):
        if len(t1) != len(t2):
            return False
        return all(_ast_unify_impl(a, b, subst) for a, b in zip(t1, t2))

    # Ground atoms / constants.
    return t1 == t2


def _ast_apply(t, subst: dict):
    """Apply a substitution to a term, following chains."""
    if is_var(t) and id(t) in subst:
        return _ast_apply(subst[id(t)], subst)
    return t


def _ast_deep_apply(t, subst: dict):
    """Apply a substitution recursively, descending into list-form terms."""
    t = _ast_apply(t, subst)
    if isinstance(t, list):
        return [_ast_deep_apply(e, subst) for e in t]
    return t


def _ast_vars(t) -> list:
    """All ``Var`` instances in a list-form term, depth-first (with repeats)."""
    if is_var(t):
        return [t]
    if isinstance(t, list):
        out = []
        for e in t:
            out.extend(_ast_vars(e))
        return out
    return []
