"""Runtime database manipulation builtins: assertz/1, asserta/1, retract/1,
abolish_table/2, abolish_all_tables/0."""

from __future__ import annotations

from typing import Any

from clausal.logic.variables import Var, Trail, deref, is_var, unify
from clausal.logic.predicate import PredicateMeta, is_term_instance
from clausal.terms import Compound
from clausal.logic.exceptions import LogicException, permission_error

from clausal.logic.builtins._registry import (
    _db_builtin, structural_unify,
)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _normalize_fact_clause(term: Any):
    """Convert a ground Compound fact to Var+Is form for output-mode queries.

    ``Compound("f", (1, 2))`` → head=Compound("f", (v0, v1)), body=[Is(v0,1), Is(v1,2)]

    This makes dynamically asserted facts queryable in output mode (with unbound
    Var arguments), matching standard Prolog semantics for assert.
    Facts asserted via the DSL already use Var+Is form via the term transformer.
    """
    from clausal.logic.database import Clause  # avoid top-level import cycle
    from clausal.terms import Unify as _Unify

    if isinstance(term, Compound):
        new_args = []
        body: list = []
        for arg in term.args:
            arg_val = deref(arg)
            if not is_var(arg_val):
                v = Var()
                new_args.append(v)
                body.append(_Unify(left=v, right=arg_val))
            else:
                new_args.append(arg_val)
        return Clause(head=Compound(term.functor, tuple(new_args)), body=body)
    # Dataclass and KWTerm facts are passed as-is; their field patterns work
    # correctly since they use Python structural matching.
    from clausal.logic.database import Clause  # already imported above
    return Clause(head=term, body=[])


def _build_clause(term_val: Any, context: str, db, module_dict) -> "Any":
    """Build a Clause from a runtime term passed to assertz/asserta.

    *context* is the calling builtin's indicator ("assertz/1" or
    "asserta/1"), used as the error context on rejection.

    Only plain terms (facts) are accepted; ground Compound facts are
    normalized to Var+Is form.

    A09-F005 (decision b): a Predicate node (a rule, ``h(X) <- b(X)``) is
    rejected with a typed ``permission_error`` — its body cannot be lowered
    by ``compile_predicate_trampoline``, and previously the clause was stored
    *before* that failure surfaced, poisoning every later query of the
    predicate. Rejecting here, before ``db.assertz``, keeps the existing
    clauses queryable. See docs/database_ops.md (A09-F026).
    """
    from clausal.terms import Predicate as _Predicate

    if isinstance(term_val, _Predicate):
        raise LogicException(
            permission_error("assert", "rule", term_val.head, context))
    term_val = _check_cell_head_permission(term_val, context, db, module_dict)
    return _normalize_fact_clause(term_val)


def _check_cell_head_permission(term_val: Any, context: str, db,
                                module_dict: "dict | None") -> Any:
    """Decide whether a CELL may be asserted/retracted, and return the term to
    use as the clause head/pattern.  Non-cells are returned unchanged.

    P3-2 Task 2 (THE FLIP) put a blanket ``permission_error`` here, because a
    functor declared with fields but given no clauses is DATA (R6), so ``f(7)``
    written anywhere in that module is the cell ``("f", 7)`` -- including the
    argument handed to ``assertz/1`` -- and nothing downstream understood a
    cell as a clause head.  P3-3 Task 5 (R11) is where the cell becomes a
    legitimate assert argument, so the blanket refusal becomes a THREE-WAY
    decision on the target row:

    ====================  ==================================================
    row.dynamic           proceed -- the cell is normalized (below) and the
                          write goes through the ordinary gate
    static: a row that    ``permission_error(modify, static_procedure, f/N)``
    is not dynamic, OR    -- the P3-2 refusal, kept verbatim in substance for
    a name DECLARED with  the case it describes (the data functor), widened
    N fields in this      only in wording for a static procedure that does
    module                have clauses
    neither               ``existence_error(procedure, f/N)``
    ====================  ==================================================

    A declared-with-fields functor has no Database ROW at all until something
    gives it clauses -- being data is precisely having none -- so the row
    lookup alone would call the P3-2 case unknown and hand back an
    existence_error where the whole point of that refusal is to say "this name
    is data; declare it -dynamic".  ``functor_signature_for`` is the funnel
    that answers "is this name declared here, and with how many fields", and
    it is what keeps the two refusals on the right side of the line.

    The genuinely-unknown case is an error rather than assertz's usual "create
    the predicate" because a cell is INDISTINGUISHABLE from a str-headed data
    tuple -- THE DISCIPLINE, in ``clausal/logic/cells.py``'s module docstring:
    every str-first runtime tuple IS a cell, ``("hello", 1)`` included.  So
    ``assertz(T)`` on a T that happens to be one would otherwise silently mint
    a predicate the program never declared.  Requiring an existing declaration
    is what keeps a plain data tuple from creating state.

    NORMALIZATION.  A cell is a SPELLING of a term, so it must produce the
    same clause the same term spelled any other way produces.  When the target
    is a class predicate (the ``-dynamic`` case, overwhelmingly), the head is
    that class's instance -- so the clause list stays homogeneous, first-arg
    indexing sees the shape it sees for every other clause, and a later
    ``retract`` by cell pattern can unify with a clause loaded from source.
    With no class (a Compound-headed predicate, a bare ``Database()``) it is a
    ``Compound``, which is exactly what ``assertz(Compound(...))`` builds
    today.  Either way ``_normalize_fact_clause`` does the rest, and the ARG
    OBJECTS are shared with the caller's cell, so bindings made against the
    normalized term reach the caller's variables.
    """
    from clausal.logic.cells import compound_cell_shape  # noqa: PLC0415
    from clausal.logic.exceptions import existence_error  # noqa: PLC0415

    ok, functor = compound_cell_shape(term_val)
    if not ok:
        return term_val
    arity = len(term_val) - 1
    args = tuple(term_val[1:])
    pred_cls = _find_pred_cls(functor, arity, module_dict, None)
    if pred_cls is not None:
        # The CANONICAL name is the class's, not the spelling the cell used:
        # an ``-import_from`` alias binds the exporter's class under the local
        # name, and the row lives under the exporter's (see ``_find_pred_cls``).
        functor = pred_cls.__name__
    home = _home_db(db, pred_cls)
    row = home.row(functor, arity) if home is not None else None
    if row is not None and row.dynamic:
        if pred_cls is not None:
            return pred_cls(*args)
        return Compound(functor, args)
    if row is None and not _declared_with_fields(module_dict, functor, arity):
        raise LogicException(existence_error(
            "procedure", Compound("/", (functor, arity)),
            f"{context}: no predicate {functor}/{arity} is known here, and a "
            f"cell argument does not create one — a cell is indistinguishable "
            f"from a plain data tuple, so the target must already be declared "
            f"-dynamic({functor}/{arity})",
        ))
    raise LogicException(permission_error(
        "modify", "static_procedure",
        Compound("/", (functor, arity)),
        f"{context}: {functor}/{arity} "
        + ("is a static procedure" if row is not None and row.clauses else
           "is a data functor (declared with fields and given no clauses), "
           "so its terms compile to cells and it has no clause list")
        + f" — declare it -dynamic({functor}/{arity}) to modify it at runtime",
    ))


def _declared_with_fields(module_dict: "dict | None", functor: str,
                          arity: int) -> bool:
    """True if *functor* is declared in this module with exactly *arity*
    fields -- i.e. it is a DATA functor here, not an unknown name.

    Reads the module's ``__clausal_functor_signatures__`` registry through
    ``functor_signature_for``, the funnel the compiler's own cell placers use,
    so ``-import_from``'d spellings answer too.
    """
    if module_dict is None:
        return False
    from clausal.logic.compiler.terms_to_ast import (  # noqa: PLC0415
        functor_signature_for,
    )
    fields = functor_signature_for(functor, module_dict)
    return fields is not None and len(fields) == arity


def _find_pred_cls(functor: str, arity: int,
                   module_dict: "dict | None", head: "Any" = None) -> "Any":
    """Return the PredicateMeta class the goal named, or None.

    ARITY-CHECKED (P3-3 Task 3, identity todo instance 3): ``module_dict``
    holds one class per NAME, so a ``p/1`` assert used to hand ``p/3``'s class
    to the lock check and to the recompile — and ``compiler._install`` would
    then re-bind that class onto ``p/1``'s row, moving a predicate the assert
    never mentioned.  A name that is bound at another arity resolves to no
    class here; the gate still sees the write, because it is asked about the
    ROW.

    IDENTITY-RESOLVED (P3-3 Task 3 fix round 2, the same todo instance): the
    canonical *functor* is the CLASS's name, which is not always the spelling
    the goal used.  ``-import_from(m, [alias(bo_p, AliasS)])`` binds the
    exporter's class under ``AliasS`` only, so ``module_dict[functor]`` finds
    either nothing or — when the importer also declares ``-dynamic(bo_p/1)``
    — a local shadow class that is not the predicate the goal named.  The
    goal's own term settles it: ``AliasS(5)`` is an INSTANCE of the exporter's
    class, so *head*'s type is the predicate, whatever it is spelled here.
    Accepted only when that class is reachable from this module dict under
    some spelling, so a term that merely passed through this module cannot
    redirect the write to a predicate the module cannot see.
    """
    from clausal.logic.predicate import PredicateMeta  # noqa: PLC0415
    if module_dict is None:
        return None
    candidate = module_dict.get(functor)
    named = (candidate if isinstance(candidate, PredicateMeta)
             and len(candidate._fields) == arity else None)
    own = type(head)
    if (
        named is not own
        and isinstance(own, PredicateMeta)
        and own.__name__ == functor
        and len(own._fields) == arity
        and any(v is own for v in module_dict.values())
    ):
        return own
    return named


def _home_db(db, pred_cls) -> "Any":
    """The Database whose row a write through *pred_cls* must land in.

    A predicate reached through an ``-import_from`` is ONE predicate: the
    class is shared deliberately, and it reads the OWNER's row.  A runtime
    assert made through it therefore belongs in that row -- write it into the
    asserting module's own database instead and the two modules end up with
    two clause lists behind one class, which is the shape that made an
    importer's ``assertz`` change the owner's answers while the owner's row
    still held its own clauses (P3-3 Task 3 fix round 1).

    Falls back to *db* when there is no class, or when the class is still on
    its private detached row -- that row is nobody's predicate, and writing
    there would hide the clause from the module database entirely.
    """
    row = getattr(pred_cls, "_row", None) if pred_cls is not None else None
    if row is None or row.detached:
        return db
    return row.db


def _home_globals(db, module_dict: "dict | None", home) -> "dict | None":
    """The module globals to recompile *home*'s clause list against.

    The clause list belongs to the home database, so the namespace its clause
    BODIES resolve in has to be the home database's too (P3-3 Task 3 fix
    round 2).  Handing the recompile the ASSERTING module's globals instead
    re-lowers the owner's whole predicate against a namespace it was never
    written in and installs the result on the owner's row: a rule body calling
    a helper the importer happens to redefine starts answering from the
    importer's helper, and the owner's own answers change without anything
    having been written to them.

    Only the cross-database case differs; when the write lands in *db* itself
    this is the caller's ``module_dict``, unchanged.  A home database with no
    module dict of its own (a bare ``Database()``) keeps the caller's, which
    is the only namespace on offer.
    """
    if home is db:
        return module_dict
    home_dict = getattr(home, "module_dict", None)
    return home_dict if isinstance(home_dict, dict) else module_dict


# ── assertz / retract ──────────────────────────────────────────────────────────


@_db_builtin("assertz", 1, fields=("term",))
def _assertz_factory(db):
    """assertz(Term) — add Term as a fact at end of its predicate's clause list.

    Ground facts are automatically normalized to Var+Is form so they are
    queryable in output mode (matching standard Prolog assert semantics).
    when a module dict is available on the database, also syncs to the
    PredicateMeta class and recompiles with module globals for cross-predicate
    resolution.
    """
    from clausal.logic.database import head_key
    from clausal.logic.compiler import compile_predicate_trampoline
    module_dict = getattr(db, "module_dict", None)

    def assertz__1(term, trail, k):
        term_val = deref(term)
        if is_var(term_val):
            return
        clause = _build_clause(term_val, "assertz/1", db, module_dict)
        functor, arity = head_key(clause.head)
        pred_cls = _find_pred_cls(functor, arity, module_dict, term_val)
        # THROUGH THE GATE (P3-3 Task 3).  The lock check that used to stand
        # here is the gate's policy now — one question, "may this author write
        # this row", asked identically by all four channels — and it still
        # raises a typed permission_error rather than a RuntimeError, which
        # the drive loop would treat as generator exhaustion and swallow
        # (A09-F006 / decision A09-D002 a).  ``through=pred_cls`` is what
        # carries the check onto an -import_from'd predicate: the clause goes
        # into THIS module's row, but a shared class makes the exporter's row
        # part of the write's blast radius.
        home = _home_db(db, pred_cls)
        home_globals = _home_globals(db, module_dict, home)
        with home.mutate(functor, arity, author=db.runtime_author(),
                         kind="assert", detail="assertz/1", through=pred_cls):
            home.assertz(clause)
            clauses = home.clauses_for(functor, arity)
            compile_predicate_trampoline(functor, arity, clauses, home,
                                         globals_=home_globals,
                                         pred_cls=pred_cls)
        yield None

    return assertz__1


@_db_builtin("asserta", 1, fields=("term",))
def _asserta_factory(db):
    """asserta(Term) — add Term as a fact at front of its predicate's clause list.

    when a module dict is available on the database, also syncs to the
    PredicateMeta class and recompiles with module globals.
    """
    from clausal.logic.database import head_key
    from clausal.logic.compiler import compile_predicate_trampoline
    module_dict = getattr(db, "module_dict", None)

    def asserta__1(term, trail, k):
        term_val = deref(term)
        if is_var(term_val):
            return
        clause = _build_clause(term_val, "asserta/1", db, module_dict)
        functor, arity = head_key(clause.head)
        pred_cls = _find_pred_cls(functor, arity, module_dict, term_val)
        # Through the gate; see assertz/1 above.
        home = _home_db(db, pred_cls)
        home_globals = _home_globals(db, module_dict, home)
        with home.mutate(functor, arity, author=db.runtime_author(),
                         kind="assert", detail="asserta/1", through=pred_cls):
            home.asserta(clause)
            clauses = home.clauses_for(functor, arity)
            compile_predicate_trampoline(functor, arity, clauses, home,
                                         globals_=home_globals,
                                         pred_cls=pred_cls)
        yield None

    return asserta__1


@_db_builtin("retract", 1, fields=("term",))
def _retract_factory(db):
    """retract(Term) — remove the first clause whose head unifies with Term.

    Uses unification (not structural equality) so it correctly handles
    normalized facts whose heads contain Var placeholders.  Bindings
    from the head unification are undone after the clause is removed
    (retract is not backtrackable in this implementation).
    when a module dict is available on the database, also syncs to the
    PredicateMeta class.
    """
    from clausal.logic.database import head_key
    from clausal.logic.compiler import compile_predicate_trampoline
    module_dict = getattr(db, "module_dict", None)

    def retract__1(term, trail, k):
        term_val = deref(term)
        if is_var(term_val):
            return
        # A CELL pattern goes through the SAME gate as the assert doors (P3-3
        # Task 5, R11) and comes back normalized to the shape the clause list
        # actually holds -- without that, ``_first_match_index`` would compare
        # a tuple against a class-term head and never match, so a legal
        # ``retract(("p", 1))`` would silently fail instead of retracting.
        term_val = _check_cell_head_permission(term_val, "retract/1", db,
                                               module_dict)
        try:
            functor, arity = head_key(term_val)
        except TypeError:
            return
        pred_cls = _find_pred_cls(functor, arity, module_dict, term_val)
        home = _home_db(db, pred_cls)
        clause_list = home._clauses.get((functor, arity))
        if clause_list is None:
            return
        # SEARCH FIRST, THEN OPEN THE TRANSACTION (P3-3 Task 3 fix round 2).
        # A retract that matches nothing is not a write, and the gate's exit
        # invalidates on the KIND rather than on what the body did — so
        # opening a transaction around the search made a failed retract drop
        # the compiled dispatch, abolish the tabled answers and stamp a write
        # that never happened.  ``Database.retract`` has always pre-checked
        # for a match and opened no transaction; both retract doors agree.
        index = _first_match_index(term_val, clause_list)
        if index < 0:
            return
        # THROUGH THE GATE (P3-3 Task 3).  The lock check that used to stand
        # here is the gate's policy now, and its exit is what invalidates the
        # dispatch when the last clause goes (the recompile below is skipped
        # then, and the predicate would otherwise keep dispatching to the
        # function compiled from the clause it just lost).  The transaction
        # closes BEFORE the yield: leaving it open across a solution the
        # caller may abandon would leak an open transaction.  ``home`` is the
        # row the CLASS reads (see ``_home_db``): a predicate reached through
        # an -import_from is one predicate, so a retract through it removes
        # from the owner's clause list, the one both modules see — and the
        # recompile runs in THAT database's namespace (see ``_home_globals``).
        home_globals = _home_globals(db, module_dict, home)
        with home.mutate(functor, arity, author=db.runtime_author(),
                         kind="retract", detail="retract/1",
                         through=pred_cls):
            removed = clause_list.pop(index)
            clauses = home.clauses_for(functor, arity)
            if clauses:
                compile_predicate_trampoline(
                    functor, arity, clauses, home,
                    globals_=home_globals, pred_cls=pred_cls)
        # A09-F008 (decision A09-D003 a): bind the pattern on the REAL
        # trail so the retracted clause's argument values escape with the
        # solution (ISO/SWI "retract by pattern"). The clause is already
        # removed, so binding its template vars is safe; normal
        # backtracking undoes these bindings via the engine trail.
        from clausal.terms import Unify as _Unify  # avoid top-level cycle
        structural_unify(term_val, removed.head, trail)
        for goal in removed.body:
            if isinstance(goal, _Unify):
                structural_unify(deref(goal.left), deref(goal.right), trail)
        yield None
        return  # retract is not backtrackable

    def _first_match_index(term_val, clause_list):
        """Index of the first clause whose head unifies with *term_val* (and
        whose ``Unify`` body goals are consistent with that unification), or
        ``-1`` when none matches.

        A pure SEARCH: it removes nothing, so the caller can ask before it
        decides whether there is a write to open a transaction for (P3-3
        Task 3 fix round 2).  Leaves no bindings behind either way."""
        from clausal.terms import Unify as _Unify  # avoid top-level cycle
        for i, clause in enumerate(clause_list):
            tmp_trail = Trail()
            mark = tmp_trail.mark()
            if not structural_unify(term_val, clause.head, tmp_trail):
                tmp_trail.undo(mark)
                continue
            # Verify body: check that Unify goals are consistent with the head
            # unification.  We check only Unify goals (normalization artefacts).
            body_ok = True
            for goal in clause.body:
                if isinstance(goal, _Unify):
                    lv = deref(goal.left)
                    rv = deref(goal.right)
                    chk_trail = Trail()
                    chk_mark = chk_trail.mark()
                    if not structural_unify(lv, rv, chk_trail):
                        body_ok = False
                        chk_trail.undo(chk_mark)
                        break
                    chk_trail.undo(chk_mark)  # don't retain Is bindings
            if not body_ok:
                tmp_trail.undo(mark)  # undo head bindings before next iteration
                continue
            # Found a matching clause.
            tmp_trail.undo(mark)  # clean up temporary bindings
            return i
        return -1

    return retract__1


# ── Tabling ───────────────────────────────────────────────────────────────────


@_db_builtin("abolish_table", 2, fields=("functor", "arity"))
def _abolish_table_factory(db):
    """abolish_table(functor, Arity) — remove cached answers for a tabled predicate."""

    def abolish_table__2(functor_arg, arity_arg, trail, k):
        f = deref(functor_arg)
        a = deref(arity_arg)
        if is_var(f) or is_var(a):
            return
        if not isinstance(f, str) or not isinstance(a, int):
            return
        db.abolish_table(f, a)
        yield None

    return abolish_table__2


@_db_builtin("abolish_all_tables", 0, fields=())
def _abolish_all_tables_factory(db):
    """abolish_all_tables — remove all cached tabling answers."""

    def abolish_all_tables__0(trail, k):
        db.abolish_all_tables()
        yield None

    return abolish_all_tables__0
