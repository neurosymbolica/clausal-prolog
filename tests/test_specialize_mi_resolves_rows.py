"""F1 rows 32/33: ``-specialize`` finds its meta-interpreter as a ROW in the
specializing module's own database, and ``analyze_mi`` reads a row.

The compiler used to read the MI's ``PredicateMeta`` class out of the module
dict and skip anything else; after the retirement flip every binding is a
mangled atom, so ``-specialize`` would have stopped finding any MI.  Plus the
two rulings that ride along (2026-09-24):

* QA -- an MI defined at several arities is refused, listing them;
* QB -- pre-registration mints the target's ROW, so the target reads as a
  PREDICATE (not data) from step 1c on.
"""

from __future__ import annotations

import os
import sys

import pytest

import clausal.import_hook  # noqa: F401 — installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic import compiler_v2
from clausal.logic.atoms import mangle
from clausal.logic.compiler_v2 import _meta_interpreter_row
from clausal.logic.database import Clause, Database
from clausal.logic.predicate import PredicateMeta
from clausal.logic.specialization import CannotSpecialize, analyze_mi
from clausal.terms import Compound

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
_MIS = "clausal.examples.metainterpreters"


@pytest.fixture(scope="module")
def mis():
    import importlib
    return importlib.import_module(_MIS)


def _pattern_shape(p):
    return (p.fields, p.goal_arg, p.program_arg, p.extra_args,
            p.match_clause_index, p.append_index, p.recursive_call_indices,
            p.recursive_call_style, p.base_clause is not None,
            p.recursive_clause is not None)


@pytest.mark.parametrize("mi", ["solve", "solve_count", "solve_limit", "solve_tree"])
def test_analyze_mi_reads_a_row_exactly_as_it_reads_the_class(mis, mi):
    cls = getattr(mis, mi)
    assert isinstance(cls, PredicateMeta) and cls._row is not None
    assert _pattern_shape(analyze_mi(cls._row)) == _pattern_shape(analyze_mi(cls))


# A PRIVATE module name: loading the fixture under its dotted
# ``tests.fixtures.`` name leaves a ``sys.modules`` entry with no parent
# package attribute, which breaks a later plain ``import`` of it elsewhere.
_SPEC = "_rows3233_specialize_natnum"


@pytest.fixture
def fresh_spec_module():
    """Load the fixture afresh under a private name; drop it afterwards."""
    sys.modules.pop(_SPEC, None)

    def load():
        return _load_module(_SPEC, os.path.join(FIXTURES,
                                                "specialize_natnum.clausal"))
    yield load
    sys.modules.pop(_SPEC, None)


def test_the_mi_is_found_in_the_module_s_db_whatever_it_is_bound_to(
        mis, fresh_spec_module):
    module = fresh_spec_module()
    db = module.__dict__["$module"].db
    md = dict(module.__dict__)
    assert isinstance(md["solve_count"], PredicateMeta)

    row = _meta_interpreter_row(db, md, "solve_count", refuse_ambiguous=True)
    assert row is not None, "the imported MI was not found: nothing compared"
    assert row is mis.solve_count._row

    md["solve_count"] = mangle(_MIS, "solve_count")      # the post-flip shape
    assert _meta_interpreter_row(db, md, "solve_count",
                                 refuse_ambiguous=True) is row
    md["solve_count"] = None                            # not bound at all
    assert _meta_interpreter_row(db, md, "solve_count",
                                 refuse_ambiguous=True) is row


def test_a_predicate_bound_only_by_a_python_import_is_still_found(mis):
    """No row in this database -- the last-resort binding route."""
    found = _meta_interpreter_row(Database(), {"solve": mis.solve}, "solve",
                                  refuse_ambiguous=True)
    assert found is mis.solve          # the class itself, until W4b-3
    assert _meta_interpreter_row(
        Database(), {"solve": mangle(_MIS, "solve")}, "solve",
        refuse_ambiguous=True) is mis.solve._row


def test_a_python_built_mi_keeps_its_class_fields_and_its_refusal():
    """A class with fields but no registered signature, and one with no row
    at all, answer as they did through the class route."""
    from clausal.logic.predicate import make_predicate
    cls = make_predicate("pybuilt_mi", ["GOALS", "PROGRAM"])
    assert cls._row is None
    found = _meta_interpreter_row(Database(), {"pybuilt_mi": cls},
                                  "pybuilt_mi", refuse_ambiguous=True)
    assert found is cls
    with pytest.raises(CannotSpecialize, match=r"pybuilt_mi: expected at "
                                               r"least 2 clauses .*got 0"):
        analyze_mi(found)


def _two_arity_db():
    db = Database()
    db.assertz(Clause(head=Compound("mi2", (1,)), body=[]))
    db.assertz(Clause(head=Compound("mi2", (1, 2)), body=[]))
    return db


def test_an_mi_defined_at_several_arities_is_refused_listing_them():
    """Ruling QA."""
    with pytest.raises(RuntimeError, match=r"defined at 2 arities \(mi2/1, mi2/2\)"):
        _meta_interpreter_row(_two_arity_db(), {}, "mi2", refuse_ambiguous=True)
    # Pre-registration defers the refusal to the run step.
    assert _meta_interpreter_row(_two_arity_db(), {}, "mi2",
                                 refuse_ambiguous=False) is None


def test_the_specialized_target_is_a_predicate_from_pre_registration(
        monkeypatch, fresh_spec_module):
    """Ruling QB: observed at step 2, the step right after pre-registration
    -- and the row minted there is the one the specialization is installed
    on, not a stale twin beside it."""
    seen = {}
    real = compiler_v2._process_directives

    def spy(*args, **kwargs):
        db = args[1] if len(args) > 1 else kwargs["db"]
        seen["kind"] = db.declared_kind("solve_count_natnum", 2)
        seen["row"] = db.row("solve_count_natnum", 2)
        return real(*args, **kwargs)

    monkeypatch.setattr(compiler_v2, "_process_directives", spy)
    module = fresh_spec_module()
    assert seen, "step 2 never ran"
    assert seen["kind"] == "predicate"

    db = module.__dict__["$module"].db
    row = db.row("solve_count_natnum", 2)
    assert row is seen["row"], "the installed row is not the pre-minted one"
    assert row.clauses and row.dispatch_fn is not None
    assert module.__dict__["solve_count_natnum"]._row is row


def test_a_row_with_clauses_but_no_field_names_is_refused():
    db = Database()
    for n in (1, 2):
        db.assertz(Clause(head=Compound("nosig_mi", (n,)), body=[]))
    assert db.signature_for("nosig_mi", 1) is None
    with pytest.raises(CannotSpecialize, match="no field names are registered"):
        analyze_mi(db.row("nosig_mi", 1))


def test_a_declared_mi_with_no_clauses_gets_analyze_mi_s_refusal(
        tmp_path, monkeypatch):
    """A clause-less ``-dynamic`` MI: the refusal comes from analyze_mi,
    whose message is the one place it is spelled."""
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("spec_empty_mi", None)
    (tmp_path / "spec_empty_mi.clausal").write_text(
        "-dynamic(empty_mi/2)\n\n"
        "prog(P) <- (P is [])\n\n"
        "-specialize(empty_mi, prog, alias=empty_spec)\n")
    try:
        with pytest.raises(CannotSpecialize,
                           match=r"empty_mi: expected at least 2 clauses .*got 0"):
            _load_module("spec_empty_mi", str(tmp_path / "spec_empty_mi.clausal"))
    finally:
        sys.modules.pop("spec_empty_mi", None)


def test_a_clause_less_row_is_found_in_the_db_without_any_binding():
    """Step 2 of the lookup: the post-flip shape, where the binding may not
    resolve mid-load -- the database alone must find the clause-less row."""
    db = Database()
    db.mark_dynamic("cl_mi", 2)
    row = _meta_interpreter_row(db, {}, "cl_mi", refuse_ambiguous=True)
    assert row is not None and row is db.row("cl_mi", 2)
    with pytest.raises(CannotSpecialize, match=r"got 0"):
        analyze_mi(row)


def _two_arity_owner(monkeypatch, name):
    """A REAL owner: a Database defining ``amb_mi`` at two arities (one
    ``.clausal`` file cannot), registered under *name* the way a loaded
    module is, so the owner lookup runs unmocked."""
    import types
    from types import SimpleNamespace
    db = Database({"__name__": name})
    for n in (1, 2):
        db.assertz(Clause(head=Compound("amb_mi", (n, n)), body=[]))
        db.assertz(Clause(head=Compound("amb_mi", (n, n, n)), body=[]))
    mod = types.ModuleType(name)
    mod.__dict__["$module"] = SimpleNamespace(db=db)
    monkeypatch.setitem(sys.modules, name, mod)
    return db


@pytest.mark.parametrize("shape", ["mangled", "class"])
def test_the_binding_route_refuses_several_arities_too(monkeypatch, shape):
    """QA holds on every route and for both binding shapes, with the same
    message, against an owner that really defines two arities."""
    _two_arity_owner(monkeypatch, "_amb_owner")
    if shape == "mangled":
        binding = mangle("_amb_owner", "amb_mi")
    else:
        from clausal.logic.predicate import make_predicate
        binding = make_predicate("amb_mi", ["G", "P"])
        binding.__module__ = "_amb_owner"
    md = {"amb_mi": binding}
    with pytest.raises(RuntimeError,
                       match=r"defined at 2 arities \(amb_mi/2, amb_mi/3\)"):
        _meta_interpreter_row(Database(), md, "amb_mi", refuse_ambiguous=True)
    assert _meta_interpreter_row(Database(), md, "amb_mi",
                                 refuse_ambiguous=False) is None


def test_a_second_arity_without_clauses_is_still_ambiguous():
    """QA across tiers: clauses at one arity and a bare row at another."""
    db = Database()
    for n in (1, 2):
        db.assertz(Clause(head=Compound("tier_mi", (n, n)), body=[]))
    db.mark_dynamic("tier_mi", 3)
    with pytest.raises(RuntimeError, match=r"tier_mi/2, tier_mi/3"):
        _meta_interpreter_row(db, {}, "tier_mi", refuse_ambiguous=True)
