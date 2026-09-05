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

import pytest

import clausal.import_hook  # noqa: F401 — installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.database import Clause, Database, WriteStamp
from clausal.logic.exceptions import LogicException
from clausal.logic.predicate import make_predicate
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from clausal.terms import Compound


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _fixture_path(stem: str) -> str:
    return os.path.join(FIXTURES, f"{stem}.clausal")


def _load_fixture(stem: str, as_name: str | None = None):
    return _load_module(as_name or f"tests.fixtures.{stem}", _fixture_path(stem))


def _clause(functor, *args):
    return Clause(head=Compound(functor, tuple(args)), body=[])


def _write_module(tmp_path, name: str, source: str):
    path = tmp_path / f"{name}.clausal"
    path.write_text(textwrap.dedent(source).lstrip())
    return _load_module(name, str(path))


def _db_of(module):
    return module.__dict__["$module"].db


def _answers(module, functor):
    lm = module.__dict__["$module"]
    x = Var()
    return [deref(x) for _ in call(functor, x, module=lm)]


def _refusal_text(exc) -> str:
    """The gate's one refusal line, wherever a channel surfaced it."""
    if isinstance(exc, LogicException):
        return str(exc.term.args[1])
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


def test_a_dispatch_install_through_the_class_property_outside_a_txn_raises():
    """THE SECOND DOOR (P3-3 Task 2 carry-forward). ``PredicateMeta.
    _dispatch_fn`` is a class-property onto the same row; gating
    ``Database.mutate`` alone would leave it wide open, and it is the door
    ``compiler._install`` writes through."""
    db = Database()
    cls = make_predicate("gd", ["x"])
    cls._bind_row(db, "gd", 1)
    with pytest.raises(RuntimeError) as exc_info:
        cls._dispatch_fn = lambda *a: iter(())
    assert "dispatch_fn" in str(exc_info.value)
    assert db.row("gd", 1).dispatch_fn is None, "and nothing was written"


def test_a_dispatch_install_through_the_class_gate_is_allowed():
    db = Database()
    cls = make_predicate("gd2", ["x"])
    cls._bind_row(db, "gd2", 1)
    fn = lambda *a: iter(())  # noqa: E731
    with cls._mutate("test", "recompile"):
        cls._dispatch_fn = fn
    assert db.row("gd2", 1).dispatch_fn is fn


def test_assigning_none_is_invalidation_and_needs_no_txn():
    """``invalidate()`` stays THE one invalidation point, and it is not a
    clobber: a cleared dispatch recompiles from the OWNER's clause list."""
    db = Database()
    cls = make_predicate("gd3", ["x"])
    cls._bind_row(db, "gd3", 1)
    with cls._mutate("test", "recompile"):
        cls._dispatch_fn = lambda *a: iter(())
    cls._dispatch_fn = None                      # no txn — allowed
    assert db.row("gd3", 1).dispatch_fn is None


# ── The policy: may this author write this row ─────────────────────────────


_LOCKED_SRC = """
    -module({name}, [{name}_p/1])

    {name}_p(1)
"""


def _locked_module(tmp_path, name):
    module = _write_module(tmp_path, name, _LOCKED_SRC.format(name=name))
    return module, _db_of(module), getattr(module, f"{name}_p")


def test_channel_1_low_level_db_assertz_from_a_non_owner_is_refused(tmp_path):
    module, db, cls = _locked_module(tmp_path, "gate_c1")
    assert cls._locked is True
    with pytest.raises(LogicException) as exc_info:
        db.assertz(Clause(head=cls(2), body=[]))
    assert "may not write gate_c1_p/1" in _refusal_text(exc_info.value)
    assert _answers(module, "gate_c1_p") == [1], "and the answers did not move"


def test_channel_3_the_class_mutator_from_a_non_owner_is_refused(tmp_path):
    module, db, cls = _locked_module(tmp_path, "gate_c3")
    with pytest.raises(RuntimeError) as exc_info:
        cls._assertz(Clause(head=cls(2), body=[]))
    assert "may not write gate_c3_p/1" in str(exc_info.value)
    assert _answers(module, "gate_c3_p") == [1]


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
    assert len(owner.impclob_colour._clauses) == 2


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
        str(tmp_path / "gate_prov.clausal"))


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
    ``load_clausal_module``'s ``_clausal_test_*`` name are the same file."""
    from clausal.testing import load_clausal_module

    _load_fixture("impclob_decl_vocab")
    a = _load_fixture("impclob_implements", as_name="_gate_probe_a")
    b = load_clausal_module(_fixture_path("impclob_implements"))
    assert _answers(a, "impclob_check") == ["ok"]
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
    assert len(owner.impclob_colour._clauses) == 2


def test_alias_scenario_3_a_second_implementer_of_a_vocabulary_is_refused():
    """The clause-free vocabulary import stays legal (nothing to destroy); the
    SECOND implementer is refused, and credited to the first implementer."""
    _load_fixture("impclob_decl_vocab")
    use = _load_fixture("impclob_implements")
    with pytest.raises(SyntaxError) as exc_info:
        _load_fixture("impclob_implements_rival")
    msg = str(exc_info.value)
    assert "may not write impclob_verdict/2" in msg
    assert "impclob_implements" in msg
    assert _answers(use, "impclob_check") == ["ok"]


# ── Fix round 1: the gate's own hygiene ────────────────────────────────────


def test_a_refused_load_writes_nothing_at_all():
    """The property the deleted step-3c pre-pass carried, restored on the gate.

    Step 3c ran BEFORE the write loop expressly so that "a refusal that fired
    halfway through the loop would leave the other module with a partly-
    clobbered clause list".  Consulting the gate per predicate INSIDE the loop
    dropped that: ``gate_rival`` implements ``gv_free`` (legal — clause-free
    vocabulary) before it redefines ``gv_owned`` (refused), so the exporter's
    shared ``gv_free`` class was left holding the failed load's clause, with
    its ``_clauses_source`` naming a module that never finished loading.

    The gate's policy is pure, so the load now runs it over every key it is
    about to write BEFORE writing any of them."""
    vocab = _load_fixture("gate_vocab")
    assert len(vocab.gv_free._clauses) == 0, "the vocabulary starts clause-free"

    with pytest.raises(SyntaxError) as exc_info:
        _load_fixture("gate_rival")
    assert "may not write gv_owned/1" in str(exc_info.value)

    assert len(vocab.gv_free._clauses) == 0, (
        "the LEGAL earlier write must not have landed either — the refusal "
        "is for the load, not for one predicate of it"
    )
    assert vocab.gv_free._clauses_source is None, (
        "and the exporter's class must not be attributed to a module that "
        "failed to load"
    )
    assert len(vocab.gv_owned._clauses) == 1


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
    assert cls._row is owner_row

    next(call("gd_add", 2, module=user.__dict__["$module"]), None)

    assert sorted(_answers(owner, "gd_p")) == [1, 2], "the owner sees it"
    assert sorted(_answers(user, "gd_p")) == [1, 2], "and so does the importer"
    assert cls._row is owner_row, "the shared class did not move"
    assert len(owner_row.clauses) == 2
    runtime = [s for s in owner_row.writes
               if s.author.startswith("runtime-assert:")]
    assert runtime, f"the assert stamped nothing on the owner: {owner_row.writes}"
    assert "gate_dyn_user" in runtime[-1].author, (
        "and the stamp names the module that asserted, not the one that "
        "compiled the predicate"
    )
