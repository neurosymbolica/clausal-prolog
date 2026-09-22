"""W4a: the PredicateMeta INSTANCE path is retired (spec
docs/superpowers/specs/2026-09-22-w4a-instance-path-retirement-design.md).
A predicate class builds CELLS, and every door that built an instance is
a loud refusal, so an out-of-tree minter fails rather than drifting."""
import pytest

from clausal.logic.predicate import PredicateMeta, RetiredStateError, make_predicate
from clausal.logic.variables import Var


def test_clausal_head_is_a_raising_tombstone():
    Pt = make_predicate("Pt", ["x", "y"])
    with pytest.raises(RetiredStateError, match="_clausal_head"):
        Pt._clausal_head(x=1, y=2)


def test_make_predicate_refuses_the_instances_keyword():
    with pytest.raises(TypeError, match="instances"):
        make_predicate("Old", ["a"], instances=True)


def test_calling_a_class_always_builds_the_cell():
    Pt = make_predicate("Pt2", ["x", "y"])
    cell = Pt(x=1)
    assert cell[0] == "Pt2" and cell[1] == 1 and isinstance(cell[2], Var)
    assert type(cell) is tuple, "never an instance, whatever the class carries"


def test_no_fast_instance_constructor_is_attached():
    Pt = make_predicate("Pt3", ["x"])
    assert not hasattr(Pt, "_clausal_new")
