"""D27 (B, explicit opt-in; ruled 2026-10-07): ``to_python_text(T)`` hands
every GROUND, NON-EMPTY list whose elements are all one-char atoms -- a char
list -- to Python as TEXT, a ``str``, whatever built it.  ``to_python``
itself is unchanged.

Why the conversion exists: the engine builds one char list in two shapes.  The
chars carrier ``('$chars', s)`` (a DCG output, an open tail bound later, a
recursion-built list, ``"ab"`` under ``-double_quotes(chars)``) crosses as
``'ab'``; the SAME term built as a plain list (``L = [a, b]``,
``atom_chars``, a closed ``append``, ``reverse``, ``maplist``, ``nth0``,
``length`` + unify) crosses as ``['a', 'b']``.  A user report found answers
of one term in two Python shapes, depending on which builtin made them.

Why ``to_python`` is unchanged: every ``py.*`` wrapper converts its arguments with
``to_python``, and there a list of one-char atoms is often a list of
symbols -- ``partition_spec([[x, y]], P)`` must reach JAX as
``(('x', 'y'),)``, not as the one axis ``'xy'``.

Under ``to_python_text``, and unchanged by it:

* ``[]`` is nil, not a char list: it crosses as the Python list ``[]`` at top
  level and nested, however it was built;
* a mixed list (``[a, bc]``, ``[a, 1]``, a list of one-char STRINGS) stays a
  list; a list with an unbound tail crosses raw;
* engine-internal semantics, the answer paths (``Var.value``, ``--``,
  ``query()``) and the ``++`` thunk path see the same terms as before.
"""
from __future__ import annotations

import pytest

from clausal.logic.atoms import mint
from clausal.logic.cells import chars
from clausal.logic.solve import solve
from clausal.logic.to_python import to_python as _to_python_default, to_python_text
from clausal.logic.variables import Var, Trail, unify
from clausal.terms import DictTerm, SegList, ConcreteSeg, VarSeg
from clausal.testing import load_clausal_module
from tests._suffix import SEAM


to_python = to_python_text            # the explicit conversion under test


def test_it_is_exported_beside_to_python():
    import clausal
    from clausal.modules.py import _helpers
    assert clausal.to_python_text is to_python_text
    assert "to_python_text" in clausal.__all__
    assert _helpers.to_python_text is to_python_text


# ── to_python_text on Python-built terms ─────────────────

def test_a_plain_char_list_is_text():
    out = to_python(["a", "b"])
    assert out == "ab" and type(out) is str


def test_a_one_element_char_list_is_text():
    assert to_python(["a"]) == "a"


def test_elements_bound_through_vars_count():
    x, y = Var(), Var()
    t = Trail()
    assert unify(x, mint("a"), t) and unify(y, mint("b"), t)
    assert to_python([x, y]) == "ab"


def test_a_var_bound_to_a_char_list_is_text():
    v = Var()
    assert unify(v, ["x", "y"], Trail())
    assert to_python(v) == "xy"


def test_a_ground_seglist_with_a_bound_tail_is_text():
    v = Var()
    assert unify(v, ["b"], Trail())
    out = to_python(SegList([ConcreteSeg(["a"]), VarSeg(v)]))
    assert out == "ab" and type(out) is str


def test_nil_stays_the_empty_list():
    out = to_python([])
    assert out == [] and type(out) is list


def test_an_empty_seglist_stays_the_empty_list():
    out = to_python(SegList([ConcreteSeg([])]))
    assert out == [] and type(out) is list


@pytest.mark.parametrize("lst", [
    ["a", "bc"],                 # a multi-char atom
    ["a", 1],                    # a number
    [chars("a"), chars("b")],    # one-char STRINGS, not atoms
    ["a", ("f", "b")],           # a compound
    ["a", ["b"]],                # a nested list
])
def test_a_mixed_list_stays_a_list(lst):
    out = to_python(lst)
    assert type(out) is list and len(out) == len(lst), out


def test_a_list_of_one_char_strings_is_a_list_of_texts():
    assert to_python([chars("a"), chars("b")]) == ["a", "b"]


def test_a_list_with_an_unbound_element_crosses_with_the_var():
    v = Var()
    out = to_python(["a", v])
    assert type(out) is list and out[0] == "a" and out[1] is v


def test_a_non_ground_open_char_list_crosses_raw():
    seg = SegList([ConcreteSeg(["a", "b"]), VarSeg(Var())])
    assert to_python(seg) is seg


def test_char_lists_nested_in_a_compound_become_text():
    out = to_python(("f", ["a", "b"], [], ["x", 1]))
    assert out == ("f", "ab", [], ["x", 1])


def test_nil_nested_in_a_compound_stays_the_empty_list():
    out = to_python(("r", "x", [], "y"))
    assert out == ("r", "x", [], "y") and type(out[2]) is list


def test_char_lists_nested_in_a_list_become_text():
    assert to_python([["a", "b"], ["x", "y"]]) == ["ab", "xy"]


def test_char_lists_as_dict_values_become_text():
    assert to_python(DictTerm({"k": ["x", "y"], "n": []})) == {"k": "xy", "n": []}
    assert to_python({"k": ["x", "y"]}) == {"k": "xy"}


def test_a_set_converts_too():
    # a list is unhashable, so no char list sits in a set; the pre-pass
    # still walks sets and leaves their elements' conversion to to_python
    from clausal.terms import SetTerm
    assert to_python(SetTerm({("f", chars("a")), "b"})) == frozenset({("f", "a"), "b"})


def test_a_registered_functor_rebuilds_from_converted_args():
    # the tuple data cell rebuilds a Python tuple; its char-list element is
    # text by the time the rebuild sees it, as a carrier element would be
    from clausal.logic.cells import TUPLE_TAG
    assert to_python((TUPLE_TAG, ["a", "b"], 1)) == ("ab", 1)
    assert to_python((TUPLE_TAG, chars("ab"), 1)) == ("ab", 1)


def test_a_dataclass_term_field_is_converted():
    import dataclasses
    @dataclasses.dataclass
    class P:
        x: object
    out = to_python(P(["a", "b"]))
    assert type(out) is P and out.x == "ab"


def test_single_char_atoms_that_read_as_symbols_are_chars_too():
    # every one-char atom is a char, including ones that read as symbols:
    # [x, y] as coordinates becomes 'xy' (the caveat for a caller who opts in)
    assert to_python(["x", "y"]) == "xy"
    assert to_python(["1", "+"]) == "1+"


# ── engine-built shapes: one Python shape whatever built the term ───────────

_SRC = """\
-double_quotes(chars)
-private([a, b, bc, ab, r(_, _, _), f(_)])

greet >> ("a", "b")
nothing >> []

rec_chars(0, []),
rec_chars(N, [a, *T]) <- (N > 0, eval_(N - 1, M), rec_chars(M, T))

lit_list(L) <- (L is [a, b])
by_atom_chars(L) <- atom_chars(ab, L)
append_closed(L) <- append([a], [b], L)
append_bound_tail(L) <- (append(L0, [b], L), L0 is [a])
by_reverse(L) <- reverse([b, a], L)
by_maplist(L) <- maplist(copy_term, [a, b], L)
by_nth0(L) <- (length(L, 2), nth0(0, L, a), nth0(1, L, b))
length_unify(L) <- (length(L, 2), L is [a, b])
by_dcg(L) <- phrase(greet, L)
open_tail(L) <- (L is [a, *T], T is [b])
by_recursion(L) <- rec_chars(2, L)
dq_literal(L) <- (L is "ab")

plain_nil(L) <- (L is [])
dcg_nil(L) <- phrase(nothing, L)
nested_nil(L) <- (L is r(a, [], b))
mixed_atoms(L) <- (L is [a, bc])
mixed_int(L) <- (L is [a, 1])
open_unbound(L) <- (L is [a, *_])
nested_cell(L) <- (L is f([a, b]))
nested_list(L) <- (L is [[a, b], [b, a]])
nested_dict(L) <- (L is {a: [a, b]})
"""


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    p = tmp_path_factory.mktemp("d27") / f"charlists{SEAM}"
    p.write_text(_SRC)
    return load_clausal_module(p)


def _answer(mod, name):
    L = Var()
    for _ in solve((name, L), mod):
        return to_python(L.value), to_python(L)   # the value, and the Var itself
    raise AssertionError(f"{name}/1 has no answer")


@pytest.mark.parametrize("name", [
    "lit_list", "by_atom_chars", "append_closed", "append_bound_tail",
    "by_reverse", "by_maplist", "by_nth0", "length_unify",
    # already text before D27 (the carrier); pinned so they stay so
    "by_dcg", "open_tail", "dq_literal",
])
def test_every_way_of_building_ab_crosses_as_the_same_text(mod, name):
    for out in _answer(mod, name):
        assert out == "ab" and type(out) is str, (name, out)


def test_a_recursion_built_char_list_crosses_as_text(mod):
    for out in _answer(mod, "by_recursion"):
        assert out == "aa" and type(out) is str, out


@pytest.mark.parametrize("name", ["plain_nil", "dcg_nil"])
def test_an_engine_built_nil_crosses_as_the_empty_list(mod, name):
    for out in _answer(mod, name):
        assert out == [] and type(out) is list, (name, out)


def test_an_engine_built_nested_nil_stays_the_empty_list(mod):
    for out in _answer(mod, "nested_nil"):
        assert out == ("r", "a", [], "b") and type(out[2]) is list, out


def test_engine_built_mixed_lists_stay_lists(mod):
    assert _answer(mod, "mixed_atoms")[0] == ["a", "bc"]
    assert _answer(mod, "mixed_int")[0] == ["a", 1]


def test_an_engine_built_open_char_list_crosses_raw(mod):
    out, _ = _answer(mod, "open_unbound")
    assert isinstance(out, SegList), out


def test_engine_built_nested_char_lists_become_text(mod):
    assert _answer(mod, "nested_cell")[0] == ("f", "ab")
    assert _answer(mod, "nested_list")[0] == ["ab", "ba"]
    assert _answer(mod, "nested_dict")[0] == {"a": "ab"}


# ── the thunk path (unwrap_atom) is deliberately NOT changed ────────────────

def test_unwrap_atom_hands_a_char_list_over_by_identity():
    """D27 = B is the to_python boundary.  The ``++``/f-string path keeps its
    container contract: a plain char list crosses as itself, so ``Y is ++(L)``
    still hands the list back and ``L = Y`` still holds."""
    from clausal.logic.to_python import unwrap_atom
    lst = ["a", "b"]
    assert unwrap_atom(lst) is lst
    assert unwrap_atom(chars("ab")) == "ab"


# ── to_python ITSELF IS UNCHANGED (D27 is an explicit conversion) ────────────────────────────────

@pytest.mark.parametrize("val, expected", [
    (["a", "b"], ["a", "b"]),
    ([["x", "y"]], [["x", "y"]]),              # a JAX multi-axis PartitionSpec entry
    (("f", ["a", "b"]), ("f", ["a", "b"])),
    ({"k": ["x", "y"]}, {"k": ["x", "y"]}),
    ([], []),
    (("r", "x", [], "y"), ("r", "x", [], "y")),
    (chars("ab"), "ab"),                        # the carrier was text already
])
def test_the_default_keeps_a_plain_char_list_a_list(val, expected):
    out = _to_python_default(val)
    assert out == expected and type(out) is type(expected), out


def test_the_default_keeps_engine_built_shapes_as_built(mod):
    for name, expected in [("lit_list", ["a", "b"]), ("by_atom_chars", ["a", "b"]),
                           ("by_dcg", "ab"), ("plain_nil", []), ("dcg_nil", []),
                           ("nested_nil", ("r", "a", [], "b"))]:
        L = Var()
        for _ in solve((name, L), mod):
            out = _to_python_default(L)
            assert out == expected and type(out) is type(expected), (name, out)
            break
