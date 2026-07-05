"""clausal.logic.goal_expansion — body-walking goal expansion pass (V3-3).

Transforms individual goals within clause bodies.  Applied after term
expansion but before compilation in the ``compile_module`` pipeline.

Built-in expansions
-------------------
- **Regex pre-compilation + auto-binding** (Phase 3): static ``Match/2``
  and ``Search/2`` patterns with ALLCAPS/leading-underscore named groups
  are rewritten to ``Match/3`` + ``Unify`` chains.  The compiled
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


def _is_logic_var_name(name: str) -> bool:
    """Check if a name follows the logic variable convention."""
    if name == "_":
        return False
    if name.startswith("__"):
        return False
    if name.startswith("_"):
        return True
    return name.isupper()


def _extract_static_pattern(goal: Call) -> str | None:
    """Return the pattern string if the first arg is a string literal, else None."""
    if not goal.args:
        return None
    first = goal.args[0]
    if isinstance(first, str):
        return first
    if hasattr(first, "value") and isinstance(first.value, str):
        return first.value
    return None


def _get_call_name(goal: Call) -> str | None:
    """Extract the functor name from a Call node."""
    func = goal.func
    if isinstance(func, LoadName):
        return func.name
    return None


def _expand_regex(goal: Any, ctx: _ExpansionContext) -> Any:
    """Expand Match/2 and Search/2 with auto-binding + pre-compilation.

    Also pre-compiles static patterns in Match/3 and Search/3.
    """
    if not isinstance(goal, Call):
        return goal

    func_name = _get_call_name(goal)
    if func_name is None:
        return goal
    # Support dotted names like "clausal.regex.Match"
    short_name = func_name.rsplit(".", 1)[-1] if "." in func_name else func_name
    if short_name not in ("Match", "Search"):
        return goal

    nargs = len(goal.args)

    pattern_str = _extract_static_pattern(goal)
    if pattern_str is None:
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

    # Match/2 or Search/2: check for auto-bindable groups.
    bindable = {
        name: idx
        for name, idx in compiled.groupindex.items()
        if _is_logic_var_name(name)
    }

    if not bindable:
        new_args = [LoadName(name=re_key)] + goal.args[1:]
        return Call(func=goal.func, args=new_args, kwargs=goal.kwargs)

    # Auto-bind: rewrite to Match/3 + Unify chain.
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
