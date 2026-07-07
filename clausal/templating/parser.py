"""
Template parser: detection and structural analysis of @{}-decorated templates.

Syntax overview::

    @{}
    def make_visitor(VISIT, FN):
        def VISIT(self, FN):
            {make_field_visit(f) for f in fields}
            FN.visit(self)

Detection: FunctionDef with a single empty-dict decorator.

Escapes (bare expression statements in template body):
  {expr}                  — splice single stmt
  {expr1, expr2}          — splice multiple stmts
  {*expr}                 — extend from list
  {g(x) for x in iter}   — loop + splice

Magic parameters:
  def NAME(__args__={expr}):   — runtime arguments (sole param)
    expr → ast.arguments | ast.arg | tuple[ast.arg, ...]

  class NAME({expr}):          — runtime base classes (sole base)
    expr → list[ast.expr] | ast.expr | tuple[ast.expr, ...]
"""

import ast

__all__ = [
    "TemplateCompileError",
    "is_template_func",
]


# ======================================================================
# Errors
# ======================================================================

class TemplateCompileError(Exception):
    pass


# ======================================================================
# Escape detection
# ======================================================================

def _is_escape(node: ast.stmt):
    """Detect {expr}, {a,b}, {*expr}, {g(x) for x in iter}."""
    if not isinstance(node, ast.Expr):
        return None
    v = node.value
    if isinstance(v, ast.Set) and len(v.elts) == 1 and isinstance(v.elts[0], ast.Starred):
        return ("star", v.elts[0].value)
    if isinstance(v, ast.SetComp):
        return ("comp", v)
    if isinstance(v, ast.Set):
        return ("single", v.elts)
    return None


def is_template_func(node: ast.AST) -> bool:
    """True if node is an @{}-decorated function."""
    return (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and len(node.decorator_list) == 1
            and isinstance(node.decorator_list[0], ast.Dict)
            and not node.decorator_list[0].keys)


# ======================================================================
# Magic parameter / base detection
# ======================================================================

_MAGIC_ARGS = "__args__"


def _detect_magic_args(arguments: ast.arguments):
    """Return (True, expr) if __args__={expr} found, else (False, None)."""
    all_args = [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs]
    if not any(a.arg == _MAGIC_ARGS for a in all_args):
        return False, None
    if len(all_args) != 1:
        raise TemplateCompileError(
            f"{_MAGIC_ARGS} must be the sole parameter (found {len(all_args)})")
    # A10-F014: __args__ must be an ordinary positional parameter. A posonly
    # (`__args__, /`) or kwonly (`*, __args__`) placement keeps its default in
    # a different list — indexing arguments.defaults raised a bare
    # StopIteration; reject it with a clean TemplateCompileError instead.
    if not any(a.arg == _MAGIC_ARGS for a in arguments.args):
        raise TemplateCompileError(
            f"{_MAGIC_ARGS} must be a positional parameter")
    idx = next(i for i, a in enumerate(arguments.args) if a.arg == _MAGIC_ARGS)
    didx = idx - (len(arguments.args) - len(arguments.defaults))
    if didx < 0:
        raise TemplateCompileError(f"{_MAGIC_ARGS} requires a {{expr}} default")
    d = arguments.defaults[didx]
    if isinstance(d, ast.Set) and len(d.elts) == 1:
        return True, d.elts[0]
    if isinstance(d, ast.SetComp):
        lc = ast.ListComp(elt=d.elt, generators=d.generators)
        ast.copy_location(lc, d)
        return True, lc
    raise TemplateCompileError(
        f"{_MAGIC_ARGS} default must be {{expr}} or {{expr for ... in ...}}")


def _detect_magic_bases(bases: list[ast.expr]):
    """Return (True, expr) if sole base is {expr}, else (False, None)."""
    if len(bases) == 1 and isinstance(bases[0], ast.Set) and len(bases[0].elts) == 1:
        return True, bases[0].elts[0]
    return False, None
