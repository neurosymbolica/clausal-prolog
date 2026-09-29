"""A ground units mismatch is caught as error(system_error(units_mismatch), _).

todo/done/ground-arithmetic-units-mismatch-iso-term-2026-09-12.md (ruling
2026-09-12).  The CLP side channel already threw the ISO term for a
comparison; the ground path (``Quantity`` arithmetic reached through
``eval_/2``, ``sum_list/2``, ``max_list/2``, a ``++`` escape) reached
``catch/3`` as the transliterated ``UnitsMismatch(Message)`` cell, which no
``.clausal`` catcher can be written against (TitleCase).  The Python class
stays the internal signal: an uncaught mismatch still raises
``UnitsMismatch``, and a ``++UnitsMismatch(M)`` catcher still matches.
"""
import pytest

from clausal.logic.solve import _deref_walk, solve
from clausal.logic.variables import Var
from clausal.terms import UnitsMismatch

_SRC = """\
-import_from(py.units, [metre, second, UnitsMismatch])
-private([caught, units_mismatch])
cmp(R) <- catch((_X == 5(metre) + 3(second)), error(system_error(units_mismatch), _), R is caught)
ev(R) <- catch(eval_(5(metre) + 3(second), _), error(system_error(units_mismatch), _), R is caught)
sl(R) <- catch(sum_list([5(metre), 3(second)], _), error(system_error(units_mismatch), _), R is caught)
ml(R) <- catch(max_list([5(metre), 3(second)], _), error(system_error(units_mismatch), _), R is caught)
esc(R) <- catch((_X is ++(metre(3) + second(2))), error(system_error(units_mismatch), _), R is caught)
py_catcher(M) <- catch(eval_(5(metre) + 3(second), _), ++UnitsMismatch(M), M == M)
uncaught(X) <- eval_(5(metre) + 3(second), X)
"""


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    from clausal.import_hook import _load_module
    d = tmp_path_factory.mktemp("umiso")
    p = d / "umiso.clausal"
    p.write_text(_SRC)
    return _load_module("umiso_mod", str(p))


def _answers(mod, pred):
    v = Var()
    return [_deref_walk(v) for _ in solve((pred, v), mod)]


@pytest.mark.parametrize("pred", ["cmp", "ev", "sl", "ml", "esc"])
def test_iso_catcher_selects_a_units_mismatch(mod, pred):
    assert _answers(mod, pred) == ["caught"]


def test_python_catcher_still_matches(mod):
    [msg] = _answers(mod, "py_catcher")
    assert "metre vs second" in str(msg)


def test_uncaught_mismatch_is_still_the_python_class(mod):
    with pytest.raises(UnitsMismatch):
        _answers(mod, "uncaught")
