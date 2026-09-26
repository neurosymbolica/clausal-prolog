"""``to_python`` is the public DEEP outbound converter (dumb-seam step (a),
2026-09-26): every engine term shape converts all the way down, and a
functor registered in ``python_terms`` (the ONE registry) rebuilds its
Python object.

Before this it had arms for atom, chars, SegString, list, tuple and dict
only; a ``Compound``, ``KWTerm``, ``SetTerm`` or ``SegList`` crossed RAW
with untouched insides, and a dict key was converted but never normalised.
"""
import datetime as dt
from typing import NamedTuple

import pytest

from clausal.logic.atoms import mint, NIL_KEY
from clausal.logic.cells import chars, TUPLE_TAG
from clausal.logic.to_python import to_python
from clausal.logic.variables import Var, Trail, unify
from clausal.terms import Compound, KWTerm, SetTerm, DictTerm, SegList, SegString, VarSeg, ConcreteSeg


# ── the hot-path contract is untouched ──────────────────────────────────────

def test_a_plain_str_is_the_same_object():
    s = "permitted"
    assert to_python(s) is s


def test_a_namedtuple_survives():
    class P(NamedTuple):
        x: int
        y: object
    out = to_python(P(1, chars("t")))
    assert type(out) is P and out.y == "t" and type(out.y) is str


# ── Compound ────────────────────────────────────────────────────────────────

def test_an_atom_functor_compound_is_its_cell_converted():
    c = Compound("pair", (mint("a"), chars("text")))
    assert to_python(c) == ("pair", "a", "text")
    assert type(to_python(c)[2]) is str


def test_a_compound_nested_in_a_list_converts_too():
    out = to_python([Compound("f", (chars("x"),))])
    assert out == [("f", "x")] and type(out[0][1]) is str


def test_a_compound_with_no_cell_keeps_its_shape_with_converted_args():
    # arity 0 is not an ISO term and has no cell (the 1-tuple is reserved)
    c0 = Compound("foo", ())
    out = to_python(c0)
    assert isinstance(out, Compound) and out.functor == "foo" and out.args == ()
    # a Var functor has no cell either; its args still convert
    v = Var()
    cv = Compound(v, (chars("x"),))
    out = to_python(cv)
    assert isinstance(out, Compound) and out.functor is v
    assert out.args == ("x",) and type(out.args[0]) is str


# ── KWTerm ──────────────────────────────────────────────────────────────────

def test_a_kwterm_keeps_its_shape_with_converted_fields():
    k = KWTerm("r", a=chars("t"), b=[mint("x"), chars("y")])
    out = to_python(k)
    assert isinstance(out, KWTerm) and out.functor == "r"
    assert out.a == "t" and type(out.a) is str
    assert out.b == ["x", "y"] and type(out.b[1]) is str


# ── SetTerm / set ───────────────────────────────────────────────────────────

def test_a_setterm_is_a_frozenset_of_converted_elements():
    s = SetTerm({mint("a"), chars("b"), ("f", chars("c"))})
    out = to_python(s)
    assert type(out) is frozenset
    assert out == {"a", "b", ("f", "c")}
    assert all(type(e) is str for e in out if not isinstance(e, tuple))


def test_a_python_set_converts_elementwise_and_keeps_its_type():
    assert to_python({chars("b")}) == {"b"}
    assert type(to_python(frozenset({chars("b")}))) is frozenset


# ── SegList ─────────────────────────────────────────────────────────────────

def test_a_ground_seglist_walks_to_its_list_converted():
    v = Var()
    trail = Trail()
    seg = SegList([ConcreteSeg([mint("a"), chars("t")]), VarSeg(v)])
    assert unify(v, [1, chars("u")], trail)
    out = to_python(seg)
    assert out == ["a", "t", 1, "u"] and type(out[3]) is str


def test_a_ground_seglist_of_chars_is_text():
    seg = SegList([ConcreteSeg(["a", "b"])])
    out = to_python(seg)
    assert type(out) is str and out == "ab"


def test_a_non_ground_seglist_crosses_raw_like_a_non_ground_segstring():
    seg = SegList([ConcreteSeg([1]), VarSeg(Var())])
    assert to_python(seg) is seg
    sseg = SegString(["hel", VarSeg(Var())])
    assert to_python(sseg) is sseg


# ── DictTerm keys ───────────────────────────────────────────────────────────

def test_dict_keys_are_normalised():
    # nil in every spelling is the one key ()
    d = DictTerm({(): 1})
    assert to_python(d) == {NIL_KEY: 1}
    # an atom key and its text are ONE Python key (the advisory-equality
    # consequence the 2026-09-21 spec calls wanted) -- documented, not hidden:
    d2 = DictTerm({mint("k"): 1, chars("k"): 2})
    out = to_python(d2)
    assert set(out) == {"k"} and len(out) == 1


def test_dict_values_convert_at_depth():
    d = DictTerm({mint("k"): [Compound("f", (chars("x"),))]})
    assert to_python(d) == {"k": [("f", "x")]}


# ── the ONE registry: a registered functor rebuilds its Python object ───────

def test_a_registered_date_cell_rebuilds_its_object():
    assert to_python(("date", 2023, 6, 1)) == dt.date(2023, 6, 1)
    assert to_python([("datetime", 2023, 6, 1, 1, 2, 3, 4)]) == [
        dt.datetime(2023, 6, 1, 1, 2, 3, 4)]


def test_a_look_alike_stays_a_cell_converted_elementwise():
    out = to_python(("date", chars("x"), "y"))
    assert out == ("date", "x", "y") and type(out[1]) is str


def test_the_tuple_data_cell_rebuilds_a_python_tuple():
    out = to_python((TUPLE_TAG, 1, chars("t"), ("f", mint("a"))))
    assert out == (1, "t", ("f", "a")) and type(out[1]) is str


def test_an_unregistered_cell_is_a_tuple_converted_elementwise():
    assert to_python(("cite", mint("art52"), chars("s"))) == ("cite", "art52", "s")


def test_to_python_and_the_registry_agree_on_every_registered_functor():
    """No second table: every ``FROM_TERM`` entry is what ``to_python``
    consults, so registering a type once serves both converters."""
    from clausal.logic import python_terms as pt
    for functor, rebuild in pt.FROM_TERM.items():
        if functor == TUPLE_TAG:
            continue
        # build a value through TO_TERM, cross it back through to_python
        cls = next(c for c, fn in pt.TO_TERM.items()
                   if fn is not None and pt.FROM_TERM.get(functor) is rebuild
                   and c is not tuple and fn(_sample(c))[0] == functor)
        sample = _sample(cls)
        assert to_python(pt.to_term(sample)) == sample, functor


def _sample(cls):
    return {
        dt.datetime: dt.datetime(2023, 6, 1, 2, 3, 4, 5),
        dt.date: dt.date(2023, 6, 1),
        dt.time: dt.time(1, 2, 3, 4),
        dt.timedelta: dt.timedelta(1, 2, 3),
    }[cls]
