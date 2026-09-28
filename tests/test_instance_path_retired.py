"""W4a: the PredicateMeta INSTANCE path is retired (spec
docs/superpowers/specs/2026-09-22-w4a-instance-path-retirement-design.md).
A predicate class builds CELLS, and every door that built an instance is
a loud refusal, so an out-of-tree minter fails rather than drifting."""
import pytest

from clausal.logic.predicate import RetiredStateError
from clausal.logic.variables import Var


def test_make_predicate_is_removed():
    """W4b-3 slice 6 made ``make_predicate`` a stub that refused every call;
    it was removed before 1.0, with ``MakePredicateRetiredError``."""
    with pytest.raises(ImportError):
        from clausal.logic.predicate import make_predicate  # noqa: F401
    with pytest.raises(ImportError):
        from clausal.logic.predicate import MakePredicateRetiredError  # noqa: F401


def test_the_python_twins_no_longer_carry_a_predicatemeta_instance_arm():
    """The CODE of each twin, docstrings excluded -- prose may name the
    metaclass (it has to, to say what went), an executable line may not."""
    import ast
    import inspect
    import textwrap

    from clausal.logic import predicate as P

    for fn in (P._is_term_instance_py, P._term_field_names_py):
        body = ast.parse(textwrap.dedent(inspect.getsource(fn))).body[0].body
        if (isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            body = body[1:]                       # drop the docstring
        assert body, f"{fn.__name__} has no body left to check"
        code = "\n".join(ast.unparse(node) for node in body)
        assert "PredicateMeta" not in code, (
            f"{fn.__name__} still carries the instance arm:\n{code}")


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


def test_the_c_source_no_longer_carries_the_instance_arm():
    import pathlib

    from clausal.logic import predicate as P

    src = (pathlib.Path(P.__file__).parent / "variables" / "_variables.c").read_text()
    assert "Fast path: PredicateMeta instance" not in src
    # ... and W4b-3 slice 8 took the rest: the registration entry point, the
    # slot it filled and the CLASS arms that tested the slot.
    assert "py_register_predicate_meta" not in src
    assert "PredicateMeta_type" not in src
    # positive control: the file read is the extension source
    assert "PyInit__variables" in src and "init_term_inspection_cache" in src


def test_a_dataclass_head_is_not_liftable_and_the_clause_comes_back_unchanged():
    """The lift's gate and its rebuild admit the same head shapes.

    Review finding (2026-09-22): the gate used to admit anything
    ``is_term_instance`` accepted, while the rebuild below it called
    ``_clausal_head`` -- which a ``@dataclass`` term has not got.  A
    non-Compound dataclass head therefore passed the gate and died in the
    rebuild.  W4a's deletion made that a ``TypeError`` instead of an
    ``AttributeError``, which is no better, so the gate lost the arm: a head
    is a Compound or a cell, and anything else is simply not liftable.
    """
    from clausal.logic.compiler.list_dispatch import _lift_clause_at_pos
    from clausal.logic.database import Clause
    from clausal.pythonic_ast.nodes import BinOp
    from clausal.terms import Unify

    v = Var()
    clause = Clause(head=BinOp(left=v, right=2),
                    body=[Unify(left=v, right=[1, 2, 3])])
    assert _lift_clause_at_pos(clause, 0) is clause
