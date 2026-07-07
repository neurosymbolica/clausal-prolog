"""A03 compiler goals, control & specialization — adversarial audit tests (2026-07-05).

Findings ledger: docs/superpowers/audits/2026-07-05-fable-partition/03-compiler-goals/findings.md

Suspected-bug tests assert the *correct* behaviour and are marked
``@pytest.mark.xfail(strict=False)`` with the finding ID; confirmed-correct
behaviour is a plain regression guard.  Run PER FILE only:

    python -m pytest tests/audit_2026_07_05/test_03_compiler_goals.py -v
"""
import inspect

import pytest

from clausal.import_hook import _load_module
from clausal.logic import solve as solve_mod
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref, is_var, walk


# ── Fixture module ────────────────────────────────────────────────────────────
# All predicates live in ONE module (atoms/functors are module-scoped; a second
# load would mint distinct functor classes that never unify with the first).

FIXTURE = '''
-import_from(clausal.examples.metainterpreters, [Solve, SolveCount, SolveLimit, SolveTree])
-private([kab(KA)])

# ── A03-F001: TRO with nondeterministic prefix goals ──────────────────
# member prefix (MemberIn wrongly classed deterministic)
trm(0, ACC, ACC),
trm(N, ACC, OUT) <- (N > 0, X in [1, 2], N1 := N - 1, ACC1 := ACC + X, trm(N1, ACC1, OUT))

# undetermined If prefix (Branch wrongly classed deterministic)
tri(0, ACC, ACC),
tri(N, ACC, OUT) <- (N > 0, If(C is 1, X := 5, X := 7), N1 := N - 1, ACC1 := ACC + X, tri(N1, ACC1, OUT))

# atom_concat split-mode prefix (wrongly in _DETERMINISTIC_BUILTINS)
tac(0, ACC, ACC),
tac(N, ACC, OUT) <- (N > 0, atom_concat(P, Q, "ab"), N1 := N - 1, ACC1 is [P, *ACC], tac(N1, ACC1, OUT))

# shallow twins = differential oracle (ShallowStrategy has no TRO)
-shallow([strm/3, stri/3, swk5/3, sfee/2])
strm(0, ACC, ACC),
strm(N, ACC, OUT) <- (N > 0, X in [1, 2], N1 := N - 1, ACC1 := ACC + X, strm(N1, ACC1, OUT))
stri(0, ACC, ACC),
stri(N, ACC, OUT) <- (N > 0, If(C is 1, X := 5, X := 7), N1 := N - 1, ACC1 := ACC + X, stri(N1, ACC1, OUT))

# non-tail controls (Unify after the self-call disables TRO)
trn(0, ACC, ACC),
trn(N, ACC, OUT) <- (N > 0, X in [1, 2], N1 := N - 1, ACC1 := ACC + X, trn(N1, ACC1, OUT0), OUT is OUT0)
trin(0, ACC, ACC),
trin(N, ACC, OUT) <- (N > 0, If(C is 1, X := 5, X := 7), N1 := N - 1, ACC1 := ACC + X, trin(N1, ACC1, OUT0), OUT is OUT0)

# deterministic TRO regression guards
cnt(0, ACC, ACC),
cnt(N, ACC, OUT) <- (N > 0, N1 := N - 1, ACC1 := ACC + N, cnt(N1, ACC1, OUT))
trob(0, ACC, ACC),
trob(N, ACC, OUT) <- (N > 0, once(in_(X, [5, 6])), N1 := N - 1, ACC1 := ACC + X, trob(N1, ACC1, OUT))
# catch prefix is non-deterministic per the table → TRO off, still correct
ctp(0, ACC, ACC),
ctp(N, ACC, OUT) <- (N > 0, catch(X is 1, _, X is 2), N1 := N - 1, ACC1 := ACC + X, ctp(N1, ACC1, OUT))

# ── A03-F002: destructive reuse behind nondeterministic prefixes ─────
drm(OUT) <- (SRC is [1, 2], X in [10, 20], append(SRC, [X], OUT))
drb(OUT) <- (SRC is [1, 2], If(C is 1, X is 10, X is 20), append(SRC, [X], OUT))
# controls: live-after source (DR off) and deterministic prefix (intended DR)
drmc(OUT) <- (SRC is [1, 2], X in [10, 20], append(SRC, [X], OUT), length(SRC, _))
drok(OUT) <- (SRC is [1, 2], append(SRC, [3], OUT))

# ── A03-F003: signal-mode TRO bucket compiles to a non-generator ─────
# 4 clauses → indexed; the var-headed TRO clause sits ALONE in the default
# bucket, whose funcdef then contains no yield at all.
idx(0, "z0"),
idx(90, "n90"),
idx(80, "n80"),
idx(N, R) <- (N > 0, N < 50, N1 := N - 1, idx(N1, R))

# control: a second var-headed (non-TRO) clause puts a yield in the bucket
jdx(0, "z0"),
jdx(90, "n90"),
jdx(80, "n80"),
jdx(M, "big") <- (M > 100),
jdx(N, R) <- (N > 0, N < 50, N1 := N - 1, jdx(N1, R))

# TRO + check_indices + indexing, list heads — correct-behaviour guard
wk5([], ACC, ACC),
wk5([9], 9, "nine"),
wk5([8], 8, "eight"),
wk5([H, *T], ACC, OUT) <- (ACC1 := ACC + H, wk5(T, ACC1, OUT))
swk5([], ACC, ACC),
swk5([9], 9, "nine"),
swk5([8], 8, "eight"),
swk5([H, *T], ACC, OUT) <- (ACC1 := ACC + H, swk5(T, ACC1, OUT))

# ── A03-F004: catch with declared-functor catcher ─────────────────────
boom(X) <- (X > 0, throw(kab(X)))
wboom(X) <- boom(X)
cfun(N, R) <- catch(throw(kab(7)), kab(N), R is "caught")
cchain(N, R) <- catch(wboom(5), kab(N), R is "caught")
cvar(R) <- catch(wboom(5), _E, R is "caught")
cstr(R) <- catch(throw("bang"), "bang", R is "caught")
targ(C, R) <- catch(throw(kab(7)), C, R is "caught")

# ── A03-F005/F006: setof sort, findall template freshness ────────────
so(L) <- setof(X5, in_(X5, [3, 1, 3, 2]), L)
fat2(L, Y) <- (findall([X, Y], in_(X, [1, 2]), L), Y is 9)
fa(L) <- findall(X2, in_(X2, [3, 1, 3, 2]), L)
bg(L) <- bagof(X3, in_(X3, [3, 1, 3, 2]), L)
bge(L) <- bagof(X4, in_(X4, []), L)

# ── control constructs — regression guards ────────────────────────────
onc(X, Y) <- (once(in_(X, [1, 2, 3])), in_(Y, ["a", "b"]))
oncf(X) <- (once(in_(X, [])), X is 1)
cn3(X) <- call_nth(in_(X, [10, 20, 30]), 2)
ca(N) <- count_all(in_(_, [5, 6, 7]), N)
cawrong() <- count_all(in_(_, [1, 2]), 5)
sccb(T, A) <- (setup_call_cleanup(T is 1, True, True), A is T)
sccf(X) <- (setup_call_cleanup(X is 1, False, True) or X is 2)
ce1(R) <- (catch_error(throw("x"), E), R is "sw")
cr1(R) <- catch_recover(throw("x"), E2, R is "rec")
crec(R) <- catch(throw("p"), "p", in_(R, [1, 2]))
cmiss(R) <- catch(throw("other"), "bang", R is "x")
fal() <- forall(in_(X6, [1, 2, 3]), X6 > 0)
falf() <- forall(in_(X7, [1, 2, 3]), X7 > 1)
fz(X, R) <- (freeze(X, R is "fired"), X is 1)
wgr(X, R) <- (when(ground(X), R is "g"), X is 5)
wand(WX, WY, R) <- (when((nonvar(WX), ground(WY)), R is "both"), WX is 1, WY is 2)

# ── reified / general ITE — regression guards ─────────────────────────
ifu(X) <- If(C is 1, X is "then", X is "else")
ifn(X, Y) <- (If(A is 1, X is "t", X is "e"), If(B is 1, Y is "t", Y is "e"))
clfd(X, L) <- If(X >= 0, L is "pos", L is "neg")
cldif(X, L) <- If(X is not 3, L is "ne", L is "eq")
mem2(X) <- (X in [1, 2])
gen("a"),
gen("b"),
gen("c"),
altif(X, R) <- If(gen(X), R is "yes", R is "no")

# ── continuation-TCO — regression guards ──────────────────────────────
w(X) <- gen(X)
w2(X) <- w(X)
alt(X) <- (gen(X) or w(X))
items2(1, [2, 3]),
items2(7, [8]),
sp2([H, *T]) <- items2(H, T)
k4(1, "a"),
k4(1, "b"),
k4(2, "c"),
k4(9, "d"),
k4(8, "e"),
wk(R) <- k4(1, R)

# disjoint-guard pair, shallow vs trampoline parity
sfee(DAYS, FEE) <- (DAYS >= 25, FEE == 75)
sfee(DAYS, FEE) <- (DAYS >= 0, DAYS < 25, FEE == 3 * DAYS)
tfee(DAYS, FEE) <- (DAYS >= 25, FEE == 75)
tfee(DAYS, FEE) <- (DAYS >= 0, DAYS < 25, FEE == 3 * DAYS)

# ── tabled ITE / NAF ──────────────────────────────────────────────────
-table(Path/2)
Edge(1, 2),
Edge(2, 3),
Edge(3, 1),
Path(PA, PB) <- Edge(PA, PB)
Path(PA, PB) <- (Edge(PA, PC), Path(PC, PB))
CheckPath(CX, RESULT) <- If(Path(1, CX), RESULT is "reachable", RESULT is "unreachable")
NotPath(NX) <- (not Path(1, NX))

# ── specialization ────────────────────────────────────────────────────
MatchClause(GOAL, FRESH_BODY, PROGRAM) <- (
    CLAUSE in PROGRAM,
    copy_term(CLAUSE, [FRESH_HEAD, FRESH_BODY]),
    GOAL is FRESH_HEAD,
)

NatProg(PROGRAM) <- (
    PROGRAM is [
        [["natnum", 0], []],
        [["natnum", ["s", NX2]], [["natnum", NX2]]]
    ]
)
GraphProg(PROGRAM) <- (
    PROGRAM is [
        [["edge", "a", "b"], []],
        [["edge", "b", "c"], []],
        [["edge", "b", "d"], []],
        [["path", GX, GY], [["edge", GX, GY]]],
        [["path", GX, GY], [["edge", GX, GZ], ["path", GZ, GY]]]
    ]
)
ConstProg(PROGRAM) <- (
    PROGRAM is [
        [["f", 1], []],
        [["g"], [["f", 2]]]
    ]
)
FactProg(PROGRAM) <- (
    PROGRAM is [
        [["fact", 0, 1], []],
        [["fact", FN, FF], [["gt", FN, 0], ["sub", FN, 1, FN1], ["fact", FN1, FF1], ["mul", FN, FF1, FF]]]
    ]
)

# A03-F007: MI with goals BETWEEN MatchClause and the recursive call
SolveGuard([], _PROGRAM, _LIM),
SolveGuard([GOAL, *GOALS], PROGRAM, LIM) <- (
    MatchClause(GOAL, BODY, PROGRAM),
    LIM > 0,
    append(BODY, GOALS, ALL_GOALS),
    LIM1 := LIM - 1,
    SolveGuard(ALL_GOALS, PROGRAM, LIM1),
)
-specialize(SolveGuard, NatProg, alias=SolveGuardNat)

# A03-F008: deep unfolding vs single-clause functor with constant arg
-specialize(Solve, ConstProg, alias=ConstShallow)
-specialize(Solve, ConstProg, alias=ConstDeep, depth=5)

# A03-F009: CPD + counting-extension chaining
-specialize(SolveCount, GraphProg, alias=CountGraph)
-specialize(SolveCount, GraphProg, alias=CountGraphCPD, cpd=True)
-specialize(Solve, GraphProg, alias=GraphSpec)
-specialize(Solve, GraphProg, alias=GraphCPD, cpd=True)

# regression guards: limit (pre-match), tree (split), residual builtins
-specialize(SolveLimit, NatProg, alias=LimNat)
-specialize(SolveTree, GraphProg, alias=TreeGraph)
-specialize(Solve, FactProg, alias=FactSpec)
'''


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    p = tmp_path_factory.mktemp("a03") / "a03_fixture.clausal"
    p.write_text(FIXTURE)
    return _load_module("a03_audit_fixture", str(p))


def sols(mod, goal, *outvars, limit=None):
    """Solutions of goal as tuples of walked outvars (query cache cleared)."""
    from clausal import solve
    solve_mod._query_cache.clear()
    res = []
    for _tr in solve(goal, mod):
        res.append(tuple(walk(deref(v)) for v in outvars))
        if limit and len(res) >= limit:
            break
    return res


def has_sol(mod, goal):
    from clausal import solve
    solve_mod._query_cache.clear()
    for _ in solve(goal, mod):
        return True
    return False


NAT3 = [["natnum", ["s", ["s", ["s", 0]]]]]


def _program(mod, source_pred):
    from clausal import solve
    solve_mod._query_cache.clear()
    v = Var()
    for _ in solve(source_pred(v), mod):
        return walk(deref(v))
    raise AssertionError("program source failed")


# ── A03-F001 — TRO loses solutions behind nondeterministic prefixes ──────────


class TestF001TroNondetPrefix:
    @pytest.mark.xfail(strict=False, reason="A03-F001: MemberIn prefix wrongly deterministic → TRO drops solutions")
    def test_member_prefix_all_solutions(self, mod):
        O = Var()
        assert sorted(sols(mod, mod.trm(2, 0, O), O)) == [(2,), (3,), (3,), (4,)]

    @pytest.mark.xfail(strict=False, reason="A03-F001: undetermined If (Branch) prefix wrongly deterministic")
    def test_branch_prefix_all_solutions(self, mod):
        O = Var()
        assert sorted(sols(mod, mod.tri(1, 0, O), O)) == [(5,), (7,)]

    @pytest.mark.xfail(strict=False, reason="A03-F001: atom_concat/3 split mode is nondet but in _DETERMINISTIC_BUILTINS")
    def test_atom_concat_prefix_all_solutions(self, mod):
        O = Var()
        assert sorted(sols(mod, mod.tac(1, [], O), O)) == sorted([([""],), (["a"],), (["ab"],)])

    # controls / oracle
    def test_shallow_oracle_member(self, mod):
        O = Var()
        assert sorted(sols(mod, mod.strm(2, 0, O), O)) == [(2,), (3,), (3,), (4,)]

    def test_shallow_oracle_branch(self, mod):
        O = Var()
        assert sorted(sols(mod, mod.stri(1, 0, O), O)) == [(5,), (7,)]

    def test_non_tail_control_member(self, mod):
        O = Var()
        assert sorted(sols(mod, mod.trn(2, 0, O), O)) == [(2,), (3,), (3,), (4,)]

    def test_non_tail_control_branch(self, mod):
        O = Var()
        assert sorted(sols(mod, mod.trin(1, 0, O), O)) == [(5,), (7,)]

    def test_deterministic_tro_still_correct(self, mod):
        O = Var()
        assert sols(mod, mod.cnt(5, 0, O), O) == [(15,)]

    def test_deterministic_tro_deep_stack_safe(self, mod):
        O = Var()
        assert sols(mod, mod.cnt(3000, 0, O), O) == [(4501500,)]

    def test_once_prefix_is_deterministic_and_correct(self, mod):
        O = Var()
        assert sols(mod, mod.trob(2, 0, O), O) == [(10,)]

    def test_catch_prefix_blocks_tro_and_correct(self, mod):
        O = Var()
        assert sols(mod, mod.ctp(2, 0, O), O) == [(2,)]

    def test_analysis_marks_nondet_prefixes_ineligible(self, mod):
        """Direct analysis check: these clauses must NOT be TRO-eligible."""
        from clausal.logic.compiler.terms_to_goalop import terms_to_goalop
        from clausal.logic.compiler.optimisations import tro as tro_pass
        bad = []
        for name in ("trm", "tri", "tac"):
            cl = getattr(mod, name)._clauses[-1]
            plan = tro_pass.analyse(terms_to_goalop(cl.body, db=None), cl.head, name, 3)
            if plan.eligible:
                bad.append(name)
        if bad:
            pytest.xfail(f"A03-F001: TRO analysis wrongly eligible for {bad}")


# ── A03-F002 — destructive reuse corrupts containers on backtracking ─────────


class TestF002DestructiveReuseNondetPrefix:
    @pytest.mark.xfail(strict=False, reason="A03-F002: DR mutates dead-source list behind member prefix")
    def test_member_prefix_append(self, mod):
        O = Var()
        assert sols(mod, mod.drm(O), O) == [([1, 2, 10],), ([1, 2, 20],)]

    @pytest.mark.xfail(strict=False, reason="A03-F002: DR mutates dead-source list behind undetermined If")
    def test_branch_prefix_append(self, mod):
        O = Var()
        assert sols(mod, mod.drb(O), O) == [([1, 2, 10],), ([1, 2, 20],)]

    def test_live_after_source_is_safe(self, mod):
        O = Var()
        assert sols(mod, mod.drmc(O), O) == [([1, 2, 10],), ([1, 2, 20],)]

    def test_deterministic_prefix_dr_correct(self, mod):
        O = Var()
        assert sols(mod, mod.drok(O), O) == [([1, 2, 3],)]

    def test_analysis_flags_dict_put_and_set_union_too(self, mod):
        """The same determinism gate covers all _DR_CANDIDATES."""
        from clausal.terms import Call, LoadName, Unify, in_
        from clausal.logic.compiler.terms_to_goalop import terms_to_goalop
        from clausal.logic.compiler import destructive_reuse as dr
        SRC, X, OUT = Var(), Var(), Var()
        body = [Unify(left=SRC, right={"a": 1}),
                in_(left=X, right=[1, 2]),
                Call(func=LoadName(name="dict_put"), args=["k", X, SRC, OUT], kwargs=[])]
        eligible = dr.analyse_ir(terms_to_goalop(body, db=None), None)
        if eligible:
            pytest.xfail("A03-F002: dict_put DR-eligible behind MemberIn prefix")

    def test_alternate_prefix_blocks_dr(self, mod):
        from clausal.terms import Call, LoadName, Unify, Or
        from clausal.logic.compiler.terms_to_goalop import terms_to_goalop
        from clausal.logic.compiler import destructive_reuse as dr
        SRC, X, OUT = Var(), Var(), Var()
        body = [Unify(left=SRC, right=[1]),
                Or(left=Unify(left=X, right=1), right=Unify(left=X, right=2)),
                Call(func=LoadName(name="append"), args=[SRC, [X], OUT], kwargs=[])]
        assert dr.analyse_ir(terms_to_goalop(body, db=None), None) == set()


# ── A03-F003 — signal-mode TRO-only bucket is not a generator ────────────────


class TestF003TroSignalBucketNotGenerator:
    def test_dispatch_to_tro_only_bucket(self, mod):
        O = Var()
        assert sols(mod, mod.idx(3, O), O) == [("z0",)]

    def test_keyed_bucket_works(self, mod):
        O = Var()
        assert sols(mod, mod.idx(0, O), O) == [("z0",)]

    def test_bucket_with_extra_var_clause_works(self, mod):
        O = Var()
        assert sols(mod, mod.jdx(3, O), O) == [("z0",)]
        O2 = Var()
        assert sols(mod, mod.jdx(200, O2), O2) == [("big",)]

    def test_default_bucket_is_generator_function(self, mod):
        """The compiled default-bucket function must be a generator function."""
        disp = mod.idx._get_dispatch()
        bad = []
        for cell in disp.__closure__ or []:
            v = cell.cell_contents
            if isinstance(v, list):
                for item in v:
                    if isinstance(item, tuple) and len(item) == 3 and callable(item[2]):
                        if not inspect.isgeneratorfunction(item[2]):
                            bad.append(item[2].__name__)
        if bad:
            pytest.xfail(f"A03-F003: non-generator bucket fns {bad}")

    def test_interleaved_signal_mode_iterators(self, mod):
        from clausal import solve
        solve_mod._query_cache.clear()
        R1, R2 = Var(), Var()
        it1 = iter(solve(mod.jdx(3, R1), mod))
        it2 = iter(solve(mod.jdx(7, R2), mod))
        out = [(walk(deref(R1)), walk(deref(R2))) for _ in zip(it1, it2)]
        assert out == [("z0", "z0")]

    def test_tro_check_indices_with_indexing(self, mod):
        O1, O2 = Var(), Var()
        assert sols(mod, mod.wk5([1, 2, 3], 0, O1), O1) == [(6,)]
        assert sols(mod, mod.swk5([1, 2, 3], 0, O2), O2) == [(6,)]

    def test_tro_check_indices_keyed_overlap(self, mod):
        O = Var()
        assert sols(mod, mod.wk5([9], 9, O), O) == [("nine",), (18,)]


# ── A03-F004 — catch never matches declared-functor exception terms ──────────


class TestF004CatchFunctorCatcher:
    def test_functor_catcher_direct_throw(self, mod):
        N, R = Var(), Var()
        assert sols(mod, mod.cfun(N, R), N, R) == [(7, "caught")]

    def test_functor_catcher_through_chain(self, mod):
        N, R = Var(), Var()
        assert sols(mod, mod.cchain(N, R), N, R) == [(5, "caught")]

    def test_var_catcher_catches_through_chain(self, mod):
        R = Var()
        assert sols(mod, mod.cvar(R), R) == [("caught",)]

    def test_string_catcher_catches(self, mod):
        R = Var()
        assert sols(mod, mod.cstr(R), R) == [("caught",)]

    def test_instance_catcher_via_variable_arg_catches(self, mod):
        """Passing a pre-built functor instance as the catcher works —
        the compile-time Compound conversion is what breaks cfun."""
        N, R = Var(), Var()
        assert sols(mod, mod.targ(mod.kab(N), R), N, R) == [(7, "caught")]

    def test_compound_vs_instance_unify_is_the_root_cause(self, mod):
        from clausal.logic.variables import Trail, unify
        from clausal.terms import Compound
        inst = mod.kab(7)
        ok = unify(Compound("kab", (Var(),)), inst, Trail())
        if not ok:
            pytest.xfail("A03-F004: unify(Compound('kab',(N,)), kab(7)) is False")

    def test_rethrow_on_catcher_mismatch(self, mod):
        from clausal.logic.exceptions import LogicException
        with pytest.raises(LogicException):
            sols(mod, mod.cmiss(Var()))

    def test_nondeterministic_recovery(self, mod):
        R = Var()
        assert sols(mod, mod.crec(R), R) == [(1,), (2,)]

    def test_catch_error_and_catch_recover(self, mod):
        R = Var()
        assert sols(mod, mod.ce1(R), R) == [("sw",)]
        R2 = Var()
        assert sols(mod, mod.cr1(R2), R2) == [("rec",)]


# ── A03-F005 / A03-F006 — setof sort, findall template freshness ─────────────


class TestF005F006FindallFamily:
    def test_setof_is_sorted(self, mod):
        L = Var()
        assert sols(mod, mod.so(L), L) == [([1, 2, 3],)]

    def test_setof_dedups(self, mod):
        L = Var()
        [(got,)] = sols(mod, mod.so(L), L)
        assert sorted(got) == [1, 2, 3] and len(got) == 3

    def test_findall_free_vars_are_fresh_per_solution(self, mod):
        L, Y = Var(), Var()
        [(got, _y)] = sols(mod, mod.fat2(L, Y), L, Y)
        # ISO: rows carry fresh variables, NOT the later-bound value 9
        assert not all(row[1] == 9 for row in got)

    def test_findall_order_and_duplicates(self, mod):
        L = Var()
        assert sols(mod, mod.fa(L), L) == [([3, 1, 3, 2],)]

    def test_bagof_keeps_duplicates_fails_on_empty(self, mod):
        L = Var()
        assert sols(mod, mod.bg(L), L) == [([3, 1, 3, 2],)]
        L2 = Var()
        assert sols(mod, mod.bge(L2), L2) == []


# ── A03-F007/F008/F009 — specialization ──────────────────────────────────────


class TestF007SpecializationDropsMidBodyGoals:
    def test_generic_mi_respects_guard(self, mod):
        prog = _program(mod, mod.NatProg)
        assert not has_sol(mod, mod.SolveGuard(NAT3, prog, 1))
        assert has_sol(mod, mod.SolveGuard(NAT3, prog, 10))

    @pytest.mark.xfail(strict=False, reason="A03-F007: goals between MatchClause and recursive call silently dropped")
    def test_specialized_mi_respects_guard(self, mod):
        assert not has_sol(mod, mod.SolveGuardNat(NAT3, 1))

    def test_specialized_mi_succeeds_within_limit(self, mod):
        assert has_sol(mod, mod.SolveGuardNat(NAT3, 10))


class TestF008DeepUnfoldConstantCheck:
    def test_generic_and_shallow_spec_fail(self, mod):
        prog = _program(mod, mod.ConstProg)
        assert not has_sol(mod, mod.Solve([["g"]], prog))
        assert not has_sol(mod, mod.ConstShallow([["g"]]))

    @pytest.mark.xfail(strict=False, reason="A03-F008: deep unfold inlines single clause without checking constant args")
    def test_deep_spec_fails_like_generic(self, mod):
        assert not has_sol(mod, mod.ConstDeep([["g"]]))


class TestF009CpdExtensionChaining:
    def test_plain_cpd_matches_generic(self, mod):
        prog = _program(mod, mod.GraphProg)
        Y1, Y2, Y3 = Var(), Var(), Var()
        gen = sorted(sols(mod, mod.Solve([["path", "a", Y1]], prog), Y1))
        spec = sorted(sols(mod, mod.GraphSpec([["path", "a", Y2]]), Y2))
        cpd = sorted(sols(mod, mod.GraphCPD([["path", "a", Y3]]), Y3))
        assert spec == gen == [("b",), ("c",), ("d",)]
        assert cpd == gen

    def test_counting_spec_matches_generic(self, mod):
        prog = _program(mod, mod.GraphProg)
        Y1, C1, Y2, C2 = Var(), Var(), Var(), Var()
        gen = sorted(sols(mod, mod.SolveCount([["path", "a", Y1]], prog, C1), Y1, C1))
        spec = sorted(sols(mod, mod.CountGraph([["path", "a", Y2]], C2), Y2, C2))
        assert spec == gen == [("b", 2), ("c", 4), ("d", 4)]

    @pytest.mark.xfail(strict=False, reason="A03-F009: CPD chaining emits duplicate Evaluate targets; deep solutions lost")
    def test_cpd_counting_matches_generic(self, mod):
        Y, C = Var(), Var()
        got = sorted(sols(mod, mod.CountGraphCPD([["path", "a", Y]], C), Y, C))
        assert got == [("b", 2), ("c", 4), ("d", 4)]


class TestSpecializationRegressionGuards:
    def test_limit_pre_match_goals_preserved(self, mod):
        prog = _program(mod, mod.NatProg)
        assert not has_sol(mod, mod.SolveLimit(NAT3, prog, 2))
        assert not has_sol(mod, mod.LimNat(NAT3, 2))
        assert has_sol(mod, mod.SolveLimit(NAT3, prog, 9))
        assert has_sol(mod, mod.LimNat(NAT3, 9))

    def test_split_style_proof_trees_equal(self, mod):
        prog = _program(mod, mod.GraphProg)
        Y1, T1, Y2, T2 = Var(), Var(), Var(), Var()
        gen = [str(x) for x in sols(mod, mod.SolveTree([["path", "a", Y1]], prog, T1), Y1, T1)]
        spec = [str(x) for x in sols(mod, mod.TreeGraph([["path", "a", Y2]], T2), Y2, T2)]
        assert spec == gen

    def test_residual_builtin_dispatch(self, mod):
        F = Var()
        assert sols(mod, mod.FactSpec([["fact", 4, F]]), F) == [(24,)]


# ── control constructs / ITE / TCO — regression guards ───────────────────────


class TestControlConstructGuards:
    def test_once_commits_continuation_backtracks(self, mod):
        X, Y = Var(), Var()
        assert sols(mod, mod.onc(X, Y), X, Y) == [(1, "a"), (1, "b")]

    def test_once_failing_goal_fails(self, mod):
        X = Var()
        assert sols(mod, mod.oncf(X), X) == []

    def test_call_nth_and_count_all(self, mod):
        X = Var()
        assert sols(mod, mod.cn3(X), X) == [(20,)]
        N = Var()
        assert sols(mod, mod.ca(N), N) == [(3,)]
        solve_mod._query_cache.clear()
        assert not any(True for _ in call("cawrong", module=mod))

    def test_setup_call_cleanup_bindings_and_failure(self, mod):
        T, A = Var(), Var()
        assert sols(mod, mod.sccb(T, A), T, A) == [(1, 1)]
        X = Var()
        assert sols(mod, mod.sccf(X), X) == [(2,)]

    def test_forall(self, mod):
        solve_mod._query_cache.clear()
        assert any(True for _ in call("fal", module=mod))
        solve_mod._query_cache.clear()
        assert not any(True for _ in call("falf", module=mod))

    def test_freeze_and_when(self, mod):
        X, R = Var(), Var()
        assert sols(mod, mod.fz(X, R), X, R) == [(1, "fired")]
        X2, R2 = Var(), Var()
        assert sols(mod, mod.wgr(X2, R2), X2, R2) == [(5, "g")]
        WX, WY, R3 = Var(), Var(), Var()
        assert sols(mod, mod.wand(WX, WY, R3), WX, WY, R3) == [(1, 2, "both")]


class TestIteGuards:
    def test_undetermined_unify_ite_two_solutions(self, mod):
        X = Var()
        assert sols(mod, mod.ifu(X), X) == [("then",), ("else",)]

    def test_nested_undetermined_ite_four_paths(self, mod):
        X, Y = Var(), Var()
        assert sols(mod, mod.ifn(X, Y), X, Y) == [
            ("t", "t"), ("t", "e"), ("e", "t"), ("e", "e")]

    def test_fd_reified_ground_and_undetermined(self, mod):
        L1, L2 = Var(), Var()
        assert sols(mod, mod.clfd(5, L1), L1) == [("pos",)]
        assert sols(mod, mod.clfd(-2, L2), L2) == [("neg",)]
        X, L3 = Var(), Var()
        assert sorted(sols(mod, mod.clfd(X, L3), L3)) == [("neg",), ("pos",)]

    def test_dif_reified_all_modes(self, mod):
        L1, L2 = Var(), Var()
        assert sols(mod, mod.cldif(3, L1), L1) == [("eq",)]
        assert sols(mod, mod.cldif(4, L2), L2) == [("ne",)]
        X, L3 = Var(), Var()
        assert sorted(sols(mod, mod.cldif(X, L3), L3)) == [("eq",), ("ne",)]

    def test_general_ite_runs_then_per_condition_solution(self, mod):
        X, R = Var(), Var()
        assert sols(mod, mod.altif(X, R), X, R) == [
            ("a", "yes"), ("b", "yes"), ("c", "yes")]

    def test_tabled_ite_and_naf(self, mod):
        R1, R2 = Var(), Var()
        assert sols(mod, mod.CheckPath(2, R1), R1) == [("reachable",)]
        assert sols(mod, mod.CheckPath(99, R2), R2) == [("unreachable",)]
        assert sols(mod, mod.NotPath(2)) == []
        assert sols(mod, mod.NotPath(99)) == [()]


class TestContinuationTcoGuards:
    def test_passthrough_wrappers_all_solutions(self, mod):
        X1, X2 = Var(), Var()
        assert sols(mod, mod.w(X1), X1) == [("a",), ("b",), ("c",)]
        assert sols(mod, mod.w2(X2), X2) == [("a",), ("b",), ("c",)]

    def test_or_arm_tail_calls(self, mod):
        X = Var()
        assert sols(mod, mod.alt(X), X) == [
            ("a",), ("b",), ("c",), ("a",), ("b",), ("c",)]

    def test_deferred_head_pattern_gates_tco_output_mode(self, mod):
        L = Var()
        assert sols(mod, mod.sp2(L), L) == [([1, 2, 3],), ([7, 8],)]

    def test_tail_call_into_indexed_bucket_ref(self, mod):
        R = Var()
        assert sols(mod, mod.wk(R), R) == [("a",), ("b",)]

    def test_shallow_trampoline_parity_disjoint_guards(self, mod):
        for days, want in [(30, [(75,)]), (10, [(30,)])]:
            F1, F2 = Var(), Var()
            assert sols(mod, mod.sfee(days, F1), F1) == want
            assert sols(mod, mod.tfee(days, F2), F2) == want

    def test_membership_generates(self, mod):
        X = Var()
        assert sols(mod, mod.mem2(X), X) == [(1,), (2,)]
