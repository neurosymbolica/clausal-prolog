"""tests/test_inspection_registration_probes.py — registration-asserting
probes for the seven non-``type_checks`` inspection/constraint builtins named
in todo/done/registration-asserting-probes-for-inspection-builtins-2026-09-05.md
(P3-3 Task 8 fold-in).

The cautionary tale (P3-2 Task 2 fix round 2, ``.superpowers/sdd/
p32-cell-default-flip/task-2-report.md`` §20-21): a probe for ``callable_/1``
called it ``callable`` — the ISO spelling, not the registered one — and
because BOTH the cell input and the class-term control raised the SAME
``KeyError`` for the unregistered name, the comparison read as "twins agree"
while neither twin had actually run. ``type_checks.py`` was fixed with
registration-asserting probes; this file extends that same discipline to the
seven names Task 2's own report (§25) flagged as never re-audited the same
way: ``term_variables/2``, ``copy_term/2``, ``=../2``, ``functor/3``,
``arg/3``, ``numbervars/3``, ``dif/2``.

Pattern mirrored from
``tests/test_tagged_terms.py::TestCallableAndTheTupleDataEdge``: every probe
first asserts the name it is about to drive resolves through the same
registry ``call()`` consults (``_BUILTINS`` / ``_DB_BUILTINS`` in
``clausal.logic.builtins._registry``), THEN drives a cell-shaped input.
(The retired ``Compound`` class used to be driven alongside as a control.)
"""

from __future__ import annotations

import pytest

from clausal.logic.atoms import mint
from clausal.logic.database import Module
from clausal.logic.solve import solve
from clausal.logic.variables import Var, Trail, deref
from clausal.terms import Call, LoadName


# ── Helpers ────────────────────────────────────────────────────────────────────


def _assert_registered(name: str, arity: int) -> None:
    """Fail loudly if *name*/*arity* is not actually registered — the exact
    check the ``callable_`` incident shows a probe must not skip."""
    from clausal.logic.builtins._registry import _BUILTINS, _DB_BUILTINS

    assert (name, arity) in _BUILTINS or (name, arity) in _DB_BUILTINS, (
        f"{name}/{arity} is not registered — a probe against it would "
        f"compare two identical KeyErrors and call that agreement"
    )


def _fresh_module():
    return Module("_t8_inspection_probe")


def _goal(functor, *args):
    return Call(func=LoadName(name=functor), args=list(args), kwargs=[])


def _drive(g):
    """Assert *g*'s functor/arity is actually registered, THEN return a
    fresh ``(module, trail, solutions-iterator)`` driving it.

    P3-3 Task 8 fix round 1 (F5): every probe helper below funnels through
    this single choke point so the registration assertion cannot be left
    off a probe by construction — the ``callable_`` incident's whole lesson
    is that a comparison which never actually registered the check can look
    healthy while proving nothing. Standing this up as ONE driving helper
    (rather than a per-test-method sibling call) is stronger than the
    original per-class ``test_X_is_registered`` methods, which stay in
    place as explicit, individually-readable pins but are no longer the
    only thing standing between a probe and a silently-unregistered name.
    """
    _assert_registered(g.func.name, len(g.args))
    mod = _fresh_module()
    trail = Trail()
    return mod, trail, solve(g, mod, trail)


def _solutions(g):
    _mod, _trail, it = _drive(g)
    return list(it)


def _sol_var(g, var):
    """Deref *var* after each solution of *g*."""
    _mod, _trail, it = _drive(g)
    return [deref(var) for _ in it]


def _sol_vars(g, *variables):
    """Deref every var in *variables*, as a tuple, after each solution of *g*."""
    _mod, _trail, it = _drive(g)
    return [tuple(deref(v) for v in variables) for _ in it]


# ── functor/3 ──────────────────────────────────────────────────────────────────


class TestFunctor3RegistrationAndCellParity:
    def test_functor_3_is_registered(self):
        _assert_registered("functor", 3)

    def test_decompose_cell(self):
        name_c, arity_c = Var(), Var()
        [(nc, ac)] = _sol_vars(
            _goal("functor", ("pt", 1, 2), name_c, arity_c), name_c, arity_c
        )
        assert (nc, ac) == (mint("pt"), 2)


# ── arg/3 ──────────────────────────────────────────────────────────────────────


class TestArg3RegistrationAndCellParity:
    def test_arg_3_is_registered(self):
        _assert_registered("arg", 3)

    def test_first_arg_of_cell(self):
        out_c = Var()
        assert _sol_var(_goal("arg", 1, ("pt", 1, 2), out_c), out_c) == [1]

    def test_second_arg_of_cell(self):
        out_c = Var()
        assert _sol_var(_goal("arg", 2, ("pt", 1, 2), out_c), out_c) == [2]


# ── copy_term/2 ──────────────────────────────────────────────────────────────


class TestCopyTerm2RegistrationAndCellParity:
    def test_copy_term_2_is_registered(self):
        _assert_registered("copy_term", 2)

    def test_copy_of_cell_is_a_cell(self):
        """The cell keeps its shape across the copy — the point of the P3-2
        Task 2 tuple branch in ``_copy_term_py`` (a cell copy that silently
        returned the ORIGINAL would share the source's variables, breaking a
        meta-interpreter's ``copy_term`` use)."""
        copy_c = Var()
        [result_c] = _sol_var(_goal("copy_term", ("pt", 1, 2), copy_c), copy_c)
        assert result_c == ("pt", 1, 2) and type(result_c) is tuple

    def test_copy_of_cell_with_a_var_gets_a_fresh_var(self):
        x = Var()
        copy_c = Var()
        [result_c] = _sol_var(_goal("copy_term", ("pt", x), copy_c), copy_c)
        assert result_c != ("pt", x)  # fresh Var, not the original
        assert result_c[0] == "pt" and result_c[1] is not x


# ── term_variables/2 ─────────────────────────────────────────────────────────


class TestTermVariables2RegistrationAndCellParity:
    def test_term_variables_2_is_registered(self):
        _assert_registered("term_variables", 2)

    def test_vars_collected_from_a_cell(self):
        v1, v2 = Var(), Var()
        vars_c = Var()
        [collected_c] = _sol_var(_goal("term_variables", ("pt", v1, v2), vars_c), vars_c)
        # Identity-preserving collection: the SAME Var objects come back.
        assert collected_c == [v1, v2]


# ── numbervars/3 ─────────────────────────────────────────────────────────────


class TestNumberVars3RegistrationAndCellParity:
    def test_numbervars_3_is_registered(self):
        _assert_registered("numbervars", 3)

    def test_numbering_a_cells_vars(self):
        v1, v2 = Var(), Var()
        end_c = Var()
        _mod, _trail, it = _drive(_goal("numbervars", ("pt", v1, v2), 0, end_c))
        labels_c = None
        for _ in it:
            labels_c = (deref(v1), deref(v2), deref(end_c))
        assert labels_c == (
            ("$VAR", 0), ("$VAR", 1), 2,
        )


# ── dif/2 ────────────────────────────────────────────────────────────────────


class TestDif2RegistrationAndCellParity:
    def test_dif_2_is_registered(self):
        _assert_registered("dif", 2)

    def test_unresolvable_dif_over_cells(self):
        """Two structurally-open cells that COULD still unify: dif/2 posts a
        (deferred) constraint and succeeds."""
        x, y = Var(), Var()
        assert len(_solutions(_goal("dif", ("pt", x), ("pt", y)))) == 1

    def test_definitely_equal_cells_fail_dif(self):
        assert len(_solutions(_goal("dif", ("pt", 1), ("pt", 1)))) == 0


# ── =.. (registered as unpack/2) ─────────────────────────────────────────────


class TestUnivIsRegisteredAsUnpackAndCellParity:
    """``unpack/2`` is the Python-callable form of ISO ``=..``.

    UPDATED 2026-09-09. This probe used to assert that ISO ``=..`` had no
    registered spelling of its own. It does now — spec
    docs/superpowers/specs/2026-09-09-standard-order-of-terms-design.md §6
    registers the canonical quoted form so corpus code has an ISO spelling to
    migrate to. The assertion is replaced rather than deleted, and made
    STRONGER: the two names must resolve to the SAME function object, because
    ``'=..'`` is registered as an alias and not as a second implementation.
    If someone later gives it logic of its own, this fails."""

    def test_iso_spelling_is_registered_as_an_alias_of_unpack(self):
        """Both names must wrap the SAME implementation function.

        Not the same REGISTRY entry: `_builtin` puts simple-mode functions
        through `_simple_to_trampoline`, which builds a fresh wrapper per
        registration, so the two entries are necessarily distinct objects.
        What must hold is that both wrappers close over one implementation —
        that is what makes `'=..'` an alias rather than a second copy that
        could drift.
        """
        from clausal.logic.builtins._registry import _BUILTINS
        from clausal.logic.builtins.inspection import _univ__2

        assert ("=..", 2) in _BUILTINS

        def closed_over(fn):
            return {id(c.cell_contents) for c in (fn.__closure__ or ())}

        iso = closed_over(_BUILTINS[("=..", 2)])
        unpack = closed_over(_BUILTINS[("unpack", 2)])
        assert id(_univ__2) in iso, "'=..' does not wrap _univ__2"
        assert id(_univ__2) in unpack, "unpack/2 does not wrap _univ__2"
        assert iso == unpack, (
            "'=..' and unpack/2 wrap different things — one has grown "
            "logic of its own")

    def test_unpack_2_is_registered(self):
        _assert_registered("unpack", 2)

    def test_decompose_cell(self):
        lst_c = Var()
        [result_c] = _sol_var(_goal("unpack", ("pt", 1, 2), lst_c), lst_c)
        assert result_c == [mint("pt"), 1, 2]
