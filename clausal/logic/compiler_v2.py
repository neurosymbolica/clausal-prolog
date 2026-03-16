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

    # ── Step 0: Term expansion (before directive processing) ────────────
    from clausal.logic.term_expansion import run_term_expansion
    predicate_nodes = run_term_expansion(predicate_nodes, module_dict)

    # ── Step 1: Process imports ──────────────────────────────────────────
    _process_imports(module_items, module_dict)

    # ── Step 2: Process directives ───────────────────────────────────────
    _process_directives(module_items, db)

    # ── Step 3: Process module/private declarations ──────────────────────
    _process_declarations(module_items, module_dict)

    # ── Step 4: Assert all clauses ───────────────────────────────────────
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

    # ── Step 7: Lock non-dynamic predicates ──────────────────────────────
    for obj in module_dict.values():
        if isinstance(obj, PredicateMeta) and hasattr(obj, '_fields'):
            key = (obj.__name__, len(obj._fields))
            if not db.is_dynamic(*key):
                obj._lock()

    return logic_module


def _process_imports(module_items: list, module_dict: dict) -> None:
    """Execute import directives, populating module_dict."""
    for item in module_items:
        if isinstance(item, ImportFromItem):
            mod = importlib.import_module(item.module)
            for name_spec in item.names:
                if isinstance(name_spec, tuple):
                    orig_name, local_name = name_spec
                    module_dict[local_name] = getattr(mod, orig_name)
                else:
                    module_dict[name_spec] = getattr(mod, name_spec)
        elif isinstance(item, ImportModuleItem):
            mod = importlib.import_module(item.module)
            # Store the top-level name (e.g., "foo" for "foo.bar.baz").
            top_name = item.module.split(".")[0]
            module_dict[top_name] = importlib.import_module(top_name)


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


def _process_declarations(module_items: list, module_dict: dict) -> None:
    """Process -module and -private declarations: create PredicateMeta classes
    and atom assignments."""
    for item in module_items:
        if isinstance(item, (ModuleDeclItem, PrivateDeclItem)):
            exports = item.exports if isinstance(item, ModuleDeclItem) else item.items
            for entry in exports:
                if isinstance(entry, str):
                    # Atom: assign string to module dict.
                    module_dict.setdefault(entry, entry)
                elif isinstance(entry, tuple):
                    functor_name, field_names = entry
                    if functor_name not in module_dict or not isinstance(
                        module_dict.get(functor_name), PredicateMeta
                    ):
                        cls = make_predicate(functor_name, field_names)
                        module_dict[functor_name] = cls
