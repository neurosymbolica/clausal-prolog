"""Index plans live on the Database ROW, not the class (P1, spec 2026-09-17 §2.1).

Until now `_index_plans` & co. were CLASS-ONLY state (census: "the class holds
state that the spec says it does not"). A row home is what lets a call site
find a predicate's plans by (functor, arity) without the class.
"""
from clausal import Var
from clausal.import_hook import _load_module
from clausal.logic.predicate import PredicateMeta


def _load(tmp_path, name, src):
    p = tmp_path / f"{name}.clausal"; p.write_text(src)
    return _load_module(name, str(p)).__dict__["$module"]


SRC = (
    "-private([" + ", ".join(f"c{i}" for i in range(40)) + "])\n"
    + "".join(f"colour({i}, c{i}),\n" for i in range(40))
)   # enough clauses to be indexed; -private declares the bare colour atoms


def test_the_class_attribute_reads_through_to_the_row(tmp_path):
    mod = _load(tmp_path, "ip_a", SRC)
    cls = mod.module_dict["colour"]
    row = mod.db.row("colour", 2)
    assert row is not None
    assert cls._index_plans is row.index_plans
    assert cls._index_plans_joint is row.index_plans_joint
    assert cls._index_plans_hierarchical is row.index_plans_hierarchical


def test_the_compiler_wrote_plans_onto_the_row(tmp_path):
    # the writer in compiler/predicate.py is untouched; its assignment now lands on the row
    mod = _load(tmp_path, "ip_b", SRC)
    row = mod.db.row("colour", 2)
    assert isinstance(row.index_plans, dict) and row.index_plans, "first-arg index expected"


def test_assignment_on_the_class_lands_on_the_row(tmp_path):
    mod = _load(tmp_path, "ip_c", SRC)
    cls = mod.module_dict["colour"]
    cls._index_plans = {"marker": {}}
    assert mod.db.row("colour", 2).index_plans == {"marker": {}}


def test_a_detached_class_still_has_plans_through_its_private_row():
    class Loose(metaclass=PredicateMeta):
        pass
    assert Loose._index_plans == {}
    Loose._index_plans = {0: {}}
    assert Loose._index_plans == {0: {}}


def test_a_fresh_row_has_empty_plans(tmp_path):
    mod = _load(tmp_path, "ip_d", "-dynamic(empty/1)\n")
    row = mod.db.row("empty", 1)
    assert row is not None and row.index_plans == {} and row.index_plans_joint == {} \
        and row.index_plans_hierarchical == {}
