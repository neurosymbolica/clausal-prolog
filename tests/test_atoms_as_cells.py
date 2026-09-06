"""Stage A probes: a 1-tuple ("foo",) is accepted as an atom beside today's
str atom (spec §6.3, §6.4).  Each test names the spec row it pins.

Builtin goals are cell-shaped tuples, and ``solve/1`` (module=None) refuses
an unqualified cell goal outright (P3-3 Task 6, ``solve.py``'s
``_module_for_moduleless_solve``) — there is no calling module to infer for
a bare tuple goal, builtin or not.  So every probe here runs against a
throwaway loaded module, the same convention ``tests/test_cell_goals.py``
uses for cell goals (``_load_module`` + ``module.__dict__["$module"]``);
the module's own content is irrelevant since only builtins are exercised.
"""
import os
import tempfile

import pytest

import clausal.import_hook  # noqa: F401 — installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.solve import solve
from clausal.logic.exceptions import LogicException

CELL = ("foo",)


def _lm(module):
    return module.__dict__["$module"]


@pytest.fixture
def mod():
    with tempfile.NamedTemporaryFile(
        suffix=".clausal", mode="w", delete=False
    ) as f:
        f.write("z0,\n")
        path = f.name
    try:
        return _load_module("_atoms_as_cells_probe", path)
    finally:
        os.unlink(path)


def _true(goal, m):
    return len(list(solve(goal, _lm(m)))) == 1


def test_atom_1_accepts_cell_atom(mod):           # §6.3 row atom/1
    assert _true(("atom", CELL), mod)


def test_atomic_1_accepts_cell_atom(mod):         # §6.3 row atomic/1
    assert _true(("atomic", CELL), mod)


def test_compound_1_rejects_cell_atom(mod):       # §6.3 arity-0 is not compound
    assert not _true(("compound", CELL), mod)


def test_callable_1_accepts_cell_atom(mod):       # §6.3 row callable/1
    assert _true(("callable_", CELL), mod)


def test_must_be_atom_accepts_cell_atom_and_cell_type_name(mod):
    assert _true(("must_be", ("atom",), CELL), mod)
    assert _true(("must_be", "atom", CELL), mod)


def test_must_be_compound_accepts_cell(mod):
    assert _true(("must_be", ("compound",), ("f", 1)), mod)
    with pytest.raises(LogicException):
        list(solve(("must_be", ("compound",), CELL), _lm(mod)))
