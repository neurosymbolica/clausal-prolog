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
from clausal.templating.term_rewriting import TermTransformer, EmbedTransformer


# ── helpers ───────────────────────────────────────────────────────────────────

def _ns():
    """Namespace with all simple_ast names + a mock Var constructor."""
    ns = {name: getattr(sa, name) for name in sa.__all__}
    ns['Var'] = lambda name: f'<Var {name}>'   # mock; returns distinguishable sentinel
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
    exec(compile(transformed, '<test>', 'exec'), ns)
    return ns


# ── TermTransformer: literals ──────────────────────────────────────────────────

def literal_test(string, literal_type, value):
    node = term_eval(string, literal_type)
    assert node.value == value


def test_integer():
    literal_test("42", sa.IntLiteral, 42)


def test_float():
    literal_test("3.14", sa.FloatLiteral, 3.14)


def test_complex():
    literal_test("1j", sa.ComplexLiteral, 1j)


def test_string():
    literal_test("'hello'", sa.StringLiteral, 'hello')


def test_bytes():
    literal_test("b'hi'", sa.BytesLiteral, b'hi')


def test_bool_true():
    literal_test("True", sa.BoolLiteral, True)


def test_bool_false():
    literal_test("False", sa.BoolLiteral, False)


def test_none():
    term_eval("None", sa.NoneLiteral)


def test_ellipsis():
    term_eval("...", sa.EllipsisLiteral)


# ── TermTransformer: names ─────────────────────────────────────────────────────

def test_bare_name_becomes_load_name():
    node = term_eval("foo", sa.LoadName)
    assert node.name == 'foo'


def test_logic_variable_first_use():
    # _X on first use creates a Var (our mock returns a sentinel string)
    node = term_eval("_X", str)  # ?
    assert node == '<Var _X>'


def test_logic_variable_reuse():
    # _X used twice in the same expression: second use must be the same object
    # The walrus pattern ensures they share the same Python variable.
    node = term_eval("_X == _X", sa.Eq)
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
    ("a == b",  sa.Eq),
    ("a != b",  sa.NotEq),
    ("a < b",   sa.Lt),
    ("a <= b",  sa.LtE),
    ("a > b",   sa.Gt),
    ("a >= b",  sa.GtE),
    ("a is b",  sa.Is),
    ("a in b",  sa.In),
])
def test_cmpop(src, cls):
    node = term_eval(src, cls)
    assert node.left.name == 'a'
    assert node.right.name == 'b'


def test_compare_chain():
    node = term_eval("a < b <= c", sa.CompareChain)
    assert len(node.comparisons) == 2
    assert isinstance(node.comparisons[0], sa.Lt)
    assert isinstance(node.comparisons[1], sa.LtE )


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
    node = term_eval("[a, b, c]", sa.ListLiteral)
    assert len(node.elements) == 3
    assert all(isinstance(e, sa.LoadName) for e in node.elements)


def test_empty_list():
    node = term_eval("[]", sa.ListLiteral)
    assert node.elements == []


def test_tuple_literal():
    node = term_eval("(a, b)", sa.TupleLiteral)
    assert len(node.elements) == 2


def test_set_literal():
    node = term_eval("{a, b}", sa.SetLiteral)
    assert len(node.elements) == 2


def test_dict_literal():
    node = term_eval("{'k': v}", sa.DictLiteral)
    assert len(node.keys) == 1
    assert isinstance(node.keys[0], sa.StringLiteral)
    assert node.keys[0].value == 'k'
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
    assert isinstance(kw.value, sa.IntLiteral)


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
    # *a in a list context
    node = term_eval("[*a]", sa.ListLiteral)
    assert isinstance(node.elements[0], sa.StarUnpack)


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
    assert isinstance(ns['result'], sa.StringLiteral)
    assert ns['result'].value == 'hello'


def test_embed_spaced_double_dash_not_escaped():
    # '- -x' (with space) must NOT be treated as the '--' escape
    ns = embed_exec("result = - -42")
    # regular Python double-negation, result is 42 (an int, not a simple_ast node)
    assert ns['result'] == 42


def test_embed_normal_code_unchanged():
    ns = embed_exec("x = 1 + 2")
    assert ns['x'] == 3


# ── EmbedTransformer: trailing-comma fact notation ────────────────────────────

def test_embed_trailing_comma_calls_assert_fact():
    facts = []
    ns = _ns()
    ns['$assert_fact'] = facts.append
    src = "f(a),"   # trailing-comma tuple statement
    tree = ast.parse(src)
    ast.fix_missing_locations(tree)
    transformed = EmbedTransformer().visit(tree)
    ast.fix_missing_locations(transformed)
    exec(compile(transformed, '<test>', 'exec'), ns)
    assert len(facts) == 1
    assert isinstance(facts[0], sa.Call)
    assert isinstance(facts[0].func, sa.LoadName)
    assert facts[0].func.name == 'f'


def test_embed_trailing_comma_predicate():
    # pred(x) <- body,  — trailing comma wraps a rule in a tuple;
    # TermTransformer should still recognise '<-' and produce Predicate.
    facts = []
    ns = _ns()
    ns['$assert_fact'] = facts.append
    src = "pred(x) <- body,"
    tree = ast.parse(src)
    ast.fix_missing_locations(tree)
    transformed = EmbedTransformer().visit(tree)
    ast.fix_missing_locations(transformed)
    exec(compile(transformed, '<test>', 'exec'), ns)
    assert len(facts) == 1
    assert isinstance(facts[0], sa.Predicate)


# ── EmbedTransformer: 'with the_following' block ──────────────────────────────

def test_embed_the_following():
    src = """\
with the_following as clauses:
    a + b
    f(x)
"""
    ns = embed_exec(src)
    assert isinstance(ns['clauses'], list)
    assert len(ns['clauses']) == 2
    assert isinstance(ns['clauses'][0], sa.Add)
    assert isinstance(ns['clauses'][1], sa.Call)
