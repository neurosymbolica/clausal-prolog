"""The P1 category-A sites route to the Database row (spec 2026-09-17 §2.2).

Every test here drives a real ``.clausal`` load, so what it pins is the
BEHAVIOUR of a rerouted site, not the spelling of its line — the spelling
was ``tools/predmeta_census/check_p1.py``'s business (deleted 2026-09-26 with
the other PredicateMeta census tools; it is in the git history).

Three of the tests pin a site the pass deliberately LEFT on the class, because
the measured row answer is not the one the site asks for.  They are
regression guards for the next person who reads the census table and reaches
for ``db.row(functor, arity) is not None``.
"""
from __future__ import annotations

import pytest

from clausal import Var
from clausal.import_hook import _load_module
from clausal.logic.atoms import is_atom
from clausal.logic.solve import call
from clausal.logic.variables import deref
from tests._suffix import SEAM


def _write(tmp_path, name, src):
    p = tmp_path / f"{name}{SEAM}"
    p.write_text(src)
    return p


def _load(tmp_path, name, src):
    """Load *src* as a module and return its ``$module`` handle."""
    return _load_module(name, str(_write(tmp_path, name, src))).__dict__["$module"]


def _answers(module, functor):
    x = Var()
    return sorted(deref(x) for _ in call(functor, x, module=module))


# ── clausal/logic/compiler/globals_env.py: _GlobalsDb.signature_for ─────────


def test_signature_for_answers_from_the_row(tmp_path):
    from clausal.logic.compiler.globals_env import _GlobalsDb

    mod = _load(tmp_path, "p1_sig", "p(1, 2),\n")
    row = mod.db.row("p", 2)
    assert row is not None and row.signature is not None
    env = _GlobalsDb(mod.module_dict)
    assert env.signature_for("p", 2) == row.signature


def test_signature_for_is_arity_exact(tmp_path):
    """The shim took ``arity`` and ignored it; the row is keyed by it."""
    from clausal.logic.compiler.globals_env import _GlobalsDb

    mod = _load(tmp_path, "p1_sig2", "p(1, 2),\n")
    env = _GlobalsDb(mod.module_dict)
    assert env.signature_for("p", 3) is None
    assert env.signature_for("nope", 2) is None


def test_signature_for_answers_None_without_a_module_handle():
    """A hand-built globals dict carries no ``$module`` — and no signatures."""
    from clausal.logic.compiler.globals_env import _GlobalsDb

    assert _GlobalsDb({}).signature_for("p", 2) is None


# ── clausal/logic/compiler_v2.py step 4a: the -dynamic sites ────────────────


def test_a_dynamic_declaration_at_a_second_arity_records_both(tmp_path):
    """Both declarations are recorded, and the per-NAME set has both arities.

    THE WART IS GONE (option D, 2026-09-22): the set used to be stamped onto
    the CLASS's own row, which is what made it a per-NAME set living on a
    per-(name, arity) row.  It is derived from the Database now, so this
    asserts the DECLARATIONS rather than the stamp.
    """
    mod = _load(tmp_path, "p1_dyn", "-dynamic(d/1)\n-dynamic(d/2)\nd(1),\n")
    db = mod.module_dict["$module"].db
    assert db.is_dynamic("d", 1) and db.is_dynamic("d", 2)
    assert {a for (f, a) in db._dynamic if f == "d"} == {1, 2}


def test_the_declared_arity_row_already_exists_when_step_4a_looks(tmp_path):
    """Why step 4a asks the CLASS's row rather than ``db.row(functor, arity)``.

    Step 2's ``mark_dynamic`` puts every declared ``(functor, arity)`` into the
    database, so by the time step 4a runs, ``db.row(functor, arity) is not
    None`` is TRUE for every spec it sees — vacuous as a membership test.  The
    branch it guards calls ``_bind_row(db, functor, arity)``, so the vacuous
    answer would hand ``d/1``'s class to ``d/2``'s row.  The class's own row
    answers with the arity the class actually has.

    (Loading this shape at all is a separate, PRE-EXISTING defect: a
    ``-dynamic`` declaration at an arity the name's class does not have ends
    with the class on the wrong row anyway, via ``compiler/predicate.py``'s
    resolve-by-name — a P4 row, out of P1's scope.  This test asserts only
    what step 4a can see.)
    """
    mod = _load(tmp_path, "p1_dyn2", "-dynamic(d/1)\n-dynamic(d/2)\nd(1),\n")
    assert mod.db.row("d", 2) is not None, "the vacuous test this site avoids"
    assert mod.db.row("d", 1) is not None
    # Post-W4b-2d the NAME's binding is a handle, which carries no arity of
    # its own (it was d/1's class, whose ``_fields`` said 1): nothing can be
    # handed to the wrong row.  What the site protected is observable on the
    # rows themselves -- d/1 holds the clause, d/2 holds nothing.
    from clausal.logic.predicate import mint_predicate_handle
    assert mod.module_dict["d"] == mint_predicate_handle(mod.db, "d")
    assert len(mod.db.row("d", 1).clauses) == 1
    assert not mod.db.row("d", 2).clauses


def test_the_ordinary_dynamic_predicate_still_answers(tmp_path):
    """The positive control for the same site: one declaration, one arity."""
    mod = _load(tmp_path, "p1_dyn4", "-dynamic(d/1)\nd(1),\n")
    from clausal.logic.predicate import resolve_predicate_row
    row = resolve_predicate_row(mod.module_dict["d"], arity=1, db=mod.db)
    assert row is not None and row.key == ("d", 1)
    assert _answers(mod, "d") == [1]


def test_a_clause_less_dynamic_predicate_still_compiles(tmp_path):
    """The positive control for the same site: a ``-dynamic`` predicate with
    no clauses must still reach step 5 and get its always-fail dispatch, so
    querying it fails with 0 solutions rather than raising."""
    mod = _load(tmp_path, "p1_dyn3", "-dynamic(e/1)\nq(1),\n")
    assert _answers(mod, "e") == []
    # The DECLARATION, not the class stamp (option D, 2026-09-22).
    assert mod.module_dict["$module"].db.is_dynamic("e", 1)


# ── -import_from: an adopted row answers every rerouted membership test ─────


def test_an_imported_predicate_passes_the_rerouted_membership_tests(
        tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    _write(tmp_path, "exp_p1", "-module(exp_p1, [p(X)])\np(1),\np(2),\n")
    _load_module("exp_p1", str(tmp_path / f"exp_p1{SEAM}"))
    mod = _load(tmp_path, "imp_p1",
                "-import_from(exp_p1, [p])\nq(X) <- p(X),\n")
    assert _answers(mod, "q") == [1, 2]


# ── clausal/logic/compiler_v2.py _run_specialization: the enumeration ───────


def test_the_specialize_diagnostic_lists_rows_not_classes(tmp_path):
    """The available-predicate list is the Database's rows.

    ``zonkish/2`` is declared and given no clauses, so it is a class in the
    module dict with NO row — the discriminator between the two enumerations.
    """
    src = ("-private([zonkish(X, Y)])\n"
           "-discontiguous(zonkish/2)\n"
           "prog(P) <- (P is [1]),\n"
           "-specialize(nosuch_mi, prog, alias=zz)\n"
           "realpred(1),\n")
    with pytest.raises(RuntimeError) as exc:
        _load(tmp_path, "p1_spec", src)
    msg = str(exc.value)
    assert "nosuch_mi" in msg
    assert "'realpred'" in msg and "'prog'" in msg
    # P4 prerequisite (2026-09-18): a DECLARATION creates its row, so the
    # declared, clause-less zonkish/2 is one of the rows and is listed.
    assert "zonkish" in msg, "a declared predicate has a row and is listed"


# ── clausal/logic/builtins/database_ops.py: _find_pred_cls ─────────────────


def test_a_local_assert_lands_on_this_module_s_own_row(tmp_path):
    """The non-redirect leg: the module's spelling names the row the head's
    own class reads, so the write stays here."""
    mod = _load(tmp_path, "p1_loc",
                "-dynamic(lp/1)\nadd_lp(X) <- assertz(lp(X)),\n")
    next(call("add_lp", 7, module=mod), None)
    row = mod.db.row("lp", 1)
    assert row is not None and len(row.clauses) == 1
    assert _answers(mod, "lp") == [7]


def test_a_class_in_the_module_dict_without_a_local_row_still_resolves(
        tmp_path, monkeypatch):
    """The CLASS FALLBACK the row lookup keeps (review round 1).

    A predicate class reached by a plain Python import — bound into the
    importer's module dict, with no ``-import_from`` and therefore no adopted
    row — is at the right arity under the right spelling and has NO row in
    this Database.  ``db.row(functor, arity)`` cannot see it, so
    ``_find_pred_cls`` falls back to the class, exactly as it did before the
    reroute, and ``listing(pp/1)`` keeps working through
    ``io._row_for_indicator``'s third leg.

    Same class-without-a-row shape that left compiler_v2 851/882 on the class.
    """
    import io as _io
    import sys as _sys

    from clausal.logic.atoms import mint
    from clausal.logic.builtins import get_builtin_dispatch
    from clausal.logic.trampoline import StepGenerator, solutions
    from clausal.logic.variables import Trail

    monkeypatch.syspath_prepend(str(tmp_path))
    _write(tmp_path, "p1_pex", "-module(p1_pex, [pp(X)])\n\npp(1),\n")
    exporter = _load_module("p1_pex", str(tmp_path / f"p1_pex{SEAM}"))
    mod = _load(tmp_path, "p1_pim", "other(1),\n")
    # What ``from p1_pex import pp`` leaves behind: the class, no row.
    mod.module_dict["pp"] = exporter.__dict__["pp"]
    assert mod.db.row("pp", 1) is None

    dispatch = get_builtin_dispatch("listing", 1, mod.db)
    trail, buf, old = Trail(), _io.StringIO(), _sys.stdout
    _sys.stdout = buf
    try:
        solutions(StepGenerator(dispatch, None, None, None,
                                ("/", mint("pp"), 1), trail))
    finally:
        _sys.stdout = old
    out = buf.getvalue()
    assert "pp/1" in out
    assert "1 clause(s)" in out


def test_an_imported_predicate_is_reached_through_the_adopted_row(tmp_path,
                                                                  monkeypatch):
    """The other leg of the same lookup: an ``-import_from``'d name resolves
    because the importer's Database ADOPTED the exporter's row, so the
    rerouted ``db.row(functor, arity)`` finds the very same object the
    exporter owns — the fact the whole reroute rests on.

    The REDIRECT leg (an aliased import, where the canonical functor names no
    row here and the head's own class settles it) is pinned by
    ``tests/test_mutation_gate.py::test_an_aliased_import_asserts_ON_ITS_OWNER``.
    """
    monkeypatch.syspath_prepend(str(tmp_path))
    _write(tmp_path, "p1_own", "-module(p1_own, [op_p(X)])\n\nop_p(1),\n")
    owner = _load_module("p1_own", str(tmp_path / f"p1_own{SEAM}"))
    mod = _load(tmp_path, "p1_use",
                "-import_from(p1_own, [op_p])\np1_use_q(X) <- op_p(X),\n")
    owner_db = owner.__dict__["$module"].db
    assert mod.db.row("op_p", 1) is owner_db.row("op_p", 1)
    assert _answers(mod, "p1_use_q") == [1]


# ── the sites this pass LEFT, with the measurement that left them ──────────


def test_a_directive_target_declared_without_clauses_still_loads(tmp_path):
    """compiler_v2 ``_validate_directive_targets`` stays on the class.

    A predicate declared here and given no clauses has a class in the module
    dict and NO ROW, so ``db.row(functor, arity) is not None`` would REFUSE
    this load — which the function's own docstring promises to accept.
    """
    mod = _load(tmp_path, "p1_disc",
                "-private([zonkish(X, Y)])\n-discontiguous(zonkish/2)\nq(1),\n")
    # P4 prerequisite (2026-09-18): the declaration created the row, and
    # _validate_directive_targets accepts the target through it; the class
    # fallback remains only for a class with no row (a plain Python import).
    assert mod.db.row("zonkish", 2) is not None
    assert _answers(mod, "q") == [1]


def test_an_untablable_target_names_the_shape_it_found(tmp_path):
    """compiler_v2 ``_refuse_untablable_target`` stays on the class: its
    ``is_pred`` chooses BETWEEN refusals, and a declared clause-less predicate
    has no row to choose from."""
    src = "-private([zonkish(X, Y)])\n-table(zonkish/2)\nq(1),\n"
    with pytest.raises(SyntaxError) as exc:
        _load(tmp_path, "p1_table", src)
    assert "no clauses in this module" in str(exc.value)


def test_a_clause_block_may_find_a_non_class_under_its_own_name(tmp_path,
                                                               monkeypatch):
    """compiler_v2 step 4's ``isinstance`` guard stays: measured over the
    suite, 34 of 14,615 arrivals find a non-class binding (an interned atom
    tuple, or nothing) under a functor that has clause nodes — and the branch
    it guards calls ``_bind_row`` on whatever it found."""
    monkeypatch.syspath_prepend(str(tmp_path))
    _write(tmp_path, "p1_atomexp", "-module(p1_atomexp, [shared_name])\n")
    _load_module("p1_atomexp", str(tmp_path / f"p1_atomexp{SEAM}"))
    mod = _load(tmp_path, "p1_atomuse",
                "-import_from(p1_atomexp, [shared_name])\n"
                "shared_name(1),\n")
    # THE POINT: what the import left under the name is the interned atom
    # TUPLE, not a predicate class, and step 4 looked the name up in this very
    # dict.  Dropping the guard hands this tuple to ``_bind_row``.
    binding = mod.module_dict["shared_name"]
    assert is_atom(binding), type(binding)
    assert not isinstance(binding, type)
    # And the load survived: the clause block got its own predicate anyway.
    assert _answers(mod, "shared_name") == [1]


def test_the_specialize_diagnostic_names_the_population_it_lists(tmp_path):
    """Final review minor 5 + roborev L6, 2026-09-17.

    Two defects in one line.  The wording said "not found in module dict"
    while listing the DATABASE's predicates, so a reader chasing a missing
    name looked in the wrong place.  And the list was built from ``db._rows``
    ∪ ``db._adopted``, where ``_rows`` is LAZILY materialised: the two
    enumerations answer the same question and only one of them scans every
    container ``row()``'s ``known`` test consults.  It now goes through
    ``Database.functors()``, the same containers ``arities_for`` scans plus
    ``_adopted``.

    MEASURED: no ordinary LOAD distinguishes the two here -- a ``-dynamic``
    declaration's row is materialised at step 4a, so ``'ghost'`` below is a
    CONTROL that passed before this change too.  The difference is pinned
    directly on the accessor in the next test, where a key is marked dynamic
    without anyone asking for its row.  This is a robustness fix, and it is
    recorded as one.
    """
    src = ("-dynamic(ghost/1)\n"
           "prog(P) <- (P is [1]),\n"
           "-specialize(nosuch_mi, prog, alias=zz)\n"
           "realpred(1),\n")
    with pytest.raises(RuntimeError) as exc:
        _load(tmp_path, "p1_spec2", src)
    msg = str(exc.value)
    assert "no predicate of that name in this module's database" in msg, msg
    assert "'ghost'" in msg, (
        "a clause-less -dynamic name is known to this database and its row "
        f"is merely unmaterialised — got {msg}")
    assert "'realpred'" in msg and "'prog'" in msg


def test_functors_scans_every_container_row_consults(tmp_path):
    """``Database.functors()`` is the functor-only twin of ``arities_for``:
    same containers, plus the rows this database ADOPTED at ``-import_from``
    (which answer reads here under this module's own spelling)."""
    mod = _load(tmp_path, "p1_fn", "-dynamic(ghost/1)\nreal(1),\n")
    functors = mod.db.functors()
    assert functors == sorted(functors), "sorted, so a diagnostic can print it"
    assert "real" in functors and "ghost" in functors
    # every name it lists is a name this database knows at some arity
    for f in functors:
        assert mod.db.arities_for(f) or f in {
            k for (k, _a) in mod.db._adopted}, f

    # THE DIFFERENCE, pinned where a load cannot show it: a key known only
    # through a container whose row nobody has materialised.
    from clausal.logic.database import Database
    bare = Database()
    bare.mark_dynamic("late", 1)
    assert "late" not in {f for (f, _a) in (*bare._rows, *bare._adopted)}, (
        "the old enumeration's population")
    assert bare.functors() == ["late"]
