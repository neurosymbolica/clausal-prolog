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


# ── Task 5: the name position (spec §5.4, §6.4; §13 rows 7–12, 18c) ───────────
#
# ``functor/3`` and ``unpack/2`` (``=..``) CONSTRUCT CELLS, never a
# ``Compound``, and hand back ``mint(slot0)`` as the name.  ``'.'``/2 in the
# name position builds the engine's list shapes (§5.4) — never a
# ``(".", H, T)`` cell.

from clausal.logic.atoms import char_atom, mint            # noqa: E402
from clausal.logic.predicate import is_atom_value          # noqa: E402
from clausal.logic.variables import Var, deref             # noqa: E402


def _one(goal, m, *vars_):
    """Solve *goal* against *m*, assert exactly ONE answer, and return the
    ``deref``'d values of *vars_* SNAPSHOTTED inside the iteration.

    ``solve`` undoes the trail when its generator is exhausted, so a deref
    taken after ``list(solve(...))`` sees the variables unbound again.
    """
    snaps = [tuple(deref(v) for v in vars_) for _ in solve(goal, _lm(m))]
    assert len(snaps) == 1, f"expected exactly 1 answer, got {len(snaps)}"
    return snaps[0]


def test_functor_3_constructs_a_cell_and_names_an_atom(mod):   # §6.4, §13 rows 7–8
    T = Var()
    (t,) = _one(("functor", T, mint("foo"), 2), mod, T)
    assert type(t) is tuple and t[0] == "foo" and len(t) == 3
    N, A = Var(), Var()
    n, a = _one(("functor", ("foo", 1), N, A), mod, N, A)
    assert n == mint("foo") and a == 1
    T0 = Var()
    (t0,) = _one(("functor", T0, mint("foo"), 0), mod, T0)
    assert t0 == mint("foo")


def test_functor_3_accepts_a_cell_atom_name(mod):              # §6.4, Stage A
    T = Var()
    (t,) = _one(("functor", T, ("foo",), 2), mod, T)
    assert type(t) is tuple and t[0] == "foo" and len(t) == 3
    T0 = Var()
    (t0,) = _one(("functor", T0, ("foo",), 0), mod, T0)
    assert t0 == ("foo",)


def test_univ_constructs_a_cell_and_round_trips(mod):          # §13 rows 10–11
    T = Var()
    (t,) = _one(("unpack", T, [mint("foo"), 1]), mod, T)
    assert t == ("foo", 1)
    L = Var()
    (lv,) = _one(("unpack", ("foo", 1, ("bar",)), L), mod, L)
    assert lv == [mint("foo"), 1, ("bar",)]
    T2 = Var()
    (t2,) = _one(("unpack", T2, lv), mod, T2)
    assert t2 == ("foo", 1, ("bar",))


def test_univ_accepts_a_cell_atom_name(mod):                   # §6.4, Stage A
    T = Var()
    (t,) = _one(("unpack", T, [("foo",), 1]), mod, T)
    assert t == ("foo", 1)
    T0 = Var()
    (t0,) = _one(("unpack", T0, [("foo",)]), mod, T0)
    assert t0 == ("foo",)


def test_functor_3_rejects_number_name_with_arity(mod):
    with pytest.raises(LogicException):
        list(solve(("functor", Var(), 3, 2), _lm(mod)))


def test_functor_3_rejects_a_non_atomic_name(mod):             # §6.4 type_error(atomic)
    with pytest.raises(LogicException):
        list(solve(("functor", Var(), [1, 2], 0), _lm(mod)))


def test_univ_rejects_a_non_atomic_single_element_name(mod):   # §6.4 type_error(atomic)
    with pytest.raises(LogicException):
        list(solve(("unpack", Var(), [[1, 2]]), _lm(mod)))


def test_cons_construction_never_builds_a_dot_cell(mod):       # §5.4, §13 row 18c
    T = Var()
    (t,) = _one(("unpack", T, [mint("."), char_atom("a"), "bc"]), mod, T)
    assert t == "abc"
    T2 = Var()
    (t2,) = _one(("unpack", T2, [mint("."), 1, [2]]), mod, T2)
    assert t2 == [1, 2]
    T3 = Var()
    (t3,) = _one(("functor", T3, mint("."), 2), mod, T3)
    from clausal.terms import SegList
    assert isinstance(t3, SegList)
    T4 = Var()
    (t4,) = _one(("unpack", T4, [mint("."), 1, []]), mod, T4)
    assert t4 == [1]


def test_gensym_and_global_atom_mint_atoms(mod):
    A = Var()
    (a,) = _one(("gensym", mint("g"), A), mod, A)
    assert is_atom_value(a)
    A2 = Var()
    (a2,) = _one(("gensym", ("g",), A2), mod, A2)              # cell prefix, Stage A
    assert is_atom_value(a2)
    G = Var()
    (g,) = _one(("global_atom", mint("zzq_probe"), G), mod, G)
    assert g == mint("zzq_probe")
    _one(("global_atom", mint("zzq_probe"), mint("zzq_probe")), mod)  # guard, by ==
    G2 = Var()
    (g2,) = _one(("global_atom", ("zzq_probe",), G2), mod, G2)  # cell name, Stage A
    assert g2 == mint("zzq_probe")


def test_type_error_term_carries_atom_args():
    from clausal.logic.exceptions import type_error
    t = type_error("atom", 3, "who")
    assert t.args[0].args[0] == mint("atom")
    assert t.args[1] == "who"                                  # context stays a string


def test_listing_accepts_cell_atom(mod, capsys):
    # ``z0`` is the one fact the probe module defines (see the ``mod`` fixture).
    assert len(list(solve(("listing", ("z0",)), _lm(mod)))) == 1
    assert "z0/0" in capsys.readouterr().out


def test_resolve_module_accepts_a_cell_atom_designator(mod):
    from clausal.logic.solve import resolve_module
    assert (resolve_module(("_atoms_as_cells_probe",))
            is resolve_module("_atoms_as_cells_probe"))
