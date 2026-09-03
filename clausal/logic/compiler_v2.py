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

import importlib
import warnings
from typing import Any

from clausal.atom_diagnostics import truth_literal_hint_lines
from clausal.logic.database import Module as LogicModule, Clause, head_key
from clausal.logic.compiler import (
    compile_predicate_trampoline,
    compile_predicate_shallow,
)
from clausal.logic.predicate import (
    PredicateMeta, make_predicate, module_source_path, record_clause_source,
    term_field_names_of_class,
)
from clausal.pythonic_ast.nodes import (
    BareAtomRefs as BareAtomRefsItem,
    Directive as DirectiveItem,
    ImportFromDirective as ImportFromItem,
    ImportModuleDirective as ImportModuleItem,
    ModuleDeclaration as ModuleDeclItem,
    OverwritesDeclaration as OverwritesDeclItem,
    PrivateDeclaration as PrivateDeclItem,
    SpecializeDirective as SpecializeItem,
    ImplicitAtomsDeclaration as ImplicitAtomsItem,
    StrictAtomsDeclaration as StrictAtomsItem,
)


class ClausalAtomShadowingWarning(UserWarning):
    """A local ``-module``/``-private`` declaration names an *atom* that is
    also bound by an ``-import_from`` in the same file (Phase 4 of
    GLOBAL_ATOMS_DEFAULT.md).

    The local declaration creates a distinct ``PredicateMeta`` class from
    the imported one, so uses of the name in this module will not unify
    with values from the imported module.  Add the name to
    ``-overwrites([...])`` to silence this warning, or remove the local
    declaration and rely on the import.

    Narrowed trigger: the warning fires only for atom-name (zero-arity)
    shadowing — the case introduced by Phase 2's global-default atom rule.
    Predicate-functor shadowing remains the existing per-module convention
    and is not flagged; see ``GLOBAL_ATOMS_DEFAULT.md`` §"Predicates with
    arity".
    """


class ClausalUnusedOverwritesWarning(UserWarning):
    """An ``-overwrites([...])`` entry names something that is not actually
    shadowing an imported atom in this module (Phase 4 of
    GLOBAL_ATOMS_DEFAULT.md).

    Either remove the entry, or add the redeclaration if that was the
    intent.  Under the narrowed Phase-4 trigger, predicate-functor entries
    in ``-overwrites`` also count as unused: the warning never would have
    fired for a predicate functor, so the entry suppresses nothing.
    """


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


class ClausalAtomIdentityMismatchWarning(ClausalAtomShadowingWarning):
    """Two *declared* atoms with the same name but distinct module-local
    identity were compared during unification (diagnostic aid, opt-in).

    Name resolution for declared atoms is lexical against the *defining*
    module (see ``docs/import.md`` and ``GLOBAL_ATOMS_DEFAULT.md``): two
    modules that each ``-module``/``-private``-declare the same atom hold
    **distinct** classes, so unifying one against the other silently fails —
    no error, no solution.  This is intended scoping, but the failure is
    indistinguishable from a legitimately-unsatisfiable query.

    When ``CLAUSAL_WARN_ATOM_IDENTITY=1`` is set, unification emits this
    (one-shot per name pair) warning naming both owning modules so the
    mismatch is diagnosable.  Remedy: share one definition via
    ``-import_from(defining_module, [Atom])`` instead of re-declaring.

    Subclasses ``ClausalAtomShadowingWarning`` so existing ``-overwrites``
    /warning-filter machinery that targets the family also covers it.
    """


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
    _process_imports(module_items, module_dict)

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
    _process_directives(module_items, db)

    # ── Step 3: Process module/private declarations ──────────────────────
    _process_declarations(module_items, module_dict)

    # ── Step 3b: Auto-mint undeclared bare atom references ───────────────
    #    Phase 2 of GLOBAL_ATOMS_DEFAULT.md.  Must run AFTER declarations
    #    (so module-local atoms shadow the global) and BEFORE clause
    #    compilation (so referenced names resolve in module_dict).
    #    Phase 3: if ``-strict_atoms`` is present in module_items, raise
    #    NameError on undeclared names instead of minting.
    _process_bare_atom_refs(module_items, module_dict, module_name)

    # ── Step 3c: refuse to overwrite an imported predicate's clauses ─────
    #    Must run BEFORE step 4, which mutates the shared class in place: a
    #    refusal that fired halfway through the loop would leave the other
    #    module with a partly-clobbered clause list, which is the very fault
    #    it exists to prevent.
    _reject_redefinition_of_imported_predicates(
        predicate_nodes, module_items, module_dict, module_name)

    # ── Step 4: assertz all clauses ───────────────────────────────────────
    pending: dict[tuple[str, int], PredicateMeta | None] = {}
    for pred_node in predicate_nodes:
        logic_module.define_predicate(pred_node)
        functor, arity = head_key(pred_node.head)
        key = (functor, arity)

        # Sync to PredicateMeta class.
        pred_cls = module_dict.get(functor)
        if isinstance(pred_cls, PredicateMeta):
            db_clauses = db.clauses_for(functor, arity)
            pred_cls._clauses[:] = db_clauses
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
                # Stamp the declared arity on the class whatever its clause
                # state — the ``_refuse_call_at`` fallback only reads it while
                # the clause list is EMPTY, which includes the retract-back-
                # to-empty return leg of a predicate that did have clauses.
                stamped = module_dict.get(functor)
                if isinstance(stamped, PredicateMeta):
                    if stamped._dynamic_arities is None:
                        stamped._dynamic_arities = set()
                    stamped._dynamic_arities.add(arity)
                key = (functor, arity)
                if key in pending:
                    continue
                pred_cls = module_dict.get(functor)
                if (
                    isinstance(pred_cls, PredicateMeta)
                    and len(pred_cls._fields) == arity
                ):
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
    for (functor, arity), pred_cls in pending.items():
        clauses = db.clauses_for(functor, arity)
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
            if pred_cls is not None:
                pred_cls._dispatch_fn = wrapped
            db.set_dispatch(functor, arity, wrapped)

    # ── Step 6b: Meta-interpreter specialization ────────────────────────
    #    Runs after all predicates are compiled so source programs can be
    #    called.  Specialized predicates compile themselves internally.
    _run_specialization(module_items, predicate_nodes, module_dict, db)

    # ── Step 7: Lock non-dynamic predicates ──────────────────────────────
    for obj in module_dict.values():
        if isinstance(obj, PredicateMeta) and hasattr(obj, '_fields'):
            key = (obj.__name__, len(obj._fields))
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


def _process_imports(module_items: list, module_dict: dict) -> None:
    """Execute import directives, populating module_dict."""
    for item in module_items:
        if isinstance(item, ImportFromItem):
            mod = _resolve_module(item.module)
            for name_spec in item.names:
                if isinstance(name_spec, tuple):
                    orig_name, local_name = name_spec
                    value = getattr(mod, orig_name)
                    module_dict[local_name] = value
                    # Also store under the dotted key ("module.OrigName") so
                    # that _inject_call_targets can resolve it when the compiler
                    # emits LoadName(name="module.OrigName") for remapped imports.
                    module_dict[f"{item.module}.{orig_name}"] = value
                else:
                    value = getattr(mod, name_spec)
                    module_dict[name_spec] = value
                    # Dotted key for compiler resolution (e.g. "py.sympy.inf").
                    module_dict[f"{item.module}.{name_spec}"] = value
            # Also store the module object under the user-facing name so
            # that dotted-name resolution (e.g. ``uuid.Uuid4``) works in
            # the compiler's _inject_call_targets.
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
    ``head_key`` hands step 3c ``f`` while the file only ever mentions ``G``.
    Indexing the alias alone let the aliased spelling walk straight past the
    refusal and clobber the exporter through step 5's dispatch assignment,
    with the clause list left intact so the damage was invisible to a clause
    count (found by review, 2026-08-25).
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


def _reject_redefinition_of_imported_predicates(
    predicate_nodes: list, module_items: list, module_dict: dict,
    module_name: str,
) -> None:
    """Refuse a clause for an ``-import_from``'d predicate that another module
    has already supplied clauses for.

    ``-import_from`` binds the exporter's predicate CLASS, and step 4 writes
    this module's clauses straight onto it.  Whatever was there was silently
    overwritten — for the other module's own queries too
    (``todo/done/imported-functor-clause-list-replaced-not-extended.md``).

    Extending instead is not a fix that can be made correct here: the clause
    list is not what answers a goal.  Step 5 compiles ONE dispatch function
    from ONE clause list against ONE ``globals_`` (``globals_=module_dict``),
    so a merged list would mean compiling the other module's clause bodies —
    written against its ``-private`` atoms and its imports — in this module's
    scope.  A merged clause list with an unmerged dispatch function trades a
    visible bug for an invisible one.

    Two shapes are deliberately NOT refused:

    * a **clause-free** import.  That is a declaration — a bare vocabulary
      atom, or a signature whose implementer lives downstream — and supplying
      its clauses is an established idiom in downstream rulebase corpora.
      Nothing is destroyed, so nothing is refused.
    * a **reload of the same file**.  Ownership is keyed on the source path,
      so a file that reaches step 4 twice in one process (dotted import plus
      ``load_clausal_module``, or a straight re-load) re-runs an assignment
      that is idempotent.  Keying it on the module *name* instead is what made
      the previous attempt at this refuse a file beside itself
      (``todo/done/imported-clause-refusal-misattributes-ownership.md``).
    """
    origins = _import_from_origins(module_items, module_dict)
    if not origins:
        return
    here = module_source_path(module_dict)
    checked: set[str] = set()
    for pred_node in predicate_nodes:
        functor, arity = head_key(pred_node.head)
        if functor in checked or functor not in origins:
            continue
        checked.add(functor)
        exporter_name, bound_cls = origins[functor]
        # Under an alias the class is NOT in module_dict under its own functor
        # — the import bound it under the alias — so fall back to the class the
        # import itself bound.
        pred_cls = module_dict.get(functor)
        if not isinstance(pred_cls, PredicateMeta):
            pred_cls = bound_cls
        if not isinstance(pred_cls, PredicateMeta) or not pred_cls._clauses:
            continue
        source = getattr(pred_cls, "_clauses_source", None)
        if source is not None and here is not None and source[1] == here:
            # Our own clauses, from an earlier compile of this same file.
            # Re-running step 4's assignment is idempotent.
            continue
        from clausal.import_diagnostics import (  # noqa: PLC0415
            describe_imported_predicate_redefinition,
        )
        raise SyntaxError(describe_imported_predicate_redefinition(
            functor, arity, module_name, exporter_name, pred_cls,
            exporter_module=module_dict.get(exporter_name),
        ))


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
            cls = module_dict.get(functor)
            fields = term_field_names_of_class(cls)
            if isinstance(cls, PredicateMeta) and fields is not None and len(fields) == arity:
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

    cls = module_dict.get(functor)
    fields = term_field_names_of_class(cls)
    is_pred = isinstance(cls, PredicateMeta) and fields is not None and len(fields) == arity

    if functor in specialize_aliases:
        raise SyntaxError(
            f"-table({functor}/{arity}): {functor} is a -specialize alias, and "
            f"-specialize compiles it against a database of its own that no "
            f"-table directive reaches — the directive would have no effect.  "
            f"Table the meta-interpreter or the object predicate instead, or "
            f"drop the directive."
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


def _process_directives(module_items: list, db: Any) -> None:
    """Apply directive metadata to the database."""
    _directive_methods = {
        "dynamic": "mark_dynamic",
        "discontiguous": "mark_discontiguous",
        "table": "mark_tabled",
        "shallow": "mark_shallow",
    }
    for item in module_items:
        if isinstance(item, DirectiveItem):
            method_name = _directive_methods.get(item.name)
            if method_name is not None:
                method = getattr(db, method_name)
                for functor, arity in item.specs:
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
            raise RuntimeError(
                f"-specialize: meta-interpreter '{item.mi_name}' not found "
                f"in module dict (available: "
                f"{[k for k, v in module_dict.items() if isinstance(v, PredicateMeta)]})"
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
        if item.cpd:
            specialized_cls = specialize_mi_cpd(
                pattern, program_data, item.new_name, module_dict,
                pred_cls=target_cls, max_depth=item.depth or 10,
            )
        elif item.depth > 0:
            specialized_cls = specialize_mi_deep(
                pattern, program_data, item.new_name, module_dict,
                pred_cls=target_cls, max_depth=item.depth,
            )
        else:
            specialized_cls = specialize_mi(
                pattern, program_data, item.new_name, module_dict,
                pred_cls=target_cls,
            )

        # The specialized predicate is already compiled and installed
        # in module_dict by specialize_mi.  No need to inject into
        # predicate_nodes — it's already fully compiled.


def _process_bare_atom_refs(
    module_items: list,
    module_dict: dict,
    module_name: str = "<module>",
) -> None:
    """Auto-mint undeclared bare atom references into the process-wide
    ``predicate_builtins`` dict, then assign each result into ``module_dict``.

    Implements rule 1.4 (global fallthrough) of GLOBAL_ATOMS_DEFAULT.md.
    Every bare ``LoadName`` fallthrough collected by the term-rewriting walker
    arrives here as a ``BareAtomRefs`` module item.  A name is skipped (left
    unminted) when any higher-precedence resolution rule already supplies it:

    * already bound in ``module_dict`` — by imports (Step 0), declarations
      (Step 3), or by an in-file ``_make_functor_class_ast`` exec-time block;
    * registered as a builtin in ``_BUILTINS`` / ``_DB_BUILTINS`` under any
      arity — these resolve through ``get_builtin_predicate`` later in the
      pipeline, and minting them as 0-arity classes would shadow that lookup.

    The collected set is naturally over-broad (it also contains predicate
    functor names and imported-utility names), but that over-collection is
    harmless: the skip rules above filter out every case except the
    genuinely undeclared bare-atom one.

    Phase 3 of GLOBAL_ATOMS_DEFAULT.md: if a ``StrictAtomsItem`` is present
    in ``module_items``, the global-fallthrough mint is disabled.  Names that
    would otherwise have been minted are instead collected and reported as
    a single ``NameError`` with a diagnostic naming each offending atom and
    the file, and suggesting the five legitimate ways to declare or reach
    it (``-module``, ``-private``, ``-import_from``, qualified reference,
    ``global_atom/2``).

    Lazy import of ``predicate_builtins`` — ``clausal.import_hook`` depends
    transitively on this package, so a top-level import would create a cycle
    at package load time.
    """
    from clausal.import_hook import predicate_builtins
    from clausal.logic.builtins._registry import _BUILTINS, _DB_BUILTINS

    builtin_names = {name for (name, _arity) in _BUILTINS}
    builtin_names.update(name for (name, _arity) in _DB_BUILTINS)

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
    undeclared: list[str] = []

    for item in module_items:
        if not isinstance(item, BareAtomRefsItem):
            continue
        for name in item.names:
            if name in module_dict:
                # Higher-precedence rule already supplied this name.
                continue
            if name in builtin_names:
                # Builtin under any arity — resolved by get_builtin_predicate.
                continue
            if effective_strict:
                undeclared.append(name)
                continue
            cls = predicate_builtins.setdefault(
                name, make_predicate(name, [])
            )
            module_dict[name] = cls

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


def _process_declarations(module_items: list, module_dict: dict) -> None:
    """Process -module and -private declarations: create PredicateMeta classes
    and atom assignments.

    A declared atom or predicate always gets a module-local class — even when
    a global-default class for the same name already sits in ``module_dict``
    (placed there by ``module_dict.update(predicate_builtins)`` at exec
    start).  This implements the spec rules of GLOBAL_ATOMS_DEFAULT.md:
    listing in ``-module`` or ``-private`` opts the name into module-local
    identity, distinct from the global default.

    To avoid clobbering a class minted by ``_make_functor_class_ast`` for an
    in-file predicate clause (which runs before this pass), we only override
    when the existing entry is the *global* class for that name — i.e. when
    ``module_dict[name] is predicate_builtins.get(name)``.

    Phase 4 of GLOBAL_ATOMS_DEFAULT.md: after building the local classes,
    cross-check ``-import_from`` bindings against local *atom* declarations
    and emit ``ClausalAtomShadowingWarning`` for the intersection, modulo
    ``-overwrites([...])`` entries.  Names listed in ``-overwrites`` but not
    shadowing an imported atom earn ``ClausalUnusedOverwritesWarning``.  The
    trigger is narrowed to atoms because predicate functors are already
    module-local-by-default and never participated in the Phase 2 global
    flip — shadowing a predicate functor with an import is the existing
    convention, not the new footgun the warning catches.
    """
    # Lazy import — see _process_bare_atom_refs.
    from clausal.import_hook import predicate_builtins

    for item in module_items:
        if isinstance(item, (ModuleDeclItem, PrivateDeclItem)):
            exports = item.exports if isinstance(item, ModuleDeclItem) else item.items
            for entry in exports:
                if isinstance(entry, str):
                    name = entry
                    field_names: tuple | list = ()
                elif isinstance(entry, tuple):
                    name, field_names = entry
                else:
                    continue
                existing = module_dict.get(name)
                # Create a fresh local class when:
                # * no class exists, or
                # * the existing class is the global-default class for this
                #   name (declarations are explicit opt-in to module-local
                #   identity, so they must shadow the global default).
                global_cls = predicate_builtins.get(name)
                if (
                    not isinstance(existing, PredicateMeta)
                    or (existing is global_cls and global_cls is not None)
                ):
                    cls = make_predicate(name, field_names)
                    # Attribute the declared class to its *owning* clausal
                    # module (make_predicate() otherwise stamps __module__ with
                    # clausal.logic.predicate, its defining frame).  Correct
                    # attribution powers the CLAUSAL_WARN_ATOM_IDENTITY
                    # diagnostic, which names both owning modules on a
                    # cross-module same-name atom compare.
                    owner = module_dict.get("__name__")
                    if owner:
                        cls.__module__ = owner
                    module_dict[name] = cls

    _check_atom_shadowing(module_items, module_dict)


def _check_atom_shadowing(module_items: list, module_dict: dict) -> None:
    """Phase 4 shadowing detection: compare ``-import_from`` bindings to local
    atom declarations and emit warnings.

    The check intersects two sets:

    * **Local atom names** — entries in ``-module(...)``/``-private([...])``
      that are bare strings (``isinstance(entry, str)``).  Tuple entries
      (predicate functors) are excluded under the narrowed Phase-4 trigger.
    * **Imported names** — local bindings from ``-import_from``.  For
      ``[Foo]`` this is ``Foo``; for ``[alias(Bar, Local)]`` it is
      ``Local`` (the alias name is what shadows in this module).

    The intersection minus ``-overwrites([...])`` entries earns
    ``ClausalAtomShadowingWarning``.  ``-overwrites`` entries that do not
    correspond to any shadowed atom earn ``ClausalUnusedOverwritesWarning``.

    Warning emission uses ``warnings.warn_explicit`` with ``filename``/
    ``lineno`` from the module's ``__file__`` so each warning carries
    source attribution.  Sorting ``warn_shadowing`` and ``warn_unused_ow``
    before emission keeps warning order deterministic across runs.
    """
    local_atom_names: set[str] = set()
    imported_sources: dict[str, str] = {}  # local_name → source module path
    overwritten: set[str] = set()

    for item in module_items:
        if isinstance(item, ModuleDeclItem):
            for entry in item.exports:
                if isinstance(entry, str):
                    local_atom_names.add(entry)
                # Predicate-functor tuple entries excluded by narrowed
                # Phase-4 trigger.
        elif isinstance(item, PrivateDeclItem):
            for entry in item.items:
                if isinstance(entry, str):
                    local_atom_names.add(entry)
        elif isinstance(item, ImportFromItem):
            for entry in item.names:
                if isinstance(entry, str):
                    imported_sources[entry] = item.module
                elif isinstance(entry, tuple):
                    # ``alias(Orig, Local)`` — the binding in this module is
                    # the *local* name (the second tuple element).
                    _orig, local_name = entry
                    imported_sources[local_name] = item.module
        elif isinstance(item, OverwritesDeclItem):
            for name in item.items:
                overwritten.add(name)

    shadowed = set(imported_sources.keys()) & local_atom_names
    warn_shadowing = shadowed - overwritten
    warn_unused_ow = overwritten - shadowed

    if not warn_shadowing and not warn_unused_ow:
        return

    mod_name = module_dict.get("__name__", "<unknown>")
    file_path = module_dict.get("__file__", "<unknown>")

    for name in sorted(warn_shadowing):
        source_mod = imported_sources[name]
        msg = (
            f"`{mod_name}` redeclares atom `{name}`, which is also imported "
            f"via -import_from(`{source_mod}`, [...]).  The local declaration "
            f"creates a separate class from the imported one — uses in this "
            f"module will not unify with values from `{source_mod}`.  Either "
            f"remove `{name}` from -module(...)/-private([...]) (and rely on "
            f"the import), or add it to -overwrites([...]) to silence this "
            f"warning."
        )
        warnings.warn_explicit(
            msg,
            ClausalAtomShadowingWarning,
            filename=file_path,
            lineno=0,
        )

    for name in sorted(warn_unused_ow):
        msg = (
            f"`{mod_name}` lists `{name}` in -overwrites([...]) but does not "
            f"redeclare an imported atom of that name.  Remove the entry, "
            f"or add the redeclaration if intended."
        )
        warnings.warn_explicit(
            msg,
            ClausalUnusedOverwritesWarning,
            filename=file_path,
            lineno=0,
        )
