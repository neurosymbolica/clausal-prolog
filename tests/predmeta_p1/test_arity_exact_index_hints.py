"""Index hints are ARITY-EXACT (P1, spec 2026-09-17 §2.3 — the four R! sites).

Before: the two hint passes looked the callee up BY NAME in ``base_globals``
and read the class's ``_index_plans`` whatever the call's arity, even though
both had already computed that arity.  After: ``db.row(fname, arity)`` — a
call at arity N can only ever see the plans compiled for arity N.

The four sites:
  * ``goal_trampoline._inject_bucket_refs_trampoline``
  * ``goal_trampoline.analyse_ir_bucket_refs``
  * ``optimisations.call_site.analyse``
  * ``optimisations.call_site.populate_runtime_from_plan``

Each takes ``db=`` now; the db is threaded from the compile pipeline
(``CompilationContext.db``), never looked up through ``$module``.
"""
from __future__ import annotations

from clausal import Var
from clausal.import_hook import _load_module
from clausal.logic.builtins import _normalize_fact_clause
from clausal.logic.compiler import compile_predicate_trampoline
from clausal.logic.compiler.compile_ctx import CompilationContext
from clausal.logic.compiler.strategy import TrampolineStrategy
from clausal.logic.database import Clause, Database
from clausal.logic.predicate import PredicateMeta
from clausal.logic.solve import call
from clausal.logic.variables import deref
from clausal.terms import Call, Compound, LoadName


# ── fixture: one locked, indexed callee living in a real Database ────────────


def _locked_indexed_callee(db, name, arity, facts):
    """Compile *facts* as ``name/arity`` into *db*, locked and indexed.

    The row is bound BEFORE the compile so the plans the compiler writes
    through the class land on the Database's row (they are row-local state
    since Task 1) rather than on a detached row that is later discarded.
    """
    cls = PredicateMeta(name, (), {"_fields": tuple(f"arg{i}" for i in range(arity))})
    cls._bind_row(db, name, arity)
    clauses = [_normalize_fact_clause(Compound(name, tuple(a))) for a in facts]
    compile_predicate_trampoline(name, arity, clauses, pred_cls=cls)
    cls._locked = True
    return cls


# _INDEX_THRESHOLD is 4; 40 distinct first args is comfortably indexed.
_FACTS2 = [(i, i * 10) for i in range(40)]


def _callee_db():
    db = Database()
    cls = _locked_indexed_callee(db, "colour", 2, _FACTS2)
    return db, cls


def _body(nargs):
    """A clause body calling ``colour`` with a static literal 3 first."""
    x = Var()
    args = [3, x][:nargs]
    return [Call(func=LoadName(name="colour"), args=args, kwargs=[])]


def _mkctx(db):
    return CompilationContext(
        db=db, var_context={}, trail_name="trail",
        strategy=TrampolineStrategy(),
    )


# ── the row is the thing the sites now read ─────────────────────────────────


def test_the_db_has_a_row_only_at_the_compiled_arity():
    db, cls = _callee_db()
    row = db.row("colour", 2)
    assert row is not None
    assert row.locked and row.index_plans
    # the same name at another arity has NO row — that is the whole point
    assert db.row("colour", 1) is None


# ── site 1: _inject_bucket_refs_trampoline ──────────────────────────────────


def test_inject_hints_at_the_matching_arity():
    from clausal.logic.compiler.goal_trampoline import _inject_bucket_refs_trampoline
    db, cls = _callee_db()
    base_globals = {"colour": cls}
    clause = Clause(head=Compound("caller", (Var(),)), body=_body(2))
    ctx = _mkctx(db)
    _inject_bucket_refs_trampoline(ctx, [clause], base_globals, db=db)
    assert [k for k in ctx.bucket_ref_map if k[1] == 2], ctx.bucket_ref_map
    assert any(".bucket(" in k for k in base_globals)


def test_inject_skips_a_call_at_an_arity_with_no_row():
    from clausal.logic.compiler.goal_trampoline import _inject_bucket_refs_trampoline
    db, cls = _callee_db()
    base_globals = {"colour": cls}
    clause = Clause(head=Compound("caller", (Var(),)), body=_body(1))
    ctx = _mkctx(db)
    _inject_bucket_refs_trampoline(ctx, [clause], base_globals, db=db)
    assert not ctx.bucket_ref_map, (
        "a colour/1 call must not borrow colour/2's buckets: position 0's "
        f"buckets are keyed on colour/2's first arg — got {ctx.bucket_ref_map}"
    )
    assert not [k for k in base_globals if ".bucket(" in k]


def test_inject_without_a_db_emits_no_hints():
    from clausal.logic.compiler.goal_trampoline import _inject_bucket_refs_trampoline
    db, cls = _callee_db()
    base_globals = {"colour": cls}
    clause = Clause(head=Compound("caller", (Var(),)), body=_body(2))
    ctx = _mkctx(None)
    _inject_bucket_refs_trampoline(ctx, [clause], base_globals, db=None)
    assert not ctx.bucket_ref_map


# ── site 2: analyse_ir_bucket_refs ──────────────────────────────────────────


def test_ir_walker_hints_at_the_matching_arity():
    from clausal.logic.compiler.goal_trampoline import analyse_ir_bucket_refs
    db, cls = _callee_db()
    clause = Clause(head=Compound("caller", (Var(),)), body=_body(2))
    br, _jbr = analyse_ir_bucket_refs([clause], {"colour": cls}, db=db)
    assert [k for k in br if k[1] == 2], br


def test_ir_walker_skips_a_call_at_an_arity_with_no_row():
    from clausal.logic.compiler.goal_trampoline import analyse_ir_bucket_refs
    db, cls = _callee_db()
    clause = Clause(head=Compound("caller", (Var(),)), body=_body(1))
    br, jbr = analyse_ir_bucket_refs([clause], {"colour": cls}, db=db)
    assert not br and not jbr, br


# ── site 3: call_site.analyse ───────────────────────────────────────────────


def _ir_for(nargs, db):
    from clausal.logic.compiler.terms_to_goalop import terms_to_goalop
    return terms_to_goalop(_body(nargs), db=db)


def test_call_site_analyse_hints_at_the_matching_arity():
    from clausal.logic.compiler.optimisations import call_site
    db, cls = _callee_db()
    plan = call_site.analyse(_ir_for(2, db), None, {"colour": cls}, db=db)
    assert plan.hints


def test_call_site_analyse_skips_an_arity_with_no_row():
    from clausal.logic.compiler.optimisations import call_site
    db, cls = _callee_db()
    plan = call_site.analyse(_ir_for(1, db), None, {"colour": cls}, db=db)
    assert not plan.hints and not plan.joint_hints


def test_call_site_analyse_without_a_db_emits_no_hints():
    from clausal.logic.compiler.optimisations import call_site
    db, cls = _callee_db()
    plan = call_site.analyse(_ir_for(2, db), None, {"colour": cls}, db=None)
    assert not plan.hints


# ── site 4: call_site.populate_runtime_from_plan ────────────────────────────


def test_populate_runtime_writes_the_map_at_the_matching_arity():
    from clausal.logic.compiler.optimisations import call_site
    db, cls = _callee_db()
    base_globals = {"colour": cls}
    ir = _ir_for(2, db)
    plan = call_site.analyse(ir, None, base_globals, db=db)
    ctx = _mkctx(db)
    call_site.populate_runtime_from_plan(ir, plan, ctx, base_globals, db=db)
    assert [k for k in ctx.bucket_ref_map if k[1] == 2], ctx.bucket_ref_map
    assert any(".bucket(" in k for k in base_globals)


def test_populate_runtime_refuses_a_hint_at_an_arity_with_no_row():
    """A hint fabricated for a colour/1 SubCall must not resolve a bucket:
    populate_runtime_from_plan re-reads the callee's plans, and at arity 1
    there is no row to read them from."""
    from clausal.logic.compiler.optimisations import call_site
    db, cls = _callee_db()
    base_globals = {"colour": cls}
    ir = _ir_for(1, db)
    fabricated = call_site.CallSitePlan(
        hints=((0, "colour.bucket(pos=0, 3)"),), joint_hints=(),
    )
    ctx = _mkctx(db)
    call_site.populate_runtime_from_plan(ir, fabricated, ctx, base_globals, db=db)
    assert not ctx.bucket_ref_map, ctx.bucket_ref_map
    assert not [k for k in base_globals if ".bucket(" in k]


# ── positive control: db really reaches the passes from the pipeline ────────


def test_the_compile_pipeline_threads_its_db_to_the_populator():
    """``goal_shallow._prepopulate_call_site_runtime`` is the production
    caller of site 4.  It passes ``ctx.db``; if the threading were missing
    (db None everywhere) the map below would be empty."""
    from clausal.logic.compiler.goal_shallow import _prepopulate_call_site_runtime
    db, cls = _callee_db()
    ctx = _mkctx(db)
    ctx.base_globals = {"colour": cls}
    _prepopulate_call_site_runtime(_body(2), ctx)
    assert [k for k in ctx.bucket_ref_map if k[1] == 2], ctx.bucket_ref_map
    assert any(".bucket(" in k for k in ctx.base_globals)


# ── and the ordinary load path is untouched ─────────────────────────────────


def _load(tmp_path, name, src):
    p = tmp_path / f"{name}.clausal"
    p.write_text(src)
    return _load_module(name, str(p)).__dict__["$module"]


_SRC = (
    "".join(f"colour({i}, {i * 10}),\n" for i in range(40))
    + "pick_three(Y) <- colour(3, Y),\n"
)


def test_the_ordinary_load_path_still_indexes_and_answers(tmp_path):
    mod = _load(tmp_path, "ax_load", _SRC)
    row = mod.db.row("colour", 2)
    assert row is not None and row.index_plans
    y = Var()
    assert [deref(y) for _ in call("pick_three", y, module=mod)] == [30]


# ── the dotted spelling an -import_from remap emits ─────────────────────────


def test_a_dotted_callee_resolves_through_the_object_at_that_spelling():
    """``-import_from`` rewrites references to the EXPORTER's dotted
    spelling, which is a base_globals key and never a Database key (the
    importer adopted the row under the LOCAL name).  ``hint_row`` resolves
    it through the object bound there — still arity-exact, because the
    arity comes from that object's own row key."""
    from clausal.logic.compiler.arg_index import hint_row
    db, cls = _callee_db()          # colour/2, locked, in `db`
    importer = Database()           # a DIFFERENT Database, as an importer is
    base_globals = {"pkg.mod.colour": cls}
    row = hint_row(importer, "pkg.mod.colour", 2, base_globals)
    assert row is db.row("colour", 2)
    # ... and the same spelling at another arity resolves to nothing
    assert hint_row(importer, "pkg.mod.colour", 1, base_globals) is None
    # ... and an unlocked callee is still refused
    cls._locked = False
    assert hint_row(importer, "pkg.mod.colour", 2, base_globals) is None


def test_a_dotted_callee_with_no_binding_is_no_row():
    from clausal.logic.compiler.arg_index import hint_row
    db, _cls = _callee_db()
    assert hint_row(db, "pkg.mod.colour", 2, {}) is None
    assert hint_row(db, "pkg.mod.colour", 2, None) is None
