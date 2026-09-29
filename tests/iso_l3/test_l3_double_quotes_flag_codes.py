"""current_prolog_flag(double_quotes, M) under ``codes``.

The native front end lowers a ``codes`` literal itself (the seam has no
codes mode), so the engine's mode stayed chars/atom and the flag reported
that last chars/atom mode while ``codes`` was in force.  Scryer reports
``codes`` (the flag value at the end of the file, as here)."""
from __future__ import annotations

import pytest


@pytest.mark.parametrize("before,want", [
    ("", "codes"),
    (":- set_prolog_flag(double_quotes, atom).\n", "codes"),
    (":- set_prolog_flag(double_quotes, chars).\n", "codes"),
])
def test_codes_is_reported(native, ans, before, want):
    mod = native.load(f"l3_dq_codes_{len(before)}",
                      before + ":- set_prolog_flag(double_quotes, codes).\n"
                      "f(M) :- current_prolog_flag(double_quotes, M).\n"
                      "g(X) :- X = \"ab\".\n")
    assert ans(mod, "f") == [want]
    assert ans(mod, "g") == [[97, 98]]


def test_atom_after_codes_is_reported(native, ans):
    mod = native.load("l3_dq_codes_then_atom",
                      ":- set_prolog_flag(double_quotes, codes).\n"
                      ":- set_prolog_flag(double_quotes, atom).\n"
                      "f(M) :- current_prolog_flag(double_quotes, M).\n")
    assert ans(mod, "f") == ["atom"]
