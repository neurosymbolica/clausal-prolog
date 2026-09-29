"""callable/1 under its ISO name (8.3.9).  Only callable_/1 was registered,
so ``callable(f(X))`` in a clause body was existence_error(procedure,
callable/1).  Answers are Scryer's."""
import pytest

from clausal.logic.solve import solve

SRC = """\
-allow_singletons
-private([f(_)])
c_compound() <- callable(f(X))
c_list() <- callable([a])
c_number() <- callable(3)
c_atom() <- callable(foo)
c_var() <- callable(V)
-private([a, foo])
"""


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    from clausal.import_hook import _load_module
    d = tmp_path_factory.mktemp("cisoname")
    p = d / "cisoname.clausal"
    p.write_text(SRC)
    return _load_module("cisoname_mod", str(p))


@pytest.mark.parametrize("pred,answers", [
    ("c_compound", 1), ("c_list", 1), ("c_number", 0), ("c_atom", 1),
    ("c_var", 0),
])
def test_callable_1(mod, pred, answers):
    assert len(list(solve(pred, mod))) == answers
