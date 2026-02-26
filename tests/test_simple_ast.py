"""Tests for simple_ast."""
import ast
import sys
import simple_ast as sa


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
    # In a function body too
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
    assert isinstance(expr("x == y"), sa.Eq)
    assert isinstance(expr("x != y"), sa.NotEq)
    assert isinstance(expr("x < y"), sa.Lt)
    assert isinstance(expr("x <= y"), sa.LtE)
    assert isinstance(expr("x > y"), sa.Gt)
    assert isinstance(expr("x >= y"), sa.GtE)
    assert isinstance(expr("x is y"), sa.Is)
    assert isinstance(expr("x is not y"), sa.IsNot)
    assert isinstance(expr("x in y"), sa.In)
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
    assert isinstance(s, sa.Assert) and s.msg is not None
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
    assert s.position.lineno == 1 and s.position.col_offset == 0
    print("  location preserved OK")

def test_dump():
    d = sa.dump(sa.simplify(ast.parse("x + 1")))
    assert "Add" in d and "LoadName" in d and "IntLiteral" in d
    print("  dump OK")

def test_children():
    node = sa.Add(left=sa.LoadName(name="x"), right=sa.IntLiteral(value=1))
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


import ast as _ast
import conversion
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
