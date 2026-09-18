"""Stage 1 of the atoms-as-str flip (spec 2026-09-18, RULED Q2): under
``-double_quotes(chars)`` a string is the CARRIER ``('$chars', text)`` -- a
reserved-tag cell equal to the list of its char atoms everywhere -- so that a
bare Python str can stop meaning "text".  These pin the carrier's identity
with the list spelling across the operations that used to key on ``str``."""
from __future__ import annotations

import pathlib

import pytest

from clausal.logic.atoms import is_atom, mint
from clausal.logic.cells import CHARS_TAG, chars, chars_text, is_chars
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from clausal.testing import load_clausal_module

_HDR = "-double_quotes(chars)\n-private([yes, no, a, b])\n"


def _mod(tmp_path, body):
    p = tmp_path / "carrier.clausal"; p.write_text(_HDR + body)
    return load_clausal_module(p)


def _first(mod, name, *args):
    for _ in call(name, *args, module=mod):
        return [deref(x) for x in args]
    return None


def test_the_carrier_shape():
    c = chars("ab")
    assert c == (CHARS_TAG, "ab") and is_chars(c) and chars_text(c) == "ab"
    assert not is_chars(("ab",)) and not is_chars("ab") and not is_chars((CHARS_TAG, 1))
    assert not is_atom(c)


def test_a_chars_literal_compiles_to_the_carrier(tmp_path):
    mod = _mod(tmp_path, 'p(X) <- (X is "ab")\nq(X) <- (X is "")\n')
    (x,) = _first(mod, "p", Var()); assert x == chars("ab"), x
    (e,) = _first(mod, "q", Var()); assert e == chars(""), e


def test_a_single_quoted_literal_is_still_an_atom(tmp_path):
    mod = _mod(tmp_path, "p(X) <- (X is 'ab')\n")
    (x,) = _first(mod, "p", Var()); assert x == ("ab",) and is_atom(x)


class TestEqualToTheListSpelling:
    def test_msort_interleaves_carriers_and_char_lists(self, tmp_path):
        mod = _mod(tmp_path, 'p(L) <- msort(["b", [a], "a", [b]], L)\n')
        (l,) = _first(mod, "p", Var())
        keys = [x if isinstance(x, list) else chars_text(x) for x in l]
        assert [k if isinstance(k, str) else "".join(c[0] for c in k) for k in keys] == ["a", "a", "b", "b"], l

    def test_string_1_and_length_2(self, tmp_path):
        mod = _mod(tmp_path, 'p(R) <- if_(string("ab"), R is yes, R is no)\nq(N) <- length("abc", N)\n')
        (r,) = _first(mod, "p", Var()); assert r == ("yes",)
        (n,) = _first(mod, "q", Var()); assert n == 3

    def test_append_keeps_the_carrier_kind(self, tmp_path):
        mod = _mod(tmp_path, 'p(R) <- append("ab", "cd", R)\n')
        (r,) = _first(mod, "p", Var()); assert r == chars("abcd"), r

    def test_identity_eq_across_spellings(self, tmp_path):
        mod = _mod(tmp_path, "p(R) <- if_('=='(\"ab\", [a, b]), R is yes, R is no)\n")
        (r,) = _first(mod, "p", Var()); assert r == ("yes",), r

    def test_unify_across_spellings(self, tmp_path):
        """Needs the C list-unify to read the carrier (slice 2)."""
        mod = _mod(tmp_path, "p(R) <- if_('='(\"ab\", [a, b]), R is yes, R is no)\n")
        (r,) = _first(mod, "p", Var()); assert r == ("yes",), r


class TestSlice3Funnels:
    """Slice 3: ``=..`` cons tail, rendering, the io producers, CLP ``==``,
    and the Python-side crossings all read the carrier as its text."""

    def test_univ_conses_a_char_onto_a_carrier(self, tmp_path):
        mod = _mod(tmp_path, "p(T) <- unpack(T, ['.', a, \"bc\"])\nq(T) <- unpack(T, ['.', 1, \"bc\"])\n")
        (t,) = _first(mod, "p", Var()); assert t == chars("abc"), t
        (u,) = _first(mod, "q", Var()); assert u == [1, ("b",), ("c",)], u

    def test_writeq_and_write_never_show_the_tag(self):
        from clausal.terms import term_str, term_canonical
        assert term_str(chars("ab")) == '"ab"'
        assert term_str(chars("ab"), quoted=False, double_quotes=False) == "[a, b]"
        assert term_canonical(chars("ab")) == "'.'(a,'.'(b,[]))"
        assert "$chars" not in term_str(("f", chars("x")))

    def test_to_string_producers_answer_the_carrier(self, tmp_path):
        mod = _mod(tmp_path, 'p(S) <- write_to_string("hi", S)\nq(S) <- term_to_string([a, 1], S)\nr(S) <- write_text_to_string("hi", S)\n')
        (s,) = _first(mod, "p", Var()); assert s == chars("[h,i]"), s
        (t,) = _first(mod, "q", Var()); assert t == chars("[a, 1]"), t
        (u,) = _first(mod, "r", Var()); assert u == chars("hi"), u

    def test_infix_eq_between_a_bare_str_and_the_carrier(self):
        from clausal.logic.clpfd import fd_eq, fd_ne
        from clausal.logic.variables import Trail
        t = Trail()
        assert fd_eq("ab", chars("ab"), t) and fd_eq(chars("ab"), "ab", t)
        assert not fd_eq("ab", chars("ac"), t)
        assert fd_ne("ab", chars("ac"), t) and not fd_ne("ab", chars("ab"), t)

    def test_python_side_crossings_read_the_text(self):
        from clausal.logic.to_python import to_python
        from clausal.logic.seam import text_of, text_value
        assert to_python(chars("ab")) == "ab"
        assert to_python([chars("ab"), 1]) == ["ab", 1]
        assert text_of(chars("ab")) == "ab" and text_value(chars("ab")) == "ab"

    def test_a_chars_literal_in_a_head_is_a_string_literal(self, tmp_path):
        """A ``"..."`` head argument keeps the str literal's capture+unify
        guard: every spelling of the text matches, and the stored head keeps
        the literal (the test runner reads names off stored heads)."""
        mod = _mod(tmp_path, 'p("ab", R) <- (R is yes)\np("cd", R) <- (R is no)\n')
        from clausal.logic.atoms import char_atom
        assert _first(mod, "p", chars("ab"), Var())[1] == ("yes",)
        assert _first(mod, "p", "cd", Var())[1] == ("no",)
        assert _first(mod, "p", [char_atom("a"), char_atom("b")], Var())[1] == ("yes",)
        assert _first(mod, "p", chars("zz"), Var()) is None
        x = Var(); assert _first(mod, "p", x, Var())[0] == chars("ab")     # output mode binds the carrier
        heads = [c.head for c in mod.__dict__["$module"].db.clauses_for("p", 2)]
        from clausal.logic.predicate import term_field_names
        assert [getattr(h, term_field_names(h)[0]) for h in heads] == [chars("ab"), chars("cd")], heads

    def test_runner_reads_chars_test_names_and_runs_the_right_body(self, tmp_path):
        from clausal.testing import collect_tests, run_test
        p = tmp_path / "t.clausal"
        p.write_text(_HDR + 'test("first") <- (X is 1, X == 1)\ntest("second") <- (Y is 2, Y == 3)\n')
        mod = load_clausal_module(p)
        assert collect_tests(mod) == ["first", "second"]
        assert run_test(mod, "first").passed and not run_test(mod, "second").passed
