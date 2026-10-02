"""Load step 7 -- locking the static predicates a module owns.

A locked row is what refuses a runtime ``assertz``/``retract`` on a static
procedure.  The step used to find its population by walking the module dict
for ``PredicateMeta`` classes, which selects NOTHING once a predicate's module
binding is a mangled atom -- every static predicate would silently become
mutable (todo/the-lock-loop-stops-selecting-after-the-flip-2026-09-24.md).
The population is now the Database's own rows, so these tests pin:

* the positive control: the population is NON-EMPTY for a module known to
  have static predicates, and a lock step that locks nothing fails here;
* that the lock needs no module dict at all, so a binding's Python type
  cannot empty it;
* the bug the module-dict walk had: an importer locked its exporter's
  ``-dynamic`` predicate, refusing even the owner's own ``assertz``.
"""

from __future__ import annotations

import os
import textwrap

import pytest

import clausal.import_hook  # noqa: F401 — installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.compiler_v2 import _lock_static_predicates
from clausal.logic.database import Clause, Database
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import solve
from clausal.logic.variables import Var, deref
from tests._suffix import SEAM


def _write_module(tmp_path, name: str, source: str):
    path = tmp_path / f"{name}{SEAM}"
    path.write_text(textwrap.dedent(source).lstrip())
    return _load_module(name, str(path))


def _lm(module):
    return module.__dict__["$module"]


def _answers(lm, functor):
    x = Var()
    return sorted(deref(x) for _ in solve((functor, x), lm))


def test_a_module_s_static_predicates_are_locked_and_its_dynamic_ones_not(
        tmp_path):
    """The positive control: a module known to have static predicates comes
    out of the load with a NON-EMPTY set of locked rows, exactly its static
    ones."""
    lm = _lm(_write_module(tmp_path, "lsp_mixed", """
        -dynamic(lsp_d/1)

        lsp_s(1),
        lsp_t(1, 2),
        lsp_d(1),
    """))
    db = lm.db
    locked = {k for k in db.owned_keys() if db.row(*k).locked}
    assert locked, "the lock step locked nothing: every static predicate is mutable"
    assert locked == {("lsp_s", 1), ("lsp_t", 2)}
    assert db.row("lsp_d", 1).locked is False

    with pytest.raises(LogicException, match="static"):
        list(solve(("assertz", ("lsp_s", 2)), lm))
    list(solve(("assertz", ("lsp_d", 2)), lm))
    assert _answers(lm, "lsp_d") == [1, 2]


def test_the_lock_reads_the_database_not_the_module_dict():
    """The step takes the Database alone -- there is no module-dict binding
    whose shape could empty its population."""
    db = Database()
    db.assertz(Clause(head=("st", 1), body=[]))
    db.assertz(Clause(head=("dy", 1), body=[]))
    db.mark_dynamic("dy", 1)

    assert _lock_static_predicates(db) == 1
    assert db.row("st", 1).locked is True
    assert db.row("dy", 1).locked is False


def test_importing_a_dynamic_predicate_does_not_lock_it_on_its_owner(
        tmp_path, monkeypatch):
    """The importer does not re-declare ``-dynamic``, and must not need to:
    the declaration is the OWNER's.  The module-dict walk asked the
    importer's database ``is_dynamic`` about the adopted row, got ``False``,
    and locked the owner's row -- after which the owner's own ``assertz``
    was refused as a write to a static procedure."""
    monkeypatch.syspath_prepend(str(tmp_path))
    owner = _lm(_write_module(tmp_path, "lsp_dyn_owner", """
        -module(lsp_dyn_owner, [lsp_lp(A)])
        -dynamic(lsp_lp/1)

        lsp_lp(1),
    """))
    importer = _lm(_write_module(tmp_path, "lsp_dyn_user", """
        -import_from(lsp_dyn_owner, [lsp_lp])

        lsp_host(X) <- lsp_lp(X),
    """))

    assert owner.db.row("lsp_lp", 1).locked is False
    list(solve(("assertz", ("lsp_lp", 2)), owner))
    list(solve(("assertz", ("lsp_lp", 3)), importer))
    assert _answers(owner, "lsp_lp") == [1, 2, 3]


def test_an_imported_static_predicate_stays_locked(tmp_path, monkeypatch):
    """The other half of the import case: dropping the importer-side lock
    leaves an imported STATIC predicate locked, because its owner's own
    load step locked it."""
    monkeypatch.syspath_prepend(str(tmp_path))
    owner = _lm(_write_module(tmp_path, "lsp_st_owner", """
        -module(lsp_st_owner, [lsp_sp(A)])

        lsp_sp(1),
    """))
    importer = _lm(_write_module(tmp_path, "lsp_st_user", """
        -import_from(lsp_st_owner, [lsp_sp])

        lsp_use(X) <- lsp_sp(X),
    """))

    assert importer.db.row("lsp_sp", 1) is owner.db.row("lsp_sp", 1)
    assert owner.db.row("lsp_sp", 1).locked is True
    with pytest.raises(LogicException, match="static"):
        list(solve(("assertz", ("lsp_sp", 2)), importer))


def test_a_static_predicate_whose_name_is_bound_to_an_atom_is_locked():
    """``t5b_slot`` is imported as an ATOM, so the module dict binds the name
    to that atom -- and the module also defines a local ``t5b_slot/2``.  The
    module-dict walk never saw the predicate and left it writable."""
    path = os.path.join(os.path.dirname(__file__), "fixtures",
                        "t5b_local_pred.clausal")
    lm = _lm(_load_module("tests.fixtures.t5b_local_pred", path))
    assert lm.db.row("t5b_slot", 2).locked is True
    with pytest.raises(LogicException, match="static"):
        list(solve(("assertz", ("t5b_slot", "t5b_a", 9)), lm))


def test_a_declared_clause_less_predicate_locks_its_database_row(tmp_path):
    """A fielded declaration with no clauses, named by a directive, gets a
    row -- but the class in the module dict carries a DIFFERENT (detached)
    row, and the module-dict walk locked that one, leaving the real row
    writable."""
    lm = _lm(_write_module(tmp_path, "lsp_declonly",
                           "-private([lsp_p(X)])\n-discontiguous(lsp_p/1)\n\n"
                           "lsp_q(1),\n"))
    assert lm.db.row("lsp_p", 1).locked is True
    with pytest.raises(LogicException, match="static"):
        list(solve(("assertz", ("lsp_p", 1)), lm))
