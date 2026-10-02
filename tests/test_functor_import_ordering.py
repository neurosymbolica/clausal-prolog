"""Clause heads bind by POSITION when the functor is imported in the same file.

``todo/done/functor-field-name-mismatch-diagnostic.md`` — a module that both declares
a functor locally and ``-import_from``s the same name used to emit its clause
heads with the LOCAL field names against the FOREIGN class the import rebound:

    -module(use, [verdict(STATUS, CITATIONS)])   # mints _fields=(STATUS, CITATIONS)
    -import_from(schema, [verdict])              # rebinds verdict -> schema's class
    verdict("ok", [])                            # verdict(STATUS=…, CITATIONS=…) -> TypeError

Field names are a module-local *labelling of slots*; **arity** is the
cross-module contract.  So a head for a functor the same file imports is
emitted positionally: it binds against whatever class the import supplied, and
a module-local labelling can no longer contradict a foreign class.  A genuine
disagreement is an arity disagreement, which still raises — with full
attribution — from ``PredicateMeta.__call__``.

The narrowing matters: heads are emitted positionally only where the file does
NOT emit a guarded class block at the head itself.  Where it does (the first
clause of a functor), the block re-mints the class to exactly the derived
fields, so keyword emission is precise and is left alone — that is the shape
``tests/fixtures/impord_atom_then_pred.clausal`` pins (import a 0-arity
vocabulary atom, then define a same-named predicate).
"""

from __future__ import annotations

import ast
import os
import warnings

import pytest

from clausal.logic.atoms import mint
import clausal.import_hook  # noqa: F401 — installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.predicate import ClausalTermConstructionError
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref, walk
from clausal.templating.term_rewriting import EmbedTransformer
from tests._suffix import SEAM


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _fixture_path(stem: str) -> str:
    return os.path.join(FIXTURES, f"{stem}.clausal")


def _load_fixture(stem: str):
    return _load_module(f"tests.fixtures.{stem}", _fixture_path(stem))


def _solutions(pred_cls, arity: int):
    """All solutions of *pred_cls* as tuples of stringified bindings."""
    args = [Var() for _ in range(arity)]
    return [
        tuple(walk(deref(a)) for a in args)
        for _ in call(pred_cls, *args)
    ]


def _unparse(source: str) -> str:
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=SyntaxWarning)
        tree = ast.parse(source)
        rewritten = EmbedTransformer(
            source_lines=source.splitlines(), filename=f"t{SEAM}",
        ).visit(tree)
    ast.fix_missing_locations(rewritten)
    return ast.unparse(rewritten)


# ── Codegen: which heads become positional ─────────────────────────────────


class TestHeadEmission:
    def test_imported_functor_head_is_positional(self):
        out = _unparse(
            "-module(m, [f(STATUS, CITATIONS)])\n"
            "-import_from(other, [f])\n"
            "f(A, B) <- g(A, B)\n"
        )
        # ``$head(<binding>, ...)``: the head is built from the binding
        # without calling it (W4b-2d task 5) -- still positional.
        assert "head=$head(f, (A := $Var()), (B := $Var()))" in out
        assert "STATUS=" not in out
        assert "CITATIONS=" not in out

    def test_local_only_functor_head_stays_keyword(self):
        out = _unparse(
            "-module(m, [f(STATUS, CITATIONS)])\n"
            "f(A, B) <- g(A, B)\n"
        )
        assert "STATUS=" in out
        assert "CITATIONS=" in out

    def test_aliased_import_does_not_make_the_original_positional(self):
        """``alias(f, F2)`` binds F2, not f — f is still purely local."""
        out = _unparse(
            "-module(m, [f(STATUS, CITATIONS)])\n"
            "-import_from(other, [alias(f, renamed)])\n"
            "f(A, B) <- g(A, B)\n"
        )
        assert "STATUS=" in out
        assert "CITATIONS=" in out

    def test_first_clause_that_mints_its_own_class_stays_keyword(self):
        """No local declaration → the head emits its own class block, so the
        bound class is known exactly and keyword emission is precise."""
        out = _unparse(
            "-module(m, [])\n"
            "-import_from(other, [f])\n"
            "f(A, B) <- g(A, B)\n"
        )
        assert "a=" in out and "b=" in out

    def test_second_clause_after_a_local_mint_is_positional(self):
        """import-then-declare shape: the first clause re-mints over the
        imported atom and the second binds positionally against that
        re-minted class."""
        out = _unparse(
            "-module(m, [])\n"
            "-import_from(other, [f])\n"
            "f(A, B) <- g(A, B)\n"
            "f(C, D) <- h(C, D)\n"
        )
        assert out.count("a=") == 1


# ── End to end: the pair that used to fail now loads ───────────────────────


class TestDeclareThenImport:
    """``-module(m, [f(…)])`` then ``-import_from(v, [f])`` — the ordering that
    produced the bare ``TypeError``."""

    def test_the_pair_is_refused_at_load_not_by_a_field_name_type_error(self):
        """The field-name clash no longer surfaces: the head is emitted
        positionally, so the module body runs.  What stops the load now is
        the operator ruling of 2026-09-24 -- ``fnmismatch_use`` supplies the
        clauses of a predicate ``fnmismatch_schema`` only DECLARES
        (``-dynamic``, no clauses), the dropped "vocabulary-implements"
        idiom -- and that refusal is a ``SyntaxError`` from step 3d, never the
        ``TypeError`` this fixture was written for.

        (Until 2026-09-24 this class also pinned that the pair LOADS, that
        the local name IS the schema's class, and that solutions flow
        through the local clause.  All three were the idiom itself; identity
        across a declare-then-import is still pinned against a DEFINING
        exporter by ``test_differing_field_names_across_the_import``.)"""
        schema = _load_module(
            "tests.fixtures.fnmismatch_schema",
            _fixture_path("fnmismatch_schema"),
        )
        with pytest.raises(SyntaxError) as exc_info:
            _load_module(
                "tests.fixtures.fnmismatch_use", _fixture_path("fnmismatch_use"),
            )
        assert not isinstance(exc_info.value, ClausalTermConstructionError)
        msg = " ".join(str(exc_info.value).split())
        assert ("tests.fixtures.fnmismatch_schema only declares "
                "fnm_verdict/2") in msg
        assert _solutions(schema.fnm_verdict, 2) == []

    def test_differing_field_names_across_the_import(self):
        """The local declaration spells (STATUS, CITATIONS), the exporter
        (OUTCOME, CITES).  Identity is shared and the exporter's facts flow."""
        vocab = _load_fixture("impord_vocab")
        use = _load_fixture("impord_declare_then_import")
        assert use.impord_verdict is vocab.impord_verdict
        assert _solutions(use.impord_dti_check, 1) == [(mint("ok"),), (mint("no"),)]

    def test_a_local_fact_fills_the_foreign_slots_in_order(self):
        """The bodyless-fact path (``_build_fact_statements``): a fact for an
        imported functor is emitted POSITIONALLY, ``maybe`` in slot 0 and
        ``pending`` in slot 1, not by the local field names.

        Checked on the generated code since 2026-09-24: loading the fixture
        end to end now stops at the dropped "vocabulary-implements" idiom
        (``impord_fact_vocab`` only declares ``impord_fverdict/2``), so the
        answers can no longer be read back.  The load is still checked: it
        must be THAT refusal, not a field-name ``TypeError`` -- which is what
        the positional emission is for."""
        out = _unparse(
            "-private([maybe, pending])\n"
            "-module(m, [f(STATUS, CITATIONS)])\n"
            "-import_from(other, [f])\n"
            "f(maybe, pending)\n"
        )
        assert "head=$head(f, 'maybe', 'pending')" in out
        assert "STATUS=" not in out

        _load_fixture("impord_fact_vocab")
        with pytest.raises(SyntaxError) as exc_info:
            _load_fixture("impord_declare_then_import_fact")
        assert not isinstance(exc_info.value, ClausalTermConstructionError)
        assert "only declares impord_fverdict/2" in " ".join(
            str(exc_info.value).split())


class TestImportThenDeclare:
    """The other textual ordering: import binds first, then the -module
    entry re-exports it with shared class identity."""

    def test_identity_and_solutions_are_preserved(self):
        vocab = _load_fixture("impord_vocab")
        use = _load_fixture("impord_import_then_declare")
        assert use.impord_verdict is vocab.impord_verdict
        assert _solutions(use.impord_itd_check, 1) == [(mint("ok"),), (mint("no"),)]


class TestZeroArityAtomThenPredicate:
    """The shape ``tests/fixtures/impord_atom_then_pred.clausal`` pins: import
    a 0-arity vocabulary atom and then define a same-named predicate.

    P3-1 Task 2 fix round 1 (controller ruling, 2026-09-04): pre-pivot, the
    clause-head class block re-minted a class that a DOTTED owner-path
    reference (``tests.fixtures.impord_atomvocab.impord_qd``) also happened
    to reach — a quirk of class re-minting, never a contract. Post-pivot
    (§1b/R2, atoms are plain strs, no class to re-mint), the split was:
    (a) the re-defined predicate IS registered in the importing module's own
    database and fully callable by its bare LOCAL name; (b) a reference that
    goes through the dotted OWNER path found the owner's atom and calling it
    was a genuine error. That ruling deferred "routing a qualified goal to
    the local predicate" to P3-3's qualified-goal design.

    P3-3 Task 5b (controller ruling, 2026-09-06) is that routing, and it
    SUPERSEDES half (b): resolution is keyed on ``(name, arity)``, an atom
    has no arity-N meaning (ISO treats ``f`` and ``f/2`` as unrelated
    objects), so the APPLIED form reaches this file's own ``impord_qd/2``.
    Half (a) is unchanged, and the BARE form still means the imported atom —
    the two positions get different globals keys, which is the whole point.
    """

    def test_local_name_call_reaches_the_redefined_predicate(self):
        """(a) ``impord_qd`` by its bare local name is the re-minted /2
        predicate, registered in ``impord_atom_then_pred``'s own database —
        independent of whatever the module ATTRIBUTE ``impord_qd`` (the
        atom's own spelling, unaffected by the local redefinition) holds."""
        _load_fixture("impord_atomvocab")
        use = _load_fixture("impord_atom_then_pred")
        lm = use.__dict__["$module"]
        k, v = Var(), Var()
        results = sorted(
            (walk(deref(k)), walk(deref(v)))
            for _ in call("impord_qd", k, v, module=lm)
        )
        assert results == [(mint("a"), 1), (mint("b"), 2)]

    def test_the_applied_form_reaches_the_local_predicate(self):
        """(b), as P3-3 Task 5b re-decides it: ``impord_atp_lookup``'s body
        applies ``impord_qd`` at arity 2.  ``-import_from`` remapped that call
        to the FULL dotted name, and the owner never defines ``impord_qd`` as
        a functor at any arity — so the remap named an ATOM, which has no
        arity-2 meaning, while this file's own ``impord_qd/2`` does.  The
        local row answers.

        See ``tests/test_import_arity_resolution.py`` for the dedicated
        Task 5b pins, including the negative one (an imported FUNCTOR of
        arity N colliding with local arity-N clauses is untouched)."""
        _load_fixture("impord_atomvocab")
        use = _load_fixture("impord_atom_then_pred")
        lm = use.__dict__["$module"]
        k, v = Var(), Var()
        results = sorted(
            (walk(deref(k)), walk(deref(v)))
            for _ in call("impord_atp_lookup", k, v, module=lm)
        )
        assert results == [(mint("a"), 1), (mint("b"), 2)]


class TestALocalHeadAtANewArityLoadsBesideTheImport:
    """A head for an imported name at an arity the owner does not define
    builds the IMPORTER's own predicate at that arity.

    Re-pinned 2026-09-25 to the operator's name + arity ruling
    (2026-09-24: "a local p/2 beside an imported p/1 LOADS";
    ``predicate._foreign_head_verdict`` answers ``"local"``).  Until then
    this class was ``TestGenuineArityDisagreementStillRaises`` and pinned
    the owner's arity ``ClausalTermConstructionError``.  A genuine clash --
    a clause for the imported predicate at the OWNER's arity -- is still
    refused, attributably, by the load gate
    (``tests/test_heads_without_calling_binding_both_eras.py::
    test_a_head_naming_an_imported_predicate_reaches_the_gate``)."""

    def test_the_pair_loads_and_each_arity_answers_its_own_clauses(self):
        own = _load_fixture("impord_arity_vocab")
        use = _load_fixture("impord_arity_clash")        # no error
        lm = use.__dict__["$module"]
        om = own.__dict__["$module"]
        # the importer's own impord_narrow/2 answers its own clause
        s, c = Var(), Var()
        assert [(walk(deref(s)), walk(deref(c)))
                for _ in call("impord_narrow", s, c, module=lm)] == [("ok", [])]
        assert lm.db.head_signatures("impord_narrow")[2] == (
            "STATUS", "CITATIONS")
        # the owner is unchanged: one arity, its own clause ...
        assert om.db.head_signatures("impord_narrow") == {1: ("ONLY",)}
        x = Var()
        assert [walk(deref(x))
                for _ in call("impord_narrow", x, module=om)] == ["solo"]
        # ... and it still answers through the import at its own arity
        y = Var()
        assert [walk(deref(y))
                for _ in call("impord_narrow", y, module=lm)] == ["solo"]
