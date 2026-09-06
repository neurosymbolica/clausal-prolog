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
from clausal.templating.term_rewriting import (
    TermTransformer,
    EmbedTransformer,
    _make_functor_class_ast,
)
from clausal.logic.variables import Var as RealVar
from clausal.terms import DictTerm, SetTerm


# ── helpers ───────────────────────────────────────────────────────────────────

def _ns():
    """Namespace with all simple_ast names + a mock Var constructor + terms extras."""
    ns = {name: getattr(sa, name) for name in sa.__all__}
    ns['Var'] = lambda: '<Var>'   # mock; returns a sentinel string
    ns['DictTerm'] = DictTerm
    ns['SetTerm'] = SetTerm
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
    # nv
    assert term_eval("42", int) == 42


def test_float():
    # nv
    assert term_eval("3.14", float) == 3.14


def test_complex():
    # nv
    assert term_eval("1j", complex) == 1j


def test_string():
    # nv
    assert term_eval("'hello'", str) == 'hello'


def test_bytes():
    # nv
    assert term_eval("b'hi'", bytes) == b'hi'


def test_bool_true():
    # nv
    result = term_eval("True", bool)
    assert result is True


def test_bool_false():
    # nv
    result = term_eval("False", bool)
    assert result is False


def test_none():
    # nv
    tree = ast.parse("None", mode='eval')
    ast.fix_missing_locations(tree)
    transformed = TermTransformer().visit(tree.body)
    expr_tree = ast.fix_missing_locations(ast.Expression(body=transformed))
    assert eval(compile(expr_tree, '<test>', 'eval'), _ns()) is None


def test_ellipsis():
    # nv
    tree = ast.parse("...", mode='eval')
    ast.fix_missing_locations(tree)
    transformed = TermTransformer().visit(tree.body)
    expr_tree = ast.fix_missing_locations(ast.Expression(body=transformed))
    assert eval(compile(expr_tree, '<test>', 'eval')) is ...


# ── TermTransformer: names ─────────────────────────────────────────────────────

def test_bare_name_becomes_load_name():
    # nv
    node = term_eval("foo", sa.LoadName)
    assert node.name == 'foo'


def test_logic_variable_first_use():
    # X (ALL-CAPS) on first use creates a Var (our mock returns a sentinel string)
    # nv
    node = term_eval("X", str)
    assert node == '<Var>'


def test_logic_variable_reuse():
    # X used twice in the same expression: second use must be the same object
    # The walrus pattern ensures they share the same Python variable.
    # nv
    node = term_eval("X == X", sa.ArithEq)
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
    # nv
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
    # nv
    node = term_eval(src, cls)
    assert isinstance(node.operand, sa.LoadName)


# ── TermTransformer: boolean operators ────────────────────────────────────────

def test_bool_and():
    # nv
    node = term_eval("a and b", sa.And)
    assert isinstance(node.left,  sa.LoadName)
    assert isinstance(node.right, sa.LoadName)


def test_bool_or():
    # nv
    node = term_eval("a or b", sa.Or)
    assert isinstance(node.left,  sa.LoadName)
    assert isinstance(node.right, sa.LoadName)


def test_bool_and_folded():
    # a and b and c → And(And(a, b), c)
    # nv
    node = term_eval("a and b and c", sa.And)
    assert isinstance(node.left, sa.And)
    assert node.left.left.name == 'a'
    assert node.left.right.name == 'b'
    assert isinstance(node.right, sa.LoadName)
    assert node.right.name == 'c'


# ── TermTransformer: comparison operators ─────────────────────────────────────

@pytest.mark.parametrize("src,cls", [
    ("a == b",        sa.ArithEq),
    ("a != b",        sa.ArithNeq),
    ("a < b",         sa.Lt),
    ("a <= b",        sa.LtE),
    ("a > b",         sa.Gt),
    ("a >= b",        sa.GtE),
    ("a is b",        sa.Unify),
    ("a is not b",    sa.DoesNotUnify),
    ("a in b",        sa.in_),
    ("a not in b",    sa.NotIn),
])
def test_cmpop(src, cls):
    # nv
    node = term_eval(src, cls)
    assert node.left.name == 'a'
    assert node.right.name == 'b'


def test_compare_chain():
    # nv
    node = term_eval("a < b <= c", sa.CompareChain)
    assert len(node.comparisons) == 2
    assert isinstance(node.comparisons[0], sa.Lt)
    assert isinstance(node.comparisons[1], sa.LtE)

# ── TermTransformer: walrus operator ':=' removed (was Evaluate) ──────────────

def test_walrus_is_syntax_error():
    # ':=' no longer parses — its eager-arithmetic meaning lives in eval_/2.
    # nv
    tree = ast.parse("(N := N1 + 1)", mode="eval")
    ast.fix_missing_locations(tree)
    with pytest.raises(SyntaxError, match="eval_"):
        TermTransformer().visit(tree.body)


def test_plain_eq_not_arith_constraint():
    # a == b → ArithEq
    # nv
    node = term_eval("a == b", sa.ArithEq)
    assert node.left.name == 'a'
    assert node.right.name == 'b'


# ── TermTransformer: '<-' pseudo-operator ─────────────────────────────────────

def test_arrow_assign():
    # a<-b (no space: '-' immediately follows '<') → Predicate
    # nv
    node = term_eval("a<-b", sa.Predicate)
    assert isinstance(node.head, sa.LoadName)
    assert node.head.name == 'a'
    assert isinstance(node.body, sa.LoadName)
    assert node.body.name == 'b'


def test_arrow_assign_with_spaces():
    # a <- b (spaces around '<-' but '<' and '-' adjacent) → Predicate
    # nv
    node = term_eval("a <- b", sa.Predicate)
    assert isinstance(node.head, sa.LoadName)
    assert node.head.name == 'a'
    assert isinstance(node.body, sa.LoadName)
    assert node.body.name == 'b'


def test_spaced_lt_negate_not_arrow():
    # a < -b (space between '<' and '-') is NOT '<-', just Lt of Negate
    # nv
    node = term_eval("a < -b", sa.Lt)
    assert isinstance(node.right, sa.Negate)


def test_arrow_body_requires_parens():
    # Unparenthesized non-call/non-name bodies are rejected with a clear error.
    # nv
    import pytest
    # BinOp bodies — USub buried in left spine
    for expr in ["a <- b + c", "a <- b - c", "a <- b * c", "a <- b + c + d"]:
        with pytest.raises(SyntaxError, match="parenthesized"):
            term_eval(expr, sa.Predicate)
    # BoolOp bodies — <- hidden inside or/and
    for expr in ["a <- b or c", "a <- b and c"]:
        with pytest.raises(SyntaxError, match="parenthesized"):
            term_eval(expr, sa.Predicate)
    # IfExp body — <- hidden inside ternary (now rejected as unsupported syntax)
    with pytest.raises(SyntaxError, match="not supported"):
        term_eval("a <- b if c else d", sa.Predicate)


def test_arrow_body_binop_with_parens():
    # Parenthesized operator bodies work fine.
    # nv
    node = term_eval("a <- (b + c)", sa.Predicate)
    assert isinstance(node.head, sa.LoadName) and node.head.name == 'a'
    assert isinstance(node.body, sa.Add)
    assert isinstance(node.body.left, sa.LoadName) and node.body.left.name == 'b'
    assert isinstance(node.body.right, sa.LoadName) and node.body.right.name == 'c'

    node = term_eval("a <- (b - c)", sa.Predicate)
    assert isinstance(node.body, sa.Sub)

    node = term_eval("a <- (b * c)", sa.Predicate)
    assert isinstance(node.body, sa.Mult)

    node = term_eval("a <- (b + c + d)", sa.Predicate)
    assert isinstance(node.body, sa.Add)


def test_arrow_body_pow_still_works():
    # a <- b ** c  parses as  a < -(b ** c)  — USub at top level (** > unary -).
    # ** binds tighter than unary -, so USub is on top → treated like a
    # parenthesized body.  This is technically safe, though style-wise
    # parentheses are recommended.
    # nv
    node = term_eval("a <- b ** c", sa.Predicate)
    assert isinstance(node.body, sa.Pow)


def test_arrow_detection_no_positions():
    # Programmatically constructed AST nodes lack source positions.
    # _detect_arrow should raise ValueError, not crash with AttributeError.
    # nv
    import ast as pyast
    import pytest
    from clausal.templating.term_rewriting import _detect_arrow, _check_hidden_arrow
    left = pyast.Name(id='a', ctx=pyast.Load())
    usub = pyast.UnaryOp(op=pyast.USub(), operand=pyast.Name(id='b', ctx=pyast.Load()))
    with pytest.raises(ValueError, match="missing source positions"):
        _detect_arrow(left, [pyast.Lt()], [usub])

    # Same for _check_hidden_arrow
    boolop = pyast.BoolOp(
        op=pyast.Or(),
        values=[
            pyast.Compare(left=left, ops=[pyast.Lt()], comparators=[usub]),
            pyast.Name(id='c', ctx=pyast.Load()),
        ],
    )
    with pytest.raises(ValueError, match="missing source positions"):
        _check_hidden_arrow(boolop)

    # fix_missing_locations makes it work (positions default to 1:0)
    pyast.fix_missing_locations(pyast.Expression(body=pyast.Compare(
        left=left, ops=[pyast.Lt()], comparators=[usub]
    )))
    # Now positions exist but aren't adjacent (all default to 1:0)
    result = _detect_arrow(left, [pyast.Lt()], [usub])
    assert result is None


def test_arrow_detection_extra_whitespace():
    """Arrow ``<-`` must be detected regardless of whitespace before ``<``."""
    # nv
    import ast as pyast
    from clausal.templating.term_rewriting import _detect_arrow

    for spaces in [1, 2, 4, 8]:
        code = f'head(X){" " * spaces}<- body(X)\n'
        source_lines = code.splitlines(keepends=True)
        tree = pyast.parse(code)
        compare = tree.body[0].value
        result = _detect_arrow(
            compare.left, compare.ops, compare.comparators, source_lines
        )
        assert result is not None, (
            f"Arrow not detected with {spaces} space(s) before <-"
        )

    # ``a < -b`` (space between ``<`` and ``-``) must NOT be detected as arrow
    code = "a < -b\n"
    source_lines = code.splitlines(keepends=True)
    tree = pyast.parse(code)
    compare = tree.body[0].value
    result = _detect_arrow(
        compare.left, compare.ops, compare.comparators, source_lines
    )
    assert result is None, "a < -b should not be detected as arrow"


def test_negative_literal_folding():
    # -3 in a term should be Constant(-3), not Negate(3).
    # nv
    node = term_eval("-3", int)
    assert node == -3
    node = term_eval("-1.5", float)
    assert node == -1.5
    # -x (variable) should still be Negate
    node = term_eval("-x", sa.Negate)
    assert isinstance(node.operand, sa.LoadName)


# ── TermTransformer: collections ──────────────────────────────────────────────

def test_list_literal():
    # Python lists are terms directly — result is a plain list.
    # nv
    node = term_eval("[a, b, c]", list)
    assert len(node) == 3
    assert all(isinstance(e, sa.LoadName) for e in node)


def test_empty_list():
    # nv
    node = term_eval("[]", list)
    assert node == []


def test_tuple_literal():
    # nv
    node = term_eval("(a, b)", sa.TupleLiteral)
    assert len(node.elements) == 2


def test_set_literal():
    # nv
    node = term_eval("{a, b}", sa.SetLiteral)
    assert len(node.elements) == 2


def test_dict_literal():
    # nv
    node = term_eval("{'k': v}", DictTerm)
    assert len(node) == 1
    assert 'k' in node
    assert isinstance(node['k'], sa.LoadName)


# ── TermTransformer: call expressions ─────────────────────────────────────────

def test_call_positional():
    # nv
    node = term_eval("f(a, b)", sa.Call)
    assert isinstance(node.func, sa.LoadName)
    assert node.func.name == 'f'
    assert len(node.args) == 2
    assert isinstance(node.args[0], sa.LoadName)


def test_call_keyword():
    # nv
    node = term_eval("f(x=1)", sa.Call)
    assert len(node.kwargs) == 1
    kw = node.kwargs[0]
    assert isinstance(kw, sa.Keyword)
    assert kw.name == 'x'
    assert kw.value == 1   # plain Python int, not IntLiteral


def test_call_string_callable():
    # '+'(a, b) — string used as functor name, e.g. for operators
    # nv
    node = term_eval("'+'(a, b)", sa.Call)
    assert isinstance(node.func, sa.LoadName)
    assert node.func.name == '+'
    assert len(node.args) == 2
    assert all(isinstance(arg, sa.LoadName) for arg in node.args)


def _term_eval_with_quote_map(src: str):
    """``term_eval`` but with the file's quote map threaded in.

    ``term_eval`` builds a bare ``TermTransformer()`` — no quote map, so the
    quote character is unknown and the double-quoted-functor rule cannot
    fire.  These tests are about the rule, so they supply the map the
    EmbedTransformer would have built.
    """
    from clausal.templating.quote_map import build_quote_map

    tree = ast.parse(src, mode='eval')
    ast.fix_missing_locations(tree)
    transformer = TermTransformer(
        source_lines=src.splitlines(keepends=True),
        quote_map=build_quote_map(src.splitlines(keepends=True)),
    )
    transformed = transformer.visit(tree.body)
    expr_tree = ast.fix_missing_locations(ast.Expression(body=transformed))
    return eval(compile(expr_tree, '<test>', 'eval'), _ns())


def test_double_quoted_string_is_never_a_functor():
    """ISO 6.3.3: only an atom can name a functor, and ``"foo"`` is not an
    atom spelling under the strings design.  Refused in every mode, so it
    can land before the mode means anything."""
    with pytest.raises(SyntaxError) as exc_info:
        _term_eval_with_quote_map('"+"(a, b)')
    assert "functor" in str(exc_info.value)


def test_single_quoted_string_callable_survives_the_quote_map():
    node = _term_eval_with_quote_map("'+'(a, b)")
    assert isinstance(node, sa.Call)
    assert isinstance(node.func, sa.LoadName)
    assert node.func.name == '+'


def test_call_string_callable_keyword():
    # nv
    node = term_eval("'f'(x=1)", sa.Call)
    assert isinstance(node.func, sa.LoadName)
    assert node.func.name == 'f'


# ── TermTransformer: other expressions ────────────────────────────────────────

def test_if_expr():
    # nv
    node = term_eval("if_(c, a, b)", sa.IfExpr)
    assert isinstance(node.test,   sa.LoadName)
    assert isinstance(node.body,   sa.LoadName)
    assert isinstance(node.orelse, sa.LoadName)


def test_if_expr_rejects_two_args():
    # nv
    with pytest.raises(SyntaxError, match="exactly 3"):
        term_eval("if_(c, a)", sa.IfExpr)


def test_if_expr_ternary_rejected():
    # nv
    with pytest.raises(SyntaxError, match="not supported"):
        term_eval("a if c else b", sa.IfExpr)


def test_subscript():
    # nv
    node = term_eval("a[b]", sa.LoadSubscript)
    assert isinstance(node.object, sa.LoadName)
    assert isinstance(node.index,  sa.LoadName)


# ── Dot attribute-access sugar: VAR.key ≡ VAR[key] ───────────────────────────

def test_dot_on_logic_var_lowers_to_subscript():
    """``P.k`` is sugar for ``P[k]`` — same LoadSubscript node."""
    # nv
    node = term_eval("P.k", sa.LoadSubscript)
    assert isinstance(node.index, sa.LoadName)
    assert node.index.name == "k"


def test_dot_atom_key_matches_bracket_form():
    """``P.k`` and ``P[k]`` produce structurally identical nodes."""
    # nv
    dotted = term_eval("P.k", sa.LoadSubscript)
    bracket = term_eval("P[k]", sa.LoadSubscript)
    assert type(dotted.index) is type(bracket.index)
    assert dotted.index.name == bracket.index.name


def test_dot_variable_key_lowers_to_subscript():
    """``P.KEY`` reads the key named by the logic variable ``KEY``."""
    # nv
    node = term_eval("P.KEY", sa.LoadSubscript)
    # A logic-variable key is a Var, not a LoadName atom reference.
    assert not isinstance(node.index, sa.LoadName)


def test_dot_chain_lowers_to_nested_subscripts():
    """``P.a.b`` is ``P[a][b]`` — outermost attribute is the outer index."""
    # nv
    node = term_eval("P.a.b", sa.LoadSubscript)
    assert node.index.name == "b"
    assert isinstance(node.object, sa.LoadSubscript)
    assert node.object.index.name == "a"


def test_dot_on_non_variable_base_still_loadattr():
    """``mod.pred`` keeps the qualified-name behaviour."""
    # nv
    node = term_eval("mod.pred", sa.LoadAttr)
    assert node.attr == "pred"


def test_dot_method_call_on_logic_var_rejected():
    """``P.foo(A)`` — the method-call form stays a SyntaxError."""
    # nv
    with pytest.raises(SyntaxError, match="[Mm]ethod-call"):
        term_eval("P.foo(A)", sa.LoadSubscript)


def test_dot_logic_var_attr_on_module_base_still_rejected():
    """``mod.X`` — a logic variable cannot name a qualified predicate."""
    # nv
    with pytest.raises(SyntaxError, match="Logic variable"):
        term_eval("mod.X", sa.LoadAttr)


def test_starred():
    # *a in a list context — result is a plain Python list
    # nv
    node = term_eval("[*a]", list)
    assert isinstance(node[0], sa.StarUnpack)


def test_list_comp():
    # nv
    node = term_eval("[x for x in xs]", sa.ListComp)
    assert isinstance(node.element, sa.LoadName)
    assert len(node.clauses) == 1
    clause = node.clauses[0]
    assert isinstance(clause, sa.ForClause)
    assert isinstance(clause.iterable, sa.LoadName)


def test_lambda_syntax_rejected():
    # nv
    with pytest.raises(SyntaxError, match="arrow syntax"):
        term_eval("lambda x: x", object)


# ── TermTransformer: position is always set ───────────────────────────────────

def test_position_set():
    # nv
    node = term_eval("x + y", sa.Add)
    lineno, col_offset, end_lineno, end_col_offset = node.position
    assert lineno == 1
    assert col_offset == 0


# ── EmbedTransformer: '--' escape ─────────────────────────────────────────────

def test_embed_double_dash():
    # '--' applies to its immediate operand; wrap the whole expression in parens.
    # nv
    ns = embed_exec("result = --(x + y)")
    assert isinstance(ns['result'], sa.Add)
    assert isinstance(ns['result'].left,  sa.LoadName)
    assert isinstance(ns['result'].right, sa.LoadName)


def test_embed_double_dash_nested():
    # nv
    ns = embed_exec("result = --'hello'")
    assert ns['result'] == 'hello'   # plain Python string, not StringLiteral


def test_embed_spaced_double_dash_not_escaped():
    # '- -x' (with space) must NOT be treated as the '--' escape
    # nv
    ns = embed_exec("result = - -42")
    # regular Python double-negation, result is 42 (an int, not a simple_ast node)
    assert ns['result'] == 42


def test_embed_normal_code_unchanged():
    # nv
    ns = embed_exec("x = 1 + 2")
    assert ns['x'] == 3


# ── EmbedTransformer: trailing-comma fact notation ────────────────────────────

def test_embed_trailing_comma_defines_fact():
    # Trailing-comma fact: ``f(a),`` goes through $define_predicate with body=True.
    # nv
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
    # nv
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
    # nv
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
    # nv
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
    # nv
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
    # nv
    point = _make_functor_class("point", "x_", "y_")
    result = point(x_=1)
    assert result.x_ == 1
    assert isinstance(result.y_, RealVar)


def test_partial_term_explicit_none_preserved():
    # nv
    point = _make_functor_class("point", "x_", "y_")
    result = point(x_=1, y_=None)
    assert result.y_ is None


def test_partial_term_no_args_all_vars():
    # nv
    point = _make_functor_class("point", "x_", "y_")
    result = point()
    assert isinstance(result.x_, RealVar)
    assert isinstance(result.y_, RealVar)


def test_partial_term_fresh_vars_each_call():
    # nv
    point = _make_functor_class("point", "x_", "y_")
    r1 = point(x_=1)
    r2 = point(x_=1)
    assert r1.y_ is not r2.y_


# ── TermTransformer: anonymous variable _ ─────────────────────────────────────


def test_anon_var_is_var():
    """Bare _ in predicate context → fresh Var(), not LoadName."""
    # nv
    ns = {"Var": RealVar}
    tree = ast.parse("_", mode="eval")
    ast.fix_missing_locations(tree)
    transformed = TermTransformer().visit(tree.body)
    expr = ast.fix_missing_locations(ast.Expression(body=transformed))
    result = eval(compile(expr, "<test>", "eval"), ns)
    assert isinstance(result, RealVar)


def test_anon_var_fresh_each_occurrence():
    """Two _ in the same expression yield distinct Var objects."""
    # nv
    ns = {"Var": RealVar}
    # Eval _ == _ — both sides should be different Var objects
    tree = ast.parse("(_ == _)", mode="eval")
    ast.fix_missing_locations(tree)
    transformed = TermTransformer().visit(tree.body)
    expr = ast.fix_missing_locations(ast.Expression(body=transformed))
    from clausal.pythonic_ast import nodes as sa
    result = eval(compile(expr, "<test>", "eval"), {**{n: getattr(sa, n) for n in sa.__all__}, "Var": RealVar})
    assert isinstance(result, sa.ArithEq)
    assert isinstance(result.left, RealVar)
    assert isinstance(result.right, RealVar)
    assert result.left is not result.right  # distinct Var objects


def test_anon_var_not_reused_like_named_var():
    """Named vars (X) are reused; _ is always fresh."""
    # nv
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


# ── walrus (:=) removal (Phase 2) ─────────────────────────────────────────────

def test_walrus_error_names_all_replacements():
    """The `:=` SyntaxError teaches every replacement idiom.

    ':=' kind-of-worked as eager arithmetic, so LLMs reached for it where
    ``==`` / ``is`` were meant; the removal error must point at ``eval_/2``
    (the old behaviour), ``==``, ``is``, and ``++``.
    """
    tree = ast.parse("(Y := X * 2)", mode="eval")
    ast.fix_missing_locations(tree)
    with pytest.raises(SyntaxError) as exc_info:
        TermTransformer().visit(tree.body)
    msg = str(exc_info.value)
    assert "eval_" in msg and "==" in msg and "is" in msg and "++" in msg
