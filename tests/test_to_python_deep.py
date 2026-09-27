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

@pytest.mark.compound_retirement_slice8
def test_an_atom_functor_compound_is_its_cell_converted():
    c = Compound("pair", (mint("a"), chars("text")))
    assert to_python(c) == ("pair", "a", "text")
    assert type(to_python(c)[2]) is str


@pytest.mark.compound_retirement_slice8
def test_a_compound_nested_in_a_list_converts_too():
    out = to_python([Compound("f", (chars("x"),))])
    assert out == [("f", "x")] and type(out[0][1]) is str


@pytest.mark.compound_retirement_slice8
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

@pytest.mark.compound_retirement_slice9
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
    d = DictTerm({mint("k"): [("f", chars("x"))]})
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


def test_every_registered_type_round_trips_and_every_functor_has_an_owner():
    """The ONE registry, both ways, for EVERY entry: each TO_TERM class has a
    sample here (a new registration without one FAILS this test, on purpose),
    its term's head is in FROM_TERM, and to_python rebuilds the sample -- same
    value AND same exact type.  Every FROM_TERM functor except the data tuple
    is produced by some TO_TERM entry, so no rebuild is orphaned."""
    from clausal.logic import python_terms as pt
    produced = set()
    for cls, to_fn in pt.TO_TERM.items():
        if cls is tuple:
            continue
        assert cls in _SAMPLES, f"{cls.__name__} is registered but has no sample here"
        sample = _SAMPLES[cls]
        term = to_fn(sample)
        assert type(term) is tuple and term[0] in pt.FROM_TERM, (cls, term)
        produced.add(term[0])
        back = to_python(term)
        assert back == sample and type(back) is cls, (cls, back)
    assert produced == set(pt.FROM_TERM) - {TUPLE_TAG}, (produced, set(pt.FROM_TERM))


_SAMPLES = {
    dt.datetime: dt.datetime(2023, 6, 1, 2, 3, 4, 5),
    dt.date: dt.date(2023, 6, 1),
    dt.time: dt.time(1, 2, 3, 4),
    dt.timedelta: dt.timedelta(1, 2, 3),
}


# ── ONE OWNER OF RECURSION (roborev 231, MEDIUM) ────────────────────────────

def test_a_nested_data_tuple_is_converted_exactly_once():
    """The inner data cell ('()', 'date', 2023, 6, 1) is the PYTHON TUPLE
    ('date', 2023, 6, 1).  Converting the outer cell used to hand that
    already-converted tuple to a recursive from_fn, which read it as a date
    TERM: the answer was (datetime.date(2023, 6, 1),)."""
    inner = (TUPLE_TAG, "date", 2023, 6, 1)
    assert to_python(inner) == ("date", 2023, 6, 1)
    out = to_python((TUPLE_TAG, inner))
    assert out == (("date", 2023, 6, 1),), out
    assert type(out[0]) is tuple and not isinstance(out[0], dt.date)
    # and the same through from_term, the other door out of the registry
    from clausal.logic.python_terms import from_term
    assert from_term((TUPLE_TAG, inner)) == (("date", 2023, 6, 1),)


def test_a_registered_from_fn_is_shallow():
    """The rule every from_fn must keep: components arrive converted."""
    from clausal.logic.python_terms import FROM_TERM
    # an element a RECURSIVE from_fn would turn into a date: shallow keeps it
    out = FROM_TERM[TUPLE_TAG]((TUPLE_TAG, ("date", 2023, 6, 1), 2))
    assert out == (("date", 2023, 6, 1), 2) and type(out[0]) is tuple


# ── the exact-type fast path (roborev 235c): dispatch ORDER ─────────────────

def test_a_plain_str_never_derefs_and_a_bound_var_to_an_atom_does():
    v = Var()
    trail = Trail()
    assert unify(v, mint("bar"), trail)
    assert to_python(v) == "bar" and type(to_python(v)) is str


def test_exact_scalars_cross_as_themselves_bool_stays_bool():
    for x in (True, 0, 1.5, None, b"ab", 2j):
        assert to_python(x) is x, x
    assert to_python(True) is True and type(to_python(False)) is bool


def test_a_scalar_subclass_is_not_on_the_fast_path_and_crosses_unchanged():
    import enum
    class E(enum.IntEnum):
        A = 1
    assert to_python(E.A) is E.A
    from clausal.logic.atoms import atom
    from clausal.lint_warnings import ClausalAtomClassDeprecationWarning
    with pytest.warns(ClausalAtomClassDeprecationWarning):   # deprecated (step (f)); still crosses untouched
        a = atom("x")
    assert to_python(a) is a           # a boundary tag crosses OUT untouched


def test_the_carrier_is_tested_before_the_generic_tuple_arm():
    # ('$chars', 'x') is a 2-tuple whose head is a str: it must be text, never
    # the cell ('$chars', 'x') with a registry lookup on '$chars'
    out = to_python(chars("x"))
    assert type(out) is str and out == "x"
    out = to_python([chars("x")])
    assert out == ["x"] and type(out[0]) is str



def test_a_dataclass_term_instance_is_rebuilt_with_converted_fields():
    """Dumb seam step (c): a dataclass term class converts through (it used
    to cross unchanged); a pythonic_ast Node -- code, not data -- does not."""
    import dataclasses
    from clausal.logic.predicate import is_term_instance
    @dataclasses.dataclass
    class P:
        x: object
        y: object = 1
    inst = P(chars("x"))
    assert is_term_instance(inst)
    out = to_python(inst)
    assert type(out) is P and out is not inst
    assert out.x == "x" and type(out.x) is str and out.y == 1
    from clausal.pythonic_ast.nodes import LoadName
    node = LoadName(name=chars("x"))
    assert to_python(node) is node, "a Node is code and crosses as itself"
