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
from clausal.logic.specialization import analyze_mi
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


def _specializing_module():
    sys.modules.pop("tests.fixtures.specialize_natnum", None)
    return _load_module("tests.fixtures.specialize_natnum",
                        os.path.join(FIXTURES, "specialize_natnum.clausal"))


def test_the_mi_is_found_in_the_module_s_db_whatever_it_is_bound_to(mis):
    module = _specializing_module()
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
    row = _meta_interpreter_row(Database(), {"solve": mis.solve}, "solve",
                                refuse_ambiguous=True)
    assert row is not None and row is mis.solve._row


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
        monkeypatch):
    """Ruling QB: observed at step 2, the step right after pre-registration."""
    seen = {}
    real = compiler_v2._process_directives

    def spy(module_items, db, module_dict):
        seen["kind"] = db.declared_kind("solve_count_natnum", 2)
        return real(module_items, db, module_dict)

    monkeypatch.setattr(compiler_v2, "_process_directives", spy)
    _specializing_module()
    assert seen, "step 2 never ran"
    assert seen["kind"] == "predicate"
