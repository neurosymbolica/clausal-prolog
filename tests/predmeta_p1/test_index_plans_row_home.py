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
    assert cls._state_row().index_plans is row.index_plans
    assert cls._state_row().index_plans_joint is row.index_plans_joint
    assert cls._state_row().index_plans_hierarchical is row.index_plans_hierarchical


def test_the_compiler_wrote_plans_onto_the_row(tmp_path):
    # the writer in compiler/predicate.py is untouched; its assignment now lands on the row
    mod = _load(tmp_path, "ip_b", SRC)
    row = mod.db.row("colour", 2)
    assert isinstance(row.index_plans, dict) and row.index_plans, "first-arg index expected"


def test_assignment_on_the_class_lands_on_the_row(tmp_path):
    mod = _load(tmp_path, "ip_c", SRC)
    cls = mod.module_dict["colour"]
    cls._state_row().index_plans = {"marker": {}}
    assert mod.db.row("colour", 2).index_plans == {"marker": {}}


def test_a_detached_class_still_has_plans_through_its_private_row():
    class Loose(metaclass=PredicateMeta):
        pass
    assert Loose._state_row().index_plans == {}
    Loose._state_row().index_plans = {0: {}}
    assert Loose._state_row().index_plans == {0: {}}


def test_a_fresh_row_has_empty_plans(tmp_path):
    mod = _load(tmp_path, "ip_d", "-dynamic(empty/1)\n")
    row = mod.db.row("empty", 1)
    assert row is not None and row.index_plans == {} and row.index_plans_joint == {} \
        and row.index_plans_hierarchical == {}


# ── a DETACHED row's plans travel with the class (roborev M1) ───────────────


def _detached_indexed_class(name, arity, facts, db):
    """Compile *facts* through a class that is still on its PRIVATE row.

    ``compile_predicate_trampoline`` writes the plans first and ``_install``
    binds afterwards, so this is the one order in which plans are written onto
    a detached row and then have to survive the bind.  (The fixture in
    ``test_arity_exact_index_hints`` binds FIRST, which is the workaround this
    test exists to remove.)
    """
    from clausal.logic.builtins import _normalize_fact_clause
    from clausal.logic.compiler import compile_predicate_trampoline
    from clausal.terms import Compound

    cls = PredicateMeta(name, (), {"_fields": tuple(f"arg{i}" for i in range(arity))})
    assert cls._row is None, "a fresh class has no row until something asks"
    clauses = [_normalize_fact_clause(Compound(name, tuple(a))) for a in facts]
    compile_predicate_trampoline(name, arity, clauses, db, pred_cls=cls)
    return cls


def test_plans_written_on_a_detached_row_survive_the_bind():
    """_INDEX_THRESHOLD is 4; 8 distinct first args is indexed."""
    from clausal.logic.database import Database

    db = Database()
    cls = _detached_indexed_class("shade", 2, [(i, i * 10) for i in range(8)], db)
    row = db.row("shade", 2)
    assert row is not None and not row.detached
    assert cls._row is row, "the compile's _install binds the class to db's row"
    assert row.index_plans, (
        "the plans the compiler wrote through the class were left behind on "
        "its detached row: _bind_row migrates clauses but not index_plans*"
    )
    assert cls._state_row().index_plans is row.index_plans


def test_a_real_to_real_rebind_leaves_the_targets_plans_alone(tmp_path):
    """The migration is scoped to a DETACHED old row (the ruling): a class
    on one REAL row must not overwrite another row's plans, which belong to
    that row's Database, not to the class.

    Since 2026-09-24 an authorized re-bind across databases no longer moves
    the class at all -- it raises (the vocabulary-implements steal is gone)
    -- so what is pinned is that the refused move leaves BOTH rows' plans,
    and the class's binding, exactly as they were."""
    import pytest
    from clausal.logic.database import Database

    a, b = Database(), Database()
    cls = PredicateMeta("hue", (), {"_fields": ("arg0",)})
    cls._bind_row(a, "hue", 1)
    cls._state_row().index_plans = {"from-a": {}}
    target = b.row("hue", 1, create=True)
    target.index_plans = {"already-here": {}}
    with pytest.raises(RuntimeError, match="never changes its defining module"):
        cls._bind_row(b, "hue", 1, authorized=True)
    assert cls._row is a.row("hue", 1)
    assert target.index_plans == {"already-here": {}}
    assert a.row("hue", 1).index_plans == {"from-a": {}}


def test_a_detached_rows_plans_do_not_overwrite_a_populated_target():
    """... and even from a detached row, only EMPTY target dicts are filled."""
    from clausal.logic.database import Database

    db = Database()
    cls = PredicateMeta("tint", (), {"_fields": ("arg0",)})
    cls._state_row().index_plans = {"detached": {}}   # mints the private detached row
    assert cls._row.detached
    target = db.row("tint", 1, create=True)
    target.index_plans = {"target": {}}
    cls._bind_row(db, "tint", 1)
    assert target.index_plans == {"target": {}}


def test_plans_do_not_migrate_onto_a_row_with_a_DIFFERENT_key():
    """Re-review residual on M1: the migration was guarded on "the old row is
    DETACHED" and "the target is empty" but NOT on the two rows naming the
    same predicate.

    A detached compile names its own key (the class's name and field count).
    Binding that class under ANOTHER name -- which ``_bind_row`` exists to do,
    since an aliased ``-import_from`` binds a class under a name that is not
    its own -- then handed the target row bucket functions built for a
    DIFFERENT predicate, and ``locked`` travels in the same block, so
    ``hint_row`` would go on to emit them at that target's call sites.
    """
    from clausal.logic.database import Database

    db = Database()
    # db=None: the compile writes plans onto the class's PRIVATE row and
    # ``_install`` binds nothing, which is the documented out-of-tree shape.
    cls = _detached_indexed_class("shade", 2, [(i, i * 10) for i in range(8)], None)
    assert cls._row.detached and cls._row.key == ("shade", 2)
    assert cls._state_row().index_plans, "the fixture must actually have plans"
    cls._state_row().locked = True

    cls._bind_row(db, "tint", 2)

    target = db.row("tint", 2)
    assert target is not None and cls._row is target
    assert target.index_plans == {}, (
        "shade/2's bucket functions were handed to tint/2: they are keyed on "
        f"shade's own arguments -- got {target.index_plans}")
    assert target.index_plans_joint == {} and target.index_plans_hierarchical == {}
