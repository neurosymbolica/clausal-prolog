"""
Template compiler: transforms @{}-decorated functions into functions
that build substituted AST statement lists.

All output is AST nodes — no string codegen. Source locations from
the template propagate to compiled output for readable tracebacks.
"""

import ast
import copy

from .parser import (
    TemplateCompileError,
    is_template_func,
    _is_escape,
    _detect_magic_args,
    _detect_magic_bases,
)

__all__ = [
    "TemplateCompileError",
    "compile_template_func",
    "transform_module_ast",
    "transform_module",
    "functiondef_to_function",
    "stmts_to_function",
]


# ======================================================================
# AST micro-constructors
# ======================================================================

def _name(id: str, ctx=None):
    return ast.Name(id=id, ctx=ctx or ast.Load())

def _store(id: str):
    return ast.Name(id=id, ctx=ast.Store())

def _attr(value, attr: str):
    return ast.Attribute(value=value, attr=attr, ctx=ast.Load())

def _call(func, args=(), kws=()):
    return ast.Call(func=func, args=list(args), keywords=list(kws))

def _const(value):
    return ast.Constant(value=value)

def _list(elts):
    return ast.List(elts=list(elts), ctx=ast.Load())

def _kw(arg: str, value):
    return ast.keyword(arg=arg, value=value)

def _assign(target: str, value):
    return ast.Assign(targets=[_store(target)], value=value)

def _expr_stmt(expr):
    return ast.Expr(value=expr)

def _append(target: str, value):
    return _expr_stmt(_call(_attr(_name(target), "append"), [value]))

def _extend(target: str, value):
    return _expr_stmt(_call(_attr(_name(target), "extend"), [value]))

def _isinstance_check(x, cls):
    return _call(_name("isinstance"), [x, cls])

def _ast_attr(attr: str):
    return _attr(_name("_ast"), attr)

def _ast_call(name: str, args=(), kws=()):
    return _call(_ast_attr(name), args, kws)

def _loc(node, lineno: int):
    node.lineno = node.end_lineno = lineno
    node.col_offset = node.end_col_offset = 0
    return node

def _import_ast():
    return ast.Import(names=[ast.alias(name="ast", asname="_ast")])

def _type_error(prefix: str, value_var: str):
    return ast.Raise(
        exc=_call(_name("TypeError"), [ast.JoinedStr(values=[
            _const(prefix),
            ast.FormattedValue(
                value=_attr(_call(_name("type"), [_name(value_var)]),
                            "__name__"),
                conversion=-1),
        ])]),
        cause=None)


# ======================================================================
# String-callable rewriter (for escape expression elts)
# ======================================================================

class _StringCallableRewriter(ast.NodeTransformer):
    """Rewrite 'string'(args) in escape-expression elts.

    Valid identifiers:  'foo'(a, b)  → foo(a, b)
    Non-identifiers:    '+='(a, b)   → globals()['+='](a, b)

    This prevents the SyntaxWarning Python's compiler emits for string-as-
    callable, and the resulting TypeError when the generated code runs.
    """

    def visit_Call(self, node):
        self.generic_visit(node)
        if isinstance(node.func, ast.Constant) and isinstance(node.func.value, str):
            name = node.func.value
            loc = node.func
            if name.isidentifier():
                node.func = ast.copy_location(
                    ast.Name(id=name, ctx=ast.Load()), loc)
            else:
                node.func = ast.copy_location(
                    ast.Subscript(
                        value=ast.copy_location(_call(_name("globals")), loc),
                        slice=ast.copy_location(ast.Constant(value=name), loc),
                        ctx=ast.Load(),
                    ), loc)
        return node


# ======================================================================
# Identifier field tables
# ======================================================================

_IDENT_FIELDS = {
    (ast.FunctionDef, "name"), (ast.AsyncFunctionDef, "name"),
    (ast.ClassDef, "name"), (ast.Attribute, "attr"),
    (ast.keyword, "arg"), (ast.arg, "arg"),
    (ast.alias, "name"), (ast.alias, "asname"),
    (ast.ImportFrom, "module"), (ast.ExceptHandler, "name"),
}

_IDENT_LIST_FIELDS = {
    (ast.Global, "names"), (ast.Nonlocal, "names"),
}


def _is_stmt_list(name: str, value) -> bool:
    return (isinstance(value, list) and value
            and all(isinstance(v, ast.stmt) for v in value))


# ======================================================================
# Normalizers for magic args/bases
# ======================================================================

def _normalize_args(raw_var: str, result_var: str) -> list[ast.stmt]:
    """if/elif chain: raw → ast.arguments."""
    def _empty_args(args_expr):
        return _ast_call("arguments", kws=[
            _kw("posonlyargs", _list([])), _kw("args", args_expr),
            _kw("vararg", _const(None)), _kw("kwonlyargs", _list([])),
            _kw("kw_defaults", _list([])), _kw("kwarg", _const(None)),
            _kw("defaults", _list([])),
        ])

    raw, res = _name(raw_var), _store(result_var)
    return [ast.If(
        test=_isinstance_check(raw, _ast_attr("arguments")),
        body=[ast.Assign(targets=[copy.deepcopy(res)], value=raw)],
        orelse=[ast.If(
            test=_isinstance_check(raw, _ast_attr("arg")),
            body=[ast.Assign(targets=[copy.deepcopy(res)],
                             value=_empty_args(_list([raw])))],
            orelse=[ast.If(
                test=_isinstance_check(raw, _name("list")),
                body=[ast.Assign(targets=[copy.deepcopy(res)],
                                 value=_empty_args(raw))],
                orelse=[ast.If(
                    test=_isinstance_check(raw, _name("tuple")),
                    body=[ast.Assign(targets=[copy.deepcopy(res)],
                                     value=_empty_args(_call(_name("list"), [raw])))],
                    orelse=[_type_error("__args__: expected arguments/arg/list/tuple, got ",
                                       raw_var)],
                )],
            )],
        )],
    )]


def _normalize_bases(raw_var: str, result_var: str) -> list[ast.stmt]:
    """if/elif chain: raw → list[ast.expr]."""
    raw, res = _name(raw_var), _store(result_var)
    return [ast.If(
        test=_isinstance_check(raw, _name("list")),
        body=[ast.Assign(targets=[copy.deepcopy(res)], value=raw)],
        orelse=[ast.If(
            test=_isinstance_check(raw, _name("tuple")),
            body=[ast.Assign(targets=[copy.deepcopy(res)],
                             value=_call(_name("list"), [raw]))],
            orelse=[ast.If(
                test=_isinstance_check(raw, _ast_attr("AST")),
                body=[ast.Assign(targets=[copy.deepcopy(res)],
                                 value=_list([raw]))],
                orelse=[_type_error("__bases__: expected list/tuple/expr, got ",
                                   raw_var)],
            )],
        )],
    )]


# ======================================================================
# ASTBuilder
# ======================================================================

class ASTBuilder:
    """Emit AST stmts that construct other AST nodes at runtime."""

    def __init__(self, sub_names: set[str]):
        self.sub_names = sub_names
        self._counter = 0
        self._stmts: list[ast.stmt] = []

    def _fresh(self, prefix="_n"):
        self._counter += 1
        return f"{prefix}{self._counter}"

    def _emit(self, stmt):
        self._stmts.append(stmt)

    @property
    def statements(self) -> list[ast.stmt]:
        return self._stmts

    # -- Statement lists (escape-aware) --

    def build_stmt_list(self, stmts: list[ast.stmt], var: str):
        self._emit(_assign(var, _list([])))
        for s in stmts:
            esc = _is_escape(s)
            if esc is None:
                self._emit(_append(var, _name(self._build(s))))
            else:
                self._emit_escape(esc, var, getattr(s, "lineno", 0))

    def _splice_check(self, tmp: str, target: str) -> list[ast.stmt]:
        return [ast.If(
            test=_isinstance_check(_name(tmp), _name("list")),
            body=[_extend(target, _name(tmp))],
            orelse=[ast.If(
                test=_isinstance_check(_name(tmp), _ast_attr("AST")),
                body=[_append(target, _name(tmp))],
                orelse=[_type_error("Escape: expected AST node(s), got ", tmp)],
            )],
        )]

    def _emit_escape(self, esc, target: str, ln: int):
        kind, payload = esc
        rewrite = _StringCallableRewriter().visit
        if kind == "single":
            for expr in payload:
                tmp = self._fresh("_esc")
                self._emit(_loc(_assign(tmp, rewrite(expr)), ln))
                for s in self._splice_check(tmp, target):
                    self._emit(_loc(s, ln))
        elif kind == "star":
            self._emit(_loc(_extend(target, rewrite(payload)), ln))
        elif kind == "comp":
            self._emit_comp(payload, target, ln)

    def _emit_comp(self, sc: ast.SetComp, target: str, ln: int):
        tmp = self._fresh("_ce")
        elt = _StringCallableRewriter().visit(sc.elt)
        body = [_assign(tmp, elt), *self._splice_check(tmp, target)]
        for gen in reversed(sc.generators):
            for ifc in reversed(gen.ifs):
                body = [ast.If(test=ifc, body=body, orelse=[])]
            body = [ast.For(target=gen.target, iter=gen.iter,
                            body=body, orelse=[])]
        for s in body:
            self._emit(_loc(s, ln))

    # -- Node building --

    def _build(self, node: ast.AST) -> str:
        m = getattr(self, f"_build_{type(node).__name__}", None)
        return m(node) if m else self._build_generic(node)

    def _build_generic(self, node: ast.AST) -> str:
        var = self._fresh()
        ln = getattr(node, "lineno", 0)
        kws = []
        for fn, fv in ast.iter_fields(node):
            if _is_stmt_list(fn, fv):
                lv = self._fresh("_sl")
                self.build_stmt_list(fv, lv)
                kws.append(_kw(fn, _name(lv)))
            else:
                kws.append(_kw(fn, self._val(node, fn, fv)))
        self._emit(_loc(_assign(var, _ast_call(type(node).__name__,
                                               kws=kws)), ln))
        return var

    def _val(self, parent, fname, value) -> ast.expr:
        if value is None:
            return _const(None)
        if isinstance(value, (bool, int, float, complex, bytes)):
            return _const(value)
        if isinstance(value, str):
            if (type(parent), fname) in _IDENT_FIELDS and value in self.sub_names:
                return _name(value)
            return _const(value)
        if isinstance(value, list):
            if not value:
                return _list([])
            if (type(parent), fname) in _IDENT_LIST_FIELDS:
                return _list([_name(v) if isinstance(v, str) and v in self.sub_names
                              else _const(v) for v in value])
            return _list([_name(self._build(v)) if isinstance(v, ast.AST)
                          else _const(v) for v in value])
        if isinstance(value, ast.AST):
            return _name(self._build(value))
        return _const(value)

    # -- Specialized: FunctionDef (with __args__) --

    def _build_FunctionDef(self, node):
        return self._build_funcdef(node, "FunctionDef")

    def _build_AsyncFunctionDef(self, node):
        return self._build_funcdef(node, "AsyncFunctionDef")

    def _build_funcdef(self, node, cls: str) -> str:
        var = self._fresh()
        ln = getattr(node, "lineno", 0)
        has_magic, expr = _detect_magic_args(node.args)
        kws = []
        for fn, fv in ast.iter_fields(node):
            if fn == "args" and has_magic:
                raw, norm = self._fresh("_rawargs"), self._fresh("_args")
                self._emit(_loc(_assign(raw, expr), ln))
                for s in _normalize_args(raw, norm):
                    self._emit(_loc(s, ln))
                kws.append(_kw(fn, _name(norm)))
            elif _is_stmt_list(fn, fv):
                lv = self._fresh("_sl")
                self.build_stmt_list(fv, lv)
                kws.append(_kw(fn, _name(lv)))
            else:
                kws.append(_kw(fn, self._val(node, fn, fv)))
        self._emit(_loc(_assign(var, _ast_call(cls, kws=kws)), ln))
        return var

    # -- Specialized: ClassDef (with magic bases) --

    def _build_ClassDef(self, node: ast.ClassDef) -> str:
        var = self._fresh()
        ln = getattr(node, "lineno", 0)
        has_magic, expr = _detect_magic_bases(node.bases)
        kws = []
        for fn, fv in ast.iter_fields(node):
            if fn == "bases" and has_magic:
                raw, norm = self._fresh("_rawbases"), self._fresh("_bases")
                self._emit(_loc(_assign(raw, expr), ln))
                for s in _normalize_bases(raw, norm):
                    self._emit(_loc(s, ln))
                kws.append(_kw(fn, _name(norm)))
            elif _is_stmt_list(fn, fv):
                lv = self._fresh("_sl")
                self.build_stmt_list(fv, lv)
                kws.append(_kw(fn, _name(lv)))
            else:
                kws.append(_kw(fn, self._val(node, fn, fv)))
        self._emit(_loc(_assign(var, _ast_call("ClassDef", kws=kws)), ln))
        return var

    # -- Specialized: leaf nodes --

    def _build_Name(self, node):
        var = self._fresh()
        ln = getattr(node, "lineno", 0)
        self._emit(_loc(_assign(var, _ast_call("Name", kws=[
            _kw("id", _name(node.id) if node.id in self.sub_names
                 else _const(node.id)),
            _kw("ctx", self._val(node, "ctx", node.ctx)),
        ])), ln))
        return var

    def _build_Constant(self, node):
        var = self._fresh()
        self._emit(_loc(_assign(var, _ast_call("Constant", kws=[
            _kw("value", _const(node.value)),
        ])), getattr(node, "lineno", 0)))
        return var

    def _build_arg(self, node):
        var = self._fresh()
        ann = (_const(None) if node.annotation is None
               else _name(self._build(node.annotation)))
        self._emit(_loc(_assign(var, _ast_call("arg", kws=[
            _kw("arg", _name(node.arg) if node.arg in self.sub_names
                 else _const(node.arg)),
            _kw("annotation", ann),
        ])), getattr(node, "lineno", 0)))
        return var

    def _build_Call(self, node: ast.Call) -> str:
        # String callable: '+'(a, b) → Name(id='+')(a, b)
        if isinstance(node.func, ast.Constant) and isinstance(node.func.value, str):
            node = copy.copy(node)
            node.func = ast.copy_location(
                ast.Name(id=node.func.value, ctx=ast.Load()), node.func)
        return self._build_generic(node)

    def _build_Load(self, n):
        v = self._fresh(); self._emit(_assign(v, _ast_call("Load"))); return v
    def _build_Store(self, n):
        v = self._fresh(); self._emit(_assign(v, _ast_call("Store"))); return v
    def _build_Del(self, n):
        v = self._fresh(); self._emit(_assign(v, _ast_call("Del"))); return v


# ======================================================================
# Compiler entry points
# ======================================================================

def compile_template_func(func_node: ast.FunctionDef) -> ast.FunctionDef:
    """Compile @{} template → function returning list[ast.stmt]."""
    if not is_template_func(func_node):
        raise TemplateCompileError("Not an @{} template function")

    sub_names = {a.arg for a in [*func_node.args.posonlyargs,
                                  *func_node.args.args,
                                  *func_node.args.kwonlyargs]}

    builder = ASTBuilder(sub_names)
    builder.build_stmt_list(func_node.body, "_body")
    builder._emit(_expr_stmt(_call(
        _ast_attr("fix_missing_locations"),
        [_ast_call("Module", kws=[
            _kw("body", _name("_body")),
            _kw("type_ignores", _list([])),
        ])])))
    builder._emit(ast.Return(value=_name("_body")))

    result = ast.FunctionDef(
        name=func_node.name,
        args=copy.deepcopy(func_node.args),
        body=[_import_ast(), *builder.statements],
        decorator_list=[],
        returns=func_node.returns,
        type_comment=func_node.type_comment,
        **({'type_params': []} if hasattr(func_node, 'type_params') else {}),
    )
    ast.copy_location(result, func_node)
    ast.fix_missing_locations(result)
    return result


class TemplateBlockTransformer(ast.NodeTransformer):
    def visit_FunctionDef(self, node):
        return compile_template_func(node) if is_template_func(node) \
            else self.generic_visit(node)
    visit_AsyncFunctionDef = visit_FunctionDef


def transform_module_ast(tree: ast.Module) -> ast.Module:
    """Transform all @{} functions in a module AST in place."""
    new_tree = TemplateBlockTransformer().visit(tree)
    ast.fix_missing_locations(new_tree)
    return new_tree


def transform_module(source: str) -> str:
    """Parse, compile @{} templates, return source string."""
    return ast.unparse(transform_module_ast(ast.parse(source)))


# ======================================================================
# AST → callable
# ======================================================================

def functiondef_to_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    globals_: dict | None = None,
    filename: str = "<template>",
):
    """Compile an ast.FunctionDef (or AsyncFunctionDef) into a Python callable.

    The function name is read from node.name.  globals_ provides names
    visible at definition time (closures, helper functions, etc.).
    """
    module = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(module)
    code = compile(module, filename, "exec")
    ns = dict(globals_ or {})
    exec(code, ns)
    return ns[node.name]


def stmts_to_function(
    body: list[ast.stmt],
    name: str,
    args: ast.arguments | None = None,
    *,
    decorators: list[ast.expr] | None = None,
    returns: ast.expr | None = None,
    globals_: dict | None = None,
    filename: str = "<template>",
):
    """Wrap a statement list in a function definition and return a callable.

    Parameters
    ----------
    body:       statements forming the function body
    name:       name to give the function
    args:       parameter signature; defaults to no parameters
    decorators: decorator list
    returns:    return-annotation expression
    globals_:   names made available in the function's defining scope
    filename:   filename used in tracebacks
    """
    if args is None:
        args = ast.arguments(
            posonlyargs=[], args=[], vararg=None,
            kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[],
        )
    extra = {'type_params': []} if 'type_params' in ast.FunctionDef._fields else {}
    func_node = ast.FunctionDef(
        name=name,
        args=args,
        body=body,
        decorator_list=decorators or [],
        returns=returns,
        type_comment=None,
        **extra,
    )
    return functiondef_to_function(func_node, globals_=globals_, filename=filename)
