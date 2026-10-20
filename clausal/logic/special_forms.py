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
