"""Runtime database manipulation builtins: assertz/1, asserta/1, retract/1,
abolish_table/2, abolish_all_tables/0."""

from __future__ import annotations

from typing import Any

from clausal.logic.variables import Var, Trail, deref, is_var, unify
from clausal.logic.atoms import is_atom as _term_is_atom, spelling as _spelling
from clausal.logic.exceptions import (
    LogicException, instantiation_error, permission_error,
)
from clausal.logic.exceptions import _error as _error_term
from clausal.logic.atoms import mint

from clausal.logic.builtins._registry import (
    _db_builtin, structural_unify,
)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _hoist_every_argument(args, build_head):
    """The Var+Unify lowering of a fact: each bound argument of *args* becomes
    a fresh ``Var`` in the head plus a prepended ``Unify`` body goal, and
    *build_head* makes the head from the new argument tuple."""
    from clausal.logic.database import Clause  # avoid top-level import cycle
    from clausal.terms import Unify as _Unify

    new_args = []
    body: list = []
    for arg in args:
        arg_val = deref(arg)
        if not is_var(arg_val):
            v = Var()
            new_args.append(v)
            body.append(_Unify(left=v, right=arg_val))
        else:
            new_args.append(arg_val)
    return Clause(head=build_head(tuple(new_args)), body=body,
                  hoisted=len(body))


def _normalize_fact_clause(term: Any, hoist_all: bool = False):
    """Lower an asserted fact so it answers output-mode queries.

    With *hoist_all*, ``("f", 1, 2)`` → head=("f", v0, v1),
    body=[Unify(v0, 1), Unify(v1, 2)]; without it only STRUCTURED arguments
    are hoisted (below).

    This makes dynamically asserted facts queryable in output mode (with unbound
    Var arguments), matching standard Prolog semantics for assert.
    Facts asserted via the DSL already use Var+Is form via the term transformer.

    The head is the CELL.  *hoist_all* gives it the every-argument lowering
    -- the cell a no-class dynamic predicate receives (``_resolve_cell_head``).
    """
    from clausal.logic.database import Clause  # avoid top-level import cycle

    # A CELL head (the P2 head shape) gets the lowering the compiler gives a
    # source clause (``database._normalize_structural_head_args``): each
    # STRUCTURED argument -- a cell, a list holding one -- is
    # replaced by a fresh Var and a prepended ``Unify`` body goal.  Before
    # 2026-09-26 an asserted cell head kept ``dz(f(1))`` as the head itself,
    # compiled to ``case ['f', x]``, which an unbound caller never matches:
    # ``dz(X)`` did not answer ``f(1)``.  Atomic arguments keep the head's
    # capture-and-unify guard, which already binds an unbound caller.
    # ``hoisted`` lets clause/2 put the lowered arguments back.
    from clausal.logic.cells import compound_cell_shape, make_cell  # noqa: PLC0415
    if hoist_all and compound_cell_shape(term)[0]:
        return _hoist_every_argument(
            term[1:], lambda new: make_cell(term[0], *new))
    if compound_cell_shape(term)[0]:
        from clausal.logic.database import _normalize_structural_head_args  # noqa: PLC0415
        head, body = _normalize_structural_head_args(term, [])
        return Clause(head=head, body=body, hoisted=len(body))
    # Dataclass facts are passed as-is; their field patterns work
    # correctly since they use Python structural matching.
    return Clause(head=term, body=[])


def _build_clause(term_val: Any, context: str, db, module_dict) -> "Any":
    """Build a Clause from a runtime term passed to assertz/asserta.

    *context* is the calling builtin's indicator ("assertz/1" or
    "asserta/1"), used as the error context on rejection.

    Only plain terms (facts) are accepted; a cell fact is normalized by
    ``_normalize_fact_clause``.

    A09-F005 (decision b): a Predicate node (a rule, ``h(X) <- b(X)``) is
    rejected with a typed ``permission_error`` — its body cannot be lowered
    by ``compile_predicate_trampoline``, and previously the clause was stored
    *before* that failure surfaced, poisoning every later query of the
    predicate. Rejecting here, before ``db.assertz``, keeps the existing
    clauses queryable. See docs/database_ops.md (A09-F026).

    A CELL argument is FROZEN here (P3-3 Task 5 fix round 1, F1) -- see
    ``_freeze_asserted_head_args``.  Only on this path: ``retract`` calls the
    gate directly and must keep SHARING the caller's variables, since binding
    them is how a retracted clause's values escape with the solution.
    """
    from clausal.terms import Predicate as _Predicate
    from clausal.logic.cells import compound_cell_shape  # noqa: PLC0415

    if isinstance(term_val, _Predicate):
        raise LogicException(
            permission_error("assert", "rule", term_val.head, context))
    was_cell, _cell_functor = compound_cell_shape(term_val)
    term_val, hoist_all = _resolve_cell_head(term_val, context, db,
                                             module_dict)
    if was_cell:
        term_val = _freeze_asserted_head_args(term_val)
    return _normalize_fact_clause(term_val, hoist_all=hoist_all)


def _freeze_asserted_head_args(head: Any) -> Any:
    """Rebuild *head* with each argument DEREFERENCED, so the stored clause
    holds the value a variable had at assert time rather than the variable.

    P3-3 Task 5 fix round 1 (F1).  The gate normalizes a cell by handing its
    slots straight to the class constructor, and
    ``_normalize_fact_clause`` passes a class term through untouched -- so the
    stored head held the CALLER'S LIVE ``Var``.  The collect-by-assert idiom
    then stored one clause per solution, all of them the same variable::

        for _ in solve(("src", X), m):     # src(1), src(2)
            assertz(("seen", X))
        # seen(X) answered [2, 2], not [1, 2]

    The every-argument lowering never had that shape because
    ``_normalize_fact_clause`` derefs each argument and rebuilds a bound one as
    a fresh ``Var`` plus a ``Unify`` body goal.  This is that same freeze, one
    step earlier, so the class-term head gets it too: a SHALLOW ``deref``,
    deliberately matching what that machinery does rather than a deep walk.

    An UNBOUND argument still comes through as the caller's ``Var`` -- again
    matching the every-argument lowering, which keeps an unbound argument live.  That
    residual, and the identical defect in the class-term spelling
    ``assertz(m.seen(X))`` (ruled out of scope for this round), are recorded in
    ``todo/assert-stores-live-vars-for-class-term-and-cell-spellings-2026-09-06.md``;
    ISO ``assert/1`` copies its argument outright, which is the eventual fix.
    """
    from clausal.logic.cells import compound_cell_shape, make_cell  # noqa: PLC0415
    is_cell, functor = compound_cell_shape(head)
    if is_cell:                                     # P2: a head is a cell
        return make_cell(functor, *(deref(a) for a in head[1:]))
    return head


def _check_cell_head_permission(term_val: Any, context: str, db,
                                module_dict: "dict | None") -> Any:
    """The term ``_resolve_cell_head`` answers, without its lowering flag
    (retract/1, which unifies against the stored heads and lowers nothing)."""
    return _resolve_cell_head(term_val, context, db, module_dict)[0]


def _resolve_cell_head(term_val: Any, context: str, db,
                       module_dict: "dict | None") -> "tuple[Any, bool]":
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
    is data; declare it -dynamic".  ``_declared_here_at_arity`` answers "does
    this module declare that name at that arity", which -- asked ONLY after
    the row lookup has come back None, as it is here -- is the same question,
    and it is what keeps the two refusals on the right side of the line.

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
    With no class (a bare ``Database()`` row) it is the cell with the
    canonical functor, and the flag returned beside it is True:
    ``_normalize_fact_clause`` gives it the every-argument lowering.
    Either way ``_normalize_fact_clause`` does the rest, and the ARG OBJECTS
    are shared with the caller's cell, so bindings made against the
    normalized term reach the caller's variables.

    Returns ``(term, hoist_all)``; *hoist_all* is False except in that case.
    """
    from clausal.logic.cells import compound_cell_shape, make_cell  # noqa: PLC0415
    from clausal.logic.exceptions import existence_error  # noqa: PLC0415

    ok, functor = compound_cell_shape(term_val)
    if not ok:
        return term_val, False
    arity = len(term_val) - 1
    args = tuple(term_val[1:])
    pred_cls = _find_pred_cls(functor, arity, module_dict)
    # The CANONICAL name is the predicate's own, not the spelling the cell
    # used: an ``-import_from`` alias binds the exporter's predicate under the
    # local name, and the row lives under the exporter's.
    home = _home_db(db, pred_cls, functor, arity)
    functor = _canonical_functor(db, pred_cls, functor)
    row = home.row(functor, arity) if home is not None else None
    if row is not None and row.dynamic:
        # P2 head flip (2026-09-19): a head IS the cell, so a cell reaching a
        # dynamic predicate needs no normalisation at all -- it only needs the
        # CANONICAL functor, which an -import_from alias can differ from.
        cell = term_val if functor == term_val[0] else make_cell(functor, *args)
        return cell, pred_cls is None
    foreign = row is not None and row.db is not db
    if foreign:
        # THE OWNERSHIP REFUSAL SPEAKS FIRST for somebody else's row
        # (2026-09-21, the P2 aliased-assertz ruling's channel-4 half).  This
        # check is about THIS module's vocabulary — "is that name data here" —
        # and its remedy, "declare it -dynamic(f/N)", is advice about THIS
        # module.  Reached for a row an ``-import_from`` shares, both are the
        # wrong thing to say: declaring it here would not help and must not,
        # and the reader needs to be told whose predicate it is.  The gate's
        # policy is the one that has an answer, so ask it before refusing in
        # this function's own words.
        #
        # ON THE ROW, not ``home is not db`` (roborev job 78, finding 3):
        # ``_home_db`` answers *db* whenever there is no class, and this
        # module's Database still resolves an ADOPTED key to the exporter's
        # row — so the class-shaped test missed exactly the shape this block
        # exists for.  A row knows its own database; that is the question.
        from clausal.logic.database import (  # noqa: PLC0415
            WRITE_ASSERT, WRITE_RETRACT, refusal_error, write_refusal,
        )
        kind = (WRITE_RETRACT if context.startswith("retract")
                else WRITE_ASSERT)
        author = db.runtime_author()
        reason = write_refusal(row, author, kind)
        if reason is not None:
            raise refusal_error(functor, arity, author, kind, reason,
                                channel=context)
    if row is None and not _declared_here_at_arity(module_dict, functor, arity):
        # RULED R7 (2026-09-28): writing a procedure nothing declares is
        # permission_error(modify, static_procedure, PI), with the refusing
        # builtin as context.  ISO has no permission type for "not yet
        # existing", and 7.5.2 makes a user procedure static by default, so
        # this is the same refusal as for a declared static predicate.
        from clausal.logic.builtins._registry import (  # noqa: PLC0415
            _BUILTINS, _DB_BUILTINS,
        )
        builtin = (functor, arity) in _BUILTINS or (functor, arity) in _DB_BUILTINS
        if not builtin and not context.startswith("retract"):
            from clausal.logic.builtins.flags import (  # noqa: PLC0415
                assert_creates_dynamic,
            )
            if assert_creates_dynamic(db):
                # ISO 7.5.2(2): with the flag on, asserting into a procedure
                # that does not exist CREATES it, as a dynamic procedure of
                # the calling module.  Only a name nothing declares gets
                # here: a static predicate (it has a row), a builtin and a
                # declared data functor are refused below as before.
                (home if home is not None else db).mark_dynamic(functor, arity)
                cell = (term_val if functor == term_val[0]
                        else make_cell(functor, *args))
                return cell, pred_cls is None
            # The refusal the construction of the clause used to raise
            # itself (``UndeclaredFunctorError``, a NameError too); the
            # construction defers to here because only this builtin knows
            # the calling module's flag.
            from clausal.logic.compiler.globals_env import (  # noqa: PLC0415
                UndeclaredFunctorError,
            )
            refusal = UndeclaredFunctorError(
                functor, arity, "procedure", context,
                why=(f"no predicate {functor}/{arity} is declared here, and "
                     f"a cell argument does not create one — a cell is "
                     f"indistinguishable from a plain data tuple — so "
                     f"declare it -dynamic({functor}/{arity}) first, or set "
                     f"the flag assert_creates_dynamic to true in this "
                     f"module"))
            # No ``name``: the solve-time undefined-name enrichment would
            # replace this with a plain NameError and lose the ISO term, and
            # the name is not undefined -- the procedure is.
            refusal.name = None
            raise refusal
        if context.startswith("retract") and not builtin:
            # ISO 8.9.3 (and Scryer): retracting from a procedure that does
            # not exist FAILS -- there is no clause to remove.  The caller
            # finds no clause list for it and fails.
            return term_val, False
        # A builtin is a static procedure (ISO 8.9.1.3 / 8.9.3.3, Scryer:
        # ``retract(atom_length(a, 1))`` is permission_error(modify,
        # static_procedure, atom_length/2)).
        why = (f"{context}: {functor}/{arity} is a builtin, a static "
               f"procedure" if builtin else
               f"{context}: no predicate {functor}/{arity} is declared here, "
               f"and a cell argument does not create one — a cell is "
               f"indistinguishable from a plain data tuple — so declare it "
               f"-dynamic({functor}/{arity}) first")
        raise LogicException(permission_error(
            "modify", "static_procedure", ("/", functor, arity), why))
    # THE REMEDY NAMES THE RIGHT MODULE (roborev job 78, finding 4).  For a
    # row this module merely reaches through an ``-import_from``, "declare it
    # -dynamic here" is advice that would not work and must not: the
    # declaration belongs in the module that OWNS the predicate.  Reached only
    # when the gate above permitted the write (a shared row that is neither
    # dynamic nor locked), so the refusal is still this function's — it is the
    # remedy, not the verdict, that changes.
    # ``module_name`` answers a placeholder (``<detached>``, ``<anonymous>``)
    # for a Database with no module dict, which names nothing a reader can act
    # on — prefer the load that supplied the clauses, and say "another module"
    # rather than print a placeholder.
    owner = row.source[1] if row is not None and row.source else None
    if owner is None and row is not None:
        named = row.db.module_name()
        owner = None if named.startswith("<") else named
    remedy = (f" — declare it -dynamic({functor}/{arity}) to modify it at "
              f"runtime")
    if foreign:
        remedy = (f" — it belongs to {owner}, so the -dynamic({functor}/"
                  f"{arity}) declaration that would permit this write "
                  f"belongs there, not here"
                  if owner else
                  f" — it belongs to another module, so the "
                  f"-dynamic({functor}/{arity}) declaration that would permit "
                  f"this write belongs there, not here")
    raise LogicException(permission_error(
        "modify", "static_procedure",
        ("/", functor, arity),
        f"{context}: {functor}/{arity} "
        + ("is a static procedure" if row is not None and row.clauses else
           "is a data functor (declared with fields and given no clauses), "
           "so its terms compile to cells and it has no clause list")
        + remedy,
    ))


def _declared_here_at_arity(module_dict: "dict | None", functor: str,
                            arity: int) -> bool:
    """True if *functor* is DECLARED in this module with exactly *arity*
    fields -- whatever it then turned out to be.

    RENAMED from ``_declared_with_fields`` in P3-3 Task 5 fix round 1 (F7),
    because the old name promised a data/predicate distinction this does not
    make: a ``-dynamic`` predicate, a static one and a data functor declared
    with the same field count all answer True here.  What it actually answers
    is "does this module declare that name at that arity".

    That is exactly the right question at its ONE call site, and only because
    of the ordering there: it is consulted after ``home.row(functor, arity)``
    came back ``None``.  A declared name with no row has no clauses, no
    dispatch, no signature and no ``-dynamic`` mark in the Database, which is
    what being a DATA functor consists of -- so at that point "declared here"
    and "is a data functor here" coincide, and the P3-2 diagnostic is the
    right one.  Move the call above the row lookup and that stops being true.

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
                   module_dict: "dict | None", _seen: "frozenset" = frozenset()) -> "Any":
    """The predicate BINDING the goal's name denotes at *arity* -- a
    module-qualified handle (mangled atom) -- or ``None``.

    ARITY-CHECKED (P3-3 Task 3): ``module_dict`` holds one binding per NAME,
    so a ``p/1`` assert must not be handed ``p/3``'s predicate; a name bound
    at another arity resolves to nothing here and the gate still sees the
    write, because it is asked about the ROW.

    What it answers is the module's own binding when that denotes a predicate
    of this arity (``is_declared_predicate``, era-agnostic; the class arm is
    exactly the old ``len(_fields) == arity``).  F1 rows 58/59, 2026-09-24:
    the function used to return "a class" through five legs.  Two of them
    redirected by the HEAD's own class; a head is a cell since P2, and over
    the house suite they were reached 0 times in 229 calls, so they are gone.
    With them gone every remaining leg answered exactly this binding check,
    so the row-comparison scaffolding went too.  Callers take the canonical
    name from ``predicate_binding_name`` and the write target from
    ``_home_db`` -- neither reads the class.
    """
    from clausal.logic.predicate import binding_grants_arity  # noqa: PLC0415
    if module_dict is None:
        return None
    db = getattr(module_dict.get("$module"), "db", None)
    candidate = module_dict.get(functor)
    # Review round 5: ``binding_grants_arity``, not ``is_declared_predicate``
    # -- an IMPORTED binding is this name's predicate only at an arity it was
    # imported at (the adopted rows); an owner arity added later (assertz) is
    # not reachable through the importer's name, in either era.
    if binding_grants_arity(candidate, arity, db, functor):
        return candidate
    # A HANDLE whose own route is lost (its owner popped from sys.modules)
    # still names the predicate this module IMPORTED when this database
    # adopted a row for it -- see ``_home_db``.  Not for any other mangled
    # atom: a ``-hide`` data atom can have an unresolvable owner too, and it
    # is no predicate.
    if _adopted_row_named_by(db, candidate, functor, arity) is not None:
        return candidate
    # An ALIASED import: a cell built from ``alias(gd_p, gd_loc)``'s local
    # name is spelled ``gd_p`` (the owner's), which this module does not bind;
    # the binding lives under the importer's spelling.  Only when the name is
    # bound to NOTHING here -- a local ``gd_p`` keeps its own meaning, and so
    # does a ROW this database owns under that spelling with no binding (a
    # predicate created by assertz, say): roborev 2026-09-25.
    if candidate is None and db is not None and not db.owns(functor, arity):
        local = db.adopted_spelling(functor, arity)
        # *_seen*: two aliased imports that swap names (``alias(a, b)`` and
        # ``alias(b, a)``) with neither local name bound would send this
        # fallback back and forth forever; a spelling already tried answers
        # nothing.
        if local is not None and local not in _seen:
            return _find_pred_cls(local, arity, module_dict,
                                  _seen | {functor})
    return None


def _adopted_row_named_by(db, handle, functor: str, arity: int):
    """The row this database adopted for ``functor/arity`` -- but only when
    *handle* is that row's handle: its atom half is the row's own functor and
    its module half the module owning the row's database.  A ``-hide`` data
    atom or an unrelated handle rebound under an imported name is not the
    import, and must not route a write to the owner's row."""
    from clausal.logic.atoms import demangle, is_mangled  # noqa: PLC0415
    if db is None or not is_mangled(handle):
        return None
    row = db.adopted_row(functor, arity)
    if row is None and not db.owns(functor, arity):
        # *functor* may be the OWNER's spelling of an aliased import (a cell
        # built from the alias); the adopted row is keyed by the local one --
        # unless this database owns a row under *functor* itself (roborev
        # 2026-09-25).
        local = db.adopted_spelling(functor, arity)
        row = db.adopted_row(local, arity) if local is not None else None
    if row is None:
        return None
    module_name, name = demangle(handle)
    if name != row.key[0] or module_name != row.db.module_name():
        return None
    return row


def _canonical_functor(db, binding, functor: str) -> str:
    """The predicate's OWN name for a write through *binding*: an
    ``-import_from`` alias binds the exporter's predicate under a local
    spelling, and its row lives under the exporter's name."""
    from clausal.logic.atoms import demangle, is_mangled  # noqa: PLC0415
    from clausal.logic.predicate import predicate_binding_name  # noqa: PLC0415
    if binding is None:
        return functor
    name = predicate_binding_name(binding, db=db)
    if name is None and is_mangled(binding):
        # Its owner is unresolvable, but an imported name binds the OWNER's
        # handle (ruling D1), whose atom half is the owner's own name.
        name = demangle(binding)[1]
    return name or functor


def _home_db(db, binding, functor: str, arity: int) -> "Any":
    """The Database whose row a write through *binding* must land in.

    A predicate reached through an ``-import_from`` is ONE predicate: it
    reads the OWNER's row, so a runtime assert made through it belongs in
    that row -- write it into the asserting module's own database instead and
    the two modules end up with two clause lists behind one predicate (P3-3
    Task 3 fix round 1).

    The row comes from ``resolve_predicate_row`` (the class's ``_row`` today;
    the owner's row for a handle).  When a HANDLE's own route is lost -- its
    owner was popped from ``sys.modules`` by the test runner, which the Q0
    ``db=`` hint does not cover for a foreign module -- the row this database
    ADOPTED at import is the same owner row, and is used instead: without it
    the write lands on the importer's own dead twin with no error (measured
    on ``gate_dyn_user`` by the F1 review).  Falls back to *db* when there is
    no binding, or when the class is still on its private detached row.
    """
    if binding is None:
        return db
    row = _binding_row(db, binding, functor, arity)
    return db if row is None else row.db


def _binding_row(db, binding, functor: str, arity: int) -> "Any":
    """The live row *binding* denotes at *arity*, or ``None`` -- the one
    place the "own row, else the adopted row, detached is nobody's" rule
    lives (``_home_db`` and ``io._indicator_row`` both read it).

    *functor* is the IMPORTER's spelling of the name -- the local name the
    goal or indicator used, which for an ``alias(Orig, Local)`` import is
    ``Local``, not the owner's ``Orig``: adopted rows are keyed by the
    importer's spelling, and ``_adopted_row_named_by`` checks the handle's
    atom half against the row's own (owner's) name.

    The row comes from ``resolve_predicate_row`` (the class's ``_row`` today;
    the owner's row for a handle).  When a HANDLE's own route is lost -- its
    owner popped from ``sys.modules`` -- the row this database ADOPTED for it
    at import is the same owner row.  A DETACHED row (a class still on its
    private row) answers ``None``: it is nobody's predicate.  For a class the
    row is NOT arity-checked here (``resolve_predicate_row``'s class arm does
    not consult *arity*); a caller that needs exact arity checks
    ``row.key[1]``.
    """
    from clausal.logic.predicate import resolve_predicate_row  # noqa: PLC0415
    if binding is None:
        return None
    row = resolve_predicate_row(binding, arity=arity, db=db)
    if row is None:
        row = _adopted_row_named_by(db, binding, functor, arity)
    if row is None or row.detached:
        return None
    return row


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
    when a module dict is available on the database, also recompiles with
    module globals for cross-predicate resolution.
    """
    from clausal.logic.database import head_key
    from clausal.logic.compiler import compile_predicate_trampoline
    module_dict = getattr(db, "module_dict", None)

    def assertz__1(term, trail, k):
        term_val = deref(term)
        if is_var(term_val):
            # ISO 8.9.1.3 a: an unbound clause is an instantiation error
            # (Scryer too); it used to fail silently (triage B4a).
            raise LogicException(instantiation_error("assertz/1"))
        clause = _build_clause(term_val, "assertz/1", db, module_dict)
        functor, arity = head_key(clause.head)
        pred_cls = _find_pred_cls(functor, arity, module_dict)
        # THROUGH THE GATE (P3-3 Task 3).  The lock check that used to stand
        # here is the gate's policy now — one question, "may this author write
        # this row", asked identically by all four channels — and it still
        # raises a typed permission_error rather than a RuntimeError, which
        # the drive loop would treat as generator exhaustion and swallow
        # (A09-F006 / decision A09-D002 a).  ``through=pred_cls`` is what
        # carries the check onto an -import_from'd predicate: the clause goes
        # into THIS module's row, but a shared class makes the exporter's row
        # part of the write's blast radius.
        home = _home_db(db, pred_cls, functor, arity)
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

    when a module dict is available on the database, also recompiles with
    module globals.
    """
    from clausal.logic.database import head_key
    from clausal.logic.compiler import compile_predicate_trampoline
    module_dict = getattr(db, "module_dict", None)

    def asserta__1(term, trail, k):
        term_val = deref(term)
        if is_var(term_val):
            # ISO 8.9.1.3 a: an unbound clause is an instantiation error
            # (Scryer too); it used to fail silently (triage B4a).
            raise LogicException(instantiation_error("asserta/1"))
        clause = _build_clause(term_val, "asserta/1", db, module_dict)
        functor, arity = head_key(clause.head)
        pred_cls = _find_pred_cls(functor, arity, module_dict)
        # Through the gate; see assertz/1 above.
        home = _home_db(db, pred_cls, functor, arity)
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
    when a module dict is available on the database, also recompiles
    through the predicate's binding.
    """
    from clausal.logic.database import head_key
    from clausal.logic.compiler import compile_predicate_trampoline
    module_dict = getattr(db, "module_dict", None)

    def retract__1(term, trail, k):
        term_val = deref(term)
        if is_var(term_val):
            # ISO 8.9.3.3 a (Scryer too): an unbound clause is an
            # instantiation error; it used to fail silently.
            raise LogicException(instantiation_error("retract/1"))
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
        pred_cls = _find_pred_cls(functor, arity, module_dict)
        home = _home_db(db, pred_cls, functor, arity)
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
        # Spec §6.4: the functor argument is an ATOM, read by spelling.
        if not _term_is_atom(f) or not isinstance(a, int):
            return
        db.abolish_table(_spelling(f), a)
        yield None

    return abolish_table__2


@_db_builtin("abolish_all_tables", 0, fields=())
def _abolish_all_tables_factory(db):
    """abolish_all_tables — remove all cached tabling answers."""

    def abolish_all_tables__0(trail, k):
        db.abolish_all_tables()
        yield None

    return abolish_all_tables__0
