import ast
import sys
import types as _types
from dataclasses import dataclass, fields
from .transform_nodes import _transform_node_list

_unspecified = object()

# Primitive scalar type names — anything else in an annotation is a Node subclass.
_PRIMITIVE_NAMES = frozenset({'str', 'int', 'float', 'bool', 'bytes', 'complex'})


def _field_kind(f):
    """Classify a dataclass field as 'node', 'optional_node', 'node_list', or 'plain'.

    With ``from __future__ import annotations`` (PEP 563), every annotation is
    stored as a plain string, so we parse it directly instead of trying to use
    it as a live type object (which was the original bug).

    Rules:
      Optional[X] where X is a non-primitive  → 'optional_node'
      list[X]     where X is a non-primitive  → 'node_list'
      list[X]     where X is a primitive       → 'plain'
      any primitive scalar                     → 'plain'
      anything else (Node, Params, ForClause…) → 'node'
    """
    s = f.type if isinstance(f.type, str) else repr(f.type)
    s = s.strip()

    optional = False
    if s.startswith('Optional[') and s.endswith(']'):
        s = s[9:-1].strip()
        optional = True

    if s.startswith('list[') and s.endswith(']'):
        elem = s[5:-1].strip()
        return 'plain' if elem in _PRIMITIVE_NAMES else 'node_list'

    if s in _PRIMITIVE_NAMES:
        return 'plain'

    return 'optional_node' if optional else 'node'


# ── Tiny AST helpers ──────────────────────────────────────────────────────────

def _name(id, ctx=ast.Load()):
    return ast.Name(id=id, ctx=ctx)

def _attr(value, attr):
    return ast.Attribute(value=value, attr=attr, ctx=ast.Load())

def _self_attr(attr):
    return _attr(_name("self"), attr)

def _call(func, args=None, keywords=None):
    return ast.Call(func=func, args=args or [], keywords=keywords or [])

def _arg(name):
    return ast.arg(arg=name)

def _positional_args(*names):
    """ast.arguments with only positional args: def f(a, b, ...)"""
    return ast.arguments(
        posonlyargs=[], args=[_arg(n) for n in names],
        vararg=None, kwonlyargs=[], kw_defaults=[],
        kwarg=None, defaults=[],
    )

def _self_and_kwonly_args(names):
    """ast.arguments with self + keyword-only args (placeholder defaults)."""
    return ast.arguments(
        posonlyargs=[], args=[_arg("self")],
        vararg=None,
        kwonlyargs=[_arg(n) for n in names],
        kw_defaults=[ast.Constant(value=None)] * len(names),
        kwarg=None, defaults=[],
    )


def _compile_function(func_def, filename, lineno, func_globals=None, kwdefaults=None):
    """Compile a single ast.FunctionDef into a function object.

    Avoids exec() — extracts the code object from the compiled module
    and constructs the function directly via types.FunctionType.
    """
    module = ast.Module(body=[func_def], type_ignores=[])
    ast.fix_missing_locations(module)
    module_code = compile(module, filename, "exec")

    func_code = next(
        c for c in module_code.co_consts if isinstance(c, _types.CodeType)
        if isinstance(c, _types.CodeType) and c.co_name == func_def.name
    )
    func_code = func_code.replace(co_firstlineno=lineno)

    func = _types.FunctionType(func_code, func_globals or {})
    if kwdefaults is not None:
        func.__kwdefaults__ = kwdefaults
    return func


# ── The decorator ─────────────────────────────────────────────────────────────

def node_class(NodeClass):
    """
    Decorator that applies @dataclass and generates three methods via AST:

    visit_children(self, visit)
      — calls visit() on every Node / list[Node] field
    transform_children(self, transform)
      — returns self.transform_fields(...) with
        transformed Node / list[Node] fields
    __call__(self, *, <fields>=…)
      — returns a copy with selectively replaced fields
    """
    NodeClass = dataclass(NodeClass)

    frame = sys._getframe(1)
    filename = frame.f_code.co_filename
    lineno = frame.f_lineno

    all_fields = fields(NodeClass)
    user_fields = [f for f in all_fields if f.name != "position"]

    if not user_fields:
        return NodeClass

    classified = [(f, _field_kind(f)) for f in user_fields]

    # ── visit_children(self, visit) -> None ───────────────────────────────

    visit_body = []
    for f, kind in classified:
        if kind == "node":
            visit_body.append(
                ast.Expr(value=_call(_name("visit"), [_self_attr(f.name)]))
            )
        elif kind == "optional_node":
            # if self.f is not None: visit(self.f)
            visit_body.append(
                ast.If(
                    test=ast.Compare(
                        left=_self_attr(f.name),
                        ops=[ast.IsNot()],
                        comparators=[ast.Constant(value=None)],
                    ),
                    body=[ast.Expr(value=_call(_name("visit"), [_self_attr(f.name)]))],
                    orelse=[],
                )
            )
        elif kind == "node_list":
            visit_body.append(
                ast.For(
                    target=_name("_elem", ast.Store()),
                    iter=_self_attr(f.name),
                    body=[ast.Expr(value=_call(_name("visit"), [_name("_elem")]))],
                    orelse=[],
                )
            )

    if not visit_body:
        visit_body = [ast.Pass()]

    NodeClass.visit_children = _compile_function(
        ast.FunctionDef(
            name="visit_children",
            args=_positional_args("self", "visit"),
            body=visit_body,
            decorator_list=[],
            returns=ast.Constant(value=None),
        ),
        filename, lineno,
    )

    # ── transform_children(self, transform) ───────────────────────────────

    transform_kws = []
    for f, kind in classified:
        if kind == "node":
            val = _call(_name("transform"), [_self_attr(f.name)])
        elif kind == "optional_node":
            # transform(self.f) if self.f is not None else None
            val = ast.IfExp(
                test=ast.Compare(
                    left=_self_attr(f.name),
                    ops=[ast.IsNot()],
                    comparators=[ast.Constant(value=None)],
                ),
                body=_call(_name("transform"), [_self_attr(f.name)]),
                orelse=ast.Constant(value=None),
            )
        elif kind == "node_list":
            val = _call(
                _name("_transform_node_list"),
                [_self_attr(f.name), _name("transform")],
            )
        else:
            continue
        transform_kws.append(ast.keyword(arg=f.name, value=val))

    NodeClass.transform_children = _compile_function(
        ast.FunctionDef(
            name="transform_children",
            args=_positional_args("self", "transform"),
            body=[
                ast.Return(
                    value=_call(
                        _attr(_name("self"), "transform_fields"),
                        keywords=transform_kws,
                    )
                )
            ],
            decorator_list=[],
        ),
        filename, lineno,
        func_globals={"_transform_node_list": _transform_node_list},
    )

    # ── __call__(self, *, <user_fields>=_unspecified) ─────────────────────

    constructor_kws = [
        ast.keyword(arg="position", value=_self_attr("position")),
    ]

    kwdefault_names = []
    for f in user_fields:
        kwdefault_names.append(f.name)
        constructor_kws.append(
            ast.keyword(
                arg=f.name,
                value=ast.IfExp(
                    test=ast.Compare(
                        left=_name(f.name),
                        ops=[ast.Is()],
                        comparators=[_name("_unspecified")],
                    ),
                    body=_self_attr(f.name),
                    orelse=_name(f.name),
                ),
            )
        )

    NodeClass.__call__ = _compile_function(
        ast.FunctionDef(
            name="__call__",
            args=_self_and_kwonly_args(kwdefault_names),
            body=[
                ast.Return(
                    value=_call(
                        _attr(_name("self"), "__class__"),
                        keywords=constructor_kws,
                    )
                )
            ],
            decorator_list=[],
        ),
        filename, lineno,
        func_globals={"_unspecified": _unspecified},
        kwdefaults={name: _unspecified for name in kwdefault_names},
    )

    return NodeClass
