"""Spec §6.7: display of atoms (arity-0 cells), strings and chars.

Builtin goals are cell-shaped tuples, and ``solve/1`` (module=None) refuses
an unqualified cell goal outright, so the write-family probes run against a
throwaway loaded module — the same convention ``tests/test_atoms_as_cells.py``
and ``tests/test_double_quotes_directive.py`` use.
"""
import contextlib
import io
import re
import os
import tempfile

import pytest

import clausal.import_hook  # noqa: F401 — installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.terms import (
    atom_needs_quotes,
    quote_atom,
    term_html,
    term_pformat,
    term_str,
)
from clausal.logic.cells import chars
from clausal.logic.solve import solve


@pytest.fixture
def mod():
    with tempfile.NamedTemporaryFile(
        suffix=".clausal", mode="w", delete=False
    ) as f:
        f.write("z0,\n")
        path = f.name
    try:
        return _load_module("_writers_atoms_strings_probe", path).__dict__["$module"]
    finally:
        os.unlink(path)


@pytest.mark.parametrize("s,bare", [
    ("foo", True), ("fooBar_1", True), ("Foo", False), ("foo bar", False),
    ("", False), ("[]", True), ("{}", True), ("!", True), (";", True), (",", False),
    ("+", True), ("=..", True), ("hello-world", False), ("_x", False), ("1a", False),
    # A lone `.` is the end token -- quoted, though longer graphic runs
    # containing a dot (`=..` above) stay bare.
    (".", False),
])
def test_atom_needs_quotes(s, bare):
    assert atom_needs_quotes(s) is (not bare)


def test_quote_atom_escapes():
    assert quote_atom("it's") == r"'it\'s'"
    assert quote_atom("a\\b") == r"'a\\b'"
    assert quote_atom("a\nb") == r"'a\nb'"


def test_term_str_arity0_cell_is_bare_spelling():
    assert term_str(("flag",)) == "flag"
    assert term_str(("foo bar",)) == "'foo bar'"
    assert term_str(("foo", ("bar",), 1)) == "foo(bar, 1)"


def test_term_pformat_and_html_arity0():
    assert term_pformat(("flag",)) == "flag"
    assert "flag" in term_html(("flag",)) and "flag()" not in term_html(("flag",))


def test_write_family_prints_cell_atom_bare(mod):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        list(solve(("write", ("flag",)), mod))
        list(solve(("write", ("foo", ("foo bar",))), mod))
    assert buf.getvalue() == "flagfoo(foo bar)"


def test_writeq_quotes_and_write_canonical_is_cons_form(mod):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        list(solve(("writeq", ("foo bar",)), mod))
        list(solve(("write_canonical", ("foo", ("foo bar",), 1)), mod))
        list(solve(("write_canonical", [1, 2]), mod))
        list(solve(("write_canonical", []), mod))
    assert buf.getvalue() == "'foo bar'foo('foo bar',1)'.'(1,'.'(2,[]))[]"


def test_term_canonical_partial_list_and_nesting():
    from clausal.terms import term_canonical, ConcreteSeg, SegList, VarSeg
    from clausal.logic.variables import Var
    assert term_canonical(("f", [("a",), ("b c",)])) == "f('.'(a,'.'('b c',[])))"
    # A PARTIAL list is a SegList (spec §5.4: a Python list is always a
    # PROPER list), so ``[1 | T]`` -- not ``[1, X]`` -- is what renders with
    # the hole in the tail position: ``'.'(1,_N)``.
    t = term_canonical(SegList([ConcreteSeg([1]), VarSeg(Var())]))
    assert t.startswith("'.'(1,_") and t.endswith(")")
    # ...while the proper 2-element list keeps its ``[]`` terminator.  The
    # variable's number is its engine identity, so it is matched, not pinned.
    assert re.fullmatch(r"'\.'\(1,'\.'\(_\d+,\[\]\)\)", term_canonical([1, Var()]))


def test_term_canonical_partial_string_walks_to_chars():
    """A ``SegString`` is walked first and prints as the cons chain of its
    chars with the hole as the tail (spec §6.7)."""
    from clausal.terms import term_canonical, SegString, VarSeg
    from clausal.logic.variables import Var
    out = term_canonical(SegString(["he", VarSeg(Var())]))
    assert re.fullmatch(r"'\.'\(h,'\.'\(e,_\d+\)\)", out), out


def test_term_str_hidden_atom_display_unchanged():
    assert term_str(("m\x1fbar",)) == "m.bar"


def test_term_canonical_has_no_operator_forms():
    """§6.7: canonical output has no operator syntax and no spaces — an
    operator node prints as the ``op(...)`` term it is.  Node fields are
    ``position, left, right``, so the operands must be passed by keyword."""
    from clausal.terms import Add, Div, Mod, Mult, Negate, term_canonical
    assert term_canonical(Div(left=("foo",), right=2)) == "/(foo,2)"
    assert term_canonical(Add(left=1, right=Mult(left=2, right=3))) == "+(1,*(2,3))"
    # ISO spells `%` as mod/2 (9.1.3); a unary operator prints as `-(3)`.
    assert term_canonical(Mod(left=7, right=2)) == "mod(7,2)"
    assert term_canonical(Negate(operand=3)) == "-(3)"


@pytest.mark.parametrize("node_name,functor", [
    ("Lt", "<"),
    ("Gt", ">"),
    ("LtE", "=<"),          # ISO spells `<=` as `=<`
    ("GtE", ">="),
    ("StructuralEq", "=="),      # Prolog ==/2
    ("StructuralNeq", "\\=="),   # Prolog \==/2
    ("ArithEq", "=:="),          # Prolog =:=/2
    ("ArithNeq", "=\\="),        # Prolog =\=/2
])
def test_term_canonical_comparison_functors(node_name, functor):
    """Every comparison node prints as the ISO functor it denotes — the four
    whose Python surface spelling differs (`<=`, `==`, `!=` twice over) and
    the four that pass straight through."""
    from clausal.pythonic_ast import nodes as simple_ast
    from clausal.terms import term_canonical
    node = getattr(simple_ast, node_name)(left=1, right=2)
    assert term_canonical(node) == functor + "(1,2)"


def test_term_canonical_numbers_variables_are_distinct():
    """§6.7: distinct variables print distinctly (``f(X,X,Y)`` is not
    ``f(_,_,_)``), which ISO/Scryer spell ``_N``."""
    from clausal.terms import term_canonical
    from clausal.logic.variables import Var
    X, Y = Var(), Var()
    out = term_canonical(("f", X, X, Y))
    args = out[len("f("):-1].split(",")
    assert args[0] == args[1] != args[2]
    assert all(a.startswith("_") for a in args)


def test_term_canonical_never_colours():
    """Canonical output exists to be compared byte for byte, so it carries
    no ANSI even when a colouring style is current."""
    from clausal.terms import ANSI_COLORS, TermStyle, get_style, set_style, term_canonical
    from clausal.logic.variables import Var
    previous = get_style()
    try:
        set_style(TermStyle(colors=ANSI_COLORS))
        assert "\x1b" not in term_canonical(("f", 1))
        assert term_canonical(("f", 1)) == "f(1)"
        assert "\x1b" not in term_canonical(("f", Var(), [1, ("a",)]))
    finally:
        set_style(previous)


def test_lone_dot_atom_is_quoted():
    """The end-token hazard: a lone ``.`` atom must re-read as an atom."""
    from clausal.terms import term_canonical
    assert quote_atom(".") == "'.'"
    assert term_str((".",)) == "'.'"
    assert term_canonical((".",)) == "'.'"
    # ...and a cell whose functor is spelled `.` is just that cell (§5.4).
    assert term_canonical((".", 1, 2)) == "'.'(1,2)"


def test_writer_helpers_are_exported():
    import clausal.terms as terms_mod
    for name in ("term_canonical", "atom_needs_quotes", "quote_atom", "quote_string"):
        assert name in terms_mod.__all__


# ── Task 15 item 4: write_term/2 and the double_quotes switch ───────────────


def _out(mod, goal):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert len(list(solve(goal, mod))) == 1
    return buf.getvalue()


class TestTermStrDoubleQuotes:
    """``term_str(..., double_quotes=False)`` prints a string as the LIST of
    char atoms it is — the option ISO's ``write_term/2`` calls
    ``double_quotes(false)``, and Scryer's default."""

    def test_double_quotes_false_prints_the_char_list(self):
        assert term_str("abc", double_quotes=False) == "[a, b, c]"
        assert term_str([("a",), ("b",)], double_quotes=False) == "[a, b]"

    def test_double_quotes_true_is_the_default_and_prints_a_string(self):
        assert term_str("abc") == '"abc"'
        assert term_str("abc", double_quotes=True) == '"abc"'
        assert term_str("abc", quoted=False) == "abc"

    def test_a_char_that_needs_quotes_follows_the_quoted_option(self):
        assert term_str(" a", double_quotes=False) == "[' ', a]"
        assert term_str(" a", double_quotes=False, quoted=False) == "[ , a]"

    def test_the_empty_string_is_the_empty_list_in_both_modes(self):
        assert term_str("", double_quotes=False) == "[]"
        assert term_str("", double_quotes=True) == "[]"

    def test_it_threads_into_arguments(self):
        assert term_str(("f", ("a",), "bc"), double_quotes=False) == "f(a, [b, c])"


class TestWriteTerm2:
    """``write_term(Term, Options)`` — the ISO writer with the option list.
    Every expected rendering below is Scryer 0.10.0's, byte for byte: the
    ISO family prints NO space after a comma (fix round 1, item 0)."""

    def test_quoted_alone_prints_a_string_as_its_char_list(self, mod):
        assert _out(mod, ("write_term", "abc", [("quoted", True)])) == "[a,b,c]"

    def test_quoted_and_double_quotes_print_the_double_quoted_spelling(self, mod):
        opts = [("quoted", True), ("double_quotes", True)]
        assert _out(mod, ("write_term", "abc", opts)) == '"abc"'
        # …and the ISO comma spacing is kept even then: this is the writer's
        # SPELLING option, not a switch into the display family.
        assert _out(mod, ("write_term", ("f", ("a",), "bc"), opts)) == 'f(a,"bc")'

    def test_no_options_is_exactly_write_1(self, mod):
        assert _out(mod, ("write_term", [("a",), ("b",)], [])) == "[a,b]"
        assert _out(mod, ("write_term", ("a b",), [])) == "a b"
        assert _out(mod, ("write_term", [1, 2], [])) == "[1,2]"

    def test_quoted_quotes_an_atom(self, mod):
        assert _out(mod, ("write_term", ("a b",), [("quoted", True)])) == "'a b'"

    def test_ignore_ops_is_accepted(self, mod):
        assert _out(mod, ("write_term", ("f", 1), [("ignore_ops", True)])) == "f(1)"

    def test_an_unknown_option_is_a_domain_error(self, mod):
        from clausal.logic.atoms import mint
        from clausal.logic.exceptions import LogicException

        with pytest.raises(LogicException) as exc:
            list(solve(("write_term", ("a",), [("bogus", True)]), mod))
        formal = exc.value.term.args[0]
        assert formal.functor == "domain_error"
        assert formal.args[0] == mint("write_option")
        assert formal.args[1] == ("bogus", True)

    def test_a_non_list_option_argument_is_a_type_error(self, mod):
        from clausal.logic.atoms import mint
        from clausal.logic.exceptions import LogicException

        with pytest.raises(LogicException) as exc:
            list(solve(("write_term", ("a",), ("foo",)), mod))
        formal = exc.value.term.args[0]
        assert formal.functor == "type_error"
        assert formal.args[0] == mint("list")

    def test_an_unbound_option_list_is_an_instantiation_error(self, mod):
        from clausal.logic.atoms import mint
        from clausal.logic.exceptions import LogicException
        from clausal.logic.variables import Var

        with pytest.raises(LogicException) as exc:
            list(solve(("write_term", ("a",), Var()), mod))
        assert exc.value.term.args[0] == mint("instantiation_error")

    def test_a_partial_option_list_is_an_instantiation_error(self, mod):
        """Fix round 1, item 7: ``[quoted(true) | _]`` reaches the reader as
        a non-ground ``Seg*``.  ISO 8.14.2.3 b says instantiation_error, not
        ``type_error(list, …)``.

        A ``Seg*`` cannot be compiled into a goal's argument list, so these
        two go through ``call`` — the runtime entry the audit suite uses for
        ``Seg*`` rows."""
        from clausal.logic.atoms import mint
        from clausal.logic.exceptions import LogicException
        from clausal.logic.solve import call
        from clausal.logic.variables import Var
        from clausal.terms import ConcreteSeg, SegList, VarSeg

        partial = SegList([ConcreteSeg([("quoted", True)]), VarSeg(Var())])
        with pytest.raises(LogicException) as exc:
            list(call("write_term", ("a",), partial, module=mod))
        assert exc.value.term.args[0] == mint("instantiation_error")

    def test_a_ground_seg_option_list_is_read_normally(self, mod):
        """The other half of item 7: a GROUND ``Seg*`` walks to the plain
        list it is and its options take effect."""
        from clausal.logic.solve import call
        from clausal.terms import ConcreteSeg, SegList

        ground = SegList([ConcreteSeg([("quoted", True)])])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            assert len(list(call("write_term", ("a b",), ground,
                                 module=mod))) == 1
        assert buf.getvalue() == "'a b'"

    def test_the_atom_spellings_of_the_booleans_are_accepted(self, mod):
        """Source ``quoted(true)`` folds ``true`` to Python ``True`` (spec
        §8), but a term built by hand may carry the ATOM — both are read."""
        from clausal.logic.atoms import mint
        opts = [("quoted", mint("true")), ("double_quotes", mint("true"))]
        assert _out(mod, ("write_term", "abc", opts)) == '"abc"'
        assert _out(mod, ("write_term", ("a b",),
                          [("quoted", mint("false"))])) == "a b"


class TestTheThreeWriterFamilies:
    """Task 15 item 4 as AMENDED (operator, 2026-09-07).  Three families:

    * ISO — ``write/1``, ``writeq/1``, ``write_canonical/1``,
      ``write_term/2``: a string is the LIST of its characters.
      ``writeln/1`` and ``write_to_string/2`` are not ISO names but are
      ``write/1``'s semantics.
    * Clausal TEXT — ``write_text/1``, ``writeln_text/1``,
      ``write_text_to_string/2``: a string prints as its text.  This is
      where f-strings go.
    * Clausal DISPLAY — ``print_term/1``, ``term_to_string/2``: the
      ``[quoted(true), double_quotes(true)])`` SPELLING, plus the display
      comma spacing.

    Fix round 1, item 0 (operator): the ISO family prints NO whitespace
    after a comma, so its output is byte-comparable with Scryer; the
    display family keeps ``", "``.
    """

    def test_write_is_iso_and_prints_a_string_as_its_char_list(self, mod):
        assert _out(mod, ("write", "abc")) == "[a,b,c]"
        assert _out(mod, ("write", [("a",), ("b",)])) == "[a,b]"
        assert _out(mod, ("write", ("a b",))) == "a b"
        assert _out(mod, ("write", "")) == "[]"
        assert _out(mod, ("write", [1, 2])) == "[1,2]"

    def test_the_iso_family_has_no_space_after_a_comma(self, mod):
        """Scryer 0.10.0, byte for byte: ``write([1,2])`` → ``[1,2]``,
        ``write(f(a,b))`` → ``f(a,b)``, ``writeq(f(a,"b"))`` → ``f(a,[b])``.
        """
        from clausal.terms import Compound, DictTerm

        assert _out(mod, ("write", ("f", ("a",), ("b",)))) == "f(a,b)"
        assert _out(mod, ("writeq", ("f", ("a",), "b"))) == "f(a,[b])"
        assert _out(mod, ("write", Compound("f", (1, 2)))) == "f(1,2)"
        assert _out(mod, ("write", DictTerm({("k",): ("v",)}))) == "{k:v}"
        assert _out(mod, ("write_term", [1, 2], [])) == "[1,2]"

    def test_the_iso_family_routes_every_term_shape_through_term_str(self, mod):
        """Fix round 1, item 1: ``Compound``/``KWTerm``/``DictTerm`` used to
        fall to ``str()``, which routes back through ``term_str``'s DISPLAY
        defaults and so leaked double-quoted strings and Python reprs into an
        ISO writer's output."""
        from clausal.terms import Compound, DictTerm, KWTerm

        assert _out(mod, ("write", Compound("f", (1, "ab")))) == "f(1,[a,b])"
        assert _out(mod, ("write", KWTerm("p", a="ab"))) == "p(a=[a,b])"
        assert _out(mod, ("write", DictTerm({("k",): "ab"}))) == "{k:[a,b]}"

    def test_write_equals_the_option_free_write_term(self, mod):
        from clausal.terms import Compound, DictTerm, KWTerm

        for term in ("abc", [("a",), ("b",)], ("foo", ("bar",), "baz"),
                     ("a b",), [1, 2], "",
                     Compound("f", (1, "ab")), KWTerm("p", a="ab"),
                     DictTerm({("k",): "ab"}), b"ab", ()):
            assert (_out(mod, ("write", term))
                    == _out(mod, ("write_term", term, []))), term

    def test_write_equals_write_term_for_a_ground_seg(self, mod):
        """Fix round 2, item 1: ``write/1``/``writeln/1``/
        ``write_to_string/2`` formatted ``deref(term)``, and ``Seg*`` is not
        in ``_ISO_TERM_TYPES``, so a ground ``SegList``/``SegString`` fell to
        ``str()`` -- display spacing (``[1, 2]``) or a raw ``SegString([...])``
        repr -- and ``write/1`` stopped agreeing with
        ``write_term(T, [])``, which walks.  All three walk now.

        A ``Seg*`` cannot be compiled into a goal's argument list, so these
        go through ``call``."""
        from clausal.logic.solve import call
        from clausal.terms import ConcreteSeg, SegList, SegString

        def out_call(name, *args):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                assert len(list(call(name, *args, module=mod))) == 1
            return buf.getvalue()

        for term, want in ((SegList([ConcreteSeg([1, 2])]), "[1,2]"),
                           (SegString(["ab"]), "[a,b]"),
                           (SegList([ConcreteSeg([("a",), ("b",)])]), "[a,b]")):
            assert out_call("write", term) == want, term
            assert out_call("write_term", term, []) == want, term
            assert out_call("writeln", term) == want + "\n", term

    def test_the_text_family_walks_a_ground_seg_too(self, mod):
        """Fix round 3, item 5: ``write_text``/``writeln_text``/
        ``write_text_to_string`` used ``deref``, so a ground ``Seg*`` fell to
        ``str()`` and printed a raw ``SegString([...])`` repr -- the same
        hole the ISO trio had in round 2."""
        from clausal.logic.solve import call
        from clausal.logic.variables import Var, deref
        from clausal.terms import ConcreteSeg, SegList, SegString

        def out_call(name, *args):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                assert len(list(call(name, *args, module=mod))) == 1
            return buf.getvalue()

        assert out_call("write_text", SegString(["ab"])) == "ab"
        assert out_call("write_text",
                        SegList([ConcreteSeg([("a",), ("b",)])])) == "ab"
        assert out_call("write_text", SegList([ConcreteSeg([1, 2])])) == "[1, 2]"
        assert out_call("writeln_text", SegString(["ab"])) == "ab\n"
        S = Var()
        got = [deref(S) for _ in call("write_text_to_string",
                                      SegString(["ab"]), S, module=mod)]
        assert got == [chars("ab")]

    def test_the_nil_tuple_prints_as_the_empty_list_in_every_family(self, mod):
        """Fix round 2, item 5: ``()`` is the hashable spelling of nil, and
        both cell tests are FALSY on it, so it used to fall to ``str()`` and
        print ``()``.  ``b""`` had the same shape of hole in the text
        family."""
        for spelling in ((), "", [], b""):
            assert _out(mod, ("write", spelling)) == "[]", spelling
            assert _out(mod, ("writeq", spelling)) == "[]", spelling
            assert _out(mod, ("write_text", spelling)) == "[]", spelling
            assert _out(mod, ("write_term", spelling, [])) == "[]", spelling

    def test_writeq_is_iso_too_and_only_adds_quoting(self, mod):
        assert _out(mod, ("writeq", "abc")) == "[a,b,c]"
        assert _out(mod, ("writeq", ("a b",))) == "'a b'"
        opts = [("quoted", True)]
        for term in ("abc", [("a",), ("b",)], ("foo", ("bar",), "baz"),
                     ("a b",), [1, 2], "", b"ab"):
            assert (_out(mod, ("writeq", term))
                    == _out(mod, ("write_term", term, opts))), term

    def test_the_iso_family_prints_a_code_list_as_numbers(self, mod):
        """Fix round 1, item 5: ``b"ab"`` is the code list ``[97,98]`` and
        the ISO family spells it out; the TEXT family keeps ``b'ab'``."""
        assert _out(mod, ("write", b"ab")) == "[97,98]"
        assert _out(mod, ("writeq", b"ab")) == "[97,98]"
        assert _out(mod, ("write_term", b"ab", [])) == "[97,98]"
        assert _out(mod, ("write", b"")) == "[]"
        assert _out(mod, ("write_text", b"ab")) == "b'ab'"

    def test_the_text_family_prints_a_string_as_its_text(self, mod):
        assert _out(mod, ("write_text", chars("abc"))) == "abc"
        assert _out(mod, ("write_text", [("a",), ("b",)])) == "ab"
        assert _out(mod, ("write_text", ("a b",))) == "a b"
        assert _out(mod, ("write_text", chars(""))) == "[]"
        assert _out(mod, ("write_text", [1, 2])) == "[1, 2]"
        assert _out(mod, ("writeln_text", chars("abc"))) == "abc\n"

    def test_write_text_to_string_answers_the_text(self, mod):
        from clausal.logic.variables import Var, deref
        S = Var()
        got = [deref(S)
               for _ in solve(("write_text_to_string", chars("abc"), S), mod)]
        assert got == [chars("abc")]
        S2 = Var()
        got2 = [deref(S2)
                for _ in solve(("write_to_string", chars("abc"), S2), mod)]
        assert got2 == [chars("[a,b,c]")]

    def test_print_term_and_term_to_string_are_the_display_form(self, mod):
        from clausal.logic.variables import Var, deref

        assert _out(mod, ("print_term", chars("abc"))) == '"abc"\n'
        expected = {
            chars("abc"): '"abc"',
            chars(""): "[]",
            chars("a b"): '"a b"',
        }
        for term, want in expected.items():
            S = Var()
            got = [deref(S) for _ in solve(("term_to_string", term, S), mod)]
            assert got == [chars(want)], term
        # The display family keeps the ``", "`` the ISO family drops.
        S2 = Var()
        got2 = [deref(S2)
                for _ in solve(("term_to_string", ("f", ("a",), chars("bc")), S2), mod)]
        assert got2 == [chars('f(a, "bc")')]
        assert _out(mod, ("write_term", ("f", ("a",), chars("bc")),
                          [("quoted", True), ("double_quotes", True)])) \
            == 'f(a,"bc")'
