"""Load step 4 -- what the clause install writes onto the ROW, whatever the
predicate's name is bound to.

Step 4 used to stamp ``row.source`` (the owner the mutation gate reads) only
when the module dict bound the functor to a ``PredicateMeta`` class.  After the
PredicateMeta retirement flip every binding is a mangled atom, so nothing
would be stamped, every row would read as unowned, and the gate's
clause-clobber refusal would pass every load.  These tests pin the stamp to
the row, with the non-class shape exercised TODAY: ``t5b_local_pred`` binds
``t5b_slot`` to an imported ATOM while defining a local ``t5b_slot/2``.

The last test is a TRIPWIRE, not a fix: a predicate's keyword signature for
an undeclared predicate still comes from the class's field names, and nothing
supplies those once there is no class.  It must fail when the flip lands
until that is designed (todo/step4-signature-comes-from-the-class-2026-09-24.md).
"""

from __future__ import annotations

import os
import textwrap

import clausal.import_hook  # noqa: F401 — installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.predicate import PredicateMeta, module_source_path


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _write_module(tmp_path, name: str, source: str):
    path = tmp_path / f"{name}.clausal"
    path.write_text(textwrap.dedent(source).lstrip())
    return _load_module(name, str(path))


def test_a_predicate_whose_name_is_bound_to_an_atom_is_owned_by_its_load():
    """The post-flip shape, available today: the name is not a class."""
    module = _load_module("tests.fixtures.t5b_local_pred",
                          os.path.join(FIXTURES, "t5b_local_pred.clausal"))
    lm = module.__dict__["$module"]
    assert not isinstance(module.__dict__.get("t5b_slot"), PredicateMeta), (
        "the fixture no longer exercises a non-class binding")
    row = lm.db.row("t5b_slot", 2)
    assert row.clauses, "the local definition wrote no clauses"
    assert row.source == ("tests.fixtures.t5b_local_pred",
                          module_source_path(module.__dict__))


def test_every_clause_bearing_row_a_module_owns_has_an_owner(
        tmp_path, monkeypatch):
    """The population check: non-empty, covering BOTH binding shapes, and no
    clause-bearing owned row left unstamped.  ``s4rs_slot`` is imported as an
    atom, so the local ``s4rs_slot/2`` arrives with a non-class binding."""
    monkeypatch.syspath_prepend(str(tmp_path))
    _write_module(tmp_path, "s4rs_vocab", """
        -module(s4rs_vocab, [s4rs_slot])
    """)
    module = _write_module(tmp_path, "s4rs_owned", """
        -import_from(s4rs_vocab, [s4rs_slot])

        s4rs_a(1),
        s4rs_a(2),
        s4rs_b(X, Y) <- (s4rs_a(X), s4rs_a(Y)),
        s4rs_slot(7, 1),
    """)
    assert not isinstance(module.__dict__.get("s4rs_slot"), PredicateMeta), (
        "s4rs_slot is bound to a class: the non-class path is not exercised")
    assert isinstance(module.__dict__.get("s4rs_a"), PredicateMeta)
    db = module.__dict__["$module"].db
    bearing = {k for k in db.owned_keys() if db.row(*k).clauses}
    assert {("s4rs_a", 1), ("s4rs_b", 2), ("s4rs_slot", 2)} <= bearing
    assert {k for k in bearing if db.row(*k).source is None} == set()
    assert {db.row(*k).source[0] for k in bearing} == {"s4rs_owned"}


def test_an_undeclared_predicate_carries_the_field_names_of_its_head(tmp_path):
    """TRIPWIRE for the flip.  ``define_predicate`` registers no signature
    here; the ``(r, s)`` comes from the class the rewriter minted."""
    module = _write_module(tmp_path, "s4rs_sig", """
        s4rs_pair(1, 2),
        s4rs_swap(R, S) <- s4rs_pair(S, R),
    """)
    db = module.__dict__["$module"].db
    assert db.row("s4rs_swap", 2).signature == ("r", "s"), (
        "EXPECTED to go red when the PredicateMeta flip lands: the field "
        "names live only on the class -- see "
        "todo/step4-signature-comes-from-the-class-2026-09-24.md")
