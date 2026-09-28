"""Tests for clausal → Prolog source emission (Phase 1.2)."""

import pytest

from clausal.tools.prolog_ast import (
    PAtom, PVar, PNumber, PString, PCompound, PList, PCurly,
    PClause, PDCGRule, PDirective, PModule,
)
from clausal.tools.prolog_operators import OperatorTable
from clausal.tools.clausal_to_prolog import (
    UntranslatableConstructError,
    _quote_atom as _quote_atom_ref,
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

    def test_var_names_are_re_exported_from_clausal_to_prolog(self):
        """The five var-mangling cases that were here are gone.

        They pinned ``_x`` -> ``X`` and ``RESULT`` -> ``Result``; they also
        duplicated tests/test_prolog_dialect.py verbatim (DUPLICATE_TESTS.md
        recorded the pairing).  Both functions are the identity now, so an
        emission test asserting ``f(x) == x`` had no subject.  Injectivity,
        round-trip fidelity and the wildcard are pinned in
        tests/test_prolog_var_identity.py instead.

        What this file can still say that the others cannot: the exporter
        re-exports the pair, and it is the SAME pair — an emitter that grew a
        private mangler of its own would slip past a dialect-module test.
        """
        from clausal.tools import prolog_dialect
        assert clausal_var_to_prolog is prolog_dialect.clausal_var_to_prolog
        assert prolog_var_to_clausal is prolog_dialect.prolog_var_to_clausal


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
edge(1, 2),
edge(2, 3),
reach(X, Y) <- edge(X, Y)
reach(X, Y) <- (edge(X, Z), reach(Z, Y))
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
        source = 'double(X, Y) <- eval_(X * 2, Y)'
        result = clausal_source_to_prolog(source)
        assert "double(X, Y) :-" in result
        assert "Y is X * 2" in result

    def test_negation(self):
        # nv
        source = 'safe(X) <- (not danger(X))'
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
        source = '-module(my_mod, [foo(X)])\nfoo(1),\n'
        result = clausal_source_to_prolog(source)
        assert ":- module(my_mod, [foo/1])." in result

    def test_unification(self):
        # nv
        source = 'id(X, Y) <- (X is Y)'
        result = clausal_source_to_prolog(source)
        assert "X = Y" in result

    def test_disequality(self):
        # nv
        source = 'different(X, Y) <- (X is not Y)'
        result = clausal_source_to_prolog(source)
        assert "dif(X, Y)" in result or "X \\= Y" in result

    def test_simple_fact_no_args(self):
        # nv
        source = 'hello(),\n'
        result = clausal_source_to_prolog(source)
        assert "hello." in result

    def test_or_becomes_semicolon(self):
        # nv
        source = 'test() <- (a() or b())'
        result = clausal_source_to_prolog(source)
        assert ";" in result

    def test_comparison_operators(self):
        # nv
        source = 'check(X, Y) <- (X >= Y)'
        result = clausal_source_to_prolog(source)
        assert "X >= Y" in result

    def test_lte_becomes_prolog_lte(self):
        # nv
        source = 'check(X, Y) <- (X <= Y)'
        result = clausal_source_to_prolog(source)
        assert "X =< Y" in result

    def test_clp_arithmetic_eq(self):
        """An UNQUOTED `==` is the CLP constraint and emits `#=`, with its import.

        Ruling 2026-09-18. This test asserted `"X == Y" in result` before that
        ruling; that string now names the OTHER construct, so it is not a
        rename -- the identity case is :meth:`test_structural_eq` below, and
        both are kept so neither direction can go green on the other's
        behaviour.
        """
        # nv
        source = 'same(X, Y) <- (X == Y)'
        result = clausal_source_to_prolog(source)
        assert "#=(X, Y)" in result, result
        # The import travels with the emission: without it the emitted file
        # raises existence_error at CALL time, never at consult time.
        assert ":- use_module(library(clpz), [(#=)/2])." in result, result

    def test_structural_eq(self):
        """A QUOTED `'=='` is ISO term identity and emits `==`, with NO import."""
        # nv
        source = "same(X, Y) <- ('=='(X, Y))"
        result = clausal_source_to_prolog(source)
        assert "X == Y" in result, result
        assert "clpz" not in result, result

    def test_structural_neq(self):
        # nv
        # Ruling R16 (2026-09-29): `!=` is a constraint, so a non-numeric (or
        # not-known-numeric) one exports as dif/2, never the plain test \==.
        source = 'diff(X, Y) <- (X != Y)'
        result = clausal_source_to_prolog(source)
        assert "dif(X, Y)" in result
        assert "\\==" not in result

    @pytest.mark.parametrize("body, goal", [
        ("X != 3", "#\\=(X, 3)"),                 # an integer literal
        ("X != -2", "#\\=(X, -2)"),
        ("X + 1 != Y", "#\\=(X + 1, Y)"),          # arithmetic
        ("X != foo", "dif(X, foo)"),               # an atom
        ("X != 1.5", "dif(X, 1.5)"),               # a float: not CLP(Z)
        ("X != Y", "dif(X, Y)"),                   # unknown
        ("X is not Y", "dif(X, Y)"),
    ])
    def test_not_equal_is_clpz_or_dif(self, body, goal):
        # nv
        source = f"-private([foo])\nne(X, Y) <- ({body}, Y is Y)"
        result = clausal_source_to_prolog(source)
        assert goal in result, result

    def test_numeric_not_equal_imports_its_clpz_operator(self):
        # nv
        result = clausal_source_to_prolog("ne(X) <- (X != 3)")
        assert "use_module(library(clpz), [(#\\=)/2])" in result, result
        both = clausal_source_to_prolog("ne(X) <- (X != 3, X == 4)")
        assert "[(#=)/2, (#\\=)/2]" in both, both
        none = clausal_source_to_prolog("ne(X, Y) <- (X != Y)")
        assert "clpz" not in none, none

    def test_chained_not_equal(self):
        # nv
        result = clausal_source_to_prolog("ne(X, Y) <- (X != Y != 3)")
        assert "dif(X, Y)" in result and "#\\=(Y, 3)" in result, result

    def test_variable_names_cross_unchanged(self):
        """Variables keep their spelling through a full source translation.

        Was: ``foo(X, Head, Result)`` — ``_x`` uppercased, ``_head``
        titlecased, ``RESULT`` titlecased.  Every one of those spellings is a
        logic variable on both sides of the boundary, so translating them was
        renaming for its own sake, and the rename was not even injective.
        Each name here occurs twice, so the singleton post-pass does not fire
        and what is left is the naming rule alone.
        """
        # nv
        source = 'foo(_x, _head, RESULT) <- bar(_x, _head, RESULT)'
        result = clausal_source_to_prolog(source)
        assert "foo(_x, _head, RESULT)" in result
        assert "bar(_x, _head, RESULT)" in result

    def test_string_literals(self):
        # nv -- a str literal DENOTES AN ATOM (R2); "hello world" needs
        # quoting only because of the space, and is a QUOTED ATOM, not a
        # double-quoted char list. See TestStrLiteralIsAtom below.
        source = '-double_quotes(atom)\ntest("hello world"),\n'
        result = clausal_source_to_prolog(source)
        assert "'hello world'" in result
        assert '"hello world"' not in result

    def test_integer_literals(self):
        # nv
        source = 'edge(1, 2),\n'
        result = clausal_source_to_prolog(source)
        assert "edge(1, 2)." in result

    def test_empty_list(self):
        # nv
        source = 'foo([]),\n'
        result = clausal_source_to_prolog(source)
        assert "[]" in result

    def test_list_literal(self):
        # nv
        source = 'foo([1, 2, 3]),\n'
        result = clausal_source_to_prolog(source)
        assert "[1, 2, 3]" in result

    def test_builtin_name_mapping(self):
        """Builtin names map correctly."""
        # nv
        source = 'test() <- findall(X, member(X, L), R)'
        result = clausal_source_to_prolog(source)
        assert "findall" in result
        assert "member" in result

    def test_import_from_directive(self):
        # nv
        source = '-import_from(tests.fixtures.importable_utils, [helper, double])'
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
        source = 'edge(1, 2),\n'
        pmod = clausal_source_to_prolog_ast(source)
        assert len(pmod.items) == 1
        item = pmod.items[0]
        assert isinstance(item, PClause)
        assert item.body is None
        assert isinstance(item.head, PCompound)
        assert item.head.functor == "edge"

    def test_rule_has_body(self):
        # nv
        source = 'reach(X, Y) <- edge(X, Y)'
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
        """Names cross unchanged; the singleton post-pass still fires.

        The two passes used to compound: ``_x`` became ``X``, which no longer
        carried a leading underscore, so the singleton pass put one back and
        the argument arrived as ``_X``.  Identity removes the first step, and
        a Clausal ``_x``-style name is now already underscore-led — the
        singleton pass leaves it alone rather than double-prefixing it.

        The pass itself is NOT dead, so an ALL-CAPS singleton is included:
        it has no leading underscore of its own and still gets one, which is
        what silences the ISO singleton warning it exists to silence.
        """
        # nv
        source = 'foo(_x, _head, RESULT),\n'
        pmod = clausal_source_to_prolog_ast(source)
        item = pmod.items[0]
        assert isinstance(item, PClause)
        head = item.head
        assert isinstance(head, PCompound)
        assert head.args[0] == PVar("_x")
        assert head.args[1] == PVar("_head")
        assert head.args[2] == PVar("_RESULT")

    def test_list_with_star_unpack(self):
        # nv
        source = 'foo([H, *T]),\n'
        pmod = clausal_source_to_prolog_ast(source)
        item = pmod.items[0]
        head = item.head
        lst = head.args[0]
        assert isinstance(lst, PList)
        assert lst.tail is not None  # has tail

    def test_negation_becomes_naf(self):
        # nv
        source = 'safe(X) <- (not danger(X))'
        pmod = clausal_source_to_prolog_ast(source)
        item = pmod.items[0]
        body = item.body
        assert isinstance(body, PCompound)
        assert body.functor == "\\+"

    def test_eval_becomes_is(self):
        # nv
        source = 'double(X, Y) <- eval_(X * 2, Y)'
        pmod = clausal_source_to_prolog_ast(source)
        item = pmod.items[0]
        body = item.body
        assert isinstance(body, PCompound)
        assert body.functor == "is"

    def test_and_becomes_conjunction(self):
        # nv
        source = 'test() <- (a() and b())'
        pmod = clausal_source_to_prolog_ast(source)
        item = pmod.items[0]
        body = item.body
        assert isinstance(body, PCompound)
        assert body.functor == ","

    def test_or_becomes_disjunction(self):
        # nv
        source = 'test() <- (a() or b())'
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
        out = clausal_source_to_prolog("add_one(X, Y) <- eval_(X + 1, Y)\n")
        assert "Y is X + 1" in out, out
        assert "eval_" not in out, out


# ── Literal mapping: a Clausal str literal DENOTES AN ATOM ───────────
#
# AUTHORITY (user-ratified, R2 family): under the current Python surface a
# Clausal ``str`` literal denotes an ATOM. Atoms are global strs by spelling;
# there is no separate string value, so ``'x'``/``"x"`` in source IS the atom
# ``x`` and unifies with a same-spelling imported atom because they are the
# SAME Python object. Text:
# ``/workspace/clausal-bug-fix/implementation_plans/tagged-tuple-term-representation.md``
# line 231, "Surface literal rulings" (user 2026-09-04, re-confirmed P3-2).
#
# Verified against the live engine before this change was written: an atom
# imported from another module derefs to a plain ``str`` and
# ``atom == "spelling"`` / ``atom is sys.intern("spelling")`` are both True
# (see ``compiler_v2._process_bare_atom_refs``: ``module_dict[name] =
# predicate_builtins.setdefault(name, name)`` -- "no class is minted (R2)").
#
# The ISO-reader rules in that same section (single quotes = quoted atom,
# double quotes = char list) govern the FUTURE surface, not what this
# translator reads today: today's input is Python, where ``'x'`` and ``"x"``
# are one and the same ``str``.
#
# The previous mapping (str -> PString -> Prolog double-quoted char list) was
# faithful to the RETIRED pre-P3-1 semantics, in which ``str`` was Clausal's
# string type.

class TestStrLiteralIsAStringByDefault:
    """The default -double_quotes mode is ``chars`` (2026-09-26): a ``"..."``
    literal in a module that declares nothing is a STRING, emitted as the
    Prolog double-quoted token both target engines read as chars."""

    def test_plain_str_literal_emits_a_prolog_string(self):
        out = clausal_source_to_prolog('ok(X) <- (X is "hello")\n')
        assert 'X = "hello".' in out, out

    def test_str_literal_is_a_pstring_in_the_ast(self):
        from clausal.tools.prolog_ast import PString
        pmod = clausal_source_to_prolog_ast('ok(X) <- (X is "hello")\n')
        rhs = pmod.items[0].body.args[1]
        assert isinstance(rhs, PString), rhs

    def test_single_quoted_is_still_an_atom(self):
        out = clausal_source_to_prolog("ok(X) <- (X is 'a b')\n")
        assert "X = 'a b'." in out, out


class TestStrLiteralIsAtom:
    """`_convert_constant`'s str branch emits an ATOM, not a char list, under
    ``-double_quotes(atom)`` -- the opt-out since the 2026-09-26 flip."""

    def test_plain_str_literal_emits_bare_atom(self):
        out = clausal_source_to_prolog('-double_quotes(atom)\nok(X) <- (X is "hello")\n')
        assert "X = hello." in out, out
        assert '"hello"' not in out, out

    def test_str_literal_is_a_patom_in_the_ast(self):
        pmod = clausal_source_to_prolog_ast('-double_quotes(atom)\nok(X) <- (X is "hello")\n')
        rhs = pmod.items[0].body.args[1]
        assert isinstance(rhs, PAtom), rhs
        assert rhs.name == "hello"

    def test_str_literal_needing_quotes_is_quoted(self):
        out = clausal_source_to_prolog('-double_quotes(atom)\nok(X) <- (X is "a b")\n')
        assert "X = 'a b'." in out, out

    def test_str_literal_in_argument_position(self):
        out = clausal_source_to_prolog('-double_quotes(atom)\nfact(X) <- p("k", X)\n')
        assert "p(k, X)" in out, out

    def test_test_clause_head_name_becomes_quoted_atom(self):
        # The G3 driver addresses test clauses BY NAME; head and generated
        # name list come from one emission source, so they move together.
        out = clausal_source_to_prolog('-double_quotes(atom)\ntest("fib 0") <- fib(0, 0)\n')
        assert "test('fib 0')" in out, out

    def test_dict_key_and_value_both_become_atoms(self):
        out = clausal_source_to_prolog('-double_quotes(atom)\nok(X) <- (X is {"label": "hi there"})\n')
        assert "attribute(label, 'hi there')" in out, out

    def test_dcg_terminal_list_of_str_becomes_atoms(self):
        out = clausal_source_to_prolog('-double_quotes(atom)\ngreeting() >> (["hello", "world"])\n')
        assert "[hello, world]" in out, out


class TestAtomQuotingIsIsoSafe:
    """`_quote_atom`/`_needs_quoting` are the emitter for every migrated
    literal -- each case below was verified by consulting the emitted text in
    real Scryer and reading the atom back with ``atom_codes/2``."""

    OP = OperatorTable.iso_default()

    def _emit(self, name):
        return emit_term(PAtom(name), self.OP)

    @pytest.mark.parametrize("name,expected", [
        ("hello", "hello"),
        ("a b", "'a b'"),
        ("it's", r"'it\'s'"),
        ('say "hi"', "'say \"hi\"'"),
        ("line1\nline2", r"'line1\nline2'"),   # class G: the newline defect
        ("a\tb", r"'a\tb'"),
        ("a\\b", r"'a\\b'"),
        ("", "''"),
        ("Foo", "'Foo'"),
        ("_foo", "'_foo'"),
        ("1abc", "'1abc'"),
    ])
    def test_quoting_shapes(self, name, expected):
        assert self._emit(name) == expected

    def test_comma_atom_must_be_quoted(self):
        # RED before this change: `_needs_quoting` listed "," as a special
        # atom needing no quotes, so a `,` literal emitted `p(,)` --
        # Scryer: error(syntax_error(incomplete_reduction)). Verified.
        assert self._emit(",") == "','"

    def test_solitary_dot_atom_must_be_quoted(self):
        # Bare `.` collides with the end token: `X = .` + the clause
        # terminator reads as `..`. Scryer rejects it; `'.'` is accepted.
        assert self._emit(".") == "'.'"

    @pytest.mark.parametrize("name", ["/*", "/*/", "/**/"])
    def test_graphic_atom_beginning_with_comment_open_is_quoted(self, name):
        # ISO 6.4.2: a graphic token may not BEGIN with `/*`. Unquoted,
        # `t(/*).` opens a comment that swallows the rest of the file and
        # Scryer reports syntax_error(incomplete_reduction). Verified.
        assert self._emit(name) == _quote_atom_ref(name)

    @pytest.mark.parametrize("name", ["*/*", "//*", "-/*", "+/*+", "*/"])
    def test_comment_open_inside_a_graphic_atom_is_harmless(self, name):
        # The rule is LEADING-position only: tokenization is maximal munch, so
        # once inside a graphic token `/*` is just more graphic characters.
        # Each of these consults unquoted in Scryer -- verified -- so quoting
        # them would be needless churn.
        assert self._emit(name) == name

    def test_non_ascii_alphanumeric_is_not_treated_as_plain(self):
        # str.isalnum() is true for characters no ISO reader accepts in an
        # unquoted atom (superscripts, etc.), so it cannot be the test.
        assert self._emit("a²") == "'a²'"


class TestBytesLiteralUnchanged:
    """`b"..."` is PARKED, not migrated.

    Whether Python ``bytes`` keeps unifying with an int list once ``b"..."``
    denotes a code list is a SURFACE-phase question the rulings explicitly
    park ("same shape as the retired str~list bridge, NOT a Phase 3 concern",
    tagged-tuple-term-representation.md:~248). So the literal migration must
    leave it exactly as it was: it still falls through ``_convert_constant``'s
    final ``PAtom(str(value))``, which stringifies the Python repr. Verified
    byte-identical against the pre-migration translator.
    """

    def test_bytes_literal_emission_is_untouched(self):
        out = clausal_source_to_prolog('ok(X) <- (X is b"abc")')
        assert out.strip() == "ok(X) :-\n    X = 'b\\'abc\\''."


class TestBracketAtomLiteralIsFaithful:
    """`"[]"` / `"{}"` used to be the one literal the atom mapping could not
    render faithfully (f47e1a8e warned, and refused under strict). THE FLIP
    (2026-09-06-atoms-as-cells-strings §11) made the engine agree with ISO
    6.3.5 -- the atom `[]` IS the empty list on both sides -- so the collapse
    is faithful and the warning is gone (item J, 2026-09-07); see
    tests/test_prolog_execution.py::TestBracketAtomLiteralAgrees.
    """

    @pytest.mark.parametrize("literal", ["[]", "{}"])
    def test_emitted_bare_with_no_warning(self, literal):
        out = clausal_source_to_prolog('ok(K) <- (K is %r)' % literal)
        assert "WARNING" not in out, out
        assert f"K = {literal}" in out, out

    def test_strict_mode_accepts_it(self):
        out = clausal_source_to_prolog('-double_quotes(atom)\nok(K) <- (K is "[]")', strict=True)
        assert "K = []" in out, out


def test_titlecase_unit_name_still_lowers_as_a_quantity():
    """A unit is a NAME position, in the translator as in the engine.

    ``-import_from(py.units, [Metre])`` is the SUPPORTED deprecation-window
    spelling and still resolves, so ``5.0(Metre)`` is a quantity: the
    magnitude survives and the unit is discarded into a note, exactly as the
    lowercase spelling is.  Reading the unit NAME as a logic variable made
    ``_try_quantity`` return None, and the clause exported as the
    unrepresentable ``X = ???(_Metre)`` under a bogus "compound unit
    expression" refusal -- a working quantity silently exported as something
    else."""
    from clausal.tools.clausal_to_prolog import clausal_source_to_prolog
    out = clausal_source_to_prolog(
        "-import_from(py.units, [Metre])\n"
        "-module(tc_unit, [speed(X)])\n"
        "speed(X) <- (X is 5.0(Metre))\n"
    )
    text = out if isinstance(out, str) else str(out)
    assert "X = 5.0" in text, text
    assert "???" not in text, text
    assert "compound unit expression" not in text, text
    assert "Metre" in text  # kept as the unit note


def test_lowercase_unit_name_lowers_the_same_way():
    """The control, so the assertion above cannot pass by accident."""
    from clausal.tools.clausal_to_prolog import clausal_source_to_prolog
    out = clausal_source_to_prolog(
        "-import_from(py.units, [metre])\n"
        "-module(tc_unit_lc, [speed(X)])\n"
        "speed(X) <- (X is 5.0(metre))\n"
    )
    text = out if isinstance(out, str) else str(out)
    assert "X = 5.0" in text, text
    assert "???" not in text, text
