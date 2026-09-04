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
import sys
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
            if isinstance(cls, PredicateMeta):
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

    cls = module_dict.get(functor)
    if isinstance(cls, PredicateMeta):
        fields = term_field_names_of_class(cls)
        is_pred = fields is not None and len(fields) == arity
    else:
        is_pred = False

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
      self-mapped atom str for this name — a genuine Python import (Step
      0) or any other legitimately-bound value is trusted as before;
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
    from clausal.import_hook import predicate_builtins
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
    undeclared: list[str] = []

    for item in module_items:
        if not isinstance(item, BareAtomRefsItem):
            continue
        for name in item.names:
            existing = module_dict.get(name, _MISSING)
            if existing is not _MISSING:
                # A leaked-pool-atom shape is a plain str equal to its own
                # name that is STILL the identical object the process pool
                # holds for that name right now — exactly what this
                # function's own auto-mint branch below,
                # ``_process_declarations``, and ``global_atom/2`` all
                # install. Anything else already bound (a real
                # PredicateMeta class, a Python import, any other object)
                # is trusted unconditionally, same as before this fix.
                leaked_pool_atom = (
                    isinstance(existing, str)
                    and existing == name
                    and predicate_builtins.get(name) is existing
                )
                if not leaked_pool_atom or name in local_names:
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
            # Accept the spelling — no class is minted (§1b/R2).  Shared via
            # ``predicate_builtins`` (the same pool ``$intern_atom`` and
            # ``_process_declarations`` use) purely so the SAME str object
            # backs the name everywhere it is auto-accepted; a fresh literal
            # would already compare equal, but sharing the object keeps
            # today's ``mod.x is predicate_builtins["x"]``-shaped pins true.
            module_dict[name] = predicate_builtins.setdefault(name, name)

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
      empty predicate class for it, for exactly the same reason.

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
            for entry in exports:
                if isinstance(entry, str):
                    # Atom: bind the spelling, mint nothing -- UNLESS a
                    # same-named real predicate already exists in
                    # module_dict (Phenomenon A: an in-file 0-arity fact
                    # statement or an N-arity clause re-minted a genuine
                    # PredicateMeta class over this atom's own -module/
                    # -private line, exec-time, via the guarded block in
                    # ``_make_functor_class_ast``/``_build_zero_arity_fact_
                    # statements``).  The predicate wins -- do not clobber
                    # it back to a plain str; see
                    # ``_make_atom_str_assign_ast``'s docstring for the
                    # matching guard on the OTHER direction (a str must
                    # not clobber a real predicate either).
                    if not isinstance(module_dict.get(entry), PredicateMeta):
                        module_dict[entry] = predicate_builtins.setdefault(
                            entry, entry
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
                # spelling needs no shared identity; ``sys.intern`` is kept
                # for the cheap compares, not for identity.
                module_dict[name] = sys.intern(name)
