"""
codegen.py — Compile Python AST nodes into callable functions.
"""

import ast
import builtins as _builtins

__all__ = [
    "functiondef_to_function",
    "stmts_to_function",
]

_BUILTIN_NAMES = frozenset(vars(_builtins))


def _infer_args(stmts: list[ast.stmt], globals_: dict | None = None) -> ast.arguments:
    """Infer positional parameters by scanning name loads before assignments.

    A name becomes a parameter if it is loaded before it is assigned anywhere
    in ``stmts`` (at the top-level scope only — nested functions, classes,
    lambdas, and comprehensions introduce their own scopes and are not
    descended into, except that the outermost iterable of a comprehension IS
    evaluated in the enclosing scope).  Built-in names and names present in
    ``globals_`` are excluded (they are already available, not arguments).

    Order is the order of first qualifying load.
    """
    assigned: set[str] = set()
    params: list[str] = []
    seen: set[str] = set()
    excluded = _BUILTIN_NAMES if not globals_ else _BUILTIN_NAMES | globals_.keys()

    class _Scanner(ast.NodeVisitor):
        # ── nested scopes: record the name being bound, but do not descend ─────
        def visit_FunctionDef(self, node):
            assigned.add(node.name)
        visit_AsyncFunctionDef = visit_FunctionDef
        def visit_ClassDef(self, node):
            assigned.add(node.name)
        def visit_Lambda(self, node): pass

        # Only the outermost iterable of a comprehension is in the enclosing scope.
        def _comp(self, node):
            self.visit(node.generators[0].iter)
        visit_ListComp = _comp
        visit_SetComp = _comp
        visit_DictComp = _comp
        visit_GeneratorExp = _comp

        # ── name handling ─────────────────────────────────────────────────────
        def _record_load(self, name: str):
            if name not in assigned and name not in seen and name not in excluded:
                params.append(name)
                seen.add(name)

        def visit_Name(self, node):
            if isinstance(node.ctx, ast.Load):
                self._record_load(node.id)
            elif isinstance(node.ctx, (ast.Store, ast.Del)):
                assigned.add(node.id)

        # ── assignment ordering: value (RHS) must be visited before targets ──
        def visit_Assign(self, node):
            self.visit(node.value)
            for target in node.targets:
                self.visit(target)

        def visit_AnnAssign(self, node):
            if node.value:
                self.visit(node.value)
            self.visit(node.target)

        def visit_NamedExpr(self, node):
            # A10-F015: walrus `(x := expr)` evaluates value before binding the
            # target, like Assign — the generic (target, value) field order
            # would mark the target assigned before scanning the value.
            self.visit(node.value)
            self.visit(node.target)

        def visit_AugAssign(self, node):
            # Read-modify-write: target is implicitly loaded before being stored.
            if isinstance(node.target, ast.Name):
                self._record_load(node.target.id)
                assigned.add(node.target.id)
            else:
                self.visit(node.target)   # Attribute/Subscript: object is Load
            self.visit(node.value)

        # ── for loop: evaluate iterable before assigning loop target ─────────
        def visit_For(self, node):
            self.visit(node.iter)
            self.visit(node.target)
            for s in node.body:
                self.visit(s)
            for s in node.orelse:
                self.visit(s)

        # ── global/nonlocal: treat as already available, not parameters ──────
        def visit_Global(self, node):
            for name in node.names:
                assigned.add(name)

        def visit_Nonlocal(self, node):
            for name in node.names:
                assigned.add(name)

    scanner = _Scanner()
    for stmt in stmts:
        scanner.visit(stmt)

    return ast.arguments(
        posonlyargs=[],
        args=[ast.arg(arg=name) for name in params],
        vararg=None,
        kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[],
    )


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
    args:       parameter signature; if omitted, inferred from the body via
                ``_infer_args`` (names that are loaded before being assigned
                become positional parameters, in order of first load)
    decorators: decorator list
    returns:    return-annotation expression
    globals_:   names made available in the function's defining scope
    filename:   filename used in tracebacks
    """
    if args is None:
        args = _infer_args(body, globals_)
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
