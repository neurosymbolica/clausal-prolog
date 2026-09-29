"""compiler_v2 — Module-level compilation from ModuleAST.

Drives compilation from a list of ModuleItems (Predicate nodes, Directive
descriptors, Import descriptors) produced by EmbedTransformer.

The old v1 pipeline (exec bytecode → $define_predicate → compile each pending
predicate; deleted from import_hook.py after months dormant behind the
hardcoded ``_USE_V2_PIPELINE`` flag) is replaced by:

    compile_module(predicate_nodes, module_items, module_dict, module_name)

which handles directives, class creation, clause assertion, predicate
compilation, tabling wraps, and locking in a single pass.
"""

from __future__ import annotations

import contextlib
import importlib
import warnings
from typing import Any

from clausal.atom_diagnostics import truth_literal_hint_lines
from clausal.logic.database import (
    Module as LogicModule, Clause, head_key, refusal_error,
    WRITE_LOAD_CLAUSES, WRITE_LOAD_DISPATCH,
)
from clausal.logic.cells import DECLARED_ATOMS_KEY, IMPORT_FROM_KEY
from clausal.logic.atoms import (
    is_atom as _term_is_atom,
    is_mangled,
    mint as _mint_atom,
    spelling as _atom_spelling,
)
from clausal.logic.exceptions import LogicException
from clausal.logic.compiler import (
    compile_predicate_trampoline,
    compile_predicate_shallow,
)
from clausal.logic.predicate import (
    record_clause_source,
    field_names_for, is_declared_predicate, is_declared_predicate_name,
    binding_grants_arity,
    predicate_arities_for, predicate_binding_name, predicate_owner_module,
    resolve_predicate_row, _db_for_module_name,
    module_source_path,
    is_bound_predicate_at, declared_head, is_local_predicate_binding,
    end_loading_declarations,
)
from clausal.pythonic_ast.nodes import (
    AtomAppliedAsFunctor as AtomAppliedAsFunctorItem,
    BareAtomRefs as BareAtomRefsItem,
    CrossModeLiteralSites as CrossModeLiteralSitesItem,
    DoubleQuotesMode as DoubleQuotesModeItem,
    HeadFieldNames as HeadFieldNamesItem,
    Directive as DirectiveItem,
    HideDeclaration as HideDeclItem,
    ImportFromDirective as ImportFromItem,
    ImportModuleDirective as ImportModuleItem,
    ModuleDeclaration as ModuleDeclItem,
    PrivateDeclaration as PrivateDeclItem,
    SpecializeDirective as SpecializeItem,
    ImplicitAtomsDeclaration as ImplicitAtomsItem,
    StrictAtomsDeclaration as StrictAtomsItem,
)


# Sentinel distinguishing "not present" from a legitimately-bound None/False
# in module_dict -- see _process_bare_atom_refs (P3-1 Task 7 fix round 1).
_MISSING = object()


def _spelling_or_self(value):
    """*value*'s spelling if it is an ATOM, otherwise *value* unchanged.

    Two lines rather than a shared helper (2026-09-06-atoms-as-cells-strings,
    Task 9): the leaked-pool-atom shape test below is the only consumer here
    and the same two lines live beside the sibling test in ``import_hook``.
    """
    return _atom_spelling(value) if _term_is_atom(value) else value

_strict_atoms_deprecation_emitted = False


class ClausalStrictAtomsDeprecationWarning(DeprecationWarning):
    """``-strict_atoms`` is redundant now that strict resolution is the
    default. The directive still works but can be deleted."""


def _warn_strict_atoms_deprecated() -> None:
    """Emit the ``-strict_atoms`` deprecation notice at most once per
    process. Guarded by a module global rather than the warnings-filter
    dedup so it is exactly-once regardless of the consumer's filters."""
    global _strict_atoms_deprecation_emitted
    if _strict_atoms_deprecation_emitted:
        return
    _strict_atoms_deprecation_emitted = True
    import warnings
    warnings.warn(
        "-strict_atoms is redundant: strict atom resolution is now the "
        "default. The directive still works but can be deleted. "
        "(Shown once per process.)",
        ClausalStrictAtomsDeprecationWarning,
        stacklevel=2,
    )


def _head_field_names(module_items, by_arity: bool = False) -> dict:
    """The rewriter's per-functor field names for this load, keyed by NAME
    (each name's primary arity) -- or, with *by_arity*, keyed
    ``(name, arity)`` for every arity the file gives the name.

    Read off the ``HeadFieldNames`` module item (``{}`` when there is none,
    e.g. a hand-built item list).  This -- not the functor's class -- is where
    step 4's ``row.signature`` comes from: the class's ``_fields`` was only
    ever a copy of the same ``EmbedTransformer._seen_functors`` entry, carried
    on a vehicle that does not survive the PredicateMeta flip.
    """
    for item in module_items:
        if isinstance(item, HeadFieldNamesItem):
            return item.by_arity if by_arity else item.fields
    return {}


def compile_module(
    predicate_nodes: list,
    module_items: list,
    module_dict: dict,
    module_name: str = "<module>",
) -> LogicModule:
    """Compile a module from its ModuleAST.

    Parameters
    ----------
    predicate_nodes : list
        Runtime Predicate nodes (simple_ast) collected during bytecode exec.
        Each has .head (simple_ast Call or term) and .body (simple_ast node
        or True for facts).
    module_items : list
        Structural descriptors accumulated by EmbedTransformer at AST
        transform time: DirectiveItem, ImportFromItem, ImportModuleItem,
        ModuleDeclItem, PrivateDeclItem.
    module_dict : dict
        The Python module's __dict__: each predicate name is bound to its
        handle here, and the dict is used for cross-predicate resolution.
    module_name : str
        Module name for the LogicModule.

    Returns
    -------
    LogicModule
        The compiled logic module with all predicates dispatched.
    """
    logic_module = LogicModule(module_name, module_dict=module_dict)
    db = logic_module.db
    _install_real_module(module_dict, logic_module)

    # ── Step 0-: Reserved truth-value names ───────────────────────────────
    #    Runs before everything so the diagnostic names the real problem
    #    rather than whatever incidental error the name causes downstream.
    _reject_reserved_truth_names(module_items, predicate_nodes, module_name)

    # ── Step 0: Process imports (before term expansion, so imported TE
    #    rules are available) ──────────────────────────────────────────────
    _process_imports(module_items, module_dict, db)

    # ── Step 0b: the -double_quotes facts, and the cross-mode literal lint ─
    #    The mode is recorded for this module's IMPORTERS; the lint judges
    #    this module's own seam sites, which name callees whose mode is the
    #    OWNER's fact -- answerable only now that the imports have run.
    _record_double_quotes_mode(module_items, db)
    _apply_prolog_flag_directives(module_items, db)
    _lint_cross_mode_literals(module_items, module_dict)

    # ── Step 1: Term expansion (after imports, before directives) ────────
    from clausal.logic.term_expansion import run_term_expansion
    predicate_nodes = run_term_expansion(predicate_nodes, module_dict, db)

    # ── Step 1b: Goal expansion (regex pre-compile + auto-binding) ─────
    from clausal.logic.goal_expansion import run_goal_expansion
    predicate_nodes = run_goal_expansion(predicate_nodes, module_dict)

    # ── Step 1c: Pre-register specialized predicates ─────────────────────
    #    Create empty PredicateMeta classes for -specialize targets so that
    #    later clauses (e.g. Test) can reference them during compilation.
    _preregister_specializations(module_items, module_dict, db)

    # ── Step 2: Process directives ───────────────────────────────────────
    _process_directives(module_items, db, module_dict)

    # ── Step 2b: warn on an exported ATOM also made a predicate ──────────
    #    Operator ruling 2026-09-26 (a warning, not a refusal: ISO allows
    #    the atom foo beside a predicate foo/N).
    _warn_atom_exports_defined_as_predicates(
        module_items, predicate_nodes, module_name)
    #    ... and on a name/N export entry whose arity looks like a typo
    #    (ruling 2026-09-29: a warning; a clause-less name/N is legal).
    _warn_export_arity_mismatches(
        module_items, predicate_nodes, module_name, module_dict)

    # ── Step 3: Process module/private declarations ──────────────────────
    #    Needs to know which declared functors are PREDICATES (P3-2 Task 2 /
    #    R6): a predicate keeps its class, a data functor binds its interned
    #    spelling.  "Has clauses" cannot be read off the class here -- Step 4
    #    is what attaches them -- so it is read off the clause nodes and the
    #    predicate-shaped directives instead.
    _process_declarations(
        module_items, module_dict,
        _predicate_functor_names(predicate_nodes, module_items), db=db,
    )

    # ── Step 3b: Auto-mint undeclared bare atom references ───────────────
    #    Phase 2 of GLOBAL_ATOMS_DEFAULT.md.  Must run AFTER declarations
    #    (so module-local atoms shadow the global) and BEFORE clause
    #    compilation (so referenced names resolve in module_dict).
    #    Phase 3: if ``-strict_atoms`` is present in module_items, raise
    #    NameError on undeclared names instead of minting.
    _process_bare_atom_refs(module_items, module_dict, module_name)

    # ── Step 3b-bis: settle the imported "atom applied as a functor" sites ─
    #    P3-3 Task 4 fix round 2 (O2).  The rewrite could not tell whether an
    #    ``-import_from``'d name is a functor: that is the OWNER's fact, and
    #    the owner had not executed.  It has now — the module body ran before
    #    ``compile_module`` was called, and the ``-import_from`` rewrite
    #    copied the owner's functor signatures into this file's registry —
    #    so the question is answerable here, and BEFORE clause compilation
    #    turns an unresolvable reference into a runtime ``TypeError`` with no
    #    file or line on it.
    _check_atoms_applied_as_functors(module_items, module_dict)

    # ── Step 3b-ter: route an imported ATOM's APPLIED form to the local row ─
    #    P3-3 Task 5b, sub-shape 1.  Same phase and same reason as 3b-bis:
    #    "is the imported name a functor?" is the OWNER's fact and is first
    #    answerable here.  A local arity-N definition wins over an imported
    #    same-spelling atom, so the call site is re-pointed off the import
    #    remap and onto the local name BEFORE step 4 compiles the bodies.
    _route_imported_atom_calls_to_local(
        module_items, predicate_nodes, module_dict)

    # ── Step 3b-quater: an imported PREDICATE applied at ANOTHER arity ──
    #    Operator ruling 2026-09-24 (the aliased-import leak): an
    #    unqualified call resolves in THIS module under the name the caller
    #    USED.  The import remap spells ``nl(3, L)`` as the owner's dotted
    #    key, which would resolve ``/2`` in the OWNER under the OWNER's name;
    #    re-point such a call site to the local name instead.
    _route_other_arity_imported_calls_to_local(
        module_items, predicate_nodes, module_dict, db)

    # ── Step 3c: resolve each imported name to the CLASS it bound ────────
    #    Names only, no policy: ``origins`` maps every spelling an
    #    ``-import_from`` introduces (the alias AND the class's own functor)
    #    to the class itself.  The REFUSAL that used to live here is the
    #    mutation gate's now (P3-3 Task 3) — one policy, asked by every
    #    channel — and this is what hands the gate the shared class whose row
    #    a write would land on when ``module_dict.get(functor)`` cannot find
    #    it (identity todo instance 3, the aliased import).
    origins = _import_from_origins(module_items, module_dict, db=db)
    author = db.load_author()

    # ── Step 3d: ask the gate about EVERY clause this load will write ────
    #    A dry run over the whole predicate set, before the write loop below
    #    touches anything.  The pre-pass this replaced ran here for exactly
    #    this reason: a refusal fired partway through the write loop leaves
    #    the module it was protecting holding the earlier, LEGAL writes of a
    #    load that then failed -- a shared class implementing one export and
    #    attributed to a module that never finished loading.  The policy is
    #    pure (``Database.refusal_for`` mints nothing and opens no
    #    transaction), so asking twice is free and asking early is honest.
    _refuse_foreign_writes(db, predicate_nodes, module_dict, origins, author,
                           module_name)
    _refuse_unrefused_deferred_heads(predicate_nodes, module_dict, module_name)

    # ── Step 3e: a name imported AND declared here as a procedure ────────
    #    Operator ruling 2026-09-26.  After step 3d, so a procedure import
    #    met by local CLAUSES keeps the gate's own refusal message.
    _refuse_import_local_clashes(module_items, predicate_nodes, module_name)

    # ── Step 4: assertz all clauses ───────────────────────────────────────
    pending: dict[tuple[str, int], "str | None"] = {}
    head_fields = _head_field_names(module_items)
    head_fields_by_arity = _head_field_names(module_items, by_arity=True)
    for pred_node in predicate_nodes:
        functor, arity = head_key(pred_node.head)
        key = (functor, arity)

        # The same rule as step 3d (``_local_binding``).  This module's own
        # predicate HANDLE (``$declare_head``, W4b-3 slice 5) is what the
        # write goes THROUGH for the gate's ``through=`` -- never an
        # ``-import_from`` of the same spelling -- and what step 5 compiles
        # through, so the compile writes its index plans onto this row
        # (``_plan_row_for``) and installs through it.  (A ``PredicateMeta``
        # class was bound to the row here until W4b-3 slice 7 deleted it.)
        local, declared = _local_binding(module_dict, functor, arity)
        with _load_gate(db, functor, arity, author, WRITE_LOAD_CLAUSES,
                        _load_through(local, origins, functor, arity),
                        origins, module_name, module_dict):
            logic_module.define_predicate(pred_node)
            pending[key] = local
            # Whatever the name is bound to -- this module's handle, an
            # imported one, an atom or nothing -- the clauses just written are this load's, and the gate reads the
            # owner off the ROW.  ``create=True`` because that never answers
            # an ADOPTED row (another database's): this load owns what it
            # just wrote, never what it imported.
            clause_row = db.row(functor, arity, create=True)
            record_clause_source(clause_row, module_name, module_dict)
            # THE DECLARATION SITE (W4b-3 slice 5): the rewriter's class
            # carried it (``_registered_at``) onto the row when step 4 bound
            # it (``_bind_row``, first bind wins); the module body's
            # ``$declare_head`` record carries it now.  Same population: a
            # name this module declared and still binds to its own handle.
            if (clause_row.declared_at is None and declared is not None
                    and isinstance(declared[2], tuple)):
                clause_row.declared_at = declared[2]
            # THE SIGNATURE comes from the rewriter's head field names, on
            # the same row and under the same "whatever the name is bound
            # to" rule (operator ruling 2026-09-24): it describes the row's
            # clauses, not the module dict's binding.  It used to be read off
            # the class (``pred_cls._fields``), which is gone after the
            # flip; measured parity 2,450/2,457 stamping arrivals, the rest
            # being declare-then-import-then-define, where the class was a
            # FOREIGN placeholder and this module's own declaration is the
            # right label (implementation_plans/step4-signature-source-
            # design-2026-09-24.md §3) -- a shape that is REFUSED at step 3d
            # since the vocabulary-implements idiom was dropped (2026-09-24),
            # so it no longer arrives here.  First clause wins: a later clause
            # finds the row already stamped.  A ``define_predicate`` that
            # registered names from a non-cell head got there first too.
            if clause_row.signature is None:
                fields = head_fields_by_arity.get(key)
                if fields is None:
                    fields = head_fields.get(functor)
                if fields is not None and len(fields) == arity:
                    clause_row.signature = tuple(fields)

    # ── Step 4a: seed pending from -dynamic specs (A12-F005) ─────────────
    #    A declared-but-clause-less dynamic predicate must still compile to
    #    a dispatch (the always-fail trampoline) so querying it fails
    #    cleanly with 0 solutions instead of raising NotImplementedError
    #    from _get_dispatch().
    for item in module_items:
        if isinstance(item, DirectiveItem) and item.name == "dynamic":
            for functor, arity in item.specs:
                # THE DECLARATION NAMES THE IMPORT (2026-09-21, the P2
                # aliased-assertz ruling).  A module that writes
                # ``-dynamic(bo_p/1)`` while importing that very predicate
                # under an ALIAS has named the import: "I intend to assert
                # against this", the same thing the non-aliased sibling says.
                # There the ``-import_from`` binds the exporter's class under
                # ``bo_p`` itself, so the canonical spelling already resolves
                # to the shared class and the write reaches the owner's row.
                # Under an alias only ``AliasS`` is bound, and the shadow
                # class ``term_rewriting`` mints for the declaration takes the
                # canonical spelling instead — so ``_find_pred_cls`` answered
                # with a predicate that is nobody's, and the clause landed on
                # the importer's own row while the shared class kept reading
                # the owner's (``todo/aliased-assertz-loses-the-owner-under-
                # cells-2026-09-20.md``).  Binding the import here is what
                # makes the two spellings ONE case.
                imported = _imported_binding_by_canonical_name(
                    origins, db, functor, arity)
                if imported is not None and not db.is_defined(functor, arity):
                    # NOT when this module has clauses of its own under the
                    # name: that is a genuine clash, and a local definition
                    # keeps its own predicate — the same rule
                    # ``Database.adopt_row`` states for rows.
                    module_dict[functor] = imported
                # NO STAMP HERE ANY MORE (option D, 2026-09-22).  The
                # declared arity used to be written onto the CLASS at this
                # point, which for a clause-less ``-dynamic`` has no row yet,
                # so the write MINTED a private throwaway row -- 207 of the
                # 214 engine-side detached rows in a suite run came from that
                # one statement, and it was the last thing keeping the
                # detached row on the load path.  Nothing is lost: step 2's
                # ``mark_dynamic`` already records ``(functor, arity)`` in
                # ``db._dynamic``, and ``_declared_arity`` derives the
                # per-NAME set from there.  It still reads only while the
                # clause list is EMPTY, which includes the retract-back-to-
                # empty return leg of a predicate that did have clauses.
                #
                # THE OWNER'S DECLARATIONS ARE WHAT AN IMPORTER SEES, and
                # that survives option D unchanged (it used to be roborev job
                # 78 finding 5's observation about the WRITE).  The
                # declared-arity set is a property of the PREDICATE, not of
                # the module that mentioned it: `_declared_arity` derives it
                # from `cls._row._db`, and for an `-import_from` the shared
                # class's row IS the exporter's, so the read lands on the
                # OWNER's Database. Deriving from the COMPILING module's db
                # instead would have lost exactly that.
                key = (functor, arity)
                if key in pending:
                    continue
                pred_cls = module_dict.get(functor)
                # P1 (spec 2026-09-17 §2.2): the class's OWN ROW names its
                # arity, so this is the arity-checked membership test with no
                # class test and no ``_fields`` read.  ``_row`` is absent on
                # a non-predicate binding.  (It used to be set for every
                # predicate class reaching here as a SIDE EFFECT: the stamp
                # above read ``_dynamic_arities``, a property over the row,
                # which minted a detached row when there was none.  The stamp
                # is gone, so nothing here mints one.)
                #
                # NOT ``db.row(functor, arity) is not None``: step 2's
                # ``mark_dynamic`` already put ``(functor, arity)`` in this
                # database, so that test is VACUOUSLY TRUE here (measured
                # 2026-09-17), and ``-dynamic(d/2)`` beside ``d/1`` clauses
                # would then bind d/1's class onto d/2's row.
                #
                # A predicate HANDLE (a mangled atom -- the binding after the
                # flip) has no ``_row``, so the class test below would send an
                # IMPORTED ``-dynamic`` to ``pending[key] = None``: step 5 then
                # compiled this module's own empty dispatch and the mutation
                # gate refused it as a redefinition (flip dry run R5).  Ask the
                # era-agnostic foreignness test for a handle first; it reads
                # the owner's row at THIS arity, so a local ``-dynamic(p/2)``
                # beside an imported ``p/1`` stays local (name+arity ruling).
                if type(pred_cls) is str and is_mangled(pred_cls):
                    if _belongs_elsewhere(pred_cls, db, arity):
                        continue
                    # A LOCAL handle.  There is no class to bind: the row is
                    # this Database's own (``resolve_predicate_row``, the
                    # owner's row for a handle), so step 5 compiles it with
                    # no class -- ``pending[key] = None``, the entry a
                    # clause-less ``-dynamic`` class also gets (option D: it
                    # has no ``_row`` yet).  Said here explicitly rather than
                    # reached by ``getattr(<str>, "_row")`` answering None.
                    _lrow = resolve_predicate_row(pred_cls, arity=arity, db=db)
                    if _lrow is not None and _lrow.db is not db:
                        raise RuntimeError(
                            f"-dynamic({functor}/{arity}): a handle "
                            f"_belongs_elsewhere called local reads another "
                            f"Database's row")
                    pending[key] = None
                    continue
                # (A ``PredicateMeta`` class bound to its row here until
                # W4b-3 slice 7 deleted the class.)
                pending[key] = None

    # ── Step 4a-bis: register this db as a handle owner, EARLY ───────────
    #    (This was the flip point, W4b-2d task 8, which rebound classes to
    #    handles; since W4b-3 slices 5-7 every predicate binding in the
    #    module dict is already its HANDLE -- the body's ``$declare_head``,
    #    an ``-import_from`` -- so there is nothing to rebind.)  The db
    #    becomes an owner for handles naming its module (ruling Q0) NOW,
    #    not only at the end of the load: a handle may be RUN before
    #    ``compile_module`` returns (a ``-specialize`` source program at
    #    step 6b, an ``-initialization`` goal), and a module the caller
    #    never put in ``sys.modules`` would otherwise resolve to nothing.
    #    Idempotent and weak.
    from clausal.logic.predicate import register_handle_owner  # noqa: PLC0415
    register_handle_owner(db)
    # The module body's ``$declare_head`` record retires here too (W4b-3
    # slice 5): it answered for the handles this load declared exactly as
    # long as the rewriter's classes did, and from here on the Database is
    # the sole authority for them.
    end_loading_declarations(module_dict)

    # ── Step 4b: validate directive targets (A12-F003) ───────────────────
    _validate_directive_targets(module_items, db, module_dict)

    # ── Step 4c: stratification analysis (report, never refuse) ──────────
    #    A negation cycle with an untabled member warns at load time instead
    #    of surfacing later as a bare RecursionError (or a wrong answer) at
    #    whichever query happens to reach it. Fully tabled cycles are
    #    legitimate WFS programs and stay silent.
    from clausal.logic.stratification import check_stratification
    check_stratification(db, module_name)

    # ── Step 5: Compile each predicate ───────────────────────────────────
    #    Through the gate as well as step 4 (P3-3 Task 3): the dispatch is the
    #    channel the aliased-import clobber actually travelled — the clause
    #    list was guarded and the dispatch was not, so the damage was
    #    invisible to a clause count.  One policy, asked again for the write
    #    that lands the compiled function.
    for (functor, arity), pred_cls in pending.items():
        clauses = db.clauses_for(functor, arity)
        with _load_gate(db, functor, arity, author, WRITE_LOAD_DISPATCH,
                        _load_through(pred_cls, origins, functor, arity),
                        origins, module_name, module_dict):
            if db.is_shallow(functor, arity):
                compile_predicate_shallow(
                    functor, arity, clauses, db,
                    globals_=module_dict, pred_cls=pred_cls,
                )
            else:
                compile_predicate_trampoline(
                    functor, arity, clauses, db,
                    globals_=module_dict, pred_cls=pred_cls,
                )

    # ── Step 6: Wrap tabled predicates ───────────────────────────────────
    #    Step 5 already installed the wrapper (``compiler._install`` is the
    #    choke point that also survives an assertz-driven recompile), so this
    #    pass is idempotent belt-and-braces for any compile path that installs
    #    a dispatch some other way.
    for (functor, arity), pred_cls in pending.items():
        if db.is_tabled(functor, arity):
            from clausal.logic.tabling import ensure_tabled_wrapper
            # THE ROW (W3): ``db.get_dispatch`` -- installed -> lazy
            # recompile -> registry.
            original_fn = db.get_dispatch(functor, arity)
            wrapped = ensure_tabled_wrapper(db, functor, arity, original_fn)
            if wrapped is original_fn:
                continue
            with db.mutate(functor, arity, author=author,
                           kind=WRITE_LOAD_DISPATCH, detail="table-wrap",
                           through=pred_cls):
                db.set_dispatch(functor, arity, wrapped)

    # ── Step 6b: Meta-interpreter specialization ────────────────────────
    #    Runs after all predicates are compiled so source programs can be
    #    called.  Specialized predicates compile themselves internally.
    _run_specialization(module_items, predicate_nodes, module_dict, db)

    # ── Step 7: Lock non-dynamic predicates ──────────────────────────────
    _lock_static_predicates(db)

    # Ruling Q0 (final): record this LOADED database as the owner handles
    # naming its module resolve to once the ``.clausal`` runner pops it from
    # ``sys.modules``.  Handle resolution only (weak; see
    # ``predicate._HANDLE_OWNERS``) -- a user-written ``M:G`` never sees it.
    from clausal.logic.predicate import register_handle_owner  # noqa: PLC0415
    register_handle_owner(db)

    return logic_module


_IMPORT_PLACEHOLDER = "_clausal_import_placeholder"


def mark_import_placeholder(module: LogicModule) -> LogicModule:
    """Mark *module* as the import hook's exec-time PLACEHOLDER ``$module``:
    the one module ``compile_module`` may replace (``_install_real_module``).
    Returns *module*."""
    setattr(module, _IMPORT_PLACEHOLDER, True)
    return module


def _install_real_module(module_dict: dict, logic_module: LogicModule) -> None:
    """Make *logic_module* the module ``module_dict`` names, for the WHOLE of
    ``compile_module`` (pre-flip task 4; W4b-2d dry run root cause R1).

    ``import_hook._run_v2_pipeline`` execs the module body with a PLACEHOLDER
    ``LogicModule`` bound as ``$module`` (the body's ``-constants``
    directives register onto it).  The placeholder's Database shares the
    module dict, so it reports the real module's name and claims every
    local handle -- but its store is EMPTY.  Every name-keyed lookup of the
    module being compiled goes through that namespace:
    ``_db_for_module_name`` reads ``sys.modules[name].__dict__["$module"]``
    and ``resolve_module`` coerces through ``__clausal_module__`` (absent,
    so it wrapped a fresh, equally empty ``Module``).  So a handle to this
    module resolved mid-compile -- a ``-specialize`` source program called at
    step 6b, once the flip binds it to a handle -- answered from nothing.

    Swapping here, before step 0, closes it for every step: the constants the
    body registered are carried across (the one thing the placeholder holds;
    it has no clauses), then both names point at the real module.

    Only a module the hook MARKED as its placeholder
    (``mark_import_placeholder``) is replaced -- never "whatever ``$module``
    holds".  A second compile into a namespace that already finished loading
    (the direct API on a loaded module's dict) must not swap the live module,
    whose db has clauses, for a fresh one; before this function
    compile_module wrote neither name, so leaving them is today's behaviour.
    No ``$module`` (the direct API), or an unmarked one: nothing installed.
    A marker rather than a ``compile_module`` keyword keeps its signature,
    which tests (and wrappers) monkeypatch positionally.
    """
    placeholder = module_dict.get("$module")
    if not getattr(placeholder, _IMPORT_PLACEHOLDER, False):
        return
    logic_module.constants.update(getattr(placeholder, "constants", None) or {})
    logic_module.constant_units.update(
        getattr(placeholder, "constant_units", None) or {})
    module_dict["$module"] = logic_module
    module_dict["__clausal_module__"] = logic_module


_MODULE_ALIASES: dict[str, str] = {
    "csv_mod": "py.csv",
    "date_time": "py.datetime",
    "files_mod": "py.files",
    "hash_mod": "py.hash",
    "hmac_mod": "py.hmac",
    "http_mod": "py.http",
    "json_mod": "py.json",
    "log": "py.logging",
    "os_mod": "py.os",
    "pbkdf2_mod": "py.pbkdf2",
    "process_mod": "py.process",
    "random_mod": "py.random",
    "regex": "py.re",
    "sqlite": "py.sqlite",
    "tcp_mod": "py.tcp",
    "url_mod": "py.url",
    "uuid": "py.uuid",
    "uuid_mod": "py.uuid",
    "yaml": "py.yaml",
    "spacy": "py.spacy",
    "sympy": "py.sympy",
    "scipy_cluster": "py.scipy_cluster",
    "scipy_constants": "py.scipy_constants",
    "scipy_differentiate": "py.scipy_differentiate",
    "scipy_fft": "py.scipy_fft",
    "scipy_integrate": "py.scipy_integrate",
    "scipy_interpolate": "py.scipy_interpolate",
    "scipy_linalg": "py.scipy_linalg",
    "scipy_ndimage": "py.scipy_ndimage",
    "scipy_optimize": "py.scipy_optimize",
    "scipy_signal": "py.scipy_signal",
    "scipy_sparse": "py.scipy_sparse",
    "scipy_spatial": "py.scipy_spatial",
    "scipy_special": "py.scipy_special",
    "scipy_stats": "py.scipy_stats",
    "torch": "py.torch",
    "torch_nn": "py.torch_nn",
    "torch_data": "py.torch_data",
    "torch_functional": "py.torch_functional",
    "torch_distributions": "py.torch_distributions",
    "jax": "py.jax",
    "jax_random": "py.jax_random",
    "jax_nn": "py.jax_nn",
    "jax_transforms": "py.jax_transforms",
    "jax_scipy": "py.jax_scipy",
    "jax_sharding": "py.jax_sharding",
    "jax_tree": "py.jax_tree",
    "jax_optax": "py.jax_optax",
    "jax_equinox": "py.jax_equinox",
    "jax_flax": "py.jax_flax",
    "opencv": "py.opencv",
    "opencv_calib3d": "py.opencv_calib3d",
    "opencv_color": "py.opencv_color",
    "opencv_contours": "py.opencv_contours",
    "opencv_draw": "py.opencv_draw",
    "opencv_features": "py.opencv_features",
    "opencv_imgproc": "py.opencv_imgproc",
    "opencv_objdetect": "py.opencv_objdetect",
    "opencv_video": "py.opencv_video",
    "sklearn": "py.sklearn",
    # Clausal-domain modules (not third-party wrappers — no py/ subdirectory)
    "currency": "currency",
    "graphs": "graphs",
    "imperial": "imperial",
    "prolog": "prolog",
    "provenance": "provenance",
    "units": "units",
}

_CURRENCY_JURISDICTIONS = None


def _currency_jurisdictions():
    """Lazily load the generated currency jurisdiction names (cached)."""
    global _CURRENCY_JURISDICTIONS
    if _CURRENCY_JURISDICTIONS is None:
        from clausal.modules.countries._data import JURISDICTIONS
        _CURRENCY_JURISDICTIONS = frozenset(JURISDICTIONS)
    return _CURRENCY_JURISDICTIONS


def _resolve_module(module_path: str):
    """Import a module, trying clausal.modules first (with alias mapping)."""
    mapped = _MODULE_ALIASES.get(module_path)
    if mapped is None and module_path in _currency_jurisdictions():
        mapped = f"countries.{module_path}"
    if mapped is None:
        mapped = module_path
    try:
        return importlib.import_module(f"clausal.modules.{mapped}")
    except (ModuleNotFoundError, ImportError):
        return importlib.import_module(module_path)


def _imported_reference(mod, orig_name: str, value):
    """What the importer's DOTTED key for *orig_name* should hold.

    P3-3 Task 5b, sub-shape 2.  The dotted key is the one the ``-import_from``
    remap emits for every reference to the imported spelling
    (``term_rewriting``'s ``_import_remap``), so it is a REFERENCE to the
    name, not the module attribute — and for a name the owner DECLARED as an
    atom the reference means the atom, whatever else the owner also holds
    under that spelling.

    Post-pivot a declared atom binds its own interned spelling, so the two
    normally coincide.  They come apart for exactly one shape: the owner
    declares the name in its ``-module``/``-private`` list AND writes 0-arity
    clauses for it, so the clause block's predicate handle wins the binding
    (``_process_declarations``' don't-clobber guard).  The owner's own
    lowering still answers such a reference with the str — its ``-module``
    list is in front of it — and the importer used to answer with the
    predicate object, so a dict key written by the owner and read by the
    importer silently missed.  ``DECLARED_ATOMS_KEY`` is what lets the importer answer the way
    the owner does.

    The declaration is the authority, not the presence of /0 clauses: a name
    with 0-arity clauses that the owner never declared as an atom is a
    predicate, and stays the predicate handle.  A DUAL declaration
    (``-module(m, [dual, dual(G)])``) is a functor too — its handle carries
    fields (``field_names_for``) — so only a zero-field handle is answered
    with the spelling.

    The module ATTRIBUTE (``mod.name`` from Python, and this file's own bare
    local binding) is untouched: it keeps the predicate handle, so ``call/N``
    and ``assertz`` still find the /0 predicate through the namespace (see
    ``higher_order._namespace_dispatch`` → ``database_ops._find_pred_cls``).
    """
    fields = field_names_for(value)
    if fields != ():
        return value
    declared = getattr(mod, "__dict__", {}).get(DECLARED_ATOMS_KEY)
    if not declared or orig_name not in declared:
        return value
    from clausal.import_hook import predicate_builtins  # noqa: PLC0415
    return predicate_builtins.setdefault(orig_name, _mint_atom(orig_name))


def _plant_imported_rows(db, mod, orig_name: str, local_name: str,
                         selected=None) -> None:
    """Make *local_name* resolve, in *db*, to the row the exporter owns.

    Spec §4 q1.  The binding above is the whole import relationship today --
    one Python object reference -- and the importing Database has no record of
    it at all.  This puts the relationship in the store, under the IMPORTER's
    own spelling, so ``db.row(functor, arity)`` answers "what does this name
    mean here" for imported names as well as local ones.

    The arity comes from the exporter's database, because an ``-import_from``
    names a predicate without one.  Purely additive: nothing resolves THROUGH
    the importer's database yet, so planting cannot change how a goal is
    reached -- it can only make a question answerable that returned ``None``
    before.
    """
    if db is None:
        return
    exporter = getattr(mod, "__dict__", {}).get("$module")
    exporter_db = getattr(exporter, "db", None)
    if exporter_db is None or exporter_db is db:
        return
    for arity in exporter_db.arities_for(orig_name):
        if selected is not None and arity not in selected:
            continue        # D20: ``name/N`` imports the arities it names
        row = exporter_db.row(orig_name, arity)
        if row is not None:
            db.adopt_row(local_name, arity, row)


def _refuse_missing_indicators(item, mod, orig_name: str, selected,
                               module_dict: dict) -> None:
    """D20: an ``-import_from(m, [p/N])`` entry whose exporter has no
    ``p/N`` is a load-time existence error (as Scryer's ``use_module(m,
    [p/N])`` refuses an indicator ``m`` does not export).  It names the
    module, the indicator and the line, and says which arities ``m`` has for
    ``p``.  A Python module has no predicate arities at all, so an indicator
    against one is refused too."""
    from clausal.logic.predicate import namespace_db  # noqa: PLC0415
    where = module_dict.get("__file__") or module_dict.get("__name__") or ""
    line = getattr(item, "line", 0)
    at = f"{where}, line {line}" if line else where
    exporter_db = namespace_db(vars(mod))
    wanted = ", ".join(f"{orig_name}/{a}" for a in sorted(selected))
    if exporter_db is None:
        raise ImportError(
            f"{at}: -import_from({item.module}, [{wanted}]): {item.module} is "
            f"not a Clausal module, so its names have no predicate arities to "
            f"select; list the bare name `{orig_name}` instead")
    have = exporter_db.declared_arities_for(orig_name)
    missing = sorted(a for a in selected if a not in have)
    if not missing:
        return
    first = f"{orig_name}/{missing[0]}"
    if have:
        found = ", ".join(f"{orig_name}/{a}" for a in sorted(have))
        offer = f"{item.module} has {orig_name} as {found}"
    else:
        offer = f"{item.module} has no {orig_name} at any arity"
    raise ImportError(
        f"{at}: -import_from({item.module}, [{wanted}]): "
        f"existence_error(procedure, {first}) -- {item.module} has no "
        f"procedure {first}; {offer}",
        name=orig_name, path=getattr(mod, "__file__", None))


def _process_imports(module_items: list, module_dict: dict, db=None) -> None:
    """Execute import directives, populating module_dict.

    *db* is the importing module's Database -- the LOCAL in ``compile_module``.
    Since ``_install_real_module`` the dict's ``$module`` is that same module
    for the whole compile (it used to be the import hook's placeholder, and
    reaching for the dict planted into a database that was thrown away);
    the explicit parameter stays, because the direct API passes a namespace
    with no ``$module`` at all.
    """
    # The per-file ``-import_from`` record (``cells.IMPORT_FROM_KEY``),
    # rebuilt from scratch so a recompile into the same namespace does not
    # accumulate.  Read by ``solve.imported_atoms``.
    import_record = module_dict[IMPORT_FROM_KEY] = []
    # The body-time record of ``name/N`` selections has served its purpose
    # (``predicate._foreign_head_verdict``); the adopted rows planted below
    # are the record from here on.
    module_dict.pop("$import_arities", None)
    for item in module_items:
        if isinstance(item, ImportFromItem):
            mod = _resolve_module(item.module)
            exporter = getattr(mod, "__name__", None) or item.module
            for name_spec in item.names:
                local = name_spec[1] if isinstance(name_spec, tuple) else name_spec
                selected = _selected_arities(item, local)
                # ``(atom-or-name, exporter, arities)``: *arities* is ``None``
                # for a bare entry and the selected frozenset for ``name/N``
                # entries, which name a PREDICATE, never an atom (D20).
                import_record.append(
                    (name_spec[0] if isinstance(name_spec, tuple)
                     else name_spec, exporter, selected))
                if selected is not None:
                    _refuse_missing_indicators(
                        item, mod,
                        name_spec[0] if isinstance(name_spec, tuple)
                        else name_spec, selected, module_dict)
                if isinstance(name_spec, tuple):
                    orig_name, local_name = name_spec
                    value = getattr(mod, orig_name)
                    module_dict[local_name] = value
                    # Keyed by LOCAL_NAME: the aliasing module says ``link``,
                    # so ``link`` is what its database answers to.  A class
                    # cannot do this -- it carries the exporter's ``__name__``
                    # wherever it goes, which is why ``_import_from_origins``
                    # has to index an aliased import under both spellings.
                    _plant_imported_rows(db, mod, orig_name, local_name,
                                         selected)
                    # Also store under the dotted key ("module.OrigName") so
                    # that _inject_resolved_targets can resolve it when the compiler
                    # emits LoadName(name="module.OrigName") for remapped imports.
                    module_dict[f"{item.module}.{orig_name}"] = (
                        _imported_reference(mod, orig_name, value))
                else:
                    value = getattr(mod, name_spec)
                    module_dict[name_spec] = value
                    _plant_imported_rows(db, mod, name_spec, name_spec,
                                         selected)
                    # Dotted key for compiler resolution (e.g. "py.sympy.inf").
                    module_dict[f"{item.module}.{name_spec}"] = (
                        _imported_reference(mod, name_spec, value))
            # Store the module object under its user-facing name so that
            # dotted-name resolution works in the compiler's
            # ``_inject_resolved_targets`` -- but ONLY for a dotted path.
            #
            # BUG #2 (found by a downstream tool, reproduced at
            # engine level 2026-09-11): a SINGLE-SEGMENT module name is also a
            # valid Clausal identifier, so this binding shadows a profile key
            # or atom of the same spelling. The name holds a Python MODULE
            # while a bare key is the interned atom ``('currency',)`` -- two
            # different kinds of thing in one namespace slot, so the collision
            # is SILENT: the lookup finds nothing and the rule answers
            # ``unknown([key])``. `currency` is simultaneously a vocab module
            # and an invoice's own currency field, and downstream code held the
            # hazard off by emitting imports in a fixed ORDER, with a
            # regression test pinning the order.
            #
            # A dotted path binds under a key like ``py.units``, which is not
            # a writable identifier and so cannot collide. Keeping it there
            # preserves every use that depends on this (five tests in
            # imported-atom/functor resolution) and drops only the form that
            # shadows -- measured both ways: removing it entirely fails those
            # five, restricting it to dotted paths fails nothing.
            #
            # An author who wants the module wants ``-import_module``, which
            # binds it and is untouched. Each directive now does what its name
            # says: ``-import_from`` binds the names it lists.
            if "." in item.module:
                module_dict[item.module] = mod
        elif isinstance(item, ImportModuleItem):
            mod = _resolve_module(item.module)
            # Store the top-level name (e.g., "foo" for "foo.bar.baz").
            top_name = item.module.split(".")[0]
            module_dict[top_name] = mod


# The six spellings of the three truth values.  ``True``/``False`` are Python
# constants and ``Undefined`` is an injected runtime binding; ``true``/``false``/
# ``undefined`` are their parse-time aliases (``term_rewriting._TRUTH_ALIASES``).
# All six denote values, never predicates.
_RESERVED_TRUTH_NAMES = {
    "True": "True", "true": "True",
    "False": "False", "false": "False",
    "Undefined": "Undefined", "undefined": "Undefined",
}


def _reject_reserved_truth_names(
    module_items: list, predicate_nodes: list, module_name: str
) -> None:
    """Refuse to define a predicate or atom named after a truth value.

    Value position already resolves these names to the literal — that is what
    makes them builtins — but *definition* position had no guard, so a clause
    head ``true(1),`` quietly minted a ``true/1`` predicate and a declaration
    ``-private([True(X)])`` quietly minted a class.  Neither is reachable by
    name afterwards (every reference site resolves to the value instead), so
    the author gets a predicate they cannot call.

    Where a definition did fail before, it failed by accident and said so
    badly: ``True(1),`` raised ``TypeError: 'bool' object is not callable`` from
    deep in the generated code, naming neither the clause nor the rule.  Both
    spellings are therefore checked, not just the aliases — the canonical ones
    were never really definable either.

    Raises ``NameError`` listing every offending name at once, so an author
    fixing a file with several does not discover them one re-run at a time.
    """
    offenders: list[tuple[str, str]] = []   # (name, where)
    seen: set[tuple[str, str]] = set()

    def note(name, where):
        if name in _RESERVED_TRUTH_NAMES and (name, where) not in seen:
            seen.add((name, where))
            offenders.append((name, where))

    for pred_node in predicate_nodes:
        functor, arity = head_key(pred_node.head)
        note(functor, f"clause head {functor}/{arity}")

    for item in module_items:
        if isinstance(item, (ModuleDeclItem, PrivateDeclItem)):
            entries = (
                item.exports if isinstance(item, ModuleDeclItem) else item.items
            )
            kind = "-module" if isinstance(item, ModuleDeclItem) else "-private"
            for entry in entries:
                name = entry[0] if isinstance(entry, tuple) else entry
                if isinstance(name, str):
                    note(name, f"{kind} declaration")
        elif isinstance(item, DirectiveItem) and item.name != "set_prolog_flag":
            for functor, arity, *_ in item.specs:
                note(functor, f"-{item.name}({functor}/{arity})")

    if not offenders:
        return

    lines = [
        f"reserved truth value name(s) defined in {module_name}:",
    ]
    lines += [
        f"  `{name}` in {where} — `{_RESERVED_TRUTH_NAMES[name]}` is a builtin "
        f"truth value, not a predicate"
        for name, where in offenders
    ]
    lines += [
        "",
        "  The three truth values are `True`, `False` and `Undefined` (aliases:",
        "  `true`, `false`, `undefined`).  All six spellings resolve to the value",
        "  wherever they appear, so a predicate or atom of that name could never",
        "  be referenced.  Rename the predicate.",
    ]
    raise NameError("\n".join(lines))


def _import_from_origins(module_items: list, module_dict: dict,
                         db=None) -> dict:
    """``{name: (dotted module, bound predicate or None)}`` for every name an
    ``-import_from`` binds in this file.

    Indexed under BOTH names an aliased import gives a predicate.  ``alias(f,
    G)`` binds the exporter's predicate under ``G``, but it keeps its own
    functor ``f``, and a clause head compiles to that functor — so
    ``head_key`` hands the load channel ``f`` while the file only ever
    mentions ``G``.  Indexing the alias alone let the aliased spelling walk
    straight past the refusal and clobber the exporter through step 5's
    dispatch assignment, with the clause list left intact so the damage was
    invisible to a clause count (found by review, 2026-08-25).

    This is a RESOLVER, not a guard (P3-3 Task 3): it answers "which
    predicate does this head name reach", and the mutation gate answers "may
    this load write it".  It is the one place the identity todo's "resolve a
    head to its predicate once" is done for the load channel.

    Era-agnostic (F1 row 27): the bound value is whatever the module dict
    holds for a declared predicate -- a ``PredicateMeta`` class today, a
    mangled atom after the flip -- and its own name comes from
    ``predicate_binding_name``, not ``__name__``.  Measured 2026-09-24 over
    the house suite: 2,354 bindings, 275 classes, and NONE of the 2,079
    others is a declared predicate, so the wider filter changes nothing
    today; ``tests/test_import_origins_both_eras.py`` checks that both
    shapes give the same answers.
    """
    origins = _Origins()
    everything: set[str] = set()     # names some bare entry imported
    for item in module_items:
        if not isinstance(item, ImportFromItem):
            continue
        for name_spec in item.names:
            local = name_spec[1] if isinstance(name_spec, tuple) else name_spec
            bound = module_dict.get(local)
            own_name = predicate_binding_name(bound, db=db)
            if own_name is None:
                bound = None
            origins[local] = (item.module, bound)
            selected = _selected_arities(item, local)
            _merge_selection(origins, local, selected, everything)
            if own_name is not None and own_name != local:
                _merge_selection(origins, own_name, selected, everything)
                origins.setdefault(own_name, (item.module, bound))
    return origins


class _Origins(dict):
    """``_import_from_origins``' answer: ``{name: (module, bound)}``, plus
    ``arities`` -- ``{name: frozenset}`` for a name whose import selected
    arities with ``name/N`` entries (D20, 2026-09-29).  A name absent from
    ``arities`` was imported at every arity its exporter has."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.arities: dict[str, frozenset] = {}


def _merge_selection(origins, name: str, selected, everything: set) -> None:
    """Merge one entry's selection for *name* into ``origins.arities``: the
    union across entries and directives, and a bare entry (``None``) means
    every arity for good (roborev, 2026-09-29)."""
    if selected is None or name in everything:
        everything.add(name)
        origins.arities.pop(name, None)
        return
    origins.arities[name] = origins.arities.get(name, frozenset()) | selected


def _selected_arities(item, local: str) -> "frozenset | None":
    """The arities an ``-import_from`` item's ``name/N`` entries selected for
    the LOCAL name *local*, or ``None`` when it imports every arity."""
    return (getattr(item, "arities", None) or {}).get(local)


def _imported_at(origins: dict, functor: str, arity) -> bool:
    """False when *functor*'s import selected arities (``name/N``) and
    *arity* is not one of them: the import does not reach that arity, so a
    local ``functor/arity`` is a procedure of its own (ISO)."""
    if arity is None:
        return True
    selected = getattr(origins, "arities", {}).get(functor)
    return selected is None or arity in selected


def _refuse_unrefused_deferred_heads(predicate_nodes, module_dict,
                                     module_name) -> None:
    """The invariant behind ``predicate._handle_head_cell``'s deferral: a head
    built for ANOTHER module's predicate, positionally and ignoring its field
    names, because the load gate refuses it, never reaches a row.  Reached
    only when step 3d permitted this load; a deferred key among its writes
    means the gate did NOT refuse such a head, and the positional cell would
    be stored.  Raise instead of storing a head built on that assumption.

    Reachable from source: a head written through a Python-held handle
    (``h = mangle(m, 'p')`` then ``h(COLOUR) <- ...``) is not an
    ``-import_from``, so step 3d does not refuse it.  Before the deferral
    that head raised ClausalTermConstructionError (field names); now it is
    this refusal."""
    deferred = module_dict.pop("$deferred_heads", None)
    if not deferred:
        return
    written = {head_key(p.head) for p in predicate_nodes}
    stray = sorted(deferred & written)
    if stray:
        names = ", ".join(f"{f}/{a}" for f, a in stray)
        raise SyntaxError(
            f"{module_name}: the clause head(s) {names} are written through a "
            f"handle to ANOTHER module's predicate, with field names that "
            f"predicate does not have, and this module does not -import_from "
            f"it -- a module may define clauses only for its own predicates; "
            f"write them in the owning module")


def _belongs_elsewhere(binding, db, arity: int) -> bool:
    """True when *binding* already reads another Database's real row -- i.e.
    it is somebody else's predicate, reached here through an
    ``-import_from``.  A class on its private detached row is unbound, not
    foreign.

    The row comes from ``resolve_predicate_row`` (F1 row 29): the class's
    ``_row`` today, exactly what this read directly, and the owner's row for
    a mangled atom after the flip -- where a ``getattr(binding, "_row")``
    would answer ``None`` and quietly call every import local.
    """
    row = resolve_predicate_row(binding, arity=arity, db=db)
    return row is not None and not row.detached and row.db is not db


def _imported_binding_by_canonical_name(origins: dict, db, functor: str,
                                        arity: int):
    """The predicate this module IMPORTED whose own name is *functor* at
    *arity* — or None.

    A predicate keeps the exporter's name wherever it goes, so an
    ``-import_from(m, [alias(bo_p, alias_s)])`` leaves the canonical spelling
    bound to nothing in ``module_dict`` and ``alias_s`` bound to a predicate
    that calls itself ``bo_p``.  ``_import_from_origins`` has ALREADY seen
    through that — it indexes an aliased import under both the alias and
    the predicate's own name — so this is ``_imported_binding`` plus the two
    checks that call site needs and it does not:

    * ARITY.  ``origins`` is keyed by name alone, and a name bound at another
      arity is not the predicate this ``-dynamic(f/N)`` declares.
    * FOREIGNNESS.  ``_belongs_elsewhere`` keeps a module's own declaration
      from ever being rerouted, including the degenerate import-from-self.

    Both checks are era-agnostic (F1 row 29): ``is_declared_predicate`` is
    the class's ``len(_fields) == arity`` today and ``_belongs_elsewhere``
    reads the class's ``_row`` through ``resolve_predicate_row`` -- the same
    two reads this made directly -- and each answers for a mangled atom too.

    NOT a scan of ``module_dict.values()`` by ``__name__`` (roborev job 78,
    finding 1): that also matches a class reached by a plain Python import, a
    ``-specialize`` target, or anything another rewrite pass left in the dict,
    none of which is an ``-import_from``.
    """
    bound = _imported_binding(origins, functor, arity)
    if bound is None or not is_declared_predicate(bound, arity=arity, db=db):
        return None
    return bound if _belongs_elsewhere(bound, db, arity) else None


def _lock_static_predicates(db) -> int:
    """Load step 7: lock every static predicate this Database OWNS; return
    how many rows it locked.

    A locked row is what refuses a runtime ``assertz``/``retract`` on a
    static procedure (``database.write_refusal`` reads ``row.locked``), so a
    selector that quietly selects nothing leaves every static predicate
    mutable with no error anywhere.  That is why the population is
    ``db.owned_keys()`` and not the module dict.  This loop used to walk
    ``module_dict.values()`` filtering on ``isinstance(obj, PredicateMeta)``,
    which selects nothing once a predicate's module binding is a mangled
    atom (todo/the-lock-loop-stops-selecting-after-the-flip-2026-09-24.md).

    Measured over the house suite (3641 module loads, 2026-09-24) against
    that walk, the store-keyed population differs in three ways, each a
    correction:

    * an IMPORTED row is not locked here.  205 imported static rows were
      already locked by their owner's own step 7; the one that was not is a
      ``-dynamic`` predicate, which the walk then locked -- asking
      ``is_dynamic`` of the IMPORTER's database, which never holds the
      owner's declaration -- so after a module imported it, even the owner's
      own ``assertz`` was refused.
    * an owned static row whose name is bound as an ATOM (a name that is
      also a data atom) is locked; the walk never saw it.
    * an owned static row is locked even when the class bound under its
      name carries a different row; the walk locked that other row instead.

    Locking an imported row is its OWNER's job alone.  An owner that never
    ran this step -- rows built directly in Python rather than loaded
    through ``compile_module`` -- is no longer locked as a side effect of
    some module importing it.
    """
    locked = 0
    for key in db.owned_keys():
        if db.is_dynamic(*key):
            continue
        db.row(*key).locked = True
        locked += 1
    return locked


def _refuse_foreign_writes(db, predicate_nodes: list, module_dict: dict,
                           origins: dict, author: str,
                           module_name: str) -> None:
    """Refuse the LOAD, before it writes anything, if the gate would refuse
    any one of the predicates it is about to write.

    One question per ``(functor, arity)``, asked of the same rows the write
    itself would touch (``Database.refusal_for`` shares its blast-radius
    definition with ``Database.mutate``).  See step 3d.
    """
    checked: set[tuple[str, int]] = set()
    for pred_node in predicate_nodes:
        functor, arity = head_key(pred_node.head)
        if (functor, arity) in checked:
            continue
        checked.add((functor, arity))
        pred_cls = _local_binding(module_dict, functor)[0]
        pred_cls = _load_through(pred_cls, origins, functor, arity)
        exc = db.refusal_for(
            functor, arity, author=author, kind=WRITE_LOAD_CLAUSES,
            detail=_LOAD_SITES[WRITE_LOAD_CLAUSES], through=pred_cls,
        )
        if exc is not None:
            raise _redefinition_error(
                exc, functor, arity, pred_cls, origins, module_name,
                module_dict, db=db,
            )
        refused = _implements_an_imported_declaration(
            origins, module_dict, functor, arity, module_name, author)
        if refused is not None:
            raise refused


def _implements_an_imported_declaration(origins: dict, module_dict: dict,
                                        functor: str, arity: int,
                                        module_name: str,
                                        author: str = "<load>"):
    """The load error for clauses this module writes against a predicate it
    ``-import_from``'s from ANOTHER module -- or ``None``.

    A predicate has exactly one defining module, and a LOAD may not add
    clauses to another module's predicate.  Before 2026-09-24 the gate let
    such a write through wherever the exporter's row held nothing a load had
    written, and step 4 then MOVED the shared class off the exporter's row
    onto this module's (the "vocabulary-implements" idiom, DROPPED by
    operator ruling --
    ``todo/done/vocabulary-implements-steal-has-no-row-form-2026-09-24.md``).
    After the PredicateMeta flip there is no class to move, so it would have
    stopped answering silently; and where the exporter's row held runtime
    clauses, the move already lost them silently (round-3 review).

    Asked AFTER the gate (the caller checks ``Database.refusal_for`` first),
    so a row a load wrote that still holds clauses keeps the existing clobber
    refusal and its message.  Everything else that reaches here is refused,
    with a message for the exporter's actual shape:

    * a PYTHON module (not a loaded Clausal module) exporting a predicate
      class -- a ``PredicateMeta`` class statement or metaclass call (the
      retired ``make_predicate``'s shape): the
      class was created in Python, so no Clausal module owns it;
    * clause-free and never written by a load -- a declaration-only export
      (NO row post-flip, a private detached row today) or an empty
      ``-dynamic`` one: the exporter ONLY DECLARES it;
    * a ``-dynamic`` row holding clauses asserted at RUNTIME (no load
      source): assert from here instead (it lands on the owner's row), or
      define a predicate of this module's own;
    * a row a load wrote, since emptied: the clobber diagnostic, through
      ``_redefinition_error`` so it reads exactly like the gate's own
      clobber refusal (gate line included).

    *author* is the load's author, for that gate line.

    Keyed on the binding's ARITY-EXACT predicate, never on class identity:
    ``is_declared_predicate`` answers for a class today and a mangled handle
    after the flip, and it is arity-strict in both, so a same-spelling
    import at ANOTHER arity is not this predicate -- that is a local
    predicate sharing a name, and it loads.

    Pure and pre-write: step 3d calls it from the dry run, before the write
    loop touches anything.  Step 4's clause install relies on it: after this
    pass no load binds another module's predicate to its own row.
    """
    origin = origins.get(functor)
    if origin is None or not _imported_at(origins, functor, arity):
        return None
    exporter, bound = origin
    if bound is None or _is_self_import(exporter, module_name, author):
        return None
    # ONE arity source with ``is_foreign_class_at_other_arity`` (step 4,
    # ``_load_through``): the bound ROW's arity for a class on a real row.
    if not is_bound_predicate_at(bound, arity):
        return None
    local = module_dict.get(functor)
    if (local is not None and local != bound
            and is_bound_predicate_at(local, arity)):
        # The canonical spelling is bound to a predicate of THIS module, not
        # to the import: an aliased ``-import_from(m, [alias(f, G)])`` leaves
        # ``f`` free, and a local ``f/N`` then keeps its own predicate (the
        # rule ``Database.adopt_row`` states for rows; pinned by
        # ``test_a_local_definition_wins_a_clash_with_an_aliased_import``).
        # The gate resolves the head the same way -- ``module_dict`` first.
        return None
    imported_as = [name for name, (mod, b) in origins.items()
                   if mod == exporter and b == bound and name != functor]
    imported_as = imported_as[0] if imported_as else None
    row = resolve_predicate_row(bound, arity=arity)
    from clausal import import_diagnostics as diag  # noqa: PLC0415
    if row is not None and row.detached:
        # A class's PRIVATE detached row is no Clausal row at all: whatever
        # it holds (a Python-made class asserted into before any bind), no
        # exporter's Database has this predicate.
        row = None
    if row is not None and row.source is not None:
        # A load wrote this row; its clauses were retracted since (the gate
        # refuses it outright while it still holds any).  Same text as the
        # gate's own clobber refusal.
        owner = row.source[1]
        gate = refusal_error(
            functor, arity, author, WRITE_LOAD_CLAUSES,
            f"it is owned by {owner}; a load may not add clauses to another "
            f"module's predicate",
            channel=_LOAD_SITES[WRITE_LOAD_CLAUSES],
        )
        return _redefinition_error(gate, functor, arity, bound, origins,
                                   module_name, module_dict)
    if row is not None and row.clauses:
        return SyntaxError(diag.describe_imported_runtime_dynamic_implemented(
            functor, arity, module_name, exporter, len(row.clauses),
            imported_as=imported_as,
        ))
    # (A predicate CLASS made in a Python module had its own message here;
    # the class was deleted at W4b-3 slice 7, and a Python module supplies a
    # predicate only as a ``_get_dispatch`` object, which is no declaration.)
    return SyntaxError(diag.describe_imported_declaration_implemented(
        functor, arity, module_name, exporter, imported_as=imported_as,
    ))


def _is_self_import(exporter: str, module_name: str, author: str) -> bool:
    """Is this ``-import_from`` the module importing ITSELF?

    Decided by the identity the gate keys ownership on (``write_refusal``
    rule 1): the canonical SOURCE PATH, not the name.  One file compiles
    under two module names in one process (a dotted import and a private
    ``_clausal_test_*`` name), so the raw ``-import_from`` string can name
    this very file under its other name.  The exporter is resolved the way
    the import resolved it (``_resolve_module``); a module that cannot be
    resolved, or has no source path, is compared by name only.
    """
    if exporter == module_name:
        return True
    try:
        mod = _resolve_module(exporter)
    except ImportError:
        return False
    path = module_source_path(mod)
    return path is not None and path == author


_LOAD_SITES = {
    WRITE_LOAD_CLAUSES: "compile_module step 4",
    WRITE_LOAD_DISPATCH: "compile_module step 5",
}


def _local_binding(module_dict: dict, functor: str, arity=None):
    """``(binding, declared)`` for the binding a load write of *functor*
    goes THROUGH when this module itself holds the name: the module's own
    predicate HANDLE (``$declare_head``, W4b-3 slice 5 -- where the
    rewriter's class used to be; *declared* is ``declared_head``'s
    ``(functor, fields, site)``).  ``(None, None)`` otherwise, and
    ``_load_through`` falls back to an ``-import_from`` of the name.  The ONE
    rule step 3d and step 4 share."""
    binding = module_dict.get(functor)
    # The declaration AT *arity* when the body made one there (a name may
    # have several, operator ruling 2026-09-29), else the name's first.
    declared = (declared_head(module_dict, binding, arity)
                if arity is not None else None)
    if declared is None:
        declared = declared_head(module_dict, binding)
    if declared is not None:
        return binding, declared
    return None, None


def _load_through(pred_cls, origins: dict, functor: str, arity=None):
    """The ``through=`` a load write of ``functor/arity`` hands the gate: the
    module's own binding for the name, else the ``-import_from`` binding.

    Operator ruling 2026-09-24: a local ``p/2`` beside an imported ``p/1``
    LOADS -- name and arity make a different predicate.  ``through=``
    resolves a handle at the written arity, so a's ``p/1`` is never in the
    blast radius.  (An imported CLASS at another arity was dropped here,
    reading *db* and *arity*, until W4b-3 slice 7 deleted the class.)
    """
    return pred_cls if pred_cls is not None else _imported_binding(
        origins, functor, arity)


def _imported_binding(origins: dict, functor: str, arity=None):
    """The predicate an ``-import_from`` bound for *functor* -- a class today,
    a mangled atom after the flip -- or ``None``.

    Used to hand the mutation gate the shared predicate a write would land on
    when ``module_dict.get(functor)`` finds nothing — which is exactly the
    ALIASED import (identity todo instance 3): the predicate is in the module
    dict under its alias, so the functor a clause head compiles to reaches
    nothing, and the write went unexamined while step 5 replaced the shared
    dispatch anyway.

    ``_import_from_origins`` already filtered the value to a declared
    predicate, so this is a lookup.  Every consumer is era-agnostic (F1 row
    29): ``through=`` resolves either shape, ``_imported_binding_by_
    canonical_name`` reads it through the resolvers, and the redefinition
    diagnostic reads its row through ``resolve_predicate_row``.
    """
    origin = origins.get(functor)
    if origin is None or not _imported_at(origins, functor, arity):
        return None
    return origin[1]


@contextlib.contextmanager
def _load_gate(db, functor: str, arity: int, author: str, kind: str,
               pred_cls, origins: dict, module_name: str, module_dict: dict):
    """Open the mutation gate for a load-time write, translating a refusal
    into this channel's ``SyntaxError``.

    The POLICY is the gate's — this channel keeps none of its own (P3-3 Task
    3; the pre-pass that used to sit at step 3c is deleted).  What survives
    here is the DIAGNOSTIC: "you cannot write this" alone leaves the author
    with a rule and nowhere to put it, so the gate's refusal line is wrapped
    in ``describe_imported_predicate_redefinition``'s account of what is
    about to be lost, who wrote it, and where the clause could legitimately
    go.  The gate line rides along at the end, so all four channels say the
    same thing about the same policy.

    ``-import_from`` binds the exporter's predicate CLASS, and the write
    would land on it: extending instead is not a fix that can be made
    correct here, because ONE dispatch is compiled from ONE clause list
    against ONE ``globals_``, so a merged list would compile the other
    module's clause bodies — written against its ``-private`` atoms and its
    imports — in this module's scope.
    """
    # ``detail`` names the SITE, not the module: it leads the refusal line
    # ("compile_module step 4: <path> may not write f/1: ...") and lands in
    # the row's write stamp, where the author already carries the file.
    ctx = db.mutate(functor, arity, author=author, kind=kind,
                    detail=_LOAD_SITES.get(kind, kind), through=pred_cls)
    try:
        row = ctx.__enter__()
    except LogicException as exc:
        raise _redefinition_error(
            exc, functor, arity, pred_cls, origins, module_name, module_dict,
            db=db,
        ) from None
    try:
        yield row
    except BaseException as exc:  # noqa: BLE001 — re-raised below
        if not ctx.__exit__(type(exc), exc, exc.__traceback__):
            raise
    else:
        ctx.__exit__(None, None, None)


_CLASHING_DIRECTIVES = ("dynamic", "discontiguous", "table", "shallow",
                        "meta_predicate")


def _imported_indicators(module_items: list) -> dict:
    """``{(local_name, arity): (directive_text, owner, kind)}`` for every
    predicate indicator an ``-import_from`` of a CLAUSAL module brings.

    *kind* is ``"data"`` (a field-carrying export entry, R6/R6b),
    ``"dynamic"`` (a dynamic procedure) or ``"static"`` (any other
    procedure).  The arities are the OWNER's for the imported spelling
    (``Database.declared_arities_for``); an import names a predicate but
    carries no arity.  A Python module (``py.json``) has no Database and
    brings no indicator."""
    from clausal.logic.predicate import namespace_db  # noqa: PLC0415
    found: dict = {}
    for item in module_items:
        if not isinstance(item, ImportFromItem):
            continue
        try:
            mod = _resolve_module(item.module)
        except ImportError:
            continue
        owner_db = namespace_db(vars(mod))
        if owner_db is None:
            continue
        for name_spec in item.names:
            if isinstance(name_spec, tuple):
                spelling, local = name_spec
                text = f"-import_from({item.module}, [alias({spelling}, {local})])"
            else:
                spelling = local = name_spec
                text = f"-import_from({item.module}, [{spelling}])"
            selected = _selected_arities(item, local)
            for arity in owner_db.declared_arities_for(spelling):
                if selected is not None and arity not in selected:
                    continue            # D20: not imported at this arity
                if owner_db.declared_kind(spelling, arity) == "data":
                    kind = "data"
                else:
                    row = owner_db.row(spelling, arity)
                    kind = ("dynamic" if row is not None and row.dynamic
                            else "static")
                found.setdefault((local, arity), (text, item.module, kind))
    return found


def _local_procedure_declarations(module_items: list,
                                  predicate_nodes: list) -> dict:
    """``{(name, arity): [description, ...]}`` for every procedure this file
    declares itself: ``-dynamic``/``-discontiguous``/``-table``/``-shallow``/
    ``-meta_predicate`` directives (listed first -- they are the explicit
    declaration) and clauses."""
    found: dict = {}
    for item in module_items:
        if isinstance(item, DirectiveItem) and item.name in _CLASHING_DIRECTIVES:
            for spec in item.specs:
                functor, arity = spec[0], spec[1]
                found.setdefault((functor, arity), []).append(
                    f"-{item.name}({functor}/{arity})")
    for node in predicate_nodes:
        functor, arity = head_key(node.head)
        found.setdefault((functor, arity), []).append(
            f"(clauses for {functor}/{arity})")
    return found


def _first(declarations: list, *directives: str) -> "str | None":
    return next((d for d in declarations
                 if any(d.startswith(f"-{name}(") for name in directives)),
                None)


def _import_clash(kind: str, declarations: list) -> "str | None":
    """The local declaration that clashes with an import of *kind*, or
    ``None`` -- the narrowed rule (operator ruling 2026-09-26): refuse only
    what would be silently unreachable or IGNORED, allow only what takes
    effect.

    * a DATA import: every local declaration (the import rebinds the name
      after the body runs, so the local procedure is unreachable);
    * a STATIC procedure import: ``-dynamic``, ``-shallow`` and
      ``-meta_predicate`` (ignored -- the owner's row answers, this module
      compiles only its own rows, and ``meta_predicate_specs`` reads an
      adopted row's owner);
    * a DYNAMIC procedure import: ``-shallow`` and ``-meta_predicate`` (the
      same), and ``-table`` where a local ``-dynamic`` is present (it makes
      ``_refuse_untablable_target`` step aside, and the table would be
      ignored -- roborev 207).  The local ``-dynamic`` itself is the
      assert-through idiom, and takes effect.

    Accepted: ``-discontiguous`` on a procedure import (pinned).  Left to the
    older refusals, with their own messages, for a PROCEDURE import only:
    clauses against it are refused by the load gate at step 3d, which runs
    BEFORE this check; ``-table`` on it with no local clauses and no local
    ``-dynamic`` gets ``None`` here on purpose, so the load goes on to step
    6's ``_validate_directive_targets``, whose refusal names the owner.
    Against a DATA import every local declaration, a lone ``-table``
    included, is refused here (the first bullet)."""
    if kind == "data":
        return declarations[0]
    if kind == "static":
        return _first(declarations, "dynamic", "shallow", "meta_predicate")
    found = _first(declarations, "shallow", "meta_predicate")
    if found is None and _first(declarations, "dynamic") is not None:
        found = _first(declarations, "table")
    return found


def _import_local_clashes(module_items: list, predicate_nodes: list) -> list:
    """Every clash :func:`_import_clash` refuses, as ``(name, arity,
    declaration, import_text, owner, kind)``, in indicator order.  The one
    copy of the rule: the load refusal and the census tool
    (``tools/import_local_clash_census``) both call this."""
    imported = _imported_indicators(module_items)
    if not imported:
        return []
    local = _local_procedure_declarations(module_items, predicate_nodes)
    clashes = []
    for key in sorted(set(imported) & set(local)):
        text, owner, kind = imported[key]
        declaration = _import_clash(kind, local[key])
        if declaration is not None:
            clashes.append((key[0], key[1], declaration, text, owner, kind))
    return clashes


_IMPORT_KIND_TEXT = {
    "data": "a DATA functor (a term constructor with no clauses), so the "
            "local procedure would be unreachable",
    "static": "a static procedure, so the local declaration would be ignored "
              "(its clauses and properties are the owner's)",
    "dynamic": "a dynamic procedure, so the local declaration would be "
               "ignored (only a local -dynamic of it, which lets assertz add "
               "to the owner's predicate, and -discontiguous are accepted)",
}


def _refuse_import_local_clashes(module_items: list, predicate_nodes: list,
                                 module_name: str) -> None:
    """Refuse a load that imports a predicate indicator and ALSO declares it
    here where the local declaration would be silently unreachable or
    ignored (operator ruling 2026-09-26, in the spirit of ISO 13211-2: a
    local definition that clashes with an import is an error; narrowed the
    same day, see :func:`_import_clash`).

    Before this the local declaration was never reached: ``_process_imports``
    rebinds each imported name AFTER the module body ran, so a call to a
    local ``-dynamic(edge/2)`` beside an imported ``edge`` reached the import
    instead (an ``existence_error`` for a DATA import, the owner's clauses
    for a static procedure import) where ISO's clause-less dynamic procedure
    fails.

    By indicator, like Scryer: a local ``edge/3`` beside an imported
    ``edge/2`` is a different predicate and loads.  An aliased import
    ``alias(edge, e)`` clashes on its LOCAL name ``e``."""
    clashes = _import_local_clashes(module_items, predicate_nodes)
    if not clashes:
        return
    name, arity, declaration, text, owner, kind = clashes[0]
    raise SyntaxError(
        f"{module_name} declares {name}/{arity} locally ({declaration}), "
        f"but it also imports {name}/{arity} from {owner} ({text}), where it "
        f"is {_IMPORT_KIND_TEXT[kind]}.  A predicate cannot be both imported "
        f"and defined in the same module.  Either remove {name} from the "
        f"-import_from list to define {name}/{arity} here, or drop the local "
        f"declaration to use {owner}'s; to keep both, import it under "
        f"another name (alias({name}, other)).")


def _redefinition_error(exc, functor: str, arity: int, pred_cls,
                        origins: dict, module_name: str,
                        module_dict: dict, db=None) -> SyntaxError:
    """The load channel's surface exception for a gate refusal."""
    gate_line = exc.message or ""
    origin = origins.get(functor)
    # P1 (spec 2026-09-17 §2.2), simplification: *pred_cls* arrives already
    # resolved.  Both ``_load_gate`` call sites pass either step 4's
    # isinstance-guarded class or ``_imported_binding``'s result, which is a
    # declared predicate (class or mangled atom) or ``None`` — so a type test
    # here would be a ``None`` check in a type test's clothing.
    if origin is None or pred_cls is None:
        return SyntaxError(gate_line)
    exporter_name = origin[0]
    from clausal.import_diagnostics import (  # noqa: PLC0415
        describe_imported_predicate_redefinition,
    )
    described = describe_imported_predicate_redefinition(
        functor, arity, module_name, exporter_name,
        resolve_predicate_row(pred_cls, arity=arity, db=db),
        exporter_module=module_dict.get(exporter_name),
    )
    return SyntaxError(f"{described}\n  {gate_line}")


def _validate_directive_targets(module_items: list, db: Any, module_dict: dict) -> None:
    """A12-F003: reject a -table/-discontiguous/-shallow directive whose target
    predicate is never defined (or defined only at a different arity).

    A one-character typo in such a target silently forfeits the
    termination/dedup guarantee the author explicitly asked for (the predicate
    just runs untabled). The check runs after all clauses are collected, so
    forward declaration stays legal. ``-dynamic`` is exempt — it mints its own
    empty predicate (A12-F005) and a clause-less dynamic predicate is legit
    ISO. A target that is a declared predicate binding (e.g. an imported or
    -private-declared predicate's handle) also counts as defined.

    ``-table`` is held to a stricter standard than its two siblings, because
    unlike them it is not a property of *this* module's view of the predicate
    but of the dispatch function the predicate's own module compiled.  Step 6
    wraps the predicates this module compiled; a target this module did not
    compile is marked tabled in this module's database and then never wrapped
    anywhere — the author asked for memoisation and termination and got neither,
    with no diagnostic at all.  So a ``-table`` target must be a predicate this
    module compiles: one with clauses here, or a ``-dynamic`` one that will get
    them.  See ``todo/done/
    tabling-lifecycle-gaps-rewrap-and-cross-module-table.md`` for why wrapping
    the foreign class from here instead was rejected (it is a shared object: the
    defining module and every other importer would get tabling they did not ask
    for, keyed into this module's table store)."""
    _checked = ("table", "discontiguous", "shallow")
    _specialize_aliases = {
        item.new_name for item in module_items
        if isinstance(item, SpecializeItem)
    }
    for item in module_items:
        if not isinstance(item, DirectiveItem) or item.name not in _checked:
            continue
        for functor, arity in item.specs:
            if db.clauses_for(functor, arity):
                continue
            if item.name == "table":
                _refuse_untablable_target(
                    functor, arity, db, module_dict, _specialize_aliases,
                )
                continue
            # P1 2026-09-17: this one does NOT route to ``db.row``.  A
            # predicate DECLARED here and given no clauses (``-private([p(X,
            # Y)])`` plus a directive naming it) has a class in the module
            # dict and NO ROW at all — measured — so the row test would refuse
            # a load this accepts today, and the docstring above promises the
            # opposite.  "Declared at module level" is the spec §4 question,
            # not one a row can answer yet.
            if db.row(functor, arity) is not None:
                continue           # declared here at this arity (its row exists), or adopted by -import_from
            # P4 prerequisite: reached only for a binding with NO row -- a
            # predicate visible through a plain Python import (or, post
            # W4b-2d, a mangled handle bound directly, with no row either).
            # is_declared_predicate is era-agnostic (W4b-2b) and already
            # asks the identical question this used to spell out by hand:
            # a PredicateMeta CLASS at exactly this arity.
            if is_declared_predicate(module_dict.get(functor), arity=arity,
                                     db=db):
                continue
            near = sorted({a for (f, a) in db._clauses if f == functor})
            hint = (f"; predicate {functor} is defined at arity/arities {near}"
                    if near else f"; predicate {functor} is never defined")
            raise SyntaxError(
                f"-{item.name}({functor}/{arity}): target predicate "
                f"{functor}/{arity} is not defined in this module{hint}"
            )


def _refuse_untablable_target(
    functor: str,
    arity: int,
    db: Any,
    module_dict: dict,
    specialize_aliases: set,
) -> None:
    """Raise unless ``-table(functor/arity)`` can actually be honoured.

    Reached only for a target with no clauses in this module's database.  A
    ``-dynamic`` target is fine — it compiles here (to the always-fail
    trampoline if nothing is asserted yet) and gets wrapped like any other.
    Everything else is a directive this pipeline cannot honour, and the three
    shapes it comes in want three different remedies, so name the shape."""
    if db.is_dynamic(functor, arity):
        return

    # P1 2026-09-17: like its sibling in ``_validate_directive_targets``, this
    # stays on the class.  ``is_pred`` chooses BETWEEN refusals, and the three
    # shapes want three different remedies; measured over the suite,
    # ``db.row(functor, arity) is not None`` disagrees with this test on 3 of
    # the 8 targets that reach here (``ghost/2``, ``solve_tiny/1``,
    # ``solve_count_tabled/2`` — all declared, none with a row), so rerouting
    # would replace the accurate "declared but has no clauses" with "never
    # defined".
    # ``is_pred`` is the F2 question and the row/owner reads below are F1/F4
    # (W4b-2d R6, fix I): all three era-agnostic, so a HANDLE binding gets
    # the same refusal a class does.  They used to read ``cls._row`` and
    # ``cls.__module__`` directly, which a handle does not have.  All three
    # take the Q0 ``db=`` hint.
    binding = module_dict.get(functor)
    is_pred = is_declared_predicate(binding, arity=arity, db=db)

    if functor in specialize_aliases:
        # P3-3 Task 7 retired the reason this refusal used to give -- "-specialize
        # compiles it against a database of its own that no -table directive
        # reaches" -- because that database is gone: a specialized predicate is
        # now a row in THIS one, installed through the mutation gate at step 6b.
        # The refusal is KEPT (Task 7 relocates state; it does not get to lift a
        # refusal on an unmeasured guess) and its reason narrowed to what is
        # still true: the specializer compiles and installs the alias's dispatch
        # itself, at a later step than this directive's wrapper.  Lifting it is a
        # follow-up, and starts by verifying that a tabled -specialize alias
        # really tables.
        raise SyntaxError(
            f"-table({functor}/{arity}): {functor} is a -specialize alias, and "
            f"-table is not supported on one — the specializer compiles and "
            f"installs the alias's dispatch itself, after this directive's "
            f"wrapper.  Table the meta-interpreter or the object predicate "
            f"instead, or drop the directive."
        )

    # A read that must not mint: a binding still on NO row has no clauses.
    row = (resolve_predicate_row(binding, arity=arity, db=db)
           if is_pred else None)
    if row is not None and row.clauses:
        # The remedy names the target as its OWNER spells it: under an
        # aliased import (``alias(double, dbl)``) the local ``dbl`` is not a
        # name the owner knows (roborev 213).
        origin = predicate_owner_module(binding)
        spelling = predicate_binding_name(binding, db=db) or functor
        where = f" (defined in {origin})" if origin else ""
        into = f"into {origin}" if origin else "into the module that defines it"
        raise SyntaxError(
            f"-table({functor}/{arity}): {functor}/{arity} is defined in "
            f"another module{where}, and -table only tables the dispatch "
            f"function compiled by the module that declares it — the directive "
            f"would have no effect here.  Move -table({spelling}/{arity}) "
            f"{into}."
        )

    if is_pred:
        # An IMPORTED target (its handle names another module): the -dynamic
        # advice below would lead straight into the import/local clash
        # refusal (a local -dynamic plus -table beside an import), so point
        # at the owner instead.  Coordinator ruling 2026-09-26.
        owner = predicate_owner_module(binding)
        if owner and owner != db.module_name():
            spelling = predicate_binding_name(binding, db=db) or functor
            raise SyntaxError(
                f"-table({functor}/{arity}): {functor}/{arity} is imported "
                f"from {owner} and has no clauses here, and -table only "
                f"tables the dispatch function compiled by the module that "
                f"declares it.  Table it in its owner (-table({spelling}/"
                f"{arity}) in {owner}), or define {functor}/{arity} here "
                f"without importing it, or under a different name."
            )
        raise SyntaxError(
            f"-table({functor}/{arity}): {functor}/{arity} is declared but has "
            f"no clauses in this module, so there is nothing to table.  Give it "
            f"clauses here, or declare -dynamic({functor}/{arity}) if the "
            f"clauses arrive at runtime."
        )

    near = sorted({a for (f, a) in db._clauses if f == functor})
    hint = (f"; predicate {functor} is defined at arity/arities {near}"
            if near else f"; predicate {functor} is never defined")
    raise SyntaxError(
        f"-table({functor}/{arity}): target predicate {functor}/{arity} is "
        f"not defined in this module{hint}"
    )


def _process_directives(module_items: list, db: Any, module_dict: dict | None = None) -> None:
    """Apply directive metadata to the database.

    PredicateMeta retirement, P4 prerequisite (2026-09-18): a declared
    functor that a ``-discontiguous``/``-table``/``-shallow`` directive names
    as a PREDICATE at its declared arity gets its Database row here, so "is
    this name a predicate declared here, at this arity?" (spec 2026-09-14
    §4) is answerable by ``db.row(functor, arity)`` for that shape and no
    longer only by the class the declaration minted -- the limit P1
    measured.  Only that shape: a fielded ``-private([p(X)])`` entry ALONE
    may be a DATA functor (a term constructor with no clauses), and the
    Database must keep telling data from predicates (``test_predrow``, the
    P3-3 tagging) -- a row on a data functor makes ``cite(KEY)`` in a body
    read as a call.  The directive is what says "predicate".  ``-dynamic``
    already creates its row through ``mark_dynamic``.  The row is minted
    only for a DECLARED target, so ``_validate_directive_targets``'s typo
    check (an undeclared, clause-less target) is not made vacuous.
    """
    _directive_methods = {
        "dynamic": "mark_dynamic",
        "discontiguous": "mark_discontiguous",
        "table": "mark_tabled",
        "shallow": "mark_shallow",
    }
    declared: set[tuple[str, int]] = set()
    # For diagnostics only (``Database.declaration_origins``): a Database
    # with no real module name answers a placeholder, which is not a name
    # to put in user text.
    own_module = db.module_name()
    if own_module in ("<anonymous>", "<detached>"):
        own_module = None
    for item in module_items:
        if isinstance(item, (ModuleDeclItem, PrivateDeclItem)):
            is_module = isinstance(item, ModuleDeclItem)
            entries = item.exports if is_module else item.items
            for entry in entries:
                if isinstance(entry, tuple) and entry[1]:
                    declared.add((entry[0], len(entry[1])))
                    db.declare_functor(                              # P2 Task 2: the registry
                        entry[0], tuple(entry[1]),
                        origin=("module" if is_module else "private",
                                own_module, entry[0]))
    if module_dict is not None:
        # -import_from'd fielded names arrive through the exec-time carrier map
        # (``_make_import_signatures_update_ast``), keyed by LOCAL name.  The
        # owner module and the owner's spelling (an alias renames) come from
        # the -import_from items, for diagnostics.
        imported_from: dict[str, tuple[str, str]] = {}
        for item in module_items:
            if isinstance(item, ImportFromItem):
                for name_spec in item.names:
                    if isinstance(name_spec, tuple):
                        imported_from[name_spec[1]] = (item.module, name_spec[0])
                    else:
                        imported_from[name_spec] = (item.module, name_spec)
        from clausal.logic.cells import (  # noqa: PLC0415
            FUNCTOR_SIGNATURES_KEY, registry_signatures,
        )
        for name, value in (module_dict.get(FUNCTOR_SIGNATURES_KEY) or {}).items():
            # Every declared arity (a name declared at several has a
            # per-arity value, operator ruling 2026-09-29).
            for fields in (registry_signatures(value) or {}).values():
                if fields and db.declared_fields(name, len(fields)) is None:
                    owner = imported_from.get(name)
                    db.declare_functor(
                        name, tuple(fields),
                        origin=None if owner is None else ("import", *owner))
    for item in module_items:
        if isinstance(item, DirectiveItem):
            if item.name == "predicate_export":
                # dynfix 2026-09-23 (todo/dynamic-declarations-are-invisible-
                # to-arm-3-2026-09-22.md): a bare ``name/arity`` export entry
                # (R6b, ``term_rewriting._declare_predicate_export``) mints
                # its class with synthesized field names but, until now,
                # registered NOTHING on the Database -- ``declared_kind``
                # answered ``None``, indistinguishable from never declared
                # at all.  ``mark_predicate_export`` closes that without
                # minting a row (a row would be LOCKED below at step 7,
                # refusing the "an importer may legitimately implement it
                # later" write ``test_mutation_gate.py`` pins for
                # ``gv_free/1``).
                for functor, arity in item.specs:
                    db.mark_predicate_export(functor, arity)
                continue
            if item.name == "meta_predicate":
                # Operator ruling 2026-09-25: Scryer's meta_predicate/1.
                # Recorded BEFORE any clause compiles, so a caller compiled
                # later in this load (or an importer) sees the specs.
                for functor, arity, specs in item.specs:
                    db.mark_meta_predicate(functor, arity, specs)
                continue
            method_name = _directive_methods.get(item.name)
            if method_name is not None:
                method = getattr(db, method_name)
                for functor, arity in item.specs:
                    if item.name != "dynamic" and (functor, arity) in declared:
                        db.row(functor, arity, create=True)
                    method(functor, arity)


def _ambiguous_mi(mi_name: str, arities) -> RuntimeError:
    """Ruling QA's refusal, for every route that finds several arities."""
    arities = sorted(arities)
    return RuntimeError(
        f"-specialize: meta-interpreter '{mi_name}' is defined at "
        f"{len(arities)} arities "
        f"({', '.join(f'{mi_name}/{a}' for a in arities)}); "
        f"a meta-interpreter must have exactly one -- rename one of them")


def _meta_interpreter_row(db, module_dict: dict, mi_name: str, *,
                          refuse_ambiguous: bool
                          ) -> "PredRow | None":
    """The ROW of the meta-interpreter a ``-specialize`` names, or ``None``
    (two class-era arms that returned a bound ``PredicateMeta`` class went
    with the class at W4b-3 slice 7).

    F1 rows 32/33: found in the specializing module's OWN database -- a local
    MI or an ``-import_from``'d one (an adopted row) both answer there -- so
    it works whatever the module-dict binding looks like.
    ``predicate_arities`` is the lossless population; ``arities_for`` misses
    an adopted row (measured: empty for 99 of 100 lookups over the house
    suite, because the MIs are imported).

    In order:

    1. several arities with a ROW (clauses or not) is ambiguous: refused
       when *refuse_ambiguous* (ruling QA, 2026-09-24: the class route
       silently picked one; no measured case was ambiguous), otherwise
       ``None``;
    2. the one arity with a row -- with clauses, or a clause-less
       ``-dynamic`` MI, which the caller hands to ``analyze_mi`` so its
       "expected at least 2 clauses" refusal (spelled in one place) is what
       the author sees;
    3. failing that, a module-dict binding that denotes a predicate -- one
       bound by a plain Python import has no row here -- with the same
       ambiguity refusal over its owner's arities.  A mangled atom is
       resolved to its owner's row.
    """
    rows = {a: r for a in db.predicate_arities(mi_name)
            if (r := db.row(mi_name, a)) is not None}
    if len(rows) > 1:
        if refuse_ambiguous:
            raise _ambiguous_mi(mi_name, rows)
        return None
    binding = module_dict.get(mi_name)
    if rows:
        return next(iter(rows.values()))
    if not is_declared_predicate_name(binding, db=db):
        return None
    arities = predicate_arities_for(binding, db=db)
    if len(arities) > 1:
        if refuse_ambiguous:
            raise _ambiguous_mi(mi_name, arities)
        return None
    if arities:
        return resolve_predicate_row(binding, arity=next(iter(arities)),
                                     db=db)
    return None


def _preregister_specializations(
    module_items: list,
    module_dict: dict,
    db: Any,
) -> None:
    """Pre-register specialized predicates for -specialize directives.

    Registers each target's empty ROW and binds its HANDLE (no clauses, no
    dispatch) so that later clauses can reference the specialized predicate
    by name during compilation at Step 5.  (It minted empty PredicateMeta
    classes until W4b-3 slice 4.)
    """
    from clausal.logic.specialization import analyze_mi, _specialized_fields

    for item in module_items:
        if not isinstance(item, SpecializeItem):
            continue

        # At step 1c only an IMPORTED MI has clauses; a local one is
        # skipped here and specialized at step 6b, exactly as before.
        mi_row = _meta_interpreter_row(db, module_dict, item.mi_name,
                                       refuse_ambiguous=False)
        if mi_row is None:
            continue  # Will error in _run_specialization

        # Analyze MI to get field names for the specialized predicate.
        # program_arg is auto-detected by analyze_mi from field names.
        try:
            pattern = analyze_mi(mi_row)
            fields = _specialized_fields(pattern)
        except Exception:
            continue  # Will error properly in _run_specialization

        # Register the empty predicate: a ROW and the HANDLE (W4b-3 slice 4c
        # -- it used to be a ``make_predicate`` class bound under the name,
        # which the flip then turned into this same handle).
        if item.new_name not in module_dict:
            from clausal.logic.predicate import (  # noqa: PLC0415
                mint_predicate_handle, register_handle_owner)
            try:
                module_dict[item.new_name] = mint_predicate_handle(
                    db, item.new_name)
                register_handle_owner(db)
            except ValueError:
                pass    # a db naming no module owns no handle; step 6b refuses
            # The declaration, so ``field_names_for`` answers from the NAME.
            # ``_install_specialized`` registers again later through
            # ``register_signature``; both write the same tuple.
            db.declare_functor(item.new_name, tuple(fields))
            # Ruling QB (2026-09-24): mint the ROW now.  A declared functor
            # with no row is DATA to ``declared_kind``, so between here and
            # step 6b every reference to the target read as data -- today
            # the class hid that; after the flip nothing would.  Scope: what
            # step 1c pre-registers at all, i.e. an IMPORTED MI.  A local
            # MI's target is not pre-registered (no clauses yet to analyse)
            # and has no class, row or declaration at step 2 on main either
            # (probed 2026-09-24), so the flip changes nothing for it.
            db.row(item.new_name, len(fields), create=True)


def _run_specialization(
    module_items: list,
    predicate_nodes: list,
    module_dict: dict,
    db: Any,
) -> None:
    """Process -specialize directives: evaluate source programs and run
    the specializer.  The MI pattern is auto-detected by ``analyze_mi()``.
    """
    from clausal.logic.specialization import analyze_mi, specialize_mi, specialize_mi_deep, specialize_mi_cpd
    from clausal.logic.solve import call
    from clausal.logic.variables import Var, deref, walk

    for item in module_items:
        if not isinstance(item, SpecializeItem):
            continue

        mi_row = _meta_interpreter_row(db, module_dict, item.mi_name,
                                       refuse_ambiguous=True)
        if mi_row is None:
            # P1 (spec 2026-09-17 §2.4): the diagnostic enumerates the
            # DATABASE's predicates — every container ``row()`` consults,
            # plus the rows adopted at ``-import_from`` — rather than the
            # classes that happen to sit in the module dict, so an imported
            # predicate is listed under the spelling this module uses for it.
            # The wording NAMES that population (final review minor 5 +
            # roborev L6): it used to say "module dict" while listing rows,
            # and it built the list from ``_rows``, which is lazily
            # materialised and so not quite the population it refuses
            # against.  ``Database.functors()`` is that population.
            raise RuntimeError(
                f"-specialize: meta-interpreter '{item.mi_name}': no "
                f"predicate of that name in this module's database "
                f"(available: {db.functors()})"
            )

        # Analyze the MI (auto-detects program_arg from field names).
        pattern = analyze_mi(mi_row)

        # The target's DECLARATION SITE is this directive's line, stamped on
        # its row (first stamp wins) so the specializer's construction error
        # can name it -- the ``registered by`` line the make_predicate class
        # carried (its ``_registered_at``) before W4b-3 slice 4.
        from clausal.logic.specialization import _specialized_fields  # noqa: PLC0415
        _target_row = db.row(item.new_name, len(_specialized_fields(pattern)),
                             create=True)
        _pos = getattr(item, "position", None)
        _path = module_source_path(module_dict)
        if _target_row.declared_at is None and _pos and _path:
            _target_row.declared_at = (_path, _pos[0])

        # Evaluate the source program.
        source_cls = module_dict.get(item.source_program)
        if source_cls is None:
            raise RuntimeError(
                f"-specialize: source program '{item.source_program}' "
                f"not found in module dict"
            )

        if is_declared_predicate_name(source_cls, db=db):
            # It's a predicate — call it to get the program list.
            # ``is_declared_predicate_name``, not ``is_mangled``: a ``-hide``
            # DATA atom is mangled too, and named as a source it must keep
            # getting the "must be a predicate or list" refusal below, not be
            # called and fail with an unrelated existence_error (measured on
            # the first cut of this change).  A mangled PREDICATE atom
            # (post-flip module_dict binding, F1 re-audit row 34) needs
            # no separate branch here: ``call()`` already demangles its
            # own-module handles and resolves the owning module itself (W4
            # boundary + the 2026-09-24 dangling-handle ruling), the same
            # infrastructure every other mangled-goal call site already
            # goes through — so handing it *source_cls* directly, exactly as
            # the class arm always has, is the whole migration.  Safe today:
            # ``module_dict`` holds only classes pre-flip, so no input can
            # reach this widened branch before the flip; this only starts
            # firing once one can.
            program_var = Var()
            program_data = None
            for _ in call(source_cls, program_var):
                program_data = walk(deref(program_var))
                break
            if program_data is None:
                raise RuntimeError(
                    f"-specialize: source predicate '{item.source_program}' "
                    f"returned no solutions"
                )
        elif isinstance(source_cls, list):
            program_data = source_cls
        else:
            raise RuntimeError(
                f"-specialize: source program '{item.source_program}' "
                f"must be a predicate or list, got {type(source_cls)}"
            )

        # Run the specializer (deep unfolding if depth > 0, CPD if cpd=True).
        #
        # P3-3 Task 7: ``db=db`` is what makes the specialized predicate THIS
        # module's predicate.  The specializer used to build a Database of its
        # own and drop it, so ``db.row(item.new_name, ...)`` stayed ``None``
        # and the only handle on the predicate was the class in
        # ``module_dict``; the row it now gets is registered, signed and
        # gate-stamped here beside the module's own predicates.
        if item.cpd:
            specialize_mi_cpd(
                pattern, program_data, item.new_name, module_dict,
                max_depth=item.depth or 10, db=db,
            )
        elif item.depth > 0:
            specialize_mi_deep(
                pattern, program_data, item.new_name, module_dict,
                max_depth=item.depth, db=db,
            )
        else:
            specialize_mi(
                pattern, program_data, item.new_name, module_dict, db=db,
            )

        # The specialized predicate is already compiled and installed
        # in module_dict by specialize_mi.  No need to inject into
        # predicate_nodes — it's already fully compiled.


def _locally_declared_names(module_items: list) -> frozenset[str]:
    """Names THIS module's own -module/-private/-hide/-import_from/
    -import_module directives legitimately bind.

    P3-1 Task 7 fix round 1 (Critical, review-caught): the strictness
    consumers below (and ``import_hook._make_intern_atom``'s dict-key
    path) used to treat ANY name already present in ``module_dict`` as
    "already resolved" -- but ``module_dict`` is pre-seeded at exec start
    (``module_dict.update(predicate_builtins)``, import_hook.py) with the
    ENTIRE process-wide atom pool, which accumulates every atom any
    earlier-loaded module in the same process ever declared or
    auto-accepted. That let strictness silently pass for a genuinely
    undeclared atom whenever ANY earlier module happened to share its
    spelling. Declaredness is a per-module compiler lint against THIS
    module's own declared vocabulary (§1b: "a pure compiler lint against
    the declared vocabulary — it no longer rides on Python name
    resolution") -- separate from, and not satisfied by, atom UNIFICATION
    identity being global by spelling (§1b/R2, deliberate, unchanged).
    This positive set is the fix: built from what THIS module's own
    ``module_items`` say, not from ``module_dict``'s ambient state, so a
    same-spelling declaration in a different module can no longer stand
    in for this module's own.

    ``global_atom/2``'s mint-on-demand mode (``clausal/logic/builtins/
    inspection.py``) also writes into the ``predicate_builtins`` pool, but
    at RUNTIME (inside a query), not at compile time -- irrelevant here on
    purpose: this set is built from module_items alone, so a pool write
    from a running query can never retroactively satisfy another module's
    compile-time strictness check either.
    """
    names: set[str] = set()
    for item in module_items:
        if isinstance(item, (ModuleDeclItem, PrivateDeclItem)):
            exports = (
                item.exports if isinstance(item, ModuleDeclItem) else item.items
            )
            for entry in exports:
                if isinstance(entry, str):
                    names.add(entry)
                elif isinstance(entry, tuple):
                    names.add(entry[0])
        elif isinstance(item, DirectiveItem) and item.name == "predicate_export":
            # An ISO ``name/arity`` entry in a -module/-private list (R6b):
            # declared vocabulary just like the field-carrying form, recorded
            # as a directive item rather than an export tuple because it
            # declares a PREDICATE, not a data functor's slot layout.
            names.update(functor for functor, _arity, *_ in item.specs)
        elif isinstance(item, HideDeclItem):
            names.update(item.items)
        elif isinstance(item, ImportFromItem):
            for name_spec in item.names:
                if isinstance(name_spec, tuple):
                    names.add(name_spec[1])  # local alias
                else:
                    names.add(name_spec)
        elif isinstance(item, ImportModuleItem):
            names.add(item.module.split(".")[0])
    return frozenset(names)


def _check_atoms_applied_as_functors(
    module_items: list,
    module_dict: dict,
) -> None:
    """Raise for an ``-import_from``'d ATOM that was applied with arguments.

    P3-3 Task 4 fix round 2 (O2).  ``term_rewriting`` bypasses its
    atom-applied-as-a-functor refusal for an imported name, because an
    imported FUNCTOR legitimately takes that shape and the rewrite cannot
    tell the two apart.  The deciding fact is whether the name carries a
    functor SIGNATURE — ``-import_from`` copies the owner's registry entry
    across under the local spelling for a functor and has nothing to copy for
    an atom — so ``functor_signature_for`` against this module's own
    namespace answers it, with no second source of truth introduced.

    The message was built at the call site, where its file and line are
    known; this pass only decides whether to raise it.
    """
    for item in module_items:
        if not isinstance(item, AtomAppliedAsFunctorItem):
            continue
        for name, message in item.sites:
            from clausal.logic.compiler.terms_to_ast import (  # noqa: PLC0415
                functor_signature_for,
            )
            if functor_signature_for(name, module_dict) is None:
                raise SyntaxError(message)


def _record_double_quotes_mode(module_items: list, db) -> None:
    """Record the ``DoubleQuotesMode`` item on *db* for the module's importers.

    The modes that governed at least one ``"..."`` literal; a file with no
    such literal reports the mode in force at its end, so an importer can
    still compare against it.
    """
    for item in module_items:
        if isinstance(item, DoubleQuotesModeItem) and db is not None:
            db.double_quotes_modes = frozenset(item.modes_used or (item.mode,))
            # current_prolog_flag(double_quotes, M) reports the mode in force
            # at the end of the file.
            if item.explicit:
                from clausal.logic.builtins.flags import apply_setting  # noqa: PLC0415
                apply_setting(db, "double_quotes",
                              getattr(item, "flag", "") or item.mode)
            return


def _apply_prolog_flag_directives(module_items: list, db) -> None:
    """Apply each ``-set_prolog_flag(F, V)`` directive, in file order.  The
    transformer validated them (``flags.check_setting``); ``double_quotes``
    never reaches here -- it is the compile-time ``-double_quotes`` mode."""
    from clausal.logic.builtins.flags import apply_setting  # noqa: PLC0415
    for item in module_items:
        if isinstance(item, DirectiveItem) and item.name == "set_prolog_flag":
            for name, value in item.specs:
                apply_setting(db, name, value)


def _double_quotes_modes_of_target(kind: str, target, module_dict: dict):
    """``(owner_name, modes)`` for a cross-mode site's callee, or ``(None,
    None)`` when the callee cannot be resolved at load -- an import that is
    not a predicate handle (a Python module's function, say), an owner with
    no Database, or one compiled before its Database recorded a mode.  A
    dotted base reaches here only when the transformer saw this file bind
    it with ``-import_module`` (``_import_module_bases``), so the global it
    names IS the module the goal runs against; a base bound by hosted Python
    -- possibly rebound at run time through ``seam.with_bases`` -- is never
    recorded as a site.  Never raises: the lint must not turn a working load
    into an error."""
    from clausal.logic.predicate import (  # noqa: PLC0415
        predicate_owner_module, namespace_db,
    )
    try:
        if kind == "imported":
            local_name, dotted = target
            # A predicate's binding is a mangled handle naming its owner; an
            # imported data FUNCTOR binds the plain atom, so its owner is the
            # module half of the ``-import_from`` key (``a.b.q`` -> ``a.b``).
            # Either way a module that is not a loaded .clausal module (a
            # ``py.*`` wrapper) has no Database and is not judged.
            owner = predicate_owner_module(module_dict.get(local_name))
            if owner is None:
                # The key holds the path AS WRITTEN; an aliased path
                # (``thailand`` -> ``clausal.modules.countries.thailand``)
                # resolves through the same resolver ``_process_imports``
                # used, so the module found is the one the import bound.
                owner = _resolve_module(dotted.rsplit(".", 1)[0]).__name__
            db = _db_for_module_name(owner) if owner else None
        else:
            base, chain = target
            obj = module_dict.get(base)
            for attr in chain[:-1]:
                obj = getattr(obj, attr, None)
            if obj is None:
                return None, None
            db = getattr(obj, "db", None)
            if db is None:
                db = namespace_db(getattr(obj, "__dict__", None))
            owner = db.module_name() if db is not None else None
    except Exception:  # noqa: BLE001 -- a lint never breaks a load
        return None, None
    if db is None:
        return None, None
    return owner, getattr(db, "double_quotes_modes", None)


def _lint_cross_mode_literals(module_items: list, module_dict: dict) -> None:
    """Warn for a goal-position seam literal whose callee's ``-double_quotes``
    mode differs from the host file's (``ClausalCrossModeLiteralWarning``).

    The sites were collected by ``EmbedTransformer._collect_cross_mode_sites``
    with the host's mode; the callee's mode is read off the owner's Database
    (``_record_double_quotes_mode``), which the ``-import_from`` /
    ``-import_module`` execution in Step 0 has just made reachable.  A
    callee whose literals were read under BOTH modes has no single mode to
    compare against and is not judged; neither is one that cannot be
    resolved at load.

    THE GAP, documented rather than closed: a ``--m.pred(...)`` whose base
    is bound at RUN time (``module = _RULE.get()`` inside a function --
    ``seam.with_bases``) has no module here.  A check at first call was
    priced and declined: by then the argument is a term, and a chars
    carrier reaching an atom-mode module is not evidence of a written
    ``"..."`` -- a string may be passed on purpose -- so the check would
    fire on working code.
    """
    from clausal.lint_warnings import ClausalCrossModeLiteralWarning  # noqa: PLC0415
    for item in module_items:
        if not isinstance(item, CrossModeLiteralSitesItem):
            continue
        for kind, target, literals, host_mode, location, goal, shown in item.sites:
            owner, modes = _double_quotes_modes_of_target(kind, target, module_dict)
            if not modes or len(modes) != 1:
                continue
            (target_mode,) = modes
            if target_mode == host_mode:
                continue
            quoted = ", ".join(f'"{text}"' for text in literals)
            plural = "s are" if len(literals) > 1 else " is"
            if host_mode == "chars":
                what = ("a STRING under this file's -double_quotes(chars), but "
                        f"`{shown}` is defined in module `{owner}`, whose "
                        f'-double_quotes(atom) reads "..." as an ATOM')
                remedy = ("write the atom with single quotes ("
                          + ", ".join(f"'{text}'" for text in literals)
                          + "), which is an atom in every mode")
            else:
                what = ("an ATOM under this file's -double_quotes(atom), but "
                        f"`{shown}` is defined in module `{owner}`, whose "
                        f'-double_quotes(chars) reads "..." as a STRING')
                remedy = ("declare -double_quotes(chars) in this file, or "
                          "pass the string as its char list")
            warnings.warn(ClausalCrossModeLiteralWarning(
                f"{location}: {goal}: the literal{plural} {quoted} {what}; "
                f"the goal compares a string with an atom and never "
                f"matches, and nothing raises. To send what `{shown}` "
                f"matches, {remedy}."
            ), stacklevel=2)


def _local_functor_arities(
    module_items: list, predicate_nodes: list,
) -> dict[str, set[int]]:
    """``{name: {arity, ...}}`` for every functor signature this FILE fixes.

    The same two facts ``term_rewriting._settle_atom_functor_sites`` reads --
    a clause head, or a ``-module``/``-private`` functor entry -- plus the
    ISO ``name/arity`` export spelling, which declares a predicate with no
    field list.  Read from the clause NODES rather than from ``module_dict``
    on purpose: an ``-import_from`` of the same spelling overwrites the
    module binding (``_process_imports``), so the binding cannot answer
    "does this file define ``name/N``" and the clause set can.
    """
    arities: dict[str, set[int]] = {}
    for pred_node in predicate_nodes:
        functor, arity = head_key(pred_node.head)
        arities.setdefault(functor, set()).add(arity)
    for item in module_items:
        if isinstance(item, (ModuleDeclItem, PrivateDeclItem)):
            entries = (item.exports if isinstance(item, ModuleDeclItem)
                       else item.items)
            for entry in entries:
                if isinstance(entry, tuple):
                    arities.setdefault(entry[0], set()).add(len(entry[1]))
        elif isinstance(item, DirectiveItem) and item.name == "predicate_export":
            for functor, arity in item.specs:
                arities.setdefault(functor, set()).add(arity)
    return arities


def _local_call_reroutes(
    module_items: list, predicate_nodes: list, module_dict: dict,
) -> dict[tuple[str, int], str]:
    """``{(dotted key, arity): local name}`` for call sites that mean LOCAL.

    P3-3 Task 5b, sub-shape 1.  Resolution is keyed on ``(name, arity)``: an
    imported ATOM has no arity-N meaning (ISO treats ``f`` and ``f/2`` as
    unrelated objects), so a local arity-N definition of the same spelling is
    what an applied ``f(...)`` in this file means -- nothing is ambiguous and
    nothing is shadowed.

    Three conditions, exactly the ruling's:

    (a) the name is one an ``-import_from`` remapped (this walks the same
        ``ImportFromItem``s ``term_rewriting._import_remap`` was built from,
        and rebuilds the identical dotted key);
    (b) this file establishes a functor signature for ``(name, N)`` itself --
        see ``_local_functor_arities``;
    (c) the imported binding carries NO functor signature.  That is the
        OWNER's fact, asked of the owner's namespace with the same
        ``functor_signature_for`` ``_check_atoms_applied_as_functors`` uses,
        so an imported FUNCTOR of arity N colliding with a local arity-N
        definition stays the genuine collision it is (unchanged by this
        pass, refused by the mutation gate at load as it was before).

    An EMPTY signature -- a zero-arity predicate class -- counts as no
    functor signature here: ``k/0`` and ``k/N`` are unrelated objects, so
    arity 0 is not a functor meaning AT ARITY N and there is nothing for it
    to block.  Fix round 1 (review): the difference is unobservable today.
    The shape it would decide -- a dual-declared /0 name in the owner plus
    ``k/N`` clauses in the importer -- never loads either way, because the
    owner owns ``k`` and the mutation gate refuses the importer's clauses
    (``_refuse_foreign_writes``); the only reachable route is a clause-free
    ``-private([k(A, B)])``, where blocking and not blocking agree.  Written
    this way because it is what the ruling means, not because a test
    separates the two.
    """
    if not any(isinstance(item, ImportFromItem) for item in module_items):
        # Fix round 1 (review, F2): the overwhelming majority of modules
        # ``-import_from`` nothing at all, and for those the whole pass is a
        # walk over every clause head and module item to build a table
        # nothing will read.  Condition (a) is the cheapest of the three and
        # gates the other two, so it is asked first.
        return {}
    from clausal.logic.compiler.terms_to_ast import (  # noqa: PLC0415
        functor_signature_for,
    )
    local_arities = _local_functor_arities(module_items, predicate_nodes)
    if not local_arities:
        return {}
    reroutes: dict[tuple[str, int], str] = {}
    for item in module_items:
        if not isinstance(item, ImportFromItem):
            continue
        owner_ns = getattr(module_dict.get(item.module), "__dict__", None)
        if owner_ns is None:
            continue
        for name_spec in item.names:
            if isinstance(name_spec, tuple):
                orig_name, local_name = name_spec
            else:
                orig_name = local_name = name_spec
            arities = local_arities.get(local_name)
            if not arities:
                continue                                    # (b) fails
            if functor_signature_for(orig_name, owner_ns):
                continue                                    # (c) fails
            dotted = f"{item.module}.{orig_name}"            # (a)
            for arity in arities:
                if arity > 0:
                    reroutes[(dotted, arity)] = local_name
    return reroutes


def _route_imported_atom_calls_to_local(
    module_items: list, predicate_nodes: list, module_dict: dict,
) -> None:
    """Re-point qualifying call sites from the import remap to the local name.

    P3-3 Task 5b, sub-shape 1.  ``term_rewriting`` cannot decide this at
    rewrite time: condition (c) is the OWNER's fact and the owner has not
    executed yet, exactly as for the atom-applied-as-a-functor check above.
    So the rewrite emits the remap optimistically and the decision is settled
    here, on the clause nodes, before clause compilation turns the reference
    into a dispatch.

    Only the FUNC of a body ``Call`` is re-pointed, and only the func: a bare
    reference to the same spelling in DATA position keeps the dotted key and
    therefore keeps answering with the imported atom -- which is what gives
    the two positions different globals keys, the thing a binding-level fix
    could not do.
    """
    reroutes = _local_call_reroutes(module_items, predicate_nodes, module_dict)
    if not reroutes:
        return
    from clausal.pythonic_ast.nodes import (  # noqa: PLC0415
        Call as CallNode, LoadName as LoadNameNode, Node as AstNode,
    )

    def _walk(obj) -> None:
        if isinstance(obj, AstNode):
            if (
                isinstance(obj, CallNode)
                and isinstance(obj.func, LoadNameNode)
                and not obj.kwargs
            ):
                local = reroutes.get((obj.func.name, len(obj.args)))
                if local is not None:
                    obj.func = LoadNameNode(
                        name=local, position=obj.func.position)
            for child in obj.children():
                _walk(child)
        elif isinstance(obj, (list, tuple)):
            for element in obj:
                _walk(element)

    for pred_node in predicate_nodes:
        body = getattr(pred_node, "body", None)
        if body is not None and body is not True:
            _walk(body)


def _route_other_arity_imported_calls_to_local(
    module_items: list, predicate_nodes: list, module_dict: dict, db=None,
) -> None:
    """Re-point an UNQUALIFIED call to an imported predicate at ANOTHER arity
    from the import remap's dotted key to the LOCAL name the file used.

    Operator ruling 2026-09-24 (closing the aliased-import leak,
    ``todo/done/aliased-import-other-arity-resolves-in-the-owner-2026-09-24.md``):
    importing ``numlist/1`` as ``nl`` grants that one arity under that one
    name.  ``nl(3, L)`` must resolve in THIS module under ``nl`` -- its own
    ``nl/2`` row, else a builtin ``nl/2``, else the arity refusal -- never
    ``alow``'s ``numlist/2``.  ``term_rewriting`` emits every reference to an
    imported spelling as ``LoadName("alow.numlist")``, and a dotted target
    is (correctly, for a QUALIFIED reference) resolved in the qualifier's
    module under that name; so the unqualified call has to leave the dotted
    key before ``globals_env`` sees it.

    Only the remap's own shape is touched: the FUNC of a body ``Call`` that
    is a ``LoadName`` of an ``-import_from`` dotted key.  A qualified
    ``alow.numlist(3, L)`` the author wrote does not compile to that shape
    (it yields no data-position ``LoadName`` target), so it keeps the
    qualifier's resolution.  Only arities the imported binding is NOT a
    predicate at are re-pointed -- the imported arity keeps the dotted key and
    its ``$disp_`` bake.  "Imported at" is ``predicate.binding_grants_arity``
    against the importing *db*, the same test in both eras: the owner's OTHER
    arities (one ``assertz``'d there, say) were not imported, even though a
    handle's owner would call itself a predicate at them.  Mirrors ``_route_imported_atom_calls_to_local``
    (the atom twin, P3-3 Task 5b).
    """
    spellings: dict[str, set[str]] = {}   # dotted key -> local names
    owner_names: dict[str, str] = {}
    for item in module_items:
        if not isinstance(item, ImportFromItem):
            continue
        for name_spec in item.names:
            if isinstance(name_spec, tuple):
                orig_name, local_name = name_spec
            else:
                orig_name = local_name = name_spec
            if is_declared_predicate_name(module_dict.get(local_name), db=db):
                dotted = f"{item.module}.{orig_name}"
                spellings.setdefault(dotted, set()).add(local_name)
                owner_names[dotted] = orig_name
    # Review round 5: one predicate imported under SEVERAL spellings
    # (``-import_from(alow, [numlist, alias(numlist, nl)])``) shares ONE
    # dotted key, and the remapped ``LoadName`` does not record which
    # spelling the author wrote -- so the key is AMBIGUOUS and must not be
    # re-pointed to whichever spelling the import list named last.  When the
    # unaliased spelling is among them it is used: the call then resolves
    # under the owner's own name in THIS module (a builtin under that name
    # answers ``numlist(3, L)``, as for any unaliased import).  Two or more
    # ALIASES and no unaliased spelling: not re-pointed at all.  Residual,
    # documented: in such a module an ALIASED spelling at another arity is
    # resolved under the unaliased name (or, with no unaliased spelling, in
    # the owner).  Recording the spelling in the remap is the full fix.
    reroutes: dict[str, str] = {}
    for dotted, names in spellings.items():
        if len(names) == 1:
            reroutes[dotted] = next(iter(names))
        elif owner_names[dotted] in names:
            reroutes[dotted] = owner_names[dotted]
    if not reroutes:
        return
    from clausal.pythonic_ast.nodes import (  # noqa: PLC0415
        Call as CallNode, LoadName as LoadNameNode, Node as AstNode,
    )

    def _walk(obj) -> None:
        if isinstance(obj, AstNode):
            if (
                isinstance(obj, CallNode)
                and isinstance(obj.func, LoadNameNode)
                and not obj.kwargs
            ):
                local = reroutes.get(obj.func.name)
                if local is not None and not binding_grants_arity(
                        module_dict.get(local), len(obj.args), db, local):
                    obj.func = LoadNameNode(
                        name=local, position=obj.func.position)
            for child in obj.children():
                _walk(child)
        elif isinstance(obj, (list, tuple)):
            for element in obj:
                _walk(element)

    for pred_node in predicate_nodes:
        body = getattr(pred_node, "body", None)
        if body is not None and body is not True:
            _walk(body)


#: Builtin GOAL names that are ATOMS in term position and so need no
#: declaration under strict atoms (operator ruling 2026-09-25).  ``true`` and
#: ``false`` are not here: they fold to ``True``/``False`` in the rewriter.
#: ``halt`` is a control construct with no builtin-table row, so the builtin
#: name check below does not see it; without it here a bare ``halt`` goal
#: (``q <- halt``) was refused as an undeclared atom.
BUILTIN_GOAL_ATOMS = frozenset({"fail", "halt"})


def _process_bare_atom_refs(
    module_items: list,
    module_dict: dict,
    module_name: str = "<module>",
) -> None:
    """Auto-accept undeclared bare atom references, binding the SPELLING
    itself (a plain ``str``, not a minted class — §1b/R2) into
    ``module_dict``, keyed the same way in the process-wide
    ``predicate_builtins`` pool so repeated auto-accepts of the same
    spelling (in this or another module) return the identical object.

    Implements rule 1.4 (global fallthrough) of GLOBAL_ATOMS_DEFAULT.md.
    Every bare ``LoadName`` fallthrough collected by the term-rewriting walker
    arrives here as a ``BareAtomRefs`` module item.  A name is skipped (left
    untouched) when any higher-precedence resolution rule already supplies
    it:

    * this module's own predicate HANDLE already sits in ``module_dict`` —
      bound by an in-file ``$declare_head`` statement (W4b-3 slice 5; it
      was a ``PredicateMeta`` class block), whether declared with fields or
      clause-head-only; it never leaks cross-module the way a plain atom
      str does (see below), so trusting ``module_dict`` for this shape is
      safe;
    * an already-bound object that is NOT the process-pool's exact
      self-mapped atom str for this name AND NOT the exact
      ``runtime_builtins`` entry for this name (P3-2 Task 8) — a genuine
      Python import (Step 0) or any other legitimately-bound value is
      trusted as before;
    * THIS module's own declared/imported vocabulary — see
      ``_locally_declared_names`` (P3-1 Task 7 fix round 1: -module,
      -private, -hide, -import_from, -import_module);
    * registered as a builtin in ``_BUILTINS`` / ``_DB_BUILTINS`` under any
      arity — these resolve through ``get_builtin_predicate`` later in the
      pipeline, and binding them here would shadow that lookup.

    P3-1 Task 7 fix round 1 (Critical, review-caught): a BLANKET
    ``if name in module_dict: continue`` used to stand in for all four
    reasons above at once — which was wrong for the plain-str atom shape
    specifically, because ``module_dict`` is pre-seeded at exec start with
    the ENTIRE process-wide ``predicate_builtins`` pool
    (``import_hook.py``), so an atom some OTHER, earlier-loaded module
    declared (and therefore ``setdefault``-installed into that pool) was
    indistinguishable from one THIS module legitimately declared itself.
    §1b is explicit that declaredness is "a pure compiler lint against the
    declared vocabulary — it no longer rides on Python name resolution" —
    separate from, and unaffected by, atom UNIFICATION identity being
    global by spelling (§1b/R2, deliberate, unchanged: the process-pool
    seed itself STAYS, it backs global predicate-class/atom-object
    resolution). The fix narrows the blanket check to the ONE shape that
    can actually carry pool leakage — a plain str equal to its own name
    AND still identical to the pool's current entry for that name — and
    requires THIS module's own declared/imported set to vouch for that
    shape; every other already-bound object (a real class, a Python
    import) is unaffected. ``global_atom/2``'s mint-on-demand mode also
    writes the pool, but only at query RUNTIME, long after this
    compile-time check — irrelevant here by construction.

    P3-2 Task 8 (pool split; closes todo/done/pythonic-ast-names-leak-into-
    strict-atom-namespace-2026-09-04.md): the Task 7 fix above narrowed the
    "trust it" default to exclude ONE leaked shape (a plain, self-mapped
    atom str from ``predicate_builtins``) but left a SECOND, differently-
    shaped leak open — ``module_dict`` is ALSO pre-seeded at exec start with
    ``runtime_builtins`` (see ``import_hook.py``'s pool-split comment), so a
    bare reference to an internal name like ``Add``/``Call``/``Match`` (a
    ``simple_ast.__all__`` node class) fell into the same "anything else,
    trust it" bucket Task 7 deliberately preserved for genuine classes and
    imports — a real class object, just not one THIS module ever declared.
    The fix generalizes the same identity discipline to this second shape:
    distrust an already-bound value that is identical to
    ``runtime_builtins``' entry for that name, unless THIS module's own
    declared/imported vocabulary vouches for it.

    Task 8 fix round 1 (RULING, reviewer-caught): round 1 scoped this
    distrust check to ``_SIMPLE_AST_NODE_NAMES`` (the ``simple_ast.__all__``
    classes specifically), reasoning that the todo's repro was entirely
    about that set and that ``INJECTED_RUNTIME_BUILTINS`` entries (``Var``,
    ``Undefined``, ...) were a separate, deliberate
    resolve-everywhere design. The reviewer proved this left the todo's
    "closes the whole CLASS of bug" promise undelivered: injecting a
    SYNTHETIC name into ``runtime_builtins`` reproduced the identical
    ``Add`` leak shape on an instance the narrow allowlist could not have
    anticipated, because a future ``INJECTED_RUNTIME_BUILTINS`` addition
    is by construction not in ``simple_ast.__all__``. The rule is now
    distrust-ANY-``runtime_builtins``-entry, with the resolve-everywhere
    exception moved to an explicit, reviewed allowlist —
    ``import_hook.STRICTNESS_EXEMPT_RUNTIME_NAMES`` (currently just
    ``Undefined``, with its one-line justification there) — so a future
    runtime binding fails LOUD by default instead of leaking SILENT.
    ``_SIMPLE_AST_NODE_NAMES`` is deleted: it is fully redundant under this
    general rule (every ``simple_ast.__all__`` name is, correctly, not in
    the exemption set).

    The collected set is naturally over-broad (it also contains predicate
    functor names and imported-utility names), but that over-collection is
    harmless: the skip rules above filter out every case except the
    genuinely undeclared bare-atom one.

    Phase 3 of GLOBAL_ATOMS_DEFAULT.md: if a ``StrictAtomsItem`` is present
    in ``module_items``, the global-fallthrough accept is disabled.  Names
    that would otherwise have been accepted are instead collected and
    reported as a single ``NameError`` with a diagnostic naming each
    offending atom and the file, and suggesting the five legitimate ways to
    declare or reach it (``-module``, ``-private``, ``-import_from``,
    qualified reference, ``global_atom/2``).

    Lazy import of ``predicate_builtins`` — ``clausal.import_hook`` depends
    transitively on this package, so a top-level import would create a cycle
    at package load time.
    """
    from clausal.import_hook import (
        predicate_builtins, runtime_builtins, STRICTNESS_EXEMPT_RUNTIME_NAMES,
    )
    from clausal.logic.builtins._registry import _BUILTINS, _DB_BUILTINS

    builtin_names = {name for (name, _arity) in _BUILTINS}
    builtin_names.update(name for (name, _arity) in _DB_BUILTINS)

    local_names = _locally_declared_names(module_items)

    strict_mode = any(
        isinstance(item, StrictAtomsItem) for item in module_items
    )
    implicit_mode = any(
        isinstance(item, ImplicitAtomsItem) for item in module_items
    )
    # Strict is the rule for every SOURCE file: undeclared bare atoms raise.
    # The loose (auto-mint) item is internal to the interactive profile (the
    # IPython cell transformer adds it); no directive produces it -- the
    # ``-implicit_atoms`` directive was REMOVED before 1.0 and is now a
    # load-time SyntaxError (term_rewriting).
    effective_strict = not implicit_mode
    if strict_mode:
        _warn_strict_atoms_deprecated()
    undeclared: list[str] = []

    for item in module_items:
        if not isinstance(item, BareAtomRefsItem):
            continue
        for name in item.names:
            existing = module_dict.get(name, _MISSING)
            if name in _module_constants(module_dict):
                # A declared constant's global is a VALUE, not evidence that
                # the name is a declared atom. Without this, `-constants(pi
                # = 5000)` alone would make a bare `pi` resolve to 5000 --
                # the very thing the operator's rule says a bare name never
                # does -- because the branch below trusts any bound name.
                # Declare the atom as well if the file writes it bare.
                if name not in local_names and effective_strict:
                    undeclared.append(name)
                continue
            if existing is not _MISSING:
                # A leaked-pool-atom shape is an ATOM whose spelling is its
                # own name and which is STILL EQUAL to what the process pool
                # holds for that name right now — exactly what this
                # function's own auto-mint branch below,
                # ``_process_declarations``, and ``global_atom/2`` all
                # install. Anything else already bound (a real
                # PredicateMeta class, a Python import, any other object)
                # is trusted unconditionally, same as before this fix.
                #
                # 2026-09-06-atoms-as-cells-strings §5.2: EQUALITY, not
                # identity — ``mint`` returns an equal atom, never a promise
                # of the same object (no process-wide atom table), and the
                # shape is read through the public atom API so a cell atom
                # ``("foo",)`` is recognised beside today's str.
                leaked_pool_atom = (
                    _term_is_atom(existing)
                    and _spelling_or_self(existing) == name
                    and predicate_builtins.get(name) == existing
                )
                # P3-1/P3-2 Task 8 (pool split): the SECOND leak shape a
                # pre-seeded module_dict can carry is ANY ``runtime_builtins``
                # entry (a ``simple_ast.__all__`` node class -- ``Add``,
                # ``Call``, ``Match``, ... -- or an ``INJECTED_RUNTIME_
                # BUILTINS`` value) still sitting under this name, because
                # every module's ``module_dict`` is seeded with the whole
                # compilation-support namespace at exec start (see
                # ``import_hook.py``'s pool-split comment). Same identity
                # discipline as ``leaked_pool_atom``: this shape is real and
                # generally useful (it is exactly what lets generated code
                # construct ``Predicate(...)`` etc.), but it is NOT an atom
                # declaration, so it must not stand in for one — a bare
                # reference to ``Add`` with zero declarations must still
                # raise. Closes
                # todo/done/pythonic-ast-names-leak-into-strict-atom-namespace-2026-09-04.md.
                #
                # Task 8 fix round 1 (RULING): distrust applies to the WHOLE
                # of ``runtime_builtins``, not just ``simple_ast.__all__`` --
                # round 1's narrower scoping left a future ``INJECTED_
                # RUNTIME_BUILTINS`` addition free to leak the same way
                # ``Add`` did (reviewer-proved via a synthetic injected
                # name). The ONE explicit, reviewed exemption
                # (``import_hook.STRICTNESS_EXEMPT_RUNTIME_NAMES`` --
                # currently just ``Undefined``, the Kleene K3 truth value,
                # which must resolve bare in every module by pre-existing
                # design) carves out names that are deliberately meant to
                # satisfy bare-atom resolution everywhere; anything NOT in
                # that frozenset fails loud instead of leaking silent.
                leaked_runtime_builtin = (
                    not leaked_pool_atom
                    and name in runtime_builtins
                    and name not in STRICTNESS_EXEMPT_RUNTIME_NAMES
                    and runtime_builtins[name] is existing
                )
                if (
                    not (leaked_pool_atom or leaked_runtime_builtin)
                    or name in local_names
                ):
                    continue
            if name in local_names:
                # This module's own declared/imported vocabulary — no
                # module_dict entry needed to trust it (covers a name
                # declared via -module/-private but not yet reflected in
                # module_dict at this point in the pipeline, if any).
                continue
            if name in builtin_names:
                # Builtin under any arity — resolved by get_builtin_predicate.
                continue
            if effective_strict and name not in BUILTIN_GOAL_ATOMS:
                undeclared.append(name)
                continue
            # A BUILTIN_GOAL_ATOMS name (``fail``) is accepted here even in
            # strict mode: a builtin GOAL, like ``true``, needs no
            # declaration (operator ruling 2026-09-25).  ``true``/``false``
            # never get here -- they fold to the truth values before this
            # pass -- but ``fail`` is an ordinary ATOM in term position (ISO),
            # so it becomes the atom a ``-private([fail])`` would have
            # declared, and the body compiler lowers it to failure
            # (``terms_to_goalop``).
            #
            # Accept the spelling — no class is minted (§1b/R2).  Recorded in
            # ``predicate_builtins`` (the same pool ``$intern_atom`` and
            # ``_process_declarations`` use), which is the strict-atoms
            # VOCABULARY: the set of declared spellings mapped to their
            # minted atoms.  The old identity-sharing rationale is gone with
            # the ``is``-pins it existed for (2026-09-06-atoms-as-cells-
            # strings §5.2) — atoms compare by ``==``, and ``mint`` makes no
            # same-object promise.
            module_dict[name] = predicate_builtins.setdefault(
                name, _mint_atom(name))

    if undeclared:
        raise NameError(
            _build_strict_atoms_diagnostic(undeclared, module_name)
        )

def _build_strict_atoms_diagnostic(names: list[str], module_name: str) -> str:
    """Build the multi-line diagnostic for ``-strict_atoms`` violations.

    Reports every undeclared atom in one message rather than failing at the
    first, so the author can fix them all at once.  The four (now five with
    ``global_atom/2``) legitimate routes are spelled out to make the fix
    obvious — these files are typically authoritative rules where atom
    spelling is load-bearing, so a beginner-friendly error pays off.
    """
    # De-duplicate while preserving first-seen order — frozenset is unordered,
    # but ``sorted`` makes the diagnostic deterministic across runs.
    unique_names = sorted(set(names))
    if len(unique_names) == 1:
        header = (
            f"strict_atoms: undeclared atom {unique_names[0]!r} "
            f"in {module_name}"
        )
    else:
        joined = ", ".join(repr(n) for n in unique_names)
        header = (
            f"strict_atoms: undeclared atoms {joined} in {module_name}"
        )
    lines = [
        header,
        # For `true`/`false`/`null` none of the five remedies below is the
        # right answer, so name the literal first.  Empty for ordinary atoms,
        # which keeps every other diagnostic worded exactly as before.
        *truth_literal_hint_lines(unique_names),
        "  bare atom references must be one of:",
        f"    - listed in -module({module_name}, [atom, ...])",
        "    - listed in -private([atom, ...])",
        "    - imported via -import_from(from_module, [atom])",
        "    - qualified (e.g. other_module.atom)",
        # SINGLE quotes: ``"atom"`` is a string since the flip, and
        # global_atom/2 refuses it with type_error(atom, "atom").
        "    - obtained via global_atom('atom', Atom)",
    ]
    return "\n".join(lines)


def _predicate_functor_names(predicate_nodes: list, module_items: list) -> set:
    """Functor names this file defines as PREDICATES rather than as data.

    Three sources, all of them "this name will have (or may later be given)
    clauses", which is what makes a functor a predicate:

    * a clause in this file -- the head functor of any ``predicate_nodes``
      entry;
    * a ``-dynamic``/``-table``/``-discontiguous``/``-shallow`` directive --
      the ISO declare-then-assertz pattern leaves a predicate clause-free at
      load time, and misreading it as data would compile its references to
      cells the later-asserted clauses could never match (R6 names
      ``-dynamic`` explicitly);
    * a ``-specialize`` alias -- ``_preregister_specializations`` mints an
      empty predicate class for it, for exactly the same reason;
    * an ISO ``name/arity`` entry in a ``-module``/``-private`` export list
      (R6b) -- the explicit spelling for "predicate export, clauses may live
      downstream", recorded by the rewrite as a ``predicate_export``
      directive item and picked up by the generic directive scan below.

    Read at Step 3, BEFORE Step 4 attaches clauses to classes, so the class's
    own ``_clauses`` cannot answer this question yet.
    """
    names = {head_key(node.head)[0] for node in predicate_nodes}
    for item in module_items:
        if isinstance(item, DirectiveItem) and item.name != "set_prolog_flag":
            # (a set_prolog_flag item's specs are (flag, value), no functor)
            names.update(functor for functor, _arity, *_ in item.specs)
        elif isinstance(item, SpecializeItem):
            names.add(item.new_name)
    return names


def _module_constants(module_dict: dict) -> dict:
    """The ``-constants`` declarations this module has executed so far.

    Read off the logic module's own registry (``register_module_constant``
    populates it as each declaration runs, which is before any of the
    compile steps here). Returns an empty mapping when there is no module or
    no registry, so callers can test membership unconditionally.
    """
    return getattr(module_dict.get("$module"), "constants", None) or {}


_PREDICATE_DIRECTIVES = ("dynamic", "table", "discontiguous", "shallow")


def _warn_atom_exports_defined_as_predicates(module_items: list,
                                            predicate_nodes: list,
                                            module_name: str) -> None:
    """Warn, once per (module, name), when a bare name exported as an ATOM
    (``-module(m, [..., foo, ...])``) is also made a PREDICATE here, at any
    arity: clauses (``foo,`` / ``foo <- ...`` / ``foo(1),``), a clause-free
    ``-dynamic``/``-table``/``-discontiguous``/``-shallow``, or a
    ``-specialize`` alias.  Operator ruling 2026-09-26: ISO allows both, so
    a warning; see ``ClausalAtomExportDefinedAsPredicateWarning`` for the
    harm.  Any arity (roborev 228): the module attribute is bound by NAME,
    so ``foo/1`` makes ``m.foo`` the handle just as ``foo/0`` does.  An ISO
    ``foo/N`` export entry is a predicate export, not an atom, and never
    warns."""
    exported_atoms = []
    for item in module_items:
        if isinstance(item, ModuleDeclItem):
            exported_atoms.extend(e for e in item.exports if isinstance(e, str))
    if not exported_atoms:
        return
    atoms = set(exported_atoms)
    # name -> {arity -> [shape, ...]} in source order.
    made: dict[str, dict[int, list[str]]] = {}

    def note(name, arity, shape):
        shapes = made.setdefault(name, {}).setdefault(arity, [])
        if shape not in shapes:
            shapes.append(shape)

    for node in predicate_nodes:
        functor, arity = head_key(node.head)
        if functor in atoms:
            if arity:
                note(functor, arity, f"clauses for {functor}/{arity}")
            else:
                note(functor, 0, f"a fact `{functor},`" if node.body is True
                     else f"a rule `{functor} <- ...`")
    for item in module_items:
        if isinstance(item, DirectiveItem) and item.name in _PREDICATE_DIRECTIVES:
            for spec in item.specs:
                if spec[0] in atoms:
                    note(spec[0], spec[1], f"-{item.name}({spec[0]}/{spec[1]})")
        elif isinstance(item, SpecializeItem) and item.new_name in atoms:
            note(item.new_name, None,
                 f"-specialize(..., alias={item.new_name})")
    if not made:
        return
    from clausal.lint_warnings import (  # noqa: PLC0415
        ClausalAtomExportDefinedAsPredicateWarning,
    )
    for name in dict.fromkeys(exported_atoms):
        by_arity = made.get(name)
        if not by_arity:
            continue
        arities = sorted(a for a in by_arity if a is not None)
        indicators = ", ".join(f"{name}/{a}" for a in arities) or name
        shapes = "; ".join(s for a in by_arity for s in by_arity[a])
        export = (f"{name}/{arities[0]}" if len(arities) == 1
                  else f"{name}/N")
        warnings.warn(ClausalAtomExportDefinedAsPredicateWarning(
            f"{module_name} exports `{name}` as an ATOM (the bare `{name}` in "
            f"its -module export list) and also defines the predicate "
            f"{indicators} ({shapes}).  ISO allows both, but here the module "
            f"attribute `{name}` -- in this module and in every importer -- "
            f"is the predicate's handle, not the atom '{name}', so data keyed "
            f"by the atom that is read through `{module_name}.{name}` no "
            f"longer matches.  Drop the {indicators} definition if it is only "
            f"there for conformance, or rename one of the two; to export the "
            f"predicate, write {export} in the export list instead of "
            f"`{name}`."), stacklevel=2)


def _warn_export_arity_mismatches(module_items: list, predicate_nodes: list,
                                  module_name: str,
                                  module_dict: dict | None) -> None:
    """Warn when a ``name/N`` export entry names an arity nothing here
    defines or declares, while ``name`` HAS clauses at another arity --
    ``-module(m, [base/9])`` over ``base/2`` clauses.  See
    ``ClausalExportArityMismatchWarning``.

    What counts as defining or declaring ``name/N``: a clause (after term
    and goal expansion, so a DCG rule counts at its translated arity), a
    ``-dynamic``/``-table``/``-discontiguous``/``-shallow``/
    ``-meta_predicate`` spec, or a field-carrying export entry of that
    arity.  A ``-specialize`` alias of the name counts at every arity (its
    arity is not known here).  Only CLAUSES at another arity trigger the
    warning: an export of a name with no clauses here is the "clauses live
    elsewhere" idiom and stays silent.  The head-shaped export form
    (``base(A, B, C)`` over ``base/2`` clauses) is not checked: the
    rewriter already refuses that mismatch.
    """
    exports = [item for item in module_items
               if isinstance(item, DirectiveItem)
               and item.name == "predicate_export"]
    if not exports:
        return
    clause_arities: dict[str, set[int]] = {}
    for node in predicate_nodes:
        functor, arity = head_key(node.head)
        clause_arities.setdefault(functor, set()).add(arity)
    declared: set[tuple[str, int]] = set()
    any_arity: set[str] = set()
    for item in module_items:
        if isinstance(item, DirectiveItem) and item.name in (
                *_PREDICATE_DIRECTIVES, "meta_predicate"):
            declared.update((spec[0], spec[1]) for spec in item.specs)
        elif isinstance(item, (ModuleDeclItem, PrivateDeclItem)):
            entries = (item.exports if isinstance(item, ModuleDeclItem)
                       else item.items)
            declared.update((e[0], len(e[1])) for e in entries
                            if isinstance(e, tuple) and e[1])
        elif isinstance(item, SpecializeItem):
            any_arity.add(item.new_name)
    path = (module_dict or {}).get("__file__")
    # The name the file gives itself reads better than a loader's synthetic
    # module name (``load_clausal_module`` registers ``_clausal_test_<stem>``).
    declared_name = next((item.module_name for item in module_items
                          if isinstance(item, ModuleDeclItem)
                          and item.module_name), None)
    module_name = declared_name or module_name
    from clausal.lint_warnings import (  # noqa: PLC0415
        ClausalExportArityMismatchWarning,
    )
    seen: set[tuple[str, int]] = set()
    for item in exports:
        for functor, arity in item.specs:
            if (functor, arity) in seen:
                continue
            seen.add((functor, arity))
            others = clause_arities.get(functor, set())
            if (not others or arity in others
                    or (functor, arity) in declared
                    or functor in any_arity):
                continue
            where = module_name
            if item.position is not None:
                line = item.position[0]
                where = f"{path}:{line}" if path else f"{module_name}, line {line}"
            defined = ", ".join(f"{functor}/{a}" for a in sorted(others))
            fix = (f"{functor}/{min(others)}" if len(others) == 1
                   else f"one of {defined}")
            warnings.warn(ClausalExportArityMismatchWarning(
                f"{where}: {module_name} lists {functor}/{arity} in its "
                f"-module/-private declarations, but "
                f"defines no {functor}/{arity} -- its clauses are for "
                f"{defined}.  Exporting a predicate with no clauses here is "
                f"legal (calling it raises existence_error), so this loads, "
                f"but it is most likely a typo in the export entry: did you "
                f"mean {fix}?  If {functor}/{arity} is a different procedure "
                f"on purpose, declare it (e.g. -dynamic({functor}/{arity})) "
                f"to silence this."), stacklevel=2)


def _process_declarations(module_items: list, module_dict: dict,
                          predicate_functors: set = frozenset(),
                          db=None) -> None:
    """Process -module and -private declarations: bind declared names.

    Two shapes, ONE treatment each post-flip — neither mints a class
    (§1b/R2, the atom pivot, and P3-2 Task 2, the cell flip):

    * **Bare entry** (a ``str`` — a zero-arity ATOM): no class is minted.
      Atoms are global by spelling, so there is nothing module-local to
      create; the plain str is bound into ``module_dict`` under its own
      name (idempotent — every module binds the identical spelling) purely
      so an ``-import_from`` of a declared/private atom still finds an
      attribute to import (Python's ``from mod import name`` needs
      ``mod.name`` to exist) and so a runtime ``LoadName`` reference to it
      (the auto-accept fallthrough path, before this pass distinguished it
      as declared) resolves.  Shared with the same process-wide
      ``predicate_builtins`` pool ``_process_bare_atom_refs``/
      ``$intern_atom`` use, so the identical str object backs the name
      everywhere.
    * **Tuple entry** (``(name, field_names)`` — a functor with fields):
      no class is minted either, post-flip (P3-2 Task 2 / R6 revised).
      compound DATA is cells now — a tuple ``("point", 1, 2)`` whose shape
      the module's ``__clausal_functor_signatures__`` registry describes —
      so a data functor needs no class to construct through, and the plain
      interned spelling is bound instead, exactly as a bare atom entry is.
      The don't-clobber guard is what keeps PREDICATES as handles: a
      predicate with in-file clauses already has its handle in
      ``module_dict`` (bound by ``$declare_head``, which runs during exec,
      before this pass; a ``PredicateMeta`` class until W4b-3 slice 5), and
      a predicate binding that is there is never overwritten.

    P3-1 §1b/R2: atoms are global-by-spelling interned strs, so a local
    ``-module``/``-private`` atom declaration and an ``-import_from`` of the
    same name can no longer disagree about identity — there is nothing left
    to shadow.  (Pre-pivot this docstring described a Phase 4 shadowing-
    warning cross-check + an ``-overwrites([...])`` acknowledgement
    directive; both are deleted along with the per-module atom-identity
    machinery they existed to diagnose.)
    """
    # Lazy import — see _process_bare_atom_refs.
    from clausal.import_hook import predicate_builtins

    for item in module_items:
        if isinstance(item, (ModuleDeclItem, PrivateDeclItem)):
            exports = item.exports if isinstance(item, ModuleDeclItem) else item.items
            # P3-3 Task 5b: record the atom DECLARATIONS themselves, before
            # the binding loop below decides what each name binds to.  The
            # binding cannot be read back as the declaration once a 0-arity
            # clause block has won the name (the guard below), and an
            # ``-import_from``ing module needs the declaration, not the
            # binding -- see ``_imported_reference`` and
            # ``cells.DECLARED_ATOMS_KEY``.
            declared_atoms = {e for e in exports if isinstance(e, str)}
            if declared_atoms:
                module_dict.setdefault(DECLARED_ATOMS_KEY, set()).update(
                    declared_atoms)
            for entry in exports:
                if isinstance(entry, str):
                    # Atom: bind ``mint(entry)`` -- UNLESS a
                    # same-named real predicate already exists in
                    # module_dict (Phenomenon A: an in-file 0-arity fact
                    # statement or an N-arity clause re-declared the name
                    # over this atom's own -module/-private line, exec-time,
                    # via ``$declare_head`` -- ``_make_predicate_decl_ast``/
                    # ``_build_zero_arity_fact_statements``; a PredicateMeta
                    # class block until W4b-3 slice 5).  The predicate wins -- do not clobber
                    # it back to a plain atom; see
                    # ``_make_atom_str_assign_ast``'s docstring for the
                    # matching guard on the OTHER direction (an atom must
                    # not clobber a real predicate either).
                    # A declared CONSTANT wins its global too, for the same
                    # reason a predicate does: -constants bound, gated and
                    # froze a value there, and ``++name`` reads that slot.
                    # Binding the atom over it would destroy the constant
                    # silently -- and cost nothing in exchange, since a
                    # DECLARED atom compiles to its cell literal at every
                    # reference site and never reads this binding.
                    # ``pi`` is the atom, ``++pi`` is the value.
                    if (not is_local_predicate_binding(module_dict, entry)
                            and entry not in _module_constants(module_dict)):
                        module_dict[entry] = predicate_builtins.setdefault(
                            entry, _mint_atom(entry)
                        )
                    continue
                elif isinstance(entry, tuple):
                    name, field_names = entry
                else:
                    continue
                # P3-2 Task 2 (THE FLIP, R6 revised): mint nothing.  A
                # declared functor's SHAPE is recorded in the module's
                # ``__clausal_functor_signatures__`` registry and its data
                # is compiled to cells, so there is no class to create --
                # bind the interned spelling, the same shape the bare-atom
                # branch above uses (and through the same process-wide
                # ``predicate_builtins`` pool, so one str object backs the
                # name everywhere).
                #
                # The guard is the whole predicate/data split at this site.
                # It cannot be "is there a class?": the ``-module``/
                # ``-private`` REWRITE emits a ``$declare_head`` statement
                # (``_make_predicate_decl_ast``) for every field-carrying
                # export, so by the time this runs EVERY declared functor is
                # bound to a handle, predicate and data alike.  *predicate_functors* is the real question --
                # will this name have clauses? -- answered from the clause
                # nodes and the predicate-shaped directives (see
                # ``_predicate_functor_names``).  A predicate keeps its
                # class (Phenomenon A: the predicate wins, do not clobber it
                # back to a str); a data functor's class is unbound here and
                # becomes unreachable by name, which is what makes the
                # BINDING SHAPE decide data-vs-predicate at every reference
                # site (R6).
                #
                # An already-clause-carrying class is kept too: that is an
                # imported predicate this module re-exports, not data.
                existing = module_dict.get(name)
                if name in predicate_functors:
                    continue
                # ``existing._row`` RAW, not ``existing._clauses``: the
                # facade was `(cls._row or cls._detached_row()).clauses`, so
                # merely ASKING whether a class carries clauses MINTED a
                # private throwaway row for every data functor that reached
                # here (measured: 6 of the 12 detached rows over 56 fixtures
                # came from this one read).  A class with no row cannot have
                # been given clauses, so the answer is the same and nothing
                # is minted.  ``_row`` is a plain class attribute -- reading
                # it is not a facade read (W4b-2b: resolve_predicate_row is
                # era-agnostic now, but the same "does not mint" contract
                # holds -- its class arm is the identical raw ``._row``
                # read).  NOT gated with is_declared_predicate: this site's
                # original ``isinstance(existing, PredicateMeta)`` never
                # compared arity at all (arity-blind by original design --
                # a same-name class at a different arity than this entry's
                # own ``field_names`` still took the ``continue`` if it had
                # clauses), and resolve_predicate_row's class arm preserves
                # that -- it does not consult ``arity`` either.  The
                # ``arity=len(field_names)`` argument only matters to the
                # mangled-atom arm's exact ``db.row`` lookup.
                _row = resolve_predicate_row(existing, arity=len(field_names),
                                             db=db)
                if _row is not None and _row.clauses:
                    continue
                # An IMPORTED predicate at this arity wins even with no
                # clauses yet (operator ruling 2026-09-24, option A): a
                # clause-less ``-dynamic`` exporter's row is still the
                # predicate an ``-import_from`` shares, and binding the atom
                # here split identity silently -- an ``assertz`` landed on
                # a row neither module read.  Same outcome as against a
                # DEFINING exporter (the clause test above).
                if (_row is not None and _row.db is not db
                        and not _row.detached
                        and _row.key[1] == len(field_names)):
                    continue
                # Bound in THIS module's namespace only -- deliberately NOT
                # through the process-wide ``predicate_builtins`` pool the
                # bare-atom branch above shares.  That pool is the ATOM
                # vocabulary: an entry in it makes the spelling a
                # resolvable atom for every later-loaded module, which
                # would let a functor name silently satisfy another file's
                # strict-atoms check (and did -- it turned
                # ``tests/test_undefined_name_sibling_diagnostic.py`` green
                # by accident when this went through the pool).  Cells
                # compare slot 0 with ``==``, never ``is``, so a functor
                # spelling needs no shared identity.
                #
                # 2026-09-06-atoms-as-cells-strings §5.2: a declared functor's
                # NAME used as a value IS the atom, so this binds
                # ``atoms.mint(name)`` rather than a bare ``sys.intern``
                # (``mint`` interns the spelling itself, so the cheap-compare
                # property the old call was kept for survives).  ``mint`` is
                # not the pool -- the comment above stays true.
                module_dict[name] = _mint_atom(name)
