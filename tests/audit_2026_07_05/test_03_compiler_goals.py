"""A03 compiler goals, control & specialization — adversarial audit tests (2026-07-05).

Findings ledger: docs/superpowers/audits/2026-07-05-fable-partition/03-compiler-goals/findings.md

Suspected-bug tests assert the *correct* behaviour and are marked
``@pytest.mark.xfail(strict=False)`` with the finding ID; confirmed-correct
behaviour is a plain regression guard.  Run PER FILE only:

    python -m pytest tests/audit_2026_07_05/test_03_compiler_goals.py -v
"""
import inspect

import pytest

from clausal.logic.atoms import mint
from clausal.logic.cells import chars
from clausal.import_hook import _load_module
from clausal.logic import solve as solve_mod
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref, is_var, walk
from tests._suffix import SEAM


# ── Fixture module ────────────────────────────────────────────────────────────
# All predicates live in ONE module (atoms/functors are module-scoped; a second
# load would mint distinct functor classes that never unify with the first).

FIXTURE = '''
-double_quotes(atom)
-import_from(clausal.examples.metainterpreters, [solve, solve_count, solve_limit, solve_tree])
-import_from(clausal.stdlib.reif, [memberd_t])
-private([kab(KA)])

# ── A03-F001: TRO with nondeterministic prefix goals ──────────────────
# member prefix (MemberIn wrongly classed deterministic)
trm(0, ACC, ACC),
trm(N, ACC, OUT) <- (N > 0, X in [1, 2], eval_(N - 1, N1), eval_(ACC + X, ACC1), trm(N1, ACC1, OUT))

# undetermined if_ prefix (Branch wrongly classed deterministic)
tri(0, ACC, ACC),
tri(N, ACC, OUT) <- (N > 0, if_(C is 1, eval_(5, X), eval_(7, X)), eval_(N - 1, N1), eval_(ACC + X, ACC1), tri(N1, ACC1, OUT))

# atom_concat split-mode prefix (wrongly in _DETERMINISTIC_BUILTINS)
tac(0, ACC, ACC),
tac(N, ACC, OUT) <- (N > 0, atom_concat(P, Q, "ab"), eval_(N - 1, N1), ACC1 is [P, *ACC], tac(N1, ACC1, OUT))

# shallow twins = differential oracle (ShallowStrategy has no TRO)
-shallow([strm/3, stri/3, swk5/3, sfee/2])
strm(0, ACC, ACC),
strm(N, ACC, OUT) <- (N > 0, X in [1, 2], eval_(N - 1, N1), eval_(ACC + X, ACC1), strm(N1, ACC1, OUT))
stri(0, ACC, ACC),
stri(N, ACC, OUT) <- (N > 0, if_(C is 1, eval_(5, X), eval_(7, X)), eval_(N - 1, N1), eval_(ACC + X, ACC1), stri(N1, ACC1, OUT))

# non-tail controls (Unify after the self-call disables TRO)
trn(0, ACC, ACC),
trn(N, ACC, OUT) <- (N > 0, X in [1, 2], eval_(N - 1, N1), eval_(ACC + X, ACC1), trn(N1, ACC1, OUT0), OUT is OUT0)
trin(0, ACC, ACC),
trin(N, ACC, OUT) <- (N > 0, if_(C is 1, eval_(5, X), eval_(7, X)), eval_(N - 1, N1), eval_(ACC + X, ACC1), trin(N1, ACC1, OUT0), OUT is OUT0)

# deterministic TRO regression guards
cnt(0, ACC, ACC),
cnt(N, ACC, OUT) <- (N > 0, eval_(N - 1, N1), eval_(ACC + N, ACC1), cnt(N1, ACC1, OUT))
trob(0, ACC, ACC),
trob(N, ACC, OUT) <- (N > 0, once(in_(X, [5, 6])), eval_(N - 1, N1), eval_(ACC + X, ACC1), trob(N1, ACC1, OUT))
# catch prefix is non-deterministic per the table → TRO off, still correct
ctp(0, ACC, ACC),
ctp(N, ACC, OUT) <- (N > 0, catch(X is 1, _, X is 2), eval_(N - 1, N1), eval_(ACC + X, ACC1), ctp(N1, ACC1, OUT))

# ── A03-F002: destructive reuse behind nondeterministic prefixes ─────
drm(OUT) <- (SRC is [1, 2], X in [10, 20], append(SRC, [X], OUT))
drb(OUT) <- (SRC is [1, 2], if_(C is 1, X is 10, X is 20), append(SRC, [X], OUT))
# controls: live-after source (DR off) and deterministic prefix (intended DR)
drmc(OUT) <- (SRC is [1, 2], X in [10, 20], append(SRC, [X], OUT), length(SRC, _))
drok(OUT) <- (SRC is [1, 2], append(SRC, [3], OUT))

# ── A03-F003: signal-mode TRO bucket compiles to a non-generator ─────
# 4 clauses → indexed; the var-headed TRO clause sits ALONE in the default
# bucket, whose funcdef then contains no yield at all.
idx(0, "z0"),
idx(90, "n90"),
idx(80, "n80"),
idx(N, R) <- (N > 0, N < 50, eval_(N - 1, N1), idx(N1, R))

# control: a second var-headed (non-TRO) clause puts a yield in the bucket
jdx(0, "z0"),
jdx(90, "n90"),
jdx(80, "n80"),
jdx(M, "big") <- (M > 100),
jdx(N, R) <- (N > 0, N < 50, eval_(N - 1, N1), jdx(N1, R))

# TRO + check_indices + indexing, list heads — correct-behaviour guard
wk5([], ACC, ACC),
wk5([9], 9, "nine"),
wk5([8], 8, "eight"),
wk5([H, *T], ACC, OUT) <- (eval_(ACC + H, ACC1), wk5(T, ACC1, OUT))
swk5([], ACC, ACC),
swk5([9], 9, "nine"),
swk5([8], 8, "eight"),
swk5([H, *T], ACC, OUT) <- (eval_(ACC + H, ACC1), swk5(T, ACC1, OUT))

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
ifu(X) <- if_(C is 1, X is "then", X is "else")
ifn(X, Y) <- (if_(A is 1, X is "t", X is "e"), if_(B is 1, Y is "t", Y is "e"))
clfd(X, L) <- if_(X >= 0, L is "pos", L is "neg")
cldif(X, L) <- if_(X is not 3, L is "ne", L is "eq")
mem2(X) <- (X in [1, 2])
gen("a"),
gen("b"),
gen("c"),
altif(X, R) <- if_(memberd_t(X, ["a", "b", "c"]), R is "yes", R is "no")

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
-table(path/2)
edge(1, 2),
edge(2, 3),
edge(3, 1),
path(PA, PB) <- edge(PA, PB)
path(PA, PB) <- (edge(PA, PC), path(PC, PB))
check_path(CX, RESULT) <- ((path(1, CX), RESULT is "reachable") or (not path(1, CX), RESULT is "unreachable"))
not_path(NX) <- (not path(1, NX))

# ── specialization ────────────────────────────────────────────────────
match_clause(GOAL, FRESH_BODY, PROGRAM) <- (
    CLAUSE in PROGRAM,
    copy_term(CLAUSE, [FRESH_HEAD, FRESH_BODY]),
    GOAL is FRESH_HEAD,
)

nat_prog(PROGRAM) <- (
    PROGRAM is [
        [["natnum", 0], []],
        [["natnum", ["s", NX2]], [["natnum", NX2]]]
    ]
)
graph_prog(PROGRAM) <- (
    PROGRAM is [
        [["edge", "a", "b"], []],
        [["edge", "b", "c"], []],
        [["edge", "b", "d"], []],
        [["path", GX, GY], [["edge", GX, GY]]],
        [["path", GX, GY], [["edge", GX, GZ], ["path", GZ, GY]]]
    ]
)
const_prog(PROGRAM) <- (
    PROGRAM is [
        [["f", 1], []],
        [["g"], [["f", 2]]]
    ]
)
# A03-F008 (goal-side bindings): inlining f(GVX) against fact f(1) binds the
# GOAL-side var — the binding must reach the enclosing clause head.
gv_prog(PROGRAM) <- (
    PROGRAM is [
        [["f", 1], []],
        [["gv", GVX], [["f", GVX]]]
    ]
)
# ... and a later sibling goal sharing the goal-side var (q(GSX, GSR)).
gs_prog(PROGRAM) <- (
    PROGRAM is [
        [["f", 1], []],
        [["q", 1, "ok"], []],
        [["gs", GSX, GSR], [["f", GSX], ["q", GSX, GSR]]]
    ]
)
fact_prog(PROGRAM) <- (
    PROGRAM is [
        [["fact", 0, 1], []],
        [["fact", FN, FF], [["gt", FN, 0], ["sub", FN, 1, FN1], ["fact", FN1, FF1], ["mul", FN, FF1, FF]]]
    ]
)

# A03-F007: MI with goals BETWEEN match_clause and the recursive call. The
# generic MI is exercised here; the -specialize is refused loudly (A03-D003)
# and is asserted in a dedicated per-test module so it doesn't abort this
# whole shared fixture's load.
solve_guard([], _PROGRAM, _LIM),
solve_guard([GOAL, *GOALS], PROGRAM, LIM) <- (
    match_clause(GOAL, BODY, PROGRAM),
    LIM > 0,
    append(BODY, GOALS, ALL_GOALS),
    LIM1 == LIM - 1,
    solve_guard(ALL_GOALS, PROGRAM, LIM1),
)

# A03-F008: deep unfolding vs single-clause functor with constant arg
-specialize(solve, const_prog, alias=const_shallow)
-specialize(solve, const_prog, alias=const_deep, depth=5)
-specialize(solve, gv_prog, alias=gv_deep, depth=5)
-specialize(solve, gs_prog, alias=gs_deep, depth=5)

# A03-F009: CPD + counting-extension chaining
-specialize(solve_count, graph_prog, alias=count_graph)
-specialize(solve_count, graph_prog, alias=count_graph_cpd, cpd=True)
-specialize(solve, graph_prog, alias=graph_spec)
-specialize(solve, graph_prog, alias=graph_cpd, cpd=True)

# regression guards: limit (pre-match), tree (split), residual builtins
-specialize(solve_limit, nat_prog, alias=lim_nat)
# A03-F009 guard: CPD solve_limit exercises the pre-match chaining path (the
# post-match count path is count_graph_cpd). Must match the non-CPD depth cutoff.
-specialize(solve_limit, nat_prog, alias=lim_nat_cpd, cpd=True)
-specialize(solve_tree, graph_prog, alias=tree_graph)
-specialize(solve, fact_prog, alias=fact_spec)
'''


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    p = tmp_path_factory.mktemp("a03") / f"a03_fixture{SEAM}"
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


# The fixture module reads "..." as an ATOM (the engine default), so the
# goal terms this Python side builds have to name the same atoms.
NAT3 = [[mint("natnum"), [mint("s"), [mint("s"), [mint("s"), 0]]]]]


def _program(mod, source_pred):
    """*source_pred* names a 1-ary predicate; its first answer is the program."""
    from clausal import solve
    solve_mod._query_cache.clear()
    v = Var()
    for _ in solve((source_pred, v), mod):
        return walk(deref(v))
    raise AssertionError("program source failed")


# ── A03-F001 — TRO loses solutions behind nondeterministic prefixes ──────────


class TestF001TroNondetPrefix:
    def test_member_prefix_all_solutions(self, mod):
        O = Var()
        assert sorted(sols(mod, ("trm", 2, 0, O), O)) == [(2,), (3,), (3,), (4,)]

    def test_branch_prefix_all_solutions(self, mod):
        O = Var()
        assert sorted(sols(mod, ("tri", 1, 0, O), O)) == [(5,), (7,)]

    def test_atom_concat_prefix_all_solutions(self, mod):
        """atom_concat(P,Q,"ab") is nondet (3 splits), so TRO is off and all
        three prefix solutions survive.

        ``ACC1 is [P, *ACC]`` compiles through
        ``_head_list_unify_output`` (construction mode, ACC1 unbound), whose
        tail promotes a list of CHARS back to the compact ``str``.

        THE FLIP (2026-09-06-atoms-as-cells-strings §6.2) DELETED P3-1's
        ``star_was_str`` gate, so that promotion fires unconditionally
        again — and correctly: a list of char atoms IS the string, so
        building the compact representation is not a coercion.  The
        ``P = a`` row is therefore the string "a" once more; the ``P = ""``
        and ``P = "ab"`` rows hold a non-char ATOM each and stay lists.
        """
        O = Var()
        assert sorted(sols(mod, ("tac", 1, [], O), O), key=repr) == sorted(
            [([mint("")],), (chars("a"),), ([mint("ab")],)], key=repr
        )

    # controls / oracle
    def test_shallow_oracle_member(self, mod):
        O = Var()
        assert sorted(sols(mod, ("strm", 2, 0, O), O)) == [(2,), (3,), (3,), (4,)]

    def test_shallow_oracle_branch(self, mod):
        O = Var()
        assert sorted(sols(mod, ("stri", 1, 0, O), O)) == [(5,), (7,)]

    def test_non_tail_control_member(self, mod):
        O = Var()
        assert sorted(sols(mod, ("trn", 2, 0, O), O)) == [(2,), (3,), (3,), (4,)]

    def test_non_tail_control_branch(self, mod):
        O = Var()
        assert sorted(sols(mod, ("trin", 1, 0, O), O)) == [(5,), (7,)]

    def test_deterministic_tro_still_correct(self, mod):
        O = Var()
        assert sols(mod, ("cnt", 5, 0, O), O) == [(15,)]

    def test_deterministic_tro_deep_stack_safe(self, mod):
        O = Var()
        assert sols(mod, ("cnt", 3000, 0, O), O) == [(4501500,)]

    def test_once_prefix_is_deterministic_and_correct(self, mod):
        O = Var()
        assert sols(mod, ("trob", 2, 0, O), O) == [(10,)]

    def test_catch_prefix_blocks_tro_and_correct(self, mod):
        O = Var()
        assert sols(mod, ("ctp", 2, 0, O), O) == [(2,)]

    def test_analysis_marks_nondet_prefixes_ineligible(self, mod):
        """Direct analysis check: these clauses must NOT be TRO-eligible."""
        from clausal.logic.compiler.terms_to_goalop import terms_to_goalop
        from clausal.logic.compiler.optimisations import tro as tro_pass
        bad = []
        for name in ("trm", "tri", "tac"):
            cl = mod.__clausal_module__.db.row(name, 3).clauses[-1]
            plan = tro_pass.analyse(terms_to_goalop(cl.body, db=None), cl.head, name, 3)
            if plan.eligible:
                bad.append(name)
        if bad:
            pytest.xfail(f"A03-F001: TRO analysis wrongly eligible for {bad}")


# ── A03-F002 — destructive reuse corrupts containers on backtracking ─────────


class TestF002DestructiveReuseNondetPrefix:
    def test_member_prefix_append(self, mod):
        O = Var()
        assert sols(mod, ("drm", O), O) == [([1, 2, 10],), ([1, 2, 20],)]

    def test_branch_prefix_append(self, mod):
        O = Var()
        assert sols(mod, ("drb", O), O) == [([1, 2, 10],), ([1, 2, 20],)]

    def test_live_after_source_is_safe(self, mod):
        O = Var()
        assert sols(mod, ("drmc", O), O) == [([1, 2, 10],), ([1, 2, 20],)]

    def test_deterministic_prefix_dr_correct(self, mod):
        O = Var()
        assert sols(mod, ("drok", O), O) == [([1, 2, 3],)]

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
        assert sols(mod, ("idx", 3, O), O) == [(mint("z0"),)]

    def test_keyed_bucket_works(self, mod):
        O = Var()
        assert sols(mod, ("idx", 0, O), O) == [(mint("z0"),)]

    def test_bucket_with_extra_var_clause_works(self, mod):
        O = Var()
        assert sols(mod, ("jdx", 3, O), O) == [(mint("z0"),)]
        O2 = Var()
        assert sols(mod, ("jdx", 200, O2), O2) == [(mint("big"),)]

    def test_default_bucket_is_generator_function(self, mod):
        """The compiled default-bucket function must be a generator function."""
        disp = mod.__clausal_module__.db.get_dispatch("idx", 2)
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
        it1 = iter(solve(("jdx", 3, R1), mod))
        it2 = iter(solve(("jdx", 7, R2), mod))
        out = [(walk(deref(R1)), walk(deref(R2))) for _ in zip(it1, it2)]
        assert out == [(mint("z0"), mint("z0"))]

    def test_tro_check_indices_with_indexing(self, mod):
        O1, O2 = Var(), Var()
        assert sols(mod, ("wk5", [1, 2, 3], 0, O1), O1) == [(6,)]
        assert sols(mod, ("swk5", [1, 2, 3], 0, O2), O2) == [(6,)]

    def test_tro_check_indices_keyed_overlap(self, mod):
        O = Var()
        assert sols(mod, ("wk5", [9], 9, O), O) == [(mint("nine"),), (18,)]


# ── A03-F004 — catch never matches declared-functor exception terms ──────────


class TestF004CatchFunctorCatcher:
    def test_functor_catcher_direct_throw(self, mod):
        N, R = Var(), Var()
        assert sols(mod, ("cfun", N, R), N, R) == [(7, mint("caught"))]

    def test_functor_catcher_through_chain(self, mod):
        N, R = Var(), Var()
        assert sols(mod, ("cchain", N, R), N, R) == [(5, mint("caught"))]

    def test_var_catcher_catches_through_chain(self, mod):
        R = Var()
        assert sols(mod, ("cvar", R), R) == [(mint("caught"),)]

    def test_string_catcher_catches(self, mod):
        R = Var()
        assert sols(mod, ("cstr", R), R) == [(mint("caught"),)]

    def test_prebuilt_catcher_via_variable_arg_catches(self, mod):
        """Passing a pre-built catcher TERM through a variable works — the
        compile-time Compound conversion is what breaks cfun.

        P3-2 Task 2 (THE FLIP, R6): ``kab`` is a data functor, so the
        pre-built term is the cell ``("kab", N)``, which is exactly what the
        throw site builds.  (Was ``("kab", N)``; the name binds the interned
        spelling now, so there is no constructor to call.)
        """
        N, R = Var(), Var()
        assert sols(mod, ("targ", ("kab", N), R), N, R) == [(7, mint("caught"))]

    def test_rethrow_on_catcher_mismatch(self, mod):
        from clausal.logic.exceptions import LogicException
        with pytest.raises(LogicException):
            sols(mod, ("cmiss", Var()))

    def test_nondeterministic_recovery(self, mod):
        R = Var()
        assert sols(mod, ("crec", R), R) == [(1,), (2,)]

    def test_catch_error_and_catch_recover(self, mod):
        R = Var()
        assert sols(mod, ("ce1", R), R) == [(mint("sw"),)]
        R2 = Var()
        assert sols(mod, ("cr1", R2), R2) == [(mint("rec"),)]

    # Spec acceptance (fix-A03-catch-functor-catcher.md): atoms/functors are
    # module-scoped, so a catcher naming an IMPORTED functor must resolve to
    # the SAME class the throw site constructs — two modules, `-import_from`.
    _F004_CATCH_LIB = '''
-module(a03_f004_catchlib, [kex(KX)])
thrower(TX) <- throw(kex(TX))
'''
    _F004_CATCH_IMPORTER = '''
-double_quotes(atom)
-import_from(a03_f004_catchlib, [kex, thrower])
cimp(N, R) <- catch(thrower(7), kex(N), R is "caught")
'''

    def test_imported_functor_catcher_resolves_to_same_class(self, tmp_path):
        lib = tmp_path / f"a03_f004_catchlib{SEAM}"
        lib.write_text(self._F004_CATCH_LIB)
        _load_module("a03_f004_catchlib", str(lib))
        imp = tmp_path / f"a03_f004_catchimp{SEAM}"
        imp.write_text(self._F004_CATCH_IMPORTER)
        m = _load_module("a03_f004_catchimp", str(imp))
        N, R = Var(), Var()
        assert sols(m, ("cimp", N, R), N, R) == [(7, mint("caught"))]


# ── A03-F005 / A03-F006 — setof sort, findall template freshness ─────────────


class TestF005F006FindallFamily:
    def test_setof_is_sorted(self, mod):
        L = Var()
        assert sols(mod, ("so", L), L) == [([1, 2, 3],)]

    def test_setof_dedups(self, mod):
        L = Var()
        [(got,)] = sols(mod, ("so", L), L)
        assert sorted(got) == [1, 2, 3] and len(got) == 3

    def test_findall_free_vars_are_fresh_per_solution(self, mod):
        L, Y = Var(), Var()
        [(got, _y)] = sols(mod, ("fat2", L, Y), L, Y)
        # ISO: rows carry fresh variables, NOT the later-bound value 9
        assert not all(row[1] == 9 for row in got)

    def test_findall_order_and_duplicates(self, mod):
        L = Var()
        assert sols(mod, ("fa", L), L) == [([3, 1, 3, 2],)]

    def test_bagof_keeps_duplicates_fails_on_empty(self, mod):
        L = Var()
        assert sols(mod, ("bg", L), L) == [([3, 1, 3, 2],)]
        L2 = Var()
        assert sols(mod, ("bge", L2), L2) == []


# ── A03-F007/F008/F009 — specialization ──────────────────────────────────────


# A03-F007: SolveGuard has a non-MI goal (LIM > 0) between MatchClause and the
# recursive call. Its -specialize must be refused loudly (A03-D003), so it is
# asserted here in a dedicated module rather than the shared fixture (whose
# whole load would otherwise abort).
_SOLVEGUARD_SPEC_FIXTURE = '''
-double_quotes(atom)
match_clause(GOAL, FRESH_BODY, PROGRAM) <- (
    CLAUSE in PROGRAM,
    copy_term(CLAUSE, [FRESH_HEAD, FRESH_BODY]),
    GOAL is FRESH_HEAD,
)
nat_prog(PROGRAM) <- (
    PROGRAM is [
        [["natnum", 0], []],
        [["natnum", ["s", NX2]], [["natnum", NX2]]]
    ]
)
solve_guard([], _PROGRAM, _LIM),
solve_guard([GOAL, *GOALS], PROGRAM, LIM) <- (
    match_clause(GOAL, BODY, PROGRAM),
    LIM > 0,
    append(BODY, GOALS, ALL_GOALS),
    LIM1 == LIM - 1,
    solve_guard(ALL_GOALS, PROGRAM, LIM1),
)
-specialize(solve_guard, nat_prog, alias=solve_guard_nat)
'''


class TestF007SpecializationDropsMidBodyGoals:
    def test_generic_mi_respects_guard(self, mod):
        prog = _program(mod, "nat_prog")
        assert not has_sol(mod, ("solve_guard", NAT3, prog, 1))
        assert has_sol(mod, ("solve_guard", NAT3, prog, 10))

    def test_midbody_goal_specialize_refused(self, tmp_path):
        # A03-F007/D003: a non-MI goal (LIM > 0) between MatchClause and the
        # recursive call would be silently dropped from every specialized
        # clause, so -specialize must REFUSE LOUDLY at load time rather than
        # emit a guard-less specialization. (Previously SolveGuardNat compiled
        # with the depth guard dropped, so it recursed without bound.)
        from clausal.logic.specialization import CannotSpecialize
        p = tmp_path / f"solveguard_spec{SEAM}"
        p.write_text(_SOLVEGUARD_SPEC_FIXTURE)
        with pytest.raises(CannotSpecialize, match="not MI-related"):
            _load_module("a03_solveguard_refuse", str(p))


class TestF008DeepUnfoldConstantCheck:
    def test_generic_and_shallow_spec_fail(self, mod):
        prog = _program(mod, "const_prog")
        assert not has_sol(mod, ("solve", [[mint("g")]], prog))
        assert not has_sol(mod, ("const_shallow", [[mint("g")]]))

    def test_deep_spec_fails_like_generic(self, mod):
        assert not has_sol(mod, ("const_deep", [[mint("g")]]))

    # A03-F008 remaining case: var-goal-arg vs const-head-arg. Inlining
    # f(GV) against fact f(1) binds the GOAL-side var GV, but the binding
    # had no channel back to the enclosing clause head — it surfaced
    # unbound AND gv(2) wrongly succeeded.
    def test_deep_spec_propagates_goal_side_binding(self, mod):
        prog = _program(mod, "gv_prog")
        V1, V2 = Var(), Var()
        assert sols(mod, ("solve", [[mint("gv"), V1]], prog), V1) == [(1,)]
        assert sols(mod, ("gv_deep", [[mint("gv"), V2]]), V2) == [(1,)]

    def test_deep_spec_rejects_conflicting_goal_side_const(self, mod):
        prog = _program(mod, "gv_prog")
        assert not has_sol(mod, ("solve", [[mint("gv"), 2]], prog))
        assert not has_sol(mod, ("gv_deep", [[mint("gv"), 2]]))

    def test_deep_spec_goal_side_binding_reaches_later_sibling_goal(self, mod):
        prog = _program(mod, "gs_prog")
        X1, R1, X2, R2 = Var(), Var(), Var(), Var()
        gen = sols(mod, ("solve", [[mint("gs"), X1, R1]], prog), X1, R1)
        spec = sols(mod, ("gs_deep", [[mint("gs"), X2, R2]]), X2, R2)
        assert spec == gen == [(1, mint("ok"))]
        assert not has_sol(mod, ("gs_deep", [[mint("gs"), 2, Var()]]))


class TestF009CpdExtensionChaining:
    def test_plain_cpd_matches_generic(self, mod):
        prog = _program(mod, "graph_prog")
        Y1, Y2, Y3 = Var(), Var(), Var()
        gen = sorted(sols(mod, ("solve", [[mint("path"), mint("a"), Y1]], prog), Y1))
        spec = sorted(sols(mod, ("graph_spec", [[mint("path"), mint("a"), Y2]]), Y2))
        cpd = sorted(sols(mod, ("graph_cpd", [[mint("path"), mint("a"), Y3]]), Y3))
        assert spec == gen == [(mint("b"),), (mint("c"),), (mint("d"),)]
        assert cpd == gen

    def test_counting_spec_matches_generic(self, mod):
        prog = _program(mod, "graph_prog")
        Y1, C1, Y2, C2 = Var(), Var(), Var(), Var()
        gen = sorted(sols(mod, ("solve_count", [[mint("path"), mint("a"), Y1]], prog, C1), Y1, C1))
        spec = sorted(sols(mod, ("count_graph", [[mint("path"), mint("a"), Y2]], C2), Y2, C2))
        assert spec == gen == [(mint("b"), 2), (mint("c"), 4), (mint("d"), 4)]

    def test_cpd_counting_matches_generic(self, mod):
        # A03-F009: deep CPD clauses now telescope the count with exactly one
        # increment per inlined step (single per-level template splice, not a
        # re-chain of the accumulated body), so counts equal the generic MI.
        Y, C = Var(), Var()
        got = sorted(sols(mod, ("count_graph_cpd", [[mint("path"), mint("a"), Y]], C), Y, C))
        assert got == [(mint("b"), 2), (mint("c"), 4), (mint("d"), 4)]

    def test_cpd_limit_matches_non_cpd(self, mod):
        # A03-F009: the pre-match chaining path (SolveLimit's ``MAX > 0`` /
        # ``MAX1 == MAX - 1``) must telescope one guard+decrement per level, so
        # the CPD depth cutoff matches the non-CPD specialization exactly.
        for depth, expected in ((2, False), (3, False), (4, True), (9, True)):
            assert has_sol(mod, ("lim_nat_cpd", NAT3, depth)) is expected
            assert has_sol(mod, ("lim_nat", NAT3, depth)) is expected


class TestSpecializationRegressionGuards:
    def test_limit_pre_match_goals_preserved(self, mod):
        prog = _program(mod, "nat_prog")
        assert not has_sol(mod, ("solve_limit", NAT3, prog, 2))
        assert not has_sol(mod, ("lim_nat", NAT3, 2))
        assert has_sol(mod, ("solve_limit", NAT3, prog, 9))
        assert has_sol(mod, ("lim_nat", NAT3, 9))

    def test_split_style_proof_trees_equal(self, mod):
        prog = _program(mod, "graph_prog")
        Y1, T1, Y2, T2 = Var(), Var(), Var(), Var()
        gen = [str(x) for x in sols(mod, ("solve_tree", [[mint("path"), mint("a"), Y1]], prog, T1), Y1, T1)]
        spec = [str(x) for x in sols(mod, ("tree_graph", [[mint("path"), mint("a"), Y2]], T2), Y2, T2)]
        assert spec == gen

    def test_residual_builtin_dispatch(self, mod):
        F = Var()
        assert sols(mod, ("fact_spec", [[mint("fact"), 4, F]]), F) == [(24,)]


# ── control constructs / ITE / TCO — regression guards ───────────────────────


class TestControlConstructGuards:
    def test_once_commits_continuation_backtracks(self, mod):
        X, Y = Var(), Var()
        assert sols(mod, ("onc", X, Y), X, Y) == [(1, mint("a")), (1, mint("b"))]

    def test_once_failing_goal_fails(self, mod):
        X = Var()
        assert sols(mod, ("oncf", X), X) == []

    def test_call_nth_and_count_all(self, mod):
        X = Var()
        assert sols(mod, ("cn3", X), X) == [(20,)]
        N = Var()
        assert sols(mod, ("ca", N), N) == [(3,)]
        solve_mod._query_cache.clear()
        assert not any(True for _ in call("cawrong", module=mod))

    def test_setup_call_cleanup_bindings_and_failure(self, mod):
        T, A = Var(), Var()
        assert sols(mod, ("sccb", T, A), T, A) == [(1, 1)]
        X = Var()
        assert sols(mod, ("sccf", X), X) == [(2,)]

    def test_forall(self, mod):
        solve_mod._query_cache.clear()
        assert any(True for _ in call("fal", module=mod))
        solve_mod._query_cache.clear()
        assert not any(True for _ in call("falf", module=mod))

    def test_freeze_and_when(self, mod):
        X, R = Var(), Var()
        assert sols(mod, ("fz", X, R), X, R) == [(1, mint("fired"))]
        X2, R2 = Var(), Var()
        assert sols(mod, ("wgr", X2, R2), X2, R2) == [(5, mint("g"))]
        WX, WY, R3 = Var(), Var(), Var()
        assert sols(mod, ("wand", WX, WY, R3), WX, WY, R3) == [(1, 2, mint("both"))]


class TestIteGuards:
    def test_undetermined_unify_ite_two_solutions(self, mod):
        X = Var()
        assert sols(mod, ("ifu", X), X) == [(mint("then"),), (mint("else"),)]

    def test_nested_undetermined_ite_four_paths(self, mod):
        X, Y = Var(), Var()
        assert sols(mod, ("ifn", X, Y), X, Y) == [
            (mint("t"), mint("t")), (mint("t"), mint("e")), (mint("e"), mint("t")), (mint("e"), mint("e"))]

    def test_fd_reified_ground_and_undetermined(self, mod):
        L1, L2 = Var(), Var()
        assert sols(mod, ("clfd", 5, L1), L1) == [(mint("pos"),)]
        assert sols(mod, ("clfd", -2, L2), L2) == [(mint("neg"),)]
        X, L3 = Var(), Var()
        assert sorted(sols(mod, ("clfd", X, L3), L3)) == [(mint("neg"),), (mint("pos"),)]

    def test_dif_reified_all_modes(self, mod):
        L1, L2 = Var(), Var()
        assert sols(mod, ("cldif", 3, L1), L1) == [(mint("eq"),)]
        assert sols(mod, ("cldif", 4, L2), L2) == [(mint("ne"),)]
        X, L3 = Var(), Var()
        assert sorted(sols(mod, ("cldif", X, L3), L3)) == [(mint("eq"),), (mint("ne"),)]

    def test_reified_closure_runs_then_per_way_it_holds(self, mod):
        """if_/3 requires a reifiable condition (ruling 2026-10-01): a
        reified closure answers every way it holds, then the else branch
        under the constraints that make it false (library(reif))."""
        X, R = Var(), Var()
        got = sols(mod, ("altif", X, R), X, R)
        assert got[:3] == [
            (mint("a"), mint("yes")), (mint("b"), mint("yes")), (mint("c"), mint("yes"))]
        assert len(got) == 4 and is_var(got[3][0]) and got[3][1] == mint("no")

    def test_tabled_ite_and_naf(self, mod):
        R1, R2 = Var(), Var()
        assert sols(mod, ("check_path", 2, R1), R1) == [(mint("reachable"),)]
        assert sols(mod, ("check_path", 99, R2), R2) == [(mint("unreachable"),)]
        assert sols(mod, ("not_path", 2)) == []
        assert sols(mod, ("not_path", 99)) == [()]


class TestContinuationTcoGuards:
    def test_passthrough_wrappers_all_solutions(self, mod):
        X1, X2 = Var(), Var()
        assert sols(mod, ("w", X1), X1) == [(mint("a"),), (mint("b"),), (mint("c"),)]
        assert sols(mod, ("w2", X2), X2) == [(mint("a"),), (mint("b"),), (mint("c"),)]

    def test_or_arm_tail_calls(self, mod):
        X = Var()
        assert sols(mod, ("alt", X), X) == [
            (mint("a"),), (mint("b"),), (mint("c"),), (mint("a"),), (mint("b"),), (mint("c"),)]

    def test_deferred_head_pattern_gates_tco_output_mode(self, mod):
        L = Var()
        assert sols(mod, ("sp2", L), L) == [([1, 2, 3],), ([7, 8],)]

    def test_tail_call_into_indexed_bucket_ref(self, mod):
        R = Var()
        assert sols(mod, ("wk", R), R) == [(mint("a"),), (mint("b"),)]

    def test_shallow_trampoline_parity_disjoint_guards(self, mod):
        for days, want in [(30, [(75,)]), (10, [(30,)])]:
            F1, F2 = Var(), Var()
            assert sols(mod, ("sfee", days, F1), F1) == want
            assert sols(mod, ("tfee", days, F2), F2) == want

    def test_membership_generates(self, mod):
        X = Var()
        assert sols(mod, ("mem2", X), X) == [(1,), (2,)]
