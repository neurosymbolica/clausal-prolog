"""The P1 category-A sites route to the Database row (spec 2026-09-17 §2.2).

Every test here drives a real ``.clausal`` load, so what it pins is the
BEHAVIOUR of a rerouted site, not the spelling of its line — the spelling is
``tools/predmeta_census/check_p1.py``'s business.

Three of the tests pin a site the pass deliberately LEFT on the class, because
the measured row answer is not the one the site asks for.  They are
regression guards for the next person who reads the census table and reaches
for ``db.row(functor, arity) is not None``.
"""
from __future__ import annotations

import pytest

from clausal import Var
from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import deref


def _write(tmp_path, name, src):
    p = tmp_path / f"{name}.clausal"
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


def test_a_dynamic_declaration_at_a_second_arity_keeps_the_size_two_set(tmp_path):
    """THE WART (spec §2): ``_dynamic_arities`` is a per-NAME set on the
    CLASS's own row, so both declarations land in ONE set."""
    mod = _load(tmp_path, "p1_dyn", "-dynamic(d/1)\n-dynamic(d/2)\nd(1),\n")
    cls = mod.module_dict["d"]
    assert cls._dynamic_arities == {1, 2}


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
    assert len(mod.module_dict["d"]._fields) == 1, "the NAME's class is d/1"


def test_the_ordinary_dynamic_predicate_still_answers(tmp_path):
    """The positive control for the same site: one declaration, one arity."""
    mod = _load(tmp_path, "p1_dyn4", "-dynamic(d/1)\nd(1),\n")
    cls = mod.module_dict["d"]
    assert cls._row.key == ("d", 1)
    assert _answers(mod, "d") == [1]


def test_a_clause_less_dynamic_predicate_still_compiles(tmp_path):
    """The positive control for the same site: a ``-dynamic`` predicate with
    no clauses must still reach step 5 and get its always-fail dispatch, so
    querying it fails with 0 solutions rather than raising."""
    mod = _load(tmp_path, "p1_dyn3", "-dynamic(e/1)\nq(1),\n")
    assert _answers(mod, "e") == []
    assert mod.module_dict["e"]._dynamic_arities == {1}


# ── -import_from: an adopted row answers every rerouted membership test ─────


def test_an_imported_predicate_passes_the_rerouted_membership_tests(
        tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    _write(tmp_path, "exp_p1", "-module(exp_p1, [p(X)])\np(1),\np(2),\n")
    _load_module("exp_p1", str(tmp_path / "exp_p1.clausal"))
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
    assert "zonkish" not in msg, "a class with no row is not a row"


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
    owner = _load_module("p1_own", str(tmp_path / "p1_own.clausal"))
    mod = _load(tmp_path, "p1_use",
                "-import_from(p1_own, [op_p])\np1_use_q(X) <- op_p(X),\n")
    owner_db = owner.__dict__["$module"].db
    assert mod.db.row("op_p", 1) is owner_db.row("op_p", 1)
    assert _answers(mod, "p1_use_q") == [1]


# ── clausal/testing.py: _note_generic_compound_confusion ───────────────────


GENERIC_COMPOUND_SRC = '''\
-dynamic(cite/1)

make(T) <- (
    T is ++(__import__("clausal.terms", fromlist=["Compound"]).Compound("cite", (1,)))
),

test("citation term mismatch") <- (
    make(T2),
    T2 is cite(_)
),
'''


def test_the_generic_compound_note_fires_for_a_row_backed_functor(tmp_path,
                                                                  capsys):
    """``cite/1`` is a class AND a row here (``-dynamic`` mints the row), so
    the rerouted declaredness test still names the confusion."""
    from clausal.testing import main

    p = _write(tmp_path, "p1_note", GENERIC_COMPOUND_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "generic compound" in out
    assert "cite/1" in out


# ── the sites this pass LEFT, with the measurement that left them ──────────


def test_a_directive_target_declared_without_clauses_still_loads(tmp_path):
    """compiler_v2 ``_validate_directive_targets`` stays on the class.

    A predicate declared here and given no clauses has a class in the module
    dict and NO ROW, so ``db.row(functor, arity) is not None`` would REFUSE
    this load — which the function's own docstring promises to accept.
    """
    mod = _load(tmp_path, "p1_disc",
                "-private([zonkish(X, Y)])\n-discontiguous(zonkish/2)\nq(1),\n")
    assert mod.db.row("zonkish", 2) is None
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
    _load_module("p1_atomexp", str(tmp_path / "p1_atomexp.clausal"))
    mod = _load(tmp_path, "p1_atomuse",
                "-import_from(p1_atomexp, [shared_name])\n"
                "shared_name(1),\n")
    # The load survived: the clause block got its predicate whatever the
    # import had already bound under the name.
    assert _answers(mod, "shared_name") == [1]
