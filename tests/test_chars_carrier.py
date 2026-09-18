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
