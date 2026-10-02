"""The clause-head ``match`` subject normaliser and the head patterns it feeds.

``terms.as_cells_for_match`` (C twin in ``variables/_variables.c``) hands a
compiled head ``match`` its argument dereferenced, with every slot in the top
*depth* cell levels that holds a Var BOUND to a structure replaced by that
structure -- a ``match`` does not dereference.  With *classes* it also walks
the fields of a dataclass term instance.  The two twins must agree.

Kept from the Compound-retirement tests (the class and its conversion are
gone; what remains of the normaliser is the bound-Var slot deref).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass as _dataclass
from typing import Any as _Any

import pytest

from clausal.logic.variables import Var, Trail, unify
from tests._suffix import SEAM


@_dataclass
class _Box:
    a: _Any


def _nest(d, leaf):
    t = leaf
    for _ in range(d):
        t = ("f", t)
    return t


def test_subject_normaliser_twins_agree():
    from clausal.logic.variables._variables import as_cells_for_match as c_twin
    from clausal.terms import as_cells_for_match as py_twin
    bound = Var()
    unify(bound, ("g", 1), Trail())
    bound_cell = Var()
    unify(bound_cell, ("f", 2), Trail())
    plain = ("k", ("f", 2), 9)
    cases = [
        (("f", 1), 1), (("k", ("f", 2)), 2), (("k", bound), 2), (plain, 3),
        (Var(), 2), (7, 3), (bound_cell, 1),
        # below a class pattern: an instance's fields
        (_Box(("g", 1)), 2), (("k", _Box(bound)), 3), (_Box(bound), 2),
        # a slot Var bound to a structure becomes the structure
        (("k", bound_cell), 2), (("k", bound_cell), 1), (("k", (bound_cell,)), 2),
        (("k", bound_cell, 3, "x", None, 2.5, b"b", True), 2),
    ]
    for term, depth in cases:
        for classes in (False, True):
            a, b = c_twin(term, depth, classes), py_twin(term, depth, classes)
            assert type(a) is type(b) and a == b, (term, depth, classes, a, b)
        a, b = c_twin(term, depth), py_twin(term, depth)
        assert type(a) is type(b) and a == b, (term, depth, a, b)
    # the bound slot is replaced by the structure, not left as the Var
    assert c_twin(("k", bound_cell), 2)[1] == ("f", 2)
    assert type(c_twin(("k", bound_cell), 2)[1]) is tuple
    # a top-level Var is dereferenced
    assert c_twin(bound_cell, 1) == ("f", 2)
    # no class pattern: an instance is never copied (roborev 205)
    box = _Box(bound)
    assert c_twin(box, 2) is box and py_twin(box, 2) is box
    assert c_twin(box, 2, True) is not box
    assert c_twin(box, 2, True).a == ("g", 1)
    # nothing copied when there is nothing to convert
    assert c_twin(plain, 3) is plain and py_twin(plain, 3) is plain
    # depth bounds the walk: a bound slot below it is left alone
    deep = ("k", ("k", bound_cell))
    assert c_twin(deep, 2) is deep and py_twin(deep, 2) is deep


def test_head_patterns_are_linear_in_depth():
    """roborev 203: a nested cell head compiles to a pattern whose size grows
    linearly with its depth."""
    from clausal.logic.compiler.head_match import head_to_match_pattern
    import ast as _ast
    sizes = []
    for d in (4, 8, 12):
        pat = head_to_match_pattern(_nest(d, 1), {}, [], [], None, globals_={})
        sizes.append(sum(1 for _ in _ast.walk(pat)))
    assert sizes[2] - sizes[1] == sizes[1] - sizes[0], sizes


# ── depth read off the BUILT pattern (roborev 204) ─────────────────────────


@pytest.fixture(scope="module")
def KW(tmp_path_factory):
    """A module declaring the data functors ``box/2`` and ``g/1``."""
    from clausal.import_hook import _load_module
    d = tmp_path_factory.mktemp("acfm_kw")
    p = d / f"acfm_kw{SEAM}"
    p.write_text("-module(acfm_kw, [])\n-private([box(Lo, Hi), g(A)])\n")
    sys.path.insert(0, str(d))
    try:
        mod = _load_module("acfm_kw", str(p))
    finally:
        sys.path.remove(str(d))
    return dict(mod.__dict__)


def _kw_box(lo, hi):
    from clausal.terms import Call, LoadName
    from clausal.pythonic_ast.nodes import Keyword
    return Call(func=LoadName(name="box"), args=[], kwargs=[
        Keyword(name="Lo", value=lo), Keyword(name="Hi", value=hi)])


def _g(x):
    from clausal.terms import Call, LoadName
    return Call(func=LoadName(name="g"), args=[x], kwargs=[])


def test_a_keyword_data_head_counts_its_keyword_slots(KW):
    """Keyword data terms are refused in source since 2026-09-19, so this
    head is built programmatically.  Its keyword slot holds a nested cell
    pattern: the depth must be 2."""
    from clausal.logic.compiler.head_match import (
        head_to_match_pattern, pattern_structure_depth)
    pat = head_to_match_pattern(_kw_box(_g(Var()), 2), {}, [], [], None,
                                globals_=KW)
    assert pattern_structure_depth(pat) == (2, False)
