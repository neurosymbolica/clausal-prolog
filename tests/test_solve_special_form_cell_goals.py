"""solve() of a special-form CELL with cell goal arguments.

``solve(("catch", ("throw", foo), E, True), m)`` raised
``NotImplementedError: terms_to_goalop: goal shape not yet supported
(tuple)``: the compiler lowers a special form's goal arguments as goal
NODES.  Such a query now runs as call/1 of the term.
"""
from clausal.logic.database import Module
from clausal.logic.solve import _deref_walk, solve
from clausal.logic.variables import Var


def test_special_forms_with_cell_goals():
    m = Module("sf_cells")
    E = Var()
    assert [_deref_walk(E) for _ in solve(("catch", ("throw", "foo"), E, True), m)] \
        == ["foo"]
    X, L = Var(), Var()
    assert [_deref_walk(L) for _ in solve(("findall", X, ("member", X, [1, 2]), L), m)] \
        == [[1, 2]]
    X = Var()
    assert len(list(solve(("forall", ("member", X, [1, 2]), ("integer", X)), m))) == 1
    X = Var()
    assert [_deref_walk(X) for _ in solve(("once", ("member", X, [1, 2])), m)] == [1]


def test_throw_of_an_unbound_ball_is_caught_as_the_iso_error():
    m = Module("sf_cells2")
    E = Var()
    got = [_deref_walk(E) for _ in solve(("catch", ("throw", Var()), E, True), m)]
    assert len(got) == 1 and got[0][1] == "instantiation_error"
