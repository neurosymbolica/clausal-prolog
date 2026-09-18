"""A04 runtime, search & tabling — adversarial audit tests (2026-07-05).

Findings ledger: docs/superpowers/audits/2026-07-05-fable-partition/04-runtime-tabling/findings.md

Suspected-bug tests assert the *correct* behaviour and are marked
``@pytest.mark.xfail(strict=False)`` with the finding ID; confirmed-correct
behaviour is a plain regression guard.  Run PER FILE only:

    python -m pytest tests/audit_2026_07_05/test_04_runtime_tabling.py -v

Fixture discipline: every module is loaded exactly ONCE under a unique module
name (atoms/functors and table state are module-scoped), and modules whose
tables a test mutates or poisons are private to that test.
"""
import gc

import pytest

from clausal.logic.atoms import mint
from clausal.logic.cells import chars
from clausal.import_hook import _load_module
from clausal.logic.solve import solve, call, once, query, query_wfs, _query_cache
from clausal.logic.variables import Var, Trail, deref, is_var, unify
from clausal.terms import Undefined


# ── Fixture loader ────────────────────────────────────────────────────────────

_loaded = {}


@pytest.fixture(scope="session")
def load(tmp_path_factory):
    def _load(name, source):
        if name not in _loaded:
            d = tmp_path_factory.mktemp("a04fix")
            p = d / f"{name}.clausal"
            p.write_text(source)
            _loaded[name] = _load_module(f"a04_{name}", str(p))
        return _loaded[name]
    yield _load
    _loaded.clear()


def answers(gen, *vars_):
    out = []
    for _ in gen:
        out.append(tuple(deref(v) for v in vars_))
    return out


PATH_SRC = """-table(path/2)

edge(1, 2),
edge(2, 3),
edge(3, 4),

path(X, Y) <- edge(X, Y)
path(X, Y) <- (
    path(X, Z),
    edge(Z, Y)
)
"""

TWOREC_FACTSFIRST_SRC = """-table(p/1)

p(1),
p(X) <- (
    p(Y),
    a(Y, X)
)
p(X) <- (
    p(Y),
    b(Y, X)
)

a(1, 2),
b(2, 3),
a(3, 4),
b(4, 5),
"""

TWOREC_RECFIRST_SRC = """-table(p/1)

p(X) <- (
    p(Y),
    a(Y, X)
)
p(X) <- (
    p(Y),
    b(Y, X)
)
p(1),

a(1, 2),
b(2, 3),
a(3, 4),
b(4, 5),
"""

MUTUAL_RECFIRST_SRC = """-table(ra/2)
-table(rb/2)

ra(X, Y) <- (
    rb(X, Z),
    la(Z, Y)
)
ra(X, Y) <- la(X, Y)

rb(X, Y) <- (
    ra(X, Z),
    lb(Z, Y)
)
rb(X, Y) <- lb(X, Y)

la(1, 2),
la(3, 4),
lb(2, 3),
lb(4, 1),
"""

# A04-F001 transitive SCC: a 3-node cycle r1 → r3 → r2 → r1 (rec clause first).
# The middle members never consume an ON-STACK ancestor directly (they call a
# fresh nested leader), so edge-only dependency tracking lets them complete
# mid-fixpoint. Expected fixpoint from 1 along the fact chain 1→2→…→7:
#   r1(1,·) = {2,5}   r2(1,·) = {3,6}   r3(1,·) = {4,7}
SCC3_SRC = """-table(r1/2)
-table(r2/2)
-table(r3/2)

r1(X, Y) <- (
    r3(X, Z),
    l1(Z, Y)
)
r1(X, Y) <- l1(X, Y)

r2(X, Y) <- (
    r1(X, Z),
    l2(Z, Y)
)
r2(X, Y) <- l2(X, Y)

r3(X, Y) <- (
    r2(X, Z),
    l3(Z, Y)
)
r3(X, Y) <- l3(X, Y)

l1(1, 2),
l1(4, 5),
l2(2, 3),
l2(5, 6),
l3(3, 4),
l3(6, 7),
"""


def _rename_scc3(prefix):
    src = SCC3_SRC
    for tok in ("r1", "r2", "r3", "l1", "l2", "l3"):
        src = src.replace(tok, f"{prefix}{tok}")
    return src


# A04-F001 re-lead replay: pa joins TWO calls to pb — the second call needs
# pb's FULL answer set on every fixpoint pass, but a re-led dormant member
# streams only NEW answers (add_answer dedups the old ones away).
# Fixpoint: pa = {1} ∪ pb, pb = nx(pa) → pa = {1,2,3}, pb = {2,3}.
RELEAD_JOIN_SRC = """-table(pa/1)
-table(pb/1)

pa(X) <- (
    pb(W),
    pb(X)
)
pa(1),

pb(X) <- (
    pa(Y),
    nx(Y, X)
)

nx(1, 2),
nx(2, 3),
"""

# A04-F001 re-lead replay, cross-product shape: rr = ta × tb where BOTH grow
# across the root's fixpoint passes. Without replay, a pass streams only the
# NEW answers of each re-led member, so (old ta answer × new tb answer) pairs
# are never joined. Fixpoint: ta = {1,2}, tb = {10,20}, rr = ta × tb (4 pairs).
CROSS_JOIN_SRC = """-table(ta/1)
-table(tb/1)
-table(rr/2)

rr(X, Y) <- (
    ta(X),
    tb(Y)
)

ta(X) <- fa(X)
ta(X) <- (
    rr(Z, W),
    na(W, X)
)

tb(Y) <- fb(Y)
tb(Y) <- (
    rr(Z, W),
    nb(W, Y)
)

fa(1),
fb(10),
na(10, 2),
nb(10, 20),
"""

# A04-F007 rec-clause-first: the consumer suspends BEFORE the first answer
# exists, so at once()-abandonment a SuspendedConsumer keeps the parked leader
# frame reachable (entry.suspended → consumer gen → parent chain → leader gen)
# and GC alone can never deliver GeneratorExit to the wrapper's cleanup.
RECFIRST_ONCE_SRC = """-table(qq/1)

qq(X) <- (
    qq(Y),
    ee(Y, X)
)
qq(1),

ee(1, 2),
ee(2, 3),
ee(3, 4),
ee(4, 5),
"""

NAF_SRC = """-table(tp/2)

tp(1, 2),

ntp(R) <- (
    not tp(1, 2),
    R is "negation succeeded"
)
"""

WIN_ASYM_SRC = """-table(win/1)

move("a", "b"),
move("b", "a"),
move("a", "c"),

win(X) <- (
    move(X, Y),
    not win(Y)
)
"""

WIN_SYM_SRC = """-table(win/1)

move(1, 2),
move(2, 1),

win(X) <- (
    move(X, Y),
    not win(Y)
)
"""

EVEN_ODD_SRC = """-table(even_node/1)
-table(odd_node/1)

edge(1, 2),
edge(2, 3),

even_node(X) <- (
    edge(X, Y),
    not odd_node(Y)
)
odd_node(X) <- (
    edge(X, Y),
    not even_node(Y)
)
"""

TYPES_SRC = """-table(tt/1)

tt(1),
tt(True),
tt(2.0),
tt(2),

utt(1),
utt(True),
utt(2.0),
utt(2),
"""

BOOM_SRC = """-table(boom/1)

boom(1),
boom(X) <- (
    X is 2,
    eval_(1 / 0, BAD)
)
"""

RTE_SRC = """rte(X) <- (
    X is 1,
    ++boom_rt()
)
"""

DEEP_SRC = """count_down(0),
count_down(N) <- (
    N > 0,
    eval_(N - 1, N1),
    count_down(N1)
)

build(0, []),
build(N, [N, *T]) <- (
    N > 0,
    eval_(N - 1, N1),
    build(N1, T)
)
"""

PA_SRC = """pa(1, 2),
pa(3, 3),
"""

DYN_SRC = """-table(tz/1)
-dynamic(tz/1)

tz(1),
tz(2),
"""

TRAIL_SRC = """tr7(Y) <- (([Y, *T, 6] is [5, 8, 7]) or (Y is 1))
"""

WHEN_SRC = """w8(R) <- (
    when((nonvar(X) or nonvar(Y)), R is "fired"),
    ((X is 1, 1 == 2) or (Y is 2))
)
"""

FREEZE_SRC = """f9(X, Y) <- (
    freeze(X, in_(Y, [10, 20])),
    X is 1
)
"""

THROW_SRC = """lethrow(X) <- (
    X is 1,
    throw("kaboom")
)
"""

TS_LIST_SRC = """-table(ts/1)

ts([1, *T]) <- (T is [2, 3])
"""

TD_DICT_SRC = """-table(td/1)

td(D) <- (
    D is ++{"k": X},
    X is 7
)
"""

TW_TERM_SRC = """-table(tw/1)
-private([wrap(V)])

tw(W) <- (
    D is 7,
    W is wrap(D)
)
"""


# ══ Regression guards (confirmed-correct behaviour) ═══════════════════════════


class TestModeMatrixGuards:
    def test_solve_call_once_query_matrix(self, load, clear_query_cache):
        m = load("mode", PA_SRC)
        Y = Var()
        assert answers(solve(m.pa(1, Y), m), Y) == [(2,)]
        from clausal.terms import Compound
        Y2 = Var()
        assert answers(solve(Compound("pa", (1, Y2)), m), Y2) == [(2,)]
        assert sum(1 for _ in solve(True, m)) == 1
        assert sum(1 for _ in solve(False, m)) == 0
        assert once(m.pa(1, Var()), m) is not None
        assert once(m.pa(7, Var()), m) is None
        # module inference from the goal term
        Z = Var()
        assert answers(solve(m.pa(3, Z)), Z) == [(3,)]
        # call with string functor and with the predicate class
        V = Var()
        assert answers(call("pa", 1, V, module=m), V) == [(2,)]
        V2 = Var()
        assert answers(call(m.pa, 1, V2), V2) == [(2,)]
        # deprecated query() still dereferences
        import warnings
        Q = Var()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            assert list(query(m.pa(1, Q), {"Q": Q}, m)) == [{"Q": 2}]

    def test_query_cache_distinguishes_aliased_vars(self, load, clear_query_cache):
        m = load("mode", PA_SRC)
        V, W = Var(), Var()
        distinct = answers(solve(m.pa(V, W), m), V, W)
        A = Var()
        aliased = answers(solve(m.pa(A, A), m), A)
        assert sorted(map(repr, distinct)) == ["(1, 2)", "(3, 3)"]
        assert aliased == [(3,)]


class TestTrampolineGuards:
    def test_deep_recursion_no_stack_overflow(self, load):
        m = load("deep", DEEP_SRC)
        assert sum(1 for _ in call("count_down", 30000, module=m)) == 1

    def test_deep_output_list_construction(self, load):
        m = load("deep", DEEP_SRC)
        L = Var()
        got = answers(call("build", 2000, L, module=m), L)
        assert len(got) == 1 and len(got[0][0]) == 2000

    def test_uncaught_logic_exception_surfaces(self, load):
        from clausal.logic.exceptions import LogicException
        m = load("throw", THROW_SRC)
        with pytest.raises(LogicException):
            list(call("lethrow", Var(), module=m))

    def test_star_unify_failure_restores_trail_for_or_arm(self, load):
        m = load("trail", TRAIL_SRC)
        Y = Var()
        assert answers(call("tr7", Y, module=m), Y) == [(1,)]


class TestTablingGuards:
    def test_left_recursion_facts_first_single_rec_clause(self, load):
        m = load("leftrec", PATH_SRC)
        Y = Var()
        got = sorted(a[0] for a in answers(call("path", 1, Y, module=m), Y))
        assert got == [2, 3, 4]

    def test_dynamic_tabled_assertz_retract_invalidation(self, load):
        m = load("dyn", DYN_SRC)
        db = m.__clausal_module__.db
        V = Var()
        assert sorted(a[0] for a in answers(call("tz", V, module=m), V)) == [1, 2]
        assert sum(1 for _ in call("assertz", m.tz(99), module=m)) == 1
        assert db.table_store == {}  # auto-invalidated
        V2 = Var()
        assert sorted(a[0] for a in answers(call("tz", V2, module=m), V2)) == [1, 2, 99]
        assert sum(1 for _ in call("retract", m.tz(1), module=m)) == 1
        V3 = Var()
        assert sorted(a[0] for a in answers(call("tz", V3, module=m), V3)) == [2, 99]

    def test_manual_abolish_table_recomputes(self, load):
        m = load("abolish", PATH_SRC.replace("path", "path9"))
        db = m.__clausal_module__.db
        Y = Var()
        assert sorted(a[0] for a in answers(call("path9", 1, Y, module=m), Y)) == [2, 3, 4]
        db.abolish_table("path9", 2)
        assert not any(k[0] == "path9" for k in db.table_store)
        Y2 = Var()
        assert sorted(a[0] for a in answers(call("path9", 1, Y2, module=m), Y2)) == [2, 3, 4]

    def test_wfs_symmetric_win_internal_truth_values(self, load):
        m = load("winsym_guard", WIN_SYM_SRC)
        X = Var()
        got = sorted(a[0] for a in answers(call("win", X, module=m), X))
        assert got == [1, 2]  # documented: undefined answers are yielded
        # A04-F003 spawn-always: the var-mode drive also creates exact
        # sub-tables for the spawned ground negations — every entry's every
        # answer must still be Undefined (the symmetric cycle is unfounded).
        store = m.__clausal_module__.db.table_store
        truths = [entry.truth_value(i)
                  for entry in store.values()
                  for i in range(len(entry.answers))]
        assert truths and set(truths) == {Undefined}

    def test_asym_win_ground_docs_order(self, load):
        # docs/wfs.md truth table holds when 'a' is queried first
        m = load("winasym_guard", WIN_ASYM_SRC)
        # THE FLIP: the fixture's ``move("a", "b")`` node names are ATOMS.
        assert sum(1 for _ in call("win", mint("a"), module=m)) == 1
        assert sum(1 for _ in call("win", mint("b"), module=m)) == 0
        assert sum(1 for _ in call("win", mint("c"), module=m)) == 0


class TestF008DerefWalkTemplateFreeze:
    """A01-F008 seam: `_deref_walk` (the findall/bagof/setof + tabling snapshot
    walker) was blind to tuple, KWTerm, DictTerm and the Seg types, and dropped
    Compound `_position`. A snapshot over such a template decayed to unbound
    after backtracking. Both walkers now delegate to `__walk__` hooks.
    """

    def _bound(self):
        from clausal.logic.solve import _deref_walk
        t = Trail()
        X = Var()
        unify(X, 1, t)
        return _deref_walk, t, X

    def test_tuple_template_frozen(self):
        _deref_walk, t, X = self._bound()
        snap = _deref_walk((X, "tag"))
        t.reset()
        assert snap == (1, "tag")  # was (unbound, "tag") after reset

    def test_kwterm_template_frozen(self):
        from clausal.terms import KWTerm
        _deref_walk, t, X = self._bound()
        snap = _deref_walk(KWTerm("r", a=X, b=2))
        t.reset()
        assert deref(snap.a) == 1 and snap.b == 2

    def test_dictterm_template_frozen(self):
        from clausal.terms import DictTerm
        _deref_walk, t, X = self._bound()
        snap = _deref_walk(DictTerm({"k": X}))
        t.reset()
        assert deref(dict(snap.items())["k"]) == 1

    def test_segstring_template_promotes_and_freezes(self):
        from clausal.terms import SegString, VarSeg
        from clausal.logic.solve import _deref_walk
        t = Trail()
        A = Var()
        unify(A, chars("!"), t)
        snap = _deref_walk(SegString(["hi", VarSeg(A)]))
        t.reset()
        assert snap == chars("hi!")  # F018 promotion preserved through _deref_walk

    def test_compound_position_preserved(self):
        from clausal.terms import Compound
        _deref_walk, t, X = self._bound()
        snap = _deref_walk(Compound("f", (X,), _position=(1, 2, 3, 4)))
        t.reset()
        assert deref(snap.args[0]) == 1
        assert snap._position == (1, 2, 3, 4)  # was dropped by the Compound arm

    def test_term_instance_nested_in_compound_frozen(self):
        from clausal.logic.predicate import PredicateMeta
        from clausal.terms import Compound
        _deref_walk, t, X = self._bound()
        pt = PredicateMeta("audit_f008", (), {"_fields": ("a", "b")})
        snap = _deref_walk(Compound("f", (pt(X, 2),)))
        t.reset()
        assert deref(snap.args[0].a) == 1 and snap.args[0].b == 2


class TestCToolkitGuards:
    def test_deref_walk_deep_nesting_no_crash(self):
        import clausal.logic.tabling  # registers the _VAR sentinel
        from clausal.logic.solve import _deref_walk
        x = []
        for _ in range(40000):
            x = [x]
        _deref_walk(x)  # must not segfault

    def test_deref_walk_depth_guard_graceful(self):
        import clausal.logic.tabling
        from clausal.logic.solve import _deref_walk
        x = []
        for _ in range(60000):
            x = [x]
        with pytest.raises(RecursionError):
            _deref_walk(x)

    def test_subgoal_key_depth_guard_graceful(self):
        from clausal.logic.tabling import _normalize_for_key
        x = []
        for _ in range(60000):
            x = [x]
        with pytest.raises(RecursionError):
            _normalize_for_key(x)

    def test_head_list_unify_c_python_parity(self):
        from clausal.logic.runtime.list_unify import (
            _head_list_unify_input_py, _head_list_unify_output_py,
            _head_list_unify_input, _head_list_unify_output)
        from clausal.terms import SegList, ConcreteSeg, VarSeg, SegString

        def snap(vs):
            return ["VAR" if is_var(deref(v)) else repr(deref(v)) for v in vs]

        def make_target(kind):
            return {
                "var": lambda: Var(),
                "list": lambda: [1, 2, 3],
                "str": lambda: chars("abc"),
                "bytes": lambda: b"abc",
                "shortlist": lambda: [1],
                "empty": lambda: [],
                "int": lambda: 7,
                "seglist_ground": lambda: SegList([ConcreteSeg([1, 2, 3])]),
                "segstr_ground": lambda: SegString(["ab", "c"]),
                "seglist_open": lambda: SegList([ConcreteSeg([1]), VarSeg(Var())]),
                "segstr_open": lambda: SegString(["a", VarSeg(Var())]),
            }[kind]()

        kinds = ["var", "list", "str", "bytes", "shortlist", "empty", "int",
                 "seglist_ground", "segstr_ground", "seglist_open", "segstr_open"]
        shapes = [(1, True, 0), (2, False, 0), (1, True, 1), (0, True, 0), (3, False, 0)]
        mismatches = []
        for pair, label in (((_head_list_unify_input, _head_list_unify_input_py), "in"),
                            ((_head_list_unify_output, _head_list_unify_output_py), "out")):
            fc, fp = pair
            for kind in kinds:
                for nb, has_star, na in shapes:
                    for prebind in (False, True):
                        res = {}
                        for which, fn in (("C", fc), ("Py", fp)):
                            tr = Trail()
                            tgt = make_target(kind)
                            before = [Var() for _ in range(nb)]
                            star = Var() if has_star else None
                            after = [Var() for _ in range(na)]
                            if prebind:
                                for i, v in enumerate(before):
                                    unify(v, 10 + i, tr)
                                if star is not None:
                                    unify(star, [77], tr)
                                for i, v in enumerate(after):
                                    unify(v, 20 + i, tr)
                            try:
                                r = fn(tgt, before, star, after, tr)
                                res[which] = (repr(r), snap(before),
                                              snap([star] if star is not None else []),
                                              snap(after))
                            except Exception as e:  # noqa: BLE001
                                res[which] = ("EXC:" + type(e).__name__,)
                        if res["C"] != res["Py"]:
                            mismatches.append((label, kind, nb, has_star, na, prebind, res))
        assert mismatches == []

    def test_refcount_stable_complete_table_loop(self, load, refcount_stable):
        m = load("rc1", PATH_SRC.replace("path", "pathrc").replace("edge", "edgerc"))

        def thunk():
            Y = Var()
            for _ in call("pathrc", 1, Y, module=m):
                pass

        refcount_stable(thunk, iterations=1500)

    def test_refcount_stable_fill_abolish_loop(self, load, refcount_stable):
        m = load("rc2", PATH_SRC.replace("path", "pathrd").replace("edge", "edgerd"))
        db = m.__clausal_module__.db

        def thunk():
            db.abolish_table("pathrd", 2)
            Y = Var()
            for _ in call("pathrd", 1, Y, module=m):
                pass

        refcount_stable(thunk, iterations=1500)

    def test_solutions_propagates_runtime_error(self, load):
        # control for A04-F009: the solutions() driver does NOT swallow it
        m = load("rte_sol", RTE_SRC.replace("rte", "rtesol"))
        def boom_rt():
            raise RuntimeError("user error")
        m.__clausal_module__.module_dict["boom_rt"] = boom_rt
        from clausal.logic.trampoline import StepGenerator, solutions
        pred = m.__clausal_module__.module_dict["rtesol"]
        sg = StepGenerator(pred._get_dispatch(), None, None, None, Var(), Trail())
        with pytest.raises(RuntimeError):
            solutions(sg)


# ══ A04-F001: SLG completion loses suspended-consumer derivations ═════════════


class TestF001CompletionLosesConsumers:
    def test_two_recursive_clauses_facts_first(self, load):
        # A04-F001: the leader drives its dispatch to a FIXPOINT (re-run until no
        # new answer), so both recursive clauses' derived answers are kept.
        m = load("f001a", TWOREC_FACTSFIRST_SRC)
        X = Var()
        got = sorted(set(a[0] for a in answers(call("p", X, module=m), X)))
        assert got == [1, 2, 3, 4, 5]

    def test_two_recursive_clauses_rec_first(self, load):
        # A04-F001: clause order no longer matters for single-table recursion.
        m = load("f001b", TWOREC_RECFIRST_SRC)
        X = Var()
        got = sorted(set(a[0] for a in answers(call("p", X, module=m), X)))
        assert got == [1, 2, 3, 4, 5]

    def test_mutual_recursion_rec_first_ra(self, load):
        # A04-F001: SCC-aware completion — the nested table (rb) called before
        # ra derives a base answer no longer completes empty. It stays a dormant
        # SCC member, is re-led from the root's fixpoint until the whole SCC
        # stabilizes, then the root completes it. ra(1,·) = [2,4] in any order.
        m = load("f001c", MUTUAL_RECFIRST_SRC)
        Y = Var()
        got = sorted(set(a[0] for a in answers(call("ra", 1, Y, module=m), Y)))
        assert got == [2, 4]

    def test_mutual_recursion_rec_first_rb(self, load):
        m = load("f001d", MUTUAL_RECFIRST_SRC.replace("ra", "rc").replace("rb", "rd")
                 .replace("la", "lc").replace("lb", "ld"))
        Y = Var()
        got = sorted(set(a[0] for a in answers(call("rd", 1, Y, module=m), Y)))
        assert got == [1, 3]

    def test_mutual_recursion_query_order_invariant(self, load):
        # A04-F001 acceptance: the tabled solution set is independent of which
        # SCC member is queried first.
        m1 = load("f001inv1", MUTUAL_RECFIRST_SRC)
        Ya = Var()
        ra_first = sorted(set(a[0] for a in answers(call("ra", 1, Ya, module=m1), Ya)))
        m2 = load("f001inv2", MUTUAL_RECFIRST_SRC)
        _query_cache.clear()
        list(call("rb", 1, Var(), module=m2))   # query rb first
        Ya2 = Var()
        _query_cache.clear()
        ra_after = sorted(set(a[0] for a in answers(call("ra", 1, Ya2, module=m2), Ya2)))
        assert ra_first == ra_after == [2, 4]

    def test_mutual_recursion_facts_first_control(self, load):
        # in-tree fixture ordering (base clauses first) — the passing control
        src = MUTUAL_RECFIRST_SRC.replace("ra", "re").replace("rb", "rf") \
                                 .replace("la", "le").replace("lb", "lf")
        # move base clauses before recursive ones
        src = src.replace(
            "re(X, Y) <- (\n    rf(X, Z),\n    le(Z, Y)\n)\nre(X, Y) <- le(X, Y)",
            "re(X, Y) <- le(X, Y)\nre(X, Y) <- (\n    rf(X, Z),\n    le(Z, Y)\n)")
        src = src.replace(
            "rf(X, Y) <- (\n    re(X, Z),\n    lf(Z, Y)\n)\nrf(X, Y) <- lf(X, Y)",
            "rf(X, Y) <- lf(X, Y)\nrf(X, Y) <- (\n    re(X, Z),\n    lf(Z, Y)\n)")
        m = load("f001e", src)
        Y = Var()
        got = sorted(set(a[0] for a in answers(call("re", 1, Y, module=m), Y)))
        assert got == [2, 4]


# ══ A04-F001 (transitive): ≥3-node SCCs complete prematurely ══════════════════


class TestF001TransitiveSccDeps:
    """SCC dependency edges must propagate TRANSITIVELY: a middle member of a
    longer cycle (calls a fresh nested leader, never an on-stack ancestor
    directly) ends with dependencies only via that nested dormant leader; it
    must not complete while the component is still growing."""

    def test_three_cycle_root_query(self, load):
        m = load("f001s1", _rename_scc3("a"))
        Y = Var()
        got = sorted(set(v[0] for v in answers(call("ar1", 1, Y, module=m), Y)))
        assert got == [2, 5]

    def test_three_cycle_middle_query(self, load):
        m = load("f001s2", _rename_scc3("b"))
        Y = Var()
        got = sorted(set(v[0] for v in answers(call("br2", 1, Y, module=m), Y)))
        assert got == [3, 6]

    def test_three_cycle_last_query(self, load):
        m = load("f001s3", _rename_scc3("c"))
        Y = Var()
        got = sorted(set(v[0] for v in answers(call("cr3", 1, Y, module=m), Y)))
        assert got == [4, 7]

    def test_three_cycle_members_complete_correctly_after_root(self, load):
        # After the root query, the swept members' tables must hold the full
        # component fixpoint (not be frozen empty/partial mid-fixpoint).
        m = load("f001s4", _rename_scc3("d"))
        list(call("dr1", 1, Var(), module=m))
        Y2, Y3 = Var(), Var()
        got2 = sorted(set(v[0] for v in answers(call("dr2", 1, Y2, module=m), Y2)))
        got3 = sorted(set(v[0] for v in answers(call("dr3", 1, Y3, module=m), Y3)))
        assert (got2, got3) == ([3, 6], [4, 7])
        store = m.__clausal_module__.db.table_store
        assert "evaluating" not in {e.status for e in store.values()}


# ══ A04-F001 (re-lead replay): re-led member streams only NEW answers ═════════


class TestF001ReLeadReplay:
    """Re-leading a dormant SCC member must replay the already-tabled answers
    to the new call site (like the consumer and complete paths do) — otherwise
    joins against the earlier answers are silently lost."""

    def test_double_join_pa(self, load):
        m = load("f001r1", RELEAD_JOIN_SRC)
        X = Var()
        got = sorted(set(v[0] for v in answers(call("pa", X, module=m), X)))
        assert got == [1, 2, 3]

    def test_double_join_pb_same_module(self, load):
        m = load("f001r1", RELEAD_JOIN_SRC)  # same module: after pa query
        list(call("pa", Var(), module=m))
        X = Var()
        got = sorted(set(v[0] for v in answers(call("pb", X, module=m), X)))
        assert got == [2, 3]

    def test_double_join_pb_first(self, load):
        src = RELEAD_JOIN_SRC.replace("pa", "pc").replace("pb", "pd") \
                             .replace("nx", "ny")
        m = load("f001r2", src)
        X = Var()
        got = sorted(set(v[0] for v in answers(call("pd", X, module=m), X)))
        assert got == [2, 3]

    def test_cross_product_of_two_growing_tables(self, load):
        # (old ta answer × new tb answer) pairs exist only if a re-led member
        # REPLAYS its tabled answers each pass — new-only streaming loses them.
        m = load("f001r3", CROSS_JOIN_SRC)
        X, Y = Var(), Var()
        got = sorted(set(answers(call("rr", X, Y, module=m), X, Y)))
        assert got == [(1, 10), (1, 20), (2, 10), (2, 20)]


# ══ A04-F002: _naf_tabled unsound on never-called / other-variant subgoals ════


class TestF002NafTabledNoEntry:
    def test_naf_before_any_positive_query(self, load):
        # A04-F002/F003 FIXED: _naf_tabled now SPAWNS the positive subgoal
        # (dispatch threaded from the compiler as $naf_db) and decides
        # against the completed table.
        m = load("f002a", NAF_SRC)
        R = Var()
        got = answers(call("ntp", R, module=m), R)
        assert got == []  # tp(1,2) is a fact — negation must fail

    def test_naf_after_positive_query_control(self, load):
        m = load("f002b", NAF_SRC.replace("tp", "tq").replace("ntp", "ntq"))
        assert sum(1 for _ in call("tq", 1, 2, module=m)) == 1
        R = Var()
        assert answers(call("ntq", R, module=m), R) == []

    def test_naf_ignores_subsuming_complete_variant(self, load):
        # A04-F002: `not tr2(1,2)` has no exact-variant entry, but the complete
        # var-variant table `tr2(_,_)` (populated by the query below) subsumes
        # it and holds (1,2) — negation must fail. (Fixture built ntp-first so
        # "tp" -> "tr2" does not corrupt "ntp".)
        m = load("f002c", NAF_SRC.replace("ntp", "ntr").replace("tp", "tr2"))
        X, Y = Var(), Var()
        assert answers(call("tr2", X, Y, module=m), X, Y) == [(1, 2)]
        R = Var()
        got = answers(call("ntr", R, module=m), R)
        assert got == []

    def test_acyclic_negation_chain_truth(self, load):
        # A04-F002/F003 FIXED: never-yet-called variants are spawned.
        m = load("f002d", EVEN_ODD_SRC)
        X = Var()
        got = sorted(a[0] for a in answers(call("even_node", X, module=m), X))
        assert got == [2]  # even_node(1) fails: odd_node(2) is true


# ══ A04-F003: WFS resolution is mode- and order-dependent ═════════════════════


class TestF003WfsModeOrderDependence:
    def test_asym_win_b_first_ground(self, load):
        # A04-F003 FIXED: negative-subgoal spawning + disjunctive conditions
        m = load("f003a", WIN_ASYM_SRC.replace("win", "wing").replace("move", "movg"))
        assert sum(1 for _ in call("wing", "b", module=m)) == 0

    def test_asym_win_var_mode(self, load):
        # A04-F003 FIXED: var-mode and ground-mode now agree with docs/wfs.md
        m = load("f003b", WIN_ASYM_SRC.replace("win", "winv").replace("move", "movv"))
        X = Var()
        got = sorted(a[0] for a in answers(call("winv", X, module=m), X))
        assert got == [mint("a")]


# ══ A04-F004: query_wfs truth annotation is a stub ════════════════════════════


class TestF004QueryWfsStub:
    def test_query_wfs_reports_undefined(self, load):
        # A04-F004: query_wfs reads the tabled entry's real conditions — the
        # symmetric-win answers are internally conditional, so both are
        # annotated Undefined instead of a hardcoded True.
        m = load("f004", WIN_SYM_SRC.replace("win", "winu").replace("move", "movu"))
        X = Var()
        res = query_wfs(m.winu(X), {"X": X}, m)
        assert len(res) == 2
        assert all(r["_truth"] is Undefined for r in res)


# ══ A04-F005: unhashable tabled answers crash add_answer ══════════════════════


class TestF005UnhashableAnswers:
    def test_list_answer(self, load):
        # A04-F005: a frozen list answer is canonicalized to a hashable key for
        # answer_set membership (add_answer no longer crashes on `in`).
        m = load("f005a", TS_LIST_SRC)
        V = Var()
        got = answers(call("ts", V, module=m), V)
        assert got == [([1, 2, 3],)]

    def test_dict_answer_cache_hit_is_frozen(self, load):
        # A04-F005: the STORED answer is now correctly frozen — a dict whose
        # value was body-bound derefs to the ground {"k": 7} on the cache-hit
        # (second) query. `_deref_walk` (both impls) rebuilds dict values so the
        # inner Var does not decay on backtracking.
        m = load("f005b", TD_DICT_SRC)

        def one_query():
            _query_cache.clear()
            V = Var()
            return answers(call("td", V, module=m), V)

        one_query()                       # populate the table (leader)
        assert one_query() == [({"k": 7},)]   # cache hit → frozen answer

    @pytest.mark.xfail(strict=False, reason="A04-F005 residual: the tabling "
                       "LEADER yields the live body binding, and a ++-built dict "
                       "holds a raw Var (X bound to 7 but the dict still "
                       "references X), so the FIRST (leader) query derefs to "
                       "{'k': <Var>}. The stored/cache answer is correctly "
                       "frozen (see test_dict_answer_cache_hit_is_frozen); "
                       "presenting frozen answers from the leader is a separate "
                       "change — see the residual note in the archived todo.")
    def test_dict_answer_leader_query(self, load):
        m = load("f005b2", TD_DICT_SRC)
        V = Var()
        got = answers(call("td", V, module=m), V)
        assert got == [({"k": 7},)]

    def test_term_instance_answer(self, load):
        # A04-F005: a declared-functor term instance (unhashable) is
        # canonicalized to (name, *fields) for answer_set membership.
        m = load("f005c", TW_TERM_SRC)
        V = Var()
        got = answers(call("tw", V, module=m), V)
        # R6: the answer is a cell -- slot 0 is the functor.
        assert len(got) == 1 and got[0][0][0] == "wrap"


# ══ A04-F006: cross-type variant/answer conflation ════════════════════════════


class TestF006CrossTypeConflation:
    def test_untabled_control_keeps_all_four(self, load):
        # 4 facts, 4 answers, types preserved
        m = load("f006", TYPES_SRC)
        V = Var()
        got = []
        for _ in call("utt", V, module=m):
            v = deref(V)
            got.append((repr(v), type(v).__name__))
        assert got == [("1", "int"), ("True", "bool"), ("2.0", "float"), ("2", "int")]

    def test_tabled_matches_untabled_solution_set(self, load):
        # A04-F006: type-tagged variant/dedup keys keep 1/True/2.0/2 distinct,
        # so the tabled solution set matches the untabled twin (types preserved).
        m = load("f006", TYPES_SRC)
        V = Var()
        got = []
        for _ in call("tt", V, module=m):
            v = deref(V)
            got.append((repr(v), type(v).__name__))
        assert got == [("1", "int"), ("True", "bool"), ("2.0", "float"), ("2", "int")]

    def test_subgoal_keys_distinguish_cross_type(self):
        # A04-F006: numeric leaves are type-tagged, so 1/True/1.0 no longer
        # share a variant key (was a conflation guard pinning the bug).
        from clausal.logic.tabling import make_subgoal_key
        tr = Trail()
        assert make_subgoal_key([1], tr) != make_subgoal_key([True], tr)
        assert make_subgoal_key([1], tr) != make_subgoal_key([1.0], tr)
        assert make_subgoal_key([True], tr) != make_subgoal_key([1.0], tr)
        # same-type calls still share a key (variant identity preserved)
        assert make_subgoal_key([1], tr) == make_subgoal_key([1], tr)


# ══ A04-F007: abnormal leader exit poisons the table ══════════════════════════


class TestF007PoisonedEvaluatingTables:
    def test_once_then_full_query(self, load):
        m = load("f007a", PATH_SRC.replace("path", "patha").replace("edge", "edgea"))
        Y = Var()
        t = once(m.patha(1, Y), m)
        assert t is not None and deref(Y) == 2
        _query_cache.clear()
        gc.collect()  # ensure the abandoned solve generator is finalized
        Y2 = Var()
        got = sorted(set(a[0] for a in answers(call("patha", 1, Y2, module=m), Y2)
                         if not is_var(a[0])))
        assert got == [2, 3, 4]

    def test_exception_then_requery(self, load):
        # A04-F007: a body exception drops the poisoned entry (the drive closes
        # the StepGenerator chain), so the re-query recomputes and re-raises
        # rather than silently returning the pre-crash partial answer set.
        m = load("f007b", BOOM_SRC)
        with pytest.raises(ZeroDivisionError):
            list(call("boom", Var(), module=m))
        with pytest.raises(ZeroDivisionError):
            list(call("boom", Var(), module=m))

    def test_poisoned_entry_status_mechanism(self, load):
        # A04-F007: an abandoned once() no longer leaves an "evaluating" entry —
        # the tabled-wrapper cleanup drops it on GeneratorExit (was a guard
        # pinning the poisoned state).
        m = load("f007c", PATH_SRC.replace("path", "pathc").replace("edge", "edgec"))
        Y = Var()
        once(m.pathc(1, Y), m)
        gc.collect()
        store = m.__clausal_module__.db.table_store
        statuses = {e.status for e in store.values()}
        assert "evaluating" not in statuses


class TestF007RecFirstAbandonment:
    """A04-F007 residue: with the RECURSIVE clause first, a consumer suspends
    before the first answer exists, so at once()-abandonment the
    SuspendedConsumer keeps the parked leader frame reachable — GeneratorExit
    is never delivered to the wrapper's cleanup and the module stays poisoned
    for life. The root driver must repair the table itself."""

    def test_recfirst_once_then_full_query(self, load):
        m = load("f007r1", RECFIRST_ONCE_SRC)
        Y = Var()
        t = once(m.qq(Y), m)
        assert t is not None and deref(Y) == 1
        _query_cache.clear()
        gc.collect()
        Y2 = Var()
        got = sorted(set(v[0] for v in answers(call("qq", Y2, module=m), Y2)
                         if not is_var(v[0])))
        assert got == [1, 2, 3, 4, 5]

    def test_recfirst_once_no_evaluating_entries(self, load):
        m = load("f007r2", RECFIRST_ONCE_SRC.replace("qq", "qr").replace("ee", "er"))
        Y = Var()
        once(m.qr(Y), m)
        gc.collect()
        store = m.__clausal_module__.db.table_store
        assert "evaluating" not in {e.status for e in store.values()}
        from clausal.logic.tabling import _leader_ctx
        assert _leader_ctx.stack == []  # abandoned leader must not linger

    def test_recfirst_mutual_once_then_full_queries(self, load):
        src = MUTUAL_RECFIRST_SRC.replace("ra", "rg").replace("rb", "rh") \
                                 .replace("la", "lg").replace("lb", "lh")
        m = load("f007r3", src)
        Y = Var()
        once(m.rg(1, Y), m)
        _query_cache.clear()
        gc.collect()
        Ya, Yb = Var(), Var()
        got_a = sorted(set(v[0] for v in answers(call("rg", 1, Ya, module=m), Ya)
                           if not is_var(v[0])))
        _query_cache.clear()
        got_b = sorted(set(v[0] for v in answers(call("rh", 1, Yb, module=m), Yb)
                           if not is_var(v[0])))
        assert (got_a, got_b) == ([2, 4], [1, 3])
        store = m.__clausal_module__.db.table_store
        assert "evaluating" not in {e.status for e in store.values()}


# ══ A04-F008: root-level suspend sentinel yields spurious solution ════════════


class TestF008RootSuspendSpuriousSolution:
    def test_no_unbound_answers_from_consumer_query(self, load):
        # A04-F008: every root driver treats (None, _TABLING_SUSPEND) as
        # exhaustion, not a solution, so a root/orphaned consumer never
        # fabricates an unbound answer (defense in depth with F007).
        m = load("f008", PATH_SRC.replace("path", "pathe").replace("edge", "edgee"))
        Y = Var()
        once(m.pathe(1, Y), m)  # poison: leaves consumer-only table state
        gc.collect()
        Y2 = Var()
        got = answers(call("pathe", 1, Y2, module=m), Y2)
        assert all(not is_var(v) for (v,) in got), f"spurious unbound answer: {got}"


# ══ A04-F009: C _drive_until_yield swallows RuntimeError ══════════════════════


class TestF009RuntimeErrorSwallowed:
    def test_call_propagates_user_runtime_error(self, load):
        # A04-F009: a user RuntimeError from a ++ escape must propagate out of
        # call()/solve()/once() — the C _drive_until_yield now clears only
        # PEP-479 StopIteration wrappers, not every RuntimeError.
        m = load("f009", RTE_SRC)
        def boom_rt():
            raise RuntimeError("user error")
        m.__clausal_module__.module_dict["boom_rt"] = boom_rt
        with pytest.raises(RuntimeError):
            list(call("rte", Var(), module=m))


# ══ A04-F010: when-disjunction fired flag survives backtracking ═══════════════


class TestF010WhenDisjunctionFiredFlag:
    def test_goal_fires_in_second_branch(self, load):
        # A04-F010: branch 1 fires the goal then FAILS (1 == 2); the trailed
        # fired-flag is undone with the branch, so branch 2 (Y is 2) fires the
        # goal in the surviving world. R must be bound, not skipped.
        m = load("f010", WHEN_SRC)
        R = Var()
        got = []
        for _ in call("w8", R, module=m):
            v = deref(R)
            got.append("UNBOUND" if is_var(v) else v)
        assert got == [mint("fired")]

    def test_both_conditions_satisfied_fires_once(self, load):
        # Regression guard: when both disjuncts become true in a SURVIVING
        # branch, the goal still fires (at most once — the second fire sees the
        # bound flag and yields silently), giving exactly one solution.
        m = load("f010b", 'w8b(R) <- (when((nonvar(A) or nonvar(B)), '
                          'R is "fired"), (A is 1, B is 2))\n')
        R = Var()
        got = [deref(R) for _ in call("w8b", R, module=m)]
        assert got == [mint("fired")]


# ══ A04-F011: freeze commits to the first solution of the frozen goal ═════════


class TestF011FreezeFirstSolutionOnly:
    @pytest.mark.xfail(strict=False, reason="A04-F011: frozen goal is semidet — "
                       "choice points of the frozen goal are discarded "
                       "(SWI freeze/2 backtracks); design question parked")
    def test_frozen_goal_backtracks(self, load):
        m = load("f011", FREEZE_SRC)
        X, Y = Var(), Var()
        got = answers(call("f9", X, Y, module=m), X, Y)
        assert got == [(1, 10), (1, 20)]

    def test_frozen_goal_first_solution_binding_guard(self, load):
        # current behaviour: first solution's bindings stick (regression guard)
        m = load("f011b", FREEZE_SRC.replace("f9", "f9b"))
        X, Y = Var(), Var()
        got = answers(call("f9b", X, Y, module=m), X, Y)
        assert got == [(1, 10)]
