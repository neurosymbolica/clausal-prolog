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
        # nv
        assert pascal_to_snake("FooBar") == "foo_bar"

    def test_pascal_to_snake_allcaps(self):
        # nv
        assert pascal_to_snake("CLP") == "clp"

    def test_pascal_to_snake_mixed(self):
        # nv
        assert pascal_to_snake("all_different") == "all_different"

    def test_pascal_to_snake_dcg(self):
        # nv
        assert pascal_to_snake("DCGRule") == "dcg_rule"

    def test_snake_to_pascal_simple(self):
        # nv
        assert snake_to_pascal("foo_bar") == "FooBar"

    def test_snake_to_pascal_copy_term(self):
        # nv
        assert snake_to_pascal("copy_term") == "CopyTerm"

    def test_var_leading_underscore(self):
        # nv
        assert clausal_var_to_prolog("_x") == "X"

    def test_var_allcaps(self):
        # nv
        assert clausal_var_to_prolog("RESULT") == "Result"

    def test_var_single_letter(self):
        # nv
        assert clausal_var_to_prolog("X") == "X"

    def test_var_anon(self):
        # nv
        assert clausal_var_to_prolog("_") == "_"

    def test_var_lowercase_leading(self):
        # nv
        assert clausal_var_to_prolog("_head") == "Head"


# ── emit_term ────────────────────────────────────────────────────────

class TestEmitTerm:
    def test_atom(self):
        # nv
        assert emit_term(PAtom("foo"), OperatorTable.iso_default()) == "foo"

    def test_atom_needs_quoting(self):
        # nv
        result = emit_term(PAtom("Hello World", quoted=True), OperatorTable.iso_default())
        assert result == "'Hello World'"

    def test_var(self):
        # nv
        assert emit_term(PVar("X"), OperatorTable.iso_default()) == "X"

    def test_anon_var(self):
        # nv
        assert emit_term(PVar("_"), OperatorTable.iso_default()) == "_"

    def test_integer(self):
        # nv
        assert emit_term(PNumber(42), OperatorTable.iso_default()) == "42"

    def test_float(self):
        # nv
        assert emit_term(PNumber(3.14), OperatorTable.iso_default()) == "3.14"

    def test_string(self):
        # nv
        assert emit_term(PString("hello"), OperatorTable.iso_default()) == '"hello"'

    def test_compound_simple(self):
        # nv
        t = PCompound("foo", (PAtom("a"), PVar("X")))
        assert emit_term(t, OperatorTable.iso_default()) == "foo(a, X)"

    def test_compound_binary_op(self):
        # nv
        t = PCompound("+", (PNumber(1), PNumber(2)))
        assert emit_term(t, OperatorTable.iso_default()) == "1 + 2"

    def test_compound_op_precedence(self):
        # 1 + 2 * 3: * (400) binds tighter than + (500), no parens needed on RHS
        # nv
        t = PCompound("+", (PNumber(1), PCompound("*", (PNumber(2), PNumber(3)))))
        assert emit_term(t, OperatorTable.iso_default()) == "1 + 2 * 3"

    def test_compound_op_needs_parens(self):
        # (1 + 2) * 3: + (500) in context of * (400) needs parens
        # nv
        t = PCompound("*", (PCompound("+", (PNumber(1), PNumber(2))), PNumber(3)))
        assert emit_term(t, OperatorTable.iso_default()) == "(1 + 2) * 3"

    def test_conjunction(self):
        # nv
        t = PCompound(",", (PCompound("a", ()), PCompound("b", ())))
        result = emit_term(t, OperatorTable.iso_default())
        assert result == "a, b"

    def test_disjunction(self):
        # nv
        t = PCompound(";", (PCompound("a", ()), PCompound("b", ())))
        result = emit_term(t, OperatorTable.iso_default())
        # Disjunction at top level (context_prec=1201) should not need extra parens
        assert "a ; b" in result

    def test_negation(self):
        # nv
        t = PCompound("\\+", (PCompound("a", ()),))
        result = emit_term(t, OperatorTable.iso_default())
        assert result == "\\+ a"

    def test_list_proper(self):
        # nv
        t = PList((PNumber(1), PNumber(2), PNumber(3)))
        assert emit_term(t, OperatorTable.iso_default()) == "[1, 2, 3]"

    def test_list_partial(self):
        # nv
        t = PList((PVar("H"),), tail=PVar("T"))
        assert emit_term(t, OperatorTable.iso_default()) == "[H|T]"

    def test_list_empty(self):
        # nv
        t = PList(())
        assert emit_term(t, OperatorTable.iso_default()) == "[]"

    def test_curly(self):
        # nv
        t = PCurly(PCompound(">", (PVar("X"), PNumber(0))))
        assert emit_term(t, OperatorTable.iso_default()) == "{X > 0}"

    def test_unify(self):
        # nv
        t = PCompound("=", (PVar("X"), PNumber(1)))
        assert emit_term(t, OperatorTable.iso_default()) == "X = 1"

    def test_is_eval(self):
        # nv
        t = PCompound("is", (PVar("Y"), PCompound("*", (PVar("X"), PNumber(2)))))
        assert emit_term(t, OperatorTable.iso_default()) == "Y is X * 2"

    def test_negative_number(self):
        # nv
        assert emit_term(PNumber(-1), OperatorTable.iso_default()) == "-1"

    def test_zero_arity_compound(self):
        # nv
        t = PCompound("foo", ())
        assert emit_term(t, OperatorTable.iso_default()) == "foo"

    def test_nested_compound(self):
        # nv
        t = PCompound("f", (PCompound("g", (PAtom("a"),)), PVar("X")))
        assert emit_term(t, OperatorTable.iso_default()) == "f(g(a), X)"

    def test_slash_indicator(self):
        # nv
        t = PCompound("/", (PAtom("foo"), PNumber(2)))
        assert emit_term(t, OperatorTable.iso_default()) == "foo/2"

    def test_mod_operator(self):
        # nv
        t = PCompound("mod", (PNumber(10), PNumber(3)))
        assert emit_term(t, OperatorTable.iso_default()) == "10 mod 3"

    def test_list_with_multiple_elements_and_tail(self):
        # nv
        t = PList((PNumber(1), PNumber(2)), tail=PVar("T"))
        assert emit_term(t, OperatorTable.iso_default()) == "[1, 2|T]"


# ── emit_item ────────────────────────────────────────────────────────

class TestEmitItem:
    def test_fact(self):
        # nv
        c = PClause(head=PCompound("edge", (PNumber(1), PNumber(2))))
        assert emit_item(c, OperatorTable.iso_default()) == "edge(1, 2).\n"

    def test_rule(self):
        # nv
        c = PClause(
            head=PCompound("reach", (PVar("X"), PVar("Y"))),
            body=PCompound("edge", (PVar("X"), PVar("Y")))
        )
        result = emit_item(c, OperatorTable.iso_default())
        assert "reach(X, Y) :-" in result
        assert "edge(X, Y)" in result
        assert result.endswith(".\n")

    def test_rule_with_conjunction(self):
        # nv
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
        # nv
        r = PDCGRule(
            head=PAtom("greeting"),
            body=PList((PAtom("hello"), PAtom("world")))
        )
        result = emit_item(r, OperatorTable.iso_default())
        assert "greeting -->" in result
        assert "[hello, world]" in result

    def test_directive(self):
        # nv
        d = PDirective(PCompound("dynamic", (
            PCompound("/", (PAtom("color"), PNumber(2))),
        )))
        result = emit_item(d, OperatorTable.iso_default())
        assert result.startswith(":- ")
        assert "dynamic" in result

    def test_fact_atom_head(self):
        # nv
        c = PClause(head=PAtom("hello"))
        assert emit_item(c, OperatorTable.iso_default()) == "hello.\n"


# ── emit_module ──────────────────────────────────────────────────────

class TestEmitModule:
    def test_empty_module(self):
        # nv
        m = PModule(())
        result = emit_module(m, OperatorTable.iso_default())
        assert result == ""

    def test_simple_module(self):
        # nv
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
        # nv
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
        # nv
        source = 'Double(X, Y) <- eval_(X * 2, Y)'
        result = clausal_source_to_prolog(source)
        assert "double(X, Y) :-" in result
        assert "Y is X * 2" in result

    def test_negation(self):
        # nv
        source = 'Safe(X) <- (not Danger(X))'
        result = clausal_source_to_prolog(source)
        assert "\\+ danger(X)" in result

    def test_list_spread(self):
        # nv
        source = 'append([H, *T], L, [H, *R]) <- append(T, L, R)'
        result = clausal_source_to_prolog(source)
        assert "[H|T]" in result
        assert "[H|R]" in result

    def test_module_directive(self):
        # nv
        # Foo/1 needs a backing clause or the module-export post-pass
        # (Task 4) drops it as a declaration-only export.
        source = '-module(my_mod, [Foo(X)])\nFoo(1),\n'
        result = clausal_source_to_prolog(source)
        assert ":- module(my_mod, [foo/1])." in result

    def test_unification(self):
        # nv
        source = 'Id(X, Y) <- (X is Y)'
        result = clausal_source_to_prolog(source)
        assert "X = Y" in result

    def test_disequality(self):
        # nv
        source = 'Different(X, Y) <- (X is not Y)'
        result = clausal_source_to_prolog(source)
        assert "dif(X, Y)" in result or "X \\= Y" in result

    def test_simple_fact_no_args(self):
        # nv
        source = 'Hello(),\n'
        result = clausal_source_to_prolog(source)
        assert "hello." in result

    def test_or_becomes_semicolon(self):
        # nv
        source = 'Test() <- (a() or b())'
        result = clausal_source_to_prolog(source)
        assert ";" in result

    def test_comparison_operators(self):
        # nv
        source = 'Check(X, Y) <- (X >= Y)'
        result = clausal_source_to_prolog(source)
        assert "X >= Y" in result

    def test_lte_becomes_prolog_lte(self):
        # nv
        source = 'Check(X, Y) <- (X <= Y)'
        result = clausal_source_to_prolog(source)
        assert "X =< Y" in result

    def test_structural_eq(self):
        # nv
        source = 'Same(X, Y) <- (X == Y)'
        result = clausal_source_to_prolog(source)
        assert "X == Y" in result

    def test_structural_neq(self):
        # nv
        source = 'Diff(X, Y) <- (X != Y)'
        result = clausal_source_to_prolog(source)
        assert "X \\== Y" in result

    def test_variable_naming(self):
        """Variables follow clausal → Prolog naming conventions."""
        # nv
        source = 'Foo(_x, _head, RESULT) <- Bar(_x, _head, RESULT)'
        result = clausal_source_to_prolog(source)
        assert "foo(X, Head, Result)" in result
        assert "bar(X, Head, Result)" in result

    def test_string_literals(self):
        # nv
        source = 'Test("hello world"),\n'
        result = clausal_source_to_prolog(source)
        assert '"hello world"' in result

    def test_integer_literals(self):
        # nv
        source = 'Edge(1, 2),\n'
        result = clausal_source_to_prolog(source)
        assert "edge(1, 2)." in result

    def test_empty_list(self):
        # nv
        source = 'Foo([]),\n'
        result = clausal_source_to_prolog(source)
        assert "[]" in result

    def test_list_literal(self):
        # nv
        source = 'Foo([1, 2, 3]),\n'
        result = clausal_source_to_prolog(source)
        assert "[1, 2, 3]" in result

    def test_builtin_name_mapping(self):
        """Builtin names map correctly."""
        # nv
        source = 'Test() <- findall(X, Member(X, L), R)'
        result = clausal_source_to_prolog(source)
        assert "findall" in result
        assert "member" in result

    def test_import_from_directive(self):
        # nv
        source = '-import_from(tests.fixtures.importable_utils, [Helper, Double])'
        result = clausal_source_to_prolog(source)
        assert ":- use_module(" in result
        assert "tests/fixtures/importable_utils" in result

    def test_dynamic_directive(self):
        # nv
        source = '-dynamic(Color(NAME, VALUE))'
        result = clausal_source_to_prolog(source)
        assert ":- dynamic" in result
        assert "color" in result


class TestPrologAstConversion:
    """Test the intermediate clausal → Prolog AST step."""

    def test_simple_fact(self):
        # nv
        source = 'Edge(1, 2),\n'
        pmod = clausal_source_to_prolog_ast(source)
        assert len(pmod.items) == 1
        item = pmod.items[0]
        assert isinstance(item, PClause)
        assert item.body is None
        assert isinstance(item.head, PCompound)
        assert item.head.functor == "edge"

    def test_rule_has_body(self):
        # nv
        source = 'Reach(X, Y) <- Edge(X, Y)'
        pmod = clausal_source_to_prolog_ast(source)
        assert len(pmod.items) == 1
        item = pmod.items[0]
        assert isinstance(item, PClause)
        assert item.body is not None

    def test_directive(self):
        # nv
        source = '-module(my_mod, [Foo(X)])'
        pmod = clausal_source_to_prolog_ast(source)
        assert len(pmod.items) == 1
        item = pmod.items[0]
        assert isinstance(item, PDirective)

    def test_variables_converted(self):
        # nv
        source = 'Foo(_x, _head),\n'
        pmod = clausal_source_to_prolog_ast(source)
        item = pmod.items[0]
        assert isinstance(item, PClause)
        head = item.head
        assert isinstance(head, PCompound)
        # _x → PVar("X"), _head → PVar("Head")
        assert head.args[0] == PVar("X")
        assert head.args[1] == PVar("Head")

    def test_list_with_star_unpack(self):
        # nv
        source = 'Foo([H, *T]),\n'
        pmod = clausal_source_to_prolog_ast(source)
        item = pmod.items[0]
        head = item.head
        lst = head.args[0]
        assert isinstance(lst, PList)
        assert lst.tail is not None  # has tail

    def test_negation_becomes_naf(self):
        # nv
        source = 'Safe(X) <- (not Danger(X))'
        pmod = clausal_source_to_prolog_ast(source)
        item = pmod.items[0]
        body = item.body
        assert isinstance(body, PCompound)
        assert body.functor == "\\+"

    def test_eval_becomes_is(self):
        # nv
        source = 'Double(X, Y) <- eval_(X * 2, Y)'
        pmod = clausal_source_to_prolog_ast(source)
        item = pmod.items[0]
        body = item.body
        assert isinstance(body, PCompound)
        assert body.functor == "is"

    def test_and_becomes_conjunction(self):
        # nv
        source = 'Test() <- (a() and b())'
        pmod = clausal_source_to_prolog_ast(source)
        item = pmod.items[0]
        body = item.body
        assert isinstance(body, PCompound)
        assert body.functor == ","

    def test_or_becomes_disjunction(self):
        # nv
        source = 'Test() <- (a() or b())'
        pmod = clausal_source_to_prolog_ast(source)
        item = pmod.items[0]
        body = item.body
        assert isinstance(body, PCompound)
        assert body.functor == ";"

    def test_private_directive_omitted(self):
        # nv
        source = '-private([Choose(X, Y)])'
        pmod = clausal_source_to_prolog_ast(source)
        assert len(pmod.items) == 0


class TestEvalBuiltinExport:
    """eval_/2 (eager arithmetic) exports as Prolog is/2."""

    def test_eval_exports_as_is(self):
        # nv
        from clausal.tools.clausal_to_prolog import clausal_source_to_prolog
        out = clausal_source_to_prolog("AddOne(X, Y) <- eval_(X + 1, Y)\n")
        assert "Y is X + 1" in out, out
        assert "eval_" not in out, out
