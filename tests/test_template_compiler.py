"""Tests for template_compiler."""

import ast
import dataclasses
import textwrap
from typing import Any

import pytest

from clausal.codegen import functiondef_to_function, stmts_to_function
from clausal.templating.compiler import (
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
        # nv
        tree = ast.parse("@{}\ndef f(X): pass")
        assert is_template_func(tree.body[0])

    def test_no_decorator_not_detected(self):
        # nv
        tree = ast.parse("def f(X): pass")
        assert not is_template_func(tree.body[0])

    def test_non_empty_dict_not_detected(self):
        # nv
        tree = ast.parse("@{1: 2}\ndef f(X): pass")
        assert not is_template_func(tree.body[0])

    def test_multiple_decorators_not_detected(self):
        # nv
        tree = ast.parse("@{}\n@other\ndef f(X): pass")
        assert not is_template_func(tree.body[0])

    def test_class_not_detected(self):
        # nv
        tree = ast.parse("@{}\nclass C: pass")
        assert not is_template_func(tree.body[0])


# ======================================================================
# Identifier substitution
# ======================================================================

class TestIdentifiers:
    def test_function_name(self):
        # nv
        src = "@{}\ndef t(NAME):\n    def NAME(self): pass"
        result = compile_and_run(src, "result = t('greet')")
        assert "def greet" in unparse_result(result)

    def test_argument_name(self):
        # nv
        src = "@{}\ndef t(FN):\n    def foo(self, FN): pass"
        result = compile_and_run(src, "result = t('visitor')")
        assert "visitor" in unparse_result(result)

    def test_name_in_expression(self):
        # nv
        src = "@{}\ndef t(FN):\n    def foo(self):\n        FN.visit(self)"
        result = compile_and_run(src, "result = t('v')")
        assert "v.visit(self)" in unparse_result(result)

    def test_multiple_substitutions(self):
        # nv
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
        # nv
        src = textwrap.dedent("""\
            @{}
            def t(NAME='greet'):
                def NAME(self): pass
        """)
        result = compile_and_run(src, "result = t()")
        assert "def greet" in unparse_result(result)

    def test_class_name_substitution(self):
        # nv
        src = "@{}\ndef t(CLS):\n    class CLS: pass"
        result = compile_and_run(src, "result = t('MyClass')")
        assert "class MyClass" in unparse_result(result)

    def test_attribute_name_not_substituted(self):
        # nv
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
        # nv
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
        # nv
        src = "@{}\ndef t(F):\n    def F(self):\n        {a, b}"
        result = compile_and_run(src, "result = t('f')", {
            "a": ast.parse("x = 1").body[0],
            "b": ast.parse("y = 2").body[0],
        })
        out = unparse_result(result)
        assert "x = 1" in out and "y = 2" in out

    def test_star_escape(self):
        # nv
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
        # nv
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
        # nv
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
        # nv
        src = "@{}\ndef t(F):\n    def F(self):\n        {stmts}"
        stmts = ast.parse("a = 1\nb = 2").body
        result = compile_and_run(src, "result = t('f')",
                                 {"stmts": stmts})
        out = unparse_result(result)
        assert "a = 1" in out and "b = 2" in out

    def test_nested_if_else_escapes(self):
        # nv
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
        # nv
        src = "@{}\ndef t(N):\n    def N(__args__={a}): pass"
        args = ast.arguments(
            posonlyargs=[], args=[ast.arg(arg="self"), ast.arg(arg="x")],
            vararg=None, kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[])
        result = compile_and_run(src, "result = t('f')", {"a": args})
        assert "def f(self, x)" in unparse_result(result)

    def test_args_from_single_arg(self):
        # nv
        src = "@{}\ndef t(N):\n    def N(__args__={a}): pass"
        result = compile_and_run(src, "result = t('f')",
                                 {"a": ast.arg(arg="self")})
        assert "def f(self)" in unparse_result(result)

    def test_args_from_tuple(self):
        # nv
        src = "@{}\ndef t(N):\n    def N(__args__={a}): pass"
        result = compile_and_run(src, "result = t('f')", {
            "a": (ast.arg(arg="self"), ast.arg(arg="x")),
        })
        assert "def f(self, x)" in unparse_result(result)

    def test_args_from_expression(self):
        # nv
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
        # nv
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
        # nv
        src = "@{}\ndef t(N):\n    def N(__args__={a}, other={b}): pass"
        with pytest.raises(TemplateCompileError, match="sole parameter"):
            compile_and_run(src, "result = t('f')", {
                "a": ast.arg(arg="self"), "b": ast.arg(arg="x"),
            })

    def test_args_no_default_raises(self):
        # nv
        src = "@{}\ndef t(N):\n    def N(__args__): pass"
        with pytest.raises(TemplateCompileError, match="default"):
            compile_and_run(src, "result = t('f')")


# ======================================================================
# Class templates
# ======================================================================

class TestClassTemplates:
    def test_simple_class(self):
        # nv
        src = textwrap.dedent("""\
            @{}
            def t(CLS):
                class CLS:
                    pass
        """)
        result = compile_and_run(src, "result = t('Widget')")
        assert "class Widget" in unparse_result(result)

    def test_class_with_base(self):
        # nv
        src = textwrap.dedent("""\
            @{}
            def t(CLS, BASE):
                class CLS(BASE):
                    pass
        """)
        result = compile_and_run(src, "result = t('Widget', 'QObject')")
        assert "class Widget(QObject)" in unparse_result(result)

    def test_class_with_magic_bases(self):
        # nv
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
        # nv
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
        # nv
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
        # nv
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
        # nv
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
        # nv
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
        # nv
        src = "@{}\ndef t(X):\n    def X(self): pass"
        tree = transform_module_ast(ast.parse(src))
        func = tree.body[0]
        assert func.lineno == 2  # @{} is line 1, def is line 2

    def test_escape_gets_original_line(self):
        # nv
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
        # nv
        src = "def normal(x): return x + 1"
        assert "return x + 1" in transform_module(src)

    def test_template_with_no_subs(self):
        # nv
        src = "@{}\ndef t():\n    def foo(): pass"
        result = compile_and_run(src, "result = t()")
        assert "def foo" in unparse_result(result)

    def test_compile_non_template_raises(self):
        # nv
        tree = ast.parse("def f(): pass")
        with pytest.raises(TemplateCompileError):
            compile_template_func(tree.body[0])

    def test_multiple_templates_in_module(self):
        # nv
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
        # nv
        src = "@{}\ndef t(F):\n    def F(self):\n        {s}"
        result = compile_and_run(src, "result = t('f')", {
            "s": ast.parse("x = 1").body[0],
        })
        assert "x = 1" in unparse_result(result)


# ======================================================================
# String-as-callable syntax
# ======================================================================

class TestStringCallable:
    def test_string_callable_becomes_name(self):
        # nv
        src = textwrap.dedent("""\
            @{}
            def t():
                '+'(a, b)
        """)
        result = compile_and_run(src, "result = t()")
        call = result[0].value
        assert isinstance(call, ast.Call)
        assert isinstance(call.func, ast.Name)
        assert call.func.id == '+'

    def test_string_callable_with_substitution(self):
        # nv
        src = textwrap.dedent("""\
            @{}
            def t(OP):
                'OP'(a, b)
        """)
        result = compile_and_run(src, "result = t('+')")
        call = result[0].value
        assert isinstance(call, ast.Call)
        assert isinstance(call.func, ast.Name)
        assert call.func.id == '+'

    def test_identifier_string_callable_in_comp_escape(self):
        # 'make'(x) in a comprehension escape → make(x) at runtime
        # nv
        src = textwrap.dedent("""\
            @{}
            def t():
                {'make'(x) for x in items}
        """)
        make = lambda x: ast.parse(f"print({x!r})").body[0]
        result = compile_and_run(src, "result = t()", {
            "make": make,
            "items": ["a", "b"],
        })
        out = unparse_result(result)
        assert "print('a')" in out
        assert "print('b')" in out

    def test_nonidentifier_string_callable_in_comp_escape(self):
        # '+='(a, b) in a comprehension escape → globals()['+='](a, b) at runtime
        # nv
        src = textwrap.dedent("""\
            @{}
            def t():
                {'+='(a, b) for a, b in pairs}
        """)
        make_aug = lambda a, b: ast.parse(f"{a} += {b}").body[0]
        result = compile_and_run(src, "result = t()", {
            "pairs": [("x", "1"), ("y", "2")],
            "+=": make_aug,
        })
        out = unparse_result(result)
        assert "x += 1" in out
        assert "y += 2" in out

    def test_identifier_string_callable_in_single_escape(self):
        # {'make'(x)} — single escape
        # nv
        src = textwrap.dedent("""\
            @{}
            def t():
                {'make'(x)}
        """)
        make = lambda x: ast.parse(f"pass").body[0]
        result = compile_and_run(src, "result = t()", {"make": make, "x": "hi"})
        assert len(result) == 1

    def test_nonidentifier_string_callable_in_single_escape(self):
        # nv
        src = textwrap.dedent("""\
            @{}
            def t():
                {'+='(a, b)}
        """)
        make_aug = lambda a, b: ast.parse(f"{a} += {b}").body[0]
        result = compile_and_run(src, "result = t()", {
            "+=": make_aug, "a": "x", "b": "1",
        })
        assert "x += 1" in unparse_result(result)


# ======================================================================
# Helper to create Name nodes for test data
# ======================================================================

def _name_node(id: str) -> ast.Name:
    n = ast.Name(id=id, ctx=ast.Load())
    ast.fix_missing_locations(ast.Expression(body=n))
    return n


def _args(*names: str) -> ast.arguments:
    return ast.arguments(
        posonlyargs=[], args=[ast.arg(arg=n) for n in names],
        vararg=None, kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[],
    )


# ======================================================================
# functiondef_to_function
# ======================================================================

class TestFunctiondefToFunction:
    def test_basic_return_value(self):
        # nv
        f = functiondef_to_function(ast.parse("def f(): return 1").body[0])
        assert f() == 1

    def test_name_from_node(self):
        # nv
        f = functiondef_to_function(ast.parse("def my_func(): pass").body[0])
        assert f.__name__ == "my_func"

    def test_single_parameter(self):
        # nv
        f = functiondef_to_function(ast.parse("def double(x): return x * 2").body[0])
        assert f(5) == 10

    def test_multiple_parameters(self):
        # nv
        f = functiondef_to_function(ast.parse("def add(x, y): return x + y").body[0])
        assert f(3, 4) == 7

    def test_default_parameter(self):
        # nv
        f = functiondef_to_function(
            ast.parse("def greet(name='world'): return 'hello ' + name").body[0])
        assert f() == "hello world"
        assert f("alice") == "hello alice"

    def test_globals_accessible(self):
        # nv
        f = functiondef_to_function(
            ast.parse("def f(): return helper()").body[0],
            globals_={"helper": lambda: 99},
        )
        assert f() == 99

    def test_globals_used_in_expression(self):
        # nv
        f = functiondef_to_function(
            ast.parse("def f(x): return scale * x").body[0],
            globals_={"scale": 3},
        )
        assert f(4) == 12

    def test_filename_in_code_object(self):
        # nv
        f = functiondef_to_function(
            ast.parse("def f(): pass").body[0], filename="myfile.py")
        assert f.__code__.co_filename == "myfile.py"

    def test_default_filename(self):
        # nv
        f = functiondef_to_function(ast.parse("def f(): pass").body[0])
        assert f.__code__.co_filename == "<template>"

    def test_multiline_body(self):
        # nv
        src = "def f(x):\n    y = x * 2\n    z = y + 1\n    return z"
        f = functiondef_to_function(ast.parse(src).body[0])
        assert f(5) == 11

    def test_varargs(self):
        # nv
        f = functiondef_to_function(
            ast.parse("def f(*args): return list(args)").body[0])
        assert f(1, 2, 3) == [1, 2, 3]

    def test_kwargs(self):
        # nv
        f = functiondef_to_function(ast.parse("def f(**kw): return kw").body[0])
        assert f(a=1, b=2) == {"a": 1, "b": 2}

    def test_exception_propagates(self):
        # nv
        f = functiondef_to_function(
            ast.parse("def f(): raise ValueError('boom')").body[0])
        with pytest.raises(ValueError, match="boom"):
            f()

    def test_globals_dict_not_mutated(self):
        # nv
        ns = {"x": 1}
        functiondef_to_function(ast.parse("def f(): pass").body[0], globals_=ns)
        assert set(ns.keys()) == {"x"}

    def test_async_functiondef(self):
        # nv
        import asyncio
        node = ast.parse("async def f(): return 7").body[0]
        f = functiondef_to_function(node)
        assert asyncio.run(f()) == 7


# ======================================================================
# stmts_to_function
# ======================================================================

class TestStmtsToFunction:
    def test_basic_body_no_args(self):
        # nv
        f = stmts_to_function(ast.parse("return 42").body, "answer")
        assert f() == 42

    def test_name_assigned(self):
        # nv
        f = stmts_to_function(ast.parse("pass").body, "my_fn")
        assert f.__name__ == "my_fn"

    def test_explicit_args(self):
        # nv
        f = stmts_to_function(ast.parse("return x + y").body, "add", _args("x", "y"))
        assert f(2, 3) == 5

    def test_default_args_means_no_parameters(self):
        # nv
        import inspect
        f = stmts_to_function(ast.parse("return 0").body, "f")
        assert len(inspect.signature(f).parameters) == 0

    def test_globals_accessible_in_body(self):
        # nv
        f = stmts_to_function(
            ast.parse("return helper(x)").body, "f", _args("x"),
            globals_={"helper": lambda v: v * 10},
        )
        assert f(3) == 30

    def test_multiple_statements(self):
        # nv
        f = stmts_to_function(
            ast.parse("y = x * x\nreturn y + 1").body, "f", _args("x"))
        assert f(4) == 17

    def test_filename_in_code_object(self):
        # nv
        f = stmts_to_function(ast.parse("pass").body, "f", filename="gen.py")
        assert f.__code__.co_filename == "gen.py"

    def test_default_filename(self):
        # nv
        f = stmts_to_function(ast.parse("pass").body, "f")
        assert f.__code__.co_filename == "<template>"

    def test_returns_annotation(self):
        # nv
        ret = ast.Name(id="int", ctx=ast.Load())
        f = stmts_to_function(ast.parse("return 1").body, "f", returns=ret)
        assert f.__annotations__ == {"return": int}

    def test_decorator_applied(self):
        # nv
        dec = ast.parse("staticmethod").body[0].value
        f = stmts_to_function(
            ast.parse("return x").body, "f", _args("x"), decorators=[dec])
        assert isinstance(f, staticmethod)

    def test_same_body_reused_for_two_functions(self):
        # nv
        body = ast.parse("return n").body
        f1 = stmts_to_function(body, "f1", _args("n"))
        f2 = stmts_to_function(body, "f2", _args("n"))
        assert f1(1) == 1
        assert f2(2) == 2
        assert f1.__name__ != f2.__name__

    def test_integration_with_template(self):
        """Template-generated stmts flow through stmts_to_function correctly."""
        # nv
        src = textwrap.dedent("""\
            @{}
            def make_body(N):
                return N * 2
        """)
        tree = transform_module_ast(ast.parse(src))
        make_body = functiondef_to_function(tree.body[0])
        body = make_body("x")
        f = stmts_to_function(body, "double", _args("x"))
        assert f(5) == 10


# ======================================================================
# ISO 6.3.3 inside a template body (spec §7)
# ======================================================================

class TestDoubleQuotedFunctorInTemplateBody:
    """A template body is source too, so ``"foo"(1)`` is refused there.

    The refusal lives in ``ASTBuilder._build_Call`` and needs the owning
    file's quote map, which only the real path threads
    (``EmbedTransformer`` -> ``compile_template_func(node, quote_map)``);
    ``transform_module_ast`` builds no map, so these go through
    ``EmbedTransformer`` with the source lines, as a load does.
    """

    @staticmethod
    def _embed(source: str):
        from clausal.templating.term_rewriting import EmbedTransformer
        return EmbedTransformer(
            source_lines=source.splitlines(keepends=True)
        ).visit(ast.parse(source))

    def test_double_quoted_functor_is_a_syntax_error(self):
        # nv
        with pytest.raises(SyntaxError,
                           match="double-quoted literal cannot be a functor"):
            self._embed('@{}\ndef t(X):\n    "foo"(1)\n')

    def test_single_quoted_functor_is_accepted(self):
        # nv — ``'foo'`` is an atom in every -double_quotes mode
        self._embed("@{}\ndef t(X):\n    'foo'(1)\n")

    def test_double_quoted_functor_refused_under_chars_mode_too(self):
        # nv — the rule is ISO 6.3.3, not a mode: a "..." literal is never a
        # functor, whichever way the module reads its double quotes.
        with pytest.raises(SyntaxError,
                           match="double-quoted literal cannot be a functor"):
            self._embed(
                '-double_quotes(chars)\n@{}\ndef t(X):\n    "foo"(1)\n')
