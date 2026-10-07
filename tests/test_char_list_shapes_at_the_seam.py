"""One char list, two Python shapes -- only at the seam.

The engine builds one char list in two shapes: the chars carrier
``('$chars', s)`` (a DCG output, an open tail bound later, ``"ab"`` under
``-double_quotes(chars)``) and a plain list (``L is [a, b]``, ``atom_chars``,
``append``, ``reverse``...).  Inside the engine they are ONE term: they unify
and are ``==``.  They come apart only when they cross to Python:
``to_python`` hands the carrier over as ``'ab'`` and the plain list as
``['a', 'b']``.  Which shape a given builtin produces is not guaranteed: the
engine may build more char lists as the carrier (as Scryer compacts lists of
chars into partial strings during unification), so a caller must not rely on
it.

There is deliberately no conversion that turns every list of one-char atoms
into text (``to_python_text`` was withdrawn 2026-10-08): a one-char atom used
as a symbol is a char too, so ``[x, y]`` as coordinates would become ``'xy'``.
A predicate whose answer is text returns an ATOM (``atom_chars(A, L)``), and an
atom crosses as a ``str`` whatever built it.
"""
from __future__ import annotations

import pytest

import clausal
from clausal.logic.cells import chars
from clausal.logic.solve import solve
from clausal.logic.to_python import to_python, unwrap_atom
from clausal.logic.variables import Var
from clausal.testing import load_clausal_module
from tests._suffix import SEAM


_SRC = """\
-double_quotes(chars)
-private([a, b, ab, yes])

greet >> ("a", "b")

unify_shapes(yes) <- (phrase(greet, L1), atom_chars(ab, L2), L1 is L2)
identical_shapes(yes) <- (phrase(greet, L1), atom_chars(ab, L2), L1 == L2)

as_atom(A) <- (atom_chars(ab, L), atom_chars(A, L))
dcg_as_atom(A) <- (phrase(greet, L), atom_chars(A, L))
"""


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    p = tmp_path_factory.mktemp("charshapes") / f"charshapes{SEAM}"
    p.write_text(_SRC)
    return load_clausal_module(p)


def _first(mod, name):
    v = Var()
    for _ in solve((name, v), mod):
        return to_python(v)
    raise AssertionError(f"{name}/1 has no answer")


# ── inside the engine: one term ─────────────────────────────────────────────

@pytest.mark.parametrize("name", ["unify_shapes", "identical_shapes"])
def test_the_two_shapes_are_one_term_inside_the_engine(mod, name):
    assert _first(mod, name) == "yes"


# ── at the seam: to_python's rule on a plain list ───────────────────────────
# Which shape a given builtin builds is NOT pinned: the engine may build more
# char lists as the carrier later.  What is pinned is to_python's rule for a
# plain list of one-char atoms (a list of symbols stays a list) and for the
# carrier (text).

@pytest.mark.parametrize("val, expected", [
    (["a", "b"], ["a", "b"]),
    ([["x", "y"]], [["x", "y"]]),              # two symbols, e.g. two axis names
    (("f", ["a", "b"]), ("f", ["a", "b"])),
    ({"k": ["x", "y"]}, {"k": ["x", "y"]}),
    ([], []),
    (chars("ab"), "ab"),                        # the carrier is text
])
def test_to_python_keeps_a_plain_list_of_one_char_atoms_a_list(val, expected):
    out = to_python(val)
    assert out == expected and type(out) is type(expected), out


def test_the_thunk_path_hands_a_char_list_over_by_identity():
    lst = ["a", "b"]
    assert unwrap_atom(lst) is lst
    assert unwrap_atom(chars("ab")) == "ab"


# ── text is an atom: one Python shape whatever built it ─────────────────────

@pytest.mark.parametrize("name", ["as_atom", "dcg_as_atom"])
def test_an_answer_meant_as_text_crosses_as_str_when_it_is_an_atom(mod, name):
    out = _first(mod, name)
    assert out == "ab" and type(out) is str, (name, out)


def test_there_is_no_blanket_char_list_to_text_conversion():
    assert not hasattr(clausal, "to_python_text")
    assert "to_python_text" not in clausal.__all__
