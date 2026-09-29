"""Feasibility: can the native front end REUSE the seam's directive handlers
(EmbedTransformer._handle_directive) by handing them synthesized Python-ast args built
from reader cells -- no text round trip?  Prints the statements and module items each yields.
Run from the worktree root."""
import ast, os, sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.getcwd())
import clausal; assert clausal.__file__.startswith(os.getcwd())
from clausal.templating.term_rewriting import EmbedTransformer

def pyarg(c):
    """reader cell -> the seam's surface ast for a DIRECTIVE argument (narrow subset)."""
    if type(c) is str: return ast.Name(id=c, ctx=ast.Load())
    if isinstance(c, int): return ast.Constant(value=c)
    if isinstance(c, list): return ast.List(elts=[pyarg(x) for x in c], ctx=ast.Load())
    if isinstance(c, tuple) and c[0] == "/" and len(c) == 3:
        return ast.BinOp(left=pyarg(c[1]), op=ast.Div(), right=pyarg(c[2]))
    if isinstance(c, tuple) and c[0] == "." and len(c) == 3:  # dotted module path a.b
        return ast.Attribute(value=pyarg(c[1]), attr=c[2], ctx=ast.Load())
    if isinstance(c, tuple):
        return ast.Call(func=ast.Name(id=c[0], ctx=ast.Load()), args=[pyarg(a) for a in c[1:]], keywords=[])
    raise ValueError(c)

from clausal.tools.prolog_reader import read_module
SRC = """:- module(m, [p/1, q/2]).
:- dynamic(d/1).
:- discontiguous(p/1).
:- table(q/2).
:- private([foo, pt(x, y)]).
:- set_prolog_flag(double_quotes, atom).
"""
t = EmbedTransformer(source_lines=[], filename="probe.pl")
for it in read_module(SRC):
    cell = it.term
    name, args = cell[0], [pyarg(a) for a in cell[1:]]
    if name == "private":            # the seam spells the declarations directive -private([...])
        pass
    stmt = ast.Expr(value=ast.Constant(value=None)); stmt.lineno = 1; stmt.col_offset = 0
    stmt.end_lineno = 1; stmt.end_col_offset = 0
    try:
        out = t._handle_directive(name, args, stmt)
        outs = out if isinstance(out, list) else [out]
        print(f"{name:16s} ->", [ast.unparse(o)[:70] for o in outs][:3])
    except Exception as e:
        print(f"{name:16s} RAISED {type(e).__name__}: {str(e)[:150]}")
print("module_items:", [(type(i).__name__, getattr(i, 'name', None), getattr(i, 'specs', None)) for i in t._module_items][:10])
print("atoms seen:", sorted(getattr(t, '_atoms', set())))
