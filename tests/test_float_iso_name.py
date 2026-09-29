"""float/1 under its ISO name (8.3.5): a clause body's float(X) already
worked, but a query or call/N of float/1 did not -- existence_error
(procedure, float/1).  Now the same function as float_/1."""
from clausal.logic.database import Module
from clausal.logic.solve import solve


def test_float_1_from_a_query_and_call_n():
    m = Module("float_iso")
    assert len(list(solve(("float", 1.5), m))) == 1
    assert len(list(solve(("float", 1), m))) == 0
    assert len(list(solve(("call", "float", 1.5), m))) == 1
