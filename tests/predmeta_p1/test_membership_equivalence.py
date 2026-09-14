"""Spec P1 prerequisite: WHICH Database call is equivalent to the isinstance test.

Category A of the P0 census is 30 sites asking "is this name a predicate here?",
spelled `isinstance(module_dict.get(functor), PredicateMeta)`. Rerouting them needs
an exactly-equivalent Database question, and the obvious candidate is WRONG:

    db.is_defined(functor, arity)      "any clause has been asserted"   -- STRICTER
    db.row(functor, arity) is not None "a row exists for it"            -- EQUIVALENT

`compiler_v2.py:958` deliberately "Creates empty PredicateMeta classes (no clauses,
no dispatch)", so `isinstance` is True for declared-but-empty predicates where
`is_defined` is False. Rerouting to `is_defined` would silently un-declare every
dynamic-but-unasserted predicate.

These tests pin the equivalence so P1 cannot regress to the wrong call.
"""
from __future__ import annotations
import importlib, pathlib, shutil, sys
import pytest


def _ensure_built_clausal() -> None:
    try:
        importlib.import_module("clausal.logic.variables._variables")
        return
    except ModuleNotFoundError:
        pass
    cand = "/workspace/clausal"
    if (pathlib.Path(cand) / "clausal" / "logic" / "variables").is_dir():
        sys.path.insert(0, cand)
        for mod in [m for m in sys.modules if m == "clausal" or m.startswith("clausal.")]:
            del sys.modules[mod]
        try:
            importlib.import_module("clausal.logic.variables._variables")
            return
        except ModuleNotFoundError:
            pass
    pytest.skip("no clausal tree with built C extensions", allow_module_level=True)


_ensure_built_clausal()


@pytest.fixture
def mod(tmp_path, monkeypatch):
    (tmp_path / "membfix.seam").write_text(
        "-dynamic(declared_empty/1)\n\nhas_clauses(1),\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    m = importlib.import_module("membfix")
    yield m
    for p in tmp_path.rglob("__pycache__"):
        shutil.rmtree(p, ignore_errors=True)


def _db(m):
    """A module's Database is reached through its $module, NOT through any
    predicate's _row.db -- reaching for the latter yields a DIFFERENT Database
    that reports is_defined=False even for a predicate that has clauses. That
    wrong turn is how this test came to exist."""
    logic_module = vars(m)["$module"]
    return logic_module.db


def test_the_module_database_is_reachable_through_dollar_module(mod):
    from clausal.logic.database import Database
    assert isinstance(_db(mod), Database)


def test_row_existence_IS_equivalent_to_the_isinstance_test(mod):
    from clausal.logic.predicate import PredicateMeta
    db = _db(mod)
    for name, arity in (("has_clauses", 1), ("declared_empty", 1)):
        obj = getattr(mod, name)
        assert isinstance(obj, PredicateMeta), name
        assert db.row(name, arity) is not None, (
            f"{name}: row() disagrees with isinstance -- the P1 reroute is unsound")


def test_is_defined_is_NOT_equivalent_and_this_is_why(mod):
    """The negative control for the reroute: if this ever passes, is_defined has
    changed meaning and P1's choice of call must be revisited."""
    db = _db(mod)
    assert db.is_defined("has_clauses", 1) is True
    assert db.is_defined("declared_empty", 1) is False, (
        "is_defined now reports declared-but-empty predicates as defined; "
        "re-check whether row() is still the right equivalence for P1")
    assert db.is_dynamic("declared_empty", 1) is True


def test_row_does_not_MINT_a_row_for_an_unknown_predicate(mod):
    """row(create=False) must not create -- otherwise the membership test would
    answer True for everything the moment it is asked."""
    db = _db(mod)
    assert db.row("no_such_predicate_xyz", 3) is None
