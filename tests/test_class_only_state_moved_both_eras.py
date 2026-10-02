"""W4b-2d R6: state that lived ONLY on a ``PredicateMeta`` class, moved onto
the Database / row, answered the same whether a module-dict binding is still
the CLASS or already the owner's mangled HANDLE.

The flip dry run (``implementation_plans/w4b2d-flip-dry-run-2026-09-24.md``
§2 R6, §3.4) found four class stashes outside the migrated worklist, each of
which failed SILENTLY once the binding was a handle:

* ``_tabled_home_db`` -- the cross-module WFS answer became ``[]`` where it is
  ``Undefined``; moving only the compile-time read made it ``[True]``.  Both
  reads now go through ``predicate.tabled_home_of`` (the binding's ROW).
  ``solve._tabled_call_site`` read ``__module__`` for the same question; it
  asks ``predicate_owner_module`` now.
* ``_te_predicate_nodes`` -- imported ``term_expansion`` rules vanished.  They
  live on the provider's ``Database.te_predicate_nodes`` now.
* ``_refuse_untablable_target`` read ``cls._row``/``cls.__module__``.
* ``_registered_at`` -- the arity-mismatch "defined at" line.  The site is on
  the row (``PredRow.declared_at``) now, for the handle arms.

Handle era (W4b-2d flip): the LOAD binds the OWNER's handle now (ruling
D1, ``mint_predicate_handle(owner_db, name)``), so the class arm, the
stand-in ``_flip`` and the stand-in ``_flip_all_bindings`` /
``flipped_loads`` load-time flip are gone -- after the flip each found no
class and flipped nothing.  Every test asserts the handle binding it
depends on instead.  Reads of class-only state (``_registered_at``, the
``_tabled_home_db`` stamp) became reads of where that state lives now.
"""

from __future__ import annotations

import os
import sys

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.predicate import mint_predicate_handle
from clausal.logic.solve import query_wfs
from clausal.logic.variables import Trail, Var, unify
from clausal.terms import Call as TermCall, LoadName, Undefined
from tests._suffix import SEAM

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _lm(mod):
    return mod.__dict__["$module"]


def _assert_owner_handle(user_mod, name, owner_mod):
    """The LOAD bound *name* in *user_mod* to the owner's handle (ruling
    D1).  Asserted, never set."""
    md = user_mod.__dict__
    assert md[name] == mint_predicate_handle(_lm(owner_mod).db, name), (
        f"the load did not bind {name} to the owner's handle")
    assert type(md[name]) is str


def _goal(name, *args):
    return TermCall(func=LoadName(name=name), args=list(args), kwargs=[])


def _truths(lm, name, val):
    Y = Var()
    t = Trail()
    unify(Y, val, t)
    return [r["_truth"] for r in query_wfs(_goal(name, Y), {}, lm, t)]


# ── _tabled_home_db: the cross-module tabled-NAF home ────────────────────────

_SYM_LIB = """-module({name}, [win(X)])
-table(win/1)

move(1, 2),
move(2, 1),

win(X) <- (move(X, Y), not win(Y))
"""

_ASYM_LIB = """-module({name}, [win(X)])
-table(win/1)

move(1, 2),
move(2, 3),

win(X) <- (move(X, Y), not win(Y))
"""

_USE = """-import_from({lib}, [win])
-table(res/1)

res(X) <- (not win(X))
"""

_COUNTER = [0]


@pytest.fixture
def xm_pair(tmp_path):
    loaded = []

    def load(lib_src):
        _COUNTER[0] += 1
        n = _COUNTER[0]
        lib_name = f"r6_xmnaf_lib_{os.getpid()}_{n}"
        use_name = f"r6_xmnaf_use_{os.getpid()}_{n}"
        (tmp_path / f"{lib_name}{SEAM}").write_text(lib_src.format(name=lib_name))
        (tmp_path / f"{use_name}{SEAM}").write_text(_USE.format(lib=lib_name))
        sys.path.insert(0, str(tmp_path))
        try:
            lib = _load_module(lib_name, str(tmp_path / f"{lib_name}{SEAM}"))
            use = _load_module(use_name, str(tmp_path / f"{use_name}{SEAM}"))
        finally:
            sys.path.remove(str(tmp_path))
        loaded.extend([lib_name, use_name])
        return lib, use

    yield load
    for name in loaded:
        sys.modules.pop(name, None)


def test_compile_half_finds_the_home_through_either_binding(xm_pair):
    from clausal.logic.compiler.tabled_naf import _is_tabled_naf, _resolve_tabled_call
    lib, use = xm_pair(_SYM_LIB)
    _assert_owner_handle(use, "win", lib)
    udb, ldb = _lm(use).db, _lm(lib).db
    assert _resolve_tabled_call("win", 1, udb) == (ldb, "win")
    assert _is_tabled_naf(_goal("win", Var()), udb) is True


def test_runtime_half_keeps_the_cross_module_answer_undefined(xm_pair):
    """THE silent failure: ``[]`` with neither half moved, ``[True]`` with
    only the compile-time half moved.  WFS says Undefined."""
    lib, use = xm_pair(_SYM_LIB)
    _assert_owner_handle(use, "win", lib)
    assert _truths(_lm(use), "res", 1) == [Undefined]


def test_cross_module_answer_is_undefined_end_to_end(xm_pair):
    """The dry run's repro, end to end, with BOTH modules loaded under the
    flip: ``[]`` with neither read moved and ``[True]`` with only the
    compile-time read moved.  WFS says Undefined."""
    lib, use = xm_pair(_SYM_LIB)
    _assert_owner_handle(use, "win", lib)
    assert type(use.__dict__["res"]) is str, "the flip did not happen"
    assert _truths(_lm(use), "res", 1) == [Undefined]
    assert _truths(_lm(use), "res", 2) == [Undefined]


def test_cross_module_definite_answers_stay_definite_end_to_end(
        xm_pair):
    lib, use = xm_pair(_ASYM_LIB)
    _assert_owner_handle(use, "win", lib)
    assert _truths(_lm(use), "res", 2) == []
    assert _truths(_lm(use), "res", 1) == [True]
    assert _truths(_lm(use), "res", 3) == [True]


def test_runtime_half_keeps_definite_answers_definite(xm_pair):
    lib, use = xm_pair(_ASYM_LIB)
    _assert_owner_handle(use, "win", lib)
    assert _truths(_lm(use), "res", 2) == []
    assert _truths(_lm(use), "res", 1) == [True]
    assert _truths(_lm(use), "res", 3) == [True]


def test_runtime_half_directly_redirects_to_the_home_store(xm_pair):
    """``_naf_tabled`` itself, with the CALLER's store and db: an imported
    tabled callee is evaluated in its home db, so the negation of an
    Undefined answer delays (``True`` + a delay) instead of reading an empty
    caller-side table."""
    from clausal.logic.tabling import _naf_tabled
    lib, use = xm_pair(_SYM_LIB)
    _assert_owner_handle(use, "win", lib)
    udb, ldb = _lm(use).db, _lm(lib).db
    t = Trail()
    assert _naf_tabled("win", 1, (1,), t, udb.table_store, db=udb) is True
    assert any(k[0] == "win" for k in ldb.table_store), "not evaluated in the home"
    assert not any(k[0] == "win" for k in udb.table_store), "leaked into the caller"


def test_query_wfs_annotates_an_imported_tabled_goal(tmp_path):
    """``solve._tabled_call_site`` follows the binding to its owner module
    (it read ``__module__`` -- ``'builtins'`` on a handle)."""
    sys.path.insert(0, FIXTURES)
    try:
        owner = _load_module("wfs_win", os.path.join(FIXTURES, "wfs_win.clausal"))
        p = tmp_path / f"r6_wfs_impfrom{SEAM}"
        p.write_text("-import_from(wfs_win, [win])\n\nuses_f(X) <- win(X)\n")
        use = _load_module("r6_wfs_impfrom", str(p))
        _assert_owner_handle(use, "win", owner)
        from clausal.logic.solve import _tabled_call_site
        site = _tabled_call_site(_goal("win", 1), _lm(use), Trail())
        assert site is not None and site[0].db is _lm(owner).db
        X = Var()
        got = [(r["X"], r["_truth"])
               for r in query_wfs(_goal("win", X), {"X": X}, _lm(use), Trail())]
        assert sorted(got, key=lambda r: r[0]) == [(1, Undefined), (2, Undefined)]
    finally:
        sys.path.remove(FIXTURES)
        sys.modules.pop("r6_wfs_impfrom", None)


def test_the_tabled_home_is_the_owner_row_not_a_stamp(xm_pair):
    """The class-era form checked that no ``_tabled_home_db`` stamp sat on
    the class.  There is no class to stamp now; the home is answered from
    the binding's ROW (``tabled_home_of``), which this checks directly."""
    from clausal.logic.predicate import tabled_home_of
    lib, use = xm_pair(_SYM_LIB)
    assert type(lib.__dict__["win"]) is str      # nothing to carry a stamp
    udb, ldb = _lm(use).db, _lm(lib).db
    assert tabled_home_of(use.__dict__["win"], arity=1, db=udb) == (ldb, "win")


# ── _te_predicate_nodes: imported term_expansion rules ───────────────────────


@pytest.fixture
def te_provider():
    saved = sys.modules.pop("expansion_provider", None)
    prov = _load_module("expansion_provider",
                        os.path.join(FIXTURES, "expansion_provider.clausal"))
    yield prov
    sys.modules.pop("expansion_provider", None)
    if saved is not None:
        sys.modules["expansion_provider"] = saved


def _te_binding(prov):
    te = prov.__dict__["term_expansion"]
    assert te == mint_predicate_handle(_lm(prov).db, "term_expansion"), (
        "the load did not bind the handle")
    return te


def test_imported_te_rules_are_collected_through_either_binding(te_provider):
    from clausal.logic.term_expansion import _collect_imported_te_clauses
    nodes = _collect_imported_te_clauses(
        {"term_expansion": _te_binding(te_provider)})
    assert nodes == _lm(te_provider).db.te_predicate_nodes
    assert len(nodes) == 1


def test_imported_te_rules_expand_through_either_binding(te_provider):
    """End to end through ``compile_module``: an importer whose
    ``term_expansion`` binding is the provider's class or handle gets the
    provider's one-to-many rule (each item duplicated).  Post-flip it
    silently did nothing: ``['green', 'red']``."""
    from clausal.logic.atoms import mint
    from clausal.logic.compiler_v2 import compile_module
    from clausal.logic.solve import call
    from clausal.logic.variables import deref
    from tests.test_term_expansion import _parse_and_collect
    preds, items, md = _parse_and_collect('-double_quotes(atom)\ncolor("red"),\ncolor("green"),\n')
    md["term_expansion"] = _te_binding(te_provider)
    lm = compile_module(preds, items, md, "_r6_te_importer")
    x = Var()
    got = sorted(deref(x) for _ in call("color", x, module=lm))
    assert got == sorted([mint("green"), mint("green"), mint("red"), mint("red")])


def test_imported_te_fixture_end_to_end():
    """``expansion_importer`` loaded after ``expansion_provider``, both under
    the flip: the importer's ``-import_from`` binds the provider's HANDLE.
    The dry run measured ``['green', 'red']`` here -- the imported rule
    dropped without a sound."""
    from clausal.logic.atoms import mint
    from clausal.logic.solve import call
    from clausal.logic.variables import deref
    saved = {n: sys.modules.pop(n, None)
             for n in ("expansion_provider", "_r6_exp_imp")}
    sys.path.insert(0, FIXTURES)
    try:
        prov = _load_module("expansion_provider",
                            os.path.join(FIXTURES, "expansion_provider.clausal"))
        mod = _load_module("_r6_exp_imp",
                           os.path.join(FIXTURES, "expansion_importer.clausal"))
        assert type(prov.__dict__["term_expansion"]) is str
        assert mod.__dict__["term_expansion"] == prov.__dict__["term_expansion"]
        x = Var()
        got = sorted(deref(x) for _ in call("color", x, module=_lm(mod)))
        assert got == sorted([mint("green"), mint("green"),
                              mint("red"), mint("red")])
    finally:
        sys.path.remove(FIXTURES)
        for n, m in saved.items():
            sys.modules.pop(n, None)
            if m is not None:
                sys.modules[n] = m


def test_a_handle_to_another_predicate_contributes_nothing(te_provider):
    from clausal.logic.term_expansion import _collect_imported_te_clauses
    other = mint_predicate_handle(_lm(te_provider).db, "not_term_expansion")
    assert _collect_imported_te_clauses({"x": other}) == []


# ── _refuse_untablable_target: -table naming an imported predicate ──────────


def test_table_on_an_imported_target_names_the_owner():
    from clausal.logic.compiler_v2 import _refuse_untablable_target
    from clausal.logic.database import Database
    owner = _load_module("tests.fixtures.importable_utils",
                         os.path.join(FIXTURES, "importable_utils.clausal"))
    binding = owner.__dict__["double"]
    assert binding == mint_predicate_handle(_lm(owner).db, "double")
    with pytest.raises(SyntaxError) as exc:
        _refuse_untablable_target("double", 2, Database("r6_importer"),
                                  {"double": binding}, set())
    msg = str(exc.value)
    assert "another module" in msg
    assert "(defined in tests.fixtures.importable_utils)" in msg


def test_table_on_an_imported_target_end_to_end():
    """``test_tabling_lifecycle::test_imported_target_refused_naming_the_
    other_module`` under the flip."""
    with pytest.raises(SyntaxError) as exc:
        _load_module("r6_tbl_imported_target",
                     os.path.join(FIXTURES, "table_imported_target.clausal"))
    msg = str(exc.value)
    assert "-table(double/2)" in msg
    assert "another module" in msg
    assert "importable_utils" in msg
    assert "Move -table(double/2)" in msg


# ── _registered_at: the "defined at" line of an arity mismatch ───────────────


@pytest.fixture
def arimp():
    lib = _load_module("tests.fixtures.arimp_lib",
                       os.path.join(FIXTURES, "arimp_lib.clausal"))
    use = _load_module("_r6_arimp_use", os.path.join(FIXTURES, "arimp_use.clausal"))
    yield lib, use
    sys.modules.pop("_r6_arimp_use", None)


def test_the_declaration_site_is_on_the_row(arimp):
    lib, _use = arimp
    assert type(lib.__dict__["arimp_pair"]) is str   # no class to ask
    row = _lm(lib).db.row("arimp_pair", 2)
    # the class era's ``_registered_at`` for this fixture (CLAUSAL_NO_FLIP=1,
    # 9e6c2633): the -module line, line 3
    assert row.declared_at[0].endswith("arimp_lib.clausal")
    assert row.declared_at[1] == 3


def test_unqualified_wrong_arity_points_at_the_definition(arimp):
    from clausal.logic.predicate import _refuse_unqualified_other_arity
    from clausal.predicate_diagnostics import PredicateArityMismatchError
    lib, use = arimp
    _assert_owner_handle(use, "arimp_pair", lib)
    binding = use.__dict__["arimp_pair"]
    with pytest.raises(PredicateArityMismatchError) as exc:
        _refuse_unqualified_other_arity(binding, "arimp_pair", 1, _lm(use).db)
    msg = str(exc.value)
    assert "arimp_pair takes 2 arguments" in msg
    assert "arimp_lib.clausal:" in msg


def test_direct_wrong_arity_points_at_the_definition(arimp):
    """``_dispatch_at`` -- the class arm's ``_refuse_call_at`` and the handle
    arm's ``_refuse_if_known_at_another_arity`` -- both say where."""
    from clausal.logic.predicate import _dispatch_at
    from clausal.predicate_diagnostics import PredicateArityMismatchError
    lib, use = arimp
    _assert_owner_handle(use, "arimp_pair", lib)
    with pytest.raises(PredicateArityMismatchError) as exc:
        _dispatch_at(use.__dict__["arimp_pair"], 1)
    msg = str(exc.value)
    assert "arimp_pair takes 2 arguments" in msg
    assert "arimp_lib.clausal:" in msg


def test_imported_wrong_arity_points_across_the_boundary_end_to_end():
    """``test_predicate_arity_mismatch_diagnostic::TestImportedPredicate``
    under the flip: the dry run lost the "defined at" line (§3.4)."""
    from clausal.logic.solve import call
    from clausal.predicate_diagnostics import PredicateArityMismatchError
    saved = {n: sys.modules.pop(n, None)
             for n in ("tests.fixtures.arimp_lib", "_r6_arimp_use_e2e")}
    try:
        _load_module("tests.fixtures.arimp_lib",
                     os.path.join(FIXTURES, "arimp_lib.clausal"))
        use = _load_module("_r6_arimp_use_e2e",
                           os.path.join(FIXTURES, "arimp_use.clausal"))
        assert type(use.__dict__["arimp_pair"]) is str
        with pytest.raises(PredicateArityMismatchError) as exc:
            list(call("arimp_uses", Var(), module=_lm(use)))
        msg = str(exc.value)
        assert "arimp_pair takes 2 arguments" in msg
        assert "arimp_lib.clausal:" in msg
    finally:
        for n, m in saved.items():
            sys.modules.pop(n, None)
            if m is not None:
                sys.modules[n] = m
