"""compiler_v2 — Module-level compilation from ModuleAST.

Drives compilation from a list of ModuleItems (Predicate nodes, Directive
descriptors, Import descriptors) produced by EmbedTransformer.

The old pipeline (exec bytecode → $define_predicate → _compile_all_pending)
is replaced by:

    compile_module(predicate_nodes, module_items, module_dict, module_name)

which handles directives, class creation, clause assertion, predicate
compilation, tabling wraps, and locking in a single pass.
"""

from __future__ import annotations

import importlib
import warnings
from typing import Any

from clausal.logic.database import Module as LogicModule, Clause, head_key
from clausal.logic.compiler import (
    compile_predicate_trampoline,
    compile_predicate_shallow,
)
from clausal.logic.predicate import PredicateMeta, make_predicate
from clausal.pythonic_ast.nodes import (
    BareAtomRefs as BareAtomRefsItem,
    Directive as DirectiveItem,
    ImportFromDirective as ImportFromItem,
    ImportModuleDirective as ImportModuleItem,
    ModuleDeclaration as ModuleDeclItem,
    OverwritesDeclaration as OverwritesDeclItem,
    PrivateDeclaration as PrivateDeclItem,
    SpecializeDirective as SpecializeItem,
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
            if pred_cls._signature is None:
                pred_cls._signature = pred_cls._fields
            pending[key] = pred_cls
        else:
            pending[key] = None

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
    for (functor, arity), pred_cls in pending.items():
        if db.is_tabled(functor, arity):
            from clausal.logic.tabling import make_tabled_wrapper_trampoline
            original_fn = (
                pred_cls._get_dispatch() if pred_cls is not None
                else db.get_dispatch(functor, arity)
            )
            wrapped = make_tabled_wrapper_trampoline(
                original_fn, functor, arity, db.table_store,
            )
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
    "uuid": "uuid_mod",
    "yaml": "yaml",
    "spacy": "spacy",
    "sympy": "sympy",
    "scipy_cluster": "scipy_cluster",
    "scipy_constants": "scipy_constants",
    "scipy_differentiate": "scipy_differentiate",
    "scipy_fft": "scipy_fft",
    "scipy_integrate": "scipy_integrate",
    "scipy_interpolate": "scipy_interpolate",
    "scipy_linalg": "scipy_linalg",
    "scipy_ndimage": "scipy_ndimage",
    "scipy_optimize": "scipy_optimize",
    "scipy_signal": "scipy_signal",
    "scipy_sparse": "scipy_sparse",
    "scipy_spatial": "scipy_spatial",
    "scipy_special": "scipy_special",
    "scipy_stats": "scipy_stats",
    "torch": "torch",
    "torch_nn": "torch_nn",
    "torch_data": "torch_data",
    "torch_functional": "torch_functional",
    "torch_distributions": "torch_distributions",
    "jax": "jax",
    "jax_random": "jax_random",
    "jax_nn": "jax_nn",
    "jax_transforms": "jax_transforms",
    "jax_scipy": "jax_scipy",
    "jax_sharding": "jax_sharding",
    "jax_tree": "jax_tree",
    "jax_optax": "jax_optax",
    "jax_equinox": "jax_equinox",
    "jax_flax": "jax_flax",
    "sklearn": "sklearn",
}


def _resolve_module(module_path: str):
    """Import a module, trying clausal.modules first (with alias mapping)."""
    mapped = _MODULE_ALIASES.get(module_path, module_path)
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
            if strict_mode:
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
