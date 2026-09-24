"""F1 row 35, the data half: the specializer's unfolder takes the predicate
AS DATA (``_SpecTarget``: a name, field names, and the cell they build), not
the ``PredicateMeta`` class.

Measured when this landed: all 136 specialized installs across the
specialization suites produced byte-identical clauses (variables renamed
canonically) before and after the change.
"""

from __future__ import annotations

import importlib
import re

import pytest

from clausal.logic.predicate import make_predicate
from clausal.logic.specialization import (
    _SpecTarget, _specialized_fields, _unfold, analyze_mi,
)
from clausal.logic.variables import Var


def test_the_target_builds_the_cell_the_class_builds():
    cls = make_predicate("spt_p", ["a", "b", "c"])
    target = _SpecTarget.of(cls)
    assert (target.name, target.fields) == ("spt_p", ("a", "b", "c"))
    assert target(a=1, b=2, c=3) == cls(a=1, b=2, c=3) == ("spt_p", 1, 2, 3)
    partial = target(b=2)
    assert partial[0] == "spt_p" and partial[2] == 2
    assert isinstance(partial[1], Var) and isinstance(partial[3], Var)
    with pytest.raises(TypeError):
        target(nope=1)


def _canon(clauses):
    names = {}
    return [re.sub(r"(?:Att)?Var\(_\w+\)",
                   lambda m: names.setdefault(m.group(0), f"V{len(names)}"),
                   repr(c.head) + " :- " + repr(c.body)) for c in clauses]


def _natnum_program():
    return [
        [["natnum", 0], []],
        [["natnum", ["s", "X"]], [["natnum", "X"]]],
    ]


@pytest.mark.parametrize("mi", ["solve", "solve_count", "solve_limit"])
def test_the_unfolder_runs_without_any_class(mi):
    """A target built from a name and fields alone -- the post-flip shape --
    unfolds to the same clauses as one built from a class."""
    mis = importlib.import_module("clausal.examples.metainterpreters")
    pattern = analyze_mi(getattr(mis, mi))
    fields = tuple(_specialized_fields(pattern))

    from_class = _unfold(pattern, _natnum_program(),
                         _SpecTarget.of(make_predicate("spt_spec", list(fields))))
    classless = _unfold(pattern, _natnum_program(),
                        _SpecTarget("spt_spec", fields))
    assert from_class, "nothing unfolded: nothing compared"
    assert _canon(classless) == _canon(from_class)
