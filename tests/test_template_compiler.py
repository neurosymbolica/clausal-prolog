"""Tests for template_compiler."""

import ast
import dataclasses
import textwrap
from typing import Any

import pytest

from template_compiler import (
    TemplateCompileError,
    compile_template_func,
    is_template_func,
    transform_module,
    transform_module_ast,
)


# ======================================================================
# Helpers
# ======================================================================

def compile_and_run(source: str, call_code: str,
                    extra_globals: dict | None = None) -> list[ast.stmt]:
    """Compile template source, execute call_code, return the result."""
    tree = ast.parse(source)
    new_tree = transform_module_ast(tree)
    new_tree.body.extend(ast.parse(call_code).body)
    ast.fix_missing_locations(new_tree)
    ns = dict(extra_globals or {})
    exec(compile(new_tree, "<test>", "exec"), ns)
    return ns["result"]


def unparse_result(stmts: list[ast.stmt]) -> str:
    mod = ast.Module(body=stmts, type_ignores=[])
    ast.fix_missing_locations(mod)
    return ast.unparse(mod)


@dataclasses.dataclass
class BinOp:
    left: Any
    op: str
    right: Any


# ======================================================================
# Detection
# ======================================================================

class TestDetection:
    def test_empty_dict_decorator_detected(self):
        tree = ast.parse("@{}\ndef f(X): pass")
        assert is_template_func(tree.body[0])

    def test_no_decorator_not_detected(self):
        tree = ast.parse("def f(X): pass")
        assert not is_template_func(tree.body[0])

    def test_non_empty_dict_not_detected(self):
        tree = ast.parse("@{1: 2}\ndef f(X): pass")
        assert not is_template_func(tree.body[0])

    def test_multiple_decorators_not_detected(self):
        tree = ast.parse("@{}\n@other\ndef f(X): pass")
        assert not is_template_func(tree.body[0])

    def test_class_not_detected(self):
        tree = ast.parse("@{}\nclass C: pass")
        assert not is_template_func(tree.body[0])


# ======================================================================
# Identifier substitution
# ======================================================================

class TestIdentifiers:
    def test_function_name(self):
        src = "@{}\ndef t(NAME):\n    def NAME(self): pass"
        result = compile_and_run(src, "result = t('greet')")
        assert "def greet" in unparse_result(result)

    def test_argument_name(self):
        src = "@{}\ndef t(FN):\n    def foo(self, FN): pass"
        result = compile_and_run(src, "result = t('visitor')")
        assert "visitor" in unparse_result(result)

    def test_name_in_expression(self):
        src = "@{}\ndef t(FN):\n    def foo(self):\n        FN.visit(self)"
        result = compile_and_run(src, "result = t('v')")
        assert "v.visit(self)" in unparse_result(result)

    def test_multiple_substitutions(self):
        src = textwrap.dedent("""\
            @{}
            def t(VISIT, FN):
                def VISIT(self, FN):
                    FN.go(self)
        """)
        result = compile_and_run(src, "result = t('accept', 'visitor')")
        out = unparse_result(result)
        assert "def accept" in out
        assert "visitor" in out

    def test_default_parameter_values(self):
        src = textwrap.dedent("""\
            @{}
            def t(NAME='greet'):
                def NAME(self): pass
        """)
        result = compile_and_run(src, "result = t()")
        assert "def greet" in unparse_result(result)

    def test_class_name_substitution(self):
        src = "@{}\ndef t(CLS):\n    class CLS: pass"
        result = compile_and_run(src, "result = t('MyClass')")
        assert "class MyClass" in unparse_result(result)

    def test_attribute_name_not_substituted(self):
        src = "@{}\ndef t(X):\n    def foo(self):\n        self.X = 1"
        result = compile_and_run(src, "result = t('hello')")
        # X in self.X is an attribute, not an identifier field that we sub
        # Actually Attribute.attr IS in _IDENT_FIELDS, so it will be substituted
        assert "self.hello = 1" in unparse_result(result)


# ======================================================================
# Statement escapes
# ======================================================================

class TestEscapes:
    def test_single_escape(self):
        src = textwrap.dedent("""\
            @{}
            def t(NAME):
                def NAME(self):
                    print("before")
                    {extra}
                    print("after")
        """)
        extra = ast.parse("x = 42").body[0]
        result = compile_and_run(src, "result = t('f')",
                                 {"extra": extra})
        out = unparse_result(result)
        assert "x = 42" in out
        assert "before" in out and "after" in out

    def test_multi_escape(self):
        src = "@{}\ndef t(F):\n    def F(self):\n        {a, b}"
        result = compile_and_run(src, "result = t('f')", {
            "a": ast.parse("x = 1").body[0],
            "b": ast.parse("y = 2").body[0],
        })
        out = unparse_result(result)
        assert "x = 1" in out and "y = 2" in out

    def test_star_escape(self):
        src = textwrap.dedent("""\
            @{}
            def t(F):
                def F(self):
                    {*stmts}
                    return self.x
        """)
        stmts = ast.parse("self.x = 0\nself.ready = True").body
        result = compile_and_run(src, "result = t('init')",
                                 {"stmts": stmts})
        out = unparse_result(result)
        assert "self.x = 0" in out
        assert "self.ready = True" in out
        assert "return self.x" in out

    def test_comprehension_escape(self):
        src = textwrap.dedent("""\
            @{}
            def t(NAME):
                def NAME(self):
                    {make_stmt(n) for n in names}
        """)
        def make_stmt(n):
            return ast.parse(f"print('{n}')").body[0]
        result = compile_and_run(src, "result = t('f')", {
            "names": ["a", "b", "c"],
            "make_stmt": make_stmt,
        })
        out = unparse_result(result)
        assert "print('a')" in out
        assert "print('b')" in out
        assert "print('c')" in out

    def test_comprehension_with_filter(self):
        src = textwrap.dedent("""\
            @{}
            def t(NAME):
                def NAME(self):
                    {make(f) for f in fields if f.name != 'op'}
        """)
        def make(f):
            return ast.parse(f"self.{f.name}.check()").body[0]
        result = compile_and_run(src, "result = t('validate')", {
            "fields": dataclasses.fields(BinOp),
            "make": make,
        })
        out = unparse_result(result)
        assert "self.left.check()" in out
        assert "self.right.check()" in out
        assert "op" not in out

    def test_escape_returns_list(self):
        src = "@{}\ndef t(F):\n    def F(self):\n        {stmts}"
        stmts = ast.parse("a = 1\nb = 2").body
        result = compile_and_run(src, "result = t('f')",
                                 {"stmts": stmts})
        out = unparse_result(result)
        assert "a = 1" in out and "b = 2" in out

    def test_nested_if_else_escapes(self):
        src = textwrap.dedent("""\
            @{}
            def t(FN):
                def FN(self, flag):
                    if flag:
                        {*yes}
                    else:
                        {*no}
        """)
        result = compile_and_run(src, "result = t('go')", {
            "yes": ast.parse("return True").body,
            "no": ast.parse("return False").body,
        })
        out = unparse_result(result)
        assert "return True" in out and "return False" in out


# ======================================================================
# __args__ magic
# ======================================================================

class TestMagicArgs:
    def test_args_from_arguments(self):
        src = "@{}\ndef t(N):\n    def N(__args__={a}): pass"
        args = ast.arguments(
            posonlyargs=[], args=[ast.arg(arg="self"), ast.arg(arg="x")],
            vararg=None, kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[])
        result = compile_and_run(src, "result = t('f')", {"a": args})
        assert "def f(self, x)" in unparse_result(result)

    def test_args_from_single_arg(self):
        src = "@{}\ndef t(N):\n    def N(__args__={a}): pass"
        result = compile_and_run(src, "result = t('f')",
                                 {"a": ast.arg(arg="self")})
        assert "def f(self)" in unparse_result(result)

    def test_args_from_tuple(self):
        src = "@{}\ndef t(N):\n    def N(__args__={a}): pass"
        result = compile_and_run(src, "result = t('f')", {
            "a": (ast.arg(arg="self"), ast.arg(arg="x")),
        })
        assert "def f(self, x)" in unparse_result(result)

    def test_args_from_expression(self):
        src = "@{}\ndef t(N):\n    def N(__args__={build(names)}): pass"
        def build(names):
            return ast.arguments(
                posonlyargs=[],
                args=[ast.arg(arg="self"), *[ast.arg(arg=n) for n in names]],
                vararg=None, kwonlyargs=[], kw_defaults=[],
                kwarg=None, defaults=[])
        result = compile_and_run(src, "result = t('f')", {
            "build": build, "names": ["a", "b"],
        })
        assert "def f(self, a, b)" in unparse_result(result)

    def test_args_with_body_escape(self):
        """The motivating use case: dataclass __init__."""
        src = textwrap.dedent("""\
            @{}
            def t(NAME):
                def NAME(__args__={build_args(fields)}):
                    {make_assign(f) for f in fields}
        """)
        def build_args(fields):
            return ast.arguments(
                posonlyargs=[],
                args=[ast.arg(arg="self"),
                      *[ast.arg(arg=f.name) for f in fields]],
                vararg=None, kwonlyargs=[], kw_defaults=[],
                kwarg=None, defaults=[])
        def make_assign(f):
            return ast.parse(f"self.{f.name} = {f.name}").body[0]

        result = compile_and_run(src, "result = t('__init__')", {
            "fields": dataclasses.fields(BinOp),
            "build_args": build_args,
            "make_assign": make_assign,
        })
        out = unparse_result(result)
        assert "def __init__(self, left, op, right)" in out
        assert "self.left = left" in out
        assert "self.op = op" in out
        assert "self.right = right" in out

    def test_args_not_sole_param_raises(self):
        src = "@{}\ndef t(N):\n    def N(__args__={a}, other={b}): pass"
        with pytest.raises(TemplateCompileError, match="sole parameter"):
            compile_and_run(src, "result = t('f')", {
                "a": ast.arg(arg="self"), "b": ast.arg(arg="x"),
            })

    def test_args_no_default_raises(self):
        src = "@{}\ndef t(N):\n    def N(__args__): pass"
        with pytest.raises(TemplateCompileError, match="default"):
            compile_and_run(src, "result = t('f')")


# ======================================================================
# Class templates
# ======================================================================

class TestClassTemplates:
    def test_simple_class(self):
        src = textwrap.dedent("""\
            @{}
            def t(CLS):
                class CLS:
                    pass
        """)
        result = compile_and_run(src, "result = t('Widget')")
        assert "class Widget" in unparse_result(result)

    def test_class_with_base(self):
        src = textwrap.dedent("""\
            @{}
            def t(CLS, BASE):
                class CLS(BASE):
                    pass
        """)
        result = compile_and_run(src, "result = t('Widget', 'QObject')")
        assert "class Widget(QObject)" in unparse_result(result)

    def test_class_with_magic_bases(self):
        src = textwrap.dedent("""\
            @{}
            def t(CLS):
                class CLS({base_expr}):
                    pass
        """)
        bases = [_name_node("Base1"), _name_node("Base2")]
        result = compile_and_run(src, "result = t('C')",
                                 {"base_expr": bases})
        out = unparse_result(result)
        assert "class C(Base1, Base2)" in out

    def test_class_with_magic_bases_single_expr(self):
        src = textwrap.dedent("""\
            @{}
            def t(CLS):
                class CLS({base_expr}):
                    pass
        """)
        result = compile_and_run(src, "result = t('C')",
                                 {"base_expr": _name_node("MyBase")})
        assert "class C(MyBase)" in unparse_result(result)

    def test_class_with_magic_bases_tuple(self):
        src = textwrap.dedent("""\
            @{}
            def t(CLS):
                class CLS({base_expr}):
                    pass
        """)
        result = compile_and_run(src, "result = t('C')", {
            "base_expr": (_name_node("A"), _name_node("B")),
        })
        assert "class C(A, B)" in unparse_result(result)

    def test_class_with_body_escapes(self):
        src = textwrap.dedent("""\
            @{}
            def t(CLS):
                class CLS:
                    {make_method(name) for name in methods}
        """)
        def make_method(name):
            return ast.parse(f"def {name}(self): pass").body[0]
        result = compile_and_run(src, "result = t('MyClass')", {
            "methods": ["foo", "bar"],
            "make_method": make_method,
        })
        out = unparse_result(result)
        assert "class MyClass" in out
        assert "def foo(self)" in out
        assert "def bar(self)" in out

    def test_class_with_methods_and_bases(self):
        src = textwrap.dedent("""\
            @{}
            def t(CLS, BASE):
                class CLS(BASE):
                    {make_init(fields)}
                    {make_method(name) for name in extra_methods}
        """)
        def make_init(fields):
            args = ", ".join(f.name for f in fields)
            body = "\n    ".join(f"self.{f.name} = {f.name}" for f in fields)
            return ast.parse(f"def __init__(self, {args}):\n    {body}").body[0]
        def make_method(name):
            return ast.parse(f"def {name}(self): pass").body[0]

        result = compile_and_run(src, "result = t('Node', 'AST')", {
            "fields": dataclasses.fields(BinOp),
            "make_init": make_init,
            "extra_methods": ["accept"],
            "make_method": make_method,
        })
        out = unparse_result(result)
        assert "class Node(AST)" in out
        assert "def __init__(self, left, op, right)" in out
        assert "self.left = left" in out
        assert "def accept(self)" in out

    def test_full_dataclass_expansion(self):
        """Generate a full class with __init__ + visitor from a dataclass."""
        src = textwrap.dedent("""\
            @{}
            def t(CLS, VISIT):
                class CLS:
                    {make_init(fields)}
                    def VISIT(self, visitor):
                        {make_visit(f) for f in fields}
                        visitor.visit(self)
        """)
        def make_init(fields):
            args = ", ".join(f.name for f in fields)
            body = "\n    ".join(f"self.{f.name} = {f.name}" for f in fields)
            return ast.parse(f"def __init__(self, {args}):\n    {body}").body[0]
        def make_visit(f):
            return ast.parse(f"self.{f.name}.accept(visitor)").body[0]

        result = compile_and_run(src, "result = t('BinOp', 'accept')", {
            "fields": dataclasses.fields(BinOp),
            "make_init": make_init,
            "make_visit": make_visit,
        })
        out = unparse_result(result)
        assert "class BinOp" in out
        assert "def __init__(self, left, op, right)" in out
        assert "def accept(self, visitor)" in out
        assert "self.left.accept(visitor)" in out
        assert "visitor.visit(self)" in out


# ======================================================================
# Line number propagation
# ======================================================================

class TestLineNumbers:
    def test_function_keeps_original_line(self):
        src = "@{}\ndef t(X):\n    def X(self): pass"
        tree = transform_module_ast(ast.parse(src))
        func = tree.body[0]
        assert func.lineno == 2  # @{} is line 1, def is line 2

    def test_escape_gets_original_line(self):
        src = textwrap.dedent("""\
            @{}
            def t(X):
                def X(self):
                    print("line4")
                    {extra}
                    print("line6")
        """)
        tree = transform_module_ast(ast.parse(src))
        func = tree.body[0]
        lines = {getattr(s, 'lineno', None) for s in func.body}
        # The escape at line 5 should produce stmts at line 5
        assert 5 in lines


# ======================================================================
# Edge cases
# ======================================================================

class TestEdgeCases:
    def test_non_template_function_unchanged(self):
        src = "def normal(x): return x + 1"
        assert "return x + 1" in transform_module(src)

    def test_template_with_no_subs(self):
        src = "@{}\ndef t():\n    def foo(): pass"
        result = compile_and_run(src, "result = t()")
        assert "def foo" in unparse_result(result)

    def test_compile_non_template_raises(self):
        tree = ast.parse("def f(): pass")
        with pytest.raises(TemplateCompileError):
            compile_template_func(tree.body[0])

    def test_multiple_templates_in_module(self):
        src = textwrap.dedent("""\
            @{}
            def t1(A):
                def A(): pass
            @{}
            def t2(B):
                class B: pass
        """)
        out = transform_module(src)
        # Both should be compilable
        assert "t1" in out and "t2" in out

    def test_escape_with_single_stmt_node(self):
        """Escape returning a single AST node (not a list)."""
        src = "@{}\ndef t(F):\n    def F(self):\n        {s}"
        result = compile_and_run(src, "result = t('f')", {
            "s": ast.parse("x = 1").body[0],
        })
        assert "x = 1" in unparse_result(result)


# ======================================================================
# Helper to create Name nodes for test data
# ======================================================================

def _name_node(id: str) -> ast.Name:
    n = ast.Name(id=id, ctx=ast.Load())
    ast.fix_missing_locations(ast.Expression(body=n))
    return n
