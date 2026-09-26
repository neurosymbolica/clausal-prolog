"""A name exported with NO clauses: what a call, an importer, ``-dynamic``,
``clause/2``, ``listing/1`` and the load binding answer (2026-09-26).

Two export spellings reach this, and they are different declarations today:

* ``name/arity`` -- the ISO spelling (13211-1 module exports are predicate
  indicators) -- declares a PROCEDURE.  It binds the module's predicate
  handle, and a call reports the procedure as undefined in that module.
* ``name(A, B)`` -- a field-carrying entry -- declares a DATA functor
  (ruling R6/R6b, P3-2 Task 2; ``term_rewriting._predicate_export_spec``):
  it binds the atom of its spelling, and references compile to cells.

The ISO-visible answer is the same for both, and is pinned here so neither
can drift: a call raises ``existence_error(procedure, name/arity)`` (flag
``unknown`` at ``error``); ``-dynamic`` makes it fail instead; ``clause/2``
fails (ISO 8.8.1: no such procedure); ``listing/1`` fails (Scryer's
``\\+ \\+ clause(Head, _)``).  ``current_predicate/1`` is not a Clausal
builtin, so it has no answer to pin.

Operator ruling 2026-09-26: a field-carrying export with no clauses "stays a
PROCEDURE, if it agrees with ISO".  Reclassifying it contradicts R6/R6b
and would turn the in-repo DATA exports (tagged terms, constant functors)
into procedures, so that part is PARKED as an open question.  The binding
tests for it are ``xfail(strict=True)``, and flip when it is decided.  What
lands now is behaviour-preserving: the call's MESSAGE says the name is
declared as DATA and names the ISO spelling that exports a procedure,
where it used to blame an unexplained "data reference".
"""

from __future__ import annotations

import sys

import pytest

from clausal.import_hook import _load_module
from clausal.logic.atoms import mangle
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import solve
from clausal.logic.variables import Var, walk
from clausal.terms import Compound


@pytest.fixture
def load(tmp_path):
    names = []

    def _load(name, src):
        path = tmp_path / f"{name}.clausal"
        path.write_text(src)
        sys.modules.pop(name, None)
        names.append(name)
        return _load_module(name, str(path))

    yield _load
    for name in names:
        sys.modules.pop(name, None)


def _lm(mod):
    return mod.__dict__["$module"]


def _answers(mod, goal):
    return [walk(goal) for _ in solve(goal, module=_lm(mod))]


def _error(mod, goal):
    with pytest.raises(LogicException) as info:
        list(solve(goal, module=_lm(mod)))
    term = info.value.term
    assert term.functor == "error"
    return term.args[0], str(term.args[1])


FIELDED = "-module(cle_owner, [edge(A, B)])\n"
ISO_PI = "-module(cle_owner, [edge/2])\n"


def _importer(load, owner):
    return load(f"{owner}_imp",
                f"-import_from({owner}, [edge])\n"
                f"-module({owner}_imp, [q(X)])\n"
                f"q(X) <- edge(1, X)\n")


# ── the ISO-visible answers: identical for both spellings ────────────────────


@pytest.mark.parametrize("src", [FIELDED, ISO_PI], ids=["fielded", "iso-pi"])
class TestISOAnswers:
    def test_a_call_is_an_existence_error_for_the_procedure(self, load, src):
        mod = load("cle_owner", src)
        formal, _ = _error(mod, ("edge", 1, Var()))
        assert formal == Compound("existence_error",
                                  ("procedure", Compound("/", ("edge", 2))))

    def test_a_call_through_an_importer_is_the_same_error(self, load, src):
        load("cle_owner", src)
        imp = _importer(load, "cle_owner")
        formal, _ = _error(imp, ("q", Var()))
        assert formal == Compound("existence_error",
                                  ("procedure", Compound("/", ("edge", 2))))

    def test_dynamic_makes_the_call_fail_instead(self, load, src):
        mod = load("cle_owner", src + "-dynamic(edge/2)\n")
        assert _answers(mod, ("edge", 1, Var())) == []
        load("cle_owner_imp", "-import_from(cle_owner, [edge])\n"
             "-module(cle_owner_imp, [q(X)])\nq(X) <- edge(1, X)\n")
        assert _answers(sys.modules["cle_owner_imp"], ("q", Var())) == []

    def test_clause_2_fails(self, load, src):
        mod = load("cle_owner", src)
        assert _answers(mod, ("clause", ("edge", Var(), Var()), Var())) == []

    def test_listing_fails(self, load, src, capsys):
        mod = load("cle_owner", src)
        assert _answers(mod, ("listing", ("/", "edge", 2))) == []
        assert capsys.readouterr().out == ""


# ── the load binding: which declaration each spelling makes ─────────────────


def test_the_iso_spelling_binds_the_module_handle(load):
    mod = load("cle_owner", ISO_PI)
    assert mod.__dict__["edge"] == mangle("cle_owner", "edge")
    imp = _importer(load, "cle_owner")
    assert imp.__dict__["edge"] == mangle("cle_owner", "edge")


def test_a_fielded_export_is_declared_data_today(load):
    """R6/R6b, unchanged: the binding is the atom, the Database says DATA."""
    mod = load("cle_owner", FIELDED)
    assert mod.__dict__["edge"] == "edge"
    assert _lm(mod).db.declared_kind("edge", 2) == "data"


@pytest.mark.xfail(strict=True, reason=(
    "PARKED (operator ruling 2026-09-26 vs R6/R6b): a clause-less "
    "field-carrying export stays DATA until the conflict is decided"))
def test_ruling_a_clauseless_fielded_export_binds_the_module_handle(load):
    mod = load("cle_owner", FIELDED)
    assert mod.__dict__["edge"] == mangle("cle_owner", "edge")


@pytest.mark.xfail(strict=True, reason=(
    "PARKED (operator ruling 2026-09-26 vs R6/R6b): see above"))
def test_ruling_an_importer_of_a_clauseless_fielded_export_binds_the_handle(
        load):
    load("cle_owner", FIELDED)
    imp = _importer(load, "cle_owner")
    assert imp.__dict__["edge"] == mangle("cle_owner", "edge")


def test_an_exported_bare_atom_stays_an_atom(load):
    """``-module(m, [foo, ...])``: a bare name in an export list is an ATOM,
    and stays one whatever happens to the field-carrying entries."""
    mod = load("cle_atom", "-module(cle_atom, [foo, bar(X)])\nbar(foo)\n")
    assert mod.__dict__["foo"] == "foo"
    assert _answers(mod, ("bar", Var())) == [("bar", "foo")]
    formal, _ = _error(mod, "foo")
    assert formal == Compound("existence_error",
                              ("procedure", Compound("/", ("foo", 0))))


# ── the message (behaviour-preserving part of the ruling) ───────────────────


def test_the_message_says_the_name_is_declared_data_and_how_to_export_a_procedure(
        load):
    mod = load("cle_owner", FIELDED)
    _, message = _error(mod, ("edge", 1, Var()))
    assert "data reference" not in message
    assert "edge/2 is declared as DATA" in message
    assert "edge(A, B)" in message
    assert "write edge/2 in the export list" in message


def test_the_importer_gets_the_same_message(load):
    load("cle_owner", FIELDED)
    imp = _importer(load, "cle_owner")
    _, message = _error(imp, ("q", Var()))
    assert "data reference" not in message
    assert "edge/2 is declared as DATA" in message


def test_an_undeclared_atom_keeps_the_general_message(load):
    """A plain atom called as a goal -- no DATA declaration at that arity --
    is not told about export lists."""
    mod = load("cle_atom", "-module(cle_atom, [foo, bar(X)])\nbar(foo)\n")
    _, message = _error(mod, "foo")
    assert "is declared as DATA" not in message
    assert "is not callable at arity 0" in message
