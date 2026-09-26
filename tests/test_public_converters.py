"""The public converter trio (dumb-seam step (b), 2026-09-26):

    clausal.to_python(term)   deep OUT   -- the Python value of a term
    clausal.to_clausal(obj)   deep IN    -- the term of a Python object
    clausal.term_key(term)    the standard-order sort key

Additive only: nothing an existing seam answers changes.  ``to_clausal`` is
``python_terms.to_term(strict=True)`` under its public name, driven by the
ONE registry ``to_python`` also consults; ``term_key`` is
``_standard_order_key`` made public, with the ground ``Seg*`` case keyed as
the term it walks to instead of the opaque band.
"""
import datetime as dt

import pytest

import clausal
from clausal.logic.cells import chars, TUPLE_TAG
from clausal.logic.variables import Var, Trail, unify
from clausal.terms import SegList, SegString, VarSeg, ConcreteSeg


# ── exported from the package ───────────────────────────────────────────────

def test_the_three_names_are_exported_from_clausal():
    from clausal.logic.to_python import to_python
    from clausal.logic.python_terms import to_clausal
    from clausal.logic.builtins._helpers import term_key
    assert clausal.to_python is to_python
    assert clausal.to_clausal is to_clausal
    assert clausal.term_key is term_key
    for name in ("to_python", "to_clausal", "term_key"):
        assert name in clausal.__all__, name


def test_the_names_do_not_shadow_a_builtin_predicate():
    # ``clausal.atom`` IS the builtin atom/1 -- the clash this codebase
    # tripped on.  None of the three is a predicate name.
    from clausal.logic.builtins import get_builtin_class
    for name in ("to_python", "to_clausal", "term_key"):
        assert get_builtin_class(name) is None, name
    assert get_builtin_class("atom") is not None     # the positive control


# ── to_clausal ──────────────────────────────────────────────────────────────

def test_to_clausal_is_the_strict_registry_conversion():
    from clausal.logic.python_terms import to_term
    d = dt.date(2023, 6, 1)
    assert clausal.to_clausal(d) == to_term(d, strict=True) == ("date", 2023, 6, 1)


def test_to_clausal_is_deep():
    got = clausal.to_clausal({"k": [dt.date(2023, 6, 1), (1, 2)]})
    assert got == {"k": [("date", 2023, 6, 1), (TUPLE_TAG, 1, 2)]}


def test_to_clausal_a_str_is_the_atom_and_text_is_written_chars():
    assert clausal.to_clausal("x") == "x"
    assert clausal.to_clausal(chars("x")) == chars("x")


def test_to_clausal_leaves_a_logic_variable_alone():
    v = Var()
    assert clausal.to_clausal(v) is v


def test_to_clausal_refuses_an_unregistered_class_loudly():
    class Opaque:
        pass
    with pytest.raises(TypeError, match="no registered conversion"):
        clausal.to_clausal(Opaque())


def test_to_clausal_the_documented_hazard_a_tuple_already_a_term():
    # ('date', 2023, 6, 1) is indistinguishable by shape from a data tuple;
    # the registry's rule is: a well-formed term the engine recognises is
    # left alone, anything else is data.
    assert clausal.to_clausal(("date", 2023, 6, 1)) == ("date", 2023, 6, 1)
    assert clausal.to_clausal(("date", "x", "y")) == (TUPLE_TAG, "date", "x", "y")


def test_to_python_inverts_to_clausal_on_registered_values():
    for v in (dt.date(2023, 6, 1), dt.datetime(2023, 6, 1, 2, 3),
              dt.timedelta(1, 2), (1, (2, 3)), [dt.date(2023, 6, 1)],
              {"k": (1, 2)}):
        assert clausal.to_python(clausal.to_clausal(v)) == v, v


# ── term_key ────────────────────────────────────────────────────────────────

def test_term_key_is_the_standard_order_key():
    from clausal.logic.builtins import _helpers
    assert clausal.term_key is _helpers.term_key
    assert _helpers._standard_order_key is _helpers.term_key   # in-tree alias kept


def test_term_key_orders_var_number_atom_compound():
    keys = [clausal.term_key(x) for x in (("f", 1), "a", 1, Var())]
    assert keys == sorted(keys, reverse=True)


def test_a_ground_segstring_keys_as_the_string_it_is():
    seg = SegString(["a", "b"])
    assert clausal.term_key(seg) == clausal.term_key(chars("ab"))
    assert clausal.term_key(seg) == clausal.term_key(["a", "b"])


def test_a_ground_seglist_keys_as_its_list():
    v = Var()
    trail = Trail()
    seg = SegList([ConcreteSeg([1]), VarSeg(v)])
    assert unify(v, [2, 3], trail)
    assert clausal.term_key(seg) == clausal.term_key([1, 2, 3])


def test_a_non_ground_seg_still_keys_in_the_opaque_band_and_sorts():
    from clausal.logic.builtins._helpers import _ORD_OTHER
    seg = SegString(["a", VarSeg(Var())])
    assert clausal.term_key(seg)[0] == _ORD_OTHER
    # total: sorting a mixed list never raises
    sorted([seg, "a", 1, ("f", 1)], key=clausal.term_key)


def test_sort_2_dedups_a_ground_segstring_against_its_string():
    """The engine-visible consequence: ``sort/2`` says the two are one term."""
    from clausal.logic.builtins._helpers import _standard_order_sorted
    out = _standard_order_sorted([chars("ab"), SegString(["ab"])])
    assert clausal.term_key(out[0]) == clausal.term_key(out[1])
