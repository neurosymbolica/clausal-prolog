"""The compiler's cut: a `nodes.Cut()` in a clause body compiles to
"continuation, then leave the clause exhausted", and cut-free bodies
compile byte-identically to before (the new ctx fields are read by the Cut
arm alone)."""
from __future__ import annotations

import ast

import pytest

from clausal.logic.compiler import compile_predicate_trampoline, compile_predicate_trampoline_ast
from clausal.logic.database import Clause, Database
from clausal.logic.variables import Var
from clausal.pythonic_ast import nodes
from clausal.pythonic_ast.nodes import StarUnpack
from clausal.terms import Call, LoadName


def _call(name, *args):
    return Call(func=LoadName(name=name), args=list(args), kwargs=[])


def _p_facts(db):
    for v in (1, 2, 3):
        db.assertz(Clause(head=("p", v), body=[]))


def _answers(db, functor, arity, *args):
    """All answers of functor(args...) through the compiled dispatch."""
    from clausal.logic.trampoline import StepGenerator, solutions
    from clausal.logic.variables import Trail, deref
    fn = db.get_dispatch(functor, arity)
    trail = Trail()
    sg = StepGenerator(fn, None, None, None, *args, trail)
    return solutions(sg, snapshot=lambda: tuple(deref(a) for a in args))


def test_cut_after_a_call_commits_and_skips_later_clauses():
    db = Database()
    _p_facts(db)
    x = Var()
    db.assertz(Clause(head=("q", x), body=[_call("p", x), nodes.Cut(), _call(">", x, 0)]))
    db.assertz(Clause(head=("q", 9), body=[]))
    for f, a in (("p", 1), ("q", 1)):
        compile_predicate_trampoline(f, a, db.clauses_for(f, a), db)
    assert _answers(db, "q", 1, Var()) == [(1,)]


def test_cut_in_a_disjunction_is_transparent():
    db = Database()
    x = Var()
    db.assertz(Clause(head=("r", x), body=[nodes.Or(left=nodes.Unify(left=x, right=1), right=nodes.Unify(left=x, right=2)), nodes.Cut()]))
    db.assertz(Clause(head=("r", 3), body=[]))
    compile_predicate_trampoline("r", 1, db.clauses_for("r", 1), db)
    assert _answers(db, "r", 1, Var()) == [(1,)]


def test_cut_inside_once_is_local():
    db = Database()
    _p_facts(db)
    x = Var()
    db.assertz(Clause(head=("s", x), body=[_call("once", nodes.TupleLiteral(elements=[_call("p", x), nodes.Cut()])), _call(">", x, 0)]))
    db.assertz(Clause(head=("s", 9), body=[]))
    for f, a in (("p", 1), ("s", 1)):
        compile_predicate_trampoline(f, a, db.clauses_for(f, a), db)
    assert _answers(db, "s", 1, Var()) == [(1,), (9,)]


def test_cut_inside_naf_is_local():
    db = Database()
    _p_facts(db)
    x = Var()
    db.assertz(Clause(head=("n", x), body=[nodes.Not(operand=nodes.Not(operand=nodes.TupleLiteral(elements=[_call("p", x), nodes.Cut()]))), nodes.Unify(left=x, right="ok")]))
    for f, a in (("p", 1), ("n", 1)):
        compile_predicate_trampoline(f, a, db.clauses_for(f, a), db)
    assert _answers(db, "n", 1, Var()) == [("ok",)]


def test_cut_in_a_single_clause_index_bucket_skips_the_fallback():
    """skip_trail=True arms have no `_mark`: the exit must not undo one.
    Four clauses: first-argument indexing starts at ``_INDEX_THRESHOLD``
    (4), and the `a` and `c` buckets are single-clause (skip_trail)."""
    db = Database()
    db.assertz(Clause(head=("one", "a", 1), body=[nodes.Cut()]))
    db.assertz(Clause(head=("one", "b", 2), body=[]))
    db.assertz(Clause(head=("one", "b", 3), body=[]))
    db.assertz(Clause(head=("one", "c", 4), body=[]))
    compile_predicate_trampoline("one", 2, db.clauses_for("one", 2), db)
    assert _answers(db, "one", 2, "a", Var()) == [("a", 1)]
    assert _answers(db, "one", 2, "b", Var()) == [("b", 2), ("b", 3)]
    assert _answers(db, "one", 2, Var(), Var()) == [("a", 1)]


def test_cut_in_a_clause_with_no_head_vars_gets_its_mark():
    """An arm with no head vars emits no `_mark` when cut-free; a cut-bearing
    one must emit it, since the exit undoes it."""
    db = Database()
    _p_facts(db)
    db.assertz(Clause(head="t0", body=[_call("p", Var()), nodes.Cut()]))
    db.assertz(Clause(head="t0", body=[]))
    for f, a in (("p", 1), ("t0", 0)):
        compile_predicate_trampoline(f, a, db.clauses_for(f, a), db)
    assert _answers(db, "t0", 0) == [()]


def test_cut_leaves_the_trail_balanced():
    from clausal.logic.trampoline import StepGenerator, solutions
    from clausal.logic.variables import Trail
    db = Database()
    _p_facts(db)
    x = Var()
    db.assertz(Clause(head=("q", x), body=[_call("p", x), nodes.Cut()]))
    for f, a in (("p", 1), ("q", 1)):
        compile_predicate_trampoline(f, a, db.clauses_for(f, a), db)
    trail = Trail()
    before = trail.mark()
    solutions(StepGenerator(db.get_dispatch("q", 1), None, None, None, Var(), trail))
    assert trail.mark() == before


def test_cut_free_codegen_is_unchanged():
    """Pin: a cut-free body never reads the new ctx fields.  The funcdef must
    contain no `Return` statement (the exit's signature) and no `cut_exit`."""
    db = Database()
    x, t, l, r = Var(), Var(), Var(), Var()
    db.assertz(Clause(head=("app", [], l, l), body=[]))
    db.assertz(Clause(head=("app", [x, StarUnpack(value=t)], l, [x, StarUnpack(value=r)]),
                      body=[_call("app", t, l, r)]))
    fd = compile_predicate_trampoline_ast("app", 3, db.clauses_for("app", 3), db)
    assert not any(isinstance(n, ast.Return) for n in ast.walk(fd))


def test_cut_outside_a_barrier_is_a_compiler_error():
    from clausal.logic.compiler._lower_goalop_shared import lower_shared
    from clausal.logic.compiler.compile_ctx import CompilationContext
    from clausal.logic.compiler.strategy import TrampolineStrategy
    from clausal.logic.compiler import ir
    ctx = CompilationContext(db=None, var_context={}, trail_name="trail", strategy=TrampolineStrategy(), cut_exit=None)
    with pytest.raises(ir.CompilerError, match="barrier"):
        lower_shared(ir.Cut(), ctx, [], lambda op, c, k: [])
