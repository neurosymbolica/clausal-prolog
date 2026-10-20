"""term_expansion — Apply term_expansion rules to module items.

term_expansion/4 clauses match module-level items (Predicate nodes) and
produce rewritten or additional items.  Expansion sits between Phase A
(EmbedTransformer) and Phase B (compile_module) of the pipeline.

Protocol::

    term_expansion(TERM, EXPANSION, MODULE_BEFORE, MODULE_AFTER)

- TERM: runtime Predicate node being expanded -- matched as the node, then a
  RULE as its clause term ``(H :- B)`` (seam: a ``(H <- B)`` node), a FACT
  as its head term (``_expand_item``)
- EXPANSION: a clause -- a Predicate node, a ``(H :- B)`` term, or a head
  term (a fact) -- a list of them, or the atom ``none`` (suppress); a built
  rule's body term is lowered to goals (``_AnswerLowering``)
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
from clausal.logic.special_forms import GOAL_POSITIONS
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


#: Goal-taking builtins that are not special forms, by ``(name, arity)``:
#: their goal argument is a goal too.  (call/N is handled by name.)
_EXTRA_GOAL_ARGS = {
    ("ignore", 1): (0,), ("not", 1): (0,), ("\\+", 1): (0,),
    ("aggregate_all", 3): (1,),
}


def _goal_positions(name: str, arity: int) -> tuple:
    """The 0-based positions of a ``name/arity`` call that are GOALS: call/N's
    closure, a special form's goals (``clausal/logic/special_forms.py``), or
    :data:`_EXTRA_GOAL_ARGS`'s."""
    if name == "call" and arity:
        return (0,)
    return (GOAL_POSITIONS.get((name, arity))
            or _EXTRA_GOAL_ARGS.get((name, arity), ()))


def _goal_names(goal, out: set) -> None:
    """Add to *out* the names of the predicates *goal* calls (a clause-body
    node): through And/Or/Not/if-then-else, conjunction tuples and the goal
    arguments of the meta-calls (:func:`_goal_positions`)."""
    from clausal.pythonic_ast import nodes  # noqa: PLC0415
    from clausal.logic.cells import compound_cell_shape  # noqa: PLC0415
    if isinstance(goal, nodes.And) or isinstance(goal, nodes.Or):
        _goal_names(goal.left, out)
        _goal_names(goal.right, out)
    elif isinstance(goal, nodes.Not):
        _goal_names(goal.operand, out)
    elif isinstance(goal, nodes.IfExpr):
        for g in (goal.test, goal.body, goal.orelse):
            _goal_names(g, out)
    elif isinstance(goal, nodes.IfThenElse):      # ISO ->/; (orelse may be None)
        for g in (goal.test, goal.body, goal.orelse):
            if g is not None:
                _goal_names(g, out)
    elif isinstance(goal, nodes.TupleLiteral):
        for g in goal.elements:
            _goal_names(g, out)
    elif isinstance(goal, (list, tuple)) and not compound_cell_shape(goal)[0]:
        for g in goal:
            _goal_names(g, out)
    elif isinstance(goal, nodes.Call) and isinstance(goal.func, nodes.LoadName):
        name = goal.func.name
        out.add(name)
        for i in _goal_positions(name, len(goal.args)):
            if i < len(goal.args):
                _goal_names(goal.args[i], out)
    elif isinstance(goal, nodes.LoadName):
        out.add(goal.name)
    elif type(goal) is str:
        out.add(goal)
    else:
        is_cell, functor = compound_cell_shape(goal)
        if is_cell:
            out.add(functor)
            for i in _goal_positions(functor, len(goal) - 1):
                if i + 1 < len(goal):
                    _goal_names(goal[i + 1], out)


def _expansion_helpers(expansion_clauses, regular_items) -> list:
    """The clauses of *regular_items* whose predicates the term_expansion/4
    bodies can reach, transitively, in source order.

    ISO/Scryer ``term_expansion`` routinely delegates to a helper defined in
    the same file (it is already consulted when the expansion runs).  Only the
    term_expansion/4 clauses used to be compiled into the synthetic
    expansion module, so a body calling ``step(I, O)`` of its own file failed
    the whole load.  Reachability is by NAME over the GOALS a body calls --
    its conjuncts, disjuncts, negations and if-then-else branches, and the
    goal arguments of the meta-calls -- never over the data terms it builds:
    the common idiom writes the file's own facts as patterns
    (``I is fact(X)``), and counting those as helpers would compile every
    fact a second time into the expansion module."""
    by_name: dict = {}
    for item in regular_items:
        key = _head_name_arity(item)
        if key is not None:
            by_name.setdefault(key[0], []).append(item)
    if not by_name:
        return []

    def called(nodes) -> set:
        out: set = set()
        for n in nodes:
            _goal_names(n.body, out)
        return out

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
    answers = _AnswerLowering(db, module_dict)
    expanded = []
    for item in regular_items:
        result, module_state = _expand_item(item, expansion_module, module_state,
                                            answers)
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
                                       "module_expansion_state/3",
                                       answers=answers)
                  for i in init_items]
    final_items = [_validated_expansion(i, True, slot="the Final list of "
                                        "module_expansion_state/3",
                                        answers=answers)
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


def _expand_item(item, expansion_module, module_state, answers=None):
    """Try to expand a single item using term_expansion rules.

    Returns (expanded_result, new_module_state).
    expanded_result is:
    - A single Predicate node (replacement)
    - A list of Predicate nodes (one-to-many)
    - None (suppressed)
    - The original item (no match)

    Three attempts, the first match wins:

    1. the Predicate NODE itself -- what a variable pattern binds, so a rule
       handing back what it matched (``term_expansion(T, [T, T], S, S)``)
       hands back the very clause, variable names and all;
    2. a RULE (a body other than ``true``) as the clause TERM ISO's
       ``term_expansion/2`` sees: ``(H :- B)`` in ``.clausal`` (and ``.pl``),
       a ``(H <- B)`` node in the seam (``_clause_view``) -- what a
       whole-clause pattern matches;
    3. a FACT's head -- what a bare head pattern (``fact(X)``) matches.

    A head pattern used to be tried on a RULE's head as well, and its answer
    wrapped into facts, so ``term_expansion(p(X), [p(X)], S, S)`` silently
    dropped the body of every ``p/1`` rule.  As in ISO, where a rule reads as
    ``(H :- B)`` and does not unify with ``p(X)``, it matches facts only
    (todo/done/term-expansion-cannot-hand-back-a-rule-2026-10-20.md).
    """
    if answers is None:
        answers = _AnswerLowering(None, {})
    result = _try_te_match(item, item, expansion_module, module_state,
                           wrap_head=False, answers=answers)
    if result is not None:
        return result

    body = getattr(item, "body", True)
    head = getattr(item, "head", None)
    if body is not True and head is not None:
        view = _clause_view(item, answers.seam)
        if view is not None:
            result = _try_te_match(item, view, expansion_module, module_state,
                                   wrap_head=False, answers=answers,
                                   view=view)
            if result is not None:
                return result
    elif head is not None:
        # A10-F008 / A10-D004(a): a bare-term pattern like ``fact(X)`` never
        # unifies with the whole Predicate item (which is
        # Predicate(head=fact(..), body=True)).  Retry against the FACT's
        # head; a head term in the answer is a fact again.
        result = _try_te_match(item, head, expansion_module, module_state,
                               wrap_head=True, answers=answers)
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


def _try_te_match(item, match_target, expansion_module, module_state, wrap_head,
                  answers=None, view=None):
    """Solve term_expansion(match_target, Expansion, S0, S) once.

    Returns (expanded_result, new_state) on a match, or None if no clause
    matched *match_target*. When *wrap_head* is True the expansion terms are
    head terms (the pattern matched item.head) and are wrapped into fact
    Predicate nodes.  *view* is the clause term *match_target* presents a
    rule as (``_clause_view``): an answer that rebuilds exactly it is the
    original *item*, unchanged.
    """
    from clausal.logic.solve import call

    # P2 Task 4: the patterns are cells, a head was still an instance.  Only
    # the HEAD-pattern retry is lowered: a whole-item pattern binds the
    # Predicate NODE, and rebuilding that node with a lowered head hands the
    # rules a copy -- the identity and pass-through expansions return the term
    # they matched, and three of them went red on the copy.  A RULE pattern
    # (``key(K) <- Body``) is matched against the clause VIEW
    # (``_clause_view``), whose head is the item's own cell head (W4a made
    # every head a cell, so nothing is left to lower there):
    # todo/done/term-expansion-whole-item-pattern-head-representation-2026-09-19.md.
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
        return ([_validated_expansion(e, wrap_head, answers=answers,
                                      item=item, view=view)
                 for e in expansion],
                new_state)
    return (_validated_expansion(expansion, wrap_head, answers=answers,
                                 item=item, view=view),
            new_state)


def _validated_expansion(term, wrap_head, slot=None, answers=None,
                         item=None, view=None):
    """One item of a term_expansion/4 answer, checked against the protocol
    and made the clause it denotes.

    An answer item is a CLAUSE:

    - a ``Predicate`` node -- the item a variable pattern matched, handed
      back as it is; or a seam ``(H <- B)`` the rule BUILT, whose body is a
      term (data), lowered here to the goals a written body is;
    - a ``(H :- B)`` term (``.clausal``, or any surface), lowered the same
      way; ``(H :- true)`` is the fact ``H``;
    - a head TERM (an atom or a compound), which is the fact it names, as
      in ISO, where every clause term that is not ``(H :- B)`` is a fact.

    Anything else -- a string, a number -- is refused HERE with an ISO
    ``type_error(callable, Culprit)`` that names the rule's contract; an
    UNBOUND item is ISO's ``instantiation_error``.  *slot* names where the
    item came from when it is not the answer itself (the Init/Final lists).
    Measured 2026-09-26: without this, a chars-mode module writing the
    suppression sentinel as ``"none"`` (a STRING under
    ``-double_quotes(chars)``) sailed through and crashed goal expansion
    with ``'tuple' object has no attribute 'body'``, naming neither the rule
    nor the fix; the message below says to write the ATOM ``none``.

    Before 2026-10-20 a built rule was not lowered: a ``(H :- B)`` became a
    FACT of ``(:-)/2`` (no warning), and a seam ``(H <- B)`` reached the
    compiler with a data body (``NotImplementedError``)
    (todo/done/term-expansion-cannot-hand-back-a-rule-2026-10-20.md).

    *item* and *view* (``_try_te_match``): an answer that rebuilds exactly
    the clause term *view* presented *item* as is *item* itself, so a
    whole-clause pattern handing back what it matched keeps the clause as
    written -- its variable names among it (regex auto-binding).
    """
    from clausal.logic.exceptions import (  # noqa: PLC0415
        LogicException, instantiation_error, type_error,
    )
    from clausal.logic.cells import is_chars, chars_text, compound_cell_shape  # noqa: PLC0415
    from clausal.logic.atoms import is_atom  # noqa: PLC0415
    from clausal.logic.predicate import is_term_instance  # noqa: PLC0415
    from clausal.logic.variables import is_var  # noqa: PLC0415

    term = deref(term)
    where = f"term_expansion/4: {slot}" if slot else "term_expansion/4: the expansion"
    if slot:
        what = ("a clause (`H :- B`, `H <- B`, or a fact `H <- True`) or a "
                "head term")
    elif wrap_head:
        what = ("a head term, a clause (`H :- B`, `H <- B`), a list of "
                "them, or the atom `none` (suppress)")
    else:
        what = ("a clause (`H :- B`, `H <- B`), a head term, a list of "
                "them, or the atom `none` (suppress)")
    if is_var(term):
        raise LogicException(instantiation_error(
            f"{where} is unbound; a rule must bind it to {what}"))
    if answers is None:
        answers = _AnswerLowering(None, {})
    if item is not None and term is item:
        return item
    if isinstance(term, PredicateItem):
        if (term.body is True or term.var_names is not None
                or term.source_body is not None):
            # A clause as a front end built it (a fact, or a rule with its
            # source tables): nothing to lower.
            return term
        if _rebuilds(item, view, term.head, term.body):
            return item
        return answers.clause(term.head, term.body, where)
    is_cell, functor = compound_cell_shape(term)
    if is_cell and functor == ":-" and len(term) == 3:
        if _rebuilds(item, view, term[1], term[2]):
            return item
        return answers.clause(term[1], term[2], where)
    if is_cell and functor == "-->" and len(term) == 3:
        raise LogicException(type_error(
            "callable", term,
            f"{where} is a grammar rule: term expansion runs after grammar "
            f"rules are translated, so a grammar rule it hands back is never "
            f"translated -- hand back the clauses it stands for instead "
            f"(a `H --> B` rule is a clause of H with two extra list "
            f"arguments)"))
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
    if is_cell or is_atom(term) or is_term_instance(term):
        return PredicateItem(head=term, body=True)
    hint = ""
    if is_chars(term) and not slot:
        hint = (f' -- "{chars_text(term)}" is a STRING under -double_quotes(chars); '
                f"the suppression sentinel is the ATOM none: write none or "
                f"'none'")
    raise LogicException(type_error(
        "callable", term,
        f"{where} must be {what}, got {term!r}{hint}"))


def _rebuilds(item, view, head, body) -> bool:
    """*head* and *body* are the clause *item* -- its own head and body, or
    the parts of the clause term *view* presented it as (``_clause_view``)
    -- rebuilt: the answer hands back the clause it matched.  Compared term
    by term down to the variables, which must be the clause's very own (a
    rule that writes ``(p(X) :- B)`` rebuilds the head cell, not the
    object)."""
    if item is None:
        return False
    if _same_term(head, item.head) and _same_term(body, item.body):
        return True
    if view is None:
        return False
    if isinstance(view, PredicateItem):
        view_head, view_body = view.head, view.body
    else:
        view_head, view_body = view[1], view[2]
    return _same_term(head, view_head) and _same_term(body, view_body)


def _same_term(a, b) -> bool:
    """*a* and *b* are the same term: identical, or the same cell or list
    of the same terms, with every variable the same Var."""
    from clausal.logic.variables import is_var  # noqa: PLC0415
    a, b = deref(a), deref(b)
    if a is b:
        return True
    if is_var(a) or is_var(b) or type(a) is not type(b):
        return False
    if type(a) in (tuple, list):
        return len(a) == len(b) and all(map(_same_term, a, b))
    if type(a) in (str, int, float):
        return a == b
    return False


def _clause_view(item, seam: bool):
    """A RULE *item* as the clause TERM a whole-clause pattern is matched
    against, or None when it has none.

    ``.clausal`` (and ``.pl``): ``(Head :- Body)``, the body as READ --
    ``item.source_body``, the ISO term the native front end records for
    ``clause/2`` over the clause's own variables.  The seam: the node
    ``Predicate(head=Head, body=Body)`` a ``(H <- B)`` in argument position
    builds, the body as the term its text builds there (``_seam_body_term``);
    ``Predicate.__unify__`` matches the two."""
    if seam:
        body = _seam_body_term(item.body)
        return PredicateItem(head=item.head, body=body)
    if item.source_body is None:
        return None
    return (":-", item.head, item.source_body)


def _seam_body_term(goal):
    """A seam clause body (goal nodes) as the TERM the same text builds in
    argument position: a ``Call`` is its cell (the bare leaf name of an
    imported, dotted spelling, as data cells carry it), a conjunction a
    plain tuple, an atom goal the atom; the control nodes keep their type
    with their goals converted, and every other node (a comparison, ``is``)
    is the same node in both positions."""
    from clausal.pythonic_ast import nodes  # noqa: PLC0415
    from clausal.logic.builtins.call_body import is_special_form  # noqa: PLC0415
    tt = type(goal)
    if tt is nodes.TupleLiteral:
        return tuple(_seam_body_term(e) for e in goal.elements)
    if tt in (nodes.And, nodes.Or):
        return tt(left=_seam_body_term(goal.left),
                  right=_seam_body_term(goal.right))
    if tt is nodes.Not:
        return nodes.Not(operand=_seam_body_term(goal.operand))
    if tt is nodes.IfExpr:
        return nodes.IfExpr(test=_seam_body_term(goal.test),
                            body=_seam_body_term(goal.body),
                            orelse=_seam_body_term(goal.orelse))
    if (tt is nodes.Call and isinstance(goal.func, nodes.LoadName)
            and not goal.kwargs):
        name = goal.func.name
        arity = len(goal.args)
        leaf = name.rpartition(".")[2]
        if leaf != name and not is_special_form(leaf, arity):
            name = leaf
        positions = _goal_positions(name, arity) if name != "call" else ()
        args = [_seam_body_term(a) if i in positions else a
                for i, a in enumerate(goal.args)]
        return (name, *args) if args else _mint(name)
    return goal


class _NotCallable(Exception):
    """A goal position of a built body holds a non-callable term."""


class _AnswerLowering:
    """Lowers a clause a term_expansion/4 rule BUILT -- its body a term --
    to the ``Predicate`` node a written clause is: the body's goals as the
    nodes the front ends emit for the same text (``iso_l3``'s body
    conversion, ISO 7.6.2), so the compiler meets nothing new.

    - ``,``/2 is a conjunction, ``;``/2 a disjunction, ``\\+``/1 a negation
      (the seam's ``TupleLiteral`` / plain tuple, ``Or``, ``Not``);
      ``true`` is ``True``, ``fail``/``false`` ``False``;
    - a variable goal is ``call(V)``; ``M:G`` is ``call(M:G)``, which runs G
      in M; a list (or a string) is called, and named a missing ``'.'/2``
      when it runs, as ``call/1`` does;
    - every other compound or atom is the call of its predicate, its
      special-form goal arguments (``findall/3``'s goal ...) converted the
      same way and the rest kept as data; a name an import rewrote
      (``match`` from ``library(re)``) is called by the import's dotted
      spelling, exactly as the same goal written in this file;
    - ``!``, ``->`` and ``*->`` are refused (cut-free) except in a ``.pl``
      module (D59), as everywhere else;
    - a goal position holding a number is ``type_error(callable, Body)``.

    A clause it builds has no variable-name table: the rule's variables are
    renamed for each expansion, so its regex groups bind nothing
    (docs/term_expansion.md, Gotchas)."""

    _CONTEXT = "term_expansion/4: a clause the rule built"

    def __init__(self, db, module_dict):
        from clausal.end_module import SURFACE_SEAM, surface_of  # noqa: PLC0415
        from clausal.logic.builtins.call_body import cut_allowed  # noqa: PLC0415
        surface = getattr(db, "surface", None) or surface_of(
            (module_dict or {}).get("__file__") or "")
        # No surface (a Python-made module, the tests' bare transformer): the
        # seam, the surface the Python API compiles.
        self.seam = surface in (SURFACE_SEAM, None)
        self.cut_allowed = cut_allowed(db)
        self._module_dict = module_dict or {}
        self._dotted = None

    # ── the clause ──────────────────────────────────────────────────────

    def clause(self, head, body, where):
        from clausal.logic.exceptions import (  # noqa: PLC0415
            LogicException, instantiation_error, type_error,
        )
        from clausal.logic.cells import compound_cell_shape  # noqa: PLC0415
        from clausal.logic.atoms import is_atom, is_truth_atom  # noqa: PLC0415
        from clausal.logic.variables import is_var  # noqa: PLC0415
        head = deref(head)
        if is_var(head):
            raise LogicException(instantiation_error(
                f"{where}: the head of a clause it built is unbound"))
        if is_truth_atom(head) or not (compound_cell_shape(head)[0]
                                       or is_atom(head)):
            raise LogicException(type_error(
                "callable", head,
                f"{where}: the head of a clause it built must be an atom or "
                f"a compound, got {head!r}"))
        body = deref(body)
        if body is True or (type(body) is str and body == "true"):
            return PredicateItem(head=head, body=True)
        try:
            lowered = self.goal(body)
        except _NotCallable:
            raise LogicException(type_error(
                "callable", body,
                f"{where}: the body of a clause it built is not callable: "
                f"{body!r}")) from None
        return PredicateItem(head=head, body=lowered)

    # ── goal positions ──────────────────────────────────────────────────

    def _call(self, name, args):
        from clausal.pythonic_ast import nodes  # noqa: PLC0415
        return nodes.Call(func=nodes.LoadName(name=name), args=list(args),
                          kwargs=[])

    def _resolved(self, name: str) -> str:
        """The spelling the goal ``name(...)`` has when written in this
        file: the dotted key an ``-import_from`` / ``use_module/2`` rewrote
        an imported name into (``clausal.library.re.match``), else *name*."""
        if self._dotted is None:
            from clausal.logic.atoms import is_mangled as _mangled  # noqa: PLC0415
            md = self._module_dict
            dotted = {}
            for key, value in md.items():
                if (type(key) is not str or "." not in key
                        or key.startswith("$") or value is None):
                    continue
                leaf = key.rpartition(".")[2]
                # The import binds the local spelling to the very object the
                # dotted key holds.  An ATOM never counts (an imported atom
                # is data, and a local name/N of its spelling means local),
                # a predicate handle does.
                if (md.get(leaf) is value
                        and (type(value) is not str or _mangled(value))):
                    dotted.setdefault(leaf, key)
            self._dotted = dotted
        return self._dotted.get(name, name)

    def goal(self, raw):
        from clausal.pythonic_ast import nodes  # noqa: PLC0415
        from clausal.logic.exceptions import LogicException  # noqa: PLC0415
        from clausal.logic.builtins.call_body import (  # noqa: PLC0415
            cut_refusal_error, is_conjunction_tuple, is_non_callable_term,
        )
        from clausal.logic.cells import compound_cell_shape, is_chars  # noqa: PLC0415
        from clausal.logic.variables import is_var  # noqa: PLC0415
        t = deref(raw)
        if is_var(t):
            return self._call("call", [t])     # ISO 7.6.2: call(V)
        if t is True or t is False:
            return t
        if type(t) is str:
            if t == "true":
                return True
            if t in ("fail", "false"):
                return False
            if t == "!":
                if self.cut_allowed:
                    return nodes.Cut()
                raise LogicException(cut_refusal_error(self._CONTEXT))
            return self._call(self._resolved(t), [])
        if type(t) is list or is_chars(t):
            # ``[]`` is the atom '[]' (D70): the call of '[]'/0; a non-empty
            # list or a string is '.'/2, which call/1 names when it runs.
            return self._call("[]", []) if t == [] else self._call("call", [t])
        if isinstance(t, nodes.Node):
            return self._node_goal(t)
        if is_conjunction_tuple(t):
            return nodes.TupleLiteral(elements=[self.goal(e) for e in t])
        is_cell, functor = compound_cell_shape(t)
        if is_cell:
            return self._cell_goal(t, functor)
        if is_non_callable_term(t, lists=False):
            raise _NotCallable(t)
        return self._call("call", [t])         # a goal object: call/1's

    def _refuse_if_then(self, functor):
        from clausal.logic.exceptions import LogicException  # noqa: PLC0415
        from clausal.logic.builtins.call_body import if_then_refusal_error  # noqa: PLC0415
        raise LogicException(if_then_refusal_error(functor, self._CONTEXT))

    def _node_goal(self, t):
        from clausal.pythonic_ast import nodes  # noqa: PLC0415
        from clausal.logic.exceptions import LogicException  # noqa: PLC0415
        from clausal.logic.builtins.call_body import cut_refusal_error  # noqa: PLC0415
        tt = type(t)
        if tt is nodes.TupleLiteral:
            return nodes.TupleLiteral(elements=[self.goal(e) for e in t.elements])
        if tt in (nodes.And, nodes.Or):
            return tt(left=self.goal(t.left), right=self.goal(t.right))
        if tt is nodes.Not:
            return nodes.Not(operand=self.goal(t.operand))
        if tt is nodes.IfExpr:
            return nodes.IfExpr(test=self.goal(t.test), body=self.goal(t.body),
                                orelse=self.goal(t.orelse))
        if tt is nodes.IfThenElse:
            if not self.cut_allowed:
                self._refuse_if_then("->")
            return nodes.IfThenElse(
                test=self.goal(t.test), body=self.goal(t.body),
                orelse=None if t.orelse is None else self.goal(t.orelse))
        if tt is nodes.Cut and not self.cut_allowed:
            raise LogicException(cut_refusal_error(self._CONTEXT))
        if tt is PredicateItem:
            raise _NotCallable(t)
        # A Call, a comparison, ``is``, a Python escape ...: a goal node
        # already, as written.
        return t

    def _cell_goal(self, t, functor):
        from clausal.pythonic_ast import nodes  # noqa: PLC0415
        from clausal.logic.cells import compound_cell_shape  # noqa: PLC0415
        n = len(t) - 1
        if functor == "," and n == 2:
            elements = []
            while True:
                elements.append(self.goal(t[1]))
                rest = deref(t[2])
                ok, f = compound_cell_shape(rest)
                if not (ok and f == "," and len(rest) == 3):
                    elements.append(self.goal(rest))
                    break
                t = rest
            return nodes.TupleLiteral(elements=elements)
        if functor == ";" and n == 2:
            left = deref(t[1])
            ok, lf = compound_cell_shape(left)
            if ok and len(left) == 3 and lf in ("->", "*->"):
                if lf == "->" and self.cut_allowed:
                    return nodes.IfThenElse(test=self.goal(left[1]),
                                            body=self.goal(left[2]),
                                            orelse=self.goal(t[2]))
                self._refuse_if_then(lf)
            return nodes.Or(left=self.goal(t[1]), right=self.goal(t[2]))
        if functor in ("->", "*->") and n == 2:
            if functor == "->" and self.cut_allowed:
                return nodes.IfThenElse(test=self.goal(t[1]),
                                        body=self.goal(t[2]), orelse=None)
            self._refuse_if_then(functor)
        if functor == "\\+" and n == 1:
            return nodes.Not(operand=self.goal(t[1]))
        if functor == ":" and n == 2:
            module = deref(t[1])
            if type(module) is str and module in _builtin_library_names():
                # ``lists:append(..)``: a built-in library's predicate is
                # the builtin, as the front end lowers the written goal.
                return self.goal(t[2])
            return self._call("call", [t])     # M:G runs G in M
        name = self._resolved(functor)
        # An IMPORTED name is the import's predicate, not the special form
        # it may share a name with: its arguments are data (as iso_l3).
        positions = (() if name != functor
                     else _GOAL_POSITIONS.get((functor, n), ()))
        args = []
        for i, a in enumerate(t[1:]):
            if i not in positions:
                args.append(a)
            elif (functor, n) in _ITERATED_GOAL:
                args.append(self._iterated(a))
            else:
                args.append(self.goal(a))
        return self._call(name, args)

    def _iterated(self, raw):
        """``V1^V2^G`` in bagof/setof: the ``BitXor`` chain the compiler
        strips the existential prefix from."""
        from clausal.pythonic_ast import nodes  # noqa: PLC0415
        from clausal.logic.cells import compound_cell_shape  # noqa: PLC0415
        t = deref(raw)
        if type(t) is nodes.BitXor:
            return nodes.BitXor(left=t.left, right=self._iterated(t.right))
        ok, f = compound_cell_shape(t)
        if ok and f == "^" and len(t) == 3:
            return nodes.BitXor(left=t[1], right=self._iterated(t[2]))
        return self.goal(t)


def _builtin_library_names() -> frozenset:
    """The ``library(...)`` names whose predicates are builtins
    (``iso_l3_directives._BUILTIN_LIBRARIES``)."""
    from clausal.tools.iso_l3_directives import _BUILTIN_LIBRARIES  # noqa: PLC0415
    return _BUILTIN_LIBRARIES


#: A special form's goal arguments (``findall/3``'s ...), by (name, arity).
_GOAL_POSITIONS = GOAL_POSITIONS
#: The special forms whose goal takes an existential ``V^`` prefix.
_ITERATED_GOAL = frozenset({("bagof", 3), ("setof", 3)})


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
