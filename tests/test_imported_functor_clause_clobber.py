"""A clause for an ``-import_from``'d functor must not destroy the exporter's.

``todo/done/imported-functor-clause-list-replaced-not-extended.md`` — a module that
imports a functor and then writes a clause for it used to **replace** the
shared predicate class's clause list rather than add to it::

    -module(exp, [colour(NAME)])          -module(ext, [colour(NAME)])
    colour(red),                          -import_from(exp, [colour])
    colour(green),                        colour(blue),

Merely importing ``ext`` deleted ``red`` and ``green`` — from queries the
*exporter* made, with no error and no warning.  Silent lost solutions, at a
distance, load-order dependent.

Why refuse rather than extend
-----------------------------
Extending cannot be made correct without a much larger change: the clause list
is not what answers a goal.  ``compile_module`` step 5 compiles a *single*
dispatch function from one module's clause list against **one** ``globals_``
mapping (``globals_=module_dict``), so a merged list would have to compile
clause bodies written in the exporter's scope — its ``-private`` atoms, its
imports — against the importer's globals.  A merged clause list with an
unmerged dispatch function would be a second silent wrong-answer bug wearing
the first one's clothes.

Why not give the importer its own predicate
-------------------------------------------
Because it would mean making dispatch per-module — ``_get_dispatch()`` is a
frozen duck-typed protocol with implementors outside this tree.

The clause-free case is refused too — since 2026-09-24
------------------------------------------------------
This refusal was once narrowed to functors that already have clauses, so that
the "vocabulary-implements" idiom (a module declares ``p/2`` and writes no
clauses; an importer supplies them, and everyone else imports the
declaration) kept working: nothing is destroyed there.  It only worked
because the load MOVED the shared class onto the implementer's row, which has
no form once a predicate binding is a mangled atom, so the operator DROPPED
the idiom (``todo/done/vocabulary-implements-steal-has-no-row-form-2026-09-24.md``).
That case is now its own load error with its own remedy (define it in the
implementing module, export it from there) —
``tests/test_vocabulary_implements_refused.py`` pins it, and
``TestDeclarationOnlyExporterIsRefused`` below keeps the fixtures' story.
The 2026-08-25 corpus sweep's live import-and-define shape — a 0-arity
vocabulary ATOM with a same-named predicate at another arity — is not this
idiom and still loads (``impord_atom_then_pred``).

And it must be accurate about ownership
---------------------------------------
``todo/done/imported-clause-refusal-misattributes-ownership.md``: an earlier attempt
read ``len(pred_cls._clauses)`` (the facade of the day) and credited them all to the module named in
the ``-import_from``.  Where a *previous importer* had implemented a
clause-free export, that blamed a module which had declared nothing — and,
because ownership was keyed on the module NAME, loading one file twice under
two names refused itself.  Ownership here is keyed on the SOURCE PATH of the
load that wrote the clauses, and the message names that module, not the
exporter.
"""

from __future__ import annotations

import os

import pytest

from clausal.logic.atoms import mint
import clausal.import_hook  # noqa: F401 — installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.exceptions import LogicException
from clausal.logic.predicate import resolve_predicate_row
from clausal.logic.solve import call, solve
from clausal.logic.variables import Var, deref, walk
from clausal.testing import load_clausal_module


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _fixture_path(stem: str) -> str:
    return os.path.join(FIXTURES, f"{stem}.clausal")


def _load_fixture(stem: str, as_name: str | None = None):
    return _load_module(as_name or f"tests.fixtures.{stem}", _fixture_path(stem))


def _solutions(pred_cls, arity: int):
    # THE FLIP: the answers are compared as TERMS.  ``str()`` used to
    # normalise a str-shaped atom for display; post-flip it would render the
    # arity-0 cell as its Python tuple repr, which compares against nothing.
    args = [Var() for _ in range(arity)]
    return [
        tuple(walk(deref(a)) for a in args)
        for _ in call(pred_cls, *args)
    ]


class TestExporterClausesSurvive:
    """The reproduction from the todo, as a regression test."""

    def test_redefining_a_defined_imported_functor_is_refused(self):
        _load_fixture("impclob_owner")
        with pytest.raises(SyntaxError) as exc_info:
            _load_fixture("impclob_redefine")
        msg = str(exc_info.value)
        assert "impclob_colour/1" in msg
        assert "impclob_owner" in msg
        assert "impclob_redefine" in msg

    def test_the_exporters_clauses_are_untouched_after_the_refusal(self):
        owner = _load_fixture("impclob_owner")
        assert sorted(_solutions(owner.impclob_colour, 1)) == [
            (mint("green"),), (mint("red"),)]
        with pytest.raises(SyntaxError):
            _load_fixture("impclob_redefine")
        # The whole point: the refusal must fire before anything is mutated.
        assert sorted(_solutions(owner.impclob_colour, 1)) == [
            (mint("green"),), (mint("red"),)]

    def test_the_refusal_says_what_to_do_instead(self):
        _load_fixture("impclob_owner")
        with pytest.raises(SyntaxError) as exc_info:
            _load_fixture("impclob_redefine")
        msg = str(exc_info.value)
        assert "->" in msg                 # house style: a remedy line
        assert "-import_from" in msg
        assert "2 clause" in msg           # the size of the hole

    def test_an_aliased_import_is_refused_too(self):
        """``-import_from(m, [alias(f, G)])`` binds the ALIAS, so ``G`` is the
        name a local clause head collides with.  Without this, reading the
        wrong element of the ``(orig, local)`` tuple in
        ``_import_from_origins`` would silently stop refusing and let the
        clobber back in — every other fixture here imports plainly."""
        owner = _load_fixture("impclob_owner")
        with pytest.raises(SyntaxError) as exc_info:
            _load_fixture("impclob_alias_redefine")
        msg = str(exc_info.value)
        # Named by the CLASS's own functor — what the clause actually compiles
        # against — not by the local alias spelling.
        assert "impclob_colour/1" in msg
        assert "impclob_owner" in msg
        # And, as ever, nothing was mutated on the way to the refusal.
        assert sorted(_solutions(owner.impclob_colour, 1)) == [
            (mint("green"),), (mint("red"),)]


class TestTheDiagnosticAttributesClausesCorrectly:
    """``todo/done/imported-clause-refusal-misattributes-ownership.md``.

    A second implementer is refused — the first implementer's clauses would be
    destroyed — and the message must credit the module that WROTE them.

    Until 2026-09-24 the first implementer supplied a clause-free vocabulary
    export downstream, so "the module that wrote them" and "the module named
    in the -import_from" differed and this pinned the difference.  That idiom
    is dropped; ``impclob_implements`` now DEFINES ``impclob_verdict/2`` and the
    rival imports it from there, which is exactly the migration the new
    refusal's remedy asks for.  The attribution still has to come from the
    ROW's source, and the declaration-only vocabulary must not be named.
    """

    def test_a_second_implementer_is_refused(self):
        _load_fixture("impclob_implements")
        with pytest.raises(SyntaxError) as exc_info:
            _load_fixture("impclob_implements_rival")
        assert "impclob_verdict/2" in str(exc_info.value)

    def test_the_message_credits_the_implementer_not_the_vocabulary(self):
        _load_fixture("impclob_decl_vocab")
        _load_fixture("impclob_implements")
        with pytest.raises(SyntaxError) as exc_info:
            _load_fixture("impclob_implements_rival")
        msg = str(exc_info.value)
        assert "that 1 clause is tests.fixtures.impclob_implements's own" in msg
        # It must NOT name the declaration-only vocabulary at all.
        assert "impclob_decl_vocab" not in msg
        # And it is the CLOBBER refusal, not the vocabulary-implements one.
        assert "only declares" not in msg

    def test_the_earlier_implementers_clauses_survive_the_refusal(self):
        use = _load_fixture("impclob_implements")
        with pytest.raises(SyntaxError):
            _load_fixture("impclob_implements_rival")
        assert _solutions(use.impclob_check, 1) == [(mint("ok"),)]


class TestDeclarationOnlyExporterIsRefused:
    """The "vocabulary-implements" idiom, DROPPED 2026-09-24 (operator ruling,
    ``todo/done/vocabulary-implements-steal-has-no-row-form-2026-09-24.md``).

    This class used to pin that the idiom LOADS: an importer supplied the
    clauses of ``impclob_decl_vocab``'s clause-free ``impclob_verdict/2`` and
    the vocabulary's own name then answered with them.  Now the importer is
    refused at load with a remedy, and the remedy's shape is what loads: the
    implementer defines and exports the predicate, users import it from there.
    """

    def test_implementing_a_clause_free_imported_functor_is_refused(self):
        vocab = _load_fixture("impclob_decl_vocab")
        with pytest.raises(SyntaxError) as exc_info:
            _load_fixture("impclob_implements_vocab")
        msg = " ".join(str(exc_info.value).split())
        assert ("tests.fixtures.impclob_decl_vocab only declares "
                "impclob_verdict/2") in msg
        assert "->" in msg                      # house style: a remedy line
        assert ("define impclob_verdict/2 in "
                "tests.fixtures.impclob_implements_vocab and export it") in msg
        # Nothing reached the vocabulary's predicate: it still has no row in
        # its own Database, and its binding reads no clauses.
        assert vocab.__dict__["$module"].db.row("impclob_verdict", 2) is None
        row = resolve_predicate_row(vocab.impclob_verdict, arity=2)
        assert row is None or not row.clauses

    def test_the_remedy_loads_and_its_users_see_the_clauses(self):
        impl = _load_fixture("impclob_implements")
        user = _load_fixture("impclob_verdict_user")
        assert _solutions(user.impclob_user_check, 1) == [(mint("ok"),)]
        assert _solutions(impl.impclob_verdict, 2) == [
            (mint("ok"), mint("cited"))]

    def test_reloading_the_implementer_is_idempotent(self):
        """A module's own clauses must not count as "someone else's" on a
        second load, or a reload would refuse itself."""
        _load_fixture("impclob_implements")
        use = _load_fixture("impclob_implements")  # again
        assert _solutions(use.impclob_check, 1) == [(mint("ok"),)]
        row = resolve_predicate_row(use.impclob_verdict, arity=2,
                                    db=use.__dict__["$module"].db)
        assert row is not None
        assert len(row.clauses) == 1


class TestOneFileLoadedTwiceUnderTwoNames:
    """``todo/done/imported-clause-refusal-misattributes-ownership.md``.

    ``clausal.testing.load_clausal_module`` compiles a file afresh under a
    private ``_clausal_test_*`` name, and a dotted ``-import_from`` of the same
    file compiles it under its dotted name.  Both routes are used across the
    suite, so one file legitimately reaches step 4 under two module names in
    one process.  Ownership must be keyed on the SOURCE, not the name.
    """

    def test_the_implementer_loads_under_two_different_module_names(self):
        # Since 2026-09-24 impclob_implements DEFINES impclob_verdict rather
        # than implementing a vocabulary import, so the two loads share no
        # predicate; this still pins that neither load refuses the other.
        a = _load_fixture("impclob_implements", as_name="_impclob_probe_a")
        b = _load_fixture("impclob_implements", as_name="_impclob_probe_b")
        assert _solutions(a.impclob_check, 1) == [(mint("ok"),)]
        assert _solutions(b.impclob_check, 1) == [(mint("ok"),)]

    def test_the_atom_vocabulary_shape_survives_both_load_routes(self):
        """``impord_atom_then_pred`` is the live corpus shape: import a
        0-arity vocabulary atom, then define a same-named predicate.
        Reached by both routes in the real suite -- so the property under
        test is that BOTH routes behave IDENTICALLY, not merely that both
        happen to succeed.

        P3-1 Task 2 fix round 1 (controller ruling, 2026-09-04): atoms are
        plain strs post-pivot (§1b/R2); there is no shared re-minted class
        left for a dotted owner-path reference to land on (that was a quirk
        of class re-minting, never a contract -- see
        ``tests/test_functor_import_ordering.py::TestZeroArityAtomThenPredicate``
        for the same split on the single-load-route sibling).  P3-3 Task 5b
        (controller ruling, 2026-09-06) then supplied the routing that ruling
        deferred: resolution is keyed on ``(name, arity)``, so the APPLIED
        form of the imported atom is this file's own ``impord_qd/2``.

        In EACH load route independently: the re-defined predicate is fully
        registered and callable by its bare LOCAL name (ownership keyed on
        source, not name, still holds), and the remapped call in
        ``impord_atp_lookup``'s body answers from the same local row -- the
        property under test being that the two routes agree, whatever the
        answer is.
        """
        dotted = _load_module(
            "tests.fixtures.impord_atom_then_pred",
            _fixture_path("impord_atom_then_pred"),
        )
        private = load_clausal_module(_fixture_path("impord_atom_then_pred"))

        for mod in (dotted, private):
            lm = mod.__dict__["$module"]

            k, v = Var(), Var()
            results = sorted(
                (walk(deref(k)), walk(deref(v)))
                for _ in call("impord_qd", k, v, module=lm)
            )
            assert results == [(mint("a"), 1), (mint("b"), 2)]

            k2, v2 = Var(), Var()
            lookup = sorted(
                (walk(deref(k2)), walk(deref(v2)))
                for _ in call("impord_atp_lookup", k2, v2, module=lm)
            )
            assert lookup == [(mint("a"), 1), (mint("b"), 2)]


class TestRuntimeAssertzIsAlreadySafe:
    """``todo/…-replaced-not-extended.md`` flagged this as unverified."""

    def test_assertz_against_an_imported_functor_raises(self, tmp_path):
        (tmp_path / "impclob_az.clausal").write_text(
            "-module(impclob_az, [go(X)])\n"
            "-import_from(tests.fixtures.impclob_owner, [impclob_colour])\n"
            "-private([blue])\n"
            "go(X_UNUSED) <- assertz(impclob_colour(blue))\n"
        )
        owner = _load_fixture("impclob_owner")
        az = _load_module("tests.fixtures.impclob_az",
                          str(tmp_path / "impclob_az.clausal"))
        with pytest.raises(LogicException) as exc_info:
            next(solve(("go", Var()), az), None)
        assert "permission_error" in str(exc_info.value)
        assert sorted(_solutions(owner.impclob_colour, 1)) == [
            (mint("green"),), (mint("red"),)]
