"""A -private atom in one module does not change another module's
qualified call.

todo/done/private-declaration-changes-qualified-call-resolution-elsewhere-
2026-09-27.md and todo/done/private-atom-leaks-into-another-modules-
qualified-call-2026-09-25.md: every module dict is seeded from the
process-wide atom pool, so once an UNRELATED module declared
``-private([nosuch])``, ``other_mod.nosuch(1)`` resolved to that atom as if
it were other_mod's own data reference -- a different Python type and
message than without it, depending on load order.
"""
import sys

import pytest

from clausal.predicate_diagnostics import PredicateNotFoundError
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import solve
from clausal.logic.variables import Var


def _load(tmp_path, name, src):
    from clausal.import_hook import _load_module
    p = tmp_path / f"{name}.clausal"
    p.write_text(src)
    return _load_module(name, str(p))


@pytest.fixture
def mods(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    yield tmp_path
    for k in [k for k in sys.modules if k.startswith("pacq_")]:
        del sys.modules[k]


def test_unrelated_private_atom_does_not_change_the_error(mods):
    _load(mods, "pacq_decl", "-module(pacq_decl, [])\n-private([pacq_nosuch])\n")
    _load(mods, "pacq_other", "-module(pacq_other, [real(X)])\nreal(1),\n")
    caller = _load(mods, "pacq_caller",
                   "-module(pacq_caller, [t(R)])\n-import_module(pacq_other)\n"
                   "t(R) <- (pacq_other.pacq_nosuch(R)),\n")
    with pytest.raises(PredicateNotFoundError) as info:
        list(solve(("t", Var()), caller))
    assert "is not defined in module 'pacq_other'" in str(info.value)


def test_the_owner_declaring_the_atom_still_reports_a_data_reference(mods):
    """Positive control: when the TARGET module itself declares the atom,
    the call is still the data-reference error."""
    _load(mods, "pacq_own", "-module(pacq_own, [real(X)])\n"
                            "-private([pacq_mine])\nreal(pacq_mine),\n")
    caller = _load(mods, "pacq_caller2",
                   "-module(pacq_caller2, [t(R)])\n-import_module(pacq_own)\n"
                   "t(R) <- (pacq_own.pacq_mine(R)),\n")
    with pytest.raises(LogicException) as info:
        list(solve(("t", Var()), caller))
    assert not isinstance(info.value, PredicateNotFoundError)
    assert info.value.term[1][0] == "existence_error"
