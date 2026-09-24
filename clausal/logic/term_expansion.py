"""term_expansion — Apply term_expansion rules to module items.

term_expansion/4 clauses match module-level items (Predicate nodes) and
produce rewritten or additional items.  Expansion sits between Phase A
(EmbedTransformer) and Phase B (compile_module) of the pipeline.

Protocol::

    term_expansion(TERM, EXPANSION, MODULE_BEFORE, MODULE_AFTER)

- TERM: runtime Predicate node being expanded
- EXPANSION: single Predicate, list of Predicates, or the atom ``none`` (suppress)
- MODULE_BEFORE: ``module_expansion_state(InitList, FinalList, UserState)``
- MODULE_AFTER: same, updated

Module state is threaded through all items left-to-right.  Items that
match no term_expansion rule pass through unchanged.  term_expansion clauses
themselves are not expanded.
"""

from __future__ import annotations

from typing import Any

from clausal.logic.atoms import mint as _mint
from clausal.logic.database import Module as LogicModule, Clause, head_key
from clausal.logic.compiler import compile_predicate_trampoline
from clausal.logic.variables import Var as _Var
from clausal.logic.predicate import PredicateMeta, make_predicate
from clausal.logic.builtins._helpers import functor_arity
from clausal.logic.variables import Var, Trail, deref, unify
from clausal.pythonic_ast.nodes import Predicate as PredicateItem

#: The suppression sentinel, as the ATOM the compiler emits for ``none``.
_NONE_ATOM = _mint("none")


def _is_term_expansion_clause(pred_node) -> bool:
    """True if pred_node defines a term_expansion/4 clause."""
    head = pred_node.head
    from clausal.terms import Call, LoadName
    from clausal.logic.cells import compound_cell_shape  # noqa: PLC0415
    if isinstance(head, Call) and isinstance(head.func, LoadName):
        return head.func.name == "term_expansion" and len(head.args) == 4
    is_cell, functor = compound_cell_shape(head)      # P2: a head is a cell
    if is_cell:
        return functor == "term_expansion" and len(head) - 1 == 4
    # Also check PredicateMeta instances (pre-flip shape; goes with the class)
    if isinstance(type(head), PredicateMeta):
        return functor_arity(head) == ("term_expansion", 4)
    return False


def run_term_expansion(
    predicate_nodes: list,
    module_dict: dict,
) -> list:
    """Apply term_expansion rules to predicate nodes.

    Separates term_expansion clauses from regular items, compiles the
    expansion rules, then applies them to each regular item.

    Also checks ``module_dict`` for imported modules whose LogicModule
    carries ``_te_predicate_nodes`` — these are term_expansion clauses
    from ``-import_from`` directives processed earlier in the pipeline.

    Returns the (possibly rewritten) list of predicate nodes.  If no
    term_expansion clauses exist, returns predicate_nodes unchanged
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
    # Step 1: Separate term_expansion clauses from regular items.
    expansion_clauses = []
    regular_items = []
    for node in predicate_nodes:
        if _is_term_expansion_clause(node):
            expansion_clauses.append(node)
        else:
            regular_items.append(node)

    # Step 1b: Check for imported term_expansion rules.
    imported_te_clauses = _collect_imported_te_clauses(module_dict)

    # Step 2: If no expansion clauses (local or imported), return unchanged.
    if not expansion_clauses and not imported_te_clauses:
        return predicate_nodes

    # Step 3: Compile term_expansion clauses into a mini logic module.
    # Imported rules come first (lower priority), then local rules.
    all_te_clauses = imported_te_clauses + expansion_clauses
    expansion_module = _compile_expansion_rules(all_te_clauses, module_dict)

    # Store local TE predicate nodes for downstream importers, on the
    # term_expansion class, so that -import_from(mod, [term_expansion]) can
    # pick them up.  NOT on ``$module``: that write used to land on the import
    # hook's PLACEHOLDER module (thrown away after compile), so a bare
    # ``-import_module(mod)`` never carried TE rules.  Once compile_module
    # installs the real module first (``_install_real_module``) the write
    # would have started to reach importers -- a silent change of which
    # imports bring expansion rules.  Only a by-name import does.
    if expansion_clauses:
        te_cls = module_dict.get("term_expansion")
        if isinstance(te_cls, PredicateMeta):
            te_cls._te_predicate_nodes = list(expansion_clauses)

    # Step 4: Initialize module state: module_expansion_state([], [], "nil")
    # Use the same class from the expansion module so unification works.
    mod_cls = expansion_module.module_dict["module_expansion_state"]
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
    """Collect term_expansion predicate nodes from imported modules.

    The source is a ``PredicateMeta`` class named ``term_expansion`` that
    carries ``_te_predicate_nodes`` (set when a module with TE rules is
    loaded), i.e. ``-import_from(mod, [term_expansion])``.  A bare
    ``-import_module(mod)`` does not provide expansion rules: the
    ``$module``-borne route this function used to check was only ever
    written onto the import hook's placeholder module, so it never fired.
    """
    seen = set()  # avoid duplicates
    result = []

    for value in module_dict.values():
        if (
            isinstance(value, PredicateMeta)
            and getattr(value, "__name__", "") == "term_expansion"
        ):
            te_nodes = getattr(value, "_te_predicate_nodes", None)
            if te_nodes and id(te_nodes) not in seen:
                seen.add(id(te_nodes))
                result.extend(te_nodes)

    return result


#: The field order of the ``module_expansion_state`` term, in one place.
_MODULE_STATE_FIELDS = ("init", "final", "state")

_FRESH = object()


def module_expansion_state(init=_FRESH, final=_FRESH, state=_FRESH):
    """The ``module_expansion_state(Init, Final, State)`` TERM.

    A constructor, not a ``make_predicate`` class.  It was never a predicate
    -- no clauses, never a goal -- and post-P2 the class built a cell anyway,
    so all the class added was a ``PredicateMeta`` with no Database row, i.e.
    a private throwaway row on the first facade read.  ``_make_module_state``
    minted a FRESH CLASS on every call to construct one term.

    Keeps what the class did: positional, keyword, partial construction
    filling the missing trailing fields with fresh variables (TE clause
    bodies destructure this by unification), and ``TypeError`` on a
    misspelled field.
    """
    return ("module_expansion_state",
            _Var() if init is _FRESH else init,
            _Var() if final is _FRESH else final,
            _Var() if state is _FRESH else state)


def _data_functor_ctor(functor: str, arity: int):
    """A constructor for a data functor whose NAME is only known here.

    The expansion patterns can introduce a brand-new functor (a
    ``logged_fact`` an expansion invents), and constructing it at expansion
    time needs SOMETHING CALLABLE bound to the name -- the globals placeholder
    raises "not in scope as a term class" when nothing is.  A
    ``make_predicate`` class satisfied that and left a row-less
    ``PredicateMeta`` behind; a constructor satisfies it and does not.

    Keeps the class's behaviour: positional, the ``arg0..argN-1`` keyword
    names it generated, partial construction filling the rest with fresh
    variables, and ``TypeError`` rather than a silent drop.
    """
    fields = tuple(f"arg{i}" for i in range(arity))

    def ctor(*args, **kwargs):
        if len(args) > arity:
            raise TypeError(
                f"{functor}() takes at most {arity} positional argument"
                f"{'' if arity == 1 else 's'} ({len(args)} given)")
        slots = list(args) + [_FRESH] * (arity - len(args))
        for key, value in kwargs.items():
            if key not in fields:
                raise TypeError(
                    f"{functor}() got an unexpected keyword argument {key!r}")
            index = fields.index(key)
            if index < len(args):
                raise TypeError(
                    f"{functor}() got multiple values for argument {key!r}")
            slots[index] = value
        return (functor, *(_Var() if slot is _FRESH else slot
                           for slot in slots))

    ctor.__name__ = functor
    ctor.__qualname__ = functor
    ctor._fields = fields
    return ctor


def _make_module_state(init_list, final_list, user_state):
    """Create a module_expansion_state(Init, Final, State) term."""
    return module_expansion_state(init_list, final_list, user_state)


def _collect_functor_arities(node, out: dict, seen: set) -> None:
    """Collect ``functor_name -> arity`` for every ``Call(LoadName(name), args)``
    reachable from *node* (term-instances, lists, and pythonic_ast Nodes are
    all descended). Names are ordinary lowercase functor identifiers — the
    quasi-quote ``q`` wrapper is already stripped to plain Call data by the
    time term_expansion clauses reach here."""
    from clausal.pythonic_ast.nodes import Call as _Call, LoadName as _LoadName
    from clausal.logic.predicate import is_term_instance, term_field_names
    from clausal.logic.cells import compound_cell_shape  # noqa: PLC0415

    if id(node) in seen:
        return
    seen.add(id(node))

    _is_cell, _cell_functor = compound_cell_shape(node)
    if _is_cell:
        # P2: an expansion pattern's terms are CELLS now, not Call nodes, so
        # without this arm the whole collection came back EMPTY and nothing
        # was pre-minted -- which is the "not in scope as a term class"
        # failure this pre-mint exists to prevent, arriving by a new route.
        # Same recognition rule as the Call arm: an ordinary lowercase
        # functor identifier, recorded at the arity it is WRITTEN at.
        if (_cell_functor.isidentifier() and _cell_functor[:1].islower()
                and not _cell_functor.startswith("_")):
            out.setdefault(_cell_functor, len(node) - 1)
        for a in node[1:]:
            _collect_functor_arities(a, out, seen)
        return

    if isinstance(node, _Call):
        func = node.func
        if isinstance(func, _LoadName):
            nm = func.name
            if nm.isidentifier() and nm[:1].islower() and not nm.startswith("_"):
                out.setdefault(nm, len(node.args))
        for a in node.args:
            _collect_functor_arities(a, out, seen)
        return
    if isinstance(node, list):
        for elem in node:
            _collect_functor_arities(elem, out, seen)
        return
    if is_term_instance(node):
        for fname in term_field_names(node):
            _collect_functor_arities(getattr(node, fname), out, seen)
        return
    children = getattr(node, "children", None)
    if callable(children):
        try:
            kids = children()
        except Exception:
            kids = []
        for kid in kids:
            _collect_functor_arities(kid, out, seen)


def _term_expansion_module(module_dict):
    """Mint the synthetic ``_term_expansion_`` LogicModule and its term class.

    Split out from ``_compile_expansion_rules`` (W4b-1) so a caller — or a
    test — can build the module and its ``term_expansion`` class without
    running an actual expansion.
    """
    from clausal.logic.database import Module as LogicModule
    from clausal.logic.builtins import structural_unify

    lm = LogicModule("_term_expansion_", module_dict=dict(module_dict))
    # Use structural_unify so PredicateMeta terms (e.g. module state) can be
    # destructured in TE clause bodies.  C-level unify only handles Var/list/tuple.
    lm.module_dict["unify"] = structural_unify

    # Create the term_expansion PredicateMeta class.
    te_cls = make_predicate("term_expansion", ["term", "expansion", "module_before", "module_after"])
    lm.module_dict["term_expansion"] = te_cls
    # W4b-1: register the declaration on the synthetic module's own db, so
    # ``term_expansion/4`` is answerable by NAME and not only off the class.
    lm.db.declare_functor(
        "term_expansion", ("term", "expansion", "module_before", "module_after"))

    # Also ensure module_expansion_state is constructible for state threading.
    # A CONSTRUCTOR, not a class: the globals placeholder that raises "not in
    # scope as a term class" fires when nothing CALLABLE is bound to the name,
    # so a function satisfies it and leaves no row-less PredicateMeta behind.
    lm.module_dict["module_expansion_state"] = module_expansion_state
    return lm


def _compile_expansion_rules(expansion_clauses, module_dict):
    """Compile term_expansion clauses into a mini LogicModule."""
    lm = _term_expansion_module(module_dict)
    te_cls = lm.module_dict["term_expansion"]

    # A10-F008 / A10-D004(a): pre-mint term classes for functors referenced in
    # the (quasi-quoted) expansion patterns — e.g. a brand-new ``logged_fact``
    # introduced by an expansion. Without this, constructing ``logged_fact(X)``
    # at expansion time fails with "not in scope as a term class".
    functor_arities: dict[str, int] = {}
    _seen_ids: set = set()
    for pred_node in expansion_clauses:
        _collect_functor_arities(pred_node, functor_arities, _seen_ids)
    for name, arity in functor_arities.items():
        if name not in lm.module_dict:
            lm.module_dict[name] = _data_functor_ctor(name, arity)

    # assertz each expansion clause.
    for pred_node in expansion_clauses:
        lm.define_predicate(pred_node)

    # Compile the expansion predicate.
    functor, arity = "term_expansion", 4
    clauses = lm.db.clauses_for(functor, arity)
    if clauses:
        # BIND THE ROW FIRST.  The clauses were asserted into ``lm.db``, so
        # this class IS the compiled face of a stored predicate and
        # ``_bind_row`` is the documented call for that.  Without it the
        # class is still on NO row when the compile writes ``_index_plans``
        # through the facade, which minted a private detached row -- 4 of the
        # 12 detached rows over 56 fixtures came from here -- and the index
        # plans then landed on a throwaway instead of on ``lm.db``'s row.
        te_cls._bind_row(lm.db, functor, arity)
        compile_predicate_trampoline(
            functor, arity, clauses, lm.db,
            globals_=lm.module_dict, pred_cls=te_cls,
        )

    return lm


def _expand_item(item, expansion_module, module_state):
    """Try to expand a single item using term_expansion rules.

    Returns (expanded_result, new_module_state).
    expanded_result is:
    - A single Predicate node (replacement)
    - A list of Predicate nodes (one-to-many)
    - None (suppressed)
    - The original item (no match)
    """
    # First try matching the whole Predicate item (var / Predicate patterns).
    result = _try_te_match(item, item, expansion_module, module_state,
                           wrap_head=False)
    if result is not None:
        return result

    # A10-F008 / A10-D004(a): a bare-term pattern like ``q(fact(X))`` never
    # unifies with the whole Predicate item (which is Predicate(head=fact(..),
    # body=..)). Retry against the item's HEAD; the expansion terms are then
    # head terms, so wrap each back into a fact Predicate.
    head = getattr(item, "head", None)
    if head is not None:
        result = _try_te_match(item, head, expansion_module, module_state,
                               wrap_head=True)
        if result is not None:
            return result

    # No match: pass through unchanged.
    return item, module_state



def _head_as_cell(term: Any) -> Any:
    """Lower a clause-HEAD term instance to its cell for matching.

    A NO-OP for a predicate head since W4a (2026-09-22): a head is a cell,
    and the predicate-INSTANCE shape this was written for cannot be built any
    more.  What it still lowers is a ``@dataclass`` term that is not one of
    the three excluded carriers, which is why it stays rather than going with
    the bridge.

    The defect it was written for: every TERM a term_expansion pattern
    compiles to is a cell since Task 3 (``cell_signature_for_name`` answers
    for a predicate functor too), while the clause-HEAD channel still carried
    instances.  So an item whose functor HAS clauses arrived as an instance
    and did not unify with the cell its own pattern built:
    ``term_expansion(q(key(KEY)), ...)`` silently matched nothing, and the
    module loaded with the expansion's output missing.

    Only the TOP term is lowered: nested arguments compile to cells already,
    and the lift back is not needed here -- a cell head reaching the store is
    stored as the cell it is (the head channel takes cells since the P2
    head flip; ``Database._with_instance_head`` is gone with it).
    """
    from clausal.logic.predicate import is_term_instance, term_field_names
    from clausal.terms import Compound, Call as TermCall, KWTerm
    if is_term_instance(term) and not isinstance(term, (Compound, TermCall, KWTerm)):
        return (type(term).__name__,
                *(getattr(term, f) for f in term_field_names(term)))
    return term


def _try_te_match(item, match_target, expansion_module, module_state, wrap_head):
    """Solve term_expansion(match_target, Expansion, S0, S) once.

    Returns (expanded_result, new_state) on a match, or None if no clause
    matched *match_target*. When *wrap_head* is True the expansion terms are
    head terms (the pattern matched item.head) and are wrapped into fact
    Predicate nodes.
    """
    from clausal.logic.solve import call

    # P2 Task 4: the patterns are cells, a head is still an instance.  Only
    # the HEAD-pattern retry is lowered: a whole-item pattern binds the
    # Predicate NODE, and rebuilding that node with a lowered head hands the
    # rules a copy -- the identity and pass-through expansions return the term
    # they matched, and three of them went red on the copy.  A quoted RULE
    # pattern (``q(key(K) <- Body)``) would want the same lowering one level
    # in; no fixture or corpus file writes one, and it is parked in
    # todo/term-expansion-whole-item-pattern-head-representation-2026-09-19.md.
    if wrap_head:
        match_target = _head_as_cell(match_target)

    expansion_var = Var()
    state_after = Var()
    found = False
    for _trail in call(
        "term_expansion", match_target, expansion_var, module_state, state_after,
        module=expansion_module,
    ):
        expansion = deref(expansion_var)   # committed choice: first solution
        new_state = deref(state_after)
        found = True
        break

    if not found:
        return None

    # THE FLIP (spec §6.4): ``none`` is a sentinel NAME, so it is an ATOM.
    # A plain ``str`` is a string (the char list) and is NOT the sentinel —
    # a chars-mode module writes the sentinel ``none`` or ``'none'``.
    if expansion == _NONE_ATOM:
        return None, new_state
    if isinstance(expansion, list):
        if wrap_head:
            expansion = [_wrap_as_predicate(e) for e in expansion]
        return expansion, new_state
    if wrap_head:
        return _wrap_as_predicate(expansion), new_state
    return expansion, new_state


def _wrap_as_predicate(term):
    """Wrap a head term into a fact Predicate; pass a Predicate through."""
    term = deref(term)
    if isinstance(term, PredicateItem):
        return term
    return PredicateItem(head=term, body=True)


def _extract_init_final(module_state):
    """Extract init and final item lists from the final module state.

    P2: the state carrier is a CELL -- ``('module_expansion_state', Init,
    Final, State)`` -- so Init and Final are read at their POSITIONS.

    The ``getattr(module_state, 'init', [])`` this replaces was fail-open in
    the worst way available: a cell has no ``.init``, so the DEFAULT answered,
    both lists came back empty, and the whole init/final injection produced
    NOTHING -- silently, with the module loading fine and no error anywhere.
    It is what kept ``instances=True`` load-bearing on this carrier.
    """
    from clausal.logic.variables import deref as _deref
    from clausal.logic.cells import compound_cell_shape, cell_args  # noqa: PLC0415

    is_cell, _functor = compound_cell_shape(module_state)
    if is_cell:
        args = cell_args(module_state)
        # Positions 0 and 1 are Init and Final; a carrier too short to hold
        # them is not this term, and falls through to the empty pair below.
        if len(args) >= 2:
            init, final = _deref(args[0]), _deref(args[1])
        else:
            init, final = [], []
    else:
        # The pre-P2 INSTANCE carrier.  Kept because an expansion rule may
        # still hand one back through the bridge; ``hasattr`` rather than a
        # default, so an unrecognised shape is the empty pair by DECISION
        # rather than by a silent miss.
        try:
            init = _deref(module_state.init) if hasattr(module_state, 'init') else []
            final = _deref(module_state.final) if hasattr(module_state, 'final') else []
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
