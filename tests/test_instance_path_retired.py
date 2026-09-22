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


def test_is_term_instance_is_dataclass_only():
    import dataclasses
    from clausal.logic.predicate import is_term_instance, term_field_names
    @dataclasses.dataclass
    class D:
        a: int
    assert is_term_instance(D(1)) is True and term_field_names(D(1)) == ("a",)
    Pt = make_predicate("Pt4", ["x"])
    assert is_term_instance(Pt(x=1)) is False, "a cell is not an instance"
    assert is_term_instance(Pt) is False, "nor is the class"


def test_the_python_twins_no_longer_carry_a_predicatemeta_instance_arm():
    import inspect
    from clausal.logic import predicate as P
    src = inspect.getsource(P._is_term_instance_py) + inspect.getsource(P._term_field_names_py)
    assert "PredicateMeta" not in src, "the instance arm is gone; only the dataclass arm remains"


# ── what SURVIVES the retirement ────────────────────────────────────────────
#
# The three assertions below came from ``tests/test_fast_construction.py``,
# deleted with ``_clausal_new`` (W4a).  Their subject was the FAST path, but
# each also pinned the slow, kwargs-based path a ``@dataclass`` term still
# takes -- the one rebuild route W4a deliberately leaves in place -- so they
# are carried here rather than dropped, minus the now-vacuous "no class has
# a fast constructor" half, which its own test above pins once for all.


def test_a_dataclass_node_still_walks_through_the_kwargs_path():
    from clausal.logic.solve import _deref_walk_py
    from clausal.pythonic_ast.nodes import BinOp

    node = BinOp(left=1, right=2)
    result = _deref_walk_py(node)
    assert result == node and result is not node


def test_a_dataclass_node_still_copies_through_the_kwargs_path():
    from clausal.logic.builtins.inspection import _copy_term_py
    from clausal.pythonic_ast.nodes import BinOp

    node = BinOp(left=1, right=2)
    result = _copy_term_py(node, {})
    assert result == node and result is not node


def test_a_dataclass_node_is_emitted_as_a_keyword_call():
    import ast

    from clausal.logic.compiler.terms_to_ast import term_to_ast_expr
    from clausal.pythonic_ast.nodes import BinOp

    expr = term_to_ast_expr(BinOp(left=1, right=2), {})
    assert isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name)
    assert expr.func.id == "$BinOp"
    assert expr.keywords != []


# ── the C twins ─────────────────────────────────────────────────────────────


def _c_module():
    from clausal.logic.variables import _variables as C
    return C


def test_c_and_python_twins_agree_and_neither_knows_an_instance():
    """A positive control that OBSERVES the C arm's removal.

    The retirement closed every door that BUILDS an instance, so no ordinary
    term can tell the two twins apart -- which would make a corpus-parity
    probe here pass on the old ``.so`` as happily as on the new one.  So the
    probe smuggles one past the constructors (``cls.__new__(cls)`` touches
    neither ``__call__`` nor ``_clausal_head``) and asks the C entry point
    directly: with the arm present it answers True while the Python twin
    answers False, and that disagreement is exactly what the rebuilt ``.so``
    removes.  A ``@dataclass`` instance must still be a term instance on both
    sides -- the arm that stays.
    """
    import dataclasses

    C = _c_module()
    from clausal.logic import predicate as P

    @dataclasses.dataclass
    class D:
        a: int

    Pt = make_predicate("Pt5", ["x"])
    smuggled = Pt.__new__(Pt)          # no constructor was called
    for obj in (D(1), Pt, Pt(x=1), "atom", ("f", 1), smuggled):
        assert bool(C.is_term_instance(obj)) == P._is_term_instance_py(obj), obj
    assert C.is_term_instance(smuggled) is False, (
        "the C PredicateMeta-instance arm is still live in the loaded .so"
    )
    assert bool(C.is_term_instance(D(1))) is True, "the dataclass arm stays"


def test_the_c_source_no_longer_carries_the_instance_arm():
    import pathlib

    from clausal.logic import predicate as P

    src = (pathlib.Path(P.__file__).parent / "variables" / "_variables.c").read_text()
    assert "Fast path: PredicateMeta instance" not in src
    # ... and the registration and the CLASS arms are NOT what W4a takes:
    # arms 4-7 and py_register_predicate_meta belong to W4b.
    assert "py_register_predicate_meta" in src
    assert "PyType_Check(term) && PredicateMeta_type" in src
