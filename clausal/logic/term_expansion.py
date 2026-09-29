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

from clausal.logic.atoms import demangle, is_mangled, mint as _mint
from clausal.logic.database import Module as LogicModule, Clause, head_key
from clausal.logic.compiler import compile_predicate_trampoline
from clausal.logic.variables import Var as _Var
from clausal.logic.predicate import (
    _db_for_module_name, predicate_owner_module,
)
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
    # (A ``PredicateMeta`` INSTANCE arm stood here, the pre-cell head shape.
    # W4a made such an instance impossible; deleted W4b-3 slice 2.)
    return False


def _head_name_arity(pred_node):
    """``(name, arity)`` of a Predicate node's head, or None."""
    head = pred_node.head
    from clausal.terms import Call, LoadName
    from clausal.logic.cells import compound_cell_shape  # noqa: PLC0415
    if isinstance(head, Call) and isinstance(head.func, LoadName):
        return head.func.name, len(head.args)
    if type(head) is str:
        return head, 0
    is_cell, functor = compound_cell_shape(head)
    if is_cell:
        return functor, len(head) - 1
    return None


def _expansion_helpers(expansion_clauses, regular_items) -> list:
    """The clauses of *regular_items* whose predicates the term_expansion/4
    bodies can reach, transitively, in source order.

    ISO/Scryer ``term_expansion`` routinely delegates to a helper defined in
    the same file (it is already consulted when the expansion runs).  Only the
    term_expansion/4 clauses used to be compiled into the synthetic
    expansion module, so a body calling ``step(I, O)`` of its own file failed
    the whole load.  Reachability is by NAME over every functor a body writes
    (a data term's functor included), which over-approximates harmlessly: a
    name no clause here defines selects nothing."""
    by_name: dict = {}
    for item in regular_items:
        key = _head_name_arity(item)
        if key is not None:
            by_name.setdefault(key[0], []).append(item)
    if not by_name:
        return []

    def called(nodes) -> set:
        out: dict = {}
        seen: set = set()
        for n in nodes:
            _collect_functor_arities(n.body, out, seen)
        return set(out)

    reachable: set = set()
    frontier = list(called(expansion_clauses))
    while frontier:
        name = frontier.pop()
        if name in reachable or name not in by_name:
            continue
        reachable.add(name)
        frontier.extend(called(by_name[name]))
    return [item for item in regular_items
            if (_head_name_arity(item) or (None,))[0] in reachable]


def run_term_expansion(
    predicate_nodes: list,
    module_dict: dict,
    db=None,
) -> list:
    """Apply term_expansion rules to predicate nodes.

    Separates term_expansion clauses from regular items, compiles the
    expansion rules, then applies them to each regular item.

    Also collects the term_expansion clauses of an imported
    ``term_expansion`` binding (``-import_from(mod, [term_expansion])``),
    recorded on its owner's Database.

    Returns the (possibly rewritten) list of predicate nodes.  If no
    term_expansion clauses exist, returns predicate_nodes unchanged
    (zero overhead).

    Parameters
    ----------
    predicate_nodes : list
        Runtime Predicate (simple_ast) nodes from Phase A.
    module_dict : dict
        The module's __dict__ (for resolving types in compilation).
    db : Database, optional
        The Database of the module being compiled.  Its local
        term_expansion clauses are recorded there
        (``Database.te_predicate_nodes``) for downstream importers.

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
    helpers = _expansion_helpers(expansion_clauses, regular_items)
    expansion_module = _compile_expansion_rules(all_te_clauses, module_dict,
                                                helpers)

    # Store local TE predicate nodes for downstream importers, on this
    # module's DATABASE, where ``-import_from(mod, [term_expansion])`` finds
    # them (``_te_nodes_of_binding``).  W4b-2d R6: they used to be stashed on
    # the term_expansion CLASS -- state stored nowhere else, so once the
    # importer's binding is a handle the imported rules vanished silently.
    # NOT on ``$module``: that write used to land on the import hook's
    # PLACEHOLDER module (thrown away after compile), so a bare
    # ``-import_module(mod)`` never carried TE rules; now that compile_module
    # installs the real module first (``_install_real_module``) writing there
    # would silently start carrying them.  Only a by-name import does.
    if expansion_clauses and db is not None:
        db.te_predicate_nodes = list(expansion_clauses)

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

    # Step 6: Extract Init + Final items from final module state.  They
    # join the module's items exactly as an expansion answer does, so they
    # are checked the same way (flip review, job 238): an unchecked string,
    # number or bare head term there crashed goal expansion just as an
    # unchecked answer did.
    init_items, final_items = _extract_init_final(module_state)
    # A bare head term there becomes a fact, as it does on the head-pattern
    # retry -- a rule that matched a head and consed ``bar(X)`` into Init
    # meant a fact -- so the check is the head-wrapping one.
    init_items = [_validated_expansion(i, True, slot="the Init list of "
                                       "module_expansion_state/3")
                  for i in init_items]
    final_items = [_validated_expansion(i, True, slot="the Final list of "
                                        "module_expansion_state/3")
                   for i in final_items]

    return init_items + expanded + final_items


def _collect_imported_te_clauses(module_dict: dict) -> list:
    """Collect term_expansion predicate nodes from imported modules.

    The source is a binding of the predicate ``term_expansion`` -- a class
    or a mangled handle -- whose OWNER module's Database recorded its local
    term_expansion clauses (``Database.te_predicate_nodes``, set when a
    module with TE rules is compiled), i.e.
    ``-import_from(mod, [term_expansion])``.  A bare ``-import_module(mod)``
    does not provide expansion rules: the ``$module``-borne route this
    function used to check was only ever written onto the import hook's
    placeholder module, so it never fired.
    """
    seen = set()  # avoid duplicates
    result = []

    for value in module_dict.values():
        te_nodes = _te_nodes_of_binding(value)
        if te_nodes and id(te_nodes) not in seen:
            seen.add(id(te_nodes))
            result.extend(te_nodes)

    return result


def _te_nodes_of_binding(value) -> "list | None":
    """The term_expansion clauses recorded by the module that OWNS *value*,
    when *value* is a binding of the predicate ``term_expansion`` -- a
    mangled handle whose functor half is ``term_expansion`` (a
    ``PredicateMeta`` class of that name until W4b-3 slice 7) -- else
    ``None``.

    The owner is ``predicate_owner_module`` (a handle's module half) and the
    clauses are read off
    that module's Database, never off the class.  The term_expansion
    predicate itself has no row -- its clauses are consumed by expansion,
    not compiled -- so the owner is found by module name.
    """
    if type(value) is not str:
        return None
    if not is_mangled(value) or demangle(value)[1] != "term_expansion":
        return None
    owner = predicate_owner_module(value)
    owner_db = _db_for_module_name(owner) if owner else None
    return getattr(owner_db, "te_predicate_nodes", None)


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
    all descended). Names are ordinary lowercase functor identifiers — a
    pattern is a plain term (``q()`` quasi-quotation was retired 2026-09-25,
    so a ``q`` here is the ordinary functor ``q``)."""
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

    # NO class (W4b-3 slice 4a): ``term_expansion/4`` is a ROW of the
    # synthetic module's own Database, compiled and dispatched by name
    # (``call("term_expansion", ..., module=lm)`` asks ``db.get_dispatch``).
    # It used to be a ``make_predicate`` class bound under the name.  The
    # declaration makes the name answerable as a declared functor.
    lm.db.declare_functor(
        "term_expansion", ("term", "expansion", "module_before", "module_after"))

    # Also ensure module_expansion_state is constructible for state threading.
    # A CONSTRUCTOR, not a class: the globals placeholder that raises "not in
    # scope as a term class" fires when nothing CALLABLE is bound to the name,
    # so a function satisfies it and leaves no row-less PredicateMeta behind.
    lm.module_dict["module_expansion_state"] = module_expansion_state
    return lm


def _compile_expansion_rules(expansion_clauses, module_dict, helpers=()):
    """Compile term_expansion clauses into a mini LogicModule, with the
    *helpers* (``_expansion_helpers``) their bodies call.  A helper is
    compiled HERE as written: it is not itself expanded (it runs while
    expansion happens), and it still reaches the module as an ordinary item."""
    lm = _term_expansion_module(module_dict)
    helper_keys = {k for k in map(_head_name_arity, helpers) if k is not None}

    # A10-F008 / A10-D004(a): pre-mint term classes for functors referenced in
    # the expansion patterns — e.g. a brand-new ``logged_fact``
    # introduced by an expansion. Without this, constructing ``logged_fact(X)``
    # at expansion time fails with "not in scope as a term class".
    functor_arities: dict[str, int] = {}
    _seen_ids: set = set()
    for pred_node in list(expansion_clauses) + list(helpers):
        _collect_functor_arities(pred_node, functor_arities, _seen_ids)
    # "Not bound" includes bound to an ATOM: an atom is data and builds no
    # term, and the module dict this copies is pre-seeded with the
    # process-wide atom pool, so an atom ANOTHER module declared (``fact``,
    # ``logged_fact``) sits under the name.  Skipping it left the pattern
    # compiled as a call of that str -- ``TypeError: 'str' object is not
    # callable`` at expansion time, only when an earlier load had declared
    # the atom.
    from clausal.logic.atoms import is_atom as _is_atom  # noqa: PLC0415
    for name, arity in functor_arities.items():
        if (name, arity) in helper_keys:
            continue        # a PREDICATE the bodies call, compiled below
        if name not in lm.module_dict or _is_atom(lm.module_dict[name]):
            lm.module_dict[name] = _data_functor_ctor(name, arity)
    for name, _arity in helper_keys:
        # The module dict this copies may bind the helper's name to anything
        # (a pre-minted data constructor of an earlier load, a pooled atom);
        # the call must resolve to the row compiled below.
        lm.module_dict.pop(name, None)

    # assertz each expansion clause, and each helper clause.
    for pred_node in list(expansion_clauses) + list(helpers):
        lm.define_predicate(pred_node)
    for name, arity in sorted(helper_keys):
        clauses = lm.db.clauses_for(name, arity)
        if clauses:
            compile_predicate_trampoline(
                name, arity, clauses, lm.db,
                globals_=lm.module_dict, pred_cls=None,
            )

    # Compile the expansion predicate.
    functor, arity = "term_expansion", 4
    clauses = lm.db.clauses_for(functor, arity)
    if clauses:
        # Compiled onto ``lm.db``'s own row (``pred_cls=None``): the row is
        # the predicate, so the index plans and the dispatch land there with
        # no class to bind first (W4b-3 slice 4a).
        compile_predicate_trampoline(
            functor, arity, clauses, lm.db,
            globals_=lm.module_dict, pred_cls=None,
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

    # A10-F008 / A10-D004(a): a bare-term pattern like ``fact(X)`` never
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
    ``term_expansion(key(KEY), ...)`` silently matched nothing, and the
    module loaded with the expansion's output missing.

    Only the TOP term is lowered: nested arguments compile to cells already,
    and the lift back is not needed here -- a cell head reaching the store is
    stored as the cell it is (the head channel takes cells since the P2
    head flip; ``Database._with_instance_head`` is gone with it).
    """
    from clausal.logic.predicate import is_term_instance, term_field_names
    from clausal.terms import Call as TermCall
    if is_term_instance(term) and not isinstance(term, TermCall):
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
    # they matched, and three of them went red on the copy.  A RULE
    # pattern (``key(K) <- Body``) would want the same lowering one level
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
        return ([_validated_expansion(e, wrap_head) for e in expansion],
                new_state)
    return _validated_expansion(expansion, wrap_head), new_state


def _validated_expansion(term, wrap_head, slot=None):
    """One item of a term_expansion/4 answer, checked against the protocol.

    An answer item is a clause (a ``Predicate`` node) or, on the head-pattern
    retry (*wrap_head*), a head TERM that becomes a fact.  Anything else --
    a string, a number -- is refused HERE with an ISO ``type_error(callable,
    Culprit)`` that names the rule's contract; an UNBOUND item is ISO's
    ``instantiation_error``.  *slot* names where the item came from when it
    is not the answer itself (the Init/Final lists).
    Measured 2026-09-26: without this, a chars-mode module writing the
    suppression sentinel as ``"none"`` (a STRING under
    ``-double_quotes(chars)``) sailed through and crashed goal expansion
    with ``'tuple' object has no attribute 'body'``, naming neither the rule
    nor the fix; the message below says to write the ATOM ``none``.
    """
    from clausal.logic.exceptions import (  # noqa: PLC0415
        LogicException, instantiation_error, type_error,
    )
    from clausal.logic.cells import is_chars, compound_cell_shape  # noqa: PLC0415
    from clausal.logic.atoms import is_atom  # noqa: PLC0415
    from clausal.logic.predicate import is_term_instance  # noqa: PLC0415
    from clausal.logic.variables import is_var  # noqa: PLC0415

    term = deref(term)
    where = f"term_expansion/4: {slot}" if slot else "term_expansion/4: the expansion"
    if slot:
        what = "a clause (`H <- Body`, or a fact `H <- True`) or a head term"
    elif wrap_head:
        what = "a head term, a list of head terms, or the atom `none` (suppress)"
    else:
        what = "a clause, a list of clauses, or the atom `none` (suppress)"
    if is_var(term):
        raise LogicException(instantiation_error(
            f"{where} is unbound; a rule must bind it to {what}"))
    if isinstance(term, PredicateItem):
        return term
    if slot and term == _NONE_ATOM:
        # ``none`` suppresses an ANSWER; inside Init/Final it would wrap into
        # a stray ``none/0`` fact with no diagnostic, so it is refused by name.
        raise LogicException(type_error(
            "callable", term,
            f"{where} holds the atom `none`, but suppression has no meaning "
            f"there -- a list item is {what}; leave the list shorter instead"))
    # A chars carrier is a 2-tuple headed by CHARS_TAG: compound_cell_shape
    # answers False for it, and it is neither an atom nor a term instance,
    # so no separate guard is needed to keep a STRING out of a fact head.
    if wrap_head and (compound_cell_shape(term)[0] or is_atom(term)
                      or is_term_instance(term)):
        return PredicateItem(head=term, body=True)
    hint = ""
    if is_chars(term) and not slot:
        hint = (f' -- "{term[1]}" is a STRING under -double_quotes(chars); '
                f"the suppression sentinel is the ATOM none: write none or "
                f"'none'")
    raise LogicException(type_error(
        "callable", term,
        f"{where} must be {what}, got {term!r}{hint}"))


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
