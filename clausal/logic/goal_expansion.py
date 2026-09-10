"""clausal.logic.goal_expansion — body-walking goal expansion pass (V3-3).

Transforms individual goals within clause bodies.  Applied after term
expansion but before compilation in the ``compile_module`` pipeline.

Built-in expansions
-------------------
- **Regex pre-compilation + auto-binding** (Phase 3): static ``match/2``
  and ``search/2`` patterns with ALLCAPS/leading-underscore named groups
  are rewritten to ``match/3`` + ``Unify`` chains.  The compiled
  ``re.Pattern`` object is injected into ``module_dict`` for runtime use.
- **Arrow match patterns** (reflection sugar): a ``(HEAD <- BODY)``
  expression in an argument of a reflection builtin (``reified_clause`` et
  al.) is rewritten into the equivalent reified-vocabulary pattern —
  ``Clause(Goal(...), [...])`` construction — so matchers are written in
  natural clause syntax.  Pattern variables remain the matcher clause's
  own variables; unifying them against the ground ``Variable('X')`` terms
  in reified output gives capture and sharing semantics.  Outside
  reflection-builtin arguments the arrow expression keeps its existing
  meaning (a runtime ``Predicate`` node — the assertz write-side term).
"""

from __future__ import annotations

import re as _re
from typing import Any

from clausal.pythonic_ast.nodes import (
    And,
    Call,
    IfExpr,
    LoadAttr,
    LoadName,
    Not,
    Or,
    Predicate,
    TupleLiteral,
    Unify,
)
from clausal.logic.atoms import is_atom as _term_is_atom, spelling as _atom_spelling
from clausal.logic.variables import Var, is_var, deref
from clausal.logic.predicate import is_term_instance, term_field_names


class _ExpansionContext:
    """Carries state across goal expansion for a module."""

    __slots__ = ("module_dict", "_counter", "_pattern_cache", "_clause_vars")

    def __init__(self, module_dict: dict) -> None:
        self.module_dict = module_dict
        self._counter = 0
        self._pattern_cache: dict[str, str] = {}
        # field_name → Var mapping for current clause (set per-predicate).
        self._clause_vars: dict[str, Any] = {}

    def next_id(self) -> int:
        n = self._counter
        self._counter += 1
        return n

    def intern_pattern(self, pattern_str: str) -> str:
        """Compile *pattern_str* once and inject into module_dict.

        Returns the globals key (e.g. ``"_re_0"``).
        """
        existing = self._pattern_cache.get(pattern_str)
        if existing is not None:
            return existing
        compiled = _re.compile(pattern_str)
        key = f"_re_{self.next_id()}"
        self.module_dict[key] = compiled
        self._pattern_cache[pattern_str] = key
        return key

    def find_var_for_group(self, group_name: str) -> Any | None:
        """Find the clause Var matching a regex group name.

        Group names follow logic-var convention (ALLCAPS or _leading).
        Field names are derived by lowering + stripping leading underscore.
        """
        field_name = group_name.lstrip("_").lower()
        return self._clause_vars.get(field_name)


def run_goal_expansion(
    predicate_nodes: list,
    module_dict: dict,
) -> list:
    """Walk clause bodies and apply goal expansions.

    Returns a new list of predicate nodes with expanded goals.
    """
    ctx = _ExpansionContext(module_dict)
    expanded = []
    for pred in predicate_nodes:
        expanded.append(_expand_predicate(pred, ctx))
    return expanded


def _collect_vars_from_term(term: Any, result: dict[str, Any]) -> None:
    """Collect field_name → Var mappings from a term tree.

    Walks into Call args, And/Or/Not branches, and PredicateMeta instances.
    """
    term = deref(term)
    if is_var(term):
        return
    if isinstance(term, Call):
        for a in term.args:
            _collect_vars_from_term(a, result)
        return
    if isinstance(term, And):
        _collect_vars_from_term(term.left, result)
        _collect_vars_from_term(term.right, result)
        return
    if isinstance(term, Or):
        _collect_vars_from_term(term.left, result)
        _collect_vars_from_term(term.right, result)
        return
    if isinstance(term, Not):
        _collect_vars_from_term(term.operand, result)
        return
    if isinstance(term, list):
        for e in term:
            _collect_vars_from_term(e, result)
        return
    if is_term_instance(term):
        for fname in term_field_names(term):
            val = getattr(term, fname)
            if is_var(val):
                if fname not in result:
                    result[fname] = val
            else:
                _collect_vars_from_term(val, result)


def _expand_predicate(pred: Predicate, ctx: _ExpansionContext) -> Predicate:
    """Expand goals in a single Predicate node's body."""
    if pred.body is None or pred.body is True:
        return pred

    # Collect field_name → Var mapping from the head for auto-binding.
    clause_vars: dict[str, Any] = {}
    _collect_vars_from_term(pred.head, clause_vars)
    _collect_vars_from_term(pred.body, clause_vars)
    ctx._clause_vars = clause_vars

    new_body = _expand_goal(pred.body, ctx)
    if new_body is pred.body:
        return pred
    return Predicate(head=pred.head, body=new_body)


def _expand_goal(goal: Any, ctx: _ExpansionContext) -> Any:
    """Expand a single goal, recursing into And/Or/Not/IfExpr."""
    if isinstance(goal, And):
        new_left = _expand_goal(goal.left, ctx)
        new_right = _expand_goal(goal.right, ctx)
        if new_left is goal.left and new_right is goal.right:
            return goal
        return And(left=new_left, right=new_right)
    if isinstance(goal, Or):
        new_left = _expand_goal(goal.left, ctx)
        new_right = _expand_goal(goal.right, ctx)
        if new_left is goal.left and new_right is goal.right:
            return goal
        return Or(left=new_left, right=new_right)
    if isinstance(goal, Not):
        new_inner = _expand_goal(goal.operand, ctx)
        if new_inner is goal.operand:
            return goal
        return Not(operand=new_inner)
    if isinstance(goal, IfExpr):
        new_test = _expand_goal(goal.test, ctx)
        new_body = _expand_goal(goal.body, ctx)
        new_orelse = _expand_goal(goal.orelse, ctx)
        if (new_test is goal.test and new_body is goal.body
                and new_orelse is goal.orelse):
            return goal
        return IfExpr(test=new_test, body=new_body, orelse=new_orelse)
    if isinstance(goal, TupleLiteral):
        new_elements = [_expand_goal(element, ctx) for element in goal.elements]
        if all(new is old for new, old in zip(new_elements, goal.elements)):
            return goal
        return TupleLiteral(elements=new_elements, position=goal.position)
    return _try_expand(goal, ctx)


def _try_expand(goal: Any, ctx: _ExpansionContext) -> Any:
    """Apply built-in expansion rules to a single goal."""
    expanded = _expand_regex(goal, ctx)
    if expanded is not goal:
        return expanded
    expanded = _expand_arrow_patterns(goal, ctx)
    if expanded is not goal:
        return expanded
    return goal


# ── Regex goal expansion ────────────────────────────────────────────────────


def _is_constant_name(name: str) -> bool:
    """True for the module-constant lexical class (``_PI_``, ``_円周率_``).

    Mirrors ``term_rewriting._is_constant_name``; kept local so this module
    stays free of a templating import.
    """
    return (
        len(name) >= 3
        and name[0] == "_" and name[-1] == "_"
        and name[1] != "_" and name[-2] != "_"
        and not name[1].isdigit()
    )


def _is_logic_var_name(name: str) -> bool:
    """Check if a name follows the logic variable convention.

    Constant-shaped names (``_PI_``) are excluded too — pinned by
    test_var_classifier_conformance.
    """
    if name == "_":
        return False
    if name.startswith("__"):
        return False
    if _is_constant_name(name):
        return False
    if name.startswith("_"):
        return True
    # Capital initial (ISO): ``X``, ``FOO``, ``Foo``.  ``Foo`` joined
    # this class on 2026-09-10 -- see term_rewriting._is_logic_var_name,
    # which is the copy that carries the full rationale.  All five
    # copies move together (test_var_classifier_conformance).
    return name[:1].isupper()


def _extract_static_pattern(goal: Call) -> str | None:
    """Return the pattern text if the first arg is a text literal, else None.

    THE FLIP (2026-09-06-atoms-as-cells-strings §7): a ``r"\\d+"`` literal in
    a ``.clausal`` file compiles to the ATOM ``("\\d+",)`` under the default
    ``-double_quotes(atom)`` and to the ``str`` under
    ``-double_quotes(chars)`` -- both are static patterns, and missing the
    atom shape silently demoted EVERY literal pattern to the dynamic
    runtime-autobind path (no pre-compilation, and the compile-time
    auto-binding of named groups stopped happening).
    """
    if not goal.args:
        return None
    first = goal.args[0]
    if isinstance(first, str):
        return first
    if _term_is_atom(first):
        return _atom_spelling(first)
    value = getattr(first, "value", None)
    if isinstance(value, str):
        return value
    if _term_is_atom(value):
        return _atom_spelling(value)
    return None


def _get_call_name(goal: Call) -> str | None:
    """Extract the functor name from a Call node."""
    func = goal.func
    if isinstance(func, LoadName):
        return func.name
    return None


def _is_regex_goal(goal: Any, ctx: _ExpansionContext) -> bool:
    """True iff *goal* calls the regex ``match``/``search`` predicate.

    Verified by identity against ``clausal.modules.py.re`` through the module's
    own binding (mirrors :func:`_is_reflection_goal`), so a same-named
    user predicate — ``match(A, B) <- (A is B)`` — is never hijacked (F003).
    """
    if not isinstance(goal, Call):
        return False
    name = _get_call_name(goal)
    if name is None:
        return False
    short_name = name.rsplit(".", 1)[-1]
    if short_name not in ("match", "search"):
        return False
    bound = ctx.module_dict.get(name)
    if bound is None:
        return False
    from clausal.modules.py import re as _regex_mod

    return bound is getattr(_regex_mod, short_name, None)


def _expand_regex(goal: Any, ctx: _ExpansionContext) -> Any:
    """Expand match/2 and search/2 with auto-binding + pre-compilation.

    Also pre-compiles static patterns in match/3 and search/3.
    """
    if not isinstance(goal, Call):
        return goal

    if not _is_regex_goal(goal, ctx):
        return goal

    nargs = len(goal.args)

    pattern_str = _extract_static_pattern(goal)
    if pattern_str is None:
        # Dynamic pattern (variable or f-string): group names are unknown at
        # compile time, so wire in a runtime auto-binding fallback (F007).
        if nargs == 2:
            return _dynamic_autobind_chain(goal, ctx)
        return goal

    try:
        re_key = ctx.intern_pattern(pattern_str)
    except _re.error:
        return goal

    compiled = ctx.module_dict[re_key]

    if nargs == 3:
        new_args = [LoadName(name=re_key)] + goal.args[1:]
        return Call(func=goal.func, args=new_args, kwargs=goal.kwargs)

    if nargs != 2:
        return goal

    # match/2 or search/2: check for auto-bindable groups.  The gate is the
    # variable classifier, so it moves with it -- see ``_bind_if_present``
    # below for the 2026-09-10 widening to capital-initial names.
    bindable = {
        name: idx
        for name, idx in compiled.groupindex.items()
        if _is_logic_var_name(name)
    }

    if not bindable:
        new_args = [LoadName(name=re_key)] + goal.args[1:]
        return Call(func=goal.func, args=new_args, kwargs=goal.kwargs)

    # Auto-bind: rewrite to match/3 + Unify chain.
    groups_var = Var()

    match_goal = Call(
        func=goal.func,
        args=[LoadName(name=re_key), goal.args[1], groups_var],
        kwargs=[],
    )

    from clausal.terms import PyThunk

    chain = match_goal
    for group_name in sorted(bindable, key=lambda n: bindable[n]):
        thunk = PyThunk(
            lambda g, _n=group_name: g[_n],
            (groups_var,),
        )
        # Find the clause Var for this group name.
        target_var = ctx.find_var_for_group(group_name)
        if target_var is None:
            # Group name doesn't match any clause variable — create a fresh
            # Var (e.g. typo case: YAER binds a new variable nobody reads).
            target_var = Var()

        unify_goal = Unify(left=target_var, right=thunk)
        chain = And(left=chain, right=unify_goal)

    return chain


def _dynamic_autobind_chain(goal: Call, ctx: _ExpansionContext) -> Any:
    """Runtime named-group auto-binding for a dynamic ``match/2``/``search/2``.

    The pattern is not a literal, so its group names are unknown until the goal
    runs. Rewrite ``match(P, S)`` to ``match(P, S, G)`` and append one Unify per
    clause variable: a thunk scans the runtime groups dict for a key whose
    lowered/underscore-stripped name equals the variable's field name. When a
    matching, non-None group value is present it binds; otherwise the thunk
    returns the variable itself so the Unify is a harmless no-op. The goal's own
    top-level argument variables (pattern, subject) are excluded so a group can
    never clobber them.

    The no-op answer is a FRESH ``Var`` built inside the thunk, so it is
    per-activation by construction. A closure default over the clause-TEMPLATE
    Var would alias every activation through that one shared variable, so two
    differently-instantiated calls in a single derivation would wrongly
    conflict (F007 regression). Passing the target variable through the
    thunk's ``var_objects`` fixed that, but it cannot survive THE FLIP: thunk
    arguments cross through ``to_python`` (spec §9.1), so a target already
    bound to the ATOM ``("one",)`` came back as the STRING ``"one"`` and the
    "harmless no-op" Unify then FAILED against its own variable. A fresh Var
    never crosses the boundary at all.
    """
    from clausal.terms import PyThunk

    groups_var = Var()
    match_goal = Call(
        func=goal.func,
        args=[goal.args[0], goal.args[1], groups_var],
        kwargs=[],
    )

    arg_vars = {id(deref(a)) for a in goal.args if is_var(deref(a))}

    def _bind_if_present(g, _field):
        if isinstance(g, dict):
            for key, val in g.items():
                # Same naming gate as static expansion: a group name that
                # is spelled like a Clausal LOGIC VARIABLE auto-binds
                # (docs/regex.md).  That is capital-initial (``YEAR``,
                # ``Year``) or leading-underscore (``_rest``); a lowercase
                # name is an atom spelling and stays regex-only.  TitleCase
                # joined the variable class on 2026-09-10 and this gate
                # follows it deliberately -- a group named ``Year`` that did
                # NOT bind a clause variable named ``Year`` would make the
                # gate disagree with the language about what a variable is.
                # A group that matched nothing (val None) is skipped — unlike
                # static expansion, which binds None — because in dynamic mode
                # EVERY clause variable is a candidate, and binding None to a
                # variable that merely shares a group's name would clobber it.
                if isinstance(key, str) and _is_logic_var_name(key) \
                        and key.lstrip("_").lower() == _field \
                        and val is not None:
                    return val
        # No group of that name: a FRESH variable, so the Unify succeeds and
        # binds nothing, whatever the target already holds.
        return Var()

    chain = match_goal
    for field_name, target_var in ctx._clause_vars.items():
        if id(deref(target_var)) in arg_vars:
            continue
        thunk = PyThunk(
            lambda g, _f=field_name: _bind_if_present(g, _f),
            (groups_var,),
        )
        chain = And(left=chain, right=Unify(left=target_var, right=thunk))

    return chain


# ── Arrow match-pattern expansion (reflection sugar) ────────────────────────
#
# ``reified_clause(SRC, MyPred(A, B) <- (Goalx(A), Goaly(B)))`` — the arrow
# argument arrives here as a runtime ``Predicate`` node (head/goals are
# middle-layer ``Call`` nodes, variables are the clause's real ``Var``
# objects).  It is rewritten into construction of the reified vocabulary,
# mirroring ``clausal.reflection._ClauseReifier``:
#
#   Call('Clause', [Call('Goal', ['MyPred', [A, B], []]),
#                   [Call('Goal', ['Goalx', [A], []]),
#                    Call('Goal', ['Goaly', [B], []])],
#                   Var()])
#
# The construction compiles like any other compound body argument, so the
# pattern's variables are per-invocation clause variables (capture), and
# operator/unary nodes pass through raw with mapped operands — matching
# the reifier's raw-operator representation.

_REFLECTION_BUILTIN_NAMES = frozenset((
    "reified_item", "reified_clause", "reified_file_item", "reified_subterm",
    "clause_head", "clause_body", "goal_functor",
))

# Vocabulary functors referenced by generated pattern constructions.
_VOCABULARY_NAMES = ("Clause", "Goal", "Atom", "IfThenElse")


def _is_reflection_goal(goal: Call, ctx: _ExpansionContext) -> bool:
    """True iff *goal* calls one of the reflection builtins.

    Verified by identity against ``clausal.modules.reflection`` through the
    module's own binding, so a same-named user predicate never triggers the
    sugar."""
    name = _get_call_name(goal)
    if name is None:
        return False
    # Imported names are remapped to dotted form ("reflection.reified_clause");
    # _process_imports stores the value under both the short and dotted keys.
    short_name = name.rsplit(".", 1)[-1]
    if short_name not in _REFLECTION_BUILTIN_NAMES:
        return False
    bound = ctx.module_dict.get(name)
    if bound is None:
        return False
    from clausal.modules import reflection

    return bound is getattr(reflection, short_name, None)


def _ensure_vocabulary(ctx: _ExpansionContext) -> None:
    """Make the vocabulary functors resolvable in the module.

    No-op when the module already imported them (same classes)."""
    from clausal import reflection

    for name in _VOCABULARY_NAMES:
        ctx.module_dict.setdefault(name, getattr(reflection, name))


def _expand_arrow_patterns(goal: Any, ctx: _ExpansionContext) -> Any:
    if not isinstance(goal, Call) or not _is_reflection_goal(goal, ctx):
        return goal
    new_args = [_map_pattern_arg(arg, ctx) for arg in goal.args]
    if all(new is old for new, old in zip(new_args, goal.args)):
        return goal
    return Call(func=goal.func, args=new_args, kwargs=goal.kwargs,
                position=goal.position)


def _map_pattern_arg(arg: Any, ctx: _ExpansionContext) -> Any:
    if isinstance(arg, Predicate):
        _ensure_vocabulary(ctx)
        return _pattern_clause(arg, ctx)
    if isinstance(arg, list):
        new_elements = [_map_pattern_arg(element, ctx) for element in arg]
        if all(new is old for new, old in zip(new_elements, arg)):
            return arg
        return new_elements
    return arg


def _pattern_clause(node: Predicate, ctx: _ExpansionContext) -> Call:
    head = _pattern_term(node.head, ctx)
    goals = _pattern_goal_list(node.body, ctx)
    # Explicit fresh Var wildcards the position field per invocation.
    return Call(func=LoadName(name="Clause"), args=[head, goals, Var()],
                kwargs=[])


def _functor_name(func: Any) -> str | None:
    if isinstance(func, LoadName):
        return func.name
    if isinstance(func, LoadAttr):
        base = _functor_name(func.object)
        return None if base is None else f"{base}.{func.attr}"
    return None


def _pattern_term(term: Any, ctx: _ExpansionContext) -> Any:
    """Map a pattern subterm to its reified-vocabulary construction."""
    term = deref(term)
    if is_var(term):
        return term  # capture variable — stays a clause variable
    if _term_is_atom(term):
        # THE FLIP (spec §5.1): a QUOTED atom literal (``'k'``, or ``"k"`` in
        # the default mode) is the arity-0 CELL by the time the pattern is
        # expanded, and the reified vocabulary spells an atom ``Atom(name)``
        # -- the same node a BARE name maps to just below.  Without this the
        # two spellings of one atom produced two different patterns, and a
        # quoted one matched nothing.
        return Call(func=LoadName(name="Atom"),
                    args=[_atom_spelling(term)], kwargs=[])
    if isinstance(term, Call):
        name = _functor_name(term.func)
        if name is None:
            return term
        args = [_pattern_term(a, ctx) for a in term.args]
        kwargs = [[kw.name, _pattern_term(kw.value, ctx)]
                  for kw in term.kwargs]
        return Call(func=LoadName(name="Goal"), args=[name, args, kwargs],
                    kwargs=[])
    if isinstance(term, LoadName):
        return Call(func=LoadName(name="Atom"), args=[term.name], kwargs=[])
    if isinstance(term, LoadAttr):
        dotted = _functor_name(term)
        if dotted is None:
            return term
        return Call(func=LoadName(name="Atom"), args=[dotted], kwargs=[])
    if isinstance(term, Predicate):
        return _pattern_clause(term, ctx)
    if isinstance(term, IfExpr):
        return Call(
            func=LoadName(name="IfThenElse"),
            args=[_pattern_term(term.test, ctx),
                  _pattern_term(term.body, ctx),
                  _pattern_term(term.orelse, ctx)],
            kwargs=[],
        )
    if isinstance(term, list):
        new_elements = [_pattern_term(element, ctx) for element in term]
        if all(new is old for new, old in zip(new_elements, term)):
            return term
        return new_elements
    if isinstance(term, (And, Or, Not, TupleLiteral)):
        # Goal-shaped nodes reaching term position: leave to the caller's
        # goal-context handling; raw here would never match reified output.
        return term
    from clausal.pythonic_ast.nodes import Node

    if isinstance(term, Node):
        # Operator/unary/star nodes stay raw with mapped operands —
        # mirroring the reifier's raw-operator representation.
        return term.transform_children(lambda child: _pattern_term(child, ctx))
    return term  # literals, thunks, opaque values


def _pattern_goal(goal: Any, ctx: _ExpansionContext) -> Any:
    """Map a pattern goal; conjunctions become lists (as in the reifier)."""
    goal = deref(goal)
    if isinstance(goal, TupleLiteral):
        flat: list = []
        for element in goal.elements:
            mapped = _pattern_goal(element, ctx)
            flat.extend(mapped) if isinstance(mapped, list) else flat.append(mapped)
        return flat
    if isinstance(goal, And):
        left = _pattern_goal(goal.left, ctx)
        right = _pattern_goal(goal.right, ctx)
        left = left if isinstance(left, list) else [left]
        right = right if isinstance(right, list) else [right]
        return left + right
    if isinstance(goal, Or):
        return Or(left=_pattern_goal(goal.left, ctx),
                  right=_pattern_goal(goal.right, ctx),
                  position=goal.position)
    if isinstance(goal, Not):
        return Not(operand=_pattern_goal(goal.operand, ctx),
                   position=goal.position)
    if isinstance(goal, IfExpr):
        return Call(
            func=LoadName(name="IfThenElse"),
            args=[_pattern_goal(goal.test, ctx),
                  _pattern_goal(goal.body, ctx),
                  _pattern_goal(goal.orelse, ctx)],
            kwargs=[],
        )
    return _pattern_term(goal, ctx)


def _pattern_goal_list(body: Any, ctx: _ExpansionContext) -> Any:
    """Map a pattern body to the goals-list side of a Clause pattern."""
    if body is True:
        return []  # fact pattern: ``HEAD <- True``
    body = deref(body)
    if is_var(body):
        return body  # ``HEAD <- GOALS`` captures the whole goal list
    mapped = _pattern_goal(body, ctx)
    return mapped if isinstance(mapped, list) else [mapped]
