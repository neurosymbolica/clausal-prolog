"""Tests for simple_ast."""
import ast
import sys
from clausal.pythonic_ast import nodes as sa


def body(src: str) -> list[sa.Node]:
    return sa.simplify(ast.parse(src)).body

def expr(src: str) -> sa.Node:
    """Get a single expression from a statement body (no ExprStmt wrapper)."""
    s = body(src)
    assert len(s) == 1
    return s[0]

def stmt(src: str) -> sa.Node:
    s = body(src)
    assert len(s) == 1
    return s[0]

def stmts(src: str) -> list[sa.Node]:
    return body(src)


# ── Literals ─────────────────────────────────────────────────────────────────

def test_literals():
    assert isinstance(expr("42"), sa.IntLiteral) and expr("42").value == 42
    assert isinstance(expr("3.14"), sa.FloatLiteral)
    assert isinstance(expr("1j"), sa.ComplexLiteral)
    assert isinstance(expr("'hi'"), sa.StringLiteral) and expr("'hi'").value == "hi"
    assert isinstance(expr("b'hi'"), sa.BytesLiteral)
    assert isinstance(expr("True"), sa.BoolLiteral) and expr("True").value is True
    assert isinstance(expr("False"), sa.BoolLiteral) and expr("False").value is False
    assert isinstance(expr("None"), sa.NoneLiteral)
    assert isinstance(expr("..."), sa.EllipsisLiteral)
    print("  literals OK")


def test_collections():
    assert isinstance(expr("[1,2]"), sa.ListLiteral) and len(expr("[1,2]").elements) == 2
    assert isinstance(expr("(1,2)"), sa.TupleLiteral)
    assert isinstance(expr("{1,2}"), sa.SetLiteral)
    d = expr("{'a':1}")
    assert isinstance(d, sa.DictLiteral) and len(d.keys) == 1
    d2 = expr("{**x}")
    assert d2.keys[0] is None
    print("  collections OK")


def test_fstring():
    node = expr("f'hello {name}'")
    assert isinstance(node, sa.FString)
    assert isinstance(node.parts[0], sa.StringLiteral)
    assert isinstance(node.parts[1], sa.FormattedExpr)
    assert isinstance(node.parts[1].value, sa.LoadName)
    print("  fstrings OK")


def test_no_expr_stmt():
    """Expressions go directly into body — no ExprStmt wrapper."""
    s = body("f(x)")
    assert len(s) == 1
    assert isinstance(s[0], sa.Call), f"Expected Call, got {type(s[0]).__name__}"
    # in_ a function body too
    func = stmt("def g():\n  f(x)\n  42")
    assert isinstance(func, sa.FunctionDef)
    assert isinstance(func.body[0], sa.Call)
    assert isinstance(func.body[1], sa.IntLiteral)
    print("  no ExprStmt OK")


# ── Context splitting ────────────────────────────────────────────────────────

def test_name_context():
    assert isinstance(expr("x"), sa.LoadName) and expr("x").name == "x"
    s = stmt("x = 1")
    assert isinstance(s.targets[0], sa.StoreName) and s.targets[0].name == "x"
    ss = stmts("del x")
    assert isinstance(ss[0], sa.DeleteName) and ss[0].name == "x"
    print("  name context OK")


def test_attr_context():
    assert isinstance(expr("x.a"), sa.LoadAttr) and expr("x.a").attr == "a"
    s = stmt("x.a = 1")
    assert isinstance(s.targets[0], sa.StoreAttr)
    ss = stmts("del x.a")
    assert isinstance(ss[0], sa.DeleteAttr)
    print("  attr context OK")


def test_subscript_context():
    assert isinstance(expr("x[0]"), sa.LoadSubscript)
    s = stmt("x[0] = 1")
    assert isinstance(s.targets[0], sa.StoreSubscript)
    ss = stmts("del x[0]")
    assert isinstance(ss[0], sa.DeleteSubscript)
    print("  subscript context OK")


def test_starred():
    c = expr("f(*args)")
    assert isinstance(c.args[0], sa.StarUnpack)
    s = stmt("a, *b = [1,2,3]")
    pat = s.targets[0]
    assert isinstance(pat, sa.TuplePattern)
    assert isinstance(pat.targets[1], sa.StarTarget)
    print("  starred OK")


def test_destructuring():
    s = stmt("[a, b] = [1, 2]")
    assert isinstance(s.targets[0], sa.ListPattern)
    s2 = stmt("a, b = 1, 2")
    assert isinstance(s2.targets[0], sa.TuplePattern)
    print("  destructuring OK")


# ── Operators ────────────────────────────────────────────────────────────────

def test_binops():
    for src, cls in [
        ("x + y", sa.Add), ("x - y", sa.Sub), ("x * y", sa.Mult),
        ("x / y", sa.Div), ("x // y", sa.FloorDiv), ("x % y", sa.Mod),
        ("x ** y", sa.Pow), ("x @ y", sa.MatMult),
        ("x << y", sa.LShift), ("x >> y", sa.RShift),
        ("x | y", sa.BitOr), ("x ^ y", sa.BitXor), ("x & y", sa.BitAnd),
    ]:
        node = expr(src)
        assert isinstance(node, cls), f"{src} → {type(node).__name__}, expected {cls.__name__}"
        assert isinstance(node.left, sa.LoadName)
        assert isinstance(node.right, sa.LoadName)
    print("  binops OK")


def test_boolops():
    node = expr("a and b")
    assert isinstance(node, sa.And)
    assert isinstance(node.left, sa.LoadName) and isinstance(node.right, sa.LoadName)
    node = expr("a and b and c")
    assert isinstance(node, sa.And) and isinstance(node.left, sa.And)
    assert isinstance(node.right, sa.LoadName) and node.right.name == "c"
    assert isinstance(expr("a or b"), sa.Or)
    print("  boolops OK")


def test_unaryops():
    assert isinstance(expr("+x"), sa.UnaryPlus)
    assert isinstance(expr("-x"), sa.Negate)
    assert isinstance(expr("not x"), sa.Not)
    assert isinstance(expr("~x"), sa.Invert)
    print("  unaryops OK")


def test_comparisons():
    assert isinstance(expr("x == y"), sa.ArithEq)
    assert isinstance(expr("x != y"), sa.ArithNeq)
    assert isinstance(expr("x < y"), sa.Lt)
    assert isinstance(expr("x <= y"), sa.LtE)
    assert isinstance(expr("x > y"), sa.Gt)
    assert isinstance(expr("x >= y"), sa.GtE)
    assert isinstance(expr("x is y"), sa.Unify)
    assert isinstance(expr("x is not y"), sa.DoesNotUnify)
    assert isinstance(expr("x in y"), sa.in_)
    assert isinstance(expr("x not in y"), sa.NotIn)
    node = expr("1 < x < 10")
    assert isinstance(node, sa.CompareChain)
    assert len(node.comparisons) == 2
    assert isinstance(node.comparisons[0], sa.Lt) and isinstance(node.comparisons[1], sa.Lt)
    print("  comparisons OK")


def test_augmented_assign():
    for src, cls in [
        ("x += 1", sa.AddAssign), ("x -= 1", sa.SubAssign),
        ("x *= 1", sa.MultAssign), ("x /= 1", sa.DivAssign),
        ("x //= 1", sa.FloorDivAssign), ("x %= 1", sa.ModAssign),
        ("x **= 1", sa.PowAssign), ("x @= 1", sa.MatMultAssign),
        ("x <<= 1", sa.LShiftAssign), ("x >>= 1", sa.RShiftAssign),
        ("x |= 1", sa.BitOrAssign), ("x ^= 1", sa.BitXorAssign),
        ("x &= 1", sa.BitAndAssign),
    ]:
        s = stmt(src)
        assert isinstance(s, cls), f"{src} → {type(s).__name__}, expected {cls.__name__}"
    print("  augmented assign OK")


# ── Expressions ──────────────────────────────────────────────────────────────

def test_call():
    c = expr("f(1, 2, *args, key=val, **kw)")
    assert isinstance(c, sa.Call)
    assert isinstance(c.func, sa.LoadName) and c.func.name == "f"
    assert len(c.args) == 3
    assert isinstance(c.args[2], sa.StarUnpack)
    assert len(c.kwargs) == 2
    assert c.kwargs[0].name == "key"
    assert c.kwargs[1].name is None
    print("  call OK")

def test_ifexpr():
    assert isinstance(expr("a if b else c"), sa.IfExpr)
    print("  ifexpr OK")

def test_lambda():
    node = expr("lambda x, y=1: x + y")
    assert isinstance(node, sa.Lambda)
    assert isinstance(node.params, sa.Params)
    assert len(node.params.params) == 2
    assert node.params.params[0].name == "x"
    assert node.params.params[1].default is not None
    assert isinstance(node.body, sa.Add)
    print("  lambda OK")

def test_yield():
    s = stmt("def f():\n yield 1")
    assert isinstance(s, sa.FunctionDef)
    assert isinstance(s.body[0], sa.Yield)
    print("  yield OK")

def test_walrus():
    assert isinstance(expr("(x := 10)"), sa.NamedExpr)
    print("  walrus OK")

def test_slice():
    node = expr("x[1:2:3]")
    assert isinstance(node, sa.LoadSubscript)
    assert isinstance(node.index, sa.Slice)
    assert isinstance(node.index.lower, sa.IntLiteral)
    print("  slice OK")


# ── Comprehensions ───────────────────────────────────────────────────────────

def test_comprehensions():
    lc = expr("[x for x in y if x > 0]")
    assert isinstance(lc, sa.ListComp)
    assert len(lc.clauses) == 1 and isinstance(lc.clauses[0], sa.ForClause)
    assert isinstance(lc.clauses[0].target, sa.StoreName)
    assert len(lc.clauses[0].filters) == 1
    assert isinstance(expr("{x for x in y}"), sa.SetComp)
    assert isinstance(expr("{k: v for k, v in items}"), sa.DictComp)
    assert isinstance(expr("(x for x in y)"), sa.GeneratorExpr)
    print("  comprehensions OK")


# ── Parameters ───────────────────────────────────────────────────────────────

def test_parameters():
    s = stmt("def f(a, b=1, /, c=2, *args, d, e=3, **kw): pass")
    assert isinstance(s, sa.FunctionDef)
    p = s.params.params
    assert isinstance(p[0], sa.PosOnlyParam) and p[0].name == "a" and p[0].default is None
    assert isinstance(p[1], sa.PosOnlyParam) and p[1].name == "b" and p[1].default is not None
    assert isinstance(p[2], sa.PosOrKwParam) and p[2].name == "c" and p[2].default is not None
    assert isinstance(p[3], sa.VarPositional) and p[3].name == "args"
    assert isinstance(p[4], sa.KwOnlyParam) and p[4].name == "d" and p[4].default is None
    assert isinstance(p[5], sa.KwOnlyParam) and p[5].name == "e" and p[5].default is not None
    assert isinstance(p[6], sa.VarKeyword) and p[6].name == "kw"
    # All are Param subclasses
    assert all(isinstance(pi, sa.Param) for pi in p)
    print("  parameters OK")


# ── Statements ───────────────────────────────────────────────────────────────

def test_import_flattening():
    ss = stmts("import os, sys")
    assert len(ss) == 2
    assert isinstance(ss[0], sa.Import) and ss[0].module == "os"
    assert isinstance(ss[1], sa.Import) and ss[1].module == "sys"
    ss = stmts("from os.path import join, exists")
    assert len(ss) == 2
    assert isinstance(ss[0], sa.ImportFrom) and ss[0].name == "join" and ss[0].module == "os.path"
    ss = stmts("import numpy as np")
    assert ss[0].alias == "np"
    ss = stmts("from . import foo")
    assert ss[0].level == 1
    print("  import flattening OK")


def test_delete_flattening():
    ss = stmts("del x, y.a, z[0]")
    assert len(ss) == 3
    assert isinstance(ss[0], sa.DeleteName)
    assert isinstance(ss[1], sa.DeleteAttr)
    assert isinstance(ss[2], sa.DeleteSubscript)
    print("  delete flattening OK")


def test_compound_stmts():
    s = stmt("if x:\n  pass\nelif y:\n  pass\nelse:\n  pass")
    assert isinstance(s, sa.If) and isinstance(s.orelse[0], sa.If)
    s = stmt("while True:\n  break")
    assert isinstance(s, sa.While)
    s = stmt("for x in y:\n  continue")
    assert isinstance(s, sa.For) and s.is_async is False
    s = stmt("with open('f') as fh:\n  pass")
    assert isinstance(s, sa.With) and len(s.items) == 1
    s = stmt("try:\n  pass\nexcept ValueError as e:\n  pass\nfinally:\n  pass")
    assert isinstance(s, sa.Try) and len(s.handlers) == 1 and s.handlers[0].name == "e"
    print("  compound statements OK")


def test_async():
    s = stmt("async def f():\n  pass")
    assert isinstance(s, sa.FunctionDef) and s.is_async is True
    s = stmt("async def f():\n  async for x in y:\n    pass")
    assert isinstance(s.body[0], sa.For) and s.body[0].is_async is True
    s = stmt("async def f():\n  async with ctx() as c:\n    pass")
    assert isinstance(s.body[0], sa.With) and s.body[0].is_async is True
    print("  async OK")


def test_class():
    s = stmt("class Foo(Bar, metaclass=Meta):\n  pass")
    assert isinstance(s, sa.ClassDef) and s.name == "Foo"
    assert len(s.bases) == 1 and isinstance(s.bases[0], sa.LoadName)
    assert len(s.keywords) == 1 and s.keywords[0].name == "metaclass"
    print("  class OK")


def test_decorators():
    s = stmt("@deco\ndef f(): pass")
    assert isinstance(s, sa.FunctionDef) and len(s.decorators) == 1
    print("  decorators OK")


def test_ann_assign():
    s = stmt("x: int = 1")
    assert isinstance(s, sa.AnnAssign) and isinstance(s.annotation, sa.LoadName)
    print("  annotated assign OK")

def test_raise():
    s = stmt("raise ValueError('bad') from err")
    assert isinstance(s, sa.Raise) and s.exc is not None and s.cause is not None
    print("  raise OK")

def test_assert():
    s = stmt("assert x, 'msg'")
    assert isinstance(s, sa.assertz) and s.msg is not None
    print("  assert OK")

def test_global_nonlocal():
    assert isinstance(stmt("global x, y"), sa.Global)
    assert isinstance(stmt("nonlocal z"), sa.Nonlocal)
    print("  global/nonlocal OK")

def test_multi_assign():
    s = stmt("a = b = 1")
    assert isinstance(s, sa.Assign) and len(s.targets) == 2
    print("  multi assign OK")


# ── Match ────────────────────────────────────────────────────────────────────

def test_match():
    src = """
match command:
    case "quit":
        pass
    case [x, *rest]:
        pass
    case {"action": action}:
        pass
    case Point(x=x, y=y):
        pass
    case None:
        pass
    case x if x > 0:
        pass
    case a | b:
        pass
"""
    s = stmt(src)
    assert isinstance(s, sa.Match) and len(s.cases) == 7
    assert isinstance(s.cases[0].pattern, sa.MatchLiteral)
    assert isinstance(s.cases[1].pattern, sa.MatchSequence)
    assert isinstance(s.cases[2].pattern, sa.MatchMapping)
    assert isinstance(s.cases[3].pattern, sa.MatchClass)
    assert isinstance(s.cases[4].pattern, sa.MatchLiteral) and s.cases[4].pattern.use_is is True
    assert s.cases[5].guard is not None
    assert isinstance(s.cases[6].pattern, sa.MatchOr)
    print("  match OK")


# ── Infrastructure ───────────────────────────────────────────────────────────

def test_loc_preserved():
    s = stmt("x = 1")
    lineno, col_offset, *_ = s.position
    assert lineno == 1 and col_offset == 0
    print("  location preserved OK")

def test_dump():
    d = sa.dump(sa.simplify(ast.parse("x + 1")))
    assert "Add" in d and "LoadName" in d and "IntLiteral" in d
    print("  dump OK")

def test_children():
    node = sa.Add(
        left=sa.LoadName(name="x"),
        right=sa.IntLiteral(value=1)
    )
    kids = node.children()
    assert len(kids) == 2
    assert isinstance(kids[0], sa.LoadName) and isinstance(kids[1], sa.IntLiteral)
    print("  children OK")

# def test_node_transformer():
#     class DoubleInts(sa.NodeTransformer):
#         def visit_IntLiteral(self, node):
#             return sa.IntLiteral(value=node.value * 2)

#     tree = sa.simplify(ast.parse("x = 1 + 2"))
#     tree = DoubleInts().visit(tree)
#     assign = tree.body[0]
#     add = assign.value
#     assert isinstance(add, sa.Add)
#     assert add.left.value == 2 and add.right.value == 4
#     print("  node transformer OK")


# ── Generated methods (node_class) ───────────────────────────────────────────

def test_call_copy():
    """__call__ returns a copy with selectively replaced fields."""
    orig = sa.Add(left=sa.LoadName(name="x"), right=sa.IntLiteral(value=1))
    # Replace only right
    updated = orig(right=sa.IntLiteral(value=99))
    assert updated.right.value == 99
    assert updated.left is orig.left      # left carried over, same object
    assert updated is not orig
    # Replace nothing — all fields carried over
    same = orig()
    assert same.left is orig.left
    assert same.right is orig.right
    assert same is not orig
    print("  __call__ copy OK")


def test_call_copy_list_field():
    """__call__ on a node with a list field."""
    node = sa.Module(body=[sa.LoadName(name="a"), sa.LoadName(name="b")])
    updated = node(body=[sa.LoadName(name="c")])
    assert len(updated.body) == 1
    assert updated.body[0].name == "c"
    assert len(node.body) == 2   # original unchanged
    print("  __call__ copy list field OK")


def test_visit_children_list_field():
    """visit_children traverses elements of list[Node] fields."""
    module = sa.simplify(ast.parse("a\nb\nc"))
    visited = []
    module.visit_children(visited.append)
    assert len(visited) == 3
    assert all(isinstance(n, sa.LoadName) for n in visited)
    assert [n.name for n in visited] == ["a", "b", "c"]
    print("  visit_children list field OK")


def test_visit_children_node_fields():
    """visit_children visits both node fields of a BinOp."""
    add = sa.Add(left=sa.LoadName(name="x"), right=sa.IntLiteral(value=1))
    visited = []
    add.visit_children(visited.append)
    assert len(visited) == 2
    assert isinstance(visited[0], sa.LoadName)
    assert isinstance(visited[1], sa.IntLiteral)
    print("  visit_children node fields OK")


def test_visit_children_optional_node():
    """visit_children visits an Optional[Node] field only when set."""
    ret_val = sa.simplify(ast.parse("def f():\n return 1")).body[0].body[0]
    assert isinstance(ret_val, sa.Return)
    visited = []
    ret_val.visit_children(visited.append)
    assert len(visited) == 1 and isinstance(visited[0], sa.IntLiteral)

    ret_bare = sa.simplify(ast.parse("def f():\n return")).body[0].body[0]
    assert isinstance(ret_bare, sa.Return)
    visited2 = []
    ret_bare.visit_children(visited2.append)
    assert len(visited2) == 0
    print("  visit_children optional node OK")


def test_transform_children_replaces_nodes():
    """transform_children replaces matched children and returns new node."""
    add = sa.simplify(ast.parse("x + 1")).body[0]
    assert isinstance(add, sa.Add)

    def swap_int(n):
        if isinstance(n, sa.IntLiteral):
            return sa.IntLiteral(value=42)
        return n

    new_add = add.transform_children(swap_int)
    assert isinstance(new_add, sa.Add)
    assert new_add.right.value == 42
    assert isinstance(new_add.left, sa.LoadName)
    print("  transform_children replaces nodes OK")


def test_transform_children_identity():
    """transform_children returns self when nothing changes (no allocation)."""
    add = sa.Add(left=sa.LoadName(name="x"), right=sa.IntLiteral(value=1))
    result = add.transform_children(lambda n: n)
    assert result is add
    print("  transform_children identity OK")


def test_transform_children_list_field():
    """transform_children transforms elements inside a list[Node] field."""
    func = sa.simplify(ast.parse("def f():\n a\n b")).body[0]
    assert isinstance(func, sa.FunctionDef)

    def rename(n):
        if isinstance(n, sa.LoadName):
            return sa.LoadName(name=n.name.upper())
        return n

    new_func = func.transform_children(rename)
    assert isinstance(new_func, sa.FunctionDef)
    assert new_func.body[0].name == "A"
    assert new_func.body[1].name == "B"
    print("  transform_children list field OK")


def test_transform_fields():
    """transform_fields returns self when nothing changed, copy otherwise."""
    node = sa.Add(left=sa.LoadName(name="x"), right=sa.IntLiteral(value=1))
    same = node.transform_fields(left=node.left, right=node.right)
    assert same is node

    new_right = sa.IntLiteral(value=2)
    updated = node.transform_fields(right=new_right)
    assert updated is not node
    assert updated.right.value == 2
    assert updated.left is node.left
    print("  transform_fields OK")


# ── More simplify cases ───────────────────────────────────────────────────────

def test_yield_from():
    s = stmt("def f():\n yield from it")
    assert isinstance(s, sa.FunctionDef)
    assert isinstance(s.body[0], sa.YieldFrom)
    assert isinstance(s.body[0].value, sa.LoadName)
    print("  yield from OK")


def test_await():
    s = stmt("async def f():\n await coro()")
    assert isinstance(s, sa.FunctionDef) and s.is_async
    assert isinstance(s.body[0], sa.Await)
    assert isinstance(s.body[0].value, sa.Call)
    print("  await OK")


def test_try_star():
    try:
        s = stmt("try:\n pass\nexcept* ValueError as eg:\n pass")
        assert isinstance(s, sa.Try) and s.is_star is True
        assert len(s.handlers) == 1 and s.handlers[0].name == "eg"
        print("  try/except* OK")
    except SyntaxError:
        print("  try/except* skipped (Python < 3.11)")


def test_type_alias():
    try:
        s = stmt("type Vector = list[float]")
        assert isinstance(s, sa.TypeAlias)
        assert isinstance(s.name, sa.StoreName) and s.name.name == "Vector"
        print("  type alias OK")
    except SyntaxError:
        print("  type alias skipped (Python < 3.12)")


def test_type_params():
    try:
        s = stmt("def f[T, **P, *Ts](): pass")
        assert isinstance(s, sa.FunctionDef)
        tp = s.type_params
        assert any(isinstance(p, sa.TypeVar) for p in tp)
        assert any(isinstance(p, sa.ParamSpec) for p in tp)
        assert any(isinstance(p, sa.TypeVarTuple) for p in tp)
        print("  type params OK")
    except SyntaxError:
        print("  type params skipped (Python < 3.12)")


def test_fstring_conversion_and_format_spec():
    node = expr("f'{val!r:.2f}'")
    assert isinstance(node, sa.FString)
    fe = node.parts[0]
    assert isinstance(fe, sa.FormattedExpr)
    assert fe.conversion == "r"
    assert fe.format_spec is not None
    print("  fstring conversion+format_spec OK")


def test_slice_partial():
    """Slice with missing parts should have None for those components."""
    s = expr("x[::2]")
    assert isinstance(s.index, sa.Slice)
    assert s.index.lower is None
    assert s.index.upper is None
    assert isinstance(s.index.step, sa.IntLiteral)
    print("  partial slice OK")


def test_compare_chain_shared_operand():
    """Middle operand in 1 < x < 10 should be the same StoreName/LoadName object."""
    node = expr("1 < x < 10")
    assert isinstance(node, sa.CompareChain)
    left_cmp, right_cmp = node.comparisons
    assert isinstance(left_cmp, sa.Lt) and isinstance(right_cmp, sa.Lt)
    # The shared middle operand 'x' should appear as right of first and left of second
    assert isinstance(left_cmp.right, sa.LoadName) and left_cmp.right.name == "x"
    assert isinstance(right_cmp.left, sa.LoadName) and right_cmp.left.name == "x"
    print("  compare chain shared operand OK")


def test_multi_for_comprehension():
    """Nested for-in comprehension produces multiple ForClause entries."""
    lc = expr("[x for xs in xss for x in xs if x > 0]")
    assert isinstance(lc, sa.ListComp)
    assert len(lc.clauses) == 2
    assert isinstance(lc.clauses[0], sa.ForClause)
    assert isinstance(lc.clauses[1], sa.ForClause)
    assert len(lc.clauses[1].filters) == 1
    print("  multi-for comprehension OK")


def test_for_clause_children():
    """ForClause.filters is visited as a list[Node] field."""
    fc_node = sa.simplify(ast.parse("[x for x in y if x > 0 if x < 10]")).body[0]
    assert isinstance(fc_node, sa.ListComp)
    fc = fc_node.clauses[0]
    assert isinstance(fc, sa.ForClause)
    assert len(fc.filters) == 2
    visited = []
    fc.visit_children(visited.append)
    # Should visit: target, iterable, and both filters
    assert any(isinstance(n, sa.StoreName) for n in visited)   # target
    assert any(isinstance(n, sa.LoadName) for n in visited)    # iterable
    assert sum(isinstance(n, sa.Gt) or isinstance(n, sa.Lt) for n in visited) == 2
    print("  ForClause filters visited OK")


def test_match_star_and_as():
    src = """
match x:
    case [*rest]:
        pass
    case _ as y:
        pass
    case _:
        pass
"""
    s = stmt(src)
    assert isinstance(s, sa.Match)
    assert isinstance(s.cases[0].pattern, sa.MatchSequence)
    assert isinstance(s.cases[0].pattern.patterns[0], sa.MatchStar)
    assert s.cases[0].pattern.patterns[0].name == "rest"
    assert isinstance(s.cases[1].pattern, sa.MatchAs)
    assert s.cases[1].pattern.name == "y"
    assert isinstance(s.cases[2].pattern, sa.MatchAs)
    assert s.cases[2].pattern.name is None   # bare _
    print("  MatchStar and MatchAs OK")


def test_yield_bare():
    s = stmt("def f():\n yield")
    assert isinstance(s, sa.FunctionDef)
    y = s.body[0]
    assert isinstance(y, sa.Yield) and y.value is None
    print("  bare yield OK")


def test_exception_tuple():
    """except (A, B) produces a single handler whose type is a tuple load."""
    s = stmt("try:\n pass\nexcept (ValueError, TypeError):\n pass")
    assert isinstance(s, sa.Try) and len(s.handlers) == 1
    assert s.handlers[0].type is not None
    print("  exception tuple OK")


import ast as _ast
from clausal.pythonic_ast import conversion_from_python_ast as conversion
def test_visit_dispatch():
    """Verify VISITORS dict has direct hash lookup, not name mangling."""
    # Every entry in VISITORS should map an ast type directly
    for ast_type, func in conversion.VISITORS.items():
        assert isinstance(ast_type, type) and issubclass(ast_type, _ast.AST), \
            f"Key {ast_type} is not an ast.AST subclass"
        assert callable(func), f"Value for {ast_type} is not callable"
    print("  visit dispatch OK")


def test_big_real_code():
    """Smoke test: simplify substantial Python, verify no CPython nodes leak."""
    import textwrap
    src = textwrap.dedent('''
        import os
        from pathlib import Path
        from typing import Optional, List

        class Config:
            _instance = None
            def __init__(self, path: str = "config.yaml", debug: bool = False):
                self.path = Path(path)
                self.debug = debug
                self._data: dict = {}

            @classmethod
            def get_instance(cls) -> "Config":
                if cls._instance is None:
                    cls._instance = cls()
                return cls._instance

            def load(self) -> None:
                if not self.path.exists():
                    raise FileNotFoundError(f"Config not found: {self.path}")
                with open(self.path) as f:
                    self._data = {}

            def get(self, key: str, default=None):
                return self._data.get(key, default)

        def process_items(items: List[str], *, verbose: bool = False) -> list:
            results = []
            for i, item in enumerate(items):
                if not item.strip():
                    continue
                processed = item.upper() if verbose else item.lower()
                results.append(processed)
                if verbose:
                    print(f"Item {i}: {processed!r}")
            return results

        async def fetch_all(urls):
            tasks = [fetch(url) for url in urls]
            results = {url: result for url, result in zip(urls, tasks)}
            return results

        def complex_expressions():
            a = x + y * z ** 2
            b = (a > 0) and (a < 100) or (a == -1)
            c = [i for i in range(10) if i % 2 == 0]
            d = {k: v for k, v in items.items() if k not in excluded}
            e = value if condition else alternative
            f = lambda x, y: x + y
            g, *rest = [1, 2, 3, 4, 5]
            x += 1
            x //= 2
            x |= mask
            del a, b

        try:
            result = dangerous()
        except (ValueError, TypeError) as e:
            print(e)
        except Exception:
            raise
        finally:
            cleanup()
    ''')
    tree = sa.simplify(ast.parse(src))
    assert isinstance(tree, sa.Module) and len(tree.body) > 5

    def walk(node):
        assert not isinstance(node, ast.AST), f"Leaked CPython node: {type(node)}"
        if isinstance(node, sa.Node):
            node.visit_children(walk)
    walk(tree)

    d = sa.dump(tree)
    assert len(d) > 500
    print("  big real code OK")


# ── __str__ (Python-like display) ────────────────────────────────────────────

def test_str_literals():
    assert str(sa.IntLiteral(value=42)) == "42"
    assert str(sa.FloatLiteral(value=3.14)) == "3.14"
    assert str(sa.BoolLiteral(value=True)) == "True"
    assert str(sa.BoolLiteral(value=False)) == "False"
    assert str(sa.NoneLiteral()) == "None"
    assert str(sa.EllipsisLiteral()) == "..."
    assert str(sa.StringLiteral(value="hi")) == "'hi'"
    assert str(sa.BytesLiteral(value=b"hi")) == "b'hi'"
    # also via round-trip
    assert str(expr("42")) == "42"
    assert str(expr("True")) == "True"
    assert str(expr("None")) == "None"
    assert str(expr("...")) == "..."
    print("  str literals OK")


def test_str_collections():
    assert str(expr("[1, 2, 3]")) == "[1, 2, 3]"
    assert str(expr("[]")) == "[]"
    assert str(expr("()")) == "()"
    assert str(expr("(1,)")) == "(1,)"
    assert str(expr("(1, 2)")) == "(1, 2)"
    assert str(expr("{1, 2}")) == "{1, 2}"
    assert str(expr("{1: 2, 3: 4}")) == "{1: 2, 3: 4}"
    assert str(expr("{**x}")) == "{**x}"
    assert str(expr("{1: 2, **x}")) == "{1: 2, **x}"
    print("  str collections OK")


def test_str_names_attrs():
    assert str(expr("x")) == "x"
    assert str(expr("x.a")) == "x.a"
    assert str(expr("x.a.b")) == "x.a.b"
    assert str(expr("x[0]")) == "x[0]"
    assert str(expr("x[0].a")) == "x[0].a"
    print("  str names/attrs OK")


def test_str_star():
    assert str(sa.StarUnpack(value=sa.LoadName(name="args"))) == "*args"
    assert str(sa.StarTarget(target=sa.StoreName(name="rest"))) == "*rest"
    s = stmt("a, *b = [1, 2, 3]")
    assert str(s.targets[0]) == "a, *b"
    s = stmt("[a, *b] = [1, 2, 3]")
    assert str(s.targets[0]) == "[a, *b]"
    print("  str star OK")


def test_str_binops():
    assert str(expr("x + y")) == "x + y"
    assert str(expr("x - y")) == "x - y"
    assert str(expr("x * y")) == "x * y"
    assert str(expr("x / y")) == "x / y"
    assert str(expr("x // y")) == "x // y"
    assert str(expr("x % y")) == "x % y"
    assert str(expr("x ** y")) == "x ** y"
    assert str(expr("x & y")) == "x & y"
    assert str(expr("x | y")) == "x | y"
    assert str(expr("x ^ y")) == "x ^ y"
    assert str(expr("x << y")) == "x << y"
    assert str(expr("x >> y")) == "x >> y"
    print("  str binops OK")


def test_str_boolops():
    assert str(expr("a and b")) == "a and b"
    assert str(expr("a or b")) == "a or b"
    print("  str boolops OK")


def test_str_unaryops():
    assert str(expr("-x")) == "-x"
    assert str(expr("+x")) == "+x"
    assert str(expr("~x")) == "~x"
    assert str(expr("not x")) == "not x"
    # BinOp operand gets parenthesised
    node = sa.Negate(operand=sa.Add(
        left=sa.LoadName(name="a"), right=sa.LoadName(name="b")))
    assert str(node) == "-(a + b)"
    node = sa.Not(operand=sa.And(
        left=sa.LoadName(name="a"), right=sa.LoadName(name="b")))
    assert str(node) == "not (a and b)"
    print("  str unaryops OK")


def test_str_comparisons():
    assert str(expr("x == y")) == "x == y"
    assert str(expr("x != y")) == "x != y"
    assert str(expr("x < y")) == "x < y"
    assert str(expr("x <= y")) == "x <= y"
    assert str(expr("x > y")) == "x > y"
    assert str(expr("x >= y")) == "x >= y"
    assert str(expr("x is y")) == "x is y"
    assert str(expr("x is not y")) == "x is not y"
    assert str(expr("x in y")) == "x in y"
    assert str(expr("x not in y")) == "x not in y"
    assert str(expr("1 < x < 10")) == "1 < x < 10"
    print("  str comparisons OK")


def test_str_call():
    assert str(expr("f()")) == "f()"
    assert str(expr("f(1, 2)")) == "f(1, 2)"
    assert str(expr("f(1, *args, key=val, **kw)")) == "f(1, *args, key=val, **kw)"
    assert str(expr("a.b(x)")) == "a.b(x)"
    print("  str call OK")


def test_str_ifexpr():
    assert str(expr("a if b else c")) == "a if b else c"
    print("  str ifexpr OK")


def test_str_walrus():
    assert str(expr("(x := 10)")) == "(x := 10)"
    print("  str walrus OK")


def test_str_lambda():
    assert str(expr("lambda: 1")) == "lambda: 1"
    assert str(expr("lambda x, y: x + y")) == "lambda x, y: x + y"
    assert str(expr("lambda x=1: x")) == "lambda x=1: x"
    print("  str lambda OK")


def test_str_params():
    s = stmt("def f(a, b, /, c=2, *args, d, e=3, **kw): pass")
    assert str(s.params) == "a, b, /, c=2, *args, d, e=3, **kw"
    s = stmt("def f(*args, x): pass")
    assert str(s.params) == "*args, x"
    s = stmt("def f(*, x): pass")
    assert str(s.params) == "*, x"
    print("  str params OK")


def test_str_yield():
    s = stmt("def f():\n yield")
    assert str(s.body[0]) == "yield"
    s = stmt("def f():\n yield 1")
    assert str(s.body[0]) == "yield 1"
    s = stmt("def f():\n yield from it")
    assert str(s.body[0]) == "yield from it"
    print("  str yield OK")


def test_str_await():
    s = stmt("async def f():\n await coro()")
    assert str(s.body[0]) == "await coro()"
    print("  str await OK")


def test_str_slice():
    assert str(expr("x[1:2]").index) == "1:2"
    assert str(expr("x[1:2:3]").index) == "1:2:3"
    assert str(expr("x[::2]").index) == "::2"
    assert str(expr("x[1:]").index) == "1:"
    assert str(expr("x[:5]").index) == ":5"
    print("  str slice OK")


def test_str_comprehensions():
    assert str(expr("[x for x in y]")) == "[x for x in y]"
    assert str(expr("[x for x in y if x > 0]")) == "[x for x in y if x > 0]"
    assert str(expr("{x for x in y}")) == "{x for x in y}"
    assert str(expr("(x for x in y)")) == "(x for x in y)"
    assert str(expr("{k: v for k, v in items}")) == "{k: v for k, v in items}"
    assert str(expr("[x for xs in xss for x in xs]")) == "[x for xs in xss for x in xs]"
    print("  str comprehensions OK")


def test_str_fstring():
    assert str(expr("f'hello {name}'")) == 'f"hello {name}"'
    assert str(expr("f'{val!r}'")) == 'f"{val!r}"'
    assert str(expr("f'{val:.2f}'")) == 'f"{val:.2f}"'
    assert str(expr("f'{val!r:.2f}'")) == 'f"{val!r:.2f}"'
    assert str(expr("f'x={x} y={y}'")) == 'f"x={x} y={y}"'
    print("  str fstring OK")


def test_str_combined():
    """A handful of realistic expressions."""
    assert str(expr("x == 1 + y")) == "x == 1 + y"
    assert str(expr("a.b[0](x, y=1)")) == "a.b[0](x, y=1)"
    assert str(expr("[i * 2 for i in range(10) if i % 2 == 0]")) == \
        "[i * 2 for i in range(10) if i % 2 == 0]"
    print("  str combined OK")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            failed += 1
            import traceback
            print(f"  FAIL {test.__name__}: {e}")
            traceback.print_exc()
    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed out of {passed+failed}")
    if failed:
        sys.exit(1)
    else:
        print("All tests passed!")
