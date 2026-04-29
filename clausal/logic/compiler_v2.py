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
from typing import Any

from clausal.logic.database import Module as LogicModule, Clause, head_key
from clausal.logic.compiler import (
    compile_predicate_trampoline,
    compile_predicate_shallow,
)
from clausal.logic.predicate import PredicateMeta, make_predicate
from clausal.pythonic_ast.nodes import (
    Directive as DirectiveItem,
    ImportFromDirective as ImportFromItem,
    ImportModuleDirective as ImportModuleItem,
    ModuleDeclaration as ModuleDeclItem,
    PrivateDeclaration as PrivateDeclItem,
    SpecializeDirective as SpecializeItem,
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


def _process_declarations(module_items: list, module_dict: dict) -> None:
    """Process -module and -private declarations: create PredicateMeta classes
    and atom assignments."""
    for item in module_items:
        if isinstance(item, (ModuleDeclItem, PrivateDeclItem)):
            exports = item.exports if isinstance(item, ModuleDeclItem) else item.items
            for entry in exports:
                if isinstance(entry, str):
                    # Atom: create zero-arity PredicateMeta class.
                    if entry not in module_dict or not isinstance(
                        module_dict.get(entry), PredicateMeta
                    ):
                        cls = make_predicate(entry, [])
                        module_dict[entry] = cls
                elif isinstance(entry, tuple):
                    functor_name, field_names = entry
                    if functor_name not in module_dict or not isinstance(
                        module_dict.get(functor_name), PredicateMeta
                    ):
                        cls = make_predicate(functor_name, field_names)
                        module_dict[functor_name] = cls
