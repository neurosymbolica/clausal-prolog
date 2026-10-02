"""The P3-3 Task 3 mutation gate: one door, one policy, provenance per write.

``todo/done/a-shared-predicate-has-no-single-mutation-gate.md`` listed four
channels that can mutate a shared predicate and one guard between them.  This
file pins the replacement: every channel routes through
``Database.mutate(functor, arity, author=..., kind=...)``, which asks ONE
question — "may this author write this row" — and stamps who wrote what on the
row afterwards.

The four channels, and what each does with the gate's refusal:

===========================  =========================================
channel                      surface exception
===========================  =========================================
``Database.assertz`` etc.    the gate's ``LogicException`` (unchanged)
``PredicateMeta._assertz``   ``RuntimeError`` (translated at the surface)
the ``assertz/1`` builtins   the gate's ``LogicException``
``compiler_v2`` step 4/5     ``SyntaxError`` (translated at the surface)
===========================  =========================================

The TEXT is the gate's in all four — the translations wrap it, they do not
replace it — which is what
``todo/done/…-no-single-mutation-gate.md``'s acceptance criterion
("refused with the same diagnostic") asks for.
"""

from __future__ import annotations

import os
import textwrap
import types

import pytest

from clausal.logic.atoms import mint
import clausal.import_hook  # noqa: F401 — installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.database import Clause, Database, WriteStamp
from clausal.logic.exceptions import LogicException
from clausal.logic.predicate import resolve_predicate_row
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from tests.load_write_spy_support import record_load_writes
from tests._suffix import SEAM


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _fixture_path(stem: str) -> str:
    return os.path.join(FIXTURES, f"{stem}.clausal")


def _load_fixture(stem: str, as_name: str | None = None):
    return _load_module(as_name or f"tests.fixtures.{stem}", _fixture_path(stem))


def _clause(functor, *args):
    return Clause(head=(functor, *args) if args else functor, body=[])


def _write_module(tmp_path, name: str, source: str):
    path = tmp_path / f"{name}{SEAM}"
    path.write_text(textwrap.dedent(source).lstrip())
    return _load_module(name, str(path))


def _db_of(module):
    return module.__dict__["$module"].db


def _answers(module, functor):
    lm = module.__dict__["$module"]
    x = Var()
    return [deref(x) for _ in call(functor, x, module=lm)]


def _row_of(module, binding, arity):
    """The row a module-dict *binding* reaches, read from *module*'s Database.

    After the W4b-2d flip a predicate binding is a mangled HANDLE (a str),
    not a class, so "which row does it read" goes through the db."""
    return resolve_predicate_row(binding, arity=arity, db=_db_of(module))


def _refusal_text(exc) -> str:
    """The gate's one refusal line, wherever a channel surfaced it."""
    if isinstance(exc, LogicException):
        return exc.message
    return str(exc)


# ── The gate itself ────────────────────────────────────────────────────────


def test_mutate_yields_the_row_and_stamps_the_write():
    db = Database()
    with db.mutate("f", 1, author="me", kind="assert", detail="f/1") as row:
        row.ensure_clauses().append(_clause("f", 1))
    assert db.row("f", 1).writes[-1] == WriteStamp("me", "assert", "f/1")


def test_a_nested_mutate_inherits_the_outer_authorization_and_stamp():
    """The gate authorizes a TRANSACTION, not a call: a write nested inside an
    authorized transaction is that transaction's write, stamped once."""
    db = Database()
    with db.mutate("f", 1, author="outer", kind="load-clauses"):
        db.assertz(_clause("f", 1))          # opens its own (nested) mutate
    stamps = db.row("f", 1).writes
    assert [s.author for s in stamps] == ["outer"]
    assert stamps[-1].kind == "load-clauses"


def test_the_gate_invalidates_dispatch_when_the_clause_list_changed():
    db = Database()
    with db.mutate("f", 1, author="me", kind="recompile") as row:
        row.dispatch_fn = lambda *a: iter(())
    assert db.row("f", 1).dispatch_fn is not None
    db.assertz(_clause("f", 1))
    assert db.row("f", 1).dispatch_fn is None


def test_installing_a_dispatch_inside_the_txn_is_not_invalidated_on_exit():
    db = Database()
    fn = lambda *a: iter(())  # noqa: E731
    with db.mutate("f", 1, author="me", kind="assert") as row:
        row.ensure_clauses().append(_clause("f", 1))
        row.dispatch_fn = fn
    assert db.row("f", 1).dispatch_fn is fn


# ── Channel 2 of the todo's table: the dispatch door is shut ───────────────


def test_a_dispatch_install_through_the_row_outside_a_txn_raises():
    db = Database()
    row = db.row("f", 1, create=True)
    with pytest.raises(RuntimeError) as exc_info:
        row.dispatch_fn = lambda *a: iter(())
    msg = str(exc_info.value)
    assert "PredRow.dispatch_fn" in msg, "the refusal must name the channel"
    assert "f/1" in msg
    assert "Database.mutate" in msg, "and the door that is open"


# ── The policy: may this author write this row ─────────────────────────────


_LOCKED_SRC = """
    -module({name}, [{name}_p/1])

    {name}_p(1)
"""


def _locked_module(tmp_path, name):
    module = _write_module(tmp_path, name, _LOCKED_SRC.format(name=name))
    return module, _db_of(module), getattr(module, f"{name}_p")


def test_channel_1_low_level_db_assertz_from_a_non_owner_is_refused(tmp_path):
    module, db, binding = _locked_module(tmp_path, "gate_c1")
    row = _row_of(module, binding, 1)
    assert row is db.row("gate_c1_p", 1)
    assert row.locked is True
    with pytest.raises(LogicException) as exc_info:
        db.assertz(_clause("gate_c1_p", 2))
    assert "may not write gate_c1_p/1" in _refusal_text(exc_info.value)
    assert _answers(module, "gate_c1_p") == [1], "and the answers did not move"


def test_channel_4_the_assertz_builtin_from_a_non_owner_is_refused(tmp_path):
    owner = _load_fixture("impclob_owner")
    module = _write_module(
        tmp_path, "gate_c4",
        """
        -module(gate_c4, [go(X)])
        -import_from(tests.fixtures.impclob_owner, [impclob_colour])
        -private([blue])

        go(X_UNUSED) <- assertz(impclob_colour(blue))
        """,
    )
    with pytest.raises(LogicException) as exc_info:
        next(call("go", Var(), module=module.__dict__["$module"]), None)
    assert "may not write impclob_colour/1" in _refusal_text(exc_info.value)
    assert len(_row_of(owner, owner.impclob_colour, 1).clauses) == 2


def test_channel_2_the_compiler_from_a_non_owner_is_refused_with_the_same_text():
    """The load channel translates the refusal to ``SyntaxError`` — pinned
    callers read a ``SyntaxError`` and the rich redefinition diagnostic — but
    the gate's own line rides along, so all four channels say the same thing
    about the same policy."""
    _load_fixture("impclob_owner")
    with pytest.raises(SyntaxError) as exc_info:
        _load_fixture("impclob_redefine")
    msg = str(exc_info.value)
    assert "may not write impclob_colour/1" in msg
    # ... and the diagnostic that told the author what to do instead survives.
    assert "-import_from" in msg
    assert "2 clause" in msg


def test_an_unlocked_unowned_row_takes_writes_from_anyone():
    db = Database()
    db.assertz(_clause("free", 1))
    with db.mutate("free", 1, author="somebody-else", kind="load-clauses") as row:
        row.ensure_clauses().append(_clause("free", 2))
    assert len(db.clauses_for("free", 1)) == 2


# ── Provenance is per WRITE, not per load ──────────────────────────────────


def test_the_owner_load_stamps_the_row_with_its_source_path(tmp_path):
    module = _write_module(
        tmp_path, "gate_prov",
        """
        -dynamic(gate_prov_p/1)
        -module(gate_prov, [gate_prov_p/1, gate_prov_add(X)])

        gate_prov_p(1)
        gate_prov_add(X) <- assertz(gate_prov_p(X))
        """,
    )
    db = _db_of(module)
    row = db.row("gate_prov_p", 1)
    load_stamps = [s for s in row.writes if s.kind == "load-clauses"]
    assert load_stamps, f"no load stamp in {row.writes}"
    assert load_stamps[0].author == os.path.realpath(
        str(tmp_path / f"gate_prov{SEAM}"))


def test_assertz_records_its_own_author_not_the_loading_module(tmp_path):
    """The todo's ``assertz`` defect: a runtime-asserted clause was attributed
    to the load that compiled the predicate.  It now stamps itself."""
    module = _write_module(
        tmp_path, "gate_prov2",
        """
        -dynamic(gate_prov2_p/1)
        -module(gate_prov2, [gate_prov2_p/1, gate_prov2_add(X)])

        gate_prov2_p(1)
        gate_prov2_add(X) <- assertz(gate_prov2_p(X))
        """,
    )
    db = _db_of(module)
    next(call("gate_prov2_add", 2, module=module.__dict__["$module"]), None)
    row = db.row("gate_prov2_p", 1)
    assert sorted(_answers(module, "gate_prov2_p")) == [1, 2]
    runtime = [s for s in row.writes if s.author.startswith("runtime-assert:")]
    assert runtime, f"the assert stamped nothing of its own: {row.writes}"
    assert "gate_prov2" in runtime[-1].author
    load = [s for s in row.writes if s.kind == "load-clauses"]
    assert load and load[0].author != runtime[-1].author, (
        "per-WRITE provenance: the runtime assert must not be credited to the "
        "load that compiled the predicate"
    )


# ── The identity todo's three alias scenarios ──────────────────────────────


def test_alias_scenario_1_one_file_under_two_module_names_is_not_refused():
    """Ownership is keyed on the canonical SOURCE PATH, not the module name
    (identity todo instance 1): a dotted ``-import_from`` name and
    ``load_clausal_module``'s ``_clausal_test_*`` name are the same file.

    Since 2026-09-24 ``impclob_implements`` DEFINES ``impclob_verdict/2``
    instead of implementing a vocabulary import (that idiom is a load error
    now), so the two loads no longer share a row; the scenario that made the
    source key load-bearing was the idiom itself.  Kept as the pin that
    neither route refuses the other."""
    from clausal.testing import load_clausal_module

    a = _load_fixture("impclob_implements", as_name="_gate_probe_a")
    b = load_clausal_module(_fixture_path("impclob_implements"))
    assert _answers(a, "impclob_check") == [mint("ok")]
    assert list(call("impclob_check", Var(), module=b.__dict__["$module"]))


def test_alias_scenario_2_an_aliased_import_cannot_clobber_the_exporter():
    """``alias(f, G)`` binds the class under ``G`` while its functor stays
    ``f`` (identity todo instance 2), and ``module_dict.get(f)`` is therefore
    ``None`` (instance 3).  The gate is asked about the ROW the write lands
    on, so neither spelling walks past it."""
    owner = _load_fixture("impclob_owner")
    with pytest.raises(SyntaxError) as exc_info:
        _load_fixture("impclob_alias_redefine")
    assert "may not write impclob_colour/1" in str(exc_info.value)
    assert len(_row_of(owner, owner.impclob_colour, 1).clauses) == 2


def test_alias_scenario_3_a_second_implementer_is_refused():
    """The SECOND implementer is refused, and credited to the first.  (Until
    2026-09-24 both implemented a clause-free vocabulary import; that idiom
    is itself refused now, so the first implementer DEFINES the predicate and
    the rival imports it from there.)"""
    use = _load_fixture("impclob_implements")
    with pytest.raises(SyntaxError) as exc_info:
        _load_fixture("impclob_implements_rival")
    msg = str(exc_info.value)
    assert "may not write impclob_verdict/2" in msg
    assert "impclob_implements" in msg
    assert _answers(use, "impclob_check") == [mint("ok")]


# ── Fix round 1: the gate's own hygiene ────────────────────────────────────


def test_a_refused_load_writes_nothing_at_all(monkeypatch):
    """The property the deleted step-3c pre-pass carried, restored on the gate.

    Step 3c ran BEFORE the write loop expressly so that "a refusal that fired
    halfway through the loop would leave the other module with a partly-
    clobbered clause list".  Consulting the gate per predicate INSIDE the loop
    dropped that: ``gate_rival`` writes a legal predicate (``gate_rival_local``)
    before it redefines ``gv_owned`` (refused), so the legal write had
    already landed, attributed to a module that never finished loading.

    The gate's policy is pure, so the load now runs it over every key it is
    about to write BEFORE writing any of them.  Counted at the door itself
    (``Database.mutate``), with a positive control: the same spy sees the
    writes of a load that is NOT refused.  (Until 2026-09-24 the legal first
    write implemented the clause-free ``gv_free`` -- the dropped
    "vocabulary-implements" idiom, itself a load error now.)"""
    vocab = _load_fixture("gate_vocab")
    writes = record_load_writes(monkeypatch)

    with pytest.raises(SyntaxError) as exc_info:
        _load_fixture("gate_rival")
    assert "may not write gv_owned/1" in str(exc_info.value)
    assert writes.by("gate_rival") == [], (
        f"the refused load opened {writes.by('gate_rival')} -- the LEGAL "
        f"earlier write must not have landed either; the refusal is for the "
        f"load, not for one predicate of it")
    # Read through the owner's Database, not the class (``_state_row``), so
    # the pin holds once the binding is a handle (2026-09-25, small arms).
    assert len(vocab.__dict__["$module"].db.row("gv_owned", 1).clauses) == 1

    # Positive control: the same recorder sees a permitted load's writes.
    _load_fixture("gate_vocab")
    assert ("gv_owned", 1) in writes.by("gate_vocab"), writes.opened


def test_a_raise_inside_a_transaction_still_invalidates_and_stamps():
    """State hygiene is owed however the transaction ends.

    A body that appends a clause and then raises used to leave the row holding
    the new clause with the dispatch compiled from the old one — stale, and
    unstamped.  Reachable through ``assertz/1``, whose recompile runs inside
    the transaction and can raise."""
    db = Database()
    db.assertz(_clause("boom", 1))
    fn = lambda *a: iter(())  # noqa: E731
    with db.mutate("boom", 1, author="me", kind="recompile") as row:
        row.dispatch_fn = fn
    assert db.row("boom", 1).dispatch_fn is fn

    with pytest.raises(ValueError):
        with db.mutate("boom", 1, author="me", kind="assert",
                       detail="assertz") as row:
            row.ensure_clauses().append(_clause("boom", 2))
            raise ValueError("mid-write")

    row = db.row("boom", 1)
    assert row.dispatch_fn is None, "the stale dispatch must be gone"
    assert row.writes[-1].author == "me"
    assert "failed" in str(row.writes[-1].detail), (
        f"the failed write must be stamped as one: {row.writes[-1]}"
    )


def test_a_same_length_clause_edit_still_invalidates():
    """Change detection may not be a length comparison: one transaction that
    removes a clause and adds another leaves the count alone and the compiled
    dispatch just as stale."""
    db = Database()
    db.assertz(_clause("swap", 1))
    fn = lambda *a: iter(())  # noqa: E731
    with db.mutate("swap", 1, author="me", kind="recompile") as row:
        row.dispatch_fn = fn

    with db.mutate("swap", 1, author="me", kind="assert") as row:
        clauses = row.ensure_clauses()
        del clauses[0]
        clauses.append(_clause("swap", 2))

    assert db.row("swap", 1).dispatch_fn is None


def test_an_imported_dynamic_predicate_is_asserted_ON_ITS_OWNER():
    """A runtime assert through a SHARED class writes the owner's clause list.

    ``-import_from`` shares one predicate deliberately.  P3-3 Task 2 made
    ``compiler._install`` re-bind the class on every recompile, so an
    importer's ``assertz`` moved the shared class onto the IMPORTER's row:
    the owner's own query then answered from the importer's clause list
    (``[1]`` became ``[2]``) while the owner's row still held its clause.

    The pre-P3-3 semantics — one shared class, one clause list, both modules
    seeing every clause — are restored by resolving the write to the row the
    class is bound to, and by refusing to re-bind an already-bound class onto
    another database's row from a recompile."""
    owner = _load_fixture("gate_dyn_owner")
    user = _load_fixture("gate_dyn_user")
    owner_db = _db_of(owner)
    cls = owner.gd_p
    owner_row = owner_db.row("gd_p", 1)
    assert owner_row is not None
    assert _row_of(owner, cls, 1) is owner_row
    assert _row_of(user, user.__dict__["gd_p"], 1) is owner_row, (
        "the importer's binding reads the owner's row")

    next(call("gd_add", 2, module=user.__dict__["$module"]), None)

    assert sorted(_answers(owner, "gd_p")) == [1, 2], "the owner sees it"
    assert sorted(_answers(user, "gd_p")) == [1, 2], "and so does the importer"
    assert _row_of(owner, cls, 1) is owner_row, "the shared binding did not move"
    assert _row_of(user, user.__dict__["gd_p"], 1) is owner_row
    assert len(owner_row.clauses) == 2
    runtime = [s for s in owner_row.writes
               if s.author.startswith("runtime-assert:")]
    assert runtime, f"the assert stamped nothing on the owner: {owner_row.writes}"
    assert "gate_dyn_user" in runtime[-1].author, (
        "and the stamp names the module that asserted, not the one that "
        "compiled the predicate"
    )


def test_an_assert_through_a_shared_class_keeps_the_owners_namespace():
    """The recompile an assert triggers uses the OWNER's module globals.

    Fix round 1 resolved a runtime write through an ``-import_from``'d class
    to the owner's row (``_home_db``) but kept passing the ASSERTING module's
    globals to the recompile, so the owner's whole clause list was re-lowered
    against the importer's namespace and installed on the owner's row: a rule
    body calling ``shared_helper`` started resolving the IMPORTER's
    ``shared_helper``, and the owner's own answers silently changed
    (``['owner_value']`` became ``['user_value', 9]``).

    The clause list belongs to the home database, so the namespace its bodies
    are compiled in has to be the home database's too."""
    owner = _load_fixture("gate_shared_owner")
    user = _load_fixture("gate_shared_user")

    assert _answers(owner, "sp") == [mint("owner_value")]
    assert _answers(user, "shared_helper") == [mint("user_value")]

    next(call("gsu_add", 9, module=user.__dict__["$module"]), None)

    assert _answers(owner, "sp") == [mint("owner_value"), 9], (
        "the owner's rule still resolves the OWNER's shared_helper"
    )
    assert _answers(owner, "shared_helper") == [mint("owner_value")]
    assert _answers(user, "shared_helper") == [mint("user_value")], (
        "and the importer's own helper is untouched"
    )


_NOOP_RETRACT_SRC = """
-dynamic(np/1)
-table(np/1)
-module({name}, [np/1, nr_drop(X)])

np(1),
np(2),

nr_drop(X) <- retract(np(X))
"""


def test_a_noop_retract_is_not_a_write(tmp_path):
    """``retract/1`` that matches nothing opens no transaction.

    Fix round 1 moved invalidation into the gate's unwind, keyed on the write
    KIND — but the ``retract/1`` builtin opened its transaction BEFORE the
    search, so a retract that matched nothing still dropped the compiled
    dispatch, abolished the tabled answers and stamped a write that never
    happened.  ``Database.retract`` has always pre-checked and opened no
    transaction; the two retract doors have to agree."""
    module = _write_module(tmp_path, "gate_noop_retract", _NOOP_RETRACT_SRC.format(
        name="gate_noop_retract"))
    lm = module.__dict__["$module"]
    db = lm.db
    row = db.row("np", 1)

    assert sorted(_answers(module, "np")) == [1, 2]
    dispatch_before = row.dispatch_fn
    assert dispatch_before is not None
    tables_before = len(db.table_store)
    assert tables_before == 1
    writes_before = list(row.writes)

    next(call("nr_drop", 99, module=lm), None)

    assert row.dispatch_fn is dispatch_before, "no match, so no invalidation"
    assert len(db.table_store) == tables_before, "and the table survives"
    assert list(row.writes) == writes_before, "and nothing is stamped"
    assert len(row.clauses) == 2

    # A retract that DOES match still goes through the gate.
    next(call("nr_drop", 1, module=lm), None)
    assert len(row.clauses) == 1, "the clause is gone"
    assert row.dispatch_fn is not dispatch_before, (
        "a real retract replaces the dispatch compiled from the old clause list"
    )
    assert len(db.table_store) == 0, "and abolishes the stale tabled answers"
    assert [s.kind for s in row.writes[len(writes_before):]] == ["retract"]
    assert sorted(_answers(module, "np")) == [2]


def test_an_aliased_import_asserts_ON_ITS_OWNER():
    """A write through an ALIASED ``-import_from`` lands on the owner's row.

    ``-import_from(m, [alias(bo_p, alias_s)])`` binds the exporter's class
    under ``alias_s``, so the assert's canonical functor (``bo_p``, the
    class's own name) resolves to no class by NAME in the importer's dict —
    or, when the importer also declares ``-dynamic(bo_p/1)``, to a local
    shadow class that is not the predicate the goal named.  Either way the
    clause used to land somewhere other than the row the shared class reads,
    while ``compiler._install`` still wrote the dispatch onto that shared
    class — so the owner's answers moved and its clauses did not.

    Under P2 the goal's term is a CELL, which carries the canonical name and
    no module, so the term cannot name the predicate any more.  The
    ``-dynamic(bo_p/1)`` the importer wrote is what names it: a declaration in
    a module that imports that very predicate NAMES THE IMPORT, so the
    canonical spelling binds to the shared class exactly as it does when the
    import is not aliased (``test_an_imported_dynamic_predicate_is_asserted_
    ON_ITS_OWNER``, the same shape with one spelling instead of two)."""
    owner = _load_fixture("gate_alias_owner")
    user = _load_fixture("gate_alias_user")
    owner_db = _db_of(owner)
    cls = owner.bo_p
    owner_row = owner_db.row("bo_p", 1)
    assert owner_row is not None
    assert _row_of(owner, cls, 1) is owner_row
    assert user.__dict__["alias_s"] == cls, "the alias binds the exporter's handle"

    assert _answers(owner, "bo_p") == [1]

    next(call("ga_add", 5, module=user.__dict__["$module"]), None)

    assert _answers(owner, "bo_p") == [1, 5], "the owner keeps its clause and sees the new one"
    assert _answers(user, "alias_s") == [1, 5], "and so does the importer"
    assert _row_of(owner, cls, 1) is owner_row, "the shared binding did not move"
    assert _row_of(user, user.__dict__["alias_s"], 1) is owner_row
    assert len(owner_row.clauses) == 2
    runtime = [s for s in owner_row.writes
               if s.author.startswith("runtime-assert:")]
    assert runtime, f"the assert stamped nothing on the owner: {owner_row.writes}"
    assert "gate_alias_user" in runtime[-1].author


def test_a_local_definition_wins_a_clash_with_an_aliased_import():
    """A ``-dynamic`` declaration names the import only when the module has no
    predicate of its own under the name.

    The sibling of ``test_an_aliased_import_asserts_ON_ITS_OWNER``: there the
    declaration is the module's only mention of ``bo_p``, so it names the
    import.  Here the module also writes ``bo_p(7),``, and a local definition
    keeps its own predicate — the rule ``Database.adopt_row`` states for rows,
    applied to the binding.  Without this, the reroute would send a module's
    writes to a predicate it never meant to touch."""
    owner = _load_fixture("gate_alias_owner")
    clash = _load_fixture("gate_alias_clash")

    assert clash.__dict__["bo_p"] != owner.bo_p, (
        "the local definition, not the import, holds the canonical spelling"
    )
    assert _answers(owner, "bo_p") == [1]
    assert _answers(clash, "bo_p") == [7]

    next(call("gc_add", 9, module=clash.__dict__["$module"]), None)

    assert _answers(clash, "bo_p") == [7, 9], "the write stayed local"
    assert _answers(owner, "bo_p") == [1], "and the owner is untouched"
    assert len(_db_of(owner).row("bo_p", 1).clauses) == 1


def test_a_permitted_write_to_a_foreign_row_is_told_where_to_declare_it():
    """The vocabulary refusal's REMEDY names the owning module, not this one.

    ``_check_cell_head_permission`` refuses a cell head whose row is not
    dynamic, and its remedy is "declare it -dynamic(f/N)".  For a row reached
    through an ``-import_from`` that advice is wrong in this module: the
    declaration has to go where the predicate lives.  Reached only when the
    ownership gate PERMITS the write (an adopted row that is neither dynamic
    nor locked), so the verdict is unchanged — it is the remedy that moves."""
    from clausal.logic.builtins.database_ops import _check_cell_head_permission

    owner, importer = Database(), Database()
    owner.module_dict = {"__name__": "gate_vocab_owner"}
    row = owner.row("vp", 1, create=True)
    row.ensure_clauses().append(_clause("vp", 1))
    owner._clauses[("vp", 1)] = row.clauses
    assert not row.locked and not row.dynamic, "the gate must PERMIT this one"

    assert importer.adopt_row("vp", 1, row) is True
    importer.module_dict = {"$module": types.SimpleNamespace(db=importer)}
    assert importer.row("vp", 1) is row, "the importer reaches the owner's row"

    with pytest.raises(LogicException) as exc_info:
        _check_cell_head_permission(("vp", 2), "assertz/1", importer,
                                    importer.module_dict)
    text = _refusal_text(exc_info.value)
    assert "vp/1 is a static procedure" in text
    assert "it belongs to gate_vocab_owner" in text, text
    assert "belongs there, not here" in text, text
