"""clausal.logic.compiler — predicate compiler (Steps 4 + 5).

Step 4 (head patterns): head_to_match_pattern, compile_head_to_match_case
Step 5 (body goals):    term_to_ast_expr, arith_to_ast_expr, compile_goal,
                        compile_body, _make_body_compiler

List patterns:  Bidirectional ``[HEAD, *TAIL]`` via _head_list_unify_input/output.
                Repeated head vars via dup_guards.  See block comment above
                ``_head_list_unify_input`` for the full design.

Two compilation strategies are provided:

**Simple / short-stack** (``compile_predicate``)
    Each clause becomes a ``match`` arm.  The body ends with ``yield None``
    for each solution.  Sub-predicate calls use Python ``for`` loops so the
    Python call stack grows with recursion depth.  Use for predicates whose
    call depth is bounded (e.g., fact tables, leaf predicates).

    Compiled function signature::

        def {functor}__{arity}(arg0, …, argN, trail, k):
            …
            yield None   # ← one solution

**Trampoline / stack-safe** (``compile_predicate_trampoline``)
    Every generated function is an immortal coroutine in the
    ``clausal.logic.trampoline`` Step protocol.  Sub-predicate calls use
    ``yield Step(child_gen, …)`` so the Python call stack does *not* grow.
    Solutions are surfaced via ``yield Step(parent, None)``; exhaustion via
    ``yield Step(parent, DONE)``.  The trampoline drives all generators.
    ``continuation_search.Search`` (Step 7) provides the ``__iter__``
    bridge.

    Compiled function signature::

        def {functor}__{arity}(parent, arg0, …, argN, trail):
            self = yield   # bootstrap hook
            …
            yield Step(parent, _DONE)   # ← search exhausted
"""

from __future__ import annotations

import ast
import dataclasses
from typing import Any, Callable

from clausal.logic.variables import Var, is_var, deref, unify
from clausal.logic.trampoline import Step
from clausal.terms import (
    Compound,
    ArithConstraint,
    Add, Sub, Mult, Div, FloorDiv, Mod, Pow,
    Negate,
    And, Or, Not,
    Is, IsNot, Eq, NotEq,
    Lt, LtE, Gt, GtE,
    In, NotIn,
    Call, LoadName,
)
from clausal.pythonic_ast.nodes import StarUnpack
from clausal.logic.database import Clause, Database
from clausal.logic.predicate import PredicateMeta, is_term_instance, term_field_names
from clausal.codegen import functiondef_to_function


# ── Predicate-as-class dispatch adapter ───────────────────────────────────────
#
# Phase 2 of the predicate-as-class refactor changes compiled dispatch calls
# from  ``_db.table_for(fname, arity).get_dispatch()(args, trail, k)``
# to    ``fname._get_dispatch()(args, trail, k)``
# where ``fname`` is resolved from the compiled function's globals.
#
# For predicates that are real PredicateMeta classes (e.g. from .clausal
# modules), the class itself is injected into globals and _get_dispatch()
# returns the compiled dispatch function directly.
#
# For predicates not yet available as classes (e.g. in tests that still use
# Database directly, or for builtin predicates), _DbDispatchAdapter wraps the
# Database lookup with the same _get_dispatch() interface.


class _DbDispatchAdapter:
    """Adapter: wraps db.get_dispatch() with _get_dispatch() interface.

    Used when a called predicate is in the database but not in module globals.
    Provides the same ``_get_dispatch()`` protocol as PredicateMeta classes.
    """
    __slots__ = ("_db", "_functor", "_arity")

    def __init__(self, db: Database, functor: str, arity: int) -> None:
        self._db = db
        self._functor = functor
        self._arity = arity

    def _get_dispatch(self):
        fn = self._db.get_dispatch(self._functor, self._arity)
        if fn is None:
            raise KeyError(
                f"Predicate {self._functor}/{self._arity} not found"
            )
        return fn


class _GlobalsDb:
    """Minimal db-like proxy for signature lookup from module globals.

    Used by compile_predicate when ``db=None`` — looks up ``_signature`` from
    PredicateMeta classes found in the provided globals dict.  Only
    ``signature_for`` is implemented; other Database methods are not needed
    when compiling without a live database.
    """
    __slots__ = ("_globals",)

    def __init__(self, globals_dict: dict) -> None:
        self._globals = globals_dict

    def signature_for(self, functor: str, arity: int):
        cls = self._globals.get(functor)
        if isinstance(cls, PredicateMeta):
            return cls._signature
        return None


# ── Bidirectional list pattern unification ────────────────────────────────────
#
# Problem
# -------
# A clause like ``append([HEAD, *TAIL], B, [HEAD, *RESULT]) <- append(TAIL, B, RESULT)``
# has list patterns in head positions 1 and 3.  Python's ``match`` statement
# can only *destructure* sequences — it requires the value to already be a
# list.  But position 3 may receive an unbound Var (output mode), so a plain
# MatchSequence would fail to match.
#
# Additionally, the same Var ``HEAD`` appears in both positions 1 and 3 —
# Python's ``match`` rejects duplicate name bindings in a single case arm.
#
# Solution: two-phase list unification
# -------------------------------------
# List patterns in clause heads compile as **wildcard captures** (MatchAs)
# instead of MatchSequence.  Each list pattern records a "list guard" with
# its decomposed structure (before-star elements, star var, after-star
# elements).  At runtime, unification proceeds in two phases:
#
# 1. **Input phase** (before the body runs):
#    ``_head_list_unify_input(target, before_vars, star_var, after_vars, trail)``
#    - If *target* is a list → destructure and unify each var.  Returns True.
#    - If *target* is an unbound Var → defer.  Returns None.
#    - Otherwise → clause doesn't match.  Returns False.
#
# 2. **Output phase** (at each solution / yield point):
#    ``_head_list_unify_output(target, before_vars, star_var, after_vars, trail)``
#    - Called only for guards that returned None in phase 1.
#    - Constructs ``[deref(v1), deref(v2), *deref(star), ...]`` from the
#      now-bound vars and unifies the result with *target*.
#
# The output phase runs at yield points rather than before the body because
# the body may bind vars that the list pattern depends on (e.g., RESULT in
# ``append`` is bound by the recursive call).
#
# Compiled code structure (for ``append`` clause 2)::
#
#     case [_lcap0, _v10, _lcap1]:        # wildcards for all args
#         _v8 = Var(); _v9 = Var(); _v11 = Var()   # list-pattern vars
#         _lr0 = _head_list_unify_input(_lcap0, [_v8], _v9, [], trail)
#         _lr1 = _head_list_unify_input(_lcap1, [_v8], _v11, [], trail)
#         if _lr0 is not False and _lr1 is not False:
#             for _ in dispatch(_v9, _v10, _v11, trail, k):  # body
#                 if (_lr0 is not None or _head_list_unify_output(...)) \
#                 and (_lr1 is not None or _head_list_unify_output(...)):
#                     yield None                               # solution
#
# Repeated Vars across list patterns (e.g., HEAD in positions 1 and 3) work
# because both guards reference the *same* Var() object (_v8).  Phase-1
# input destructuring binds it from one list; phase-2 output construction
# uses the bound value to build the other list.
#
# Related: ``_wrap_yields_with_output_guards`` is an AST rewriter that
# replaces every ``yield None`` in the body with the guarded version.
#
# Related: ``_derive_field_names`` in term_rewriting.py deduplicates field
# names when the same Var name appears multiple times in a trailing-comma
# fact (e.g., ``append([], B, B)`` → fields ``b``, ``b_1``), preventing
# a SyntaxError from duplicate keyword arguments.
# ──────────────────────────────────────────────────────────────────────────────


def _head_list_unify_input(target, var_vals, star_val, after_vals, trail):
    """Input-mode list pattern unification: destructure a list.

    Returns True if target is a list and all elements unify.
    Returns None if target is an unbound Var (defer to output mode).
    Returns False if target is incompatible.
    """
    d = deref(target)

    if isinstance(d, list):
        n_before = len(var_vals)
        n_after = len(after_vals)
        min_len = n_before + n_after
        if star_val is None:
            if len(d) != min_len:
                return False
        else:
            if len(d) < min_len:
                return False
        for i, v in enumerate(var_vals):
            if not unify(v, d[i], trail):
                return False
        if star_val is not None:
            star_end = len(d) - n_after if n_after else len(d)
            if not unify(star_val, d[n_before:star_end], trail):
                return False
        for i, v in enumerate(after_vals):
            if not unify(v, d[len(d) - n_after + i], trail):
                return False
        return True

    elif is_var(d):
        # Defer to output mode — vars will be bound by body
        return None

    else:
        return False


def _head_multi_star_error():
    """Raise when a multi-star list pattern receives an unbound variable."""
    raise TypeError(
        "Cannot match multi-star pattern against unbound variable"
    )


def _head_list_unify_output(target, var_vals, star_val, after_vals, trail):
    """Output-mode list pattern unification: construct list from bound vars.

    Called after body execution when target was an unbound Var.
    """
    d = deref(target)
    if not is_var(d):
        # Already bound (e.g., by body) — switch to input mode
        return _head_list_unify_input(target, var_vals, star_val, after_vals, trail)
    result = [deref(v) for v in var_vals]
    if star_val is not None:
        s = deref(star_val)
        if isinstance(s, list):
            result.extend(s)
        elif is_var(s):
            return False
        else:
            result.append(s)
    result.extend(deref(v) for v in after_vals)
    return unify(d, result, trail)


# ── Body-position star-list unification (Phase 5) ─────────────────────────────


def _body_star_unify(target, before_vals, star_val, after_vals, trail):
    """Bidirectional star-list unification for body-position Is goals.

    Handles both deconstruction (target is a ground list) and construction
    (target is an unbound Var, pattern vars are bound).
    """
    d = deref(target)

    if isinstance(d, list):
        # Deconstruction: split list according to the pattern
        return _head_list_unify_input(target, before_vals, star_val, after_vals, trail)

    if is_var(d):
        # Construction: build list from bound vars and unify with target
        return _head_list_unify_output(target, before_vals, star_val, after_vals, trail)

    return False


def _body_multi_star_unify(target, segments, trail):
    """Body-position multi-star unification.

    *segments* is a list of ``("fixed", [var1, var2, ...])`` or
    ``("star", var)`` tuples describing the pattern.

    The target must be a ground list — unbound Var targets are not supported
    for multi-star patterns (same as head-position multi-star).

    Yields once per valid split (combinatorial backtracking).
    """
    d = deref(target)
    if not isinstance(d, list):
        if is_var(d):
            raise TypeError(
                "Cannot match multi-star pattern against unbound variable"
            )
        return  # not a list → no solutions

    # Parse segments into fixed counts and star positions
    stars = []
    fixed_total = 0
    for kind, val in segments:
        if kind == "fixed":
            fixed_total += len(val)
        else:
            stars.append(val)

    n_stars = len(stars)
    n = len(d)
    if n < fixed_total:
        return  # list too short

    remainder = n - fixed_total
    # Generate all ways to distribute `remainder` items among `n_stars` stars
    for split in _multi_star_splits(n_stars, remainder):
        mark = trail.mark()
        ok = True
        pos = 0
        si = 0  # star index
        for kind, val in segments:
            if not ok:
                break
            if kind == "fixed":
                for v in val:
                    if not unify(v, d[pos], trail):
                        ok = False
                        break
                    pos += 1
            else:  # star
                length = split[si]
                if not unify(val, d[pos:pos + length], trail):
                    ok = False
                pos += length
                si += 1
        if ok:
            yield True
        trail.undo(mark)


def _multi_star_splits(n_stars, total):
    """Generate all ways to split *total* items among *n_stars* stars.

    Each split is a tuple of n_stars non-negative integers summing to total.
    """
    if n_stars == 1:
        yield (total,)
        return
    for i in range(total + 1):
        for rest in _multi_star_splits(n_stars - 1, total - i):
            yield (i, *rest)


# ── Variable naming ────────────────────────────────────────────────────────────


def _var_python_name(var: Var) -> str:
    """Return a stable Python identifier for a logic variable from its _id."""
    return f"_v{var._id}"


def _collect_vars(term: Any, seen: set[int] | None = None) -> list[Var]:
    """Recursively collect all Var objects reachable from term, in order.

    Used to pre-scan body goals left-to-right so that body-only Vars are
    registered in ``var_context`` before right-to-left body compilation starts.
    Without this pre-pass, body-only Vars are walrus-assigned in the innermost
    (last) goal's argument list but referenced in earlier (outer) goal arguments,
    causing UnboundLocalError at runtime.
    """
    if seen is None:
        seen = set()

    term = deref(term)

    if is_var(term):
        if term._id not in seen:
            seen.add(term._id)
            return [term]
        return []

    if term is None or isinstance(term, (bool, int, float, str, bytes, complex)):
        return []

    if isinstance(term, StarUnpack):
        return _collect_vars(term.value, seen)

    if isinstance(term, list):
        result: list[Var] = []
        for e in term:
            result.extend(_collect_vars(e, seen))
        return result

    if isinstance(term, dict):
        result = []
        for k, v in term.items():
            result.extend(_collect_vars(k, seen))
            result.extend(_collect_vars(v, seen))
        return result

    # KWTerm: recurse into field values
    from clausal.terms import KWTerm  # noqa: PLC0415
    if isinstance(term, KWTerm):
        result = []
        for v in term.values():
            result.extend(_collect_vars(v, seen))
        return result

    if isinstance(term, Compound):
        result = _collect_vars(term.functor, seen)
        for a in term.args:
            result.extend(_collect_vars(a, seen))
        return result

    if is_term_instance(term):
        result = []
        for name in term_field_names(term):
            result.extend(_collect_vars(getattr(term, name), seen))
        return result

    # term is an operator/goal node — recurse into its fields
    try:
        fields = dataclasses.fields(term)
        result = []
        for f in fields:
            val = getattr(term, f.name)
            if val is not None:
                result.extend(_collect_vars(val, seen))
        return result
    except TypeError:
        return []


def _collect_head_types(clauses: list[Clause]) -> dict[str, type]:
    """Return a name→type dict for all user-defined dataclass types found in clause heads.

    These are injected into the compiled function's globals so that
    ``case dog(name=_v0):`` match patterns can resolve ``dog``.
    """
    types: dict[str, type] = {}

    def _walk(term: Any) -> None:
        term = deref(term)
        if isinstance(term, StarUnpack):
            _walk(term.value)
        elif isinstance(term, Compound):
            for a in term.args:
                _walk(a)
        elif isinstance(term, list):
            for e in term:
                _walk(e)
        elif is_term_instance(term):
            cls = type(term)
            types[cls.__name__] = cls
            for name in term_field_names(term):
                _walk(getattr(term, name))

    for clause in clauses:
        _walk(clause.head)
        for goal in clause.body:
            _walk(goal)

    return types


def _collect_types_from_term(term: Any) -> dict[str, type]:
    """Return a name→type dict for all user-defined term types in *term*.

    Like _collect_head_types but operates on a single arbitrary term, used by
    _compile_as_query to inject types from inline goal arguments.
    """
    types: dict[str, type] = {}

    def _walk(t: Any) -> None:
        t = deref(t)
        if isinstance(t, StarUnpack):
            _walk(t.value)
        elif isinstance(t, Compound):
            for a in t.args:
                _walk(a)
        elif isinstance(t, list):
            for e in t:
                _walk(e)
        elif isinstance(t, dict):
            for v in t.values():
                _walk(v)
        elif is_term_instance(t):
            cls = type(t)
            types[cls.__name__] = cls
            for name in term_field_names(t):
                _walk(getattr(t, name))

    _walk(term)
    return types


def _collect_call_targets(clauses: list[Clause]) -> set[tuple[str, int]]:
    """Collect (fname, arity) pairs from Call(LoadName) nodes in clause bodies.

    Used to inject predicate class references (or _DbDispatchAdapter shims)
    into the compiled function's globals so that ``fname._get_dispatch()``
    resolves at runtime.
    """
    targets: set[tuple[str, int]] = set()

    def _walk(term: Any) -> None:
        if isinstance(term, Call) and isinstance(term.func, LoadName):
            n_kwargs = len(term.kwargs) if term.kwargs else 0
            targets.add((term.func.name, len(term.args) + n_kwargs))
        if isinstance(term, list):
            for e in term:
                _walk(e)
        elif is_term_instance(term):
            for name in term_field_names(term):
                val = getattr(term, name)
                if val is not None:
                    _walk(val)

    for clause in clauses:
        for goal in clause.body:
            _walk(goal)

    return targets


def _inject_call_targets(
    clauses: list[Clause],
    base_globals: dict,
    db: "Database | None",
    globals_: dict | None,
) -> None:
    """Inject predicate class references into base_globals for body call targets.

    For each Call(LoadName(name=fname)) in clause bodies:
    - If fname is already in base_globals (e.g. utility functions), skip.
    - If fname is in globals_ (module dict), inject it directly.
    - If fname is a builtin, inject a BuiltinPredicate adapter.
    - Otherwise, skip (predicate must be resolved at runtime or is missing).
    """
    from clausal.logic.builtins import get_builtin_predicate  # noqa: PLC0415
    call_targets = _collect_call_targets(clauses)
    for target_name, target_arity in call_targets:
        if target_name in base_globals:
            continue
        if globals_ and target_name in globals_:
            base_globals[target_name] = globals_[target_name]
        else:
            builtin = get_builtin_predicate(target_name, target_arity, db)
            if builtin is not None:
                base_globals[target_name] = builtin
            elif db is not None:
                base_globals[target_name] = _DbDispatchAdapter(db, target_name, target_arity)


def _preallocate_body_vars(
    goals: list,
    var_context: dict[int, str],
) -> list[ast.stmt]:
    """Pre-scan goals left-to-right; emit ``_vN = Var()`` for body-only Vars.

    Populates ``var_context`` for every Var found in the goals so that
    subsequent right-to-left compilation sees them as already-known (name
    reference) rather than body-only (walrus).  Returns the list of allocation
    statements to prepend to the compiled body.

    This prevents the UnboundLocalError that arises when a Var first appears as
    an argument to an outer goal but gets walrus-assigned inside an inner goal
    due to right-to-left compilation order.
    """
    stmts: list[ast.stmt] = []
    seen: set[int] = set(var_context.keys())  # head Vars already allocated
    for goal in goals:
        for var in _collect_vars(goal, seen):
            if var._id not in var_context:
                name = _var_python_name(var)
                var_context[var._id] = name
                stmts.append(_assign(name, _call(_name("Var"))))
    return stmts


# ── ast helpers ────────────────────────────────────────────────────────────────


def _name(id_: str, ctx=None) -> ast.Name:
    return ast.Name(id=id_, ctx=ctx or ast.Load())


def _attr(obj_name: str, attr: str) -> ast.Attribute:
    return ast.Attribute(value=_name(obj_name), attr=attr, ctx=ast.Load())


def _call(func: ast.expr, *args: ast.expr, **kwargs_: ast.expr) -> ast.Call:
    kws = [ast.keyword(arg=k, value=v) for k, v in kwargs_.items()]
    return ast.Call(func=func, args=list(args), keywords=kws)


# ── Unique-name counter ────────────────────────────────────────────────────────

_compile_counter: list[int] = [0]


def _fresh(prefix: str = "_t") -> str:
    """Generate a compile-time unique Python local variable name."""
    _compile_counter[0] += 1
    return f"{prefix}{_compile_counter[0]}"


# ── Term → AST expression ──────────────────────────────────────────────────────


def term_to_ast_expr(term: Any, var_context: dict[int, str]) -> ast.expr:
    """Convert a term value to a Python AST expression.

    The generated expression evaluates at runtime to the term.
    Vars already in var_context are referenced by name.  Vars not yet in
    var_context (body-only Vars) are introduced via walrus ``(_vN := Var())``.

    Supports: Var, Python scalars, list, Compound, functor dataclasses.
    Does NOT recursively evaluate arithmetic — use arith_to_ast_expr for that.
    """
    term = deref(term)

    if is_var(term):
        vid = term._id
        if vid in var_context:
            return _name(var_context[vid])
        # Body-only Var: introduce via walrus assignment
        vname = _var_python_name(term)
        var_context[vid] = vname
        return ast.NamedExpr(
            target=ast.Name(id=vname, ctx=ast.Store()),
            value=_call(_name("Var")),
        )

    if term is None or isinstance(term, bool):
        return ast.Constant(value=term)

    if isinstance(term, (int, float, str, bytes, complex)):
        return ast.Constant(value=term)

    if isinstance(term, StarUnpack):
        return ast.Starred(
            value=term_to_ast_expr(term.value, var_context),
            ctx=ast.Load(),
        )

    if isinstance(term, list):
        return ast.List(
            elts=[term_to_ast_expr(e, var_context) for e in term],
            ctx=ast.Load(),
        )

    if isinstance(term, dict):
        return ast.Dict(
            keys=[term_to_ast_expr(k, var_context) for k in term.keys()],
            values=[term_to_ast_expr(v, var_context) for v in term.values()],
        )

    if isinstance(term, Compound):
        f = term.functor
        f_expr: ast.expr
        if is_var(f):
            vid = f._id
            f_expr = _name(var_context[vid]) if vid in var_context else _call(_name("Var"))
        else:
            f_expr = ast.Constant(value=f)
        args_elts = [term_to_ast_expr(a, var_context) for a in term.args]
        return _call(
            _name("Compound"),
            f_expr,
            ast.Tuple(elts=args_elts, ctx=ast.Load()),
        )

    # Arithmetic term nodes: dispatch to arith_to_ast_expr so they generate
    # native Python binary/unary ops rather than functor-dataclass constructor calls.
    if isinstance(term, (Add, Sub, Mult, Div, FloorDiv, Mod, Pow, Negate)):
        return arith_to_ast_expr(term, var_context)

    if is_term_instance(term):
        cls_name = type(term).__name__
        return ast.Call(
            func=_name(cls_name),
            args=[],
            keywords=[
                ast.keyword(
                    arg=name,
                    value=term_to_ast_expr(getattr(term, name), var_context),
                )
                for name in term_field_names(term)
            ],
        )

    # KWTerm: generate KWTerm("functor", key=val, ...)
    from clausal.terms import KWTerm  # noqa: PLC0415
    if isinstance(term, KWTerm):
        keywords = [
            ast.keyword(arg=k, value=term_to_ast_expr(v, var_context))
            for k, v in term.items()
        ]
        return ast.Call(
            func=_name("KWTerm"),
            args=[ast.Constant(value=term.functor)],
            keywords=keywords,
        )

    raise NotImplementedError(
        f"term_to_ast_expr: unsupported term type {type(term).__name__}: {term!r}"
    )


# ── Arithmetic term → AST expression ──────────────────────────────────────────

_ARITH_BINOP_MAP: list[tuple[type, ast.operator]] = [
    (Add,      ast.Add()),
    (Sub,      ast.Sub()),
    (Mult,     ast.Mult()),
    (Div,      ast.Div()),
    (FloorDiv, ast.FloorDiv()),
    (Mod,      ast.Mod()),
    (Pow,      ast.Pow()),
]


def arith_to_ast_expr(term: Any, var_context: dict[int, str]) -> ast.expr:
    """Convert an arithmetic term to a Python arithmetic AST expression.

    Generates code that evaluates the expression to a Python number at runtime.
    Vars are dereferenced.  Arithmetic binary operators are unboxed to native
    Python ``ast.BinOp`` nodes.
    """
    term = deref(term)

    if is_var(term):
        vid = term._id
        vname = var_context.get(vid, _var_python_name(term))
        return _call(_name("deref"), _name(vname))

    if isinstance(term, (int, float)) and not isinstance(term, bool):
        return ast.Constant(value=term)

    if isinstance(term, Negate):
        return ast.UnaryOp(
            op=ast.USub(),
            operand=arith_to_ast_expr(term.operand, var_context),
        )

    for cls, ast_op in _ARITH_BINOP_MAP:
        if isinstance(term, cls):
            return ast.BinOp(
                left=arith_to_ast_expr(term.left, var_context),
                op=ast_op,
                right=arith_to_ast_expr(term.right, var_context),
            )

    # Fallback: treat as a plain term (e.g. a Var holding a number at runtime)
    return term_to_ast_expr(term, var_context)


# ── Misc AST-building helpers ──────────────────────────────────────────────────


def _yield_none_stmt() -> ast.stmt:
    return ast.Expr(value=ast.Yield(value=ast.Constant(value=None)))


def _assign(target: str, value: ast.expr) -> ast.stmt:
    return ast.Assign(
        targets=[_name(target, ast.Store())],
        value=value,
        lineno=0,
        col_offset=0,
    )


def _assign_mark(mark_name: str, trail_name: str) -> ast.stmt:
    return _assign(mark_name, _call(_attr(trail_name, "mark")))


def _undo_stmt(mark_name: str, trail_name: str) -> ast.stmt:
    return ast.Expr(value=_call(_attr(trail_name, "undo"), _name(mark_name)))


def _if(test: ast.expr, body: list[ast.stmt]) -> ast.If:
    return ast.If(test=test, body=body or [ast.Pass()], orelse=[])


def _compile_arith_cmp(
    l: Any,
    r: Any,
    ast_op: ast.cmpop,
    var_context: dict[int, str],
    k_stmts: list[ast.stmt],
) -> list[ast.stmt]:
    l_expr = arith_to_ast_expr(l, var_context)
    r_expr = arith_to_ast_expr(r, var_context)
    test = ast.Compare(left=l_expr, ops=[ast_op], comparators=[r_expr])
    return [_if(test, k_stmts)]


def _deref_cmp(
    l: Any,
    r: Any,
    ast_op: ast.cmpop,
    var_context: dict[int, str],
    k_stmts: list[ast.stmt],
) -> list[ast.stmt]:
    """Compile a structural comparison using deref on both sides."""
    l_expr = _call(_name("deref"), term_to_ast_expr(l, var_context))
    r_expr = _call(_name("deref"), term_to_ast_expr(r, var_context))
    test = ast.Compare(left=l_expr, ops=[ast_op], comparators=[r_expr])
    return [_if(test, k_stmts)]


def _dispatch_call_iter(
    fname: str,
    arity: int,
    arg_exprs: list[ast.expr],
    trail_name: str,
) -> ast.expr:
    """Generate: fname._get_dispatch()(arg0, …, trail, k)

    ``fname`` is resolved from the compiled function's globals, where it
    refers to either a PredicateMeta class or a _DbDispatchAdapter shim.
    """
    get_dispatch = ast.Call(
        func=ast.Attribute(value=_name(fname), attr="_get_dispatch"),
        args=[],
        keywords=[],
    )
    return ast.Call(
        func=get_dispatch,
        args=arg_exprs + [_name(trail_name), _name("k")],
        keywords=[],
    )


# ── Body star-list detection and compilation (Phase 5) ────────────────────────


def _is_star_list(term: Any) -> bool:
    """Return True if term is a list containing at least one StarUnpack."""
    return isinstance(term, list) and any(isinstance(e, StarUnpack) for e in term)


def _parse_star_segments(lst: list) -> list[tuple]:
    """Parse a list with StarUnpack(s) into segments.

    Returns a list of ("fixed", [elem, ...]) or ("star", var) tuples.
    """
    segments: list[tuple] = []
    fixed_buf: list = []
    for elem in lst:
        if isinstance(elem, StarUnpack):
            if fixed_buf:
                segments.append(("fixed", fixed_buf))
                fixed_buf = []
            segments.append(("star", elem.value))
        else:
            fixed_buf.append(elem)
    if fixed_buf:
        segments.append(("fixed", fixed_buf))
    return segments


def _count_stars(segments: list[tuple]) -> int:
    return sum(1 for kind, _ in segments if kind == "star")


def _compile_star_is(
    star_side: list,
    other_side: Any,
    var_context: dict[int, str],
    trail_name: str,
    k_stmts: list[ast.stmt],
) -> list[ast.stmt]:
    """Compile an Is goal where one side contains a star-list pattern.

    Generates a call to a runtime helper that handles bidirectional
    star-list unification (both construction and deconstruction).
    """
    segments = _parse_star_segments(star_side)
    n_stars = _count_stars(segments)
    other_expr = term_to_ast_expr(other_side, var_context)

    if n_stars == 1:
        return _compile_single_star_is(segments, other_expr, var_context, trail_name, k_stmts)
    else:
        return _compile_multi_star_is(segments, other_expr, var_context, trail_name, k_stmts)


def _compile_single_star_is(
    segments: list[tuple],
    other_expr: ast.expr,
    var_context: dict[int, str],
    trail_name: str,
    k_stmts: list[ast.stmt],
) -> list[ast.stmt]:
    """Compile single-star body Is: emit call to _body_star_unify."""
    before_vals: list = []
    star_val = None
    after_vals: list = []
    past_star = False

    for kind, val in segments:
        if kind == "star":
            star_val = val
            past_star = True
        elif not past_star:
            before_vals.extend(val)
        else:
            after_vals.extend(val)

    before_exprs = [term_to_ast_expr(v, var_context) for v in before_vals]
    star_expr = term_to_ast_expr(star_val, var_context) if star_val is not None else ast.Constant(value=None)
    after_exprs = [term_to_ast_expr(v, var_context) for v in after_vals]

    mark = _fresh("_m")
    return [
        _assign_mark(mark, trail_name),
        _if(
            _call(
                _name("_body_star_unify"),
                other_expr,
                ast.List(elts=before_exprs, ctx=ast.Load()),
                star_expr,
                ast.List(elts=after_exprs, ctx=ast.Load()),
                _name(trail_name),
            ),
            k_stmts,
        ),
        _undo_stmt(mark, trail_name),
    ]


def _compile_multi_star_is(
    segments: list[tuple],
    other_expr: ast.expr,
    var_context: dict[int, str],
    trail_name: str,
    k_stmts: list[ast.stmt],
) -> list[ast.stmt]:
    """Compile multi-star body Is: emit for-loop over _body_multi_star_unify."""
    # Build segments as a runtime list of tuples
    seg_elts: list[ast.expr] = []
    for kind, val in segments:
        if kind == "fixed":
            elems = ast.List(
                elts=[term_to_ast_expr(v, var_context) for v in val],
                ctx=ast.Load(),
            )
            seg_elts.append(ast.Tuple(
                elts=[ast.Constant(value="fixed"), elems],
                ctx=ast.Load(),
            ))
        else:  # star
            seg_elts.append(ast.Tuple(
                elts=[ast.Constant(value="star"), term_to_ast_expr(val, var_context)],
                ctx=ast.Load(),
            ))

    segments_expr = ast.List(elts=seg_elts, ctx=ast.Load())

    return [
        ast.For(
            target=_name("_", ast.Store()),
            iter=_call(
                _name("_body_multi_star_unify"),
                other_expr,
                segments_expr,
                _name(trail_name),
            ),
            body=k_stmts or [ast.Pass()],
            orelse=[],
        ),
    ]


# ── compile_goal ───────────────────────────────────────────────────────────────


def compile_goal(
    goal: Any,
    db: Database,
    var_context: dict[int, str],
    trail_name: str,
    k_stmts: list[ast.stmt],
) -> list[ast.stmt]:
    """Compile a goal term into Python statements.

    On success, executes k_stmts (the inlined continuation).
    On failure, does nothing (falls through without executing k_stmts).

    Parameters
    ----------
    goal       : goal term (Is, And, Or, Call, True, False, …)
    db         : live database — used for predicate dispatch and signature lookup
    var_context: mutable Var._id → python_name dict; extended for body-only Vars
    trail_name : name of the trail parameter in the enclosing compiled function
    k_stmts    : continuation statements to inline on success
    """
    goal = deref(goal)

    # Booleans — must be tested before isinstance(term, int) in the general path
    if goal is True:
        return list(k_stmts)
    if goal is False:
        return []

    match goal:

        # ── Unification ─────────────────────────────────────────────────────
        case Is(left=l, right=r):
            # Phase 5: detect star-list patterns in body Is goals
            if _is_star_list(l):
                return _compile_star_is(l, r, var_context, trail_name, k_stmts)
            if _is_star_list(r):
                return _compile_star_is(r, l, var_context, trail_name, k_stmts)
            mark = _fresh("_m")
            l_expr = term_to_ast_expr(l, var_context)
            r_expr = term_to_ast_expr(r, var_context)
            return [
                _assign_mark(mark, trail_name),
                _if(_call(_name("unify"), l_expr, r_expr, _name(trail_name)), k_stmts),
                _undo_stmt(mark, trail_name),
            ]

        # ── Dif (negation of unification) ─────────────────────────────────
        case IsNot(left=l, right=r):
            # Succeed iff l and r cannot unify right now.
            # Try to unify; if it succeeds, undo and fail.
            # If it fails, proceed with k_stmts.
            mark = _fresh("_m")
            l_expr = term_to_ast_expr(l, var_context)
            r_expr = term_to_ast_expr(r, var_context)
            return [
                _assign_mark(mark, trail_name),
                ast.If(
                    test=ast.UnaryOp(
                        op=ast.Not(),
                        operand=_call(_name("unify"), l_expr, r_expr, _name(trail_name)),
                    ),
                    body=k_stmts,
                    orelse=[],
                ),
                _undo_stmt(mark, trail_name),
            ]

        # ── Structural equality ──────────────────────────────────────────────
        case Eq(left=l, right=r):
            return _deref_cmp(l, r, ast.Eq(), var_context, k_stmts)

        case NotEq(left=l, right=r):
            return _deref_cmp(l, r, ast.NotEq(), var_context, k_stmts)

        # ── Arithmetic comparisons ───────────────────────────────────────────
        case Lt(left=l, right=r):
            return _compile_arith_cmp(l, r, ast.Lt(), var_context, k_stmts)

        case LtE(left=l, right=r):
            return _compile_arith_cmp(l, r, ast.LtE(), var_context, k_stmts)

        case Gt(left=l, right=r):
            return _compile_arith_cmp(l, r, ast.Gt(), var_context, k_stmts)

        case GtE(left=l, right=r):
            return _compile_arith_cmp(l, r, ast.GtE(), var_context, k_stmts)

        # ── Conjunction ──────────────────────────────────────────────────────
        case And(left=l, right=r):
            # Build right-to-left: r's stmts become k for l
            inner_k = compile_goal(r, db, var_context, trail_name, k_stmts)
            return compile_goal(l, db, var_context, trail_name, inner_k)

        # ── Disjunction ──────────────────────────────────────────────────────
        case Or(left=l, right=r):
            mark = _fresh("_m")
            left_stmts = compile_goal(l, db, var_context, trail_name, k_stmts)
            right_stmts = compile_goal(r, db, var_context, trail_name, k_stmts)
            # Note: both branches share var_context; body-only vars in Or
            # branches that differ between branches are a known POC limitation.
            return [
                _assign_mark(mark, trail_name),
                *left_stmts,
                _undo_stmt(mark, trail_name),
                _assign_mark(mark, trail_name),
                *right_stmts,
                _undo_stmt(mark, trail_name),
            ]

        # ── Negation-as-failure ──────────────────────────────────────────────
        case Not(operand=inner):
            # Run inner as a sub-generator; succeed iff it yields no solutions.
            # Bindings from the inner goal do not escape (the nested function
            # closes over trail, and we use a fresh mark to undo any accidental
            # bindings that the sub-generator leaves before failing).
            naf_gen = _fresh("_naf_gen")
            naf_flag = _fresh("_naf")
            inner_stmts = compile_goal(inner, db, var_context, trail_name, [_yield_none_stmt()])
            # Always append ``return; yield`` so the NAF function is a generator
            # type even when inner_stmts is empty (e.g. inner goal is False).
            # The dead ``yield`` after ``return`` is the standard Python trick.
            naf_body = inner_stmts + [
                ast.Return(value=ast.Constant(value=None)),
                ast.Expr(value=ast.Yield(value=ast.Constant(value=None))),
            ]
            naf_fn = ast.FunctionDef(
                name=naf_gen,
                args=ast.arguments(
                    posonlyargs=[], args=[], vararg=None,
                    kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[],
                ),
                body=naf_body,
                decorator_list=[], returns=None, type_comment=None,
                **_EXTRA_FUNCDEF,
            )
            naf_mark = _fresh("_m")
            return [
                naf_fn,
                _assign(naf_flag, ast.Constant(value=True)),
                _assign_mark(naf_mark, trail_name),
                ast.For(
                    target=_name("_", ast.Store()),
                    iter=_call(_name(naf_gen)),
                    body=[
                        _assign(naf_flag, ast.Constant(value=False)),
                        ast.Break(),
                    ],
                    orelse=[],
                ),
                _undo_stmt(naf_mark, trail_name),
                _if(_name(naf_flag), k_stmts),
            ]

        # ── Membership / enumeration ─────────────────────────────────────────
        case In(left=elem, right=collection):
            loop_var = _fresh("_el")
            mark = _fresh("_m")
            elem_expr = term_to_ast_expr(elem, var_context)
            coll_expr = term_to_ast_expr(collection, var_context)
            return [
                ast.For(
                    target=_name(loop_var, ast.Store()),
                    iter=_call(_name("deref"), coll_expr),
                    body=[
                        _assign_mark(mark, trail_name),
                        _if(
                            _call(_name("unify"), elem_expr, _name(loop_var), _name(trail_name)),
                            k_stmts,
                        ),
                        _undo_stmt(mark, trail_name),
                    ],
                    orelse=[],
                )
            ]

        # ── Non-membership ───────────────────────────────────────────────────
        case NotIn(left=elem, right=collection):
            found_flag = _fresh("_found")
            loop_var = _fresh("_el")
            mark = _fresh("_m")
            elem_expr = term_to_ast_expr(elem, var_context)
            coll_expr = term_to_ast_expr(collection, var_context)
            return [
                _assign(found_flag, ast.Constant(value=False)),
                ast.For(
                    target=_name(loop_var, ast.Store()),
                    iter=_call(_name("deref"), coll_expr),
                    body=[
                        _assign_mark(mark, trail_name),
                        ast.If(
                            test=_call(_name("unify"), elem_expr, _name(loop_var), _name(trail_name)),
                            body=[
                                _assign(found_flag, ast.Constant(value=True)),
                                _undo_stmt(mark, trail_name),
                                ast.Break(),
                            ],
                            orelse=[_undo_stmt(mark, trail_name)],
                        ),
                    ],
                    orelse=[],
                ),
                _if(ast.UnaryOp(op=ast.Not(), operand=_name(found_flag)), k_stmts),
            ]

        # ── CLP(FD) stub ─────────────────────────────────────────────────────
        case ArithConstraint():
            raise NotImplementedError(
                "CLP(FD) arithmetic constraints (==+) are not yet implemented"
            )

        # ── Compile-time-known predicate call ────────────────────────────────
        case Call(func=LoadName(name=fname), args=call_args, kwargs=call_kwargs):
            return _compile_predicate_call(
                fname, call_args, call_kwargs, db, var_context, trail_name, k_stmts
            )

        case Call():
            raise NotImplementedError(
                f"compile_goal: cannot compile Call with non-LoadName func: {goal.func!r}"
            )

        case _:
            raise NotImplementedError(
                f"compile_goal: unsupported goal type {type(goal).__name__}: {goal!r}"
            )


def _compile_predicate_call(
    fname: str,
    call_args: list,
    call_kwargs: list,   # list of Keyword nodes from the term
    db: Database,
    var_context: dict[int, str],
    trail_name: str,
    k_stmts: list[ast.stmt],
) -> list[ast.stmt]:
    """Compile a call to a named predicate.

    WK-4: When kwargs are present, look up the predicate's signature in the
    database and reorder keyword args to positional order.  Raises RuntimeError
    if no signature is registered.
    """
    from clausal.pythonic_ast.nodes import Keyword as KWNode

    n_pos = len(call_args)
    arity = n_pos + len(call_kwargs)

    ordered_args: list = list(call_args)
    if call_kwargs:
        sig = db.signature_for(fname, arity)
        if sig is None:
            raise RuntimeError(
                f"No signature registered for {fname}/{arity}; "
                "cannot compile keyword call without a signature"
            )
        kw_dict = {kw.name: kw.value for kw in call_kwargs if isinstance(kw, KWNode)}
        for param_name in sig[n_pos:]:
            if param_name not in kw_dict:
                raise RuntimeError(
                    f"Missing argument {param_name!r} in keyword call to {fname}/{arity}"
                )
            ordered_args.append(kw_dict[param_name])

    arg_exprs = [term_to_ast_expr(a, var_context) for a in ordered_args]
    iter_expr = _dispatch_call_iter(fname, arity, arg_exprs, trail_name)
    return [
        ast.For(
            target=_name("_", ast.Store()),
            iter=iter_expr,
            body=k_stmts or [ast.Pass()],
            orelse=[],
        )
    ]


# ── compile_body ───────────────────────────────────────────────────────────────


def compile_body(
    goals: list,
    db: Database,
    var_context: dict[int, str],
    trail_name: str,
) -> list[ast.stmt]:
    """Compile a flat list of goals as a conjunction.

    The leaf continuation is ``yield None`` (one solution).
    Goals are processed right-to-left so each wraps the next as its k_stmts.

    Body-only Vars (variables that appear in the body but not the head) are
    pre-allocated via ``_preallocate_body_vars`` so that they are registered
    in ``var_context`` as named locals before right-to-left compilation begins.
    This prevents UnboundLocalError when an outer goal references a Var that
    would otherwise only be walrus-introduced inside a later (inner) goal.
    """
    alloc_stmts = _preallocate_body_vars(goals, var_context)
    k: list[ast.stmt] = [_yield_none_stmt()]
    for goal in reversed(goals):
        k = compile_goal(goal, db, var_context, trail_name, k)
    return alloc_stmts + k


def _make_body_compiler(db: Database) -> Callable[[Clause, dict[int, str]], list[ast.stmt]]:
    """Return a body_compiler callable bound to db."""
    def _body_compiler(clause: Clause, var_context: dict[int, str]) -> list[ast.stmt]:
        return compile_body(clause.body, db, var_context, "trail")
    return _body_compiler


# ── Trampoline Step-protocol compilation ───────────────────────────────────────
#
# DONE sentinel: yielded as Step(parent, DONE) when a predicate generator has
# exhausted all clauses.  The calling generator receives DONE as the value of
# its ``_st = yield Step(child, None)`` expression and exits its while loop.
#
DONE: object = object()


# ── AST helpers for Step yields ────────────────────────────────────────────────


def _step_expr(gen_expr: ast.expr, value_expr: ast.expr) -> ast.expr:
    """Generate AST for: Step(gen_expr, value_expr)"""
    return _call(_name("Step"), gen_expr, value_expr)


def _yield_step_stmt(gen_expr: ast.expr, value_expr: ast.expr) -> ast.stmt:
    """Generate AST for statement: yield Step(gen_expr, value_expr)"""
    return ast.Expr(value=ast.Yield(value=_step_expr(gen_expr, value_expr)))


def _assign_yield_step(
    target: str, gen_expr: ast.expr, value_expr: ast.expr
) -> ast.stmt:
    """Generate AST for: target = (yield Step(gen_expr, value_expr))

    The yielded Step tells the trampoline to (re)start gen_expr.  When
    gen_expr next yields Step(back_to_us, v), the trampoline sends v here
    and target is bound to v.
    """
    return _assign(target, ast.Yield(value=_step_expr(gen_expr, value_expr)))


def _dispatch_call_trampoline(
    fname: str,
    arity: int,
    arg_exprs: list[ast.expr],
    trail_name: str,
    self_name: str,
) -> ast.expr:
    """Generate: fname._get_dispatch()(self, arg0, …, trail)

    ``fname`` is resolved from the compiled function's globals.
    ``self`` is passed as ``parent`` so the child generator knows who to
    Step back to when it finds a solution.
    """
    get_dispatch = ast.Call(
        func=ast.Attribute(value=_name(fname), attr="_get_dispatch"),
        args=[],
        keywords=[],
    )
    return ast.Call(
        func=get_dispatch,
        args=[_name(self_name)] + arg_exprs + [_name(trail_name)],
        keywords=[],
    )


# ── compile_goal_trampoline ────────────────────────────────────────────────────


def compile_goal_trampoline(
    goal: Any,
    db: Database,
    var_context: dict[int, str],
    trail_name: str,
    k_stmts: list[ast.stmt],
    self_name: str = "self",
    parent_name: str = "parent",
) -> list[ast.stmt]:
    """Compile a goal using the trampoline Step protocol.

    Identical to ``compile_goal`` for deterministic goals (Is, Eq, comparisons,
    And, Or, Not, In, NotIn).  Differs for predicate ``Call`` nodes: instead of

        for _ in dispatch(args, trail, k): k_stmts

    it generates the stack-safe coroutine pattern::

        _gen  = dispatch(self, args, trail)        # child generator
        _st   = (yield Step(_gen, None))           # start child; get solution or DONE
        while _st is not _DONE:
            <k_stmts>                              # continuation (ends with yield Step(parent,None))
            _st = (yield Step(_gen, None))         # ask child for next solution

    ``k_stmts`` for the innermost goal must be
    ``[yield Step(parent, None)]`` — use ``compile_body_trampoline`` to build
    these correctly from the inside out.

    Note: ``Not`` (NAF) compiles its inner goal with ``compile_goal`` (simple
    mode) so the inner check runs via a local for loop.  NAF inner goals must
    therefore be simple-compiled predicates or primitive goals.
    """
    goal = deref(goal)

    if goal is True:
        return list(k_stmts)
    if goal is False:
        return []

    match goal:

        # ── Deterministic goals — identical to simple mode ───────────────────
        case Is(left=l, right=r):
            # Phase 5: detect star-list patterns in body Is goals
            if _is_star_list(l):
                return _compile_star_is(l, r, var_context, trail_name, k_stmts)
            if _is_star_list(r):
                return _compile_star_is(r, l, var_context, trail_name, k_stmts)
            mark = _fresh("_m")
            l_expr = term_to_ast_expr(l, var_context)
            r_expr = term_to_ast_expr(r, var_context)
            return [
                _assign_mark(mark, trail_name),
                _if(_call(_name("unify"), l_expr, r_expr, _name(trail_name)), k_stmts),
                _undo_stmt(mark, trail_name),
            ]

        case IsNot(left=l, right=r):
            mark = _fresh("_m")
            l_expr = term_to_ast_expr(l, var_context)
            r_expr = term_to_ast_expr(r, var_context)
            return [
                _assign_mark(mark, trail_name),
                ast.If(
                    test=ast.UnaryOp(
                        op=ast.Not(),
                        operand=_call(_name("unify"), l_expr, r_expr, _name(trail_name)),
                    ),
                    body=k_stmts,
                    orelse=[],
                ),
                _undo_stmt(mark, trail_name),
            ]

        case Eq(left=l, right=r):
            return _deref_cmp(l, r, ast.Eq(), var_context, k_stmts)

        case NotEq(left=l, right=r):
            return _deref_cmp(l, r, ast.NotEq(), var_context, k_stmts)

        case Lt(left=l, right=r):
            return _compile_arith_cmp(l, r, ast.Lt(), var_context, k_stmts)

        case LtE(left=l, right=r):
            return _compile_arith_cmp(l, r, ast.LtE(), var_context, k_stmts)

        case Gt(left=l, right=r):
            return _compile_arith_cmp(l, r, ast.Gt(), var_context, k_stmts)

        case GtE(left=l, right=r):
            return _compile_arith_cmp(l, r, ast.GtE(), var_context, k_stmts)

        # ── Conjunction ──────────────────────────────────────────────────────
        case And(left=l, right=r):
            inner_k = compile_goal_trampoline(
                r, db, var_context, trail_name, k_stmts, self_name, parent_name
            )
            return compile_goal_trampoline(
                l, db, var_context, trail_name, inner_k, self_name, parent_name
            )

        # ── Disjunction ──────────────────────────────────────────────────────
        case Or(left=l, right=r):
            mark = _fresh("_m")
            left_stmts = compile_goal_trampoline(
                l, db, var_context, trail_name, k_stmts, self_name, parent_name
            )
            right_stmts = compile_goal_trampoline(
                r, db, var_context, trail_name, k_stmts, self_name, parent_name
            )
            return [
                _assign_mark(mark, trail_name),
                *left_stmts,
                _undo_stmt(mark, trail_name),
                _assign_mark(mark, trail_name),
                *right_stmts,
                _undo_stmt(mark, trail_name),
            ]

        # ── Negation-as-failure ──────────────────────────────────────────────
        # Inner goal uses simple mode (local for-loop check; no deep recursion).
        # The trampoline outer function has no ``k`` parameter, so inject
        # ``k = None`` into the inner generator's local scope so that any
        # simple-mode predicate calls inside the inner stmts can pass it.
        case Not(operand=inner):
            naf_gen = _fresh("_naf_gen")
            naf_flag = _fresh("_naf")
            inner_stmts = compile_goal(inner, db, var_context, trail_name, [_yield_none_stmt()])
            k_none_stmt = _assign("k", ast.Constant(None))
            # Always append ``return; yield`` so NAF function is a generator type.
            naf_body = [k_none_stmt] + inner_stmts + [
                ast.Return(value=ast.Constant(value=None)),
                ast.Expr(value=ast.Yield(value=ast.Constant(value=None))),
            ]
            naf_fn = ast.FunctionDef(
                name=naf_gen,
                args=ast.arguments(
                    posonlyargs=[], args=[], vararg=None,
                    kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[],
                ),
                body=naf_body,
                decorator_list=[], returns=None, type_comment=None,
                **_EXTRA_FUNCDEF,
            )
            naf_mark = _fresh("_m")
            return [
                naf_fn,
                _assign(naf_flag, ast.Constant(value=True)),
                _assign_mark(naf_mark, trail_name),
                ast.For(
                    target=_name("_", ast.Store()),
                    iter=_call(_name(naf_gen)),
                    body=[
                        _assign(naf_flag, ast.Constant(value=False)),
                        ast.Break(),
                    ],
                    orelse=[],
                ),
                _undo_stmt(naf_mark, trail_name),
                _if(_name(naf_flag), k_stmts),
            ]

        # ── Membership / enumeration (Python for-loop, safe) ─────────────────
        case In(left=elem, right=collection):
            loop_var = _fresh("_el")
            mark = _fresh("_m")
            elem_expr = term_to_ast_expr(elem, var_context)
            coll_expr = term_to_ast_expr(collection, var_context)
            return [
                ast.For(
                    target=_name(loop_var, ast.Store()),
                    iter=_call(_name("deref"), coll_expr),
                    body=[
                        _assign_mark(mark, trail_name),
                        _if(
                            _call(_name("unify"), elem_expr, _name(loop_var), _name(trail_name)),
                            k_stmts,
                        ),
                        _undo_stmt(mark, trail_name),
                    ],
                    orelse=[],
                )
            ]

        # ── Non-membership ───────────────────────────────────────────────────
        case NotIn(left=elem, right=collection):
            found_flag = _fresh("_found")
            loop_var = _fresh("_el")
            mark = _fresh("_m")
            elem_expr = term_to_ast_expr(elem, var_context)
            coll_expr = term_to_ast_expr(collection, var_context)
            return [
                _assign(found_flag, ast.Constant(value=False)),
                ast.For(
                    target=_name(loop_var, ast.Store()),
                    iter=_call(_name("deref"), coll_expr),
                    body=[
                        _assign_mark(mark, trail_name),
                        ast.If(
                            test=_call(_name("unify"), elem_expr, _name(loop_var), _name(trail_name)),
                            body=[
                                _assign(found_flag, ast.Constant(value=True)),
                                _undo_stmt(mark, trail_name),
                                ast.Break(),
                            ],
                            orelse=[_undo_stmt(mark, trail_name)],
                        ),
                    ],
                    orelse=[],
                ),
                _if(ast.UnaryOp(op=ast.Not(), operand=_name(found_flag)), k_stmts),
            ]

        case ArithConstraint():
            raise NotImplementedError(
                "CLP(FD) arithmetic constraints (==+) are not yet implemented"
            )

        # ── Stack-safe predicate call ─────────────────────────────────────────
        case Call(func=LoadName(name=fname), args=call_args, kwargs=call_kwargs):
            return _compile_predicate_call_trampoline(
                fname, call_args, call_kwargs, db, var_context,
                trail_name, k_stmts, self_name,
            )

        case Call():
            raise NotImplementedError(
                f"compile_goal_trampoline: cannot compile Call with non-LoadName func: {goal.func!r}"
            )

        case _:
            raise NotImplementedError(
                f"compile_goal_trampoline: unsupported goal type {type(goal).__name__}: {goal!r}"
            )


def _compile_predicate_call_trampoline(
    fname: str,
    call_args: list,
    call_kwargs: list,
    db: Database,
    var_context: dict[int, str],
    trail_name: str,
    k_stmts: list[ast.stmt],
    self_name: str,
) -> list[ast.stmt]:
    """Trampoline variant of _compile_predicate_call.

    Generates the coroutine-backtracking pattern::

        _gen_N  = dispatch(self, arg0, …, trail)
        _st_N   = (yield Step(_gen_N, None))
        while _st_N is not _DONE:
            <k_stmts>
            _st_N = (yield Step(_gen_N, None))

    When ``_gen_N`` yields ``Step(self, None)`` (solution found), the
    trampoline sends ``None`` to ``self`` so ``_st_N`` gets ``None`` (not
    DONE) and the while body runs.  When ``_gen_N`` yields
    ``Step(self, DONE)`` (exhausted), ``_st_N`` gets ``DONE`` and the
    while loop exits.

    WK-4 keyword normalisation is applied identically to the simple variant.
    """
    from clausal.pythonic_ast.nodes import Keyword as KWNode

    n_pos = len(call_args)
    arity = n_pos + len(call_kwargs)

    ordered_args: list = list(call_args)
    if call_kwargs:
        sig = db.signature_for(fname, arity)
        if sig is None:
            raise RuntimeError(
                f"No signature registered for {fname}/{arity}; "
                "cannot compile keyword call without a signature"
            )
        kw_dict = {kw.name: kw.value for kw in call_kwargs if isinstance(kw, KWNode)}
        for param_name in sig[n_pos:]:
            if param_name not in kw_dict:
                raise RuntimeError(
                    f"Missing argument {param_name!r} in keyword call to {fname}/{arity}"
                )
            ordered_args.append(kw_dict[param_name])

    arg_exprs = [term_to_ast_expr(a, var_context) for a in ordered_args]
    gen_name = _fresh("_gen")
    status_name = _fresh("_st")

    call_expr = _dispatch_call_trampoline(fname, arity, arg_exprs, trail_name, self_name)

    # _gen_N = dispatch(self, arg0, …, trail)
    gen_assign = _assign(gen_name, call_expr)

    # _st_N = (yield Step(_gen_N, None))
    first_step = _assign_yield_step(status_name, _name(gen_name), ast.Constant(None))

    # while _st_N is not _DONE: k_stmts; _st_N = (yield Step(_gen_N, None))
    loop_body = (k_stmts or [ast.Pass()]) + [
        _assign_yield_step(status_name, _name(gen_name), ast.Constant(None))
    ]
    loop = ast.While(
        test=ast.Compare(
            left=_name(status_name),
            ops=[ast.IsNot()],
            comparators=[_name("_DONE")],
        ),
        body=loop_body,
        orelse=[],
    )
    return [gen_assign, first_step, loop]


# ── compile_body_trampoline ────────────────────────────────────────────────────


def compile_body_trampoline(
    goals: list,
    db: Database,
    var_context: dict[int, str],
    trail_name: str,
    parent_name: str = "parent",
    self_name: str = "self",
) -> list[ast.stmt]:
    """Compile a flat list of goals as a conjunction using the Step protocol.

    The leaf continuation is ``yield Step(parent, None)`` — one solution
    surfaced to the calling generator.

    Builds right-to-left: each goal wraps the next as its k_stmts, ending
    with the leaf.  Body-only Vars are pre-allocated (same fix as compile_body).
    """
    alloc_stmts = _preallocate_body_vars(goals, var_context)
    k: list[ast.stmt] = [_yield_step_stmt(_name(parent_name), ast.Constant(None))]
    for goal in reversed(goals):
        k = compile_goal_trampoline(goal, db, var_context, trail_name, k, self_name, parent_name)
    return alloc_stmts + k


def _make_body_compiler_trampoline(
    db: Database,
) -> Callable[[Clause, dict[int, str]], list[ast.stmt]]:
    """Return a trampoline body_compiler callable bound to db."""
    def _body_compiler(clause: Clause, var_context: dict[int, str]) -> list[ast.stmt]:
        return compile_body_trampoline(clause.body, db, var_context, "trail")
    return _body_compiler


# ── compile_predicate_trampoline ───────────────────────────────────────────────


def _build_predicate_trampoline_funcdef(
    functor: str,
    arity: int,
    clauses: list[Clause],
    db: Database,
    body_compiler: Callable[[Clause, dict[int, str]], list[ast.stmt]],
) -> ast.FunctionDef:
    """Build the ``ast.FunctionDef`` for a trampoline-protocol compiled predicate.

    Returns the fixed-up FunctionDef without executing it.  Used by both
    ``compile_predicate_trampoline`` and ``compile_predicate_trampoline_ast``.
    """
    arg_names = [f"arg{i}" for i in range(arity)]
    params = ["parent"] + arg_names + ["trail"]

    bootstrap = ast.Assign(
        targets=[_name("self", ast.Store())],
        value=ast.Yield(value=None),
        lineno=0, col_offset=0,
    )
    all_stmts: list[ast.stmt] = [bootstrap]

    for clause in clauses:
        var_context: dict[int, str] = {}
        _head_arg_patterns(clause.head, var_context, arity)
        body_stmts = body_compiler(clause, var_context)
        case_arm = compile_head_to_match_case(
            head=clause.head,
            body_stmts=body_stmts,
            var_context=var_context,
            arity=arity,
        )
        subject = ast.Tuple(
            elts=[_call(_name("deref"), _name(n)) for n in arg_names],
            ctx=ast.Load(),
        )
        all_stmts.append(ast.Match(subject=subject, cases=[case_arm]))

    all_stmts.append(_yield_step_stmt(_name("parent"), _name("_DONE")))

    func_name = f"{functor}__{arity}"
    func_def = ast.FunctionDef(
        name=func_name,
        args=ast.arguments(
            posonlyargs=[],
            args=[ast.arg(arg=p) for p in params],
            vararg=None,
            kwonlyargs=[],
            kw_defaults=[],
            kwarg=None,
            defaults=[],
        ),
        body=all_stmts,
        decorator_list=[],
        returns=None,
        type_comment=None,
        **_EXTRA_FUNCDEF,
    )
    ast.fix_missing_locations(func_def)
    return func_def


def compile_predicate_trampoline(
    functor: str,
    arity: int,
    clauses: list[Clause],
    db: "Database | None" = None,
    body_compiler: Callable[[Clause, dict[int, str]], list[ast.stmt]] | None = None,
    globals_: dict | None = None,
    pred_cls: "PredicateMeta | None" = None,
) -> Callable:
    """Compile all clauses into a trampoline Step-protocol immortal coroutine.

    Unlike ``compile_predicate`` (simple/short-stack), the generated function:

    - Takes ``parent`` as first argument — the generator to Step back to.
    - Opens with ``self = yield`` — the trampoline's bootstrap hook; ``self``
      receives the generator's own reference so it can pass itself as
      ``parent`` to child generators.
    - At each solution: ``yield Step(parent, None)`` — suspends; the calling
      generator (via the trampoline) processes the solution, then resumes
      this generator to find more.
    - After all clauses exhausted: ``yield Step(parent, _DONE)`` — signals
      end of search for this predicate.

    Sub-predicate calls within clause bodies use the coroutine-backtracking
    pattern::

        _gen  = dispatch(self, args, trail)
        _st   = (yield Step(_gen, None))
        while _st is not _DONE:
            <continuation>
            _st = (yield Step(_gen, None))

    so the Python call stack does *not* grow with predicate recursion depth.

    Compiled function signature::

        def {functor}__{arity}(parent, arg0, …, argN, trail):
            self = yield   # bootstrap hook
            …              # clause match arms
            yield Step(parent, _DONE)

    The trampoline (``clausal.logic.trampoline.trampoline``) drives execution.
    ``continuation_search.Search`` (Step 7) will provide the ``__iter__``
    interface over solutions.
    """
    _effective_db = db if db is not None else _GlobalsDb(globals_ or {})

    if body_compiler is None:
        body_compiler = _make_body_compiler_trampoline(_effective_db)

    # Resolve pred_cls: explicit param > globals_ > auto-detect later.
    if pred_cls is None:
        pred_cls = (globals_ or {}).get(functor)
        if not isinstance(pred_cls, PredicateMeta):
            pred_cls = None

    if not clauses:
        fn = _compile_always_fail_trampoline(functor, arity)
        _install(db, functor, arity, fn, pred_cls=pred_cls)
        return fn

    func_def = _build_predicate_trampoline_funcdef(functor, arity, clauses, _effective_db, body_compiler)

    from clausal.terms import KWTerm as _KWTerm_t  # noqa: PLC0415
    base_globals: dict = {
        "Compound": Compound,
        "KWTerm": _KWTerm_t,
        "Var": Var,
        "unify": unify,
        "deref": deref,
        "is_var": is_var,
        "Step": Step,
        "_DONE": DONE,
        "_head_list_unify_input": _head_list_unify_input,
        "_head_list_unify_output": _head_list_unify_output,
        "_head_multi_star_error": _head_multi_star_error,
        "_body_star_unify": _body_star_unify,
        "_body_multi_star_unify": _body_multi_star_unify,
    }
    base_globals.update(_collect_head_types(clauses))
    if globals_:
        base_globals.update(globals_)
    _inject_call_targets(clauses, base_globals, db, globals_)

    if pred_cls is None:
        pred_cls = base_globals.get(functor)
        if not isinstance(pred_cls, PredicateMeta):
            pred_cls = None

    fn = functiondef_to_function(func_def, globals_=base_globals)

    def _recompile_trampoline() -> Callable:
        if db is not None:
            next_clauses = db.clauses_for(functor, arity)
        else:
            next_clauses = pred_cls._clauses if pred_cls is not None else clauses
        return compile_predicate_trampoline(
            functor, arity, next_clauses, db,
            body_compiler=body_compiler, globals_=globals_, pred_cls=pred_cls,
        )

    _install(db, functor, arity, fn, lazy_recompile=_recompile_trampoline, pred_cls=pred_cls)
    return fn


def compile_predicate_trampoline_ast(
    functor: str,
    arity: int,
    clauses: list[Clause],
    db: Database,
    body_compiler: Callable[[Clause, dict[int, str]], list[ast.stmt]] | None = None,
) -> ast.FunctionDef:
    """Return the ``ast.FunctionDef`` for a trampoline-mode compiled predicate.

    Identical to ``compile_predicate_trampoline`` but returns the AST node
    instead of executing it.  Does *not* install anything in the database.
    """
    if body_compiler is None:
        body_compiler = _make_body_compiler_trampoline(db)
    if not clauses:
        arg_names = [f"arg{i}" for i in range(arity)]
        params = ["parent"] + arg_names + ["trail"]
        func_def = ast.FunctionDef(
            name=f"{functor}__{arity}",
            args=ast.arguments(
                posonlyargs=[], args=[ast.arg(arg=p) for p in params],
                vararg=None, kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[],
            ),
            body=[
                ast.Assign(
                    targets=[_name("self", ast.Store())],
                    value=ast.Yield(value=None),
                    lineno=0, col_offset=0,
                ),
                _yield_step_stmt(_name("parent"), _name("_DONE")),
            ],
            decorator_list=[], returns=None, type_comment=None, **_EXTRA_FUNCDEF,
        )
        ast.fix_missing_locations(func_def)
        return func_def
    return _build_predicate_trampoline_funcdef(functor, arity, clauses, db, body_compiler)


def _compile_always_fail_trampoline(functor: str, arity: int) -> Callable:
    """Trampoline variant: generator that immediately yields Step(parent, DONE)."""
    arg_names = [f"arg{i}" for i in range(arity)]
    params = ["parent"] + arg_names + ["trail"]
    func_name = f"{functor}__{arity}"
    func_def = ast.FunctionDef(
        name=func_name,
        args=ast.arguments(
            posonlyargs=[],
            args=[ast.arg(arg=p) for p in params],
            vararg=None,
            kwonlyargs=[],
            kw_defaults=[],
            kwarg=None,
            defaults=[],
        ),
        body=[
            ast.Assign(
                targets=[_name("self", ast.Store())],
                value=ast.Yield(value=None),
                lineno=0, col_offset=0,
            ),
            _yield_step_stmt(_name("parent"), _name("_DONE")),
        ],
        decorator_list=[],
        returns=None,
        type_comment=None,
        **_EXTRA_FUNCDEF,
    )
    ast.fix_missing_locations(func_def)
    return functiondef_to_function(func_def, globals_={"Step": Step, "_DONE": DONE})


def _wrap_yields_with_output_guards(
    stmts: list[ast.stmt], replacement_stmts: list[ast.stmt]
) -> list[ast.stmt]:
    """Replace every ``yield None`` in *stmts* with *replacement_stmts*.

    Walks the AST statement list recursively.  Any ``Expr(Yield(None))``
    found is replaced by the *replacement_stmts* (which should contain
    guarded yields).

    If *replacement_stmts* is empty, returns *stmts* unchanged.
    """
    if not replacement_stmts:
        return stmts

    def _is_yield_none(stmt: ast.stmt) -> bool:
        return (
            isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Yield)
            and (stmt.value.value is None
                 or (isinstance(stmt.value.value, ast.Constant)
                     and stmt.value.value.value is None))
        )

    def _walk_stmts(ss: list[ast.stmt]) -> list[ast.stmt]:
        result: list[ast.stmt] = []
        for s in ss:
            if _is_yield_none(s):
                result.extend(replacement_stmts)
            else:
                result.append(_walk_stmt(s))
        return result

    def _walk_stmt(s: ast.stmt) -> ast.stmt:
        if isinstance(s, ast.If):
            s.body = _walk_stmts(s.body)
            s.orelse = _walk_stmts(s.orelse)
        elif isinstance(s, ast.For):
            s.body = _walk_stmts(s.body)
            s.orelse = _walk_stmts(s.orelse)
        elif isinstance(s, ast.While):
            s.body = _walk_stmts(s.body)
            s.orelse = _walk_stmts(s.orelse)
        elif isinstance(s, ast.Try):
            s.body = _walk_stmts(s.body)
            for h in s.handlers:
                h.body = _walk_stmts(h.body)
            s.orelse = _walk_stmts(s.orelse)
            s.finalbody = _walk_stmts(s.finalbody)
        elif isinstance(s, ast.With):
            s.body = _walk_stmts(s.body)
        return s

    return _walk_stmts(stmts)


# ── head_to_match_pattern ──────────────────────────────────────────────────────


def head_to_match_pattern(
    term: Any,
    var_context: dict[int, str],
    dup_guards: list[tuple[str, str]] | None = None,
    list_guards: list[tuple] | None = None,
    _list_reg_ids: set[int] | None = None,
) -> ast.pattern:
    """Convert a head field value to a Python ``ast.pattern`` node.

    Parameters
    ----------
    term:        value from a clause head (may be a Var, literal, dataclass, …)
    var_context: mutable dict mapping ``Var._id`` → Python local variable name.
                 Unbound Vars are registered here on first encounter.

    Pattern mapping
    ---------------
    Var (unbound)          → ``MatchAs(name="_v{id}")`` — captures the arg
    Var (bound)            → recurse after dereferencing
    None / True / False    → ``MatchSingleton``
    int, float, str, bytes → ``MatchValue(Constant(value))``
    complex                → ``MatchValue(Constant(value))``
    list                   → ``MatchSequence`` of sub-patterns
    Compound(f, args)      → ``MatchClass(Compound, functor=f, args=...)``
    functor dataclass      → ``MatchClass(cls, kwd field patterns)``
    other                  → ``MatchAs(name=None)``  (wildcard ``_``)
    """
    term = deref(term)

    # Unbound Var → MatchAs to capture the incoming argument
    # Repeated Var (already in var_context) → fresh dup name + unification guard
    if is_var(term):
        vid = term._id
        if vid in var_context:
            # Duplicate occurrence — generate a unique dup name
            orig_name = var_context[vid]
            dup_name = f"{orig_name}__dup{len(dup_guards) if dup_guards is not None else 0}"
            if dup_guards is not None:
                dup_guards.append((orig_name, dup_name))
            return ast.MatchAs(pattern=None, name=dup_name)
        name = _var_python_name(term)
        var_context[vid] = name
        # This Var is registered as a DIRECT match capture (not a list element).
        # _list_reg_ids tracks list-registered Vars; absence means direct capture.
        return ast.MatchAs(pattern=None, name=name)

    # Python singletons
    if term is None or term is True or term is False:
        return ast.MatchSingleton(value=term)

    # Python scalar literals
    if isinstance(term, (int, float, str, bytes, complex)):
        return ast.MatchValue(value=ast.Constant(value=term))

    # Python list → wildcard capture + _head_list_unify guard
    # This handles both input (destructuring) and output (construction) modes.
    if isinstance(term, list):
        # Parse list into segments: alternating fixed elements and stars
        segments: list[tuple[str, Any]] = []  # ("fixed", [elems]) or ("star", var)
        current_fixed: list[Any] = []
        star_count = 0
        for e in term:
            if isinstance(e, StarUnpack):
                star_count += 1
                if current_fixed:
                    segments.append(("fixed", current_fixed))
                    current_fixed = []
                segments.append(("star", deref(e.value)))
            else:
                current_fixed.append(deref(e))
        if current_fixed:
            segments.append(("fixed", current_fixed))

        # Collect all vars from segments for registration
        all_vars: list[Any] = []
        for seg_type, seg_val in segments:
            if seg_type == "fixed":
                all_vars.extend(seg_val)
            else:
                all_vars.append(seg_val)

        # Register vars from list elements into var_context.
        # Three cases for a Var v inside this list:
        #   (a) New Var: register normally, mark as list-registered in _list_reg_ids.
        #   (b) Already registered from a PREVIOUS LIST: same name, no dup needed
        #       (both list guards share the pre-allocated Var).
        #   (c) Already registered as a DIRECT MATCH CAPTURE (not in _list_reg_ids):
        #       generate a dup name + dup_guard so the match-captured value is
        #       compared against the list-element Var after unification.
        list_elem_vc: dict[int, str] = {}  # name overrides for this list's elements
        for v in all_vars:
            if not is_var(v):
                continue
            if v._id in var_context:
                if v._id not in list_elem_vc:
                    # is_direct_capture: True only when _list_reg_ids is provided
                    # (meaning compile_head_to_match_case called us) AND the var
                    # was registered by the direct Var branch (not a list branch).
                    is_direct_capture = (
                        _list_reg_ids is not None and v._id not in _list_reg_ids
                    )
                    if is_direct_capture:
                        # Case (c): direct match capture — need dup name
                        orig_name = var_context[v._id]
                        n_dups = len(dup_guards) if dup_guards is not None else 0
                        dup_name = f"{orig_name}__dup{n_dups}"
                        if dup_guards is not None:
                            dup_guards.append((orig_name, dup_name))
                        list_elem_vc[v._id] = dup_name
                    else:
                        # Case (b): already list-allocated or _list_reg_ids not
                        # provided (legacy call) — reuse same name
                        list_elem_vc[v._id] = var_context[v._id]
            else:
                # Case (a): new Var — register and mark as list-allocated
                name = _var_python_name(v)
                var_context[v._id] = name
                if _list_reg_ids is not None:
                    _list_reg_ids.add(v._id)
                list_elem_vc[v._id] = name
        # Build a var_context snapshot for this list guard using the element vc.
        guard_vc = dict(var_context)
        guard_vc.update(list_elem_vc)
        # Generate a capture name and record the list guard
        cap_name = f"_lcap{len(list_guards) if list_guards is not None else 0}"
        if list_guards is not None:
            if star_count > 1:
                # Multi-star: store segments format with "multi" tag
                list_guards.append((cap_name, segments, guard_vc, "multi"))
            else:
                # Single-star: existing (before, star, after) format
                before: list[Any] = []
                star: Any = None
                after: list[Any] = []
                in_after = False
                for seg_type, seg_val in segments:
                    if seg_type == "star":
                        star = seg_val
                        in_after = True
                    elif in_after:
                        after.extend(seg_val)
                    else:
                        before.extend(seg_val)
                list_guards.append((cap_name, before, star, after, guard_vc))
        return ast.MatchAs(pattern=None, name=cap_name)

    # Compound(functor, args) → MatchClass on Compound
    if isinstance(term, Compound):
        f = term.functor
        if is_var(f):
            # Variable functor: cannot match statically → wildcard
            return ast.MatchAs(pattern=None, name=None)
        sub_patterns = [head_to_match_pattern(a, var_context, dup_guards, list_guards, _list_reg_ids) for a in term.args]
        return ast.MatchClass(
            cls=_name("Compound"),
            patterns=[],
            kwd_attrs=["functor", "args"],
            kwd_patterns=[
                ast.MatchValue(value=ast.Constant(value=f)),
                ast.MatchSequence(patterns=sub_patterns),
            ],
        )

    # Functor term instance → MatchClass with field patterns
    if is_term_instance(term):
        cls_name = type(term).__name__
        fields = term_field_names(term)
        return ast.MatchClass(
            cls=_name(cls_name),
            patterns=[],
            kwd_attrs=list(fields),
            kwd_patterns=[
                head_to_match_pattern(getattr(term, name), var_context, dup_guards, list_guards, _list_reg_ids)
                for name in fields
            ],
        )

    # Fallback: wildcard (accept anything, no binding)
    return ast.MatchAs(pattern=None, name=None)


# ── Multi-star list guard compilation ──────────────────────────────────────────


def _compile_multi_star_guard(
    cap_name: str,
    segments: list[tuple[str, Any]],
    vc: dict[int, str],
    trail_name: str,
    body_stmts: list[ast.stmt],
) -> list[ast.stmt]:
    """Compile a multi-star list pattern into nested splitting loops.

    Generates code like::

        _d0 = deref(_lcap0)
        if is_var(_d0):
            _head_multi_star_error()
        if isinstance(_d0, list):
            _n0 = len(_d0)
            if _n0 >= <min_len>:
                for _sp0 in range(...):
                    ...nested loops...
                        _mmark0 = trail.mark()
                        if (unify(...) and unify(...) and ...):
                            <body_stmts>
                        trail.undo(_mmark0)
    """
    def _var_or_const_expr(elem):
        if is_var(elem) and elem._id in vc:
            return _name(vc[elem._id])
        return ast.Constant(value=elem)

    # Count fixed elements and stars
    star_vars: list[Any] = []  # star Var objects in order
    fixed_counts: list[int] = []  # fixed-elem count per fixed segment
    fixed_segments: list[list[Any]] = []  # fixed elem lists
    for seg_type, seg_val in segments:
        if seg_type == "star":
            star_vars.append(seg_val)
        else:
            fixed_counts.append(len(seg_val))
            fixed_segments.append(seg_val)

    n_stars = len(star_vars)
    min_len = sum(fixed_counts)
    d_name = f"_msd{cap_name}"  # deref'd list local
    n_name = f"_msn{cap_name}"  # len local

    # Build the unify chain and loops from inside out.
    # Strategy: enumerate lengths assigned to each star var.
    # The last star's length is determined (remaining elements).
    # For k stars we need k-1 loop variables.

    # Compute the position-to-slice mapping for each segment.
    # pos tracks current position in the list as an AST expression.
    # We build the innermost body first, then wrap with loops.

    # The innermost body: mark + unify chain + body + undo
    mark_name = f"_mmark{cap_name}"

    # Build unify chain: for each segment, unify the var/elements with the slice
    # We'll represent positions as expressions relative to split vars.
    # split var names: _sp0, _sp1, ... (k-1 of them)
    sp_names = [f"_msp{cap_name}_{i}" for i in range(n_stars - 1)]

    # Position tracking: we walk segments left-to-right building slice exprs.
    # pos_expr: AST expression for current position in the list.
    # We accumulate position as: start=0, then add fixed-segment lengths and
    # star-var lengths (star lengths are sp_names[i] for first k-1, remainder for last).
    unify_calls: list[ast.expr] = []
    # Track position as components to sum: list of (constant_offset, [sp_name, ...])
    pos_const = 0  # constant part of current position
    pos_sp: list[str] = []  # split-var names added to position so far
    star_idx = 0
    fixed_idx = 0

    def _pos_expr():
        """Build AST expr for current position."""
        parts: list[ast.expr] = []
        if pos_const:
            parts.append(ast.Constant(value=pos_const))
        parts.extend(_name(sp) for sp in pos_sp)
        if not parts:
            return ast.Constant(value=0)
        if len(parts) == 1:
            return parts[0]
        result = parts[0]
        for p in parts[1:]:
            result = ast.BinOp(left=result, op=ast.Add(), right=p)
        return result

    for seg_type, seg_val in segments:
        if seg_type == "fixed":
            # Unify each fixed element with list[pos], list[pos+1], ...
            for j, elem in enumerate(seg_val):
                idx_expr = _pos_expr()
                if j > 0:
                    idx_expr = ast.BinOp(
                        left=idx_expr, op=ast.Add(),
                        right=ast.Constant(value=j),
                    )
                subscript = ast.Subscript(
                    value=_name(d_name), slice=idx_expr, ctx=ast.Load(),
                )
                unify_calls.append(
                    _call(_name("unify"), _var_or_const_expr(elem), subscript, _name(trail_name))
                )
            pos_const += len(seg_val)
        else:
            # Star segment: slice from pos to pos+length
            star_var = seg_val
            start_expr = _pos_expr()
            if star_idx < n_stars - 1:
                # Length is sp_names[star_idx]
                end_parts: list[ast.expr] = [_pos_expr()]
                end_parts.append(_name(sp_names[star_idx]))
                end_expr = end_parts[0]
                for p in end_parts[1:]:
                    end_expr = ast.BinOp(left=end_expr, op=ast.Add(), right=p)
                pos_sp.append(sp_names[star_idx])
            else:
                # Last star: takes everything remaining up to len - trailing fixed
                trailing_fixed = 0
                # Count fixed elements in segments after this star
                found_last_star = False
                for st, sv in segments:
                    if found_last_star and st == "fixed":
                        trailing_fixed += len(sv)
                    if st == "star" and sv is star_var:
                        found_last_star = True
                if trailing_fixed:
                    end_expr = ast.BinOp(
                        left=_name(n_name), op=ast.Sub(),
                        right=ast.Constant(value=trailing_fixed),
                    )
                else:
                    end_expr = _name(n_name)

            slice_expr = ast.Subscript(
                value=_name(d_name),
                slice=ast.Slice(lower=start_expr, upper=end_expr),
                ctx=ast.Load(),
            )
            unify_calls.append(
                _call(
                    _name("unify"),
                    _var_or_const_expr(star_var),
                    slice_expr,
                    _name(trail_name),
                )
            )
            if star_idx < n_stars - 1:
                pass  # pos_sp already updated above
            else:
                # For trailing fixed segments after last star, update pos
                pos_const = 0
                pos_sp = []
                # pos is now end_expr + ... but we don't need it (no more segments
                # that need position tracking — if there are trailing fixed elems,
                # they were already counted above)
            star_idx += 1

    # Build the if-unify chain
    if len(unify_calls) == 1:
        unify_cond = unify_calls[0]
    else:
        unify_cond = ast.BoolOp(op=ast.And(), values=unify_calls)

    innermost = [
        _assign_mark(mark_name, trail_name),
        ast.If(test=unify_cond, body=body_stmts, orelse=[]),
        _undo_stmt(mark_name, trail_name),
    ]

    # Wrap with nested for-loops (inside-out, from last split var to first)
    # Each sp_names[i] ranges from 0 to (remaining - sum of later splits)
    # remaining = _n - min_len - sum of earlier splits
    current = innermost
    for i in range(n_stars - 2, -1, -1):
        # upper bound for sp_names[i]:
        # remaining after fixed and earlier splits = _n - min_len - sp0 - sp1 - ... - sp(i-1)
        # but also need to leave room for later splits (which can be 0), so upper is:
        # _n - min_len - sum(sp[0..i-1]) + 1
        upper_parts: list[ast.expr] = [
            ast.BinOp(
                left=_name(n_name), op=ast.Sub(),
                right=ast.Constant(value=min_len),
            )
        ]
        for j in range(i):
            upper_parts.append(_name(sp_names[j]))
        # Also subtract later split vars (they take the remainder)
        # For k splits (k-1 loop vars), sp[i] can range from 0 to
        # (remaining - sum_of_later_sps). But later sps are inner loops.
        # Actually: sp[i] + sp[i+1] + ... + sp[k-2] + last_star_len = remaining - sum(sp[0..i-1])
        # And each later sp and last_star can be >= 0, so sp[i] <= remaining - sum(sp[0..i-1]) - (n_stars-1-i-1)*0
        # Wait, no: remaining = n - min_len. sp[0] + sp[1] + ... + sp[k-2] + last_star_len = remaining
        # For sp[i]: upper = remaining - sp[0] - ... - sp[i-1] - sp[i+1] - ... - sp[k-2]
        # But sp[i+1]...sp[k-2] are inner loops that can be 0, and last_star = remaining - all sps >= 0
        # So sp[i] <= remaining - sp[0] - ... - sp[i-1] - 0 - ... - 0
        # upper = remaining - sum(sp[0..i-1]) + 1  (range is exclusive)
        # remaining = n - min_len
        # So upper = n - min_len - sum(sp[0..i-1]) + 1

        # sp[i] ranges from 0 to (remaining - sum(sp[0..i-1])) inclusive.
        # Later splits (sp[i+1]...) are inner loops that can be 0, so they
        # don't constrain the upper bound of sp[i].
        remaining_expr: ast.expr = ast.BinOp(
            left=_name(n_name), op=ast.Sub(),
            right=ast.Constant(value=min_len),
        )
        for j in range(i):
            remaining_expr = ast.BinOp(
                left=remaining_expr, op=ast.Sub(),
                right=_name(sp_names[j]),
            )
        upper_expr = ast.BinOp(
            left=remaining_expr, op=ast.Add(),
            right=ast.Constant(value=1),
        )

        current = [ast.For(
            target=_name(sp_names[i], ast.Store()),
            iter=_call(_name("range"), upper_expr),
            body=current,
            orelse=[],
        )]

    # Wrap with: if isinstance(_d, list) and len >= min_len
    len_check = ast.Compare(
        left=_name(n_name),
        ops=[ast.GtE()],
        comparators=[ast.Constant(value=min_len)],
    )
    guarded = [ast.If(test=len_check, body=current, orelse=[])]

    # _n = len(_d)
    len_assign = _assign(n_name, _call(_name("len"), _name(d_name)))

    # isinstance check
    isinstance_check = _call(
        _name("isinstance"), _name(d_name),
        _name("list"),
    )

    # if is_var(_d): _head_multi_star_error()
    var_check = ast.If(
        test=_call(_name("is_var"), _name(d_name)),
        body=[ast.Expr(value=_call(_name("_head_multi_star_error")))],
        orelse=[],
    )

    list_branch = ast.If(
        test=isinstance_check,
        body=[len_assign] + guarded,
        orelse=[],
    )

    # _d = deref(_lcap)
    deref_assign = _assign(d_name, _call(_name("deref"), _name(cap_name)))

    return [deref_assign, var_check, list_branch]


# ── compile_head_to_match_case ─────────────────────────────────────────────────


def compile_head_to_match_case(
    head: Any,
    body_stmts: list[ast.stmt],
    var_context: dict[int, str],
    arity: int,
    trail_name: str = "trail",
    mark_name: str = "_mark",
) -> ast.match_case:
    """Compile a clause head into one ``match_case`` arm.

    Parameters
    ----------
    head:        head term (functor dataclass or Compound)
    body_stmts:  pre-compiled body statements (from compile_body or a placeholder)
    var_context: mutable dict; Var._id → python_name mappings are added here
    arity:       expected number of arguments (len of head's fields/args)
    trail_name:  name of the trail parameter in the enclosing function
    mark_name:   name for the trail mark local variable

    Generated structure::

        case (<per-arg patterns…>,):
            _mark = trail.mark()
            try:
                <body_stmts>
            finally:
                trail.undo(_mark)
    """
    dup_guards: list[tuple[str, str]] = []
    list_guards: list[tuple] = []
    # Use a fresh context for head pattern generation so that repeated vars
    # within a single head are correctly detected (the caller's var_context
    # may already contain vars from a pre-collection pass).
    head_var_ctx: dict[int, str] = {}
    # _list_reg_ids tracks Var IDs registered via list-element branches (not direct
    # match captures).  A Var appearing in multiple list patterns reuses the same
    # pre-allocated name; a Var that was first registered as a direct match capture
    # and then appears in a list gets a dup name to avoid overwriting the capture.
    _list_reg_ids: set[int] = set()
    arg_patterns = _head_arg_patterns(head, head_var_ctx, arity, dup_guards, list_guards, _list_reg_ids)
    var_context.update(head_var_ctx)
    outer_pattern = ast.MatchSequence(patterns=arg_patterns)

    # _mark = trail.mark()
    mark_assign = ast.Assign(
        targets=[_name(mark_name, ast.Store())],
        value=_call(_attr(trail_name, "mark")),
        lineno=0,
        col_offset=0,
    )

    # trail.undo(_mark)
    undo_stmt = ast.Expr(value=_call(_attr(trail_name, "undo"), _name(mark_name)))

    # Wrap body_stmts with dup-var unification guards (innermost first)
    inner = body_stmts if body_stmts else [ast.Pass()]
    for orig_name, dup_name in reversed(dup_guards):
        # if unify(orig, dup, trail): <inner>
        inner = [ast.If(
            test=_call(
                _name("unify"),
                _name(orig_name),
                _name(dup_name),
                _name(trail_name),
            ),
            body=inner,
            orelse=[],
        )]

    # Emit list guards: input destructuring + deferred output construction
    if list_guards:
        # Separate single-star and multi-star guards
        single_star_guards = [g for g in list_guards if len(g) == 5]
        multi_star_guards = [g for g in list_guards if len(g) == 4]

        # Pre-allocate Var() for list-pattern vars (not captured by match pattern)
        list_var_allocs: list[ast.stmt] = []
        _alloc_seen: set[str] = set()
        for guard in list_guards:
            if len(guard) == 5:
                _cap_name, _before, _star, _after, _vc = guard
                elems = _before + ([_star] if _star is not None else []) + _after
            else:
                _cap_name, _segments, _vc, _ = guard
                elems = []
                for seg_type, seg_val in _segments:
                    if seg_type == "fixed":
                        elems.extend(seg_val)
                    else:
                        elems.append(seg_val)
            for elem in elems:
                if is_var(elem) and elem._id in _vc:
                    vname = _vc[elem._id]
                    if vname not in _alloc_seen:
                        _alloc_seen.add(vname)
                        list_var_allocs.append(_assign(vname, _call(_name("Var"))))

        # ── Single-star guards (existing path) ────────────────────────────
        if single_star_guards:
            def _list_guard_args(cap_name, before, star, after, vc):
                """Build AST expressions for _head_list_unify_* call args."""
                def _var_or_const(elem):
                    if is_var(elem) and elem._id in vc:
                        return _name(vc[elem._id])
                    return ast.Constant(value=elem)
                before_list = ast.List(elts=[_var_or_const(e) for e in before], ctx=ast.Load())
                if star is not None and is_var(star) and star._id in vc:
                    star_expr = _name(vc[star._id])
                else:
                    star_expr = ast.Constant(value=None)
                after_list = ast.List(elts=[_var_or_const(e) for e in after], ctx=ast.Load())
                return (_name(cap_name), before_list, star_expr, after_list, _name(trail_name))

            input_check_stmts: list[ast.stmt] = []
            lr_names: list[str] = []
            all_guard_args: list[tuple] = []
            for i, (cap_name, before, star, after, _vc) in enumerate(single_star_guards):
                lr_name = f"_lr{i}"
                lr_names.append(lr_name)
                args = _list_guard_args(cap_name, before, star, after, _vc)
                all_guard_args.append(args)
                input_check_stmts.append(
                    _assign(lr_name, _call(_name("_head_list_unify_input"), *args))
                )

            gate_tests = []
            for lr_name in lr_names:
                gate_tests.append(ast.Compare(
                    left=_name(lr_name),
                    ops=[ast.IsNot()],
                    comparators=[ast.Constant(value=False)],
                ))
            if len(gate_tests) == 1:
                gate_cond = gate_tests[0]
            else:
                gate_cond = ast.BoolOp(op=ast.And(), values=gate_tests)

            output_conditions: list[ast.expr] = []
            for i, lr_name in enumerate(lr_names):
                args = all_guard_args[i]
                output_conditions.append(ast.BoolOp(
                    op=ast.Or(),
                    values=[
                        ast.Compare(
                            left=_name(lr_name),
                            ops=[ast.IsNot()],
                            comparators=[ast.Constant(value=None)],
                        ),
                        _call(_name("_head_list_unify_output"), *args),
                    ],
                ))
            if len(output_conditions) == 1:
                output_cond = output_conditions[0]
            else:
                output_cond = ast.BoolOp(op=ast.And(), values=output_conditions)

            output_guard_stmts = [ast.If(
                test=output_cond,
                body=[ast.Expr(value=ast.Yield(value=None))],
                orelse=[],
            )]
            inner = _wrap_yields_with_output_guards(inner, output_guard_stmts)

            gated_inner = [ast.If(test=gate_cond, body=inner, orelse=[])]
            inner = input_check_stmts + gated_inner

        # ── Multi-star guards ─────────────────────────────────────────────
        for ms_guard in multi_star_guards:
            cap_name, segments, vc, _ = ms_guard
            inner = _compile_multi_star_guard(
                cap_name, segments, vc, trail_name, inner,
            )

        inner = list_var_allocs + inner

    try_finally = ast.Try(
        body=inner,
        handlers=[],
        orelse=[],
        finalbody=[undo_stmt],
    )

    return ast.match_case(
        pattern=outer_pattern,
        guard=None,
        body=[mark_assign, try_finally],
    )


def _head_arg_patterns(
    head: Any, var_context: dict[int, str], arity: int,
    dup_guards: list[tuple[str, str]] | None = None,
    list_guards: list[tuple] | None = None,
    _list_reg_ids: set[int] | None = None,
) -> list[ast.pattern]:
    """Extract per-argument patterns from a head term."""
    def _pat(term):
        return head_to_match_pattern(term, var_context, dup_guards, list_guards, _list_reg_ids)
    if isinstance(head, Compound):
        return [_pat(a) for a in head.args]
    # Call(func=LoadName(f), args=[...]) — e.g. from $assert_fact with trailing comma.
    # Extract patterns from the positional args, not from the Call dataclass fields.
    if isinstance(head, Call) and isinstance(head.func, LoadName):
        return [_pat(a) for a in head.args]
    if is_term_instance(head):
        return [_pat(getattr(head, name)) for name in term_field_names(head)]
    # Fallback: arity wildcards (accept any args)
    return [ast.MatchAs(pattern=None, name=None) for _ in range(arity)]


# ── compile_predicate ─────────────────────────────────────────────────────────

# Python 3.12+ added type_params to FunctionDef
_EXTRA_FUNCDEF: dict = (
    {"type_params": []} if "type_params" in ast.FunctionDef._fields else {}
)


def _build_predicate_funcdef(
    functor: str,
    arity: int,
    clauses: list[Clause],
    db: Database,
    body_compiler: Callable[[Clause, dict[int, str]], list[ast.stmt]],
) -> ast.FunctionDef:
    """Build the ``ast.FunctionDef`` for a simple/short-stack compiled predicate.

    Returns the fixed-up FunctionDef without executing it.  Used by both
    ``compile_predicate`` (which then calls ``functiondef_to_function``) and
    ``compile_predicate_ast`` (which returns the FunctionDef directly).
    """
    arg_names = [f"arg{i}" for i in range(arity)]
    params = arg_names + ["trail", "k"]

    all_stmts: list[ast.stmt] = []

    for clause in clauses:
        var_context: dict[int, str] = {}
        _head_arg_patterns(clause.head, var_context, arity)
        body_stmts = body_compiler(clause, var_context)
        case_arm = compile_head_to_match_case(
            head=clause.head,
            body_stmts=body_stmts,
            var_context=var_context,
            arity=arity,
        )
        subject = ast.Tuple(
            elts=[_call(_name("deref"), _name(n)) for n in arg_names],
            ctx=ast.Load(),
        )
        all_stmts.append(ast.Match(subject=subject, cases=[case_arm]))

    func_name = f"{functor}__{arity}"
    func_def = ast.FunctionDef(
        name=func_name,
        args=ast.arguments(
            posonlyargs=[],
            args=[ast.arg(arg=p) for p in params],
            vararg=None,
            kwonlyargs=[],
            kw_defaults=[],
            kwarg=None,
            defaults=[],
        ),
        body=all_stmts,
        decorator_list=[],
        returns=None,
        type_comment=None,
        **_EXTRA_FUNCDEF,
    )
    ast.fix_missing_locations(func_def)
    return func_def


def compile_predicate(
    functor: str,
    arity: int,
    clauses: list[Clause],
    db: "Database | None" = None,
    body_compiler: Callable[[Clause, dict[int, str]], list[ast.stmt]] | None = None,
    globals_: dict | None = None,
    pred_cls: "PredicateMeta | None" = None,
) -> Callable:
    """Compile all clauses of a predicate into a dispatch generator function.

    Each clause becomes one ``match`` block in the generated function.
    Clauses are tried in order; when a head matches, the body runs.
    The generator yields one value per solution (via the body).

    Parameters
    ----------
    functor:       predicate name (used for the function name)
    arity:         predicate arity
    clauses:       all current clauses for this predicate
    db:            the database; used for dispatch lookup and signature registry.
                   Optional — when None, signature lookup falls back to globals_.
    body_compiler: optional callable(clause, var_context) → list[ast.stmt].
                   Defaults to the Step-5 body compiler (compile_body via db).
    globals_:      additional names injected into the compiled function scope.
                   ``Compound``, ``Var``, ``unify``, ``deref``, and predicate
                   class references are always included automatically.
    pred_cls:      explicit PredicateMeta class to install the compiled dispatch
                   on.  If not provided, detected from base_globals by name.

    The compiled function signature is::

        def {functor}__{arity}(arg0, …, argN, trail, k):
            …

    ``k`` is reserved for the Step-7 CPS trampoline; the Step-5 body always
    ends with ``yield None`` regardless of ``k``.

    Returns the compiled callable.  Also installs it on the PredicateMeta class
    (and via ``db.set_dispatch()`` if db is provided) so subsequent
    ``_get_dispatch()`` / ``db.get_dispatch()`` calls work.
    """
    # Choose the effective db for body compilation (may be a no-db proxy).
    _effective_db = db if db is not None else _GlobalsDb(globals_ or {})

    if body_compiler is None:
        body_compiler = _make_body_compiler(_effective_db)

    # Resolve pred_cls: explicit param > globals_ > auto-detect later.
    if pred_cls is None:
        pred_cls = (globals_ or {}).get(functor)
        if not isinstance(pred_cls, PredicateMeta):
            pred_cls = None

    if not clauses:
        fn = _compile_always_fail(functor, arity)
        _install(db, functor, arity, fn, pred_cls=pred_cls)
        return fn

    func_def = _build_predicate_funcdef(functor, arity, clauses, _effective_db, body_compiler)

    from clausal.terms import KWTerm as _KWTerm  # noqa: PLC0415
    base_globals: dict = {
        "Compound": Compound,
        "KWTerm": _KWTerm,
        "Var": Var,
        "unify": unify,
        "deref": deref,
        "is_var": is_var,
        "_head_list_unify_input": _head_list_unify_input,
        "_head_list_unify_output": _head_list_unify_output,
        "_head_multi_star_error": _head_multi_star_error,
        "_body_star_unify": _body_star_unify,
        "_body_multi_star_unify": _body_multi_star_unify,
    }
    base_globals.update(_collect_head_types(clauses))
    if globals_:
        base_globals.update(globals_)
    _inject_call_targets(clauses, base_globals, db, globals_)

    # Resolve Predicate class — explicit param > globals_ > _collect_head_types.
    if pred_cls is None:
        pred_cls = base_globals.get(functor)
        if not isinstance(pred_cls, PredicateMeta):
            pred_cls = None

    fn = functiondef_to_function(func_def, globals_=base_globals)

    def _recompile_simple() -> Callable:
        if db is not None:
            next_clauses = db.clauses_for(functor, arity)
        else:
            next_clauses = pred_cls._clauses if pred_cls is not None else clauses
        return compile_predicate(
            functor, arity, next_clauses, db,
            body_compiler=body_compiler, globals_=globals_, pred_cls=pred_cls,
        )

    _install(db, functor, arity, fn, lazy_recompile=_recompile_simple, pred_cls=pred_cls)
    return fn


def compile_predicate_ast(
    functor: str,
    arity: int,
    clauses: list[Clause],
    db: Database,
    body_compiler: Callable[[Clause, dict[int, str]], list[ast.stmt]] | None = None,
) -> ast.FunctionDef:
    """Return the ``ast.FunctionDef`` for a simple-mode compiled predicate.

    Identical to ``compile_predicate`` but returns the AST node instead of
    executing it.  Useful for inspecting or pretty-printing generated code.
    Does *not* install anything in the database.
    """
    if body_compiler is None:
        body_compiler = _make_body_compiler(db)
    if not clauses:
        arg_names = [f"arg{i}" for i in range(arity)]
        params = arg_names + ["trail", "k"]
        return ast.FunctionDef(
            name=f"{functor}__{arity}",
            args=ast.arguments(
                posonlyargs=[], args=[ast.arg(arg=p) for p in params],
                vararg=None, kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[],
            ),
            body=[ast.Return(value=ast.Constant(value=None)),
                  ast.Expr(value=ast.Yield(value=ast.Constant(value=None)))],
            decorator_list=[], returns=None, type_comment=None, **_EXTRA_FUNCDEF,
        )
    return _build_predicate_funcdef(functor, arity, clauses, db, body_compiler)


def _stub_body_stmts() -> list[ast.stmt]:
    """Placeholder body: succeed once by yielding None."""
    return [ast.Expr(value=ast.Yield(value=ast.Constant(value=None)))]


def _compile_always_fail(functor: str, arity: int) -> Callable:
    """Return a generator function that matches any args but never yields."""
    arg_names = [f"arg{i}" for i in range(arity)]
    params = arg_names + ["trail", "k"]
    func_name = f"{functor}__{arity}"
    func_def = ast.FunctionDef(
        name=func_name,
        args=ast.arguments(
            posonlyargs=[],
            args=[ast.arg(arg=p) for p in params],
            vararg=None,
            kwonlyargs=[],
            kw_defaults=[],
            kwarg=None,
            defaults=[],
        ),
        # return; yield  →  generator that stops immediately
        body=[
            ast.Return(value=ast.Constant(value=None)),
            ast.Expr(value=ast.Yield(value=ast.Constant(value=None))),
        ],
        decorator_list=[],
        returns=None,
        type_comment=None,
        **_EXTRA_FUNCDEF,
    )
    ast.fix_missing_locations(func_def)
    return functiondef_to_function(func_def, globals_={})


def _install(
    db: "Database | None",
    functor: str,
    arity: int,
    fn: Callable,
    lazy_recompile: Callable | None = None,
    pred_cls: PredicateMeta | None = None,
) -> None:
    """Install fn as the compiled dispatch function.

    If ``db`` is provided, stores the dispatch fn via ``db.set_dispatch()``
    so that ``db.get_dispatch()`` works for test/non-PredicateMeta usage.

    If ``pred_cls`` is a PredicateMeta class, installs fn and lazy_recompile
    directly on the class so that ``pred_cls._get_dispatch()`` works.
    """
    if db is not None:
        db.set_dispatch(functor, arity, fn, lazy_recompile=lazy_recompile)
    if pred_cls is not None and isinstance(pred_cls, PredicateMeta):
        pred_cls._dispatch_fn = fn
        if lazy_recompile is not None:
            pred_cls._lazy_recompile = lazy_recompile


__all__ = [
    # Simple / short-stack compilation
    "compile_predicate",
    "compile_predicate_ast",
    "compile_goal",
    "compile_body",
    # Trampoline / stack-safe compilation
    "compile_predicate_trampoline",
    "compile_predicate_trampoline_ast",
    "compile_goal_trampoline",
    "compile_body_trampoline",
    "DONE",
    # Shared utilities
    "head_to_match_pattern",
    "compile_head_to_match_case",
    "term_to_ast_expr",
    "arith_to_ast_expr",
]
