"""Tests for clausal → Prolog source emission (Phase 1.2)."""

import pytest

from clausal.tools.prolog_ast import (
    PAtom, PVar, PNumber, PString, PCompound, PList, PCurly,
    PClause, PDCGRule, PDirective, PModule,
)
from clausal.tools.prolog_operators import OperatorTable
from clausal.tools.clausal_to_prolog import (
    emit_term, emit_item, emit_module,
    clausal_source_to_prolog, clausal_source_to_prolog_ast,
    pascal_to_snake, snake_to_pascal,
    clausal_var_to_prolog, prolog_var_to_clausal,
)


# ── Naming ───────────────────────────────────────────────────────────

class TestNaming:
    def test_pascal_to_snake_simple(self):
        assert pascal_to_snake("FooBar") == "foo_bar"

    def test_pascal_to_snake_allcaps(self):
        assert pascal_to_snake("CLP") == "clp"

    def test_pascal_to_snake_mixed(self):
        assert pascal_to_snake("AllDifferent") == "all_different"

    def test_pascal_to_snake_dcg(self):
        assert pascal_to_snake("DCGRule") == "dcg_rule"

    def test_snake_to_pascal_simple(self):
        assert snake_to_pascal("foo_bar") == "FooBar"

    def test_snake_to_pascal_copy_term(self):
        assert snake_to_pascal("copy_term") == "CopyTerm"

    def test_var_trailing_underscore(self):
        assert clausal_var_to_prolog("X_") == "X"

    def test_var_allcaps(self):
        assert clausal_var_to_prolog("RESULT") == "Result"

    def test_var_single_letter(self):
        assert clausal_var_to_prolog("X") == "X"

    def test_var_anon(self):
        assert clausal_var_to_prolog("_") == "_"

    def test_var_lowercase_trailing(self):
        assert clausal_var_to_prolog("head_") == "Head"


# ── emit_term ────────────────────────────────────────────────────────

class TestEmitTerm:
    def test_atom(self):
        assert emit_term(PAtom("foo"), OperatorTable.iso_default()) == "foo"

    def test_atom_needs_quoting(self):
        result = emit_term(PAtom("Hello World", quoted=True), OperatorTable.iso_default())
        assert result == "'Hello World'"

    def test_var(self):
        assert emit_term(PVar("X"), OperatorTable.iso_default()) == "X"

    def test_anon_var(self):
        assert emit_term(PVar("_"), OperatorTable.iso_default()) == "_"

    def test_integer(self):
        assert emit_term(PNumber(42), OperatorTable.iso_default()) == "42"

    def test_float(self):
        assert emit_term(PNumber(3.14), OperatorTable.iso_default()) == "3.14"

    def test_string(self):
        assert emit_term(PString("hello"), OperatorTable.iso_default()) == '"hello"'

    def test_compound_simple(self):
        t = PCompound("foo", (PAtom("a"), PVar("X")))
        assert emit_term(t, OperatorTable.iso_default()) == "foo(a, X)"

    def test_compound_binary_op(self):
        t = PCompound("+", (PNumber(1), PNumber(2)))
        assert emit_term(t, OperatorTable.iso_default()) == "1 + 2"

    def test_compound_op_precedence(self):
        # 1 + 2 * 3: * (400) binds tighter than + (500), no parens needed on RHS
        t = PCompound("+", (PNumber(1), PCompound("*", (PNumber(2), PNumber(3)))))
        assert emit_term(t, OperatorTable.iso_default()) == "1 + 2 * 3"

    def test_compound_op_needs_parens(self):
        # (1 + 2) * 3: + (500) in context of * (400) needs parens
        t = PCompound("*", (PCompound("+", (PNumber(1), PNumber(2))), PNumber(3)))
        assert emit_term(t, OperatorTable.iso_default()) == "(1 + 2) * 3"

    def test_conjunction(self):
        t = PCompound(",", (PCompound("a", ()), PCompound("b", ())))
        result = emit_term(t, OperatorTable.iso_default())
        assert result == "a, b"

    def test_disjunction(self):
        t = PCompound(";", (PCompound("a", ()), PCompound("b", ())))
        result = emit_term(t, OperatorTable.iso_default())
        # Disjunction at top level (context_prec=1201) should not need extra parens
        assert "a ; b" in result

    def test_negation(self):
        t = PCompound("\\+", (PCompound("a", ()),))
        result = emit_term(t, OperatorTable.iso_default())
        assert result == "\\+ a"

    def test_list_proper(self):
        t = PList((PNumber(1), PNumber(2), PNumber(3)))
        assert emit_term(t, OperatorTable.iso_default()) == "[1, 2, 3]"

    def test_list_partial(self):
        t = PList((PVar("H"),), tail=PVar("T"))
        assert emit_term(t, OperatorTable.iso_default()) == "[H|T]"

    def test_list_empty(self):
        t = PList(())
        assert emit_term(t, OperatorTable.iso_default()) == "[]"

    def test_curly(self):
        t = PCurly(PCompound(">", (PVar("X"), PNumber(0))))
        assert emit_term(t, OperatorTable.iso_default()) == "{X > 0}"

    def test_unify(self):
        t = PCompound("=", (PVar("X"), PNumber(1)))
        assert emit_term(t, OperatorTable.iso_default()) == "X = 1"

    def test_is_eval(self):
        t = PCompound("is", (PVar("Y"), PCompound("*", (PVar("X"), PNumber(2)))))
        assert emit_term(t, OperatorTable.iso_default()) == "Y is X * 2"

    def test_negative_number(self):
        assert emit_term(PNumber(-1), OperatorTable.iso_default()) == "-1"

    def test_zero_arity_compound(self):
        t = PCompound("foo", ())
        assert emit_term(t, OperatorTable.iso_default()) == "foo"

    def test_nested_compound(self):
        t = PCompound("f", (PCompound("g", (PAtom("a"),)), PVar("X")))
        assert emit_term(t, OperatorTable.iso_default()) == "f(g(a), X)"

    def test_slash_indicator(self):
        t = PCompound("/", (PAtom("foo"), PNumber(2)))
        assert emit_term(t, OperatorTable.iso_default()) == "foo/2"

    def test_mod_operator(self):
        t = PCompound("mod", (PNumber(10), PNumber(3)))
        assert emit_term(t, OperatorTable.iso_default()) == "10 mod 3"

    def test_list_with_multiple_elements_and_tail(self):
        t = PList((PNumber(1), PNumber(2)), tail=PVar("T"))
        assert emit_term(t, OperatorTable.iso_default()) == "[1, 2|T]"


# ── emit_item ────────────────────────────────────────────────────────

class TestEmitItem:
    def test_fact(self):
        c = PClause(head=PCompound("edge", (PNumber(1), PNumber(2))))
        assert emit_item(c, OperatorTable.iso_default()) == "edge(1, 2).\n"

    def test_rule(self):
        c = PClause(
            head=PCompound("reach", (PVar("X"), PVar("Y"))),
            body=PCompound("edge", (PVar("X"), PVar("Y")))
        )
        result = emit_item(c, OperatorTable.iso_default())
        assert "reach(X, Y) :-" in result
        assert "edge(X, Y)" in result
        assert result.endswith(".\n")

    def test_rule_with_conjunction(self):
        c = PClause(
            head=PCompound("reach", (PVar("X"), PVar("Y"))),
            body=PCompound(",", (
                PCompound("edge", (PVar("X"), PVar("Z"))),
                PCompound("reach", (PVar("Z"), PVar("Y")))
            ))
        )
        result = emit_item(c, OperatorTable.iso_default())
        assert "reach(X, Y) :-" in result
        assert "edge(X, Z)" in result
        assert "reach(Z, Y)" in result

    def test_dcg_rule(self):
        r = PDCGRule(
            head=PAtom("greeting"),
            body=PList((PAtom("hello"), PAtom("world")))
        )
        result = emit_item(r, OperatorTable.iso_default())
        assert "greeting -->" in result
        assert "[hello, world]" in result

    def test_directive(self):
        d = PDirective(PCompound("dynamic", (
            PCompound("/", (PAtom("color"), PNumber(2))),
        )))
        result = emit_item(d, OperatorTable.iso_default())
        assert result.startswith(":- ")
        assert "dynamic" in result

    def test_fact_atom_head(self):
        c = PClause(head=PAtom("hello"))
        assert emit_item(c, OperatorTable.iso_default()) == "hello.\n"


# ── emit_module ──────────────────────────────────────────────────────

class TestEmitModule:
    def test_empty_module(self):
        m = PModule(())
        result = emit_module(m, OperatorTable.iso_default())
        assert result == ""

    def test_simple_module(self):
        m = PModule((
            PClause(head=PCompound("edge", (PNumber(1), PNumber(2)))),
            PClause(head=PCompound("edge", (PNumber(2), PNumber(3)))),
        ))
        result = emit_module(m, OperatorTable.iso_default())
        assert "edge(1, 2)." in result
        assert "edge(2, 3)." in result


# ── Full translation (clausal source → Prolog source) ────────────────

class TestFullTranslation:
    """End-to-end: clausal source text → Prolog source text."""

    def test_edge_graph(self):
        source = '''
Edge(1, 2),
Edge(2, 3),
Reach(X, Y) <- Edge(X, Y)
Reach(X, Y) <- (Edge(X, Z), Reach(Z, Y))
'''
        result = clausal_source_to_prolog(source)
        assert "edge(1, 2)." in result
        assert "edge(2, 3)." in result
        assert "reach(X, Y) :-" in result
        assert "edge(X, Y)" in result
        assert "edge(X, Z)" in result
        assert "reach(Z, Y)" in result

    def test_arithmetic(self):
        source = 'Double(X, Y) <- (Y := X * 2)'
        result = clausal_source_to_prolog(source)
        assert "double(X, Y) :-" in result
        assert "Y is X * 2" in result

    def test_negation(self):
        source = 'Safe(X) <- (not Danger(X))'
        result = clausal_source_to_prolog(source)
        assert "\\+ danger(X)" in result

    def test_list_spread(self):
        source = 'Append([H, *T], L, [H, *R]) <- Append(T, L, R)'
        result = clausal_source_to_prolog(source)
        assert "[H|T]" in result
        assert "[H|R]" in result

    def test_module_directive(self):
        source = '-module(my_mod, [Foo(X)])'
        result = clausal_source_to_prolog(source)
        assert ":- module(my_mod, [foo/1])." in result

    def test_unification(self):
        source = 'Id(X, Y) <- (X is Y)'
        result = clausal_source_to_prolog(source)
        assert "X = Y" in result

    def test_disequality(self):
        source = 'Different(X, Y) <- (X is not Y)'
        result = clausal_source_to_prolog(source)
        assert "dif(X, Y)" in result or "X \\= Y" in result

    def test_simple_fact_no_args(self):
        source = 'Hello(),\n'
        result = clausal_source_to_prolog(source)
        assert "hello." in result

    def test_or_becomes_semicolon(self):
        source = 'Test() <- (a() or b())'
        result = clausal_source_to_prolog(source)
        assert ";" in result

    def test_comparison_operators(self):
        source = 'Check(X, Y) <- (X >= Y)'
        result = clausal_source_to_prolog(source)
        assert "X >= Y" in result

    def test_lte_becomes_prolog_lte(self):
        source = 'Check(X, Y) <- (X <= Y)'
        result = clausal_source_to_prolog(source)
        assert "X =< Y" in result

    def test_structural_eq(self):
        source = 'Same(X, Y) <- (X == Y)'
        result = clausal_source_to_prolog(source)
        assert "X == Y" in result

    def test_structural_neq(self):
        source = 'Diff(X, Y) <- (X != Y)'
        result = clausal_source_to_prolog(source)
        assert "X \\== Y" in result

    def test_variable_naming(self):
        """Variables follow clausal → Prolog naming conventions."""
        source = 'Foo(X_, head_, RESULT) <- Bar(X_, head_, RESULT)'
        result = clausal_source_to_prolog(source)
        assert "foo(X, Head, Result)" in result
        assert "bar(X, Head, Result)" in result

    def test_string_literals(self):
        source = 'Test("hello world"),\n'
        result = clausal_source_to_prolog(source)
        assert '"hello world"' in result

    def test_integer_literals(self):
        source = 'Edge(1, 2),\n'
        result = clausal_source_to_prolog(source)
        assert "edge(1, 2)." in result

    def test_empty_list(self):
        source = 'Foo([]),\n'
        result = clausal_source_to_prolog(source)
        assert "[]" in result

    def test_list_literal(self):
        source = 'Foo([1, 2, 3]),\n'
        result = clausal_source_to_prolog(source)
        assert "[1, 2, 3]" in result

    def test_builtin_name_mapping(self):
        """Builtin names map correctly."""
        source = 'Test() <- FindAll(X, Member(X, L), R)'
        result = clausal_source_to_prolog(source)
        assert "findall" in result
        assert "member" in result

    def test_import_from_directive(self):
        source = '-import_from(tests.fixtures.importable_utils, [Helper, Double])'
        result = clausal_source_to_prolog(source)
        assert ":- use_module(" in result
        assert "tests/fixtures/importable_utils" in result

    def test_dynamic_directive(self):
        source = '-dynamic(Color(NAME, VALUE))'
        result = clausal_source_to_prolog(source)
        assert ":- dynamic" in result
        assert "color" in result


class TestPrologAstConversion:
    """Test the intermediate clausal → Prolog AST step."""

    def test_simple_fact(self):
        source = 'Edge(1, 2),\n'
        pmod = clausal_source_to_prolog_ast(source)
        assert len(pmod.items) == 1
        item = pmod.items[0]
        assert isinstance(item, PClause)
        assert item.body is None
        assert isinstance(item.head, PCompound)
        assert item.head.functor == "edge"

    def test_rule_has_body(self):
        source = 'Reach(X, Y) <- Edge(X, Y)'
        pmod = clausal_source_to_prolog_ast(source)
        assert len(pmod.items) == 1
        item = pmod.items[0]
        assert isinstance(item, PClause)
        assert item.body is not None

    def test_directive(self):
        source = '-module(my_mod, [Foo(X)])'
        pmod = clausal_source_to_prolog_ast(source)
        assert len(pmod.items) == 1
        item = pmod.items[0]
        assert isinstance(item, PDirective)

    def test_variables_converted(self):
        source = 'Foo(X_, head_),\n'
        pmod = clausal_source_to_prolog_ast(source)
        item = pmod.items[0]
        assert isinstance(item, PClause)
        head = item.head
        assert isinstance(head, PCompound)
        # X_ → PVar("X"), head_ → PVar("Head")
        assert head.args[0] == PVar("X")
        assert head.args[1] == PVar("Head")

    def test_list_with_star_unpack(self):
        source = 'Foo([H, *T]),\n'
        pmod = clausal_source_to_prolog_ast(source)
        item = pmod.items[0]
        head = item.head
        lst = head.args[0]
        assert isinstance(lst, PList)
        assert lst.tail is not None  # has tail

    def test_negation_becomes_naf(self):
        source = 'Safe(X) <- (not Danger(X))'
        pmod = clausal_source_to_prolog_ast(source)
        item = pmod.items[0]
        body = item.body
        assert isinstance(body, PCompound)
        assert body.functor == "\\+"

    def test_named_expr_becomes_is(self):
        source = 'Double(X, Y) <- (Y := X * 2)'
        pmod = clausal_source_to_prolog_ast(source)
        item = pmod.items[0]
        body = item.body
        assert isinstance(body, PCompound)
        assert body.functor == "is"

    def test_and_becomes_conjunction(self):
        source = 'Test() <- (a() and b())'
        pmod = clausal_source_to_prolog_ast(source)
        item = pmod.items[0]
        body = item.body
        assert isinstance(body, PCompound)
        assert body.functor == ","

    def test_or_becomes_disjunction(self):
        source = 'Test() <- (a() or b())'
        pmod = clausal_source_to_prolog_ast(source)
        item = pmod.items[0]
        body = item.body
        assert isinstance(body, PCompound)
        assert body.functor == ";"

    def test_private_directive_omitted(self):
        source = '-private([Choose(X, Y)])'
        pmod = clausal_source_to_prolog_ast(source)
        assert len(pmod.items) == 0
