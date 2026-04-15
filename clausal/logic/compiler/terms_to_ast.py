"""Term → AST expression lowering.

Converts a compile-time term value (Var, scalar, list, Compound,
functor-dataclass, KWTerm, DictTerm, SetTerm, SetLiteral, DictLiteral,
StarUnpack, TupleLiteral, Call-with-LoadName, PyThunk, …) into a
Python AST expression that, at runtime, reconstructs that term.

Also provides the small parsing helpers ``_is_star_list`` /
``_parse_star_segments`` / ``_count_stars`` (used both here for list
rewriting and by ``.star_segments`` for body-Is compilation) and
``_dotted_name_from_loadattr`` (used here and by ``.globals_env``).
Co-locating the parsing helpers with ``term_to_ast_expr`` avoids a
star_segments ↔ terms_to_ast import cycle.
"""

from __future__ import annotations

import ast
from fractions import Fraction
from typing import Any

from clausal.logic.variables import Var, is_var, deref  # noqa: F401
from clausal.terms import (
    Compound,
    Add, Sub, Mult, Div, FloorDiv, Mod, Pow,
    Negate,
    Call, LoadName, LoadAttr,
    DictTerm, SetTerm, KWTerm, PyThunk,
)
from clausal.pythonic_ast.nodes import (
    StarUnpack, TupleLiteral, DictLiteral, SetLiteral,
    Lambda, literal_value,
    SetLiteral as _SetLiteral_t,
)
from clausal.logic.predicate import (
    PredicateMeta, is_term_instance, term_field_names,
)

from ._ast_helpers import _name, _call
from ._vars import _var_python_name


# ── Parsing helpers (used here and by .star_segments) ────────────────────────


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


def _dotted_name_from_loadattr(node) -> str | None:
    """Extract a dotted name string from a LoadAttr chain.

    ``LoadAttr(object=LoadName("graphs"), attr="Path")`` → ``"graphs.Path"``
    ``LoadAttr(object=LoadAttr(..., "sub"), attr="Pred")`` → ``"mod.sub.Pred"``
    ``LoadName("foo")`` → ``"foo"``

    Returns None if the chain contains non-name nodes.
    """
    if isinstance(node, LoadName):
        return node.name
    if isinstance(node, LoadAttr):
        prefix = _dotted_name_from_loadattr(node.object)
        if prefix is not None:
            return f"{prefix}.{node.attr}"
    return None


# ── Term → AST expression ──────────────────────────────────────────────────────


def term_to_ast_expr(
    term: Any, var_context: dict[int, str], *, eval_arith: bool = True
) -> ast.expr:
    """Convert a term value to a Python AST expression.

    The generated expression evaluates at runtime to the term.
    Vars already in var_context are referenced by name.  Vars not yet in
    var_context (body-only Vars) are introduced via walrus ``(_vN := Var())``.

    when *eval_arith* is True (the default), arithmetic term nodes
    (Add, Sub, …) are compiled to native Python operators so they evaluate
    at runtime.  when False, they are kept as structural term constructors
    (e.g. ``Add(left=x, right=1)``).

    Supports: Var, Python scalars, list, Compound, functor dataclasses.
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

    if isinstance(term, LoadName):
        return _name(term.name)

    term = literal_value(term)
    if term is None or isinstance(term, bool):
        return ast.Constant(value=term)

    if isinstance(term, (int, float, str, bytes, complex)):
        return ast.Constant(value=term)

    if isinstance(term, StarUnpack):
        return ast.Starred(
            value=term_to_ast_expr(term.value, var_context, eval_arith=eval_arith),
            ctx=ast.Load(),
        )

    if isinstance(term, TupleLiteral):
        _rec = lambda t: term_to_ast_expr(t, var_context, eval_arith=eval_arith)
        return ast.Tuple(
            elts=[_rec(e) for e in term.elements],
            ctx=ast.Load(),
        )

    if isinstance(term, list):
        # If the list contains a StarUnpack, use _build_star_list/_build_multi_star_list
        # helper to safely handle unbound Vars at runtime.
        _rec = lambda t: term_to_ast_expr(t, var_context, eval_arith=eval_arith)
        star_count = sum(1 for e in term if isinstance(e, StarUnpack))
        if star_count == 1:
            # Single-star: use _build_star_list(before, star, after)
            star_idx = next(i for i, e in enumerate(term) if isinstance(e, StarUnpack))
            before = term[:star_idx]
            star_val = term[star_idx].value
            after = term[star_idx + 1:]
            return ast.Call(
                func=_name("_build_star_list"),
                args=[
                    ast.List(
                        elts=[_rec(e) for e in before],
                        ctx=ast.Load(),
                    ),
                    _rec(star_val),
                    ast.List(
                        elts=[_rec(e) for e in after],
                        ctx=ast.Load(),
                    ),
                ],
                keywords=[],
            )
        elif star_count > 1:
            # Multi-star: build segments list and call _build_multi_star_list
            segments = _parse_star_segments(term)
            seg_elts = []
            for kind, val in segments:
                if kind == "star":
                    seg_elts.append(ast.Tuple(
                        elts=[ast.Constant(value="star"), _rec(val)],
                        ctx=ast.Load(),
                    ))
                else:
                    seg_elts.append(ast.Tuple(
                        elts=[
                            ast.Constant(value="fixed"),
                            ast.List(elts=[_rec(e) for e in val], ctx=ast.Load()),
                        ],
                        ctx=ast.Load(),
                    ))
            return ast.Call(
                func=_name("_build_multi_star_list"),
                args=[ast.List(elts=seg_elts, ctx=ast.Load())],
                keywords=[],
            )
        return ast.List(
            elts=[_rec(e) for e in term],
            ctx=ast.Load(),
        )

    if isinstance(term, dict):
        return ast.Dict(
            keys=[term_to_ast_expr(k, var_context, eval_arith=eval_arith) for k in term.keys()],
            values=[term_to_ast_expr(v, var_context, eval_arith=eval_arith) for v in term.values()],
        )


    if isinstance(term, DictTerm):
        return _call(
            _name("DictTerm"),
            ast.Dict(
                keys=[term_to_ast_expr(k, var_context, eval_arith=eval_arith) for k in term.keys()],
                values=[term_to_ast_expr(v, var_context, eval_arith=eval_arith) for v in term.values()],
            ),
        )

    if isinstance(term, SetTerm):
        return _call(
            _name("SetTerm"),
            ast.List(
                elts=[ast.Constant(value=e) for e in sorted(term.elements, key=repr)],
                ctx=ast.Load(),
            ),
        )

    # SetLiteral (AST node from visit_Set): emit SetTerm([elem, ...]) constructor
    if isinstance(term, _SetLiteral_t):
        return _call(
            _name("SetTerm"),
            ast.List(
                elts=[term_to_ast_expr(e, var_context, eval_arith=eval_arith) for e in term.elements],
                ctx=ast.Load(),
            ),
        )

    if isinstance(term, DictLiteral):
        _rec = lambda t: term_to_ast_expr(t, var_context, eval_arith=eval_arith)
        has_splat = any(k is None for k in term.keys)
        if not has_splat:
            # No splats: plain dict used as DictTerm constructor argument.
            return ast.Dict(
                keys=[_rec(k) for k in term.keys],
                values=[_rec(v) for v in term.values],
            )
        # Splat dict sugar: {**OLD, k: v} → DictTerm({**deref(OLD).data, k: v})
        # Splat values are DictTerms; access .data to get the underlying dict.
        py_keys = []
        py_vals = []
        for k, v in zip(term.keys, term.values):
            if k is None:
                py_keys.append(None)
                py_vals.append(
                    ast.Attribute(
                        value=_call(_name("deref"), _rec(v)),
                        attr="data",
                        ctx=ast.Load(),
                    )
                )
            else:
                py_keys.append(_rec(k))
                py_vals.append(_rec(v))
        return _call(
            _name("DictTerm"),
            ast.Dict(keys=py_keys, values=py_vals),
        )

    if isinstance(term, SetLiteral):
        _rec = lambda t: term_to_ast_expr(t, var_context, eval_arith=eval_arith)
        return ast.Set(elts=[_rec(e) for e in term.elements])

    if isinstance(term, Compound):
        f = term.functor
        f_expr: ast.expr
        if is_var(f):
            vid = f._id
            f_expr = _name(var_context[vid]) if vid in var_context else _call(_name("Var"))
        else:
            f_expr = ast.Constant(value=f)
        args_elts = [term_to_ast_expr(a, var_context, eval_arith=eval_arith) for a in term.args]
        return _call(
            _name("Compound"),
            f_expr,
            ast.Tuple(elts=args_elts, ctx=ast.Load()),
        )

    # Arithmetic term nodes: when eval_arith is set, generate native Python
    # operators so they evaluate at runtime.  when False (e.g. predicate call
    # arguments), keep them as structural term constructors.
    if eval_arith and isinstance(term, (Add, Sub, Mult, Div, FloorDiv, Mod, Pow, Negate)):
        return arith_to_ast_expr(term, var_context)

    # Call nodes with LoadName/LoadAttr func: compile as direct function call so
    # that e.g. phrase(count_leaves(T_), ...) constructs a count_leaves instance,
    # not a Call AST node.  LoadAttr handles qualified calls like mod.Pred(X_).
    if isinstance(term, Call) and isinstance(term.func, (LoadName, LoadAttr)):
        if isinstance(term.func, LoadName):
            fname = term.func.name
        else:
            fname = _dotted_name_from_loadattr(term.func)
        arg_exprs = [
            term_to_ast_expr(a, var_context, eval_arith=eval_arith)
            for a in term.args
        ]
        kw_exprs = [
            ast.keyword(
                arg=kw.name,
                value=term_to_ast_expr(kw.value, var_context, eval_arith=eval_arith),
            )
            for kw in (term.kwargs or [])
        ]
        return ast.Call(
            func=_name(fname),
            args=arg_exprs,
            keywords=kw_exprs,
        )

    # Zero-arity PredicateMeta class: the class IS the atom value.
    # Emit a bare Name reference so the compiled code loads the class directly.
    if isinstance(term, PredicateMeta) and not term._fields:
        return _name(term.__name__)

    if is_term_instance(term):
        cls_name = type(term).__name__
        return ast.Call(
            func=_name(cls_name),
            args=[],
            keywords=[
                ast.keyword(
                    arg=name,
                    value=term_to_ast_expr(
                        getattr(term, name), var_context, eval_arith=eval_arith,
                    ),
                )
                for name in term_field_names(term)
                if name not in ("_position", "position")
            ],
        )

    # KWTerm: generate KWTerm("functor", key=val, ...)
    if isinstance(term, KWTerm):
        keywords = [
            ast.keyword(arg=k, value=term_to_ast_expr(v, var_context, eval_arith=eval_arith))
            for k, v in term.items()
        ]
        return ast.Call(
            func=_name("KWTerm"),
            args=[ast.Constant(value=term.functor)],
            keywords=keywords,
        )

    # PyThunk: deferred Python expression via lambda wrapper.
    # Used for f-strings in .clausal files and ++() Python escapes.
    # The thunk stores a callable (lambda) and a list of Var objects.
    # The compiler emits: thunk.fn(deref(local0), deref(local1), ...)
    if isinstance(term, PyThunk):
        # Reference to the thunk's .fn stored in compiled function globals.
        # Use a unique name to avoid collisions.
        thunk_name = f"_pyt_{id(term)}"
        arg_exprs = []
        for var_obj in term.var_objects:
            vid = var_obj._id
            if vid in var_context:
                arg_exprs.append(_call(_name("deref"), _name(var_context[vid])))
            else:
                # Body-only var — allocate and deref
                vname = _var_python_name(var_obj)
                var_context[vid] = vname
                arg_exprs.append(_call(
                    _name("deref"),
                    ast.NamedExpr(
                        target=ast.Name(id=vname, ctx=ast.Store()),
                        value=_call(_name("Var")),
                    ),
                ))
        return ast.Call(
            func=_name(thunk_name),
            args=arg_exprs,
            keywords=[],
        )

    if isinstance(term, Lambda):
        raise NotImplementedError(
            "Lambdas are currently only supported as predicate call arguments"
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

    term = literal_value(term)
    if isinstance(term, (int, float, Fraction)) and not isinstance(term, bool):
        return ast.Constant(value=term)

    # int / int → Fraction(n, d) for exact rational arithmetic
    if isinstance(term, Div):
        left_t = deref(term.left)
        right_t = deref(term.right)
        if (isinstance(left_t, int) and not isinstance(left_t, bool)
                and isinstance(right_t, int) and not isinstance(right_t, bool)):
            return ast.Call(
                func=_name("_Fraction"),
                args=[ast.Constant(value=left_t), ast.Constant(value=right_t)],
                keywords=[],
            )

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
