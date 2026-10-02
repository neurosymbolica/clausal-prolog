"""``-import_from`` resolution is keyed on ``(name, arity)``, not on the name.

P3-3 Task 5b.  After the P3-1 atom pivot (atoms are plain ``str``; a spelling
that also carries 0-arity clauses binds to a ``PredicateMeta`` class) the
``-import_from`` lowering keyed on the NAME alone, and two shapes conflated an
imported atom with something else:

**Sub-shape 1 — imported ATOM + local arity-N definition.**  The importer
``-import_from``s a 0-arity atom and also defines ``name/N`` itself.  Every
applied ``name(...)`` went through the import remap to the owner's atom — a
``str`` post-pivot — and died in ``predicate._dispatch_at``'s str branch with
``existence_error(procedure, name/N)``, while the importer's own ``name/N`` row
sat right there unconsulted.  An atom has no arity-N meaning (ISO treats ``f``
and ``f/2`` as unrelated objects), so the local definition wins and nothing is
shadowed.  The BARE form keeps meaning the imported atom.

**Sub-shape 2 — imported declared atom that also has /0 clauses.**  The owner
declares a key in its ``-module`` list AND writes ``key,`` as a fact, so its
binding is the predicate class.  The owner's own lowering still writes the
``str`` into its dicts (its ``-module`` list is in front of it); the importer
trusted the copied binding and passed the CLASS as a dict key, missing a
present key silently.  A name the owner DECLARES as an atom is the atom str in
data position in the importer too; in goal position it is still the owner's /0
predicate.

**Negative pin.**  An imported FUNCTOR of arity N colliding with local arity-N
clauses is a genuine collision and is untouched here.
"""

from __future__ import annotations

import os

import pytest

from clausal.logic.atoms import mint
import clausal.import_hook  # noqa: F401 — installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref, walk
from tests._suffix import seam_path


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_fixture(stem: str):
    return _load_module(
        f"tests.fixtures.{stem}", seam_path(os.path.join(FIXTURES, f"{stem}.clausal"))
    )


def _solutions(pred_cls, arity: int):
    """Every solution of *pred_cls* as a tuple of walked bindings."""
    args = [Var() for _ in range(arity)]
    return [
        tuple(walk(deref(a)) for a in args)
        for _ in call(pred_cls, *args)
    ]


class TestImportedAtomWithLocalArityNPredicate:
    """Sub-shape 1: ``tests/fixtures/t5b_atom_vocab`` +
    ``tests/fixtures/t5b_local_pred``."""

    @pytest.fixture(autouse=True)
    def _modules(self):
        self.vocab = _load_fixture("t5b_atom_vocab")
        self.use = _load_fixture("t5b_local_pred")

    def test_the_applied_form_reaches_the_local_row(self):
        """``t5b_slot(t5b_a, V)`` in the importer is the importer's own
        ``t5b_slot/2``, not the owner's atom.  The call site sits ABOVE the
        clauses that establish the local functor, so the decision cannot
        depend on statement order."""
        assert _solutions(self.use.t5b_go, 1) == [(2,)]

    def test_every_local_clause_answers_through_the_rerouted_site(self):
        assert _solutions(self.use.t5b_all, 2) == [(mint("t5b_a"), 2), (mint("t5b_b"), 3)]

    def test_the_bare_form_in_a_head_stays_the_imported_atom(self):
        (value,), = _solutions(self.use.t5b_head_data, 1)
        assert value == mint("t5b_slot")
        assert type(value) is str   # STAGE 2: an atom is the str

    def test_the_bare_form_in_a_body_stays_the_imported_atom(self):
        """The two positions get DIFFERENT globals keys — the applied form is
        re-pointed at the local name, the bare form keeps the dotted import
        key — so one file can mean both with the same spelling."""
        (value,), = _solutions(self.use.t5b_body_data, 1)
        assert value == mint("t5b_slot")
        assert type(value) is str   # STAGE 2: an atom is the str

    def test_a_genuinely_imported_predicate_still_reaches_its_owner(self):
        """``t5b_other/1`` carries a functor signature in the owner and has no
        local definition, so it is untouched by the reroute."""
        assert _solutions(self.use.t5b_other_call, 1) == [(1,)]

    def test_the_module_attribute_is_unchanged(self):
        """The Python ``getattr`` surface is out of scope: the imported atom
        is what the attribute holds, exactly as before."""
        assert self.use.t5b_slot == mint("t5b_slot")
        assert type(self.use.t5b_slot) is str   # STAGE 2: an atom is the str


class TestImportedFunctorCollisionIsUnchanged:
    """Sub-shape 1's negative pin: imported FUNCTOR of arity N + local
    arity-N clauses.  A genuine collision, out of scope for Task 5b — pinned
    exactly as it behaves, which is a load-time refusal from the mutation
    gate (``tests/fixtures/t5b_functor_clash``)."""

    def test_the_load_is_refused_with_the_one_defining_module_message(self):
        _load_fixture("t5b_functor_vocab")
        with pytest.raises(SyntaxError) as exc_info:
            _load_fixture("t5b_functor_clash")
        message = str(exc_info.value)
        assert "t5b_pair/2" in message
        assert "-import_from" in message
        assert "no -multifile" in message
        assert "may not write t5b_pair/2" in message
        # Same key on both sides here, so the refusal says it once: the
        # attempted-key clause (M-e) appears only when they differ.
        assert "reached by writing" not in message


class TestALocalPredicateAtAnotherArityLoads:
    """Was ``TestBlastRadiusRefusalNamesTheAttemptedKey`` (final review M-e):
    the importer writes ``t5b_kfact/2`` of its own beside the owner's
    imported dual-declared ``t5b_kfact`` (a /0 fact).  In the class era the
    shared class put the owner's ``/0`` row in the write's blast radius and
    the load was refused ("may not write t5b_kfact/0 (reached by writing
    t5b_kfact/2)"); in the handle era ``through=`` resolves at the written
    arity and the same load succeeded.

    Operator ruling 2026-09-24: a local ``p/2`` beside an imported ``p/1``
    LOADS, in BOTH eras -- name and arity make a different predicate
    (``todo/done/imported-class-at-another-arity-blast-radius-is-class-era-only-2026-09-24.md``).
    Fixture: ``tests/fixtures/t5b_dual_arity_clash``."""

    @pytest.mark.parametrize("era", ["class", "mangled"])
    def test_it_loads_answers_and_leaves_the_owner_alone(self, era,
                                                         monkeypatch):
        import sys
        import clausal.logic.compiler_v2 as cv2
        from clausal.logic.atoms import mangle
        from clausal.logic.solve import solve
        from clausal.logic.variables import Var, deref, walk

        owner = _load_fixture("t5b_dual_owner")
        owner_db = owner.__dict__["$module"].db
        owner_clauses = list(owner_db.row("t5b_kfact", 0).clauses)
        assert owner_clauses, "the owner's /0 fact is the shape under test"
        owner_source = owner_db.row("t5b_kfact", 0).source

        use_name = "tests.fixtures.t5b_dual_arity_clash"
        if era == "mangled":
            original = cv2._refuse_foreign_writes
            rebound = []

            def refuse(db, nodes, module_dict, origins, author, module_name):
                if module_name == use_name:
                    handle = mangle("tests.fixtures.t5b_dual_owner",
                                    "t5b_kfact")
                    module_dict["t5b_kfact"] = handle
                    origins["t5b_kfact"] = ("tests.fixtures.t5b_dual_owner",
                                            handle)
                    rebound.append(module_name)
                return original(db, nodes, module_dict, origins, author,
                                module_name)

            monkeypatch.setattr(cv2, "_refuse_foreign_writes", refuse)
        try:
            use = _load_fixture("t5b_dual_arity_clash")
        finally:
            sys.modules.pop(use_name, None)
        if era == "mangled":
            assert rebound == [use_name], "the handle-era rebinding never ran"

        lm = use.__dict__["$module"]

        def answers(gen, a, b):
            return [(walk(deref(a)), walk(deref(b))) for _ in gen]

        # Every route to the importer's own t5b_kfact/2: an outside query, a
        # solve.call by name, a body goal inside the importer (t5b_dac_go),
        # and a meta-call (call/3) by name.
        a, b = Var(), Var()
        assert answers(solve(("t5b_kfact", a, b), lm), a, b) == [(1, 2)]
        a, b = Var(), Var()
        assert answers(call("t5b_kfact", a, b, module=lm), a, b) == [(1, 2)]
        a, b = Var(), Var()
        assert answers(call("t5b_dac_go", a, b, module=lm), a, b) == [(1, 2)]
        a, b = Var(), Var()
        assert answers(solve(("call", mint("t5b_kfact"), a, b), lm),
                       a, b) == [(1, 2)]
        assert lm.db.row("t5b_kfact", 2).db is lm.db
        # The owner's /0: same clause, same owner.
        assert owner_db.row("t5b_kfact", 0).clauses == owner_clauses
        assert owner_db.row("t5b_kfact", 0).source == owner_source


class TestImportedDeclaredAtomWithZeroArityClauses:
    """Sub-shape 2: ``tests/fixtures/t5b_dual_owner`` +
    ``tests/fixtures/t5b_dual_importer``."""

    @pytest.fixture(autouse=True)
    def _modules(self):
        self.owner = _load_fixture("t5b_dual_owner")
        self.use = _load_fixture("t5b_dual_importer")

    def test_the_owner_binds_the_dual_declared_name_to_its_predicate(self):
        """The precondition this task is about: the /0 clause block wins the
        owner's binding, so the declaration alone no longer shows in it.
        (W4b-2d: the binding is the predicate's HANDLE, resolving to the
        owner's /0 row; it was the class.)"""
        from clausal.logic.predicate import (
            mint_predicate_handle, resolve_predicate_row,
        )
        owner_db = self.owner.__dict__["$module"].db
        binding = self.owner.t5b_kfact
        assert binding == mint_predicate_handle(owner_db, "t5b_kfact")
        row = resolve_predicate_row(binding, arity=0, db=owner_db)
        assert row is owner_db.row("t5b_kfact", 0) and row.clauses
        assert self.owner.t5b_kplain == mint("t5b_kplain")

    def test_the_owners_own_read_answers(self):
        """The control: the owner's lowering always wrote the str."""
        assert _solutions(self.owner.t5b_owner_read, 1) == [(1,)]

    def test_the_importer_reads_the_dual_declared_key(self):
        """Was ``[]`` — a silent miss on a present key, the CLASS used where
        the dict holds a ``str``."""
        assert _solutions(self.use.t5b_iread_fact, 1) == [(1,)]

    def test_the_importer_reads_the_plain_declared_key(self):
        """The control key, declared with no /0 clause: green before and
        after."""
        assert _solutions(self.use.t5b_iread_plain, 1) == [(2,)]

    def test_the_importer_reads_through_the_owners_own_predicate(self):
        assert _solutions(self.use.t5b_iread_pass, 1) == [(1,)]

    def test_the_key_is_the_plain_str_in_a_body_argument(self):
        """Driven with a Python dict whose key is the plain spelling: only a
        ``str`` lowering can find it."""
        value = Var()
        assert [
            deref(value)
            for _ in call(self.use.t5b_ikey, {mint("t5b_kfact"): 7}, value)
        ] == [7]

    def test_the_key_is_the_plain_str_in_a_head_argument(self):
        (value,), = _solutions(self.use.t5b_ihead, 1)
        assert value == mint("t5b_kfact")
        assert type(value) is str   # STAGE 2: an atom is the str

    def test_goal_position_still_runs_the_owners_zero_arity_predicate(self):
        """``call(t5b_kfact)`` from the importer resolves ``(t5b_kfact, 0)``
        through the calling module's namespace onto the OWNER's row (P3-3
        Task 5's ``_namespace_dispatch``)."""
        assert len(list(call(self.use.t5b_icall))) == 1

    def test_the_module_attribute_is_unchanged(self):
        """Out of scope, and unchanged: the Clausal-level data reference is
        the atom, while ``mod.t5b_kfact`` from Python is still the owner's
        /0 predicate -- its handle post-W4b-2d (the class before)."""
        from clausal.logic.atoms import is_mangled
        assert is_mangled(self.use.t5b_kfact)
        assert self.use.t5b_kfact == self.owner.t5b_kfact
