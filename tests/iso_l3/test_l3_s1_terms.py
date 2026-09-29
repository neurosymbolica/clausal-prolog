"""Slice 1, terms: every ISO term shape lowers to the runtime term itself.

A data term is built as data -- an atom is its str, a compound its
functor-first cell, ``"..."`` the chars carrier -- never through a name
lookup, so no seam surface meaning (``max`` looked up, ``^`` as xor) can reach
it.  Loaded through the REAL import path with ``CLAUSAL_PL_FRONTEND=native``.
"""
from __future__ import annotations

import pytest

from clausal.logic.cells import CHARS_TAG


def test_each_term_shape_answers_as_the_iso_term(native, ans):
    mod = native.load("s1_terms", "\n".join([
        "k(1.5).",
        "k(-3).",
        "k('Hello World').",
        "k(\"ab\").",
        "k(pt(1, f(a))).",
        "k([a, b]).",
        "k('[]').",
        "k([]).",
        "k('.'(a, [])).",
        "k({a, b}).",
        "k(a + b * c).",
        "k(-).",
        "k(f(-(1))).",
        "k(- 1).",
        "k(2 ^ 3).",
        "k(max(1, 2)).",
    ]) + "\n")
    assert ans(mod, "k") == [
        1.5, -3, "Hello World", (CHARS_TAG, "ab"), ("pt", 1, ("f", "a")),
        ["a", "b"], [], [], ["a"], ("{}", (",", "a", "b")),
        ("+", "a", ("*", "b", "c")), "-", ("f", ("-", 1)), ("-", 1),
        ("^", 2, 3), ("max", 1, 2)]


def test_a_string_is_its_char_list(native, ans):
    mod = native.load("s1_str", 's("ab").\n')
    assert ans(mod, "s", 1, ["a", "b"]) == [()]
    assert ans(mod, "s", 1, ["a", "c"]) == []


def test_a_fact_variable_is_fresh_per_call_and_shared_within_the_clause(
        native, ans):
    mod = native.load("s1_vars", "same(X, X).\nany(_, _).\n")
    assert ans(mod, "same", 2, 1, 1) == [()]
    assert ans(mod, "same", 2, 1, 2) == []
    assert ans(mod, "same", 2, 2, 2) == [()]     # not bound by the first call
    assert ans(mod, "any", 2, 1, 2) == [()]      # each `_` is its own variable


def test_a_partial_list_is_a_list_with_a_tail(native, ans):
    mod = native.load("s1_plist",
                      "pl([a, b | T], T).\npair([H|T], H, T).\n")
    assert ans(mod, "pl", 2, ["a", "b", "c"]) == [["c"]]
    assert ans(mod, "pair", 3, [1, 2, 3]) == [(1, [2, 3])]


def test_iso_variable_names_never_touch_the_module_namespace(native, ans):
    """``__name__``, ``True`` and ``Var`` are legal ISO variable names."""
    mod = native.load("s1_vnames", "v(__name__, True, Var, None, True).\n")
    assert mod.__name__ == "s1_vnames"
    assert ans(mod, "v", 5, "q", 1, 2, 3, 1) == [()]
    assert ans(mod, "v", 5, "q", 1, 2, 3, 4) == []


def test_a_quoted_non_identifier_predicate_name_loads(native, ans):
    mod = native.load("s1_qname", "'hello world'(1).\n'+'(a, b).\n")
    assert ans(mod, "hello world") == [1]
    assert ans(mod, "+", 2) == [("a", "b")]


def test_one_name_at_two_arities_is_two_procedures(native, ans):
    mod = native.load("s1_arities", "p(1).\np(1, 2).\n")
    assert ans(mod, "p") == [1]
    assert ans(mod, "p", 2) == [(1, 2)]


def test_head_fields_are_positional_arg_i():
    """P1 decision 1, unchanged: the native head fields are arg_0..arg_n-1."""
    import ast
    from clausal.tools import iso_l3 as L3
    mod, _ = L3.lower_items(L3.read_iso("p(X, Y).\n"))
    heads = [n for n in ast.walk(mod) if isinstance(n, ast.Call)
             and getattr(n.func, "id", None) == "$head"]
    assert [[k.arg for k in h.keywords] for h in heads] == [["arg_0", "arg_1"]]


def test_positions_are_pl_lines_and_columns():
    import ast
    from clausal.tools import iso_l3 as L3
    src = "a(1).\n\n  p(X,\n     X).\n"
    mod, _ = L3.lower_items(L3.read_iso(src), source=src)
    preds = [n for n in ast.walk(mod) if isinstance(n, ast.Call)
             and getattr(n.func, "id", None) == "$Predicate"]
    pos = [ast.literal_eval(next(k.value for k in p.keywords
                                 if k.arg == "position")) for p in preds]
    assert pos[0][:2] == (1, 0)
    assert pos[1][:2] == (3, 2) and pos[1][2] == 4


@pytest.mark.parametrize("src", ["f(é, \"ü\").\ng(X, X).\n"])
def test_positions_count_characters_not_bytes(src):
    import ast
    from clausal.tools import iso_l3 as L3
    mod, _ = L3.lower_items(L3.read_iso(src), source=src)
    preds = [n for n in ast.walk(mod) if isinstance(n, ast.Call)
             and getattr(n.func, "id", None) == "$Predicate"]
    second = ast.literal_eval(next(k.value for k in preds[1].keywords
                                   if k.arg == "position"))
    assert second[:2] == (2, 0)
