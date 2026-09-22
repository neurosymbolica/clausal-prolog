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
    Module as LogicModule, Clause, head_key,
    WRITE_LOAD_CLAUSES, WRITE_LOAD_DISPATCH,
)
from clausal.logic.cells import DECLARED_ATOMS_KEY
from clausal.logic.atoms import (
    is_atom as _term_is_atom,
    mint as _mint_atom,
    spelling as _atom_spelling,
)
from clausal.logic.exceptions import LogicException
from clausal.logic.compiler import (
    compile_predicate_trampoline,
    compile_predicate_shallow,
)
from clausal.logic.predicate import (
    PredicateMeta, make_predicate, record_clause_source,
    term_field_names_of_class,
)
from clausal.pythonic_ast.nodes import (
    AtomAppliedAsFunctor as AtomAppliedAsFunctorItem,
    BareAtomRefs as BareAtomRefsItem,
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


_implicit_atoms_deprecation_files: set = set()


class ClausalImplicitAtomsDeprecationWarning(DeprecationWarning):
    """``-implicit_atoms`` is deprecated: declare the names instead."""


def _warn_implicit_atoms_deprecated(module_name: str) -> None:
    """Emit the ``-implicit_atoms`` deprecation notice once per FILE.

    Per file, not per process (which is what ``-strict_atoms`` does): this
    notice asks the reader to go and EDIT something, so every file that still
    carries the directive has to be named.  A once-per-process guard would
    report the first and hide the rest, which is the opposite of what a
    migration notice is for.

    Guarded by a module-level set rather than the warnings-filter dedup, so
    it is exactly-once-per-file regardless of the consumer's filters.
    """
    if module_name in _implicit_atoms_deprecation_files:
        return
    _implicit_atoms_deprecation_files.add(module_name)
    import warnings
    warnings.warn(
        f"{module_name}: -implicit_atoms is deprecated (2026-09-18). "
        "Declare the names this file mints -- list them in -private([...]) "
        "or -module(name, [...]), or -hide them -- and delete the directive. "
        "It is removed in the next landing. (Shown once per file.)",
        ClausalImplicitAtomsDeprecationWarning,
        stacklevel=2,
    )


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
        The Python module's __dict__.  PredicateMeta classes are injected
        here and used for cross-predicate resolution.
    module_name : str
        Module name for the LogicModule.

    Returns
    -------
    LogicModule
        The compiled logic module with all predicates dispatched.
    """
    logic_module = LogicModule(module_name, module_dict=module_dict)
    db = logic_module.db

    # ── Step 0-: Reserved truth-value names ───────────────────────────────
    #    Runs before everything so the diagnostic names the real problem
    #    rather than whatever incidental error the name causes downstream.
    _reject_reserved_truth_names(module_items, predicate_nodes, module_name)

    # ── Step 0: Process imports (before term expansion, so imported TE
    #    rules are available) ──────────────────────────────────────────────
    _process_imports(module_items, module_dict, db)

    # ── Step 1: Term expansion (after imports, before directives) ────────
    from clausal.logic.term_expansion import run_term_expansion
    predicate_nodes = run_term_expansion(predicate_nodes, module_dict)

    # ── Step 1b: Goal expansion (regex pre-compile + auto-binding) ─────
    from clausal.logic.goal_expansion import run_goal_expansion
    predicate_nodes = run_goal_expansion(predicate_nodes, module_dict)

    # ── Step 1c: Pre-register specialized predicates ─────────────────────
    #    Create empty PredicateMeta classes for -specialize targets so that
    #    later clauses (e.g. Test) can reference them during compilation.
    _preregister_specializations(module_items, module_dict)

    # ── Step 2: Process directives ───────────────────────────────────────
    _process_directives(module_items, db, module_dict)

    # ── Step 3: Process module/private declarations ──────────────────────
    #    Needs to know which declared functors are PREDICATES (P3-2 Task 2 /
    #    R6): a predicate keeps its class, a data functor binds its interned
    #    spelling.  "Has clauses" cannot be read off the class here -- Step 4
    #    is what attaches them -- so it is read off the clause nodes and the
    #    predicate-shaped directives instead.
    _process_declarations(
        module_items, module_dict,
        _predicate_functor_names(predicate_nodes, module_items),
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

    # ── Step 3c: resolve each imported name to the CLASS it bound ────────
    #    Names only, no policy: ``origins`` maps every spelling an
    #    ``-import_from`` introduces (the alias AND the class's own functor)
    #    to the class itself.  The REFUSAL that used to live here is the
    #    mutation gate's now (P3-3 Task 3) — one policy, asked by every
    #    channel — and this is what hands the gate the shared class whose row
    #    a write would land on when ``module_dict.get(functor)`` cannot find
    #    it (identity todo instance 3, the aliased import).
    origins = _import_from_origins(module_items, module_dict)
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

    # ── Step 4: assertz all clauses ───────────────────────────────────────
    pending: dict[tuple[str, int], PredicateMeta | None] = {}
    for pred_node in predicate_nodes:
        functor, arity = head_key(pred_node.head)
        key = (functor, arity)

        # Bind the PredicateMeta class to this predicate's Database ROW
        # (P3-3 Task 2).  This is the one place a class becomes the compiled
        # face of a stored predicate at load: after it, ``pred_cls._clauses``
        # IS ``db._clauses[key]`` and ``pred_cls._signature`` IS
        # ``db._signatures[key]``, so there is no second store for a later
        # ``assertz`` to leave stale — and no arity-blind mirror needed to
        # keep one in step.  The slice-assign below is consequently a
        # self-copy in the ordinary case; it is kept because ``clauses_for``
        # is a snapshot and the write is what the row's contract names as the
        # deliberate clause-list minting site.
        pred_cls = module_dict.get(functor)
        # P1 2026-09-17: this guard is NOT redundant and stays.  Measured over
        # the whole suite (14,615 arrivals here), 34 of them find something
        # other than a predicate class under a functor that HAS clause nodes —
        # an interned atom ``tuple`` and an absent binding — so dropping the
        # test would hand a tuple to ``_bind_row`` below.
        if not isinstance(pred_cls, PredicateMeta):
            pred_cls = None
        with _load_gate(db, functor, arity, author, WRITE_LOAD_CLAUSES,
                        pred_cls if pred_cls is not None
                        else _imported_class(origins, functor),
                        origins, module_name, module_dict):
            logic_module.define_predicate(pred_node)
            if pred_cls is not None:
                db_clauses = db.clauses_for(functor, arity)
                # ``authorized``: this is the ONE bind the mutation gate has
                # just cleared for this author, so it may move a shared class
                # onto this module's row (the clause-free vocabulary idiom).
                # Every other bind is policed -- see ``PredicateMeta.
                # _bind_row``.
                pred_cls._bind_row(db, functor, arity, authorized=True)
                # ``_ensure_clauses``, not a plain ``_clauses`` read: a read
                # mints nothing (P3-3 Task 2 fix round 1), and this IS the
                # sanctioned clause-install site — the slice-assign below has
                # to land in the Database, not in an unminted per-row list.
                pred_cls._ensure_clauses()[:] = db_clauses
                record_clause_source(pred_cls, module_name, module_dict)
                if pred_cls._signature is None:
                    pred_cls._signature = pred_cls._fields
                pending[key] = pred_cls
            else:
                pending[key] = None

    # ── Step 4a: seed pending from -dynamic specs (A12-F005) ─────────────
    #    A declared-but-clause-less dynamic predicate must still compile to
    #    a dispatch (the always-fail trampoline) so querying it fails
    #    cleanly with 0 solutions instead of raising NotImplementedError
    #    from _get_dispatch(). The minted class (term_rewriting mints it at
    #    directive processing) is attached only when its arity matches the
    #    spec, so a same-name predicate at another arity keeps its dispatch.
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
                imported = _imported_class_by_canonical_name(
                    origins, db, functor, arity)
                if imported is not None and not db.is_defined(functor, arity):
                    # NOT when this module has clauses of its own under the
                    # name: that is a genuine clash, and a local definition
                    # keeps its own predicate — the same rule
                    # ``Database.adopt_row`` states for rows.
                    module_dict[functor] = imported
                # Stamp the declared arity on the class whatever its clause
                # state — the ``_refuse_call_at`` fallback only reads it while
                # the clause list is EMPTY, which includes the retract-back-
                # to-empty return leg of a predicate that did have clauses.
                #
                # ON AN IMPORTED CLASS THIS WRITES THE OWNER'S ROW (roborev
                # job 78, finding 5): ``_dynamic_arities`` reads through to
                # ``cls._row``, which for an import is the exporter's.  That
                # is DELIBERATE and not new — the non-aliased sibling has
                # always done it, because the declared-arity set is a property
                # of the PREDICATE, not of the module that mentioned it, and
                # ``_refuse_call_at`` reads it through the same shared class.
                # The rebind above only makes the aliased spelling reach the
                # same place.  Gate-exempt for the same reason every
                # ``_dynamic_arities`` write is: it records a DECLARATION, not
                # a clause, and changes no answers.
                stamped = module_dict.get(functor)
                # THE WART (P1 spec 2026-09-17 §2): ``_dynamic_arities`` is a
                # per-NAME set living on the CLASS's OWN row, which is the row
                # of the class's own arity — not of ``arity``, the arity being
                # declared.  That row cannot be named through ``db`` here: for
                # a clause-less ``-dynamic`` declaration the class is still on
                # its DETACHED row at this point (measured 2026-09-17), so
                # ``db.row(...)`` reaches a different object, and a row-side
                # membership test would skip the stamp altogether.  So the
                # class stays for both the test and the write; the set does
                # not move.  ``_bind_row`` carries the set onto the real row.
                if isinstance(stamped, PredicateMeta):
                    if stamped._dynamic_arities is None:
                        stamped._dynamic_arities = set()
                    stamped._dynamic_arities.add(arity)
                key = (functor, arity)
                if key in pending:
                    continue
                pred_cls = module_dict.get(functor)
                # P1 (spec 2026-09-17 §2.2): the class's OWN ROW names its
                # arity, so this is the arity-checked membership test with no
                # class test and no ``_fields`` read.  ``_row`` is set for
                # every predicate class that reaches here — the stamp above
                # reads ``_dynamic_arities``, a property over the class's row,
                # which mints the detached row when there is none — and absent
                # on a non-predicate binding.
                #
                # NOT ``db.row(functor, arity) is not None``: step 2's
                # ``mark_dynamic`` already put ``(functor, arity)`` in this
                # database, so that test is VACUOUSLY TRUE here (measured
                # 2026-09-17), and ``-dynamic(d/2)`` beside ``d/1`` clauses
                # would then bind d/1's class onto d/2's row.
                cls_row = getattr(pred_cls, "_row", None)
                if cls_row is not None and cls_row.key[1] == arity:
                    if _belongs_elsewhere(pred_cls, db):
                        # A ``-dynamic`` declaration for a predicate this
                        # module IMPORTED (P3-3 Task 3 fix round 1).  The
                        # declaration is legitimate — it is how a module says
                        # "I intend to assert against this" — but the
                        # predicate is not ours to bind or to compile: doing
                        # either would hand the owner's shared class this
                        # module's (empty) clause list and its always-fail
                        # trampoline.  The mark on this database is enough;
                        # asserts resolve through the class to the owner's
                        # row.
                        continue
                    # Same binding as step 4 (P3-3 Task 2): a declared-but-
                    # clause-less dynamic predicate is exactly the shape whose
                    # first clause arrives by runtime assertz, so its class
                    # must already be reading the row that assertz appends to.
                    pred_cls._bind_row(db, functor, arity, authorized=True)
                    if pred_cls._signature is None:
                        pred_cls._signature = pred_cls._fields
                    pending[key] = pred_cls
                else:
                    pending[key] = None

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
                        pred_cls if pred_cls is not None
                        else _imported_class(origins, functor),
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
            original_fn = (
                pred_cls._get_dispatch() if pred_cls is not None
                else db.get_dispatch(functor, arity)
            )
            wrapped = ensure_tabled_wrapper(db, functor, arity, original_fn)
            if wrapped is original_fn:
                continue
            with db.mutate(functor, arity, author=author,
                           kind=WRITE_LOAD_DISPATCH, detail="table-wrap",
                           through=pred_cls):
                if pred_cls is not None:
                    pred_cls._dispatch_fn = wrapped
                db.set_dispatch(functor, arity, wrapped)

    # ── Step 6b: Meta-interpreter specialization ────────────────────────
    #    Runs after all predicates are compiled so source programs can be
    #    called.  Specialized predicates compile themselves internally.
    _run_specialization(module_items, predicate_nodes, module_dict, db)

    # ── Step 7: Lock non-dynamic predicates ──────────────────────────────
    #
    # ONLY names this Database actually holds a row for.  The walk sees every
    # value in the module dict, and plenty of them are ``PredicateMeta`` with
    # ``_fields`` while being no predicate of this Database: declared data
    # functors (the P4 prerequisite mints a row only for a functor a directive
    # names as a PREDICATE), the CLP(B) constraint term classes, and a hook
    # name like ``term_expansion`` that is present but defined elsewhere.
    #
    # Locking one of those used to MINT A DETACHED ROW as a side effect --
    # ``_locked`` is a facade over ``(cls._row or cls._detached_row())`` -- and
    # then wrote the lock into a private single-predicate Database nobody else
    # can reach.  So the lock had no enforcement effect: the refusal path is
    # ``database.write_refusal(row, ...)`` reading ``row.locked`` off the REAL
    # row, and ``compiler/globals_env.py`` and ``compiler/arg_index.py`` both
    # already spell the same test as ``row is None or not row.locked``.
    # Measured over the house suite before narrowing this: 897 detached rows
    # minted across 157 names, and 31 ``_locked`` reads in the whole suite, of
    # which the only engine-side readers on a detached class were ``__repr__``
    # and the instance read-through shim -- neither an enforcement path.
    for obj in module_dict.values():
        if isinstance(obj, PredicateMeta) and hasattr(obj, '_fields'):
            key = (obj.__name__, len(obj._fields))
            if db.row(*key) is None:
                continue        # not a predicate of this Database; nothing to lock
            if not db.is_dynamic(*key):
                obj._lock()

    return logic_module


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
    clauses for it, so the clause block's ``PredicateMeta`` wins the binding
    (``_process_declarations``' don't-clobber guard).  The owner's own
    lowering still answers such a reference with the str — its ``-module``
    list is in front of it — and the importer used to answer with the CLASS,
    so a dict key written by the owner and read by the importer silently
    missed.  ``DECLARED_ATOMS_KEY`` is what lets the importer answer the way
    the owner does.

    The declaration is the authority, not the presence of /0 clauses: a name
    with 0-arity clauses that the owner never declared as an atom is a
    predicate, and stays the class.  A DUAL declaration (``-module(m, [dual,
    dual(G)])``) is a functor too — its class carries fields — so only a
    zero-field class is answered with the spelling.

    The module ATTRIBUTE (``mod.name`` from Python, and this file's own bare
    local binding) is untouched: it keeps the predicate class, so ``call/N``
    and ``assertz`` still find the /0 predicate through the namespace (see
    ``higher_order._namespace_dispatch`` → ``database_ops._find_pred_cls``).
    """
    if not isinstance(value, PredicateMeta) or value._fields:
        return value
    declared = getattr(mod, "__dict__", {}).get(DECLARED_ATOMS_KEY)
    if not declared or orig_name not in declared:
        return value
    from clausal.import_hook import predicate_builtins  # noqa: PLC0415
    return predicate_builtins.setdefault(orig_name, _mint_atom(orig_name))


def _plant_imported_rows(db, mod, orig_name: str, local_name: str) -> None:
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
        row = exporter_db.row(orig_name, arity)
        if row is not None:
            db.adopt_row(local_name, arity, row)


def _process_imports(module_items: list, module_dict: dict, db=None) -> None:
    """Execute import directives, populating module_dict.

    *db* is the importing module's Database -- the LOCAL in ``compile_module``,
    not ``module_dict["$module"].db``: at this point the dict still holds the
    placeholder module the body exec'd against, which ``compile_module``
    replaces afterwards.  Reaching for the dict here plants into a database
    that is then thrown away.
    """
    for item in module_items:
        if isinstance(item, ImportFromItem):
            mod = _resolve_module(item.module)
            for name_spec in item.names:
                if isinstance(name_spec, tuple):
                    orig_name, local_name = name_spec
                    value = getattr(mod, orig_name)
                    module_dict[local_name] = value
                    # Keyed by LOCAL_NAME: the aliasing module says ``link``,
                    # so ``link`` is what its database answers to.  A class
                    # cannot do this -- it carries the exporter's ``__name__``
                    # wherever it goes, which is why ``_import_from_origins``
                    # has to index an aliased import under both spellings.
                    _plant_imported_rows(db, mod, orig_name, local_name)
                    # Also store under the dotted key ("module.OrigName") so
                    # that _inject_resolved_targets can resolve it when the compiler
                    # emits LoadName(name="module.OrigName") for remapped imports.
                    module_dict[f"{item.module}.{orig_name}"] = (
                        _imported_reference(mod, orig_name, value))
                else:
                    value = getattr(mod, name_spec)
                    module_dict[name_spec] = value
                    _plant_imported_rows(db, mod, name_spec, name_spec)
                    # Dotted key for compiler resolution (e.g. "py.sympy.inf").
                    module_dict[f"{item.module}.{name_spec}"] = (
                        _imported_reference(mod, name_spec, value))
            # Store the module object under its user-facing name so that
            # dotted-name resolution works in the compiler's
            # ``_inject_resolved_targets`` -- but ONLY for a dotted path.
            #
            # BUG #2 (corpus `_tools/split_domain.py:1049`, reproduced at
            # engine level 2026-09-11): a SINGLE-SEGMENT module name is also a
            # valid Clausal identifier, so this binding shadows a profile key
            # or atom of the same spelling. The name holds a Python MODULE
            # while a bare key is the interned atom ``('currency',)`` -- two
            # different kinds of thing in one namespace slot, so the collision
            # is SILENT: the lookup finds nothing and the rule answers
            # ``unknown([key])``. `currency` is simultaneously a vocab module
            # and an invoice's own currency field, and the corpus held the
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
        elif isinstance(item, DirectiveItem):
            for functor, arity in item.specs:
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


def _import_from_origins(module_items: list, module_dict: dict) -> dict:
    """``{name: (dotted module, bound class or None)}`` for every name an
    ``-import_from`` binds in this file.

    Indexed under BOTH names an aliased import gives a predicate.  ``alias(f,
    G)`` binds the exporter's class under ``G``, but the class keeps its own
    functor ``f``, and a clause head compiles to the CLASS's functor — so
    ``head_key`` hands the load channel ``f`` while the file only ever
    mentions ``G``.  Indexing the alias alone let the aliased spelling walk
    straight past the refusal and clobber the exporter through step 5's
    dispatch assignment, with the clause list left intact so the damage was
    invisible to a clause count (found by review, 2026-08-25).

    This is a RESOLVER, not a guard (P3-3 Task 3): it answers "which class
    does this head name reach", and the mutation gate answers "may this load
    write it".  It is the one place the identity todo's "resolve a head to its
    class once" is done for the load channel.
    """
    origins: dict[str, tuple[str, Any]] = {}
    for item in module_items:
        if not isinstance(item, ImportFromItem):
            continue
        for name_spec in item.names:
            local = name_spec[1] if isinstance(name_spec, tuple) else name_spec
            bound = module_dict.get(local)
            if not isinstance(bound, PredicateMeta):
                bound = None
            origins[local] = (item.module, bound)
            if bound is not None and bound.__name__ != local:
                origins.setdefault(bound.__name__, (item.module, bound))
    return origins


def _belongs_elsewhere(pred_cls, db) -> bool:
    """True when *pred_cls* already reads another Database's real row — i.e.
    it is somebody else's predicate, reached here through an
    ``-import_from``.  A class on its private detached row is unbound, not
    foreign."""
    row = getattr(pred_cls, "_row", None)
    return row is not None and not row.detached and row.db is not db


def _imported_class_by_canonical_name(origins: dict, db, functor: str,
                                      arity: int):
    """The predicate this module IMPORTED whose own name is *functor* at
    *arity* — or None.

    A class carries the exporter's ``__name__`` wherever it goes, so an
    ``-import_from(m, [alias(bo_p, AliasS)])`` leaves the canonical spelling
    bound to nothing in ``module_dict`` and ``AliasS`` bound to a class that
    calls itself ``bo_p``.  ``_import_from_origins`` has ALREADY seen through
    that — it indexes an aliased import under both the alias and
    ``bound.__name__`` — so this is ``_imported_class`` plus the two checks
    that call site needs and it does not:

    * ARITY.  ``origins`` is keyed by name alone, and a name bound at another
      arity is not the predicate this ``-dynamic(f/N)`` declares.
    * FOREIGNNESS.  ``_belongs_elsewhere`` keeps a module's own declaration
      from ever being rerouted, including the degenerate import-from-self.

    NOT a scan of ``module_dict.values()`` by ``__name__`` (roborev job 78,
    finding 1): that also matches a class reached by a plain Python import, a
    ``-specialize`` target, or anything another rewrite pass left in the dict,
    none of which is an ``-import_from``.
    """
    bound = _imported_class(origins, functor)
    if bound is None or len(bound._fields or ()) != arity:
        return None
    return bound if _belongs_elsewhere(bound, db) else None


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
        pred_cls = module_dict.get(functor)
        if not isinstance(pred_cls, PredicateMeta):
            pred_cls = _imported_class(origins, functor)
        exc = db.refusal_for(
            functor, arity, author=author, kind=WRITE_LOAD_CLAUSES,
            detail=_LOAD_SITES[WRITE_LOAD_CLAUSES], through=pred_cls,
        )
        if exc is not None:
            raise _redefinition_error(
                exc, functor, arity, pred_cls, origins, module_name,
                module_dict,
            )


_LOAD_SITES = {
    WRITE_LOAD_CLAUSES: "compile_module step 4",
    WRITE_LOAD_DISPATCH: "compile_module step 5",
}


def _imported_class(origins: dict, functor: str) -> "PredicateMeta | None":
    """The class an ``-import_from`` bound for *functor*, or ``None``.

    Used to hand the mutation gate the shared class a write would land on
    when ``module_dict.get(functor)`` finds nothing — which is exactly the
    ALIASED import (identity todo instance 3): the class is in the module
    dict under its alias, so the functor a clause head compiles to reaches
    nothing, and the write went unexamined while step 5 replaced the shared
    dispatch anyway.
    """
    origin = origins.get(functor)
    if origin is None:
        return None
    bound = origin[1]
    return bound if isinstance(bound, PredicateMeta) else None


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
        ) from None
    try:
        yield row
    except BaseException as exc:  # noqa: BLE001 — re-raised below
        if not ctx.__exit__(type(exc), exc, exc.__traceback__):
            raise
    else:
        ctx.__exit__(None, None, None)


def _redefinition_error(exc, functor: str, arity: int, pred_cls,
                        origins: dict, module_name: str,
                        module_dict: dict) -> SyntaxError:
    """The load channel's surface exception for a gate refusal."""
    gate_line = str(exc.term.args[1])
    origin = origins.get(functor)
    # P1 (spec 2026-09-17 §2.2), simplification: *pred_cls* arrives already
    # resolved.  Both ``_load_gate`` call sites pass either step 4's
    # isinstance-guarded class or ``_imported_class``'s result, and
    # ``_imported_class`` returns a predicate class or ``None`` — so the type
    # test was a ``None`` check in a type test's clothing.
    if origin is None or pred_cls is None:
        return SyntaxError(gate_line)
    exporter_name = origin[0]
    from clausal.import_diagnostics import (  # noqa: PLC0415
        describe_imported_predicate_redefinition,
    )
    described = describe_imported_predicate_redefinition(
        functor, arity, module_name, exporter_name, pred_cls,
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
    ISO. A target that is a defined PredicateMeta class (e.g. an imported or
    -private-declared predicate) also counts as defined.

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
            cls = module_dict.get(functor)
            if isinstance(cls, PredicateMeta):
                # P4 prerequisite: reached only for a class with NO row -- a
                # predicate visible through a plain Python import.  Goes with
                # the class.
                fields = term_field_names_of_class(cls)
                if fields is not None and len(fields) == arity:
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
    cls = module_dict.get(functor)
    if isinstance(cls, PredicateMeta):
        fields = term_field_names_of_class(cls)
        is_pred = fields is not None and len(fields) == arity
    else:
        is_pred = False

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

    if is_pred and cls._clauses:
        origin = getattr(cls, "__module__", None)
        where = f" (defined in {origin})" if origin else ""
        raise SyntaxError(
            f"-table({functor}/{arity}): {functor}/{arity} is defined in "
            f"another module{where}, and -table only tables the dispatch "
            f"function compiled by the module that declares it — the directive "
            f"would have no effect here.  Move -table({functor}/{arity}) into "
            f"the module that defines {functor}/{arity}."
        )

    if is_pred:
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
    for item in module_items:
        if isinstance(item, (ModuleDeclItem, PrivateDeclItem)):
            entries = (item.exports if isinstance(item, ModuleDeclItem)
                       else item.items)
            for entry in entries:
                if isinstance(entry, tuple) and entry[1]:
                    declared.add((entry[0], len(entry[1])))
                    db.declare_functor(entry[0], tuple(entry[1]))   # P2 Task 2: the registry
    if module_dict is not None:
        # -import_from'd fielded names arrive through the exec-time carrier map
        # (``_make_import_signatures_update_ast``), keyed by LOCAL name.
        from clausal.logic.cells import FUNCTOR_SIGNATURES_KEY  # noqa: PLC0415
        for name, fields in (module_dict.get(FUNCTOR_SIGNATURES_KEY) or {}).items():
            if fields and db.declared_fields(name, len(fields)) is None:
                db.declare_functor(name, tuple(fields))
    for item in module_items:
        if isinstance(item, DirectiveItem):
            method_name = _directive_methods.get(item.name)
            if method_name is not None:
                method = getattr(db, method_name)
                for functor, arity in item.specs:
                    if item.name != "dynamic" and (functor, arity) in declared:
                        db.row(functor, arity, create=True)
                    method(functor, arity)


def _preregister_specializations(
    module_items: list,
    module_dict: dict,
) -> None:
    """Pre-register specialized predicate classes for -specialize directives.

    Creates empty PredicateMeta classes (no clauses, no dispatch) so that
    later clauses can reference the specialized predicate by name during
    compilation at Step 5.
    """
    from clausal.logic.specialization import analyze_mi, _specialized_fields

    for item in module_items:
        if not isinstance(item, SpecializeItem):
            continue

        mi_cls = module_dict.get(item.mi_name)
        if not isinstance(mi_cls, PredicateMeta):
            continue  # Will error in _run_specialization

        # Analyze MI to get field names for the specialized predicate.
        # program_arg is auto-detected by analyze_mi from field names.
        try:
            pattern = analyze_mi(mi_cls)
            fields = _specialized_fields(pattern)
        except Exception:
            continue  # Will error properly in _run_specialization

        # Create and register the empty predicate class.
        if item.new_name not in module_dict:
            cls = make_predicate(item.new_name, fields)
            module_dict[item.new_name] = cls


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

        mi_cls = module_dict.get(item.mi_name)
        if not isinstance(mi_cls, PredicateMeta):
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
        pattern = analyze_mi(mi_cls)

        # Evaluate the source program.
        source_cls = module_dict.get(item.source_program)
        if source_cls is None:
            raise RuntimeError(
                f"-specialize: source program '{item.source_program}' "
                f"not found in module dict"
            )

        if isinstance(source_cls, PredicateMeta):
            # It's a predicate — call it to get the program list.
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

        # Reuse pre-registered class if available.
        existing_cls = module_dict.get(item.new_name)
        if isinstance(existing_cls, PredicateMeta):
            target_cls = existing_cls
        else:
            target_cls = None

        # Run the specializer (deep unfolding if depth > 0, CPD if cpd=True).
        #
        # P3-3 Task 7: ``db=db`` is what makes the specialized predicate THIS
        # module's predicate.  The specializer used to build a Database of its
        # own and drop it, so ``db.row(item.new_name, ...)`` stayed ``None``
        # and the only handle on the predicate was the class in
        # ``module_dict``; the row it now gets is registered, signed and
        # gate-stamped here beside the module's own predicates.
        if item.cpd:
            specialized_cls = specialize_mi_cpd(
                pattern, program_data, item.new_name, module_dict,
                pred_cls=target_cls, max_depth=item.depth or 10, db=db,
            )
        elif item.depth > 0:
            specialized_cls = specialize_mi_deep(
                pattern, program_data, item.new_name, module_dict,
                pred_cls=target_cls, max_depth=item.depth, db=db,
            )
        else:
            specialized_cls = specialize_mi(
                pattern, program_data, item.new_name, module_dict,
                pred_cls=target_cls, db=db,
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
            names.update(functor for functor, _arity in item.specs)
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

    * a genuine ``PredicateMeta`` class already sits in ``module_dict`` —
      an in-file ``_make_functor_class_ast`` exec-time block (a real
      predicate class, whether declared with fields or clause-head-only)
      never leaks cross-module the way a plain atom str does (see below),
      so trusting ``module_dict`` for this shape is safe;
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
    ``Undefined``, ``Compound``, ...) were a separate, deliberate
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
    if strict_mode and implicit_mode:
        raise SyntaxError(
            f"{module_name}: -strict_atoms and -implicit_atoms are mutually "
            f"exclusive; a file may carry at most one"
        )
    # ── NEW in this task ──────────────────────────────────────────────
    # Strict is the default (Python-style): undeclared bare atoms raise
    # unless the file opts into loose auto-mint via -implicit_atoms.
    effective_strict = not implicit_mode
    if strict_mode:
        _warn_strict_atoms_deprecated()
    if implicit_mode:
        _warn_implicit_atoms_deprecated(module_name)
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
            if effective_strict:
                undeclared.append(name)
                continue
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
        "    - obtained via global_atom(\"atom\", Atom)",
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
        if isinstance(item, DirectiveItem):
            names.update(functor for functor, _arity in item.specs)
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


def _process_declarations(module_items: list, module_dict: dict,
                          predicate_functors: set = frozenset()) -> None:
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
      Compound DATA is cells now — a tuple ``("point", 1, 2)`` whose shape
      the module's ``__clausal_functor_signatures__`` registry describes —
      so a data functor needs no class to construct through, and the plain
      interned spelling is bound instead, exactly as a bare atom entry is.
      The don't-clobber guard is what keeps PREDICATES as classes: a
      predicate with in-file clauses already has a real ``PredicateMeta``
      in ``module_dict`` (minted by ``_make_functor_class_ast``, which runs
      during exec, before this pass), and a class that is there is never
      overwritten.

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
                    # statement or an N-arity clause re-minted a genuine
                    # PredicateMeta class over this atom's own -module/
                    # -private line, exec-time, via the guarded block in
                    # ``_make_functor_class_ast``/``_build_zero_arity_fact_
                    # statements``).  The predicate wins -- do not clobber
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
                    if (not isinstance(module_dict.get(entry), PredicateMeta)
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
                # ``-private`` REWRITE emits a ``_make_functor_class_ast``
                # block for every field-carrying export, so by the time this
                # runs EVERY declared functor has one, predicate and data
                # alike.  *predicate_functors* is the real question --
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
                if isinstance(existing, PredicateMeta) and existing._clauses:
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
