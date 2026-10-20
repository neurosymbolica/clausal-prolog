"""The compiler's meta-call special forms and their goal positions: the ONE
table.

A special form is a goal the clause-body compiler lowers INLINE rather than
through a dispatch (``compiler/terms_to_goalop._convert``'s ``MetaCall``
arms, plus ``eval_/2``, which it lowers to ``ArithEval``).  Each is keyed by
``(name, arity)``: a name at another arity is an ordinary call.

Every other table that needs "which arguments of this meta-call are goals"
derives from this one or is held to it by
``tests/test_meta_goal_tables_agree.py``:

- ``builtins/call_body.SPECIAL_FORMS`` (``call/1`` of a special-form cell)
  IS this table;
- ``builtins/clause_ops.SPECIAL_FORMS`` and ``._GOAL_ARGS`` (``clause/2``);
- ``tools/iso_l3._META_GOAL_ARGS`` (the native front end lowers these
  arguments as goals);
- ``compiler/cut_scope``'s literal ``call/N`` body terms;
- ``term_expansion``'s helper reachability;
- the ``.pl`` exporter's and translator's goal walks (in their spelling).

Goal expansion does NOT descend into these goal arguments, by decision
(a meta-call scopes its bindings its own way; see that test).

The compiler's own key-named manifest, ``compiler/ir.META_GOAL_POSITIONS``,
is held to :data:`GOAL_POSITIONS` position by position by that test.

A second table, :data:`GOAL_BUILTINS`, lists the goal-taking callees that
are NOT special forms -- builtins that receive their goal as a TERM and run
it (aggregate_all/3, time_goal/1,2, phrase/2,3, maplist & co.), with
:data:`GOAL_CONTROLS` (``\\+``, not, ignore) and :data:`CLOSURE_CALLERS`
(call/N, call_goal/N) beside it.  Its readers derive
from it or are held to it by the same test:

- ``builtins/higher_order._GOAL_FIRST_LIST_BUILTINS`` and
  ``builtins/clause_ops._BUILTIN_GOAL_ARGS`` ARE slices of it;
- ``meta_predicate.builtin_goal_positions`` (a dotted goal argument is the
  qualified goal) and ``compiler/cut_scope._RUN_TIME_META`` read it;
- ``term_expansion``'s helper reachability reads it;
- the ``.pl`` translator's ``_META_GOAL_ARGS`` lists its ``.pl`` names.

Pure data with no imports of its own, so nothing here pulls in an engine
module; importing it still runs ``clausal/__init__.py``, which does.  Of the
readers, only the native front end (``iso_l3``) runs while CACHED bytecode
is produced, so the file is in ``import_hook._NATIVE_FRONTEND_FILES``; the
seam compiler reads it (``compiler/terms_to_ast`` via
``call_body.is_special_form``) only when predicates are compiled at load,
after the cached module code runs.
"""
from __future__ import annotations

#: ``(name, arity)`` -> one ROLE letter per argument:
#:
#: ``G``  a goal.  Every one of these forms is DEFINED on ``call/1`` of its
#:        goal (ISO 7.8.9 catch/3, 8.10.1 findall/3, 8.15.2 once/1 ...).
#: ``A``  a term argument (template, bag, catcher, ball, counter, expression).
#: ``W``  a when/2 condition: a term the runtime reads, not a goal.
#:
#: ``tests/test_call_runs_special_form_cells.py`` holds the keys to
#: ``terms_to_goalop`` in both directions.
SPECIAL_FORMS: dict[tuple[str, int], str] = {
    ("findall", 3): "AGA",
    ("findall", 4): "AGAA",
    ("bagof", 3): "AGA",
    ("setof", 3): "AGA",
    ("once", 1): "G",
    ("forall", 2): "GG",
    ("catch", 3): "GAG",
    ("catch_error", 2): "GA",
    ("catch_recover", 3): "GAG",
    ("throw", 1): "A",
    ("call_nth", 2): "GA",
    ("count_all", 2): "GA",
    ("setup_call_cleanup", 3): "GGG",
    ("call_cleanup", 2): "GG",
    ("freeze", 2): "AG",
    ("when", 2): "WG",
    ("eval_", 2): "AA",
    ("halt", 0): "",
    ("halt", 1): "A",
}

#: ``(name, arity)`` -> the 0-based argument positions that are GOALS, for
#: each special form that has one.
GOAL_POSITIONS: dict[tuple[str, int], tuple[int, ...]] = {
    key: tuple(i for i, role in enumerate(roles) if role == "G")
    for key, roles in SPECIAL_FORMS.items()
    if "G" in roles
}

#: The highest arity of each special form's NAME: written with fewer
#: arguments it is a call/N closure of the form (``catch(G)`` in
#: ``call(catch(G), C, R)``, ISO 8.15.4).
SPECIAL_FORM_MAX_ARITY: dict[str, int] = {}
for _name, _arity in SPECIAL_FORMS:
    if _arity > SPECIAL_FORM_MAX_ARITY.get(_name, -1):
        SPECIAL_FORM_MAX_ARITY[_name] = _arity
del _name, _arity


# ─────────────────────────────────────────────────────────────────────────────
# Goal-taking callees that are not special forms
# ─────────────────────────────────────────────────────────────────────────────

#: ``(name, arity)`` -> one ROLE letter per argument, for each engine BUILTIN
#: that is not a special form but receives a goal as a TERM and runs it:
#:
#: ``G``  a goal, run as call/1 runs it;
#: ``C``  a closure: a goal call/N extends with the list elements (maplist &
#:        co.: the first argument of each goal-first list builtin);
#: ``D``  a DCG body (phrase/2,3's first: ``[]`` there is the empty list of
#:        terminals, not the goal ``[]``);
#: ``A``  a term argument.
#:
#: call/N and call_goal/N are :data:`CLOSURE_CALLERS` (every arity); the
#: negations and ignore/1 are :data:`GOAL_CONTROLS`.  The order of the C
#: rows is the registration order of
#: ``higher_order._GOAL_FIRST_LIST_BUILTINS``.
GOAL_BUILTINS: dict[tuple[str, int], str] = {
    ("aggregate_all", 3): "AGA",
    ("time_goal", 1): "G",
    ("time_goal", 2): "GA",
    ("phrase", 2): "DA",
    ("phrase", 3): "DAA",
    **{("maplist", n): "C" + "A" * (n - 1) for n in range(2, 10)},
    ("include", 3): "CAA",
    ("exclude", 3): "CAA",
    ("foldl", 4): "CAAA",
    ("foldl", 5): "CAAAA",
    ("foldl", 6): "CAAAAA",
    ("map_list_to_pairs", 3): "CAA",
    ("take_while", 3): "CAA",
    ("drop_while", 3): "CAA",
    ("span", 4): "CAAA",
    ("group_by", 3): "CAA",
    ("sort_by", 3): "CAA",
    ("max_by", 3): "CAA",
    ("min_by", 3): "CAA",
    ("filter_map", 3): "CAA",
    ("partition", 4): "CAAA",
    ("tfilter", 3): "CAA",
    ("tpartition", 4): "CAAA",
}

#: The goal-taking callees that are neither special forms nor engine
#: builtins, ``(name, arity)`` -> roles: ``\+``/1 (and its spelling
#: ``not``/1) lowers to a ``Negate`` node, never a call, and
#: ``ignore``/1 is the library spelling of ``( G -> true ; true )`` a ``.pl``
#: file calls (no engine definition).  Walks that read call-shaped goals
#: (term_expansion's reachability, the ``.pl`` exporter and translator)
#: list them.
GOAL_CONTROLS: dict[tuple[str, int], str] = {
    ("\\+", 1): "G",
    ("not", 1): "G",
    ("ignore", 1): "G",
}

#: Names whose FIRST argument is a goal (a closure) at every arity >= 1.
CLOSURE_CALLERS: frozenset[str] = frozenset({"call", "call_goal"})


def _positions(roles: str, kinds: str) -> tuple[int, ...]:
    return tuple(i for i, role in enumerate(roles) if role in kinds)


#: ``(name, arity)`` -> 0-based positions of every goal argument (``G``,
#: ``C`` or ``D``) of :data:`GOAL_BUILTINS`.
BUILTIN_GOAL_POSITIONS: dict[tuple[str, int], tuple[int, ...]] = {
    key: _positions(roles, "GCD") for key, roles in GOAL_BUILTINS.items()
}

#: The goal-first list builtins (maplist & co.), in registration order.
GOAL_FIRST_LIST_BUILTINS: tuple[tuple[str, int], ...] = tuple(
    key for key, roles in GOAL_BUILTINS.items() if roles[0] == "C")
