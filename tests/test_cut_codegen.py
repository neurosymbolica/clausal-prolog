"""The compiler's cut: a `nodes.Cut()` in a clause body compiles to
"continuation, then leave the clause exhausted", and cut-free bodies
compile byte-identically to before (the new ctx fields are read by the Cut
arm alone)."""
from __future__ import annotations

import ast
from pathlib import Path

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


_CUT_FREE_SNAPSHOT = Path(__file__).parent / "fixtures" / "cut_free_codegen.txt"


def _cut_free_program():
    """Cut-free predicates covering every place the cut work touched:
    list dispatch (app, nrev, mem), arms with no head vars holding once /
    findall / \\+ sub-generators (z, w, k), a first-argument index with
    single-clause buckets (col), loop-mode TRO (cnt), and a shallow build."""
    from clausal.terms import Evaluate, Gt, Sub
    db = Database()
    _p_facts(db)
    x, t, l, r = Var(), Var(), Var(), Var()
    db.assertz(Clause(head=("app", [], l, l), body=[]))
    db.assertz(Clause(head=("app", [x, StarUnpack(value=t)], l, [x, StarUnpack(value=r)]),
                      body=[_call("app", t, l, r)]))
    h, t, rr, rt = Var(), Var(), Var(), Var()
    db.assertz(Clause(head=("nrev", [], []), body=[]))
    db.assertz(Clause(head=("nrev", [h, StarUnpack(value=t)], rr),
                      body=[_call("nrev", t, rt), _call("app", rt, [h], rr)]))
    x = Var()
    db.assertz(Clause(head=("mem", x, [x, StarUnpack(value=Var())]), body=[]))
    x, t = Var(), Var()
    db.assertz(Clause(head=("mem", x, [Var(), StarUnpack(value=t)]), body=[_call("mem", x, t)]))
    db.assertz(Clause(head="z", body=[_call("once", _call("mem", Var(), [1]))]))
    x, lst = Var(), Var()
    db.assertz(Clause(head=("w", lst), body=[_call("findall", x, _call("mem", x, [1, 2]), lst)]))
    db.assertz(Clause(head="k", body=[nodes.Not(operand=_call("p", 9))]))
    for key, v in (("red", 1), ("green", 2), ("blue", 3), ("red", 4), ("black", 5)):
        db.assertz(Clause(head=("col", key, v), body=[]))
    n, n1 = Var(), Var()
    db.assertz(Clause(head=("cnt", 0), body=[]))
    db.assertz(Clause(head=("cnt", n), body=[
        Gt(left=n, right=0), Evaluate(left=n1, right=Sub(left=n, right=1)), _call("cnt", n1)]))
    return db, [("p", 1), ("app", 3), ("nrev", 2), ("mem", 2), ("z", 0), ("w", 1),
                ("k", 0), ("col", 2), ("cnt", 1)]


def _cut_free_dump() -> str:
    from clausal.logic.compiler import compile_predicate_shallow_ast
    db, preds = _cut_free_program()
    out = []
    for f, a in preds:
        for i, code in enumerate(_compile_capturing(db, f, a)):
            out.append(f"### {f}/{a} trampoline #{i}\n{code}\n")
    for f, a in (("z", 0), ("k", 0), ("col", 2)):
        fd = compile_predicate_shallow_ast(f, a, db.clauses_for(f, a), db)
        out.append(f"### {f}/{a} shallow\n{ast.unparse(fd)}\n")
    return _normalise_var_names("\n".join(out))


def _normalise_var_names(text: str) -> str:
    """Generated variable names (`_v<id>`) carry process-global Var ids;
    renumber them by first appearance so the dump is stable."""
    import re
    seen: dict[str, str] = {}
    return re.sub(r"\b_v(\d+)", lambda m: seen.setdefault(m.group(1), f"_v{len(seen)}"), text)


def test_cut_free_codegen_is_unchanged():
    """Byte-identity: cut-free predicates compile to exactly what the
    compiler emitted before cut existed.  The snapshot was generated by
    `_cut_free_dump` running on the pre-cut engine (a7484a4b); regenerate it
    only for a deliberate codegen change, never to absorb a cut-related one.
    Also pins directly that an arm with no head vars holding a `once`
    sub-generator (whose def ends in `return`) gets no trail mark."""
    got = _cut_free_dump()
    assert got == _CUT_FREE_SNAPSHOT.read_text()
    z = got.split("### z/0 trampoline #0\n", 1)[1].split("###", 1)[0]
    assert "_mark" not in z and "_once_gen" in z


def test_cut_outside_a_barrier_is_a_compiler_error():
    from clausal.logic.compiler._lower_goalop_shared import lower_shared
    from clausal.logic.compiler.compile_ctx import CompilationContext
    from clausal.logic.compiler.strategy import TrampolineStrategy
    from clausal.logic.compiler import ir
    ctx = CompilationContext(db=None, var_context={}, trail_name="trail", strategy=TrampolineStrategy(), cut_exit=None)
    with pytest.raises(ir.CompilerError, match="barrier"):
        lower_shared(ir.Cut(), ctx, [], lambda op, c, k: [])


# ── Cut before a tail-recursion-optimised call ──────────────────────────────
#
# Reference answers: Scryer (scryer-prolog, stdin </dev/null) on the same
# programs written as `.pl` (answer counts):
#   walk([_|T]) :- !, walk(T).  walk([]).            walk([1,2,3]): 1
#   walk([]).  walk([_|T]) :- !, walk(T).            walk([1,2,3]): 1
#   wn([_|T]) :- p(_), !, wn(T).  wn([]).            wn([1,2,3]): 1
#   wa([_|T]) :- _ = 1, wa(T).  wa(_) :- !.          wa([1,2]): 3
#   cnt(N) :- N > 0, !, N1 is N-1, cnt(N1).  cnt(0).          cnt(100000): 1
#   cnt(0).  cnt(N) :- N > 0, !, N1 is N-1, cnt(N1).          cnt(100000): 1
#   lwn(go,[_|T]) :- p(_), !, lwn(go,T).  lwn(go,[]).  lwn(x,_).  lwn(y,_).
#                                                    lwn(go,[1,2,3]): 1
#
# A cut is a deterministic prefix goal, so `!, tail` is TRO-eligible; each
# TRO test also pins that the in-place restart is really emitted.  The deep
# runs use an integer counter: a Python-list head pattern `[_|T]` copies the
# tail on every step (quadratic with or without a cut), so `walk` stays short.

_DEEP = 100000


def _compile_capturing(db, functor, arity):
    """Compile through the full trampoline path; return every funcdef built
    (top function, buckets, fallbacks) unparsed."""
    from clausal.logic.compiler import predicate as P
    seen: list[str] = []
    orig = P.functiondef_to_function

    def hook(fd, *a, **k):
        seen.append(ast.unparse(fd))
        return orig(fd, *a, **k)

    P.functiondef_to_function = hook
    try:
        compile_predicate_trampoline(functor, arity, db.clauses_for(functor, arity), db)
    finally:
        P.functiondef_to_function = orig
    return seen


def _cons():
    t = Var()
    return [Var(), StarUnpack(value=t)], t


def _in_order(db, rec, base, rec_first):
    for c in ((rec, base) if rec_first else (base, rec)):
        db.assertz(c)


def _cnt_clauses(name):
    from clausal.terms import Evaluate, Gt, Sub
    n, n1 = Var(), Var()
    rec = Clause(head=(name, n), body=[
        Gt(left=n, right=0), nodes.Cut(),
        Evaluate(left=n1, right=Sub(left=n, right=1)), _call(name, n1)])
    return rec, Clause(head=(name, 0), body=[])


_ORDERS = pytest.mark.parametrize("rec_first", [True, False], ids=["recursive-first", "base-first"])


@_ORDERS
def test_cut_before_a_loop_mode_tro_tail_list(rec_first):
    db = Database()
    pat, t = _cons()
    _in_order(db, Clause(head=("walk", pat), body=[nodes.Cut(), _call("walk", t)]),
              Clause(head=("walk", []), body=[]), rec_first)
    code = _compile_capturing(db, "walk", 1)
    assert any("_tro = True" in c for c in code), "the cut-bearing tail lost TRO"
    assert _answers(db, "walk", 1, [1, 2, 3]) == [([1, 2, 3],)]
    assert len(_answers(db, "walk", 1, list(range(500)))) == 1


@_ORDERS
def test_cut_before_a_loop_mode_tro_tail_runs_deep(rec_first):
    db = Database()
    _in_order(db, *_cnt_clauses("cnt"), rec_first)
    code = _compile_capturing(db, "cnt", 1)
    assert any("_tro = True" in c for c in code), "the cut-bearing tail lost TRO"
    assert _answers(db, "cnt", 1, 5) == [(5,)]
    assert len(_answers(db, "cnt", 1, _DEEP)) == 1


def test_cut_after_a_nondeterministic_goal_before_the_tail():
    db = Database()
    _p_facts(db)
    pat, t = _cons()
    db.assertz(Clause(head=("wn", pat), body=[_call("p", Var()), nodes.Cut(), _call("wn", t)]))
    db.assertz(Clause(head=("wn", []), body=[]))
    for f, a in (("p", 1), ("wn", 1)):
        compile_predicate_trampoline(f, a, db.clauses_for(f, a), db)
    assert _answers(db, "wn", 1, [1, 2, 3]) == [([1, 2, 3],)]
    assert len(_answers(db, "wn", 1, list(range(300)))) == 1


def test_cut_in_a_later_clause_keeps_an_earlier_clauses_tro_restart():
    """The first arm takes the restart; the second arm's cut must not drop
    it.  (The engine runs the later arm before the restart, as it does
    without a cut, so only the answer COUNT is compared.)"""
    db = Database()
    pat, t = _cons()
    db.assertz(Clause(head=("wa", pat), body=[nodes.Unify(left=Var(), right=1), _call("wa", t)]))
    db.assertz(Clause(head=("wa", Var()), body=[nodes.Cut()]))
    code = _compile_capturing(db, "wa", 1)
    assert any("_tro = True" in c for c in code)
    assert len(_answers(db, "wa", 1, [1, 2])) == 3
    assert len(_answers(db, "wa", 1, list(range(300)))) == 301


@_ORDERS
def test_cut_before_a_signal_mode_tro_tail(rec_first):
    """A signal-mode (index bucket) TRO arm.  Built directly: the index
    path's TRO recompute names the BUCKET function as the functor, so no
    bucket clause is TRO-eligible through `compile_predicate_trampoline`
    today.  The dispatch loop below is the shape of `arg_index`'s: drive the
    bucket through `_drive_tro_bucket`, re-dispatch on a pending tail."""
    from clausal.codegen import functiondef_to_function
    from clausal.logic.compiler import DONE
    from clausal.logic.compiler.arg_index import _drive_tro_bucket
    from clausal.logic.compiler.compile_ctx import CompilationContext
    from clausal.logic.compiler.goal_trampoline import _make_body_compiler_trampoline
    from clausal.logic.compiler.predicate import _build_predicate_trampoline_funcdef
    from clausal.logic.compiler.strategy import TrampolineStrategy
    from clausal.logic.trampoline import StepGenerator, solutions
    from clausal.logic.variables import Trail
    db = Database()
    rec, base = _cnt_clauses("cnt")
    _in_order(db, rec, base, rec_first)
    clauses = db.clauses_for("cnt", 1)
    compile_predicate_trampoline("cnt", 1, clauses, db)
    g = dict(db.get_dispatch("cnt", 1).__globals__)
    ctx = CompilationContext(db=db, var_context={}, trail_name="trail", strategy=TrampolineStrategy())
    ctx.base_globals = g
    fd = _build_predicate_trampoline_funcdef(
        "cnt", 1, clauses, db, _make_body_compiler_trampoline(db, ctx_template=ctx),
        emit_done=False, tro_indices=frozenset(i for i, c in enumerate(clauses) if c is rec),
        ctx_template=ctx)
    src = ast.unparse(fd)
    assert "$tro_state[0] = True" in src
    assert ctx.clause_mark_name == "_mark" and ctx.cut_tro_restart is None  # restored
    tro_state = [False, None]
    g["$tro_state"] = tro_state
    bucket = functiondef_to_function(fd, globals_=g)

    def dispatch(this, proceed, fail, catcher, a0, trail):
        args = [a0]
        while True:
            tro_state[0] = False
            pending = [False, None]
            yield from _drive_tro_bucket(
                bucket(this, proceed, fail, catcher, *args, trail), tro_state, 1, pending)
            if not pending[0]:
                break
            args = [pending[1]]
        yield (fail, DONE)

    for k in (5, _DEEP):
        assert len(solutions(StepGenerator(dispatch, None, None, None, k, Trail()))) == 1


def test_cut_after_a_nondeterministic_goal_in_an_index_bucket():
    db = Database()
    _p_facts(db)
    pat, t = _cons()
    db.assertz(Clause(head=("lwn", "go", pat), body=[_call("p", Var()), nodes.Cut(), _call("lwn", "go", t)]))
    db.assertz(Clause(head=("lwn", "go", []), body=[]))
    db.assertz(Clause(head=("lwn", "x", Var()), body=[]))
    db.assertz(Clause(head=("lwn", "y", Var()), body=[]))
    for f, a in (("p", 1), ("lwn", 2)):
        compile_predicate_trampoline(f, a, db.clauses_for(f, a), db)
    assert _answers(db, "lwn", 2, "go", [1, 2, 3]) == [("go", [1, 2, 3])]


# ── The shallow strategy's \+ is a barrier scope ────────────────────────────


def test_cut_inside_a_shallow_naf_is_local():
    """sh(X) :- X = 7, \\+ (!, fail).  sh(8).   Scryer: [7, 8].
    s0 :- \\+ (!, fail).                        Scryer: one answer."""
    from clausal.logic.compiler import compile_predicate_shallow
    from clausal.logic.variables import Trail, deref
    db = Database()
    x = Var()
    neg = nodes.Not(operand=nodes.TupleLiteral(elements=[nodes.Cut(), False]))
    db.assertz(Clause(head=("sh", x), body=[nodes.Unify(left=x, right=7), neg]))
    db.assertz(Clause(head=("sh", 8), body=[]))
    db.assertz(Clause(head="s0", body=[nodes.Not(operand=nodes.TupleLiteral(elements=[nodes.Cut(), False]))]))
    sh = compile_predicate_shallow("sh", 1, db.clauses_for("sh", 1), db)
    a = Var()
    assert [deref(a) for _ in sh(a, Trail(), None)] == [7, 8]
    s0 = compile_predicate_shallow("s0", 0, db.clauses_for("s0", 0), db)
    assert len(list(s0(Trail(), None))) == 1
