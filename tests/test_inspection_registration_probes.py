"""tests/test_inspection_registration_probes.py — registration-asserting
probes for the seven non-``type_checks`` inspection/constraint builtins named
in todo/done/registration-asserting-probes-for-inspection-builtins-2026-09-05.md
(P3-3 Task 8 fold-in).

The cautionary tale (P3-2 Task 2 fix round 2, ``.superpowers/sdd/
p32-cell-default-flip/task-2-report.md`` §20-21): a probe for ``callable_/1``
called it ``callable`` — the ISO spelling, not the registered one — and
because BOTH the cell input and the Compound control raised the SAME
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
``clausal.logic.builtins._registry``), THEN compares a cell-shaped input
against its ``Compound`` twin side by side — a divergence is the failure,
whichever way it points.
"""

from __future__ import annotations

from clausal.logic.atoms import char_atom, mint
from clausal.logic.database import Module
from clausal.logic.solve import solve
from clausal.logic.variables import Var, Trail, deref
from clausal.terms import Compound, Call, LoadName


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

    def test_decompose_cell_matches_decompose_compound(self):
        name_c, arity_c = Var(), Var()
        [(nc, ac)] = _sol_vars(
            _goal("functor", (mint("pt"), 1, 2), name_c, arity_c), name_c, arity_c
        )
        name_p, arity_p = Var(), Var()
        [(npv, apv)] = _sol_vars(
            _goal("functor", Compound(mint("pt"), (1, 2)), name_p, arity_p), name_p, arity_p
        )
        assert (nc, ac) == (npv, apv) == (mint("pt"), 2)


# ── arg/3 ──────────────────────────────────────────────────────────────────────


class TestArg3RegistrationAndCellParity:
    def test_arg_3_is_registered(self):
        _assert_registered("arg", 3)

    def test_first_arg_of_cell_matches_first_arg_of_compound(self):
        out_c = Var()
        vals_c = _sol_var(_goal("arg", 1, ("pt", 1, 2), out_c), out_c)
        out_p = Var()
        vals_p = _sol_var(_goal("arg", 1, Compound("pt", (1, 2)), out_p), out_p)
        assert vals_c == vals_p == [1]

    def test_second_arg_of_cell_matches_second_arg_of_compound(self):
        out_c = Var()
        vals_c = _sol_var(_goal("arg", 2, ("pt", 1, 2), out_c), out_c)
        out_p = Var()
        vals_p = _sol_var(_goal("arg", 2, Compound("pt", (1, 2)), out_p), out_p)
        assert vals_c == vals_p == [2]


# ── copy_term/2 ──────────────────────────────────────────────────────────────


class TestCopyTerm2RegistrationAndCellParity:
    def test_copy_term_2_is_registered(self):
        _assert_registered("copy_term", 2)

    def test_copy_of_cell_is_a_cell_copy_of_compound_is_a_compound(self):
        """Each representation keeps its own shape across the copy — the
        point of the P3-2 Task 2 tuple branch in ``_copy_term_py`` (a cell
        copy that silently returned the ORIGINAL would share the source's
        variables, breaking a meta-interpreter's ``copy_term`` use)."""
        copy_c = Var()
        [result_c] = _sol_var(_goal("copy_term", ("pt", 1, 2), copy_c), copy_c)
        copy_p = Var()
        [result_p] = _sol_var(_goal("copy_term", Compound("pt", (1, 2)), copy_p), copy_p)

        assert result_c == ("pt", 1, 2)
        assert isinstance(result_p, Compound)
        assert result_p.functor == "pt" and result_p.args == (1, 2)

    def test_copy_of_cell_with_a_var_gets_a_fresh_var_like_compound_does(self):
        x = Var()
        copy_c = Var()
        [result_c] = _sol_var(_goal("copy_term", ("pt", x), copy_c), copy_c)
        assert result_c != ("pt", x)  # fresh Var, not the original
        assert result_c[0] == "pt" and result_c[1] is not x

        y = Var()
        copy_p = Var()
        [result_p] = _sol_var(_goal("copy_term", Compound("pt", (y,)), copy_p), copy_p)
        assert result_p.args[0] is not y


# ── term_variables/2 ─────────────────────────────────────────────────────────


class TestTermVariables2RegistrationAndCellParity:
    def test_term_variables_2_is_registered(self):
        _assert_registered("term_variables", 2)

    def test_vars_collected_from_a_cell_match_the_same_vars_in_a_compound(self):
        v1, v2 = Var(), Var()
        vars_c = Var()
        [collected_c] = _sol_var(_goal("term_variables", ("pt", v1, v2), vars_c), vars_c)
        vars_p = Var()
        [collected_p] = _sol_var(
            _goal("term_variables", Compound("pt", (v1, v2)), vars_p), vars_p
        )
        # Identity-preserving collection: the SAME Var objects come back
        # whichever shape wraps them.
        assert collected_c == [v1, v2]
        assert collected_p == [v1, v2]


# ── numbervars/3 ─────────────────────────────────────────────────────────────


class TestNumberVars3RegistrationAndCellParity:
    def test_numbervars_3_is_registered(self):
        _assert_registered("numbervars", 3)

    def test_numbering_a_cells_vars_matches_numbering_a_compounds_vars(self):
        v1, v2 = Var(), Var()
        end_c = Var()
        _mod, _trail, it = _drive(_goal("numbervars", ("pt", v1, v2), 0, end_c))
        labels_c = None
        for _ in it:
            labels_c = (deref(v1), deref(v2), deref(end_c))
        assert labels_c is not None

        w1, w2 = Var(), Var()
        end_p = Var()
        _mod2, _trail2, it2 = _drive(
            _goal("numbervars", Compound("pt", (w1, w2)), 0, end_p)
        )
        labels_p = None
        for _ in it2:
            labels_p = (deref(w1), deref(w2), deref(end_p))
        assert labels_p is not None

        assert labels_c == labels_p == (
            Compound("$VAR", (0,)), Compound("$VAR", (1,)), 2,
        )


# ── dif/2 ────────────────────────────────────────────────────────────────────


class TestDif2RegistrationAndCellParity:
    def test_dif_2_is_registered(self):
        _assert_registered("dif", 2)

    def test_unresolvable_dif_over_cells_matches_over_compounds(self):
        """Two structurally-open cells that COULD still unify: dif/2 posts a
        (deferred) constraint and succeeds, same as the Compound twin."""
        x, y = Var(), Var()
        nsol_c = len(_solutions(_goal("dif", ("pt", x), ("pt", y))))
        p, q = Var(), Var()
        nsol_p = len(_solutions(_goal("dif", Compound("pt", (p,)), Compound("pt", (q,)))))
        assert nsol_c == nsol_p == 1

    def test_definitely_equal_cells_fail_dif_like_definitely_equal_compounds(self):
        nsol_c = len(_solutions(_goal("dif", ("pt", 1), ("pt", 1))))
        nsol_p = len(_solutions(_goal("dif", Compound("pt", (1,)), Compound("pt", (1,)))))
        assert nsol_c == nsol_p == 0


# ── =.. (registered as unpack/2) ─────────────────────────────────────────────


class TestUnivIsRegisteredAsUnpackAndCellParity:
    """ISO ``=..`` has no registered spelling of its own: ``unpack/2`` is
    the Python-callable form that implements it (its own docstring floats
    ``univ/2`` as a rename candidate that was never taken — see
    ``clausal/logic/builtins/inspection.py::_univ__2``). This probe asserts
    that fact explicitly, then drives the name that IS registered."""

    def test_bare_iso_spelling_is_not_registered(self):
        from clausal.logic.builtins._registry import _BUILTINS, _DB_BUILTINS

        assert ("=..", 2) not in _BUILTINS
        assert ("=..", 2) not in _DB_BUILTINS

    def test_unpack_2_is_registered(self):
        _assert_registered("unpack", 2)

    def test_decompose_cell_matches_decompose_compound(self):
        lst_c = Var()
        [result_c] = _sol_var(_goal("unpack", (mint("pt"), 1, 2), lst_c), lst_c)
        lst_p = Var()
        [result_p] = _sol_var(_goal("unpack", Compound(mint("pt"), (1, 2)), lst_p), lst_p)
        assert result_c == result_p == [mint("pt"), 1, 2]
