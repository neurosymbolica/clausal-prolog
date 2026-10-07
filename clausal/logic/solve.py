"""clausal.logic.solve — top-level query API (Step 7).

Public API
----------
solve(goal, module=None, trail=None)             → Iterator[Trail]
once(goal, module=None, trail=None)              → Trail | None
query(goal, variables, module=None, trail=None)  → Iterator[dict[str, Any]]
call(functor, *args, module, trail=None)         → Iterator[Trail]

The ``module`` argument is optional for ``solve``, ``once``, and ``query``:
when omitted, the module is inferred from the PredicateMeta classes in the
goal term.  You can also pass an imported ``.clausal`` Python module directly
(e.g. ``import hello; solve(("greeting", X), module=hello)``), or its dotted name as a
str (``solve(("greeting", X), "hello")``) — see ``resolve_module``, which is
also what the module-qualified goal ``(":", M, G)`` resolves *M* with.

Design
------
``solve`` handles arbitrary goal terms — simple_ast nodes (Call, And, Or, …),
CELL goals (``("greeting", X := Var())``) and runtime term instances.  Runtime
terms are converted to simple_ast nodes automatically.

The query idiom: from a plain ``.py`` file, ``solve(("pred", X := Var()),
module=m)`` with the module passed every time; in Python hosted by a
``.clausal`` file, the goal-position seam ``for X in --pred(X):``.  Calling a
predicate name (``pred(X := Var())``) is a ``TypeError``: a module
attribute for a predicate is its name, a ``str``.  Vars embedded
in the goal are injected into the compiled function's globals so that the
compiled code references the *user's* Var objects.  This lets the user read
bindings via ``deref()`` on their original Var objects after each solution.

``once`` returns the Trail for the first solution (bindings still live),
or None if the goal fails.

``query`` wraps solve and fully dereferences a named set of variables,
returning a plain dict per solution.

``call`` drives a named predicate's compiled dispatch function directly.
The user passes Var objects as args.  This is the fastest path for simple
predicate calls.
"""

from __future__ import annotations

import functools as _functools
import sys
import types as _types
import weakref
from dataclasses import fields as _dc_fields, is_dataclass as _is_dataclass
from decimal import Decimal
from fractions import Fraction
from typing import Any, Iterator

from clausal.logic.variables import Var, Trail, deref, is_var, unify
from clausal.logic.to_python import strip_atom_tags as _strip_atom_tags, has_atom_tag as _has_atom_tag
from clausal.logic.atoms import (
    is_atom as _term_is_atom, mint as _mint_atom, spelling as _spelling, is_mangled, demangle,
)
from clausal.logic.database import Clause, Database, Module
from clausal.logic.predicate import (
    is_term_instance, term_field_names, _dispatch_at,
    is_declared_predicate_name,
    _refuse_unqualified_other_arity, binding_grants_arity,
)
from clausal.logic.trampoline import StepGenerator, DONE, _drive_until_yield
from clausal.logic.cells import (
    is_chars, chars_text,   # stage 1: the chars carrier
    CELL_GOAL_CONTROL_FUNCTORS,
    QUALIFIED_GOAL_FUNCTOR,
    compound_cell_shape,
    refuse_control_construct_cell,
    resolve_qualified_goal_cell,
    qualify_mangled_goal,
    DECLARED_ATOMS_KEY,
    IMPORT_FROM_KEY,
)
from clausal.terms import Quantity, Undefined
from clausal.terms import (
    Call as _ReifiedCall,
    LoadName as _ReifiedLoadName,
    LoadAttr as _ReifiedLoadAttr,
)
from clausal.terms import PyThunk as _PyThunk
from clausal.pythonic_ast.nodes import Lambda as _Lambda, Node as _GoalNode
from clausal import _sandbox_state


def _sandbox_query_edge(target: Any, context: str) -> None:
    """In the sandbox a Python-side query is a Clausal Prolog frame: its
    ``M:G`` may not resolve into a ``.pl`` or (non-allowlisted) Python
    module (:mod:`clausal.sandbox`)."""
    if _sandbox_state.ACTIVE and target is not None:
        from clausal.logic.dialect_edge import refuse_edge  # noqa: PLC0415
        from clausal.sandbox import QUERY_FRAME  # noqa: PLC0415
        refuse_edge(QUERY_FRAME, target, context)


def _sandbox_entry(goal: Any, context: str) -> None:
    """In the sandbox: refuse a Python-built goal holding anything but data
    (:func:`clausal.sandbox.check_term`)."""
    if _sandbox_state.ACTIVE:
        from clausal.sandbox import check_term  # noqa: PLC0415
        check_term(goal, context)


def _sandbox_module(module: Any, context: str) -> None:
    """In the sandbox a query never runs in a ``.pl`` or Python module."""
    if _sandbox_state.ACTIVE and module is not None:
        from clausal.sandbox import check_query_module  # noqa: PLC0415
        check_query_module(module, context)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _deref_walk_py(term: Any) -> Any:
    """Fully dereference a term, recursively walking all Var bindings.

    Unbound Vars remain as Var objects in the result.
    """
    term = deref(term)
    if is_var(term):
        return term
    if term is None or isinstance(term, (bool, int, float, str, bytes, complex)):
        return term
    if isinstance(term, list):
        return [_deref_walk_py(e) for e in term]
    if isinstance(term, tuple):
        return tuple(_deref_walk_py(e) for e in term)  # A01-F008: was blind
    if isinstance(term, dict):
        # A04-F005: rebuild plain-dict values so a frozen answer holding a dict
        # does not share live inner Vars that unbind on backtracking.
        return {_deref_walk_py(k): _deref_walk_py(v) for k, v in term.items()}
    if isinstance(term, (set, frozenset)):
        return type(term)(_deref_walk_py(e) for e in term)  # A04-F005
    # A01-F008: delegate to __walk__ hooks (DictTerm, Seg*),
    # keeping this Python fallback in sync with the C twin (_tabling_core
    # do_deref_walk) and with walk() itself. Preserves F018 Seg promotion.
    hook = getattr(term, "__walk__", None)
    if hook is not None:
        return hook()
    if is_term_instance(term):
        cls = type(term)
        # W4a: ``is_term_instance`` is dataclass-only, so *cls* is a
        # dataclass term class -- a pythonic_ast node like ``BinOp`` -- and
        # calling it is the rebuild.  (It used to look up
        # ``_clausal_head`` first, for the predicate-INSTANCE shape that no
        # longer exists.  It also used to check for a ``_clausal_new``
        # Phase-0 fast-constructor first -- that gate, and its four siblings
        # in inspection.py and the two C extensions, were retired in W4b,
        # 2026-09-23: `_make_fast_new` and the `_clausal_new` attachment were
        # already gone since W4a, so every one of the five gates fell
        # straight through to this reconstruction on every call.)
        return cls(**{
            name: _deref_walk_py(getattr(term, name))
            for name in term_field_names(term)
        })
    return term

_deref_walk = _deref_walk_py

try:
    from clausal.logic._tabling_core import _deref_walk as _deref_walk_c
    _deref_walk = _deref_walk_c
except ImportError:
    pass


def _drive_trampoline(dispatch_fn: Any, trail: Trail, *args: Any) -> Iterator[Trail]:
    """Drive a trampoline-protocol dispatch function, yielding trail per solution."""
    from clausal.logic.tabling import begin_drive_episode, end_drive_episode

    sg = StepGenerator(dispatch_fn, None, None, None, *args, trail)
    begin_drive_episode()
    try:
        while True:
            result = _drive_until_yield(sg)
            if result is None:
                return
            yield trail
    except NameError as exc:
        # Failure-only seam, and the only one solve time needs: this is the
        # outermost driver, so a NameError arriving here has already escaped
        # every catch/3 below it and is on its way to the author.  The hunt it
        # triggers reads sibling ``-module(...)`` lists off disk, which is why
        # it sits in an ``except`` and not on the loop — a solution costs
        # nothing, a raise pays once.
        from clausal.predicate_diagnostics import (  # noqa: PLC0415
            enrich_undefined_name,
        )
        better = enrich_undefined_name(exc)
        if better is None:
            raise
        # Re-raise on the ORIGINAL traceback so the frame still points at the
        # clause that used the name, and suppress the chained duplicate — the
        # replacement carries the same args.
        raise better.with_traceback(exc.__traceback__) from None
    finally:
        # A04-F007: close the root generator on ANY exit — normal, caller
        # abandonment (GeneratorExit), or a body exception that propagated past
        # the trampoline. This synchronously runs the tabled-wrapper cleanup
        # (drop a poisoned "evaluating" entry) instead of leaving it to GC.
        # close() is NOT sufficient on its own: it closes only sg's inner
        # generator, and a SuspendedConsumer registered on a table entry keeps
        # a parked tabled-wrapper frame reachable forever, so GeneratorExit
        # never reaches that wrapper's repair code. end_drive_episode() then
        # drops any still-"evaluating" entry this drive created (store, leader
        # stack, suspended consumers) so later queries recompute instead of
        # silently consuming the partial answer set.
        try:
            sg.close()
        finally:
            end_drive_episode()


def _control_node_holds_a_cell_goal(term: Any) -> bool:
    """True when *term* is a control NODE (And/Or/Not/IfExpr/TupleLiteral)
    with a CELL somewhere in goal position under it."""
    from clausal.pythonic_ast import nodes  # noqa: PLC0415
    if isinstance(term, (nodes.And, nodes.Or)):
        return (_goal_is_or_holds_cell(term.left)
                or _goal_is_or_holds_cell(term.right))
    if isinstance(term, nodes.Not):
        return _goal_is_or_holds_cell(term.operand)
    if isinstance(term, nodes.IfExpr):
        return any(_goal_is_or_holds_cell(g)
                   for g in (term.test, term.body, term.orelse))
    if isinstance(term, nodes.TupleLiteral):
        return any(_goal_is_or_holds_cell(g) for g in term.elements)
    return False


def _goal_is_or_holds_cell(goal: Any) -> bool:
    goal = deref(goal)
    return (compound_cell_shape(goal)[0]
            or _control_node_holds_a_cell_goal(goal))


def _term_to_goal(term: Any, db: Any = None) -> Any:
    """Convert a runtime term instance to a simple_ast goal node.

    ``solve(("greeting", N := Var()), module=m)`` passes a CELL goal, and a
    runtime term instance can arrive too; neither is a simple_ast ``Call``
    node.  The compiler expects goal nodes, so we convert here.
    A CELL goal ``("f", a, b)`` lowers (P3-3 Task 5, R11): slot 0
    names the predicate, the rest are its arguments, so it becomes
    ``AstCall(LoadName("f"), [a, b])``, which is what makes a cell goal and a
    class-term goal share compiled code and answer alike.  Two cell functors are not ordinary calls
    and are handled before that: the module-qualified form ``(":", M, G)``,
    which lowers to the INNER goal's node (P3-3 Task 6), and the control
    constructs (deferred to the ISO-surface phase) — see
    ``cells.resolve_qualified_goal_cell`` and
    ``cells.refuse_control_construct_cell``.

    A qualified goal's module SWITCH is not made here — this function lowers a
    term to a node and has no say in which database the node compiles against.
    ``_strip_module_qualification`` makes it, in ``_compile_as_query``, before
    this function is reached, so on the query path the qualification is
    already gone by the time it arrives.  The branch below is what keeps the
    lowering total for a direct caller (and keeps the designator validated
    wherever the term is lowered): it resolves, which is what raises on an
    unresolvable module, then lowers the inner goal.

    Simple_ast nodes and other goal forms pass through unchanged.
    """
    # W4: a mangled functor is a qualified goal.  *db* is the compiling
    # module's (ruling Q0 hint), so a handle naming it resolves when popped.
    term = qualify_mangled_goal(term, db)
    from clausal.pythonic_ast.nodes import Call as AstCall, LoadName

    if type(term) in (list, bytes, tuple) and len(term) == 0:
        # The EMPTY LIST in goal position, in any spelling (fix round 2,
        # item 4): ``solve("", m)`` raised while ``solve([], m)`` fell
        # through, for one and the same term.  ``[]`` is the atom ``'[]'``,
        # so the answer is ``existence_error(procedure, '[]'/0)``.
        from clausal.logic.exceptions import LogicException, string_goal_error
        raise LogicException(string_goal_error("", 0, "solve/1"))
    if is_chars(term):                       # a STRING in goal position: no procedure '.'/2
        # THE FLIP (spec §6.4): a ``str`` is a STRING, not an atom.
        # ``solve("z0", m)`` used to be the same call as ``solve(("z0",), m)``;
        # it is now an error, and the cell spelling is the only one that names
        # a goal.  Task 15 item 3 (ISO alignment): the string is the compound
        # ``'.'/2``, so what is missing is the PROCEDURE, not callability.
        from clausal.logic.exceptions import LogicException, string_goal_error
        raise LogicException(string_goal_error(chars_text(term), 0, "solve/1"))
    if type(term) is str:                     # STAGE 2: an atom IS the 0-arity goal of its name
        if term in CELL_GOAL_CONTROL_FUNCTORS:    # parity with call/N (F5): ','/0 is refused, not looked up
            refuse_control_construct_cell(term, term, "solve/1")
        # The 0-arity control constructs (ISO 7.8.1, 7.8.2) have no
        # predicate row -- the compiler lowers them -- so looking them up
        # raised PredicateNotFoundError where call/1 (``_resolve_named_goal``)
        # already answered: ``true`` succeeds once, ``fail``/``false`` fail.
        # Lowered to the goal literals the compiler reads the same way.
        if term == "true":
            return True
        if term == "!":
            # A cut that is the WHOLE query is local to it (ISO 7.8.3) and
            # cuts nothing: it succeeds once, as ``call(!)`` does
            # (``higher_order._ZERO_ARITY_CONTROL_GOALS``).  It used to be
            # looked up as ``!/0`` and raised PredicateNotFoundError.  A cut
            # inside a body term is refused by call/1's converter.
            return True
        if term in ("fail", "false"):
            return False
        return AstCall(func=LoadName(name=term), args=[], kwargs=[])
    if _control_node_holds_a_cell_goal(term):
        # A cell nested in an And/Or/Not/if-then-else NODE: the compiler's
        # goal lowering (terms_to_goalop) reads goal nodes and has no cell
        # arm, so ``solve(And(("p", X), ("q", X)), m)`` raised
        # ``NotImplementedError: goal shape not yet supported (tuple)``.
        # call/1 runs exactly such a body term (call_body's converter lowers
        # every cell, qualified and control cells included, with the same
        # diagnostics), so the query is that call.
        return AstCall(func=LoadName(name="call"), args=[term], kwargs=[])
    is_cell_goal, functor = compound_cell_shape(term)
    if is_cell_goal:
        if functor == QUALIFIED_GOAL_FUNCTOR and len(term) == 3:
            _module, inner = resolve_qualified_goal_cell(
                term, "solve/1", call_extra=0, dialect_gate=False)
            _sandbox_query_edge(_module, "solve/1")
            return _term_to_goal(inner, getattr(_module, "db", None))
        refuse_control_construct_cell(term, functor, "solve/1")
        return AstCall(
            func=LoadName(name=functor), args=list(term[1:]), kwargs=[],
        )
    return term


_VAR_SENTINEL = object()

# Cache: (structural_key, id(module)) →
#   (fn, code_object, var_names, thunk_names, weakref-to-module)
# The weakref is checked on every hit (see the insert site in
# _compile_as_query): an id alone can be reused by a later module.
_query_cache: dict = {}

# Upper bound on distinct cached query shapes; see eviction note at the
# insertion site in _compile_as_query.
_QUERY_CACHE_MAX = 4096


class _Uncacheable(Exception):
    """Raised internally when a goal contains a ground leaf we cannot key on."""


def _structural_key(term: Any, var_index: dict, thunks: list | None = None) -> tuple:
    """Recursively canonicalise a goal term into a hashable structural key.

    The compiled query bakes ground arguments into the generated code as literal
    constants, while logic variables become rebindable globals (remapped on a
    cache hit).  So two goals may share compiled code *only* when they have the
    same structure, the same ground literal *values* (not merely the same
    types), and variables in the same positions.  This key captures all three:

      - variables become ``('var', n)`` where ``n`` is the first-occurrence index,
        so ``p(V, V)`` (aliased) and ``p(V, W)`` (distinct) get different keys;
      - ground leaves become ``('lit', type, value)`` — keying on the value, which
        is what distinguishes ``p(1, V)`` from ``p(2, V)``;
      - compound/predicate/sequence terms recurse structurally;
      - a CELL gets its own ``('cell', functor, args)`` tag rather than falling
        into the ``('seq', tuple, ...)`` branch below (P3-3 Task 5).  A cell in
        GOAL position compiles to a CALL, while the equal-shaped tuple in
        argument position is baked as tuple DATA — two different compiled
        artifacts, so they get two different tags rather than one that reads
        "a tuple of N+1 elements" for both.  (There is no live collision to
        repair: ``_goal_cache_key`` admits only goal shapes, and a data tuple
        is never a top-level goal.  The tag is what keeps that true.)

    Raises :class:`_Uncacheable` if a ground leaf is unhashable (e.g. a list,
    dict, or ndarray argument), in which case the caller skips caching entirely
    rather than risk a stale or colliding entry.  A ``Lambda`` node raises it
    too: its body's variables are out of the remap's reach (see the node
    branch below).

    *thunks*, when a list is passed, receives every ``PyThunk`` leaf in
    traversal order — see ``_goal_cache_key``.
    """
    t = deref(term)
    if is_var(t):
        idx = var_index.get(id(t))
        if idx is None:
            idx = len(var_index)
            var_index[id(t)] = idx
        return ("var", idx)
    if isinstance(t, _PyThunk):
        # A ``++expr`` escape.  The thunk OBJECT is rebuilt on every execution
        # of the hosting Python code (a fresh closure over this iteration's
        # locals), so keying it by identity — what the ``hash(t)`` fallback
        # below used to do — gave every execution its own compiled query.
        # What is stable is the SITE: the lambda's code object is a constant
        # of the enclosing function, so two thunks share compiled code exactly
        # when they came from the same ``++``.  The closure itself is supplied
        # per execution, like a Var, by rebinding the ``_pyt_<id>`` global the
        # compiled code calls (see ``_compile_as_query``) — which is why the
        # key deliberately says nothing about the values the thunk closes over.
        code = getattr(t.fn, "__code__", None)
        if code is None:
            # Not a Python function (no code object to name the site with):
            # nothing stable to key on, so this goal simply is not cached.
            raise _Uncacheable()
        if t.var_objects:
            # A thunk that takes LOGIC variables is refused outright, the way
            # a ``Lambda`` node is below and for the same reason: this key and
            # the remap have to agree about which Vars are rebindable, and
            # ``_collect_vars`` does not reach a thunk's ``var_objects`` (it
            # has no PyThunk branch, and PyThunk is not a dataclass, so its
            # generic tail returns nothing).  Keying them as ``('var', i)``
            # slots would promise a remap ``_compile_as_query`` cannot perform
            # and the count guard cannot detect; keying them by arity alone
            # would go the other way and CONFLATE goals that lower to
            # different code (``f(X, X)`` and ``f(X, Y)`` are one arity but
            # two programs).  So: no cache.
            #
            # This DOES cost something, and the earlier note here that "the
            # goal-position surface cannot build a working one" was wrong: a
            # ``++`` (or an f-string) over a variable the same seam binds —
            # ``if --(decide(++p, verdict(S, IDS)), N is ++len(IDS)):`` — is
            # exactly such a thunk, it runs correctly, and it is refused the
            # cache, so it recompiles once per execution (measured
            # 2026-09-08: 2000 executions of that loop take 1.6s against
            # 0.16s for the same loop without the var-taking thunk).  The
            # refusal is the single line to lift once ``_collect_vars``
            # descends into ``var_objects`` and the key gives them ``('var',
            # i)`` slots — see
            # ``todo/goal-position-seam-thunk-var-objects-cache-2026-09-08.md``.
            raise _Uncacheable()
        if thunks is not None:
            thunks.append(t)
        return ("thunk", code,
                _structural_key(t._position, var_index, thunks))
    if isinstance(t, (list, tuple)):
        is_cell, functor = compound_cell_shape(t)
        if is_cell:
            return ("cell", functor,
                    tuple(_structural_key(x, var_index, thunks) for x in t[1:]))
        return ("seq", type(t),
                tuple(_structural_key(x, var_index, thunks) for x in t))
    if isinstance(t, _GoalNode) and _is_dataclass(t):
        # A goal NODE — what the rewriter hands ``solve()`` for a
        # goal-position ``--`` seam, rebuilt from scratch on every execution
        # (Task 7).  It is a dataclass, so its shape is its fields; keyed
        # field-by-field it is exactly as value-sensitive as a cell.
        # A ``Lambda`` is refused: its body's variables are deliberately NOT
        # collected by ``_collect_vars``, so a cache hit could not rebind
        # them and the cached code would keep the FIRST execution's Vars.
        if isinstance(t, _Lambda):
            raise _Uncacheable()
        return ("node", type(t),
                tuple((f.name, _structural_key(getattr(t, f.name),
                                               var_index, thunks))
                      for f in _dc_fields(t)))
    try:
        hash(t)
    except TypeError as e:
        raise _Uncacheable() from e
    return ("lit", type(t), t)


def _code_names(code) -> set:
    """Every global name *code* reads, its nested code objects included.

    ``co_names`` is per code object, and a compiled query's body can live in a
    nested one (the step generator), so a flat ``co_names`` check would call a
    perfectly good ``_pyt_<id>`` reference missing.
    """
    names = set(code.co_names)
    for const in code.co_consts:
        if isinstance(const, type(code)):
            names |= _code_names(const)
    return names


def _thunk_names_not_called(code, names) -> list:
    """The recorded ``_pyt_<id>`` names *code* never reads — empty is correct."""
    called = _code_names(code)
    return [n for n in names if n not in called]


def _goal_cache_key(goal: Any, module: Module, thunks: list | None = None):
    """Structural, value-sensitive cache key for a top-level query goal.

    Returns ``None`` (caching disabled for this goal) when the goal is neither a
    predicate term, a CELL, nor a goal NODE, or when it contains an
    unhashable ground leaf.

    Cells were previously in the "neither" bucket and so were uncached
    outright; they are hashable tuples, and ``_structural_key`` gives them their own ``('cell', ...)``
    tag, so a cell goal caches like any other predicate call (P3-3 Task 5).

    Goal NODES (``Call``/``Unify``/``And``/``TupleLiteral``, …) were the next
    occupants of that bucket, and they are the shape a goal-position ``--``
    seam hands ``solve()`` — rebuilt on every execution, so an uncached node
    meant one compile per loop iteration (Task 7).  ``_structural_key`` keys
    them field-by-field, which is what makes two executions of the same
    ``if --goal:`` one compiled query.

    *thunks*, when given, is filled with the ``PyThunk`` leaves in the order
    ``_structural_key`` visits them — the order ``_compile_as_query`` needs to
    rebind their per-execution closures on a cache hit.  Passing the SAME
    traversal is the point: a second, separately-written walk could drift out
    of step with the key's and silently rebind the wrong thunk.
    """
    if not (isinstance(goal, _GoalNode)
            or compound_cell_shape(goal)[0]):
        return None
    try:
        return (_structural_key(goal, {}, thunks), id(module))
    except _Uncacheable:
        return None




def _templatize_query_goal(goal: Any, db=None):
    """Parameterize the fully-ground top-level arguments of a predicate-call goal.

    Returns ``(template_goal, [(param_var, value), ...])``. Each direct argument
    of a single predicate-call goal (a CELL) that is
    fully ground is replaced with a fresh unbound Var; the var is bound to that
    value at run time (see ``solve``). The compiled query therefore contains no
    baked-in argument literals and is reused across calls that differ only in
    their ground arguments — instead of recompiling once per distinct value.

    Composite/control/arithmetic goals are returned unchanged (``params`` empty);
    they keep the value-keyed cache as a correct fallback.

    *db* is the querying module's database, passed to the predicate-binding
    resolver as the ruling-Q0 hint so a LOCAL handle resolves even when its
    module has been popped from ``sys.modules``.
    """
    from clausal.logic.predicate import predicate_binding_name

    def _ground_value(val):
        """Return the ground value to parameterize, or None to leave it.

        Only plain scalar literals and predicate bindings (lowered to the PLAIN
        atom of the predicate's name) are parameterized: they unify directly
        with a head literal regardless of mode.  Structural args
        (list/dict/compound) are *not* parameterized because the literal-baking
        path rewrites them (e.g. a list literal becomes cons cells) — a raw value
        bound to a Var would not match the rewritten head pattern.  Those keep the
        value-keyed cache fallback.

        A predicate binding is a ``PredicateMeta`` class of any arity today,
        its mangled handle post-flip -- see the first arm below.
        """
        dv = deref(val)
        if is_var(dv):
            return None
        # A predicate's self-denoting atom stays PLAIN in BOTH eras (operator
        # ruling 2026-09-24).  One arm for both shapes, ahead of the scalar
        # arm: post-flip the binding is a mangled ``str`` the scalar arm would
        # pass through VERBATIM, and today a zero-field CLASS used to be bound
        # as the class object itself -- which unifies with neither the plain
        # atom a ``.clausal`` source fact ``q(z)`` stores nor anything else a
        # query can write, and disagreed with ``term_to_ast_expr``'s nested
        # lowering (``__name__``).  An arity>=1 class used to fall to the
        # baking path, which already produced the plain name; parameterizing
        # it changes nothing but cache reuse.  ``predicate_binding_name`` is
        # gated on ``is_declared_predicate_name``, not ``is_mangled``: a
        # ``-hide`` DATA atom is mangled too, answers None, and keeps its
        # spelling (it falls through to the scalar arm) -- including one whose
        # owner module cannot be resolved, see ``term_to_ast_expr``.  One
        # resolver call, with the Q0 ``db`` hint.
        #
        # Ruling S, extended 2026-09-24: goal-argument use must qualify.  This
        # holds on the query-parameter path too, so a predicate binding passed
        # as a GOAL argument (``run(other_mod.z)`` with ``run(G) <- call(G)``)
        # becomes the plain atom ``z`` and is resolved in the CALLING module;
        # to reach another module's predicate, write it qualified
        # (``other_mod:z``).  Before this arm, a zero-arity class (and a
        # handle) reached ``other_mod``'s ``z``; pinned by
        # ``test_goal_argument_must_be_qualified_to_reach_another_module``.
        name = predicate_binding_name(dv, db=db)
        if name is not None:
            # The name THIS module binds the predicate under, when that is not
            # the owner's: an ``alias(p, q)`` import is ``q`` here, and ``p``
            # may be a DIFFERENT local predicate (roborev, 2026-09-25; Scryer
            # passes ``q`` and resolves it through the import).
            if db is not None:
                from clausal.logic.predicate import localize_goal  # noqa: PLC0415
                local = localize_goal(db, dv)
                if local is not dv and type(getattr(local, "name", None)) is str:
                    name = local.name
            return _mint_atom(name)
        if type(dv) in (int, float, complex, bool, str, bytes) or dv is None:
            return dv
        # A Python datetime is NOT parameterized. It was (ab0dabcd, 2026-09-02,
        # before the ruling that a date is the TERM ('date', Y, M, D)): the
        # object was bound by reference and never lowered, so once date/3
        # yielded the term a bare Python date unified with nothing and the
        # goal quietly answered NOTHING -- measured 2026-09-16 by
        # harness-date-migration. Left structural, it lowers through
        # term_to_ast_expr and meets the same refusal a nested one does, which
        # names the term to write.
        return None


    # A CELL goal parameterizes (P3-3 Task 5): the
    # goal's own arguments are slots 1.. and slot 0 is the functor, which is
    # never a parameter.  Without this branch every distinct ground argument
    # compiled its own query — a cell goal is a predicate call, and it gets the
    # same value-independent compiled query any predicate call gets.
    is_cell_goal, cell_f = compound_cell_shape(goal)
    if is_cell_goal and (
        # ARITY-MATCHED to ``_term_to_goal``'s own guard (P3-3 Task 5 fix
        # round 1, F5): only ``:``/2 is the qualified form, so
        # ``(":", A, B, C)`` is an ordinary ``:``/3 call and templatizes like
        # any other. The two guards disagreeing meant one path treated it as
        # special and the other as ordinary.
        (cell_f == QUALIFIED_GOAL_FUNCTOR and len(goal) == 3)
        or cell_f in CELL_GOAL_CONTROL_FUNCTORS
    ):
        # Neither of these two is an ordinary predicate call, so neither has
        # top-level arguments to parameterize.  A control construct is refused
        # by ``_term_to_goal`` a few lines later, and leaving it alone is what
        # makes the refusal quote the goal the caller wrote rather than a
        # template with fresh Vars in it.  A ``:``/2 goal is already GONE by
        # the time a query reaches here — ``_compile_as_query`` strips the
        # qualification before calling this function (P3-3 Task 6), and the
        # inner goal it hands over templatizes on the branch below like any
        # other cell.  What remains here is the direct caller, for whom
        # "M:G has no arguments of its own" is simply true.
        return goal, []
    if is_cell_goal:
        params = []
        new_args = []
        for a in goal[1:]:
            gv = _ground_value(a)
            if gv is None:
                new_args.append(a)
            else:
                pv = Var()
                params.append((pv, gv))
                new_args.append(pv)
        if not params:
            return goal, []
        return (goal[0],) + tuple(new_args), params

    return goal, []


_KNOWN_LEAF_TYPES = (int, float, complex, bool, str, bytes, type(None))


def _is_opaque_value(v: Any) -> bool:
    """True for a Python object the query compiler has no lowering for and
    that is no goal, predicate or term either: a plain instance of a class
    outside Clausal and the date module, not callable.  Such a value can only
    be passed through by reference.

    A NUMBER with no literal lowering -- a ``Decimal``, a ``Fraction`` or a
    ``Quantity`` -- is passed the same way.  Each is a number (rdiv/decimal
    ruling, 2026-09-17; a quantity is a number with units), immutable, and
    unifies by value, but ``term_to_ast_expr`` has no literal lowering for it
    (``ast.Constant`` cannot hold one), so ``solve(("p", Decimal("7.5"),
    X))`` raised ``NotImplementedError: unsupported term type Decimal``
    instead of answering.  A ``datetime`` stays refused: the ruling of
    2026-09-15 makes a date the TERM ``('date', Y, M, D)``, and the refusal
    names it.  So is a Module DESIGNATOR inside a goal term -- the M of a
    nested ``(":", M, G)`` -- which call/1 resolves at run time."""
    if isinstance(v, (Decimal, Fraction, Quantity, Module)):
        return True
    if isinstance(v, Var) or type(v) in _KNOWN_LEAF_TYPES:
        return False
    if isinstance(v, (list, tuple, dict, set, frozenset, type,
                      _types.ModuleType)):
        return False
    if callable(v) or _is_dataclass(v):
        return False
    if hasattr(v, "_get_dispatch") or hasattr(v, "__unify__"):
        return False
    module_name = getattr(type(v), "__module__", "") or ""
    return module_name.split(".")[0] not in ("clausal", "datetime")


#: A plain Python FUNCTION value -- a simple-mode goal function
#: ``fn(*args, trail, k)`` a caller hands in as a meta-argument, say.  It is a
#: goal OBJECT (``call/N`` and ``call_goal`` run one), but the query compiler
#: has no literal lowering for it: ``solve(("c1", 2, fn, OUT), m)`` raised
#: ``NotImplementedError: term_to_ast_expr: unsupported term type function``
#: while ``call("c1", 2, fn, OUT, module=m)`` answered.  As an ARGUMENT it
#: crosses by reference, as an opaque object does; never in a cell's functor
#: slot, which names the call itself.
_PASSABLE_CALLABLE_TYPES = (_types.FunctionType, _types.BuiltinFunctionType,
                            _types.MethodType, _functools.partial)


def _parameterize_opaque(goal: Any, params: list) -> Any:
    """*goal* with every opaque leaf (``_is_opaque_value``) inside a cell,
    conjunction tuple or list replaced by a fresh Var; ``(Var, value)`` is
    appended to *params*, which the caller binds before the search.  A
    Python function in an ARGUMENT position (``_PASSABLE_CALLABLE_TYPES``) is
    passed the same way; one in GOAL position -- the goal itself, or a
    conjunct of a top-level conjunction tuple -- is left alone, since it is
    the call.  Cells, tuples, lists and And/Or/Not nodes are walked: a value
    nested in a dict or a set is not reached (and keeps the compiler's
    refusal)."""
    from clausal.pythonic_ast import nodes as _nodes  # noqa: PLC0415

    def walk(t, goal_position=False):
        if isinstance(t, Var):
            return t
        if type(t) in (_nodes.And, _nodes.Or):
            left = walk(t.left, goal_position)
            right = walk(t.right, goal_position)
            if left is t.left and right is t.right:
                return t
            return type(t)(left=left, right=right)
        if type(t) is _nodes.Not:
            op = walk(t.operand, goal_position)
            return t if op is t.operand else _nodes.Not(operand=op)
        if type(t) is tuple:
            if t and type(t[0]) is str:        # a cell: slot 0 is its name
                new = (t[0],) + tuple(walk(e) for e in t[1:])
            else:                              # a conjunction or data tuple
                new = tuple(walk(e, goal_position) for e in t)
            return t if all(a is b for a, b in zip(new, t)) else new
        if type(t) is list:
            new = [walk(e) for e in t]
            return t if all(a is b for a, b in zip(new, t)) else new
        if _is_opaque_value(t) or (
                not goal_position and isinstance(t, _PASSABLE_CALLABLE_TYPES)
                and not hasattr(t, "_get_dispatch")):
            pv = Var()
            params.append((pv, t))
            return pv
        return t
    return walk(goal, True)


def _special_form_cell_as_call(goal: Any) -> Any:
    """A special-form CELL whose goal arguments are themselves cells --
    ``solve(("catch", ("throw", foo), E, True), m)`` -- as ``call/1`` of it.

    The compiler lowers a special form (``catch``, ``findall``, ``forall``,
    ``once``, ...) with its goal arguments as raw terms and reads them as
    goal NODES, so a cell there reached ``terms_to_goalop`` and raised
    ``NotImplementedError: goal shape not yet supported (tuple)``.  call/1
    runs exactly such a term (``call_body.special_form_dispatch``).

    A VARIABLE in a goal argument goes the same way, where the compiler
    refuses a bare goal variable (``BareGoalVariableError``): a user's
    unbound one is ``call(V)`` by ISO's body conversion, so
    ``solve(("findall", X, G, L), m)`` with G unbound is
    ``instantiation_error`` (Scryer); and a parameter Var
    ``_templatize_query_goal`` put in place of a ground atom
    (``solve(("once", "fail"), m)``) is bound to that atom before the
    search, which call/1 then runs."""
    is_cell, functor = compound_cell_shape(goal)
    if not is_cell:
        return goal
    from clausal.logic.builtins.call_body import SPECIAL_FORMS  # noqa: PLC0415
    spec = SPECIAL_FORMS.get((functor, len(goal) - 1))
    if spec is None:
        return goal
    for kind, arg in zip(spec, goal[1:]):
        if kind != "G":
            continue
        val = deref(arg)
        if type(val) is tuple or is_var(val):
            return ("call", goal)
    return goal


def _compile_as_query(goal: Any, module: Module) -> Any:
    """Compile goal as a zero-arity query predicate and return its dispatch fn.

    Vars embedded in the goal are injected into the compiled function's globals
    so that the compiled code references the *user's* Var objects rather than
    allocating fresh ones.  This means the trail binds the user's Vars directly,
    making deref(user_var) work during and after each solution.

    when module.module_dict is available, it is merged into the compiled
    function's globals so that predicate names resolve from the module namespace
    (Phase 5: cross-predicate resolution without _db string lookup).

    A module-QUALIFIED cell goal ``(":", M, G)`` switches *module* to *M* here
    (P3-3 Task 6) before anything else looks at either — see
    ``_strip_module_qualification`` for why this is the right point.
    """
    goal, module = _strip_module_qualification(goal, module)

    # Parameterize ground top-level args so distinct values reuse one compiled
    # query.  The returned param_pairs are bound to their values (on the trail)
    # by the caller before driving the search.
    goal, param_pairs = _templatize_query_goal(goal, getattr(module, "db", None))
    # An OPAQUE Python object in the goal (a socket, a lock, ``object()``) has
    # no literal lowering; it crosses by reference, as a parameter bound
    # before the search (triage C13; python_integration.md: "Any Python
    # object works as a ground term").
    goal = _parameterize_opaque(goal, param_pairs)

    # Compute cache key before AST conversion (needs original term).  After
    # templatizing, ground args are Vars, so the key is value-independent.
    # ``goal_thunks`` comes back filled by the SAME walk, in the order the
    # compiled code's ``_pyt_<id>`` globals were named (Task 7).
    goal_thunks: list = []
    cache_key = _goal_cache_key(goal, module, goal_thunks)

    goal = _special_form_cell_as_call(goal)
    goal = _term_to_goal(goal, getattr(module, "db", None))
    from clausal.logic.compiler import compile_predicate_trampoline
    from clausal.logic.compiler.goal_trampoline import compile_body_trampoline
    from clausal.logic.compiler._vars import _collect_vars, _var_python_name
    from clausal.logic.compiler.globals_env import _collect_types_from_term

    # include_bound: a Var already bound to a value with no literal lowering
    # (e.g. a datetime.date from an earlier goal, common in the test harness's
    # diagnostic re-runs) must be referenceable BY NAME from the compiled code
    # — term_to_ast_expr falls back to that reference instead of raising.
    vars_in_goal = _collect_vars(goal, include_bound=True)

    cached = _query_cache.get(cache_key) if cache_key is not None else None
    if cached is not None and cached[4]() is not module:
        # Compiled for a DEAD module whose id this one reuses (see the
        # insert site): its code resolved names in the dead module's
        # namespace, so it must not run here.
        cached = None
    if cached is not None:
        cached_fn, cached_code, cached_var_names, cached_thunk_names, _ = cached
        # The two name lists ARE the parameter list of a cached query: the
        # cached code says ``_v<id>`` / ``_pyt_<id>`` by the name it was
        # compiled with, and every one of them has to be rebound to this
        # execution's object.  A count mismatch means the key has conflated
        # two goals the remap cannot bridge (a bound Var wrapper the key
        # deref'd away but ``_collect_vars`` still collected, say) — so
        # recompile rather than run the cached code with a stale object
        # silently left in place.
        if (len(cached_var_names) != len(vars_in_goal)
                or len(cached_thunk_names) != len(goal_thunks)):
            cached = None
    if cached is not None:
        # Map new Var objects to the names the cached code expects
        new_globals = dict(cached_fn.__globals__)
        for old_name, new_var in zip(cached_var_names, vars_in_goal):
            new_globals[old_name] = new_var
        # Same for the ``++`` escapes: the compiled code calls the thunk
        # through a global, so handing it THIS execution's closure is what
        # makes a cached query still read the caller's current Python values.
        # (This is the thunk's parameter binding — a Var could not carry it:
        # unifying a Var with the PyThunk OBJECT would put the thunk into the
        # term instead of its value.)
        for old_name, new_thunk in zip(cached_thunk_names, goal_thunks):
            new_globals[old_name] = new_thunk.fn
        fn = _types.FunctionType(cached_code, new_globals, cached_fn.__name__)
        return fn, param_pairs

    db = module.db

    # Collect all Var objects reachable from goal.
    pre_var_context = {v._id: _var_python_name(v) for v in vars_in_goal}
    extra_globals: dict = {}
    # Start with module globals so predicate names resolve from the namespace.
    if module.module_dict is not None:
        extra_globals.update(module.module_dict)
    # Var globals take precedence over module globals.
    extra_globals.update({_var_python_name(v): v for v in vars_in_goal})
    # Also collect user-defined dataclass types that appear in the goal args
    # so that term_to_ast_expr can reference them in the compiled code.
    extra_globals.update(_collect_types_from_term(goal))

    def _query_body_compiler(clause: Clause, var_context: dict,
                             ctx_template=None) -> list:
        # Pre-populate var_context so _preallocate_body_vars skips user Vars
        # and term_to_ast_expr references them by name (→ global) rather than
        # emitting a walrus that creates a new Var().
        var_context.update(pre_var_context)
        # The goal's arguments are live TERM OBJECTS handed in by the caller,
        # but this template's globals are the CALLEE's module namespace.  An
        # atom in those terms (a DictTerm key/value, a list element, …) is a
        # global-by-spelling interned str (§1b/R2): it lowers to a plain
        # ``ast.Constant`` and is never re-resolved by name in the callee's
        # namespace, so it cannot land on a same-named predicate there — the
        # by-identity lowering this comment used to describe is deleted.
        # With the compile's own ctx (``accepts_ctx_template`` below): a call
        # site the target resolution routed through a ``$disp_`` entry -- the
        # name+arity ruling's other-arity dispatcher for a name bound to an
        # imported predicate at another arity, or a locked predicate -- is
        # emitted through it, exactly as in a compiled clause.  Without it
        # the query emitted ``$dispatch_at(name, N)`` on the BINDING, which
        # resolves another arity in the binding's owner, not in this module.
        return compile_body_trampoline(clause.body, db, var_context, "trail",
                                       ctx=ctx_template)

    _query_body_compiler.accepts_ctx_template = True

    # The dummy head is the ATOM ``_query``: an arity-0 head is its name
    # (``foo()`` is not a term).
    clause = Clause(head="_query", body=[goal])
    dispatch_fn = compile_predicate_trampoline(
        "_query", 0, [clause], db,
        body_compiler=_query_body_compiler,
        globals_=extra_globals,
    )

    if cache_key is not None:
        cached_var_names = [_var_python_name(v) for v in vars_in_goal]
        # Bound the cache: keying on ground *values* (for correctness) means a
        # workload that queries one module with many distinct argument values
        # would otherwise grow this dict without limit.  Evict in FIFO order
        # (dicts preserve insertion order) once the cap is reached.
        if len(_query_cache) >= _QUERY_CACHE_MAX:
            _query_cache.pop(next(iter(_query_cache)), None)
        # ``id(t)`` is the name ``term_to_ast_expr`` lowered this very thunk
        # under, and the ids cannot collide: every thunk in *goal_thunks* is
        # alive right now, and the surface never puts one thunk object in two
        # places — the rewriter builds a fresh ``PyThunk`` per ``++`` site per
        # execution, so two slots are always two objects.
        cached_thunk_names = [f"_pyt_{id(t)}" for t in goal_thunks]
        # And the compiled code must actually CALL each of them.  The key's
        # walk and ``term_to_ast_expr``'s walk are two separate traversals of
        # the same goal; if they ever disagree about which thunks are in it,
        # the hit path would rebind a global the code never reads and quietly
        # serve the FIRST execution's ``++`` values.  Make that loud here,
        # where the two lists are side by side, instead of at the answer.
        assert not _thunk_names_not_called(
            dispatch_fn.__code__, cached_thunk_names), (
            "thunk names recorded for the cache but never called by the "
            "compiled query: " + repr(_thunk_names_not_called(
                dispatch_fn.__code__, cached_thunk_names)))
        # The entry records its MODULE by weak reference, and a hit is taken
        # only when it is still that module: the key is ``id(module)``, and a
        # module the caller wraps afresh on every call (``_coerce_module``
        # over a plain Python module, a transient ``Module``) dies with this
        # query and frees its id for the next one -- whose same-shaped goal
        # used to HIT this entry and run code resolved against the dead
        # module's namespace: a silent wrong answer.  A weak reference, not a
        # strong one, so the cache does not keep every transient wrap (and
        # its database) alive until eviction.
        _query_cache[cache_key] = (dispatch_fn, dispatch_fn.__code__,
                                   cached_var_names, cached_thunk_names,
                                   weakref.ref(module))

    return dispatch_fn, param_pairs


# ── Public API ─────────────────────────────────────────────────────────────────


def _coerce_module(module) -> Module:
    """Accept a clausal Module or a Python module imported from a .clausal file.

    When *module* is a regular Python module (e.g. ``import hello_world``), the
    logic Module stored during import-hook compilation is returned via its
    ``__clausal_module__`` attribute.
    """
    if isinstance(module, Module):
        return module
    cm = getattr(module, '__clausal_module__', None)
    if cm is not None:
        return cm
    # Last resort: wrap a bare dict / module namespace as a Module.
    if hasattr(module, '__dict__') and hasattr(module, '__name__'):
        return Module(module.__name__, module_dict=vars(module))
    raise TypeError(
        f"Expected a clausal Module or an imported Clausal source module, got {type(module).__name__}"
    )


def resolve_module(designator: Any, calling_module: Any = None,
                   context: str = "") -> Module:
    """Resolve a module DESIGNATOR to the :class:`Module` whose database answers.

    P3-3 Task 6 (R10).  This is the one place that answers "which module does
    this name mean?" for the module-qualified goal ``(":", M, G)`` and for
    ``solve``'s ``module=`` argument, so the two cannot drift apart on what a
    designator is.

    The chain, in order:

      - a ``str`` is a DOTTED PYTHON MODULE NAME, looked up in ``sys.modules``
        -- which is exactly where ``clausal/import_hook.py`` registers every
        ``.clausal`` module it loads (``_load_module`` and the finder both
        write ``sys.modules[fullname]``), so the spelling a designator uses is
        the spelling an ``import`` would use.  The result is then coerced like
        any module object.
      - everything else goes straight to :func:`_coerce_module`, which is the
        pre-existing chain and stays the only copy of it: a ``Module`` is
        itself, an imported ``.clausal`` module yields its
        ``__clausal_module__``, and any other module namespace is wrapped.

    LOOKUP ONLY.  Resolution never imports -- no ``importlib.import_module``,
    no side effect on ``sys.modules``.  A module that is merely *importable*
    does not resolve, because a goal is not an import statement and running
    one must not execute a module body.

    Anything the chain refuses -- an ``int``, a cell, an unbound ``Var``, a
    ``str`` that misses in ``sys.modules`` -- raises
    ``LogicException(existence_error(module, <designator repr'd>))``.  The
    culprit is the REPR rather than the designator itself so that the error
    term is always a ground atom: an unbound-``Var`` designator must not end
    up as a culprit that unifies with whatever pattern a ``catch/3`` offers.

    *calling_module* is the module the designator was written in, when the
    caller knows it.  It does not participate in resolution (a designator is
    absolute, per the R10 chain above) -- it names the asking module in the
    diagnostic, and it is the hook a future alias/short-name chain would use.
    """
    # The culprit is the DEREFERENCED designator, not the term the caller
    # handed over: ``M`` in a ``(":", M, G)`` cell is routinely a Var bound to
    # the real designator, and reporting ``AttVar(_4=7)`` names the plumbing
    # rather than the fault (P3-3 Task 6 fix round 1, F6).  It stays the
    # designator even when the ``sys.modules`` hit below replaces *target*:
    # a str that resolved to a module object and then failed to coerce is
    # still a fault about the name the caller wrote.
    culprit = deref(designator)
    target = culprit
    # Spec §6.4: a designator WRITTEN in source arrives as an atom, so it is
    # read by spelling here.  The Python-API ``str`` path below is untouched
    # (``solve(goal, module="pkg.mod")`` passes a Python argument, not a
    # term), and under today's representation a str atom's spelling is itself.
    if _term_is_atom(target):
        target = _spelling(target)
    named = isinstance(target, str)
    if named:
        found = sys.modules.get(target)
        if found is None:
            _no_such_module(culprit, calling_module, context)
        target = found
    if _sandbox_state.ACTIVE and (named
                                  or isinstance(target, _types.ModuleType)):
        # The sandbox: a module named by a TERM -- by its name, or as an
        # object a term came to hold -- is read only when it is a Clausal
        # or an allowed adapter module; coercing any other would read its
        # attributes (and run its ``__getattr__``).
        from clausal.sandbox import refuse_unwalkable  # noqa: PLC0415
        refuse_unwalkable(target, context)
    try:
        return _coerce_module(target)
    except TypeError as exc:
        _no_such_module(culprit, calling_module, context, cause=exc)


def _no_such_module(designator, calling_module, context: str, cause=None):
    """Raise ``existence_error(module, repr(designator))``.  Never returns."""
    from clausal.logic.exceptions import (  # noqa: PLC0415 -- clausal.logic.
        LogicException, existence_error,    # exceptions imports clausal.terms,
    )                                       # which imports this module's kin
    asker = ""
    if calling_module is not None:
        asker = f" (asked from {getattr(calling_module, 'name', calling_module)!r})"
    prefix = f"{context}: " if context else ""
    exc = LogicException(existence_error(
        "module", repr(designator),
        f"{prefix}{designator!r} does not name a module{asker} — a module "
        f"designator is a dotted Python module name already present in "
        f"sys.modules (resolution is lookup-only and never imports), a "
        f"clausal Module, or an imported Clausal source module object",
    ))
    if cause is not None:
        raise exc from cause
    raise exc


def declared_atoms(module_or_package: Any) -> frozenset:
    """The atom names DECLARED by a module's (or a package's) own files.

    An atom is declared by a file when the file names it in its own
    ``-module(Name, [...])`` export list or its ``-private([...])`` list; the
    compiler records those names per file under
    ``cells.DECLARED_ATOMS_KEY`` (``__clausal_declared_atoms__``).  This is
    the union of that record over:

      - the given module, and
      - when it is a package (it has ``__path__``), every submodule already
        in ``sys.modules`` whose dotted name is under the package's and whose
        ``__file__`` lies under one of the package's ``__path__``
        directories.

    What it deliberately does NOT read:

      - the module NAMESPACE.  An ``-import_from``ed atom is bound there but
        is not in the importing file's record, and the namespace also holds
        predicates, builtins and whatever other modules were loaded first,
        so its contents depend on import order.  The per-file record does
        not.  (A file that names an imported atom in its own ``-module``
        list re-exports it, and that IS a declaration by that file.)
      - the process-wide atom pool, which holds every spelling any loaded
        module interned.

    *module_or_package* is an imported ``.clausal`` module object, a
    :class:`~clausal.logic.database.Module`, or a dotted module name
    (``str``) resolved the way ``solve``'s ``module=`` argument resolves
    one: looked up in ``sys.modules`` and never imported, so a name that is
    not loaded raises ``LogicException(existence_error(module, ...))``.

    LOADED SUBMODULES ONLY.  A package's submodules count once they are
    imported; this never imports one.  Scanning the package directory and
    importing every ``.clausal`` file found there would execute module
    bodies (and load files the package may never import) as a side effect
    of asking a question -- the same reason ``module=`` resolution is
    lookup-only.  Import the submodules you want counted first.

    NOT THE PACKAGE ROOT'S ATTRIBUTES.  For a package the answer is the
    package's atom VOCABULARY -- the union over its own files -- not the set
    of names bound on the package root: an atom declared only in a submodule
    (say a ``-private`` one) is in ``declared_atoms(pkg)`` while
    ``getattr(pkg, name)`` can raise AttributeError.  To learn the root's
    attribute surface, read the root module's own names (``vars(pkg)``).
    """
    names: set[str] = set()
    for ns in _own_file_namespaces(module_or_package, "declared_atoms"):
        names.update(ns.get(DECLARED_ATOMS_KEY) or ())
    return frozenset(names)


def _own_file_namespaces(module_or_package: Any, context: str) -> list:
    """The namespaces of a module's (or a package's) own files, in a fixed
    order: the module itself first, then -- for a package -- each LOADED
    submodule whose dotted name is under the package's and whose ``__file__``
    lies under one of its ``__path__`` directories, sorted by dotted name.

    The one copy of the argument handling and package scoping that
    :func:`declared_atoms` and :func:`imported_atoms` share.  *context* names
    the public function in the diagnostics.
    """
    target = module_or_package
    if isinstance(target, str):
        found = sys.modules.get(target)
        if found is None:
            _no_such_module(target, None, context)
        target = found
    if isinstance(target, Module):
        ns = target.module_dict or {}
    elif isinstance(target, _types.ModuleType):
        ns = vars(target)
    else:
        raise TypeError(
            f"{context}() expects a module object, a clausal Module or a "
            f"dotted module name, got {type(target).__name__}")

    found_ns = [ns]
    pkg_name = ns.get("__name__")
    pkg_path = ns.get("__path__")
    if pkg_name and pkg_path is not None:
        import os  # noqa: PLC0415
        roots = [os.path.join(os.path.realpath(p), "") for p in pkg_path]
        prefix = pkg_name + "."
        for sub_name, sub in sorted(list(sys.modules.items()),
                                    key=lambda kv: kv[0]):
            if not sub_name.startswith(prefix) or sub is None:
                continue
            sub_file = getattr(sub, "__file__", None)
            if not sub_file:
                continue
            real = os.path.realpath(sub_file)
            if not any(real.startswith(r) for r in roots):
                continue
            found_ns.append(getattr(sub, "__dict__", {}))
    return found_ns


def imported_atoms(module_or_package: Any) -> dict:
    """The atoms a module's (or a package's) own files bring in via
    ``-import_from`` without declaring them, as ``{atom: exporter}``.

    The companion of :func:`declared_atoms`, with the same argument handling,
    errors and package scoping (the module's own file and, for a package,
    its LOADED submodules -- never imported by asking).  The two answers are
    DISJOINT, so ``declared_atoms(m) | imported_atoms(m).keys()`` is every
    atom those files can name.  The motivating shape is a package
    ``__init__.seam`` with no ``-module`` list whose atoms all arrive by
    ``-import_from``.

    An entry of an ``-import_from(exporter, [...])`` directive counts when:

      - the EXPORTER's own file declares the name as an atom, in its
        ``-module``/``-private`` list.  One level, exactly the record the
        import edge itself reads (``compiler_v2._imported_reference``): a
        module that merely imports an atom and passes it on is not its
        exporter, and an imported PREDICATE is not an atom (a name that is
        both, declared as an atom AND given clauses by its owner, counts: the
        import edge answers it with the atom).  For a single-file exporter
        this is ``declared_atoms(exporter)``; for a PACKAGE exporter it is
        its ``__init__``'s declarations only, NOT the package-scoped
        ``declared_atoms``, so the answer does not depend on which of the
        exporter's submodules happen to be loaded;
      - no file in scope declares it (a file that re-declares an imported
        atom in its own ``-module``/``-private`` list owns it:
        :func:`declared_atoms` reports it instead).

    A ``name/N`` entry (D20) names a PREDICATE at an arity, never an atom,
    and is not counted.

    The key is the ATOM, i.e. the exporter's spelling: ``alias(orig, local)``
    reports ``orig``, which is what the local name is bound to.  The value is
    the exporter's dotted module name as ``sys.modules`` has it (the resolved
    module's ``__name__``, which can differ from the spelling in the
    directive when the compiler maps it to ``clausal.modules.*``), which
    :func:`declared_atoms` accepts.

    CLASHES -- the same atom imported from two exporters that both declare
    it.  The atom is the same either way (atoms are global by spelling);
    only the attribution differs, and it is deterministic:

      - within one file, the LATER ``-import_from`` directive (in source
        order) that names the atom wins, whatever local name it binds: an
        ``alias(x, y)`` entry names the atom ``x`` just as a plain ``x``
        does.  This is attribution by ATOM, not by binding -- after
        ``-import_from(m1, [x])`` and ``-import_from(m2, [alias(x, y)])``
        the local names ``x`` and ``y`` are bound by different directives,
        but they are the same atom, and it is credited to ``m2``;
      - across a package's files, the package's own ``__init__`` is asked
        first, then its loaded submodules in sorted dotted-name order, and
        the first file that imports the atom names its exporter.

    The result is a fresh ``dict`` with its keys in sorted order.  It reads
    the per-file record the compiler writes (``cells.IMPORT_FROM_KEY``), not
    the namespace's dotted ``"<exporter>.<name>"`` keys, which are an
    implementation detail of name resolution.
    """
    files = _own_file_namespaces(module_or_package, "imported_atoms")
    declared_here: set[str] = set()
    for ns in files:
        declared_here.update(ns.get(DECLARED_ATOMS_KEY) or ())
    owners: dict[str, frozenset] = {}
    found: dict[str, str] = {}
    for ns in files:
        per_file: dict[str, str] = {}
        for name, exporter, *selected in ns.get(IMPORT_FROM_KEY) or ():
            if selected and selected[0] is not None:
                # A ``name/N`` entry names a PREDICATE, never an atom (D20).
                continue
            if name in declared_here:
                continue
            if exporter not in owners:
                # The exporter's OWN FILE's record, exactly what the import
                # edge reads (``compiler_v2._imported_reference``) -- not the
                # package-scoped ``declared_atoms(exporter)``, which would
                # also credit a package exporter with atoms its loaded
                # submodules declare, and so depend on what is loaded.  An
                # exporter evicted from sys.modules since the import ran has
                # nobody left to ask, so it owns nothing (lookup-only: asking
                # never re-imports it).
                owner_mod = sys.modules.get(exporter)
                owners[exporter] = frozenset(
                    getattr(owner_mod, "__dict__", {}).get(DECLARED_ATOMS_KEY)
                    or ())
            if name in owners[exporter]:
                per_file[name] = exporter  # later directive naming it wins
        for name, exporter in per_file.items():
            found.setdefault(name, exporter)  # earlier file wins
    return dict(sorted(found.items()))


def module_signatures(module: Any) -> dict:
    """The predicates a module offers to ``-import_from``, as
    ``{name: frozenset(arities)}``.

    Valid for both kinds of module an ``-import_from`` can name:

      - a CLAUSAL module (``.clausal``/``.seam``/``.pl``): every predicate its
        own database is the home of -- clauses, ``-dynamic`` declarations,
        compiled dispatch -- plus a bare ``name/N`` entry of its ``-module``
        list.  A predicate it merely imports is not its own and is left out
        -- EXCEPT in a ``.seam`` with NO ``-module`` export list (a package
        ``__init__`` re-importing from its submodules, operator ruling M3):
        there each name it ``-import_from``s is offered, at the arities it
        was imported at, when it is an export of its source (recursively)
        by the one export rule the Python-bridge gate and the sandbox use
        (``clausal.python_bridges._exports``: lowercase, not
        underscore-led, no ``-import_module`` binding, no submodule).  A
        fielded DATA declaration (a constructor, not a predicate) is left
        out, and so is any name the module holds as a MODULE object.
        Compiler-internal ``$`` names are left out.
      - a PYTHON-BACKED module (``clausal.modules.*``, ``py.*`` and any Python
        module whose public attributes are predicate adapters, i.e. objects
        carrying ``_get_dispatch``): each public attribute that registers at
        least one arity.  An adapter keeping a non-empty ``_dispatch_fns``
        table (``ModulePredicate`` and its subclasses) answers from that
        table's keys; one that does not -- including a ``ModulePredicate``
        subclass that overrides ``_get_dispatch`` and leaves the table
        empty -- answers from the parameter list of the
        function its ``_get_dispatch()`` returns
        (``this_generator, _proceed, _fail, _catcher, *args, trail``).  An
        adapter whose dispatch takes ``*args`` has no discoverable arity: it
        is listed with an EMPTY frozenset, meaning "a predicate, arities
        unknown", never left out.  A unit or currency constant (an adapter
        with no registered arity) and a plain Python function (a term
        constructor such as ``py.datetime``'s ``date/3``) are not
        predicates and are left out.

    *module* is a module object, a :class:`~clausal.logic.database.Module`,
    or a name spelled as an ``-import_from`` spells it (``py.datetime``,
    ``date_time``, ``currency``, ``thailand``, ``pkg.mod``) and resolved the
    same way.  Unlike :func:`declared_atoms`, a name is IMPORTED when it is
    not loaded yet: the question is what an import of the module would
    bring, and answering it takes the module, exactly as the import does.
    A name that resolves to no module raises
    ``LogicException(existence_error(module, ...))``.

    The result is a fresh ``dict`` with its keys in sorted order.  A
    package is answered for its own ``__init__`` only (what an
    ``-import_from`` of the package reads), never its submodules.
    """
    target = module
    if isinstance(target, str):
        target = _import_for_signatures(target)
    if isinstance(target, Module):
        ns = target.module_dict or {}
        db = target.db
    elif isinstance(target, _types.ModuleType):
        ns = vars(target)
        from clausal.logic.predicate import namespace_db  # noqa: PLC0415
        db = namespace_db(ns)
    else:
        raise TypeError(
            f"module_signatures() expects a module object, a clausal Module "
            f"or a module name, got {type(target).__name__}")
    found: dict[str, set] = {}
    if db is not None:
        for name, arity in db.offered_keys():
            if type(name) is str and not name.startswith("$"):
                found.setdefault(name, set()).add(arity)
        for name, arities in _listless_reexports(ns, db).items():
            if name not in found and arities:
                found[name] = set(arities)
        # A name the module object holds as a MODULE (an -import_module
        # binding, or a submodule an import set) is no predicate it
        # offers, whatever its clauses say (operator ruling M3).
        for name in [n for n in found
                     if isinstance(ns.get(n), _types.ModuleType)]:
            del found[name]
    else:
        for name, value in list(ns.items()):
            if name.startswith("_") or isinstance(value, type):
                continue
            arities = _adapter_arities(value)
            if arities is not None:
                found[name] = arities
    return {name: frozenset(found[name]) for name in sorted(found)}


def _listless_reexports(ns: dict, db: Any) -> dict:
    """The predicates a listless package ``__init__.seam`` offers by
    re-import (operator rulings E1/M3): ``{name: arities}`` from the ONE
    export rule, :func:`clausal.python_bridges.listless_exports` (also
    ``_declared_exports``', the bridge gate's and the sandbox's), less a
    name that is now a submodule (``python_bridges._exports``), each
    checked against what the module BINDS: an imported Clausal predicate
    at the arities it was imported at, or an engine adapter at its
    registered arities.  An atom, a unit, a Python object or a module is
    never a predicate offered here."""
    path = ns.get("__file__")
    dotted = ns.get("__name__")
    if not (isinstance(path, str) and isinstance(dotted, str)):
        return {}
    from clausal.python_bridges import (  # noqa: PLC0415
        _exports, is_listless_package_init, listless_exports)
    if not is_listless_package_init(path):
        return {}
    allowed = _exports(dotted, path)
    from clausal.logic.predicate import _binding_owner_db  # noqa: PLC0415
    out: dict = {}
    for name, arity in listless_exports(path):
        if arity is None or name not in allowed:
            continue
        binding = ns.get(name)
        if binding is None or isinstance(binding, (type, _types.ModuleType)):
            continue
        if is_declared_predicate_name(binding, db=db):
            owner = _binding_owner_db(binding, db)
            if owner is None or owner is db:
                continue
            if not binding_grants_arity(binding, arity, db, name):
                continue
        else:
            have = _adapter_arities(binding)
            if not have or arity not in have:
                continue
        out.setdefault(name, set()).add(arity)
    return out


def _canonical_name(binding: Any) -> str:
    """The owner's own name of the predicate handle *binding*."""
    from clausal.logic.atoms import demangle  # noqa: PLC0415
    try:
        return demangle(binding)[1]
    except Exception:  # noqa: BLE001 -- not a mangled handle
        return binding if type(binding) is str else ""


def _adapter_arities(value: Any) -> "set | None":
    """The arities a Python predicate adapter registers: ``None`` when
    *value* is no predicate (no ``_get_dispatch``, or a ``_dispatch_fns``
    table with nothing in it); an empty set when it is one whose arities
    cannot be read off it."""
    get_dispatch = getattr(value, "_get_dispatch", None)
    if not callable(get_dispatch):
        return None
    table = getattr(value, "_dispatch_fns", None)
    if isinstance(table, dict):
        arities = {a for a in table if type(a) is int and a >= 0}
        if arities:
            return arities
        # An EMPTY table says "no predicate" only when the table is what
        # dispatch reads, i.e. the adapter keeps ModulePredicate's own
        # ``_get_dispatch`` (a unit or currency constant).  A subclass that
        # overrides ``_get_dispatch`` dispatches without the table, so it
        # is a predicate: read its arity off the function it returns.
        from clausal.modules.py import ModulePredicate  # noqa: PLC0415
        if (getattr(type(value), "_get_dispatch", None)
                is ModulePredicate._get_dispatch):
            return None
    import inspect  # noqa: PLC0415
    try:
        params = list(inspect.signature(get_dispatch()).parameters.values())
    except (TypeError, ValueError):
        return set()
    if any(p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD) for p in params):
        return set()
    positional = [p for p in params
                  if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    # this_generator, _proceed, _fail, _catcher ... trail
    arity = len(positional) - 5
    return {arity} if arity >= 0 else set()


#: The three existence questions, and which function answers each
#: (``getattr(mod, name, None)`` answers none of them on a ``.pl`` module,
#: where an unbound atom-shaped name reads as its atom; ruling 2026-10-01):
#:
#: - "is *name* a predicate I can call through *mod*"  -> :func:`has_predicate`
#: - "does *mod* itself define (or export) *name*"     -> :func:`defines_predicate`
#: - "is *name* a real attribute of *mod* (predicate or data)"
#:                                                     -> :func:`module_binds`


def _namespace_and_db(module: Any, caller: str):
    """``(namespace, db)`` for the argument forms :func:`module_signatures`
    takes (a name is imported if not loaded)."""
    target = module
    if isinstance(target, str):
        target = _import_for_signatures(target)
    if isinstance(target, Module):
        return target.module_dict or {}, target.db
    if isinstance(target, _types.ModuleType):
        from clausal.logic.predicate import namespace_db  # noqa: PLC0415
        ns = vars(target)
        return ns, namespace_db(ns)
    raise TypeError(
        f"{caller}() expects a module object, a clausal Module or a module "
        f"name, got {type(target).__name__}")


def has_predicate(module: Any, name: str, arity: "int | None" = None) -> bool:
    """Answers "is *name* a predicate I can call through *module*": True iff
    calling *name*/*arity* in *module* resolves to a predicate (any arity
    when *arity* is ``None``), whether *module* defines it or IMPORTS it --
    from a ``.pl`` or ``.clausal``/``.seam`` module (an ``-import_from`` /
    ``use_module`` row), or by a Python-level import binding a predicate
    handle or adapter in a facade ``__init__``.  False for a data atom and
    for a name only the ``.pl`` attribute fallback answers.

    This is the replacement for ``getattr(mod, name, None) is not None`` as
    a predicate probe.  Compare :func:`defines_predicate` ("does *module*
    itself define it"), which is False for a predicate a thin facade only
    imports, and :func:`module_binds` ("is it a real attribute"), which is
    True for a data atom too.  An adapter whose arity cannot be read answers
    True for any *arity*.  Argument forms as :func:`module_signatures`.
    """
    from clausal.logic.predicate import predicate_arities_for  # noqa: PLC0415
    ns, db = _namespace_and_db(module, "has_predicate")
    arities: set = set()
    unknown = False
    if db is not None:
        defined, _declared = db.arity_maps()
        arities |= defined.get(name, set())
        arities |= {a for (f, a) in getattr(db, "_adopted", ())
                    if f == name}
    missing = object()
    value = ns.get(name, missing) if ns is not None else missing
    if value is not missing:
        adapter = _adapter_arities(value)
        if adapter is not None:
            arities |= adapter
            unknown = not adapter
        else:
            try:
                arities |= predicate_arities_for(value)
            except Exception:  # pragma: no cover - a probe must not raise
                pass
    if unknown:
        return True
    if not arities:
        return False
    return arity is None or arity in arities


def defines_predicate(module: Any, name: str, arity: "int | None" = None) -> bool:
    """Answers "does *module* itself define (or export) *name*": True iff
    *module* offers the predicate *name*/*arity* -- it defines it, or
    imports it and re-exports it with a ``name/N`` export entry -- at any
    arity when *arity* is ``None``.  The population of
    :func:`module_signatures`, with its argument forms.

    NOT "can I call it through *module*": a thin facade that only imports a
    predicate does not define it -- ask :func:`has_predicate`.  For a
    Python-backed module whose adapter's arity cannot be read
    (``module_signatures`` lists it with an empty set), any *arity* is
    answered True.
    """
    arities = module_signatures(module).get(name)
    if arities is None:
        return False
    return arity is None or not arities or arity in arities


def module_binds(module: Any, name: str) -> bool:
    """Answers "is *name* a real attribute of *module* (predicate or data)":
    True iff *name* is a REAL attribute of *module*: present in its
    namespace (``__dict__``), which is where a definition, an import, a
    declaration and a native ``.pl`` auto-declaration all bind it.

    False for a name only the ``.pl`` attribute fallback answers (operator
    ruling 2026-10-01: ``getattr`` on a ``.pl`` module answers a name the
    module does not bind with the atom of that name), so
    ``module_binds(m, n)`` is what ``hasattr(m, n)`` meant before that
    ruling.  True for a data atom as well as a predicate: to ask for a
    predicate, use :func:`has_predicate`.  *module* is a module object, a :class:`Module` (its
    ``module_dict``), or a dotted name looked up in ``sys.modules`` (lookup
    only: a module that is not loaded binds nothing).
    """
    if isinstance(module, str):
        module = sys.modules.get(module)
        if module is None:
            return False
    if isinstance(module, Module):
        ns = module.module_dict
    elif isinstance(module, _types.ModuleType):
        ns = vars(module)
    else:
        raise TypeError(
            f"module_binds() expects a module object, a clausal Module or a "
            f"module name, got {type(module).__name__}")
    return ns is not None and name in ns


def _import_for_signatures(name: str):
    """Resolve *name* as ``-import_from`` resolves a module path
    (``compiler_v2._resolve_module``: the ``clausal.modules`` spelling
    first, then the name itself), importing it if needed.  Only a module
    that is itself ABSENT falls through to the next candidate or to
    ``existence_error(module, Name)``: a module that exists but fails to
    import (a missing dependency, an error in its body) re-raises."""
    import importlib  # noqa: PLC0415
    from clausal.logic.compiler_v2 import (  # noqa: PLC0415
        _MODULE_ALIASES, _currency_jurisdictions,
    )
    mapped = _MODULE_ALIASES.get(name)
    if mapped is None and name in _currency_jurisdictions():
        mapped = f"countries.{name}"
    for candidate in (f"clausal.modules.{mapped or name}", name):
        try:
            return importlib.import_module(candidate)
        except ModuleNotFoundError as exc:
            missing = getattr(exc, "name", None) or ""
            if not (candidate == missing
                    or candidate.startswith(missing + ".")):
                raise   # the module exists; something IT imports is missing
        except ValueError:
            break       # no module name at all ("", a leading dot)
    from clausal.logic.exceptions import (  # noqa: PLC0415
        LogicException, existence_error,
    )
    raise LogicException(existence_error(
        "module", name,
        f"module_signatures: {name!r} names no module -- a module name "
        f"is spelled as -import_from spells it (py.datetime, currency, "
        f"pkg.mod)"))


def _module_for_moduleless_solve(goal) -> tuple[Any, Module]:
    """Pick the goal and module for a ``solve(goal)`` called without ``module=``.

    Returns ``(goal, module)``.  The goal comes back STRIPPED of a top-level
    qualification when that is where the module came from, so the caller can
    hand both on and nothing resolves the same designator twice (P3-3 Task 6
    fix round 1, F8).  Resolving twice was not merely wasteful: the second
    resolution ran with the exporter as the calling module, so a diagnostic
    from it named the module that ANSWERS as the one that ASKED.

    Three cases, in the order they are asked:

      - a module-QUALIFIED cell goal carries its own answer.  ``(":", M, G)``
        names the module that answers, so ``module=`` is redundant rather than
        missing and the goal runs.  There is no calling module to report, and
        ``None`` is passed as one rather than a guess.
      - any other CELL goal has no module at all, and none can be guessed:
        a cell is a plain tuple, so there is no defining class to walk back to
        and the tuple's functor is a bare name that any number of modules may
        define.  Guessing here is exactly the module-locality bug this task
        exists to prevent, so the gap is REPORTED.
      - anything else raises the ``TypeError`` it always has.  (It used to
        walk the goal for an instance of a ``PredicateMeta`` class and answer
        that class's module first; W4a made such an instance impossible and
        W4b-3 slice 7 deleted the class and that walk, ``_infer_module``.)
    """
    _, _pre_functor = compound_cell_shape(goal)
    # W4: a mangled functor names its module.  No hint: a module-less solve
    # has no calling module (the handle rule's sys.modules and registry
    # steps still answer).
    goal = qualify_mangled_goal(goal)
    is_cell_goal, functor = compound_cell_shape(goal)
    if is_cell_goal:
        if functor == QUALIFIED_GOAL_FUNCTOR and len(goal) == 3:
            # ``_pre_functor`` is ``None`` when the goal was a bare atom
            # (``compound_cell_shape`` answers ``(False, None)`` for a
            # non-cell), so a bare ARITY-0 handle is not checked here and
            # keeps its older path -- a known gap in solve's normalisation,
            # left as it was; ``call/N`` passes the atom itself.
            raise_if_dangling_handle(_pre_functor, goal, "solve/1")
            return _strip_module_qualification(goal, None)
        from clausal.logic.exceptions import (  # noqa: PLC0415
            LogicException, existence_error,
        )
        if type(functor) is str and is_mangled(functor):
            # A MANGLED functor that ``qualify_mangled_goal`` above did NOT
            # convert to a ``(":", M, G)`` cell means its module half is not
            # a loaded Clausal module (ruling 2026-09-24, see
            # todo/mangled-goal-culprit-terms-are-malformed-2026-09-23.md):
            # this is a dangling predicate-handle, not an ordinary
            # module-less cell goal, and gets the demangled
            # ``existence_error(procedure, Name/Arity)`` shape -- never the
            # raw ``\x1f`` spelling, never a Python repr.
            module_name, name = demangle(functor)
            raise dangling_handle_exception(
                module_name, name, len(goal) - 1, False, "solve/1")
        raise LogicException(existence_error(
            # The REPR, not the goal (P3-3 Task 6 fix round 1, F4): the live
            # cell holds the caller's Vars, so a ``catch/3`` pattern unifying
            # with the culprit would alias them.  Same rule as
            # ``resolve_module``'s culprit — an error term is a ground atom.
            "module", repr(goal),
            f"solve/1: the unqualified cell goal {functor}/{len(goal) - 1} has "
            f"no calling module — pass module= (the module whose database "
            f"answers), or qualify the goal as (':', M, Goal).  A cell names a "
            f"predicate but carries no module of its own, so there is nothing "
            f"here to infer one from",
        ))
    raise TypeError(
        "Cannot infer module from goal. Pass the module explicitly, e.g.:\n"
        "  solve(goal, my_module)"
    )


def _resolved_goal_and_module(goal, module, context: str):
    """The shared entry resolution: ``(stripped goal, resolved Module)``.

    P3-3 Task 6 fix round 1 (F1, F2).  ``solve`` and ``query_wfs`` both have to
    answer "which module?" and both have to answer it the SAME way, because
    ``query_wfs`` asks a second question afterwards — which table entry holds
    this goal's truth values — of ``_tabled_entry_for_goal``, and that lookup
    must be made against the module the goal actually RAN against.  Before this
    round ``query_wfs`` passed its raw ``module`` argument to both, so a str
    designator crashed the entry lookup with an uncaught ``TypeError`` after
    the goal had already run (F1), and ``module=None`` with a qualified goal
    made the lookup bail and report every WFS-``Undefined`` answer as ``True``
    (F2).  One resolution, one answer, handed to both.
    """
    if module is None:
        return _module_for_moduleless_solve(goal)
    return _strip_module_qualification(goal, resolve_module(module, None, context))


def _strip_module_qualification(goal, module):
    """Peel a top-level ``(":", M, G)`` off *goal*, returning ``(G, M's Module)``.

    P3-3 Task 6.  This is where a qualified goal becomes a module SWITCH: the
    inner goal is compiled against — and cached under — the EXPORTING module,
    which is what makes ``solve((":", e, ("p", X)), module=i)`` answer *e*'s
    ``p/1`` while ``solve(("p", X), module=i)`` answers *i*'s.

    Doing it here, before ``_templatize_query_goal`` and ``_goal_cache_key``,
    is deliberate: from that point on a qualified goal IS an ordinary cell
    goal against another module, so it templatizes like one (ground arguments
    parameterize, distinct values share a compiled query) and its cache key is
    the ordinary ``(structural_key, id(module))`` with the RESOLVED module's
    id — which is the module the compiled artifact actually depends on.

    Non-qualified goals come back untouched.
    """
    _, _pre_functor = compound_cell_shape(goal)
    # W4: a mangled functor names its module; *module* (the resolved caller)
    # is the ruling-Q0 hint.
    goal = qualify_mangled_goal(goal, getattr(module, "db", None))
    is_cell_goal, functor = compound_cell_shape(goal)
    if not (is_cell_goal
            and functor == QUALIFIED_GOAL_FUNCTOR and len(goal) == 3):
        return goal, module
    raise_if_dangling_handle(_pre_functor, goal, "solve/1")
    target, inner = resolve_qualified_goal_cell(
        goal, "solve/1", module, call_extra=0,
        dialect_gate=False)   # route 5: Python is outside the edge rule
    _sandbox_query_edge(target, "solve/1")
    return inner, target


def raise_if_dangling_handle(
    handle: Any, qualified_goal: Any, context: str,
) -> None:
    """Raise :func:`dangling_handle_exception` iff *qualified_goal* is the
    ``(":", M, G)`` cell ``qualify_mangled_goal`` just BUILT from the
    predicate HANDLE *handle*, and ``M:G`` names no predicate in the loaded
    module ``M``.

    Shared by the goal ENTRY points (ruling 2, 2026-09-24): ``solve``'s
    normalisation and the ``call/N`` builtin make this one check, so they
    cannot disagree on when a loaded-module handle is dangling or on the
    term it raises.

    *handle* is the functor of the goal as the caller held it BEFORE
    ``qualify_mangled_goal``: slot 0 of a cell goal, or -- for an ARITY-0
    goal, which is a bare atom -- the atom itself.  It is the only way to
    tell "this qualification came from a mangled handle" apart from "the
    caller wrote ``(':', M, G)`` by hand", since both look identical
    afterwards.  Anything that is not a mangled atom (``None``, a
    hand-written ``':'``, an ordinary name) makes this a no-op, so a
    hand-written qualified goal keeps its existing, unrelated
    undefined-predicate path.  A no-op, too, whenever the target predicate
    DOES exist (a dispatch entry, or a binding in the module namespace).
    See todo/mangled-goal-culprit-terms-are-malformed-2026-09-23.md.
    """
    if not (type(handle) is str and is_mangled(handle)):
        return
    mod_name, inner = qualified_goal[1], qualified_goal[2]
    inner_is_cell, inner_name = compound_cell_shape(inner)
    name = inner_name if inner_is_cell else inner
    arity = len(inner) - 1 if inner_is_cell else 0
    module = resolve_module(mod_name, None, context)
    if module.db.get_dispatch(name, arity) is not None:
        return
    if (module.module_dict or {}).get(name) is not None:
        return
    # The HANDLE's module half, not slot 1: for an owner reached by the
    # caller's db or the handle-owner registry slot 1 is a Module object.
    raise dangling_handle_exception(
        demangle(handle)[0], name, arity, True, context)


def dangling_handle_exception(
    module_name: str, name: str, arity: int, loaded: bool, context: str,
):
    """The ``LogicException`` a dangling predicate HANDLE raises at a goal
    ENTRY point -- ``solve``'s normalisation and the ``call/N`` builtin
    (ruling 2, 2026-09-24: ``call/N`` raises exactly what ``solve`` raises,
    so both build it here and nowhere else).

    ``error(existence_error(procedure, Name/Arity), Context)`` with the
    halves already DEMANGLED; *loaded* is whether the handle's module half is
    a loaded Clausal module (predicate absent) or not (module never loaded),
    and it changes only the context text.  *context* is the entry point
    (``"solve/1"``, ``"call/2"``, ...) that opens the context string.
    """
    from clausal.logic.exceptions import (  # noqa: PLC0415
        LogicException, existence_error, dangling_handle_indicator_and_why,
    )
    indicator, why = dangling_handle_indicator_and_why(
        module_name, name, arity, loaded=loaded)
    if loaded:
        why += " (reached through a module-qualified predicate handle)"
    return LogicException(existence_error(
        "procedure", indicator, f"{context}: {why}"))


def call(
    functor,
    *args: Any,
    module: Module | None = None,
    trail: Trail | None = None,
) -> Iterator[Trail]:
    """Drive a compiled predicate; yield the Trail after each solution.

    ``functor`` may be either a predicate name string (requires ``module``) or
    a PredicateMeta class (``module`` is not needed in that case).

    Args are passed directly to the compiled dispatch function.  Output-position
    args should be Var objects — they will be bound on the Trail during each
    yielded solution.

    Parameters
    ----------
    functor:  predicate name string, or a PredicateMeta class
    *args:    arguments; may include Var objects for output positions
    module:   Module whose database holds the compiled predicate (not required
              when functor is a PredicateMeta class)
    trail:    optional Trail; a fresh one is created if not provided

    Yields
    ------
    Trail after each solution (bindings are live on the trail).

    Raises
    ------
    PredicateNotFoundError  (a ``KeyError`` and a ``LogicException`` whose
              ``.term`` is ISO ``existence_error(procedure, Name/Arity)``)
              if the predicate is not defined in module.
    """
    # W4: a module-qualified NAME (the mangled handle) is its own module
    # designator -- switch to that module and continue with the bare name.
    # ``_handle_module_name``/``_handle_name`` remember the DEMANGLED halves
    # whenever *functor* started out as a handle at all -- whether or not
    # its module turns out to be loaded -- so a failure below can raise the
    # dangling-handle shape (ruling 2026-09-24) instead of the ordinary
    # "module is required"/"not defined in module" KeyErrors, which stay
    # exactly as they were for a functor that was never a handle.
    _handle_module_name = _handle_name = None
    _sb_ctx = f"{functor if type(functor) is str else 'call'}/{len(args)}"
    if _sandbox_state.ACTIVE:
        # The functor names a predicate: an atom.  A goal OBJECT handed in
        # from Python is no data (clausal.sandbox).
        if type(functor) is not str:
            _sandbox_entry(functor, _sb_ctx)
        _sandbox_entry(args, _sb_ctx)
        _sandbox_module(module, _sb_ctx)
    if type(functor) is str:
        if is_mangled(functor):
            _handle_module_name, _handle_name = demangle(functor)
        # Q0 (round-3 review): the calling module's db is the hint, so a
        # handle naming ``module`` itself resolves there even when the
        # ``.clausal`` runner popped it from ``sys.modules``.  Only a real
        # Clausal module carries one (a Module, or an imported module's
        # ``__clausal_module__``); a designator string is resolved below.
        _cm = module if isinstance(module, Module) else getattr(
            module, "__clausal_module__", None)
        _q = qualify_mangled_goal(functor, db=getattr(_cm, "db", None))
        if _q is not functor:
            module = resolve_module(_q[1], module, "call/N")
            functor = _q[2]
            _sandbox_query_edge(module, _sb_ctx)
    # Fast path: predicate class passed directly — no module lookup needed.
    args = _python_entry(args)
    if hasattr(functor, '_get_dispatch'):
        if _sandbox_state.ACTIVE:
            from clausal.sandbox import check_goal_object  # noqa: PLC0415
            check_goal_object(
                functor, f"{getattr(functor, '_name', 'call')}/{len(args)}")
        dispatch_fn = functor._get_dispatch()
        if trail is None:
            trail = Trail()
        yield from _drive_trampoline(dispatch_fn, trail, *args)
        return

    if module is not None:
        module = _coerce_module(module)

    arity = len(args)

    # Phase 5: look up PredicateMeta class from module globals first.
    dispatch_fn = None
    other_arity_binding = None
    if module is not None and module.module_dict is not None:
        pred_cls = module.module_dict.get(functor)
        if pred_cls is None and type(functor) is str and "." in functor:
            # A DOTTED functor (``call("alow.numlist", 3, L)``): walk it the
            # way a compiled ``alow.numlist(3, L)`` does -- the first segment
            # in this module's namespace, the rest as attributes -- and hand
            # the binding to ``_dispatch_at``, whose handle route applies the
            # name+arity rule in the OWNER (its row at this arity, else a
            # builtin).  It used to refuse outright
            # ("'alow.numlist'/2 is not defined in module ...") where the
            # compiled call answered (name-arity residual Low 1).
            head, *rest = functor.split(".")
            if _sandbox_state.ACTIVE:
                from clausal.logic.compiler.globals_env import (  # noqa: PLC0415
                    _dotted_base)
                _sandbox_query_edge(
                    _dotted_base(functor.split("."), module.module_dict),
                    _sb_ctx)
            obj = module.module_dict.get(head)
            if _sandbox_state.ACTIVE and any(
                    p.startswith("_") for p in functor.split(".")):
                obj = None      # the sandbox: no walk into a Python attribute
            for part in rest:
                if obj is None:
                    break
                if _sandbox_state.ACTIVE:
                    from clausal.sandbox import walkable  # noqa: PLC0415
                    if not walkable(obj):
                        obj = None      # read only a Clausal/adapter module
                        break
                    from clausal.sandbox import read_attr  # noqa: PLC0415
                    obj = read_attr(obj, part)
                    continue
                obj = getattr(obj, part, None)
            if obj is not None and is_declared_predicate_name(obj, db=module.db):
                dispatch_fn = _dispatch_at(obj, arity, module.db)
            else:
                # A dotted predicate ADAPTER (``call("py.re.match", P, S)``):
                # the goal object the compiled ``py.re.match(P, S)`` calls.
                # Python is outside the dialect gate (route 5).
                from clausal.logic.builtins.higher_order import (  # noqa: PLC0415
                    dotted_goal_object,
                )
                hit = dotted_goal_object(module.module_dict, functor, module.db,
                                         _sb_ctx)
                if hit is not None:
                    dispatch_fn = _dispatch_at(hit[1], arity, module.db)
        # W4b-3: after the flip the binding is a module-qualified HANDLE,
        # which has no ``_get_dispatch``; skipping this phase then hands the
        # call to a same-named BUILTIN in Phase 6.  ``_dispatch_at`` resolves
        # either shape.
        #
        # Name + ARITY ruling (operator, 2026-09-24): a predicate binding --
        # class or handle alike -- is this call's target only at its own
        # arity (``globals_env._is_call_target``, the compile-time twin of
        # this lookup).  At another arity the call resolves NORMALLY:
        # this module's own db row, then the builtin.  Only when
        # neither answers does the call refuse (below) -- the same order
        # ``globals_env._inject_resolved_targets`` bakes into a compiled
        # call site.
        if pred_cls is not None and is_declared_predicate_name(pred_cls, db=module.db) \
                and not binding_grants_arity(pred_cls, arity, module.db,
                                             functor):
            other_arity_binding = pred_cls
        elif pred_cls is not None and (
                hasattr(pred_cls, '_get_dispatch')
                or is_declared_predicate_name(pred_cls, db=module.db)):
            # Pass the arity: call("citation", A, B) against citation/3 is the
            # same fault as writing it in a clause body, and gets the same
            # message rather than a TypeError about a missing `trail`.  Via
            # _dispatch_at, because pred_cls need not be a PredicateMeta.
            dispatch_fn = _dispatch_at(pred_cls, arity, module.db)

    # Name + ARITY ruling, review round: the calling module's OWN predicate
    # at the call arity wins over a same-named builtin (``get_dispatch`` asks
    # the row first, the builtin registry only after).  A class's ``_fields``
    # can be stale (see ``PredicateMeta._clause_arity``), so "declared at
    # another arity" may be wrong about a class whose clauses ARE at this
    # arity; asking the local row before Phase 6 keeps that predicate
    # answering instead of a builtin sharing its name.
    if other_arity_binding is not None:
        dispatch_fn = module.db.get_dispatch(functor, arity)

    # Phase 6: try builtins before Database fallback.
    if dispatch_fn is None and module is not None:
        from clausal.logic.builtins import get_builtin_predicate  # noqa: PLC0415
        builtin = get_builtin_predicate(functor, arity, module.db)
        if builtin is not None:
            dispatch_fn = builtin._get_dispatch()

    # Fall back to Database dispatch lookup (test modules and asserted predicates).
    if dispatch_fn is None and module is not None:
        dispatch_fn = module.db.get_dispatch(functor, arity)

    # Name + ARITY ruling: nothing in THIS module answered -- not its row, not
    # a builtin under this name -- so the call refuses, naming the name it
    # used.  It does NOT resolve the other arity in the binding's owner
    # (``_dispatch_at`` would): this call is UNQUALIFIED, and an import --
    # aliased or not -- grants the one arity it was imported at (operator
    # ruling 2026-09-24, closing the aliased-import leak).  A stale-``_fields``
    # class whose clauses ARE at this arity is still returned (its target).
    if dispatch_fn is None and other_arity_binding is not None:
        dispatch_fn = _refuse_unqualified_other_arity(
            other_arity_binding, functor, arity, module.db)

    if dispatch_fn is None:
        if _handle_name is not None:
            # *functor* arrived as a MANGLED predicate handle -- module
            # never loaded, or loaded but the predicate absent -- and gets
            # the ruled shape: LogicException(existence_error(procedure,
            # Name/Arity)), demangled, never the raw handle KeyError below
            # (which would either bake ``\x1f`` into ``functor!r`` or, once
            # resolved, still be an uncatchable plain KeyError).
            #
            # Ruling 2026-09-25: as ``PredicateNotFoundError`` -- the same
            # ISO term, and the ``KeyError`` the unqualified miss below is.
            from clausal.logic.exceptions import (  # noqa: PLC0415
                dangling_handle_indicator_and_why,
            )
            from clausal.predicate_diagnostics import (  # noqa: PLC0415
                PredicateNotFoundError,
            )
            # A diagnostic: the caller's db is the hint, and an ambiguous
            # owner is "unknown" here (only a dispatch raises it).
            from clausal.logic.predicate import _owner_db_or_none  # noqa: PLC0415
            loaded = _owner_db_or_none(
                _handle_module_name, getattr(module, "db", None)) is not None
            _indicator, why = dangling_handle_indicator_and_why(
                _handle_module_name, _handle_name, arity, loaded,
            )
            raise PredicateNotFoundError(
                f"call/N: {why}", _handle_name, arity)
        if module is None:
            raise KeyError(
                f"Predicate {functor!r}/{arity}: module is required when functor is a string"
            )
        # Operator ruling 2026-09-25: an unknown procedure is ISO
        # existence_error(procedure, Name/Arity).  ``PredicateNotFoundError``
        # is a KeyError AND a LogicException carrying that term, so every
        # ``except KeyError`` around ``call`` keeps working and ``.term`` is
        # the ISO one; the message is unchanged (``str()`` drops the quotes a
        # bare KeyError added).
        from clausal.predicate_diagnostics import (  # noqa: PLC0415
            PredicateNotFoundError,
        )
        raise PredicateNotFoundError(
            f"Predicate {functor!r}/{arity} is not defined in module {module.name!r}",
            functor, arity,
        )

    if trail is None:
        trail = Trail()

    if module is not None and type(functor) is str:
        # -meta_predicate (operator ruling 2026-09-25): a query names its
        # module, so a declared predicate's meta-arguments are qualified
        # with it -- as Scryer's toplevel expands a query goal.
        _specs = module.db.meta_predicate_specs(functor, arity)
        if _specs:
            from clausal.logic.meta_predicate import qualify_args  # noqa: PLC0415
            args = tuple(qualify_args(_specs, list(args), module.db))

    yield from _drive_trampoline(dispatch_fn, trail, *args)


def _python_entry(value):
    """THE LEAK RULE at a Python caller's door (dumb seam step (d),
    2026-09-26): an ``atom`` instance anywhere in a goal or argument list
    built by Python becomes the plain str before it can reach term space
    (or crash ``compile`` as an ast.Constant of the wrong type).

    ONE definition for the two entries Python has -- ``solve`` (a goal term;
    ``once``, ``query``, ``query_wfs`` and every goal-position seam go
    through it) and ``call`` (a functor and arguments handed straight to the
    dispatch; there is no funnel below the two that sees Python's values as
    terms).  An iterative, cycle-safe read-only scan decides first: a
    rewriter-built goal (a Node) is a leaf and costs one type test; a plain
    cell costs one pass plus a small visited table; a cons-like goal
    thousands of levels deep cannot raise RecursionError here.  Only a goal
    that holds a tag is rebuilt (a tagged CYCLE is refused, TypeError)."""
    if _has_atom_tag(value):
        return _strip_atom_tags(value)
    return value


def solve(
    goal: Any,
    module=None,
    trail: Trail | None = None,
) -> Iterator[Trail]:
    """Drive an arbitrary goal; yield the Trail after each solution.

    The goal may be any term node: Call, And, Or, Is, Not, in_, True, False, …
    Var objects embedded in the goal are referenced by identity in the compiled
    code so their bindings accumulate on the Trail and are readable via deref().

    Parameters
    ----------
    goal:    goal term
    module:  a module DESIGNATOR — a clausal Module, an imported .clausal
             Python module, or (P3-3 Task 6) the dotted name of one as a str —
             or None.  None means: a module-qualified cell goal names its own
             module; any other cell goal is an error naming the gap; anything
             else is auto-inferred from the predicate classes in the goal.
             See ``resolve_module`` and ``_module_for_moduleless_solve``.
    trail:   optional Trail; a fresh one is created if not provided

    Yields
    ------
    Trail after each solution (bindings are live on the trail).
    """
    _sandbox_entry(goal, "solve/2")
    goal, module = _resolved_goal_and_module(goal, module, "solve/2")
    goal = _python_entry(goal)
    _sandbox_module(module, "solve/2")
    if trail is None:
        trail = Trail()

    # Fast paths for trivial goals — avoid the compiler entirely.
    if goal is True:
        yield trail
        return
    if goal is False:
        return

    dispatch_fn, param_pairs = _compile_as_query(goal, module)
    # Bind parameterized ground args to their values before driving so the
    # value-independent compiled query sees the concrete arguments.
    for param_var, value in param_pairs:
        unify(param_var, value, trail)
    yield from _drive_trampoline(dispatch_fn, trail)


def query(
    goal: Any,
    variables: dict[str, Var],
    module=None,
    trail: Trail | None = None,
) -> Iterator[dict[str, Any]]:
    """Solve goal and yield one fully-dereferenced binding dict per solution.

    .. deprecated::
        Prefer ``solve`` (or ``call``) with the goal as a cell and the module
        that answers it, reading ``Var.value``::

            for trail in solve(("greeting", X := Var()), module=m):
                print(X.value)

            for trail in call("greeting", X := Var(), module=m):
                print(X.value)

        Do NOT iterate a goal built by calling a predicate from Python:
        ``m.greeting`` is a handle (a ``str``) and a builtin's term constructor such as
        ``clausal.between(1, 3, X)`` builds a CELL (a tuple), so
        ``for _ in between(1, 3, X)`` walks the tuple's elements and never
        runs the goal.

    Parameters
    ----------
    goal:      goal term (embed the same Var objects as values of variables)
    variables: mapping of name → Var whose bindings to capture each solution
    module:    Module, imported .clausal Python module, or None (auto-inferred)
    trail:     optional Trail (fresh if not provided)

    Yields
    ------
    dict mapping each name in variables to its fully-dereferenced value.
    Unbound Vars remain as Var objects in the dict.
    """
    import warnings
    warnings.warn(
        "query() is deprecated. Solve the goal as a cell with the module "
        "that answers it, and use Var.value:\n"
        "  for trail in solve((\"pred\", X := Var()), module=m): "
        "print(X.value)\n"
        "  for trail in call(\"pred\", X := Var(), module=m): "
        "print(X.value)",
        DeprecationWarning,
        stacklevel=2,
    )
    for _ in solve(goal, module, trail):
        yield {name: _deref_walk(var) for name, var in variables.items()}


def once(
    goal: Any,
    module=None,
    trail: Trail | None = None,
) -> Trail | None:
    """Return the Trail for the first solution, or None if the goal fails.

    Bindings on the returned Trail are live and readable via deref().

    Parameters
    ----------
    goal:    goal term
    module:  Module, imported .clausal Python module, or None (auto-inferred)
    trail:   optional Trail (fresh if not provided)

    Returns
    -------
    Trail (with bindings live) on success, or None on failure.
    """
    for t in solve(goal, module, trail):
        return t
    return None


def query_wfs(
    goal: Any,
    variables: dict[str, Var],
    module=None,
    trail: Trail | None = None,
) -> list[dict[str, Any]]:
    """Solve goal and return results with WFS truth annotations.

    Like ``query()``, but each result dict includes a ``"_truth"`` key
    whose value is ``True`` (unconditional), ``Undefined`` (unfounded), or
    ``True`` for non-tabled results.  The third value is the strong-Kleene
    ``Undefined`` singleton — the same one ``.clausal`` code writes — so a
    WFS-undefined answer can flow straight into Kleene-aware code.

    Each result also carries ``"_delays"``: a frozenset of ``DelayedNegation``
    objects, non-empty exactly when ``_truth`` is ``Undefined``.  Each names
    the negated tabled call the answer is conditional on (``.functor``,
    ``.arity``, ``.frozen_args``) — for a negation cycle, the cycle partner —
    so a caller can report *which* pair is unresolved, not just that
    something is.

    *module* takes the same designators ``solve`` takes — a Module, an imported
    .clausal module, its dotted name as a str, or None — and means the same
    thing, because it is resolved by the same chain before either the solve or
    the table lookup sees it.

    Returns a list (not iterator) since WFS resolution requires completing
    all SLG computation before truth values are determined.
    """
    # Resolve the module ONCE, here, and hand the same answer to both the
    # solve below and the entry lookup further down (P3-3 Task 6 fix round 1,
    # F1/F2 — see ``_resolved_goal_and_module``).  Passing the raw argument to
    # both let them disagree: the entry lookup does not accept a str
    # designator, and it bails outright on ``module=None``, which silently
    # turned every Undefined answer of a qualified goal into True.
    _sandbox_entry(goal, "query_wfs/3")
    goal, module = _resolved_goal_and_module(goal, module, "query_wfs/3")
    _sandbox_module(module, "query_wfs/3")

    # The judgement is the seam's ``judged_answers`` (a throwaway tabling
    # leader for the whole solve, 2026-09-08): EVERY goal shape is judged by
    # the delays its own derivation incurred -- a single tabled call, a
    # conjunction, an untabled wrapper, a ``++``-fed call -- so the old
    # "composite goals keep True" limitation is gone.  Definite answers
    # stream in derivation order; conditional ones are delivered after
    # global resolution (as a tabled root already delivered them), and a
    # WFS-false answer never surfaces.  Deferred answers are deduplicated
    # over the GOAL's own variables, not over *variables*: asking for none of
    # them must not merge four answers into one row.  Lazy import: seam
    # imports solve.
    from clausal.logic.seam import judged_answers  # noqa: PLC0415
    if trail is None:
        trail = Trail()
    results = []
    for truth, delays in judged_answers(
            goal, module, list(variables.values()), trail):
        r = {name: _deref_walk(var) for name, var in variables.items()}
        r["_truth"] = truth
        r["_delays"] = delays
        results.append(r)
    return results


def _tabled_call_site(goal, module, trail):
    """Return ``(module, functor, arity, goal_args)`` for a single
    tabled-predicate goal, or ``None`` for a non-tabled or composite goal.

    This is ``_tabled_entry_for_goal`` minus the table-store lookup, split out
    so a caller can take the SUBGOAL KEY at one moment and do the store lookup
    at another.  ``clausal.logic.seam._definite_answers`` needs exactly that:
    a table entry is stored under the key of the call AS WRITTEN, but the
    entry does not exist until ``solve()`` has run, so the site (and its key)
    are taken before the solve and the lookup is deferred to the first answer.
    Deriving the key at the first answer instead reads the goal's arguments as
    that answer has just bound them, which for an OPEN call
    (``wins(X)`` → ``wins(d)``) names a different subgoal and misses.

    Nothing here depends on the current bindings: the shape walk, the
    signature normalization and ``is_tabled`` are all static, so the site is
    the same before and after the solve.

    Handles every single-goal shape ``solve()`` accepts: term instances, reified
    ``Call(LoadName(...))`` — the shape ``docs/wfs.md`` and the test suite
    build (todo/wfs-undefined-lost-at-query-surface.md §3) — and qualified
    ``Call(LoadAttr(LoadName(mod), pred))``, whose table lives in the
    EXPORTING module's db. Keyword arguments are normalized positionally
    via the owning db's registered signature, mirroring the tabled-NAF
    compiler seam.

    P3-3 Task 6 adds the two CELL shapes ``solve()`` accepts: the plain cell
    ``("p", A)`` (invisible here before — it fell to the final ``else`` and
    every cell goal read as non-tabled), and the module-qualified
    ``(":", M, G)``, resolved through ``resolve_module`` so the entry is
    looked up in the EXPORTING module's db — the same rule the dotted
    ``LoadAttr`` path below already follows, reached by the new resolver
    rather than by that path's caller-dict walk.  The two are deliberately
    NOT converged here: the legacy walk stays pinned as R10 records, and
    the convergence is a filed follow-up."""
    if module is None:
        return None
    mod = _coerce_module(module)
    kwargs = []
    is_cell_goal, cell_functor = compound_cell_shape(goal)
    if (is_cell_goal
            and cell_functor == QUALIFIED_GOAL_FUNCTOR and len(goal) == 3):
        # Resolve the qualification, then fall through to the cell branch with
        # the EXPORTING module in hand.  A designator that does not resolve is
        # not this function's error to raise: it is asked AFTER solve() has
        # already run the goal, so solve() has raised it already; here the
        # honest answer for a goal that names no module is "no table".
        from clausal.logic.exceptions import LogicException  # noqa: PLC0415
        try:
            mod, goal = resolve_qualified_goal_cell(
                goal, "query_wfs/2", mod, dialect_gate=False)
        except LogicException:
            return None
        is_cell_goal, cell_functor = compound_cell_shape(goal)
    if is_cell_goal:
        functor = cell_functor
        goal_args = list(goal[1:])
    elif isinstance(goal, _ReifiedCall):
        func = goal.func
        if isinstance(func, _ReifiedLoadName):
            functor = func.name
        elif isinstance(func, _ReifiedLoadAttr):
            # Qualified goal, possibly nested (pkg.sub.Pred) — walk the
            # dotted chain down to a LoadName base, then resolve segment by
            # segment through the querying module's dict and getattr, and
            # consult the EXPORTING module's db. A directly-constructed
            # Module has module_dict=None — fall back gracefully.
            functor = func.attr
            segments = []
            node = func.object
            while isinstance(node, _ReifiedLoadAttr):
                segments.append(node.attr)
                node = node.object
            if not isinstance(node, _ReifiedLoadName):
                return None
            segments.append(node.name)
            segments.reverse()
            md = mod.module_dict
            if md is None:
                return None
            owner = md.get(segments[0])
            if len(segments) > 1:
                # The import hook does not bind submodules as parent-package
                # attributes, so walk sys.modules by the full dotted name
                # first; fall back to a getattr chain for plain objects.
                dotted = sys.modules.get(".".join(segments))
                if dotted is not None:
                    owner = dotted
                else:
                    for seg in segments[1:]:
                        if owner is None:
                            return None
                        owner = getattr(owner, seg, None)
            if owner is None:
                return None
            try:
                mod = _coerce_module(owner)
            except (TypeError, AttributeError, KeyError):
                return None
        else:
            return None
        goal_args = list(goal.args)
        kwargs = list(goal.kwargs)
    elif is_term_instance(goal):
        functor = type(goal).__name__
        goal_args = [getattr(goal, f) for f in term_field_names(goal)]
    else:
        return None
    if kwargs:
        if any(kw.name is None for kw in kwargs):
            return None  # **splat — positions unknowable here
        sig = mod.db.signature_for(functor, len(goal_args) + len(kwargs))
        if sig is None:
            return None
        kw_map = {kw.name: kw.value for kw in kwargs}
        merged = list(goal_args)
        for field in sig[len(goal_args):]:
            if field not in kw_map:
                return None
            merged.append(kw_map[field])
        goal_args = merged
    arity = len(goal_args)
    if not mod.db.is_tabled(functor, arity):
        # An -import_from-remapped predicate resolves by bare name here but
        # is tabled — and tabled INTO — the exporting module's db. Follow
        # the binding back to its defining module before giving up.
        # ``predicate_owner_module`` answers a class's ``__module__`` and a
        # mangled handle's module half alike: a bare ``getattr(binding,
        # "__module__")`` on a handle (a ``str``) answers ``'builtins'`` --
        # a silent "not tabled" once the bindings flip.
        from clausal.logic.predicate import predicate_owner_module  # noqa: PLC0415
        md = mod.module_dict
        binding = md.get(functor) if md is not None else None
        owner_name = predicate_owner_module(binding)
        owner = sys.modules.get(owner_name) if owner_name else None
        if owner is None:
            return None
        try:
            owner_mod = _coerce_module(owner)
        except (TypeError, AttributeError, KeyError):
            return None
        if owner_mod.db is mod.db or not owner_mod.db.is_tabled(functor, arity):
            return None
        mod = owner_mod
    return mod, functor, arity, goal_args


def _tabled_entry_for_goal(goal, module, trail):
    """Return ``(TableEntry, goal_args)`` for a single tabled-predicate goal,
    or ``(None, None)`` for a non-tabled or composite goal (A04-F004).

    The site walk lives in ``_tabled_call_site`` (see there for the shapes
    handled); this is that plus the store lookup, keyed on the goal's
    arguments as they stand NOW.  ``query_wfs`` calls it after its solve has
    finished and the bindings are undone, so "now" is the call as written —
    which is the key the entry is stored under.
    """
    site = _tabled_call_site(goal, module, trail)
    if site is None:
        return None, None
    mod, functor, arity, goal_args = site
    from clausal.logic.tabling import make_subgoal_key
    key = make_subgoal_key(goal_args, trail or Trail())
    return mod.db.table_store.get((functor, arity, key)), goal_args


__all__ = [
    "call",
    "solve",
    "query",
    "query_wfs",
    "once",
    "resolve_module",
    "_deref_walk",
]
