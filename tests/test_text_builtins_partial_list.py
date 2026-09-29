"""atom_chars/2, atom_codes/2, number_chars/2, number_codes/2 with a PARTIAL
list: ISO (8.16.4.3 and siblings) and Scryer raise instantiation_error; it
was type_error(list, [a|_])."""
import pytest

from clausal.logic.solve import _deref_walk, solve
from clausal.logic.variables import Var

SRC = """\
-allow_singletons
-private([a, b, f(_)])
t_atom_chars(R) <- catch((L is [a, *T], atom_chars(X, L), R is X), E, R is E)
t_atom_codes(R) <- catch((L is [a, *T], atom_codes(X, L), R is X), E, R is E)
t_number_chars(R) <- catch((L is [a, *T], number_chars(X, L), R is X), E, R is E)
t_number_codes(R) <- catch((L is [49, *T], number_codes(X, L), R is X), E, R is E)
t_non_list(R) <- catch((atom_chars(X, a), R is X), E, R is E)
"""


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    from clausal.import_hook import _load_module
    d = tmp_path_factory.mktemp("tbpl")
    p = d / "tbpl.clausal"
    p.write_text(SRC)
    return _load_module("tbpl_mod", str(p))


@pytest.mark.parametrize("name", ["atom_chars", "atom_codes", "number_chars",
                                  "number_codes"])
def test_partial_list_is_an_instantiation_error(mod, name):
    R = Var()
    [got] = [_deref_walk(R) for _ in solve((f"t_{name}", R), mod)]
    assert got == ("error", "instantiation_error", ("/", name, 2))


def test_a_non_list_is_still_a_type_error(mod):
    R = Var()
    [got] = [_deref_walk(R) for _ in solve(("t_non_list", R), mod)]
    assert got[1] == ("type_error", "list", "a")
