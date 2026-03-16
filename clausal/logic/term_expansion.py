"""term_expansion — Apply TermExpansion rules to module items.

TermExpansion/4 clauses match module-level items (Predicate nodes) and
produce rewritten or additional items.  Expansion sits between Phase A
(EmbedTransformer) and Phase B (compile_module) of the pipeline.

Protocol::

    TermExpansion(TERM, EXPANSION, MODULE_BEFORE, MODULE_AFTER)

- TERM: runtime Predicate node being expanded
- EXPANSION: single Predicate, list of Predicates, or atom ``"none"`` (suppress)
- MODULE_BEFORE: ``ModuleExpansionState(InitList, FinalList, UserState)``
- MODULE_AFTER: same, updated

Module state is threaded through all items left-to-right.  Items that
match no TermExpansion rule pass through unchanged.  TermExpansion clauses
themselves are not expanded.
"""

from __future__ import annotations

from typing import Any

from clausal.logic.database import Module as LogicModule, Clause, head_key
from clausal.logic.compiler import compile_predicate_trampoline
from clausal.logic.predicate import PredicateMeta, make_predicate
from clausal.logic.variables import Var, Trail, deref, unify
from clausal.pythonic_ast.nodes import Predicate as PredicateItem


def _is_term_expansion_clause(pred_node) -> bool:
    """True if pred_node defines a TermExpansion/4 clause."""
    head = pred_node.head
    from clausal.terms import Call, LoadName
    if isinstance(head, Call) and isinstance(head.func, LoadName):
        return head.func.name == "TermExpansion" and len(head.args) == 4
    # Also check PredicateMeta instances
    if isinstance(type(head), PredicateMeta):
        return type(head).__name__ == "TermExpansion" and len(type(head)._fields) == 4
    return False


def run_term_expansion(
    predicate_nodes: list,
    module_dict: dict,
) -> list:
    """Apply TermExpansion rules to predicate nodes.

    Separates TermExpansion clauses from regular items, compiles the
    expansion rules, then applies them to each regular item.

    Also checks ``module_dict`` for imported modules whose LogicModule
    carries ``_te_predicate_nodes`` — these are TermExpansion clauses
    from ``-import_from`` directives processed earlier in the pipeline.

    Returns the (possibly rewritten) list of predicate nodes.  If no
    TermExpansion clauses exist, returns predicate_nodes unchanged
    (zero overhead).

    Parameters
    ----------
    predicate_nodes : list
        Runtime Predicate (simple_ast) nodes from Phase A.
    module_dict : dict
        The module's __dict__ (for resolving types in compilation).

    Returns
    -------
    list
        Expanded list of predicate nodes.
    """
    # Step 1: Separate TermExpansion clauses from regular items.
    expansion_clauses = []
    regular_items = []
    for node in predicate_nodes:
        if _is_term_expansion_clause(node):
            expansion_clauses.append(node)
        else:
            regular_items.append(node)

    # Step 1b: Check for imported TermExpansion rules.
    imported_te_clauses = _collect_imported_te_clauses(module_dict)

    # Step 2: If no expansion clauses (local or imported), return unchanged.
    if not expansion_clauses and not imported_te_clauses:
        return predicate_nodes

    # Step 3: Compile TermExpansion clauses into a mini logic module.
    # Imported rules come first (lower priority), then local rules.
    all_te_clauses = imported_te_clauses + expansion_clauses
    expansion_module = _compile_expansion_rules(all_te_clauses, module_dict)

    # Store local TE predicate nodes for downstream importers.
    # Attach to both the LogicModule and the TermExpansion class (if present)
    # so that -import_from(mod, [TermExpansion]) can pick them up.
    if expansion_clauses:
        lm = module_dict.get("$module")
        if lm is not None:
            lm._te_predicate_nodes = list(expansion_clauses)
        te_cls = module_dict.get("TermExpansion")
        if isinstance(te_cls, PredicateMeta):
            te_cls._te_predicate_nodes = list(expansion_clauses)

    # Step 4: Initialize module state: ModuleExpansionState([], [], "nil")
    # Use the same class from the expansion module so unification works.
    mod_cls = expansion_module.module_dict["ModuleExpansionState"]
    module_state = mod_cls([], [], "nil")

    # Step 5: Expand each regular item.
    expanded = []
    for item in regular_items:
        result, module_state = _expand_item(item, expansion_module, module_state)
        if result is None:
            # Suppressed (expansion returned "none").
            continue
        if isinstance(result, list):
            expanded.extend(result)
        else:
            expanded.append(result)

    # Step 6: Extract Init + Final items from final module state.
    init_items, final_items = _extract_init_final(module_state)

    return init_items + expanded + final_items


def _collect_imported_te_clauses(module_dict: dict) -> list:
    """Collect TermExpansion predicate nodes from imported modules.

    Checks two sources:
    1. Python modules in ``module_dict`` whose ``$module`` LogicModule
       carries ``_te_predicate_nodes``.
    2. PredicateMeta classes named ``TermExpansion`` that carry
       ``_te_predicate_nodes`` (set when a module with TE rules is loaded).

    This allows both ``-import_module(mod)`` and
    ``-import_from(mod, [TermExpansion])`` to provide expansion rules.
    """
    import types
    seen = set()  # avoid duplicates
    result = []

    for value in module_dict.values():
        # Case 1: imported Python module with $module
        if isinstance(value, types.ModuleType):
            lm = value.__dict__.get("$module")
            if lm is not None:
                te_nodes = getattr(lm, "_te_predicate_nodes", None)
                if te_nodes and id(te_nodes) not in seen:
                    seen.add(id(te_nodes))
                    result.extend(te_nodes)
        # Case 2: imported TermExpansion PredicateMeta class
        elif (
            isinstance(value, PredicateMeta)
            and getattr(value, "__name__", "") == "TermExpansion"
        ):
            te_nodes = getattr(value, "_te_predicate_nodes", None)
            if te_nodes and id(te_nodes) not in seen:
                seen.add(id(te_nodes))
                result.extend(te_nodes)

    return result


def _make_module_state(init_list, final_list, user_state):
    """Create a ModuleExpansionState(Init, Final, State) term."""
    module_cls = make_predicate("ModuleExpansionState", ["init", "final", "state"])
    return module_cls(init_list, final_list, user_state)


def _compile_expansion_rules(expansion_clauses, module_dict):
    """Compile TermExpansion clauses into a mini LogicModule."""
    from clausal.logic.database import Module as LogicModule
    from clausal.logic.builtins import structural_unify

    lm = LogicModule("_term_expansion_", module_dict=dict(module_dict))
    # Use structural_unify so PredicateMeta terms (e.g. module state) can be
    # destructured in TE clause bodies.  C-level unify only handles Var/list/tuple.
    lm.module_dict["unify"] = structural_unify

    # Create the TermExpansion PredicateMeta class.
    te_cls = make_predicate("TermExpansion", ["term", "expansion", "module_before", "module_after"])
    lm.module_dict["TermExpansion"] = te_cls

    # Also ensure ModuleExpansionState class exists for state threading.
    mod_cls = make_predicate("ModuleExpansionState", ["init", "final", "state"])
    lm.module_dict["ModuleExpansionState"] = mod_cls

    # Assert each expansion clause.
    for pred_node in expansion_clauses:
        lm.define_predicate(pred_node)

    # Compile the expansion predicate.
    functor, arity = "TermExpansion", 4
    clauses = lm.db.clauses_for(functor, arity)
    if clauses:
        compile_predicate_trampoline(
            functor, arity, clauses, lm.db,
            globals_=lm.module_dict, pred_cls=te_cls,
        )

    return lm


def _expand_item(item, expansion_module, module_state):
    """Try to expand a single item using TermExpansion rules.

    Returns (expanded_result, new_module_state).
    expanded_result is:
    - A single Predicate node (replacement)
    - A list of Predicate nodes (one-to-many)
    - None (suppressed)
    - The original item (no match)
    """
    from clausal.logic.solve import call

    term_var = item  # The actual Predicate node
    expansion_var = Var()
    state_before = module_state
    state_after = Var()

    # Try to solve TermExpansion(item, Expansion_, state_before, state_after).
    found = False
    for trail in call(
        "TermExpansion", term_var, expansion_var, state_before, state_after,
        module=expansion_module,
    ):
        # Committed choice: use first solution.
        expansion = deref(expansion_var)
        new_state = deref(state_after)
        found = True
        break

    if not found:
        # No match: pass through unchanged.
        return item, module_state

    # Process expansion result.
    if expansion == "none":
        return None, new_state

    if isinstance(expansion, list):
        return expansion, new_state

    # Single replacement.
    return expansion, new_state


def _extract_init_final(module_state):
    """Extract init and final item lists from the final module state."""
    from clausal.logic.variables import deref as _deref
    try:
        init = _deref(getattr(module_state, 'init', []))
        final = _deref(getattr(module_state, 'final', []))
    except (AttributeError, TypeError):
        init, final = [], []

    init = _flatten_cons_list(init)
    final = _flatten_cons_list(final)

    return init, final


def _flatten_cons_list(value):
    """Convert a possibly-cons Python list to a flat list of items.

    Clausal ``[H | T]`` produces a Python list ``[BitOr(H, T)]``.
    Walk the chain to collect all heads.  Plain lists pass through.
    """
    from clausal.logic.variables import deref as _deref
    from clausal.pythonic_ast.nodes import BitOr

    if not isinstance(value, list):
        return []

    result = []
    for item in value:
        item = _deref(item)
        if isinstance(item, BitOr):
            # Walk the cons chain: BitOr(head, tail)
            node = item
            while isinstance(node, BitOr):
                result.append(_deref(node.left))
                node = _deref(node.right)
            # Tail: if it's a non-empty list, extend
            if isinstance(node, list):
                result.extend(_flatten_cons_list(node))
        else:
            result.append(item)
    return result
