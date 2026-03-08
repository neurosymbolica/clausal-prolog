"""clausal.logic.compiler — clause head → match arm compiler (Step 4).

Compiles Clause head terms into Python match/case patterns and assembles
them into a dispatch generator function per predicate.

Step 4 scope: head patterns only.  The body_compiler hook (Step 5) fills in
the body statements; until then a placeholder stub yields once on success.
"""

from __future__ import annotations

import ast
import dataclasses
from typing import Any, Callable

from clausal.logic.variables import Var, is_var, deref
from clausal.terms import Compound
from clausal.logic.database import Clause, Database
from clausal.codegen import functiondef_to_function


# ── Variable naming ────────────────────────────────────────────────────────────


def _var_python_name(var: Var) -> str:
    """Return a stable Python identifier for a logic variable from its _id."""
    return f"_v{var._id}"


# ── ast helpers ────────────────────────────────────────────────────────────────


def _name(id_: str, ctx=None) -> ast.Name:
    return ast.Name(id=id_, ctx=ctx or ast.Load())


def _attr(obj_name: str, attr: str) -> ast.Attribute:
    return ast.Attribute(value=_name(obj_name), attr=attr, ctx=ast.Load())


def _call(func: ast.expr, *args: ast.expr) -> ast.Call:
    return ast.Call(func=func, args=list(args), keywords=[])


# ── head_to_match_pattern ──────────────────────────────────────────────────────


def head_to_match_pattern(
    term: Any,
    var_context: dict[int, str],
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
    if is_var(term):
        name = _var_python_name(term)
        var_context[term._id] = name
        return ast.MatchAs(pattern=None, name=name)

    # Python singletons
    if term is None or term is True or term is False:
        return ast.MatchSingleton(value=term)

    # Python scalar literals
    if isinstance(term, (int, float, str, bytes, complex)):
        return ast.MatchValue(value=ast.Constant(value=term))

    # Python list → MatchSequence of sub-patterns
    if isinstance(term, list):
        return ast.MatchSequence(
            patterns=[head_to_match_pattern(e, var_context) for e in term]
        )

    # Compound(functor, args) → MatchClass on Compound
    if isinstance(term, Compound):
        f = term.functor
        if is_var(f):
            # Variable functor: cannot match statically → wildcard
            return ast.MatchAs(pattern=None, name=None)
        sub_patterns = [head_to_match_pattern(a, var_context) for a in term.args]
        return ast.MatchClass(
            cls=_name("Compound"),
            patterns=[],
            kwd_attrs=["functor", "args"],
            kwd_patterns=[
                ast.MatchValue(value=ast.Constant(value=f)),
                ast.MatchSequence(patterns=sub_patterns),
            ],
        )

    # Functor dataclass instance → MatchClass with field patterns
    if dataclasses.is_dataclass(term) and not isinstance(term, type):
        cls_name = type(term).__name__
        fields = dataclasses.fields(term)
        return ast.MatchClass(
            cls=_name(cls_name),
            patterns=[],
            kwd_attrs=[f.name for f in fields],
            kwd_patterns=[
                head_to_match_pattern(getattr(term, f.name), var_context)
                for f in fields
            ],
        )

    # Fallback: wildcard (accept anything, no binding)
    return ast.MatchAs(pattern=None, name=None)


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
    body_stmts:  pre-compiled body statements (from Step 5 or a placeholder)
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
    arg_patterns = _head_arg_patterns(head, var_context, arity)
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

    inner = body_stmts if body_stmts else [ast.Pass()]
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
    head: Any, var_context: dict[int, str], arity: int
) -> list[ast.pattern]:
    """Extract per-argument patterns from a head term."""
    if isinstance(head, Compound):
        return [head_to_match_pattern(a, var_context) for a in head.args]
    if dataclasses.is_dataclass(head) and not isinstance(head, type):
        return [
            head_to_match_pattern(getattr(head, f.name), var_context)
            for f in dataclasses.fields(head)
        ]
    # Fallback: arity wildcards (accept any args)
    return [ast.MatchAs(pattern=None, name=None) for _ in range(arity)]


# ── compile_predicate ─────────────────────────────────────────────────────────

# Python 3.12+ added type_params to FunctionDef
_EXTRA_FUNCDEF: dict = (
    {"type_params": []} if "type_params" in ast.FunctionDef._fields else {}
)


def compile_predicate(
    functor: str,
    arity: int,
    clauses: list[Clause],
    db: Database,
    body_compiler: Callable[[Clause, dict[int, str]], list[ast.stmt]] | None = None,
    globals_: dict | None = None,
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
    db:            the database; used to install the compiled function
    body_compiler: optional callable(clause, var_context) → list[ast.stmt].
                   If None, a stub body that yields once (succeeds) is used.
    globals_:      additional names injected into the compiled function scope.
                   ``Compound`` is always included automatically.

    Returns the compiled callable.  Also installs it on
    ``PredicateTable.dispatch_fn`` so subsequent ``get_dispatch()`` calls work.

    Function signature of the compiled predicate::

        def {functor}__{arity}(arg0, …, argN, trail, k):
            ...
    """
    if not clauses:
        fn = _compile_always_fail(functor, arity)
        _install(db, functor, arity, fn)
        return fn

    arg_names = [f"arg{i}" for i in range(arity)]
    params = arg_names + ["trail", "k"]

    all_stmts: list[ast.stmt] = []

    for clause in clauses:
        var_context: dict[int, str] = {}
        body_stmts = (
            body_compiler(clause, var_context)
            if body_compiler is not None
            else _stub_body_stmts()
        )
        case_arm = compile_head_to_match_case(
            head=clause.head,
            body_stmts=body_stmts,
            var_context=var_context,
            arity=arity,
        )
        subject = ast.Tuple(
            elts=[_name(n) for n in arg_names],
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

    base_globals: dict = {"Compound": Compound}
    if globals_:
        base_globals.update(globals_)

    fn = functiondef_to_function(func_def, globals_=base_globals)
    _install(db, functor, arity, fn)
    return fn


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


def _install(db: Database, functor: str, arity: int, fn: Callable) -> None:
    """Install fn on PredicateTable.dispatch_fn if the table exists."""
    table = db.table_for(functor, arity)
    if table is not None:
        table.dispatch_fn = fn


__all__ = [
    "head_to_match_pattern",
    "compile_head_to_match_case",
    "compile_predicate",
]
