"""Tests for term_rewriting — TermTransformer and EmbedTransformer.

TermTransformer takes a Python expression AST and produces Python AST that,
when executed, constructs a simple_ast node.  The test harness evaluates the
transformed expression in a namespace containing all simple_ast names to
recover the resulting node.

EmbedTransformer walks a whole module, converting '--expr' escapes to
TermTransformer output and detecting other DSL patterns.
"""
import ast
import pytest
from clausal.pythonic_ast import nodes as sa
from clausal.terms import ArithConstraint
from clausal.templating.term_rewriting import (
    TermTransformer,
    EmbedTransformer,
    _make_functor_class_ast,
)
from clausal.logic.variables import Var as RealVar


# ── helpers ───────────────────────────────────────────────────────────────────

def _ns():
    """Namespace with all simple_ast names + a mock Var constructor + terms extras."""
    ns = {name: getattr(sa, name) for name in sa.__all__}
    ns['Var'] = lambda: '<Var>'   # mock; returns a sentinel string
    ns['ArithConstraint'] = ArithConstraint
    return ns


def term_eval(src: str, expected_type: type):
    """Parse an expression, run TermTransformer, evaluate → simple_ast node."""
    tree = ast.parse(src, mode='eval')
    ast.fix_missing_locations(tree)
    transformed = TermTransformer().visit(tree.body)
    expr_tree = ast.fix_missing_locations(ast.Expression(body=transformed))
    result = eval(compile(expr_tree, '<test>', 'eval'), _ns())
    assert isinstance(result, expected_type)
    return result


def embed_exec(src: str) -> dict:
    """Parse a module, run EmbedTransformer, exec → returned namespace."""
    tree = ast.parse(src)
    ast.fix_missing_locations(tree)
    transformed = EmbedTransformer().visit(tree)
    ast.fix_missing_locations(transformed)
    ns = _ns()
    ns['$ast'] = ast   # required by ~~ and with-the_following generated code
    exec(compile(transformed, '<test>', 'exec'), ns)
    return ns


# ── TermTransformer: literals (Python built-ins are terms directly) ────────────

def test_integer():
    assert term_eval("42", int) == 42


def test_float():
    assert term_eval("3.14", float) == 3.14


def test_complex():
    assert term_eval("1j", complex) == 1j


def test_string():
    assert term_eval("'hello'", str) == 'hello'


def test_bytes():
    assert term_eval("b'hi'", bytes) == b'hi'


def test_bool_true():
    result = term_eval("True", bool)
    assert result is True


def test_bool_false():
    result = term_eval("False", bool)
    assert result is False


def test_none():
    tree = ast.parse("None", mode='eval')
    ast.fix_missing_locations(tree)
    transformed = TermTransformer().visit(tree.body)
    expr_tree = ast.fix_missing_locations(ast.Expression(body=transformed))
    assert eval(compile(expr_tree, '<test>', 'eval'), _ns()) is None


def test_ellipsis():
    tree = ast.parse("...", mode='eval')
    ast.fix_missing_locations(tree)
    transformed = TermTransformer().visit(tree.body)
    expr_tree = ast.fix_missing_locations(ast.Expression(body=transformed))
    assert eval(compile(expr_tree, '<test>', 'eval')) is ...


# ── TermTransformer: names ─────────────────────────────────────────────────────

def test_bare_name_becomes_load_name():
    node = term_eval("foo", sa.LoadName)
    assert node.name == 'foo'


def test_logic_variable_first_use():
    # X (ALL-CAPS) on first use creates a Var (our mock returns a sentinel string)
    node = term_eval("X", str)
    assert node == '<Var>'


def test_logic_variable_reuse():
    # X used twice in the same expression: second use must be the same object
    # The walrus pattern ensures they share the same Python variable.
    node = term_eval("X == X", sa.Eq)
    assert node.left is node.right   # same Var object


# ── TermTransformer: binary operators ─────────────────────────────────────────

@pytest.mark.parametrize("src,cls", [
    ("a + b",  sa.Add),
    ("a - b",  sa.Sub),
    ("a * b",  sa.Mult),
    ("a / b",  sa.Div),
    ("a // b", sa.FloorDiv),
    ("a % b",  sa.Mod),
    ("a ** b", sa.Pow),
    ("a @ b",  sa.MatMult),
    ("a << b", sa.LShift),
    ("a >> b", sa.RShift),
    ("a | b",  sa.BitOr),
    ("a ^ b",  sa.BitXor),
    ("a & b",  sa.BitAnd),
])
def test_binop(src, cls):
    node = term_eval(src, cls)
    assert isinstance(node.left,  sa.LoadName)
    assert isinstance(node.right, sa.LoadName)


# ── TermTransformer: unary operators ──────────────────────────────────────────

@pytest.mark.parametrize("src,cls", [
    ("-x",  sa.Negate),
    ("+x",  sa.UnaryPlus),
    ("~x",  sa.Invert),
    ("not x", sa.Not),
])
def test_unaryop(src, cls):
    node = term_eval(src, cls)
    assert isinstance(node.operand, sa.LoadName)


# ── TermTransformer: boolean operators ────────────────────────────────────────

def test_bool_and():
    node = term_eval("a and b", sa.And)
    assert isinstance(node.left,  sa.LoadName)
    assert isinstance(node.right, sa.LoadName)


def test_bool_or():
    node = term_eval("a or b", sa.Or)
    assert isinstance(node.left,  sa.LoadName)
    assert isinstance(node.right, sa.LoadName)


def test_bool_and_folded():
    # a and b and c → And(And(a, b), c)
    node = term_eval("a and b and c", sa.And)
    assert isinstance(node.left, sa.And)
    assert node.left.left.name == 'a'
    assert node.left.right.name == 'b'
    assert isinstance(node.right, sa.LoadName)
    assert node.right.name == 'c'


# ── TermTransformer: comparison operators ─────────────────────────────────────

@pytest.mark.parametrize("src,cls", [
    ("a == b",        sa.Eq),
    ("a != b",        sa.NotEq),
    ("a < b",         sa.Lt),
    ("a <= b",        sa.LtE),
    ("a > b",         sa.Gt),
    ("a >= b",        sa.GtE),
    ("a is b",        sa.Is),
    ("a is not b",    sa.IsNot),
    ("a in b",        sa.In),
    ("a not in b",    sa.NotIn),
])
def test_cmpop(src, cls):
    node = term_eval(src, cls)
    assert node.left.name == 'a'
    assert node.right.name == 'b'


def test_compare_chain():
    node = term_eval("a < b <= c", sa.CompareChain)
    assert len(node.comparisons) == 2
    assert isinstance(node.comparisons[0], sa.Lt)
    assert isinstance(node.comparisons[1], sa.LtE)


# ── TermTransformer: ArithConstraint (==+ / == +expr) ────────────────────────

def test_arith_constraint():
    # a == +b  →  ArithConstraint(expr=Eq(a, b))
    node = term_eval("a == +b", ArithConstraint)
    assert isinstance(node.expr, sa.Eq)
    assert node.expr.left.name == 'a'
    assert node.expr.right.name == 'b'


def test_arith_constraint_expression():
    # x == +(y + 1)  →  ArithConstraint(expr=Eq(x, Add(y, 1)))
    node = term_eval("x == +(y + 1)", ArithConstraint)
    assert isinstance(node.expr, sa.Eq)
    assert node.expr.left.name == 'x'
    assert isinstance(node.expr.right, sa.Add)


def test_plain_eq_not_arith_constraint():
    # a == b (no unary plus) → Eq, not ArithConstraint
    node = term_eval("a == b", sa.Eq)
    assert node.left.name == 'a'
    assert node.right.name == 'b'


# ── TermTransformer: '<-' pseudo-operator ─────────────────────────────────────

def test_arrow_assign():
    # a<-b (no space: '-' immediately follows '<') → Predicate
    node = term_eval("a<-b", sa.Predicate)
    assert isinstance(node.head, sa.LoadName)
    assert node.head.name == 'a'
    assert isinstance(node.body, sa.LoadName)
    assert node.body.name == 'b'


def test_arrow_assign_with_spaces():
    # a <- b (spaces around '<-' but '<' and '-' adjacent) → Predicate
    node = term_eval("a <- b", sa.Predicate)
    assert isinstance(node.head, sa.LoadName)
    assert node.head.name == 'a'
    assert isinstance(node.body, sa.LoadName)
    assert node.body.name == 'b'


def test_spaced_lt_negate_not_arrow():
    # a < -b (space between '<' and '-') is NOT '<-', just Lt of Negate
    node = term_eval("a < -b", sa.Lt)
    assert isinstance(node.right, sa.Negate)


# ── TermTransformer: collections ──────────────────────────────────────────────

def test_list_literal():
    # Python lists are terms directly — result is a plain list.
    node = term_eval("[a, b, c]", list)
    assert len(node) == 3
    assert all(isinstance(e, sa.LoadName) for e in node)


def test_empty_list():
    node = term_eval("[]", list)
    assert node == []


def test_tuple_literal():
    node = term_eval("(a, b)", sa.TupleLiteral)
    assert len(node.elements) == 2


def test_set_literal():
    node = term_eval("{a, b}", sa.SetLiteral)
    assert len(node.elements) == 2


def test_dict_literal():
    node = term_eval("{'k': v}", sa.DictLiteral)
    assert len(node.keys) == 1
    assert node.keys[0] == 'k'   # plain Python string, not StringLiteral
    assert isinstance(node.values[0], sa.LoadName)


# ── TermTransformer: call expressions ─────────────────────────────────────────

def test_call_positional():
    node = term_eval("f(a, b)", sa.Call)
    assert isinstance(node.func, sa.LoadName)
    assert node.func.name == 'f'
    assert len(node.args) == 2
    assert isinstance(node.args[0], sa.LoadName)


def test_call_keyword():
    node = term_eval("f(x=1)", sa.Call)
    assert len(node.kwargs) == 1
    kw = node.kwargs[0]
    assert isinstance(kw, sa.Keyword)
    assert kw.name == 'x'
    assert kw.value == 1   # plain Python int, not IntLiteral


def test_call_string_callable():
    # '+'(a, b) — string used as functor name, e.g. for operators
    node = term_eval("'+'(a, b)", sa.Call)
    assert isinstance(node.func, sa.LoadName)
    assert node.func.name == '+'
    assert len(node.args) == 2
    assert all(isinstance(arg, sa.LoadName) for arg in node.args)


def test_call_string_callable_keyword():
    node = term_eval("'f'(x=1)", sa.Call)
    assert isinstance(node.func, sa.LoadName)
    assert node.func.name == 'f'


# ── TermTransformer: other expressions ────────────────────────────────────────

def test_if_expr():
    node = term_eval("a if c else b", sa.IfExpr)
    assert isinstance(node.test,   sa.LoadName)
    assert isinstance(node.body,   sa.LoadName)
    assert isinstance(node.orelse, sa.LoadName)


def test_subscript():
    node = term_eval("a[b]", sa.LoadSubscript)
    assert isinstance(node.object, sa.LoadName)
    assert isinstance(node.index,  sa.LoadName)


def test_starred():
    # *a in a list context — result is a plain Python list
    node = term_eval("[*a]", list)
    assert isinstance(node[0], sa.StarUnpack)


def test_list_comp():
    node = term_eval("[x for x in xs]", sa.ListComp)
    assert isinstance(node.element, sa.LoadName)
    assert len(node.clauses) == 1
    clause = node.clauses[0]
    assert isinstance(clause, sa.ForClause)
    assert isinstance(clause.iterable, sa.LoadName)


def test_lambda():
    node = term_eval("lambda x: x", sa.Lambda)
    assert isinstance(node.body, sa.LoadName)


# ── TermTransformer: position is always set ───────────────────────────────────

def test_position_set():
    node = term_eval("x + y", sa.Add)
    lineno, col_offset, end_lineno, end_col_offset = node.position
    assert lineno == 1
    assert col_offset == 0


# ── EmbedTransformer: '--' escape ─────────────────────────────────────────────

def test_embed_double_dash():
    # '--' applies to its immediate operand; wrap the whole expression in parens.
    ns = embed_exec("result = --(x + y)")
    assert isinstance(ns['result'], sa.Add)
    assert isinstance(ns['result'].left,  sa.LoadName)
    assert isinstance(ns['result'].right, sa.LoadName)


def test_embed_double_dash_nested():
    ns = embed_exec("result = --'hello'")
    assert ns['result'] == 'hello'   # plain Python string, not StringLiteral


def test_embed_spaced_double_dash_not_escaped():
    # '- -x' (with space) must NOT be treated as the '--' escape
    ns = embed_exec("result = - -42")
    # regular Python double-negation, result is 42 (an int, not a simple_ast node)
    assert ns['result'] == 42


def test_embed_normal_code_unchanged():
    ns = embed_exec("x = 1 + 2")
    assert ns['x'] == 3


# ── EmbedTransformer: trailing-comma fact notation ────────────────────────────

def test_embed_trailing_comma_defines_fact():
    # Trailing-comma fact: ``f(a),`` goes through $define_predicate with body=True.
    from clausal.logic.predicate import PredicateMeta

    predicates = []
    ns = _ns()
    ns['Var'] = lambda: '<Var>'
    ns['PredicateMeta'] = PredicateMeta
    module = type('MockModule', (), {'define_predicate': lambda self, p: predicates.append(p)})()
    ns['$define_predicate'] = lambda pred, mod: mod.define_predicate(pred)
    ns['$module'] = module
    src = "f(a),"
    tree = ast.parse(src)
    ast.fix_missing_locations(tree)
    transformed = EmbedTransformer().visit(tree)
    ast.fix_missing_locations(transformed)
    exec(compile(transformed, '<test>', 'exec'), ns)
    assert len(predicates) == 1
    assert isinstance(predicates[0], sa.Predicate)
    assert predicates[0].body is True


# ── EmbedTransformer: 'with the_following' block ──────────────────────────────

def test_embed_dash_block_produces_simple_ast_terms():
    # with --{} as id: — block form of --, produces simple_ast nodes.
    src = """\
with --{} as clauses:
    a + b
    f(x)
"""
    ns = embed_exec(src)
    assert isinstance(ns['clauses'], list)
    assert len(ns['clauses']) == 2
    assert isinstance(ns['clauses'][0], sa.Add)
    assert isinstance(ns['clauses'][1], sa.Call)


def test_embed_tilde_block_expr_stmts():
    # with ~~{} as id: — block form of ~~, expression statements yield expression node.
    src = """\
with ~~{} as clauses:
    a + b
    f(x)
"""
    ns = embed_exec(src)
    assert isinstance(ns['clauses'], list)
    assert len(ns['clauses']) == 2
    assert isinstance(ns['clauses'][0], ast.BinOp)
    assert isinstance(ns['clauses'][1], ast.Call)


def test_embed_tilde_block_return_stmt():
    # with ~~{} as id: — non-expression statements yield the statement node itself.
    src = """\
with ~~{} as clauses:
    return x + 1
"""
    ns = embed_exec(src)
    assert isinstance(ns['clauses'], list)
    assert len(ns['clauses']) == 1
    assert isinstance(ns['clauses'][0], ast.Return)
    assert isinstance(ns['clauses'][0].value, ast.BinOp)


def test_embed_tilde_block_mixed():
    # with ~~{} as id: — mix of expression and statement nodes.
    src = """\
with ~~{} as clauses:
    x + 1
    return y
"""
    ns = embed_exec(src)
    assert isinstance(ns['clauses'][0], ast.BinOp)
    assert isinstance(ns['clauses'][1], ast.Return)


# ── Partial-term: _make_functor_class_ast __call__ fills missing fields ────────


def _make_functor_class(functor_name: str, *field_names: str):
    """Compile and return the Predicate class generated for the given fields."""
    from clausal.logic.predicate import PredicateMeta

    anchor = ast.parse("x").body[0]
    ast.fix_missing_locations(anchor)
    class_ast = _make_functor_class_ast(functor_name, list(field_names), anchor)
    module = ast.fix_missing_locations(
        ast.Module(body=[class_ast], type_ignores=[])
    )
    ns = {"Var": RealVar, "PredicateMeta": PredicateMeta}
    exec(compile(module, "<test>", "exec"), ns)
    return ns[functor_name]


def test_partial_term_unspecified_field_is_var():
    point = _make_functor_class("point", "x_", "y_")
    result = point(x_=1)
    assert result.x_ == 1
    assert isinstance(result.y_, RealVar)


def test_partial_term_explicit_none_preserved():
    point = _make_functor_class("point", "x_", "y_")
    result = point(x_=1, y_=None)
    assert result.y_ is None


def test_partial_term_no_args_all_vars():
    point = _make_functor_class("point", "x_", "y_")
    result = point()
    assert isinstance(result.x_, RealVar)
    assert isinstance(result.y_, RealVar)


def test_partial_term_fresh_vars_each_call():
    point = _make_functor_class("point", "x_", "y_")
    r1 = point(x_=1)
    r2 = point(x_=1)
    assert r1.y_ is not r2.y_


# ── TermTransformer: anonymous variable _ ─────────────────────────────────────


def test_anon_var_is_var():
    """Bare _ in predicate context → fresh Var(), not LoadName."""
    ns = {"Var": RealVar}
    tree = ast.parse("_", mode="eval")
    ast.fix_missing_locations(tree)
    transformed = TermTransformer().visit(tree.body)
    expr = ast.fix_missing_locations(ast.Expression(body=transformed))
    result = eval(compile(expr, "<test>", "eval"), ns)
    assert isinstance(result, RealVar)


def test_anon_var_fresh_each_occurrence():
    """Two _ in the same expression yield distinct Var objects."""
    ns = {"Var": RealVar}
    # Eval _ == _ — both sides should be different Var objects
    tree = ast.parse("(_ == _)", mode="eval")
    ast.fix_missing_locations(tree)
    transformed = TermTransformer().visit(tree.body)
    expr = ast.fix_missing_locations(ast.Expression(body=transformed))
    from clausal.pythonic_ast import nodes as sa
    result = eval(compile(expr, "<test>", "eval"), {**{n: getattr(sa, n) for n in sa.__all__}, "Var": RealVar})
    assert isinstance(result, sa.Eq)
    assert isinstance(result.left, RealVar)
    assert isinstance(result.right, RealVar)
    assert result.left is not result.right  # distinct Var objects


def test_anon_var_not_reused_like_named_var():
    """Named vars (X) are reused; _ is always fresh."""
    ns = {"Var": RealVar}
    from clausal.pythonic_ast import nodes as sa
    sa_ns = {n: getattr(sa, n) for n in sa.__all__}
    # Named var reuse: X == X produces same Var
    tree = ast.parse("X == X", mode="eval")
    ast.fix_missing_locations(tree)
    transformed = TermTransformer().visit(tree.body)
    expr = ast.fix_missing_locations(ast.Expression(body=transformed))
    named_result = eval(compile(expr, "<test>", "eval"), {**sa_ns, "Var": RealVar})
    assert named_result.left is named_result.right
    # Anonymous var: _ == _ produces distinct Vars
    tree2 = ast.parse("_ == _", mode="eval")
    ast.fix_missing_locations(tree2)
    transformed2 = TermTransformer().visit(tree2.body)
    expr2 = ast.fix_missing_locations(ast.Expression(body=transformed2))
    anon_result = eval(compile(expr2, "<test>", "eval"), {**sa_ns, "Var": RealVar})
    assert anon_result.left is not anon_result.right
