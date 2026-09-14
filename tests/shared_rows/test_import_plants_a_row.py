"""spec §4 q1: an import makes the predicate resolvable in the IMPORTER's Database.

Today `-import_from` is `getattr` and the importing Database holds no row and no
dispatch for an imported predicate -- the whole relationship is one Python object
reference in `module_dict`. These tests pin the relationship into the Database,
keyed by the IMPORTER'S OWN spelling, so that `db.row(functor, arity)` becomes a
correct answer to "what does this name mean here".

The suite asserts WHICH TREE it is exercising: this lane has twice had a probe
silently import the editable-installed canonical package while reporting on the
worktree.
"""
import os
import tempfile

import pytest

import clausal
from clausal.import_hook import _load_module

_TREE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_the_suite_is_exercising_this_worktree():
    """Positive control: without it, every assertion below could be about
    another tree entirely."""
    assert clausal.__file__.startswith(_TREE), (
        f"imported clausal from {clausal.__file__}, not from {_TREE}")


@pytest.fixture(scope="module")
def mods():
    """exporter / plain importer / aliasing importer, loaded once."""
    d = tempfile.mkdtemp()

    def write(name, text):
        p = os.path.join(d, f"{name}.clausal")
        with open(p, "w") as fh:
            fh.write(text)
        return p

    write("sr_exporter",
          "-module(sr_exporter, [edge, solo])\n"
          "edge(1, 2),\n"
          "edge(2, 3),\n"
          "solo(9),\n")
    write("sr_plain",
          "-module(sr_plain, [two_hop, own])\n"
          "-import_from(sr_exporter, [edge])\n"
          "own(0),\n"
          "two_hop(X, Z) <- (edge(X, Y), edge(Y, Z)),\n")
    write("sr_alias",
          "-module(sr_alias, [hop])\n"
          "-import_from(sr_exporter, [alias(edge, link)])\n"
          "hop(X, Y) <- (link(X, Y)),\n")

    import sys
    sys.path.insert(0, d)
    try:
        return {
            "exporter": _load_module("sr_exporter", os.path.join(d, "sr_exporter.clausal")),
            "plain": _load_module("sr_plain", os.path.join(d, "sr_plain.clausal")),
            "alias": _load_module("sr_alias", os.path.join(d, "sr_alias.clausal")),
        }
    finally:
        sys.path.remove(d)


def _db(mod):
    return mod.__dict__["$module"].db


def test_the_importer_s_database_resolves_the_imported_predicate(mods):
    """The whole point: `db.row(functor, arity)` answers for an imported name."""
    assert _db(mods["plain"]).row("edge", 2) is not None


def test_an_aliased_import_is_keyed_by_the_ALIAS(mods):
    """``alias(edge, link)`` — the importer says ``link``, so ``link`` is the key.

    This is the property that makes a row map better than a class: a class
    carries its own ``__name__``, so the exporter's spelling travels with it
    and ``_import_from_origins`` has to index under both names to stop an
    aliased write clobbering the exporter. A key has no intrinsic name.
    """
    adb = _db(mods["alias"])
    assert adb.row("link", 2) is not None, "the alias is not resolvable"


def test_an_aliased_import_does_NOT_plant_the_exporter_s_spelling(mods):
    """The aliasing module never wrote ``edge``; it must not acquire it."""
    adb = _db(mods["alias"])
    assert adb.row("edge", 2) is None


def test_adopting_never_displaces_a_row_this_database_already_has():
    """A module that imports a name AND defines its own predicate under it
    keeps its own. Resolving that clash silently, in load order, is how the
    aliased-import clobber (adf95a31) destroyed an exporter's predicate."""
    from clausal.logic.database import Database
    mine, theirs = Database(), Database()
    my_row = mine.row("p", 1, create=True)
    their_row = theirs.row("p", 1, create=True)

    adopted = mine.adopt_row("p", 1, their_row)

    assert adopted is False, "adoption displaced an existing row"
    assert mine.row("p", 1) is my_row


def test_owns_separates_a_database_s_own_predicates_from_adopted_ones():
    """The replacement for asking a class whether it 'belongs elsewhere':
    a row knows its own database, so ownership needs no class identity."""
    from clausal.logic.database import Database
    mine, theirs = Database(), Database()
    mine.row("local", 0, create=True)
    mine.adopt_row("borrowed", 1, theirs.row("borrowed", 1, create=True))

    assert mine.owns("local", 0) is True
    assert mine.owns("borrowed", 1) is False
    assert mine.owns("never_heard_of_it", 3) is False


# ── Regression pins ──────────────────────────────────────────────────────────
# Not TDD drivers: these pin behaviour that already held and must survive the
# plant. The plant adds entries to `Database._rows`, and `_rows` is read by
# `_write_rows`, which defines the mutation gate's blast radius -- so "nothing
# else moved" is the claim that needs pinning, not the new capability.

def test_an_adopted_row_reaches_the_exporter_s_clauses(mods):
    idb = _db(mods["plain"])
    assert len(idb.row("edge", 2).clauses) == 2


def test_the_importer_still_does_not_DEFINE_the_imported_predicate(mods):
    """`row exists` and `is_defined` are different questions, and the P1
    prerequisite turned on keeping them different. Adoption must not blur them."""
    idb = _db(mods["plain"])
    assert idb.row("edge", 2) is not None
    assert idb.is_defined("edge", 2) is False
    assert _db(mods["exporter"]).is_defined("edge", 2) is True


def test_the_importer_s_own_predicates_are_still_its_own(mods):
    idb = _db(mods["plain"])
    assert idb.owns("own", 1) is True
    assert idb.owns("edge", 2) is False


def test_an_import_that_names_no_predicate_plants_nothing(mods):
    """Negative control: `solo` is exported but nobody imported it, so it must
    not appear in either importer's database."""
    assert _db(mods["plain"]).row("solo", 1) is None
    assert _db(mods["alias"]).row("solo", 1) is None


def test_imported_predicates_still_answer_end_to_end(mods):
    """The behaviour the whole change must not break."""
    from clausal.logic.variables import Var
    X, Z = Var(), Var()
    assert sorted((X.value, Z.value) for _ in mods["plain"].two_hop(X, Z)) == [(1, 3)]
    A, B = Var(), Var()
    assert sorted((A.value, B.value) for _ in mods["alias"].hop(A, B)) == [(1, 2), (2, 3)]


def test_a_local_definition_takes_over_a_name_that_was_adopted_first():
    """Adoption must never shadow a predicate this database goes on to define.

    Imports are processed at step 0, BEFORE any local clause is compiled, so
    "never displace an existing entry" cannot protect a module that imports a
    name and then defines its own predicate under it -- at plant time there is
    nothing to displace yet. `tests/fixtures/fnmismatch_use.clausal` is exactly
    that module, and its local clause silently stopped producing solutions.

    The rule that makes the ordering irrelevant: a WRITE (`create=True`) always
    lands on a row this database owns.
    """
    from clausal.logic.database import Database
    mine, theirs = Database(), Database()
    mine.adopt_row("p", 1, theirs.row("p", 1, create=True))

    assert mine.row("p", 1) is not None, "a read should still resolve to the adopted row"
    assert mine.owns("p", 1) is False

    local = mine.row("p", 1, create=True)

    assert local.db is mine, "a write landed on another database's row"
    assert mine.owns("p", 1) is True
    assert mine.row("p", 1) is local, "the local row must now win reads too"
