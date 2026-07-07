"""A02 compiler heads & indexing — adversarial audit tests (2026-07-05).

Findings ledger: docs/superpowers/audits/2026-07-05-fable-partition/02-compiler-heads/findings.md

Suspected-bug tests assert the *correct* behaviour and are marked
``@pytest.mark.xfail(strict=False)`` with the finding ID; confirmed-correct
behaviour is a plain regression guard.  Run PER FILE only:

    python -m pytest tests/audit_2026_07_05/test_02_compiler_heads.py -v
"""
import datetime
from decimal import Decimal

import pytest

from clausal.import_hook import _load_module
from clausal.logic import solve as solve_mod
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref, is_var, walk
from clausal.terms import ConcreteSeg, SegList, VarSeg


# ── Fixture module ────────────────────────────────────────────────────────────
# All predicates live in ONE module (atoms/functors are module-scoped; loading
# a second copy would mint distinct atom/functor classes that never unify with
# the first load's clauses).

FIXTURE = '''
# first-arg indexing: 4 clauses trigger _INDEX_THRESHOLD; 3-clause twins are
# linear-scan controls.
kind4(1, "one"),
kind4(2, "two"),
kind4(3, "three"),
kind4("x", "ex"),

kind3(1, "one"),
kind3(2, "two"),
kind3("x", "ex"),

strs4("abc", "A"),
strs4("def", "B"),
strs4("ghi", "C"),
strs4("jkl", "D"),

strs3("abc", "A"),
strs3("def", "B"),
strs3("ghi", "C"),

emp4("", "empty"),
emp4("a", "ay"),
emp4("b", "bee"),
emp4("c", "see"),

emp3("", "empty"),
emp3("a", "ay"),
emp3("b", "bee"),

byt4(b"ab", "AB"),
byt4(b"cd", "CD"),
byt4(b"ef", "EF"),
byt4(b"gh", "GH"),

byt3(b"ab", "AB"),
byt3(b"cd", "CD"),
byt3(b"ef", "EF"),

# clause-order preservation: specific and var-headed clauses interleaved
ord6(1, "s1"),
ord6(OV1, "v1"),
ord6(1, "s2"),
ord6(2, "other"),
ord6(OV2, "v2"),
ord6(1, "s3"),

# joint dispatch: pos1 (4 keys) x pos0 (2 keys) = 8 joint keys, coverage 1.0;
# result column is a non-indexable list so it cannot win the selectivity sort.
jnt2("aa", 1, ["a1"]),
jnt2("aa", 2, ["a2"]),
jnt2("aa", 3, ["a3"]),
jnt2("aa", 4, ["a4"]),
jnt2("bb", 1, ["b1"]),
jnt2("bb", 2, ["b2"]),
jnt2("bb", 3, ["b3"]),
jnt2("bb", 4, ["b4"]),

# secondary (hierarchical) dispatch: joint coverage 8/12 < 0.8
sec2("a", 1, ["sa1"]),
sec2("a", 2, ["sa2"]),
sec2("b", 1, ["sb1"]),
sec2("b", 2, ["sb2"]),
sec2("c", 1, ["sc1"]),
sec2("c", 2, ["sc2"]),
sec2("d", 1, ["sd1"]),
sec2("d", 2, ["sd2"]),
sec2("a", SW1, ["sav"]),
sec2("b", SW2, ["sbv"]),
sec2("c", SW3, ["scv"]),
sec2("d", SW4, ["sdv"]),

# compound-keyed and atom-keyed indexing
-private([fc(FCA), gc(GCA)])
cmq4(fc(1), ["f1"]),
cmq4(fc(2), ["f2"]),
cmq4(fc(3), ["f3"]),
cmq4(gc(9), ["g9"]),

-private([red, green, blue, yellow])
col4(red, 1),
col4(green, 2),
col4(blue, 3),
col4(yellow, 4),
colr(red, CR) <- (CR is "atomrule")

# list-structure dispatch: nil/cons/var heads survive in RULE clauses
# (fact normalization hoists a ground [] head, so facts never trigger it)
ld2([], LR) <- (LR is "nil2")
ld2([LH, *LT], LR2) <- (LR2 is "cons2")
ld2(LX, LR3) <- (LR3 is "any2")

# multi-star heads
ms([*MA, "x", *MB], MA, MB),
ms2([*MC, 120, *MD], MC, MD),
ms3([*ME, 1, *MF, 2], ME, MF),
mst([*MG, 1, *MH, 2, 3], MG, MH),
mchr([*MI, "a", *MJ, "b"], MI, MJ),
mss([*MK, *ML], MK, ML),
ssok([*MM, "d"], MM),
nst([[NN1, *NN2], *NN3], NN1, NN2, NN3),

# duplicate head vars
same(DD, DD),
dupl(DE, [DE, 1]),
dz([DF, 1], [DF, 2]),

# rule-head literals (atomic kinds keep the match-guard path)
fine_int(FN, 20000) <- (FN > 10)
flag_t(FT, True) <- (FT > 0)
negf(-5, "ok"),
negr(-7, NR) <- (NR is "rok")
shr("abc", SR) <- (SR is 1)
bhr(b"ab", BR) <- (BR is 2)
tup((1, 2), TR) <- (TR is "t")

# dict / set heads
dh({"k": DHV}, DHV),
sth({1, 2}, "set"),

# output-mode list construction with multiple body solutions
outl([OA, OB]) <- (in_(OA, [1, 2]), OB == OA + 10)

# goal-op shapes (terms_to_goalop / ir)
orp(GX) <- (GX is 1 or GX is 2 or GX is 3)
iffu(IX, IA) <- If(IX > 2, IA is "big", IA is "small")
iffl(IL, IA2) <- If(IL is [1], IA2 is "one", IA2 is "other")
ftr(FR) <- (False, FR is 1)
ttr(TT) <- (True, TT is 1)

# TRO across index buckets
cds(0, "zero"),
cds(9, "nine"),
cds(CN, CRR) <- (CN > 0, CM == CN - 1, cds(CM, CRR))

# binding leak: single-clause bucket (skip_trail) binds then fails
st4(1, STR) <- (STR is "a", 1 > 2)
st4(2, "b"),
st4(3, "c"),
st4(4, "d"),

# call-site specialisation (static args into an indexed callee)
usek(UR) <- kind4(1, UR)
usekl(UR2) <- kind4(["x"], UR2)

# str/charlist head coalescing (F095): same bucket, both clauses fire
coll("abc", "s"),
coll(["a", "b", "c"], "l"),
coll("def", "d"),
coll("ghi", "g"),

# dynamic predicates for runtime-assertz probes (one per test, no coupling)
-dynamic(dyn_date/2)
dyn_date("seed", 0),
-dynamic(dyn_tuple/2)
dyn_tuple("seed", 0),
-dynamic(dyn_set/2)
dyn_set("seed", 0),
-dynamic(dyn_dec/2)
dyn_dec("seed", 0),
-dynamic(dynk/2)
dynk(1, "one"),
dynk(2, "two"),
dynk(3, "three"),
dynk(4, "four"),
addk() <- (assertz(dynk(5, "five")))
'''

BAD_FIXTURE = '''bad(BX) <- (good(BX), BY)
good(1),
'''


@pytest.fixture(scope="module")
def moddict(tmp_path_factory):
    p = tmp_path_factory.mktemp("a02") / "a02_fixture.clausal"
    p.write_text(FIXTURE)
    return _load_module("a02_audit_fixture", str(p)).__dict__


@pytest.fixture(scope="module")
def mod(moddict):
    return moddict["$module"]


def collect(mod, name, *args, outv=()):
    """Solutions as walked snapshots of *outv* (query cache cleared: it keys
    by arg types, and these tests call the same predicate with many types)."""
    solve_mod._query_cache.clear()
    snaps = []
    for _ in call(name, *args, module=mod):
        snaps.append(tuple(walk(deref(v)) for v in outv))
    return snaps


# ── A02-F001: indexed dispatch loses solutions for non-var args whose index
# key is uncomputable (partial containers, SegLists, exotic numeric types) ────


class TestF001IndexedDispatchPartialTerms:
    # controls: the linear-scan twins find these solutions
    def test_control_partial_charlist_unindexed(self, mod):
        X, R = Var(), Var()
        assert collect(mod, "strs3", [X, "b", "c"], R, outv=[X, R]) == [("a", "A")]

    def test_control_empty_list_vs_empty_str_unindexed(self, mod):
        R = Var()
        assert collect(mod, "emp3", [], R, outv=[R]) == [("empty",)]

    def test_control_partial_codelist_unindexed(self, mod):
        X, R = Var(), Var()
        assert collect(mod, "byt3", [97, X], R, outv=[X, R]) == [(98, "AB")]

    def test_control_seglist_unindexed(self, mod):
        A, R = Var(), Var()
        sl = SegList([VarSeg(A), ConcreteSeg(["c"])])
        assert collect(mod, "strs3", sl, R, outv=[A, R]) == [("ab", "A")]

    def test_control_decimal_unindexed(self, mod):
        R = Var()
        assert collect(mod, "kind3", Decimal(1), R, outv=[R]) == [("one",)]

    @pytest.mark.xfail(strict=False, reason="A02-F001: partial charlist caller routed to defaults, misses str bucket")
    def test_partial_charlist_indexed(self, mod):
        X, R = Var(), Var()
        assert collect(mod, "strs4", [X, "b", "c"], R, outv=[X, R]) == [("a", "A")]

    @pytest.mark.xfail(strict=False, reason="A02-F001: [] caller misses \"\" bucket")
    def test_empty_list_vs_empty_str_indexed(self, mod):
        R = Var()
        assert collect(mod, "emp4", [], R, outv=[R]) == [("empty",)]

    @pytest.mark.xfail(strict=False, reason="A02-F001: partial code-list caller misses bytes bucket")
    def test_partial_codelist_indexed(self, mod):
        X, R = Var(), Var()
        assert collect(mod, "byt4", [97, X], R, outv=[X, R]) == [(98, "AB")]

    @pytest.mark.xfail(strict=False, reason="A02-F001: SegList caller misses str bucket")
    def test_seglist_indexed(self, mod):
        A, R = Var(), Var()
        sl = SegList([VarSeg(A), ConcreteSeg(["c"])])
        assert collect(mod, "strs4", sl, R, outv=[A, R]) == [("ab", "A")]

    @pytest.mark.xfail(strict=False, reason="A02-F001: Decimal caller (outside _INDEXABLE_TYPES) misses int bucket; cf. A01-D001")
    def test_decimal_indexed(self, mod):
        R = Var()
        assert collect(mod, "kind4", Decimal(1), R, outv=[R]) == [("one",)]

    @pytest.mark.xfail(strict=False, reason="A02-F001: joint dispatch, partial container at pos_j hits empty joint-default")
    def test_joint_partial_container(self, mod):
        X, R = Var(), Var()
        assert collect(mod, "jnt2", [X, "a"], 2, R, outv=[X, R]) == [("a", ["a2"])]

    @pytest.mark.xfail(strict=False, reason="A02-F001: secondary dispatch, partial container at level-0 pos hits always-fail default")
    def test_secondary_partial_container(self, mod):
        X, R = Var(), Var()
        assert collect(mod, "sec2", [X], 1, R, outv=[X, R]) == [("a", ["sa1"]), ("a", ["sav"])]


# ── A02-F002: list-structure dispatch drops non-list/str/Var callers ─────────


class TestF002ListDispatchFallthrough:
    # controls: list / str / var callers route correctly
    def test_control_nil(self, mod):
        R = Var()
        assert collect(mod, "ld2", [], R, outv=[R]) == [("nil2",), ("any2",)]

    def test_control_cons(self, mod):
        R = Var()
        assert collect(mod, "ld2", [9], R, outv=[R]) == [("cons2",), ("any2",)]

    def test_control_str(self, mod):
        R = Var()
        assert collect(mod, "ld2", "ab", R, outv=[R]) == [("cons2",), ("any2",)]

    def test_control_var_enumerates_all(self, mod):
        X, R = Var(), Var()
        assert collect(mod, "ld2", X, R, outv=[R]) == [("nil2",), ("cons2",), ("any2",)]

    def test_int_caller_matches_var_clause(self, mod):
        R = Var()
        assert collect(mod, "ld2", 5, R, outv=[R]) == [("any2",)]

    def test_tuple_caller_matches_var_clause(self, mod):
        R = Var()
        assert collect(mod, "ld2", (1, 2), R, outv=[R]) == [("any2",)]

    def test_bytes_caller(self, mod):
        R = Var()
        assert collect(mod, "ld2", b"ab", R, outv=[R]) == [("cons2",), ("any2",)]

    @pytest.mark.xfail(strict=False, reason="A02-F002: non-ground SegList vs cons head needs SegList-vs-partial-pattern unify, blocked on F030 (Phase 6). The else-arm fix routes it to the var clause (any2); cons2 requires destructuring [1,*A] against [LH,*LT], which _head_list_unify_input returns False for by design.")
    def test_seglist_caller(self, mod):
        A, R = Var(), Var()
        sl = SegList([ConcreteSeg([1]), VarSeg(A)])
        assert collect(mod, "ld2", sl, R, outv=[R]) == [("cons2",), ("any2",)]


# ── A02-F003: unguarded accept-all wildcard for unhandled head-literal types
# (reachable via runtime assertz — no fact normalization on that path) ────────


class TestF003ExoticHeadWildcard:
    def _assert_fact(self, mod, cls, *args):
        solve_mod._query_cache.clear()
        list(call("assertz", cls(*args), module=mod))

    def test_control_date_true_positive(self, mod, moddict):
        self._assert_fact(mod, moddict["dyn_date"], datetime.date(2026, 1, 1), 1)
        R = Var()
        assert (1,) in collect(mod, "dyn_date", datetime.date(2026, 1, 1), R, outv=[R])

    def test_date_mismatch_must_fail(self, mod, moddict):
        self._assert_fact(mod, moddict["dyn_date"], datetime.date(2026, 1, 1), 1)
        R = Var()
        assert collect(mod, "dyn_date", datetime.date(1999, 9, 9), R, outv=[R]) == []

    def test_date_output_mode_binds(self, mod, moddict):
        self._assert_fact(mod, moddict["dyn_date"], datetime.date(2026, 1, 1), 1)
        X, R = Var(), Var()
        sols = collect(mod, "dyn_date", X, R, outv=[X, R])
        assert (datetime.date(2026, 1, 1), 1) in sols

    def test_tuple_mismatch_must_fail(self, mod, moddict):
        self._assert_fact(mod, moddict["dyn_tuple"], (1, 2), 100)
        R = Var()
        assert collect(mod, "dyn_tuple", (9, 9), R, outv=[R]) == []

    def test_set_mismatch_must_fail(self, mod, moddict):
        self._assert_fact(mod, moddict["dyn_set"], {3, 4}, 200)
        R = Var()
        assert collect(mod, "dyn_set", {5, 6}, R, outv=[R]) == []

    def test_decimal_mismatch_must_fail(self, mod, moddict):
        self._assert_fact(mod, moddict["dyn_dec"], Decimal("2.5"), 9)
        R = Var()
        assert collect(mod, "dyn_dec", Decimal("7.7"), R, outv=[R]) == []


# ── A02-F004: multi-star guard, trailing fixed after the last star ───────────


class TestF004MultiStarTrailingFixed:
    # controls: no trailing fixed after the last star — all fine
    def test_control_fixed_between_stars(self, mod):
        A, B = Var(), Var()
        assert collect(mod, "ms", [1, "x", 2], A, B, outv=[A, B]) == [([1], [2])]

    def test_control_enumerates_splits(self, mod):
        A, B = Var(), Var()
        assert collect(mod, "ms", ["x", "x"], A, B, outv=[A, B]) == [([], ["x"]), (["x"], [])]

    def test_control_adjacent_stars(self, mod):
        A, B = Var(), Var()
        assert collect(mod, "mss", [1, 2], A, B, outv=[A, B]) == [
            ([], [1, 2]), ([1], [2]), ([1, 2], []),
        ]

    def test_control_int_code_vs_bytes(self, mod):
        A, B = Var(), Var()
        assert collect(mod, "ms2", b"axb", A, B, outv=[A, B]) == [(b"a", b"b")]

    def test_control_output_mode_builds_trailing_fixed(self, mod):
        L = Var()
        assert collect(mod, "ms3", L, [7], [], outv=[L]) == [([7, 1, 2],)]

    def test_control_single_star_trailing_fixed(self, mod):
        # single-star trailing fixed takes the $head_list_unify runtime path
        A = Var()
        assert collect(mod, "ssok", "xd", A, outv=[A]) == [("x",)]

    def test_minimal_input(self, mod):
        A, B = Var(), Var()
        assert collect(mod, "ms3", [1, 2], A, B, outv=[A, B]) == [([], [])]

    def test_nonempty_stars_input(self, mod):
        A, B = Var(), Var()
        assert collect(mod, "ms3", [0, 1, 5, 2], A, B, outv=[A, B]) == [([0], [5])]

    def test_two_trailing_fixed(self, mod):
        A, B = Var(), Var()
        assert collect(mod, "mst", [0, 1, 5, 2, 3], A, B, outv=[A, B]) == [([0], [5])]

    def test_str_caller_trailing_fixed(self, mod):
        A, B = Var(), Var()
        assert collect(mod, "mchr", "xayb", A, B, outv=[A, B]) == [("x", "y")]


# ── Regression guards: confirmed-correct behaviour ────────────────────────────


class TestIndexedDispatchGuards:
    def test_bool_and_float_callers_share_int_bucket(self, mod):
        # hash-equal cross-type keys (True/1.0 vs 1) stay consistent with unify
        R = Var()
        assert collect(mod, "kind4", True, R, outv=[R]) == [("one",)]
        R = Var()
        assert collect(mod, "kind4", 1.0, R, outv=[R]) == [("one",)]

    def test_ground_charlist_reaches_str_bucket(self, mod):
        R = Var()
        assert collect(mod, "strs4", ["a", "b", "c"], R, outv=[R]) == [("A",)]

    def test_ground_codelist_reaches_bytes_bucket(self, mod):
        R = Var()
        assert collect(mod, "byt4", [97, 98], R, outv=[R]) == [("AB",)]

    def test_clause_order_preserved_in_bucket(self, mod):
        R = Var()
        assert collect(mod, "ord6", 1, R, outv=[R]) == [
            ("s1",), ("v1",), ("s2",), ("v2",), ("s3",),
        ]

    def test_clause_order_preserved_var_caller(self, mod):
        X, R = Var(), Var()
        assert collect(mod, "ord6", X, R, outv=[R]) == [
            ("s1",), ("v1",), ("s2",), ("other",), ("v2",), ("s3",),
        ]

    def test_str_charlist_heads_coalesce_to_one_bucket(self, mod):
        R = Var()
        assert collect(mod, "coll", "abc", R, outv=[R]) == [("s",), ("l",)]
        R = Var()
        assert collect(mod, "coll", ["a", "b", "c"], R, outv=[R]) == [("s",), ("l",)]

    def test_call_site_specialisation(self, mod):
        R = Var()
        assert collect(mod, "usek", R, outv=[R]) == [("one",)]
        R = Var()
        assert collect(mod, "usekl", R, outv=[R]) == [("ex",)]

    def test_binding_not_leaked_by_failed_bucket_clause(self, mod):
        solve_mod._query_cache.clear()
        R = Var()
        assert list(call("st4", 1, R, module=mod)) == []
        assert is_var(deref(R))

    def test_assertz_reindexes_new_key(self, mod):
        solve_mod._query_cache.clear()
        list(call("addk", module=mod))
        R = Var()
        assert collect(mod, "dynk", 5, R, outv=[R]) == [("five",)]
        R = Var()
        assert collect(mod, "dynk", 1, R, outv=[R]) == [("one",)]
        X, R = Var(), Var()
        assert len(collect(mod, "dynk", X, R, outv=[R])) == 5


class TestJointAndSecondaryDispatchGuards:
    def test_strategies_actually_fired(self, moddict):
        # protects the F001 joint/secondary xfails from silently probing the
        # wrong strategy if thresholds ever change
        assert getattr(moddict["jnt2"], "_index_plans_joint", None)
        assert getattr(moddict["sec2"], "_index_plans_hierarchical", None)

    def test_joint_modes(self, mod):
        R = Var()
        assert collect(mod, "jnt2", "aa", 2, R, outv=[R]) == [(["a2"],)]
        R = Var()
        assert collect(mod, "jnt2", "aa", Var(), R, outv=[R]) == [
            (["a1"],), (["a2"],), (["a3"],), (["a4"],)]
        R = Var()
        assert collect(mod, "jnt2", Var(), 2, R, outv=[R]) == [(["a2"],), (["b2"],)]
        assert len(collect(mod, "jnt2", Var(), Var(), Var())) == 8
        assert collect(mod, "jnt2", "zz", 9, Var()) == []

    def test_secondary_modes(self, mod):
        R = Var()
        assert collect(mod, "sec2", "a", 1, R, outv=[R]) == [(["sa1"],), (["sav"],)]
        R = Var()
        assert collect(mod, "sec2", "a", Var(), R, outv=[R]) == [
            (["sa1"],), (["sa2"],), (["sav"],)]
        assert len(collect(mod, "sec2", Var(), 1, Var())) == 8
        assert collect(mod, "sec2", "zz", 1, Var()) == []

    def test_secondary_partial_at_level1_consistent(self, mod):
        # [X] cannot unify an int column: only the var-at-pos1 clause matches
        X, R = Var(), Var()
        assert collect(mod, "sec2", "a", [X], R, outv=[R]) == [(["sav"],)]


class TestCompoundAtomIndexGuards:
    def test_compound_key_input_and_partial(self, mod, moddict):
        fc = moddict["fc"]
        R = Var()
        assert collect(mod, "cmq4", fc(1), R, outv=[R]) == [(["f1"],)]
        X, R = Var(), Var()
        assert collect(mod, "cmq4", fc(X), R, outv=[X, R]) == [
            (1, ["f1"]), (2, ["f2"]), (3, ["f3"])]

    def test_compound_output_mode(self, mod):
        R = Var()
        assert collect(mod, "cmq4", Var(), R, outv=[R]) == [
            (["f1"],), (["f2"],), (["f3"],), (["g9"],)]

    def test_atom_key_input_and_output(self, mod, moddict):
        R = Var()
        assert collect(mod, "col4", moddict["red"], R, outv=[R]) == [(1,)]
        A, R = Var(), Var()
        sols = collect(mod, "col4", A, R, outv=[A, R])
        assert [(getattr(a, "__name__", a), n) for a, n in sols] == [
            ("red", 1), ("green", 2), ("blue", 3), ("yellow", 4)]

    def test_atom_rule_head_output_mode(self, mod):
        A, R = Var(), Var()
        sols = collect(mod, "colr", A, R, outv=[A, R])
        assert [(getattr(a, "__name__", a), r) for a, r in sols] == [("red", "atomrule")]

    def test_tro_across_buckets(self, mod):
        R = Var()
        assert collect(mod, "cds", 3, R, outv=[R]) == [("zero",)]
        R = Var()
        # bucket 9 holds cds(9,"nine") plus the recursive default clause
        assert collect(mod, "cds", 9, R, outv=[R]) == [("nine",), ("zero",)]


class TestHeadPatternGuards:
    def test_scalar_and_singleton_rule_heads_output_mode(self, mod):
        F = Var()
        assert collect(mod, "fine_int", 50, F, outv=[F]) == [(20000,)]
        F = Var()
        assert collect(mod, "flag_t", 5, F, outv=[F]) == [(True,)]

    def test_negative_literal_heads_both_modes(self, mod):
        R = Var()
        assert collect(mod, "negf", -5, R, outv=[R]) == [("ok",)]
        X, R = Var(), Var()
        assert collect(mod, "negf", X, R, outv=[X, R]) == [(-5, "ok")]
        X, R = Var(), Var()
        assert collect(mod, "negr", X, R, outv=[X, R]) == [(-7, "rok")]

    def test_str_rule_head_honours_strings_as_lists(self, mod):
        R = Var()
        assert collect(mod, "shr", ["a", "b", "c"], R, outv=[R]) == [(1,)]
        X, R = Var(), Var()
        assert collect(mod, "shr", X, R, outv=[X, R]) == [("abc", 1)]

    def test_bytes_rule_head_honours_bytes_as_lists(self, mod):
        R = Var()
        assert collect(mod, "bhr", [97, 98], R, outv=[R]) == [(2,)]
        X, R = Var(), Var()
        assert collect(mod, "bhr", X, R, outv=[X, R]) == [(b"ab", 2)]

    def test_tuple_rule_head_all_modes(self, mod):
        R = Var()
        assert collect(mod, "tup", (1, 2), R, outv=[R]) == [("t",)]
        assert collect(mod, "tup", (9, 9), Var()) == []
        X, R = Var(), Var()
        assert collect(mod, "tup", X, R, outv=[X, R]) == [((1, 2), "t")]

    def test_dict_head_all_modes(self, mod):
        from clausal.terms import DictTerm
        V = Var()
        assert collect(mod, "dh", {"k": 5}, V, outv=[V]) == [(5,)]
        V = Var()
        assert collect(mod, "dh", DictTerm({"k": 7}), V, outv=[V]) == [(7,)]
        D = Var()
        assert collect(mod, "dh", D, 9, outv=[D]) == [(DictTerm({"k": 9}),)]

    def test_set_head_all_modes(self, mod):
        from clausal.terms import SetTerm
        R = Var()
        assert collect(mod, "sth", {1, 2}, R, outv=[R]) == [("set",)]
        assert collect(mod, "sth", {1, 3}, Var()) == []
        S, R = Var(), Var()
        assert collect(mod, "sth", S, R, outv=[S, R]) == [(SetTerm({1, 2}), "set")]

    def test_duplicate_head_vars(self, mod):
        assert len(collect(mod, "same", 1, 1)) == 1
        assert collect(mod, "same", 1, 2) == []
        X = Var()
        assert collect(mod, "same", X, 5, outv=[X]) == [(5,)]
        X = Var()
        assert collect(mod, "dupl", X, [3, 1], outv=[X]) == [(3,)]
        L = Var()
        assert collect(mod, "dupl", 7, L, outv=[L]) == [([7, 1],)]

    def test_duplicate_var_across_two_list_guards(self, mod):
        assert len(collect(mod, "dz", [5, 1], [5, 2])) == 1
        assert collect(mod, "dz", [5, 1], [6, 2]) == []
        L = Var()
        assert collect(mod, "dz", L, [7, 2], outv=[L]) == [([7, 1],)]

    def test_nested_star_list_head(self, mod):
        A, B, C = Var(), Var(), Var()
        assert collect(mod, "nst", [[1, 2, 3], "t"], A, B, C, outv=[A, B, C]) == [
            (1, [2, 3], ["t"])]
        L = Var()
        assert collect(mod, "nst", L, 1, [2], ["t"], outv=[L]) == [([[1, 2], "t"],)]
        assert collect(mod, "nst", [[], "t"], Var(), Var(), Var()) == []
        # inner pattern against a str element
        A, B, C = Var(), Var(), Var()
        assert collect(mod, "nst", ["ab", "t"], A, B, C, outv=[A, B, C]) == [
            ("a", "b", ["t"])]

    def test_multi_star_str_caller_and_output_construction(self, mod):
        A, B = Var(), Var()
        assert collect(mod, "ms", "axb", A, B, outv=[A, B]) == [("a", "b")]
        L = Var()
        assert collect(mod, "ms", L, [1], [2], outv=[L]) == [([1, "x", 2],)]

    def test_output_list_construction_multi_solution(self, mod):
        L = Var()
        assert collect(mod, "outl", L, outv=[L]) == [([1, 11],), ([2, 12],)]


class TestGoalOpShapes:
    def test_or_chain_enumerates_in_order(self, mod):
        X = Var()
        assert collect(mod, "orp", X, outv=[X]) == [(1,), (2,), (3,)]
        assert len(collect(mod, "orp", 2)) == 1

    def test_reified_if_ground_and_unbound(self, mod):
        A = Var()
        assert collect(mod, "iffu", 5, A, outv=[A]) == [("big",)]
        A = Var()
        assert collect(mod, "iffu", 1, A, outv=[A]) == [("small",)]
        A = Var()
        assert collect(mod, "iffu", Var(), A, outv=[A]) == [("big",), ("small",)]

    def test_if_with_list_unify_test(self, mod):
        A = Var()
        assert collect(mod, "iffl", [1], A, outv=[A]) == [("one",)]
        A = Var()
        assert collect(mod, "iffl", [2], A, outv=[A]) == [("other",)]

    def test_false_truncates_true_is_unit(self, mod):
        assert collect(mod, "ftr", Var()) == []
        R = Var()
        assert collect(mod, "ttr", R, outv=[R]) == [(1,)]

    def test_bare_goal_variable_rejected_at_load(self, tmp_path):
        from clausal.logic.compiler.terms_to_goalop import BareGoalVariableError
        p = tmp_path / "a02_badvar.clausal"
        p.write_text(BAD_FIXTURE)
        with pytest.raises(BareGoalVariableError, match=r"bad/1"):
            _load_module("a02_badvar_fixture", str(p))
