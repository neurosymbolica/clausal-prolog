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
  rule's body term is lowered as the same clause written would be
  (``_AnswerLowering``: the native front end's own clause lowering)
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
from clausal.logic.special_forms import (
    BUILTIN_GOAL_POSITIONS, CLOSURE_CALLERS, GOAL_CONTROLS, GOAL_POSITIONS,
)
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


#: Goal-taking callees that are not special forms, by ``(name, arity)``,
#: whose goal argument a seam clause body's TERM view converts as a goal
#: (:func:`_seam_body_term`): ``\+``/not/ignore and aggregate_all/3, from
#: ``special_forms``.  (call/N is handled by name.)
_EXTRA_GOAL_ARGS = {
    **{key: tuple(i for i, r in enumerate(roles) if r == "G")
       for key, roles in GOAL_CONTROLS.items()},
    ("aggregate_all", 3): BUILTIN_GOAL_POSITIONS[("aggregate_all", 3)],
}


def _goal_positions(name: str, arity: int) -> tuple:
    """The 0-based positions of a ``name/arity`` call that are GOALS: call/N's
    closure, a special form's goals (``clausal/logic/special_forms.py``), or
    :data:`_EXTRA_GOAL_ARGS`'s."""
    if name == "call" and arity:
        return (0,)
    return (GOAL_POSITIONS.get((name, arity))
            or _EXTRA_GOAL_ARGS.get((name, arity), ()))


def _called_positions(name: str, arity: int) -> tuple:
    """:func:`_goal_positions`, plus every goal-taking builtin's
    (``special_forms.GOAL_BUILTINS``: time_goal, phrase, maplist & co.) and
    call_goal/N's: the arguments whose predicate names a body CALLS, for
    helper reachability."""
    if arity and name in CLOSURE_CALLERS:
        return (0,)
    return (_goal_positions(name, arity)
            or BUILTIN_GOAL_POSITIONS.get((name, arity), ()))


def _goal_names(goal, out: set) -> None:
    """Add to *out* the names of the predicates *goal* calls (a clause-body
    node): through And/Or/Not/if-then-else, conjunction tuples and the goal
    arguments of the meta-calls and goal-taking builtins
    (:func:`_called_positions`)."""
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
        for i in _called_positions(name, len(goal.args)):
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
            for i in _called_positions(functor, len(goal) - 1):
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
    if (is_cell or is_atom(term)) and not answers.seam:
        # A fact on .clausal / .pl is the clause ``term`` lowered by the
        # front end, as a ``(H :- B)`` answer is: it meets every refusal a
        # fact written in the file meets (an ISO built-in's or a control
        # construct's head, ISO 7.5.1).
        if _rebuilds(item, view, term, True):
            return item
        return answers.clause(term, True, where)
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


#: The module-dict key under which the import hook hands over the native
#: front end's directive state for the file being compiled
#: (``iso_l3_directives.DirectiveContext``, ``NativePrologLoader``): a clause
#: a rule builds is lowered under it.
LOWERING_CONTEXT_KEY = "$lowering_context"

#: The global the lowered code of a built clause reads its run-time
#: variables (and its opaque data values) from, by index.
_BUILT_VALUES_KEY = "$term_expansion_values"


class _AnswerLowering:
    """Turns a clause a term_expansion/4 rule BUILT -- a ``(Head, Body)``
    pair of run-time terms -- into the ``Predicate`` node the same clause
    WRITTEN in the file compiles to.  There is no lowering of its own here:

    - ``.clausal`` / ``.pl``: the clause is handed to the native front end's
      own clause lowering (``iso_l3.lower_clause``), under the file's
      directive state (imports, ``library(reif)``'s ``if_/3``,
      ``library(clpq)``'s ``{}/1``, the surface, so ``.pl`` alone may cut).
      A run-time term is the reader's term but for its variables, so each
      Var becomes a ``VarRef`` indexing the run-time Var itself, and a value
      the reader never produces (a string carrier, a cons cell, a
      ``constant/1`` cell, a Python object) is passed through as it is.
      Whatever the front end refuses in a written clause is refused here,
      with its words.
    - the seam: the body's data shapes are turned into the goal nodes its
      text compiles to in a clause body (``_seam_goal``) -- a cell is the
      ``Call`` node, a conjunction tuple a ``TupleLiteral`` -- and nothing
      else, so the compiler meets what a written body gives it and refuses
      what it refuses there (a bare variable goal: ``BareGoalVariableError``).

    A clause it builds has no variable-name table: the rule's variables are
    renamed for each expansion, so its regex groups bind nothing
    (docs/term_expansion.md, Gotchas)."""

    def __init__(self, db, module_dict):
        from clausal.end_module import SURFACE_SEAM, surface_of  # noqa: PLC0415
        module_dict = module_dict if module_dict is not None else {}
        surface = getattr(db, "surface", None) or surface_of(
            module_dict.get("__file__") or "")
        # No surface (a Python-made module, the tests' bare transformer): the
        # seam, the surface the Python API compiles.
        self.seam = surface in (SURFACE_SEAM, None)
        self._module_dict = module_dict

    def clause(self, head, body, where):
        head, body = deref(head), deref(body)
        if self.seam:
            return self._seam_clause(head, body, where)
        return self._iso_clause(head, body, where)

    # ── .clausal / .pl: the front end's own clause lowering ──────────────

    def _iso_clause(self, head, body, where):
        import ast  # noqa: PLC0415
        from clausal.tools import iso_l3  # noqa: PLC0415
        values: list = []
        seen: dict = {}
        ctx = self._module_dict.get(LOWERING_CONTEXT_KEY)
        reader = _AsReaderTerm(values, seen,
                             chars=getattr(ctx, "dq_mode", "chars") == "chars")
        if body is True or (type(body) is str and body == "true"):
            term = reader(head)
        else:
            term = (":-", reader(head), reader(body))
        try:
            stmts = iso_l3.lower_clause(
                term, positions=iso_l3._Positions(None),
                ctx=ctx, values_global=_BUILT_VALUES_KEY)
        except iso_l3.LoweringRefused as e:
            raise SyntaxError(
                f"{where}: the clause it built is refused, as the same "
                f"clause written in the file would be: {e}") from None
        code = compile(ast.fix_missing_locations(
            ast.Module(body=stmts, type_ignores=[])),
            "<term_expansion/4>", "exec")
        built: list = []
        md = self._module_dict
        missing = object()
        saved = md.get("$define_predicate", missing)
        md["$define_predicate"] = lambda pred, _lm: built.append(pred)
        md[_BUILT_VALUES_KEY] = values
        try:
            exec(code, md)  # noqa: S102 -- the front end's own lowering
        finally:
            del md[_BUILT_VALUES_KEY]
            if saved is missing:
                del md["$define_predicate"]
            else:
                md["$define_predicate"] = saved
        node = built[0]
        # The front end records the body AS READ for clause/2; a built
        # clause has no variable names to give (see the class docstring).
        node.var_names = None
        return node

    # ── the seam: data shapes -> the goal nodes the text compiles to ─────

    def _seam_clause(self, head, body, where):
        from clausal.logic.exceptions import (  # noqa: PLC0415
            LogicException, instantiation_error, type_error,
        )
        from clausal.logic.cells import compound_cell_shape  # noqa: PLC0415
        from clausal.logic.atoms import is_atom, is_truth_atom  # noqa: PLC0415
        from clausal.logic.variables import is_var  # noqa: PLC0415
        if is_var(head):
            raise LogicException(instantiation_error(
                f"{where}: the head of a clause it built is unbound"))
        if is_truth_atom(head) or not (compound_cell_shape(head)[0]
                                       or is_atom(head)):
            raise LogicException(type_error(
                "callable", head,
                f"{where}: the head of a clause it built must be an atom or "
                f"a compound, got {head!r}"))
        # A partial list (``[_, *T]``, a SegList at run time) as the
        # compiler's source form, its holes clause variables, as assertz/1
        # spells it -- the reader route's ``_partial_list``.
        from clausal.logic.builtins.database_ops import _seglists_as_source  # noqa: PLC0415
        head = _seglists_as_source(head)
        if body is True:
            return PredicateItem(head=head, body=True)
        return PredicateItem(head=head, body=_seam_goal(_seglists_as_source(body)))


def _seam_goal(raw):
    """A seam body built in argument position, as the goal nodes the same
    text compiles to in a clause body.  Only the shapes that DIFFER between
    the two positions are rewritten -- a compound is a cell in data and a
    ``Call`` in a body, a conjunction a plain tuple in data and a
    ``TupleLiteral`` in a body, and the control nodes hold data shapes in
    their goal fields -- so everything else (a comparison, ``is``, an atom,
    a variable, a number) reaches the compiler as it would written, and
    meets the same acceptance or refusal there."""
    from clausal.pythonic_ast import nodes  # noqa: PLC0415
    from clausal.logic.builtins.call_body import is_conjunction_tuple  # noqa: PLC0415
    from clausal.logic.cells import compound_cell_shape  # noqa: PLC0415
    t = deref(raw)
    tt = type(t)
    if tt is nodes.TupleLiteral:
        return nodes.TupleLiteral(elements=[_seam_goal(e) for e in t.elements])
    if tt in (nodes.And, nodes.Or):
        return tt(left=_seam_goal(t.left), right=_seam_goal(t.right))
    if tt is nodes.Not:
        return nodes.Not(operand=_seam_goal(t.operand))
    if tt is nodes.IfExpr:
        return nodes.IfExpr(test=_seam_goal(t.test), body=_seam_goal(t.body),
                            orelse=_seam_goal(t.orelse))
    if is_conjunction_tuple(t):
        return nodes.TupleLiteral(elements=[_seam_goal(e) for e in t])
    is_cell, functor = compound_cell_shape(t)
    if not is_cell:
        return t
    n = len(t) - 1
    positions = GOAL_POSITIONS.get((functor, n), ())
    args = []
    for i, a in enumerate(t[1:]):
        if i not in positions:
            args.append(a)
        elif (functor, n) in (("bagof", 3), ("setof", 3)):
            args.append(_seam_iterated(a))
        else:
            args.append(_seam_goal(a))
    return nodes.Call(func=nodes.LoadName(name=functor), args=args, kwargs=[])


def _seam_iterated(raw):
    """``V^G`` in a seam bagof/setof: the ``BitXor`` chain, its goal a goal."""
    from clausal.pythonic_ast import nodes  # noqa: PLC0415
    t = deref(raw)
    if type(t) is nodes.BitXor:
        return nodes.BitXor(left=t.left, right=_seam_iterated(t.right))
    return _seam_goal(t)


class _AsReaderTerm:
    """A run-time term as the ISO reader's term (``prolog_reader``): each
    distinct unbound Var a ``VarRef`` indexing *values*, which holds the Var
    itself; a list, a number, an atom and a compound as the reader gives
    them; the truth values as the atoms they are read from; a string as
    ``"..."`` when ``double_quotes`` is chars.  Every value the reader
    would read DIFFERENTLY from the run-time term -- a string under another
    ``double_quotes`` mode, a cons cell or a
    ``constant/1`` cell (both rewritten there), tuple data, a Python object
    -- goes in *values* too, and is spliced back verbatim
    (``iso_l3_directives.Embedded``)."""

    def __init__(self, values: list, seen: dict, chars: bool = True):
        self._values = values
        self._seen = seen
        # Under ``double_quotes`` chars (always, in .clausal) the reader's
        # ``"..."`` IS the string carrier, so it is given as read: in a goal
        # position the front end then refuses it in its own words.
        self._chars = chars

    def _slot(self, value) -> int:
        self._values.append(value)
        return len(self._values) - 1

    def _embedded(self, value):
        import ast  # noqa: PLC0415
        from clausal.tools.iso_l3_directives import Embedded  # noqa: PLC0415
        return Embedded(ast.Subscript(
            value=ast.Name(id=_BUILT_VALUES_KEY, ctx=ast.Load()),
            slice=ast.Constant(value=self._slot(value)), ctx=ast.Load()),
            term=value)

    def __call__(self, raw):
        from clausal.tools.prolog_reader import VarRef  # noqa: PLC0415
        from clausal.logic.variables import is_var  # noqa: PLC0415
        from clausal.logic.cells import (  # noqa: PLC0415
            chars, chars_text, compound_cell_shape, is_chars)
        from clausal.terms import SegList, SegString, Undefined  # noqa: PLC0415
        t = deref(raw)
        if is_var(t):
            index = self._seen.get(id(t))
            if index is None:
                index = self._seen[id(t)] = self._slot(t)
            return VarRef(index)
        if t is True:
            return "true"
        if t is False:
            return "false"
        if t is Undefined:
            return "undefined"
        if type(t) in (int, float, str):
            return t
        if type(t) is list:
            return [self(e) for e in t]
        if isinstance(t, SegList):            # SegListView too
            return self._partial_list(t)
        if isinstance(t, SegString):
            walked = t._walk_raw()
            if type(walked) is str:
                return self(chars(walked))
            return self._embedded(t)
        if self._chars and is_chars(t):
            return ("$chars", chars_text(t))
        is_cell, functor = compound_cell_shape(t)
        if is_cell and functor == "." and len(t) == 3:
            # A cons cell: the reader's own, which the front end lowers to
            # the list it is (``[H, *T]`` over a variable tail) or keeps as
            # the improper list it is.
            return (".", self(t[1]), self(t[2]))
        if is_cell and not (functor == "constant" and len(t) == 2):
            return (functor, *(self(a) for a in t[1:]))
        return self._embedded(t)

    def _partial_list(self, t):
        """A partial list ``[E1, ..., En | T]`` (a ``SegList``) as the
        reader's cons chain ending in ``T``'s VarRef, which the front end
        lowers to ``[E1, ..., *T]`` with ``T`` a clause variable, fresh at
        every call, as for the written list.  Spliced in verbatim, the
        SegList kept the rule's own hole variable out of the clause's
        variables, and a built ``len([_|T], N) :- len(T, M), ...`` looped
        forever.  Holes before the end have no reader spelling (a seam
        shape): the compiler's own source form ``[E, *A, F, *B]`` is
        spliced, as assertz/1 does (``_seglists_as_source``)."""
        from clausal.terms import ConcreteSeg, SegList, VarSeg  # noqa: PLC0415
        walked = t._walk_raw()
        if not isinstance(walked, SegList):
            return self(walked)               # a list, or a cons chain, now
        *front, last = walked.segments
        if (isinstance(last, VarSeg)
                and all(isinstance(seg, ConcreteSeg) for seg in front)):
            elements = [e for seg in front for e in seg.elements]
            out = self(last.var)
            for e in reversed(elements):
                out = (".", self(e), out)
            return out
        from clausal.logic.builtins.database_ops import _seglists_as_source  # noqa: PLC0415
        return self._embedded(_seglists_as_source(walked))


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
