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

from clausal.logic.atoms import char_atom, mint
from clausal.logic.cells import chars
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
-double_quotes(atom)
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
iffu(IX, IA) <- if_(IX > 2, IA is "big", IA is "small")
iffl(IL, IA2) <- if_(IL is [1], IA2 is "one", IA2 is "other")
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

# A02-F001 follow-up: TRO trampoline dispatch variants x uncomputable keys.
# Each predicate has a TRO-eligible tail-recursive clause (deterministic
# prefix, self tail call) so the dispatch compiles to the tro_state variant.
# acc4: single-plan (int keys at pos0; other columns non-indexable)
acc4(0, AZA, AZA),
acc4(-1, AZB, ["neg1"]),
acc4(-2, AZC, ["neg2"]),
acc4(ACN, ACA, ACR) <- (ACN > 0, eval_(ACN - 1, ACM), eval_(ACA + 1, ACB), acc4(ACM, ACB, ACR))

# sgl4: single-plan (str keys at pos0; second column non-charlist lists)
sgl4("a", ["aye"]),
sgl4("b", ["bee"]),
sgl4("c", ["cee"]),
sgl4(SGN, SGR) <- (SGN is "go", sgl4("a", SGR))

# mp5: multi-plan (pos0 and pos1 each indexable; joint gain 4 < 4*1.5)
mp5(1, "one"),
mp5(2, "two"),
mp5(3, "three"),
mp5(4, "four"),
mp5(MPN, MPR) <- (MPN > 4, eval_(MPN - 1, MPM), mp5(MPM, MPR))

# str5: multi-plan, str keys at pos0
str5("a", "A"),
str5("b", "B"),
str5("c", "C"),
str5("d", "D"),
str5("go", SGX) <- str5("a", SGX)

# jt3: joint dispatch (8 joint keys > best single 4 * 1.5, coverage 8/9)
jt3("a", 1, ["ja1"]),
jt3("a", 2, ["ja2"]),
jt3("a", 3, ["ja3"]),
jt3("a", 4, ["ja4"]),
jt3("b", 1, ["jb1"]),
jt3("b", 2, ["jb2"]),
jt3("b", 3, ["jb3"]),
jt3("b", 4, ["jb4"]),
jt3("go", JNB, JRC) <- (eval_(JNB - 1, JMD), jt3("a", JMD, JRC))

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
    # P3-1 Task 5 (§1b): the cons rule this class's "charlist"/"empty str vs
    # empty list" controls exercised is RETIRED — a list caller (even a
    # PARTIAL one, containing a Var) no longer reaches a str-literal head
    # at all; the retirement happens before any partial-key indexing
    # question is reached. All four "charlist"/"empty" controls below now
    # return [], not their historical (pre-retirement) solutions.
    def test_control_partial_charlist_no_longer_reaches_str_head(self, mod):
        X, R = Var(), Var()
        assert collect(mod, "strs3", [X, mint("b"), mint("c")], R, outv=[X, R]) == []

    def test_control_empty_list_vs_empty_str_retired(self, mod):
        R = Var()
        assert collect(mod, "emp3", [], R, outv=[R]) == []

    def test_control_partial_codelist_unindexed(self, mod):
        X, R = Var(), Var()
        assert collect(mod, "byt3", [97, X], R, outv=[X, R]) == [(98, mint("AB"))]

    def test_control_seglist_unindexed(self, mod):
        # THE FLIP (2026-09-06-atoms-as-cells-strings): the head literal
        # ``"abc"`` is the ATOM abc in this module (the engine default is
        # ``-double_quotes(atom)``), and an atom is not a list — so a
        # char-list / SegList caller reaches nothing, which is the same
        # answer the P3-1 retirement pins above give for a plain list.
        A, R = Var(), Var()
        sl = SegList([VarSeg(A), ConcreteSeg([char_atom("c")])])
        assert collect(mod, "strs3", sl, R, outv=[A, R]) == []

    def test_control_decimal_unindexed(self, mod):
        R = Var()
        assert collect(mod, "kind3", Decimal(1), R, outv=[R]) == [(mint("one"),)]

    def test_partial_charlist_indexed_no_longer_reaches_str_head(self, mod):
        X, R = Var(), Var()
        assert collect(mod, "strs4", [X, mint("b"), mint("c")], R, outv=[X, R]) == []

    def test_empty_list_vs_empty_str_indexed_retired(self, mod):
        R = Var()
        assert collect(mod, "emp4", [], R, outv=[R]) == []

    def test_partial_codelist_indexed(self, mod):
        X, R = Var(), Var()
        assert collect(mod, "byt4", [97, X], R, outv=[X, R]) == [(98, mint("AB"))]

    def test_seglist_indexed(self, mod):
        # THE FLIP (2026-09-06-atoms-as-cells-strings): the head literal
        # ``"abc"`` is the ATOM abc in this module (the engine default is
        # ``-double_quotes(atom)``), and an atom is not a list — so a
        # char-list / SegList caller reaches nothing, which is the same
        # answer the P3-1 retirement pins above give for a plain list.
        A, R = Var(), Var()
        sl = SegList([VarSeg(A), ConcreteSeg([char_atom("c")])])
        assert collect(mod, "strs4", sl, R, outv=[A, R]) == []

    def test_decimal_indexed(self, mod):
        R = Var()
        assert collect(mod, "kind4", Decimal(1), R, outv=[R]) == [(mint("one"),)]

    def test_joint_partial_container_no_longer_reaches_str_head(self, mod):
        X, R = Var(), Var()
        assert collect(mod, "jnt2", [X, mint("a")], 2, R, outv=[X, R]) == []

    def test_secondary_partial_container_no_longer_reaches_str_heads(self, mod):
        # P3-1 Task 5 (§1b): [X] (a partial 1-element list) no longer
        # unifies with any single-char str-literal first arg ("a".."d") —
        # the cons rule that made this cross-type match possible is
        # retired, so the indexing/partial-key question this test used to
        # probe is moot: nothing reaches these str-literal heads from a
        # list caller at all. (Formerly ``test_secondary_partial_container``,
        # asserting the full 8-solution linear-scan result.)
        X, R = Var(), Var()
        assert collect(mod, "sec2", [X], 1, R, outv=[X, R]) == []


# ── A02-F001 follow-up: the TRO trampoline dispatch variants (joint inline
# body, groundness single-plan loop, groundness multi-plan loop) must apply
# the same uncomputable-key → full-scan guard as the non-TRO bodies. Before
# the fix they routed _INDEX_VAR keys to the default bucket, dropping every
# keyed clause the arg would unify with. ──────────────────────────────────────


class TestF001TrampolineTRODispatchUncomputableKeys:
    def test_fixtures_compile_to_tro_dispatch_variants(self, mod):
        # guard: each fixture must actually hit the TRO (tro_state) variant of
        # the intended dispatch strategy, or the tests below probe nothing.
        # W4b-2d: the dispatch and the row are read through the Database.
        db = mod.db
        for name, arity, n_plans in (("acc4", 3, 1), ("sgl4", 2, 1),
                                     ("mp5", 2, 2), ("str5", 2, 2)):
            fn = db.get_dispatch(name, arity)
            assert "tro_state" in fn.__code__.co_freevars, name
            assert len(db.row(name, arity).index_plans) == n_plans, name
        jfn = db.get_dispatch("jt3", 3)
        assert "tro_state" in jfn.__code__.co_freevars
        assert db.row("jt3", 3).index_plans_joint

    # controls: TRO recursion itself works through each dispatch variant
    def test_control_single_plan_tro_recursion(self, mod):
        R = Var()
        assert collect(mod, "acc4", 3, 0, R, outv=[R]) == [(3,)]
        R = Var()
        assert collect(mod, "sgl4", mint("go"), R, outv=[R]) == [([mint("aye")],)]

    def test_control_multi_plan_tro_recursion(self, mod):
        R = Var()
        assert collect(mod, "str5", mint("go"), R, outv=[R]) == [(mint("A"),)]

    def test_control_joint_tro_recursion(self, mod):
        R = Var()
        assert collect(mod, "jt3", mint("go"), 3, R, outv=[R]) == [([mint("ja2")],)]

    # single-plan TRO loop
    def test_single_plan_decimal_key(self, mod):
        R = Var()
        assert collect(mod, "acc4", Decimal(2), 0, R, outv=[R]) == [(2,)]

    def test_single_plan_partial_charlist_no_longer_reaches_str_heads(self, mod):
        # P3-1 Task 5 (§1b): [X] no longer unifies with any str-literal
        # first arg. (Formerly asserting the full 3-solution linear-scan
        # result under the retired cons rule.)
        X, R = Var(), Var()
        assert collect(mod, "sgl4", [X], R, outv=[X, R]) == []

    # multi-plan TRO loop
    def test_multi_plan_decimal_key(self, mod):
        R = Var()
        assert collect(mod, "mp5", Decimal(2), R, outv=[R]) == [(mint("two"),)]

    def test_multi_plan_partial_charlist_no_longer_reaches_str_heads(self, mod):
        # P3-1 Task 5 (§1b): retired, same rationale as the single-plan case.
        X, R = Var(), Var()
        assert collect(mod, "str5", [X], R, outv=[X, R]) == []

    def test_multi_plan_decimal_tro_restart_from_fallback(self, mod):
        # the fallback is compiled in SIGNAL mode: a tail call fired from its
        # TRO clause must re-dispatch through the outer loop, not be dropped
        R = Var()
        assert collect(mod, "mp5", Decimal(6), R, outv=[R]) == [(mint("four"),)]

    # joint TRO inline body: one component uncomputable → degrade to the
    # single-position dispatch on the other; both → full scan
    def test_joint_partial_charlist_component_no_longer_reaches_str_heads(self, mod):
        # P3-1 Task 5 (§1b): retired, same rationale as above.
        X, R = Var(), Var()
        assert collect(mod, "jt3", [X], 2, R, outv=[X, R]) == []

    def test_joint_decimal_component(self, mod):
        R = Var()
        assert collect(mod, "jt3", mint("a"), Decimal(2), R, outv=[R]) == [([mint("ja2")],)]

    def test_joint_both_components_uncomputable_no_longer_reaches_str_heads(self, mod):
        # P3-1 Task 5 (§1b): retired, same rationale as above (the Decimal
        # second component being uncomputable is orthogonal — the str
        # component's cross-type reach is what this test now pins as gone).
        X, R = Var(), Var()
        assert collect(mod, "jt3", [X], Decimal(2), R, outv=[X, R]) == []

    def test_joint_decimal_tro_restart_through_single_dispatch(self, mod):
        # Decimal at the (more selective) int column degrades to the str
        # single dispatch, whose "go" bucket signals a TRO tail call that
        # must re-dispatch into the "a" bucket
        R = Var()
        assert collect(mod, "jt3", mint("go"), Decimal(3), R, outv=[R]) == [([mint("ja2")],)]


# ── A02-F002: list-structure dispatch drops non-list/str/Var callers ─────────


class TestF002ListDispatchFallthrough:
    # controls: list / str / var callers route correctly
    def test_control_nil(self, mod):
        R = Var()
        assert collect(mod, "ld2", [], R, outv=[R]) == [(mint("nil2"),), (mint("any2"),)]

    def test_control_cons(self, mod):
        R = Var()
        assert collect(mod, "ld2", [9], R, outv=[R]) == [(mint("cons2"),), (mint("any2"),)]

    def test_control_str(self, mod):
        # A STRING caller: "ab" is the list of its char atoms, so it takes
        # the ``[LH, *LT]`` cons clause exactly as ``[9]`` does.
        R = Var()
        assert collect(mod, "ld2", chars("ab"), R, outv=[R]) == [
            (mint("cons2"),), (mint("any2"),)]

    def test_control_var_enumerates_all(self, mod):
        X, R = Var(), Var()
        assert collect(mod, "ld2", X, R, outv=[R]) == [(mint("nil2"),), (mint("cons2"),), (mint("any2"),)]

    def test_int_caller_matches_var_clause(self, mod):
        R = Var()
        assert collect(mod, "ld2", 5, R, outv=[R]) == [(mint("any2"),)]

    def test_tuple_caller_matches_var_clause(self, mod):
        R = Var()
        assert collect(mod, "ld2", (1, 2), R, outv=[R]) == [(mint("any2"),)]

    def test_bytes_caller(self, mod):
        R = Var()
        assert collect(mod, "ld2", b"ab", R, outv=[R]) == [(mint("cons2"),), (mint("any2"),)]

    @pytest.mark.xfail(strict=False, reason="A02-F002: non-ground SegList vs cons head needs SegList-vs-partial-pattern unify, blocked on F030 (Phase 6). The else-arm fix routes it to the var clause (any2); cons2 requires destructuring [1,*A] against [LH,*LT], which _head_list_unify_input returns False for by design.")
    def test_seglist_caller(self, mod):
        A, R = Var(), Var()
        sl = SegList([ConcreteSeg([1]), VarSeg(A)])
        assert collect(mod, "ld2", sl, R, outv=[R]) == [(mint("cons2"),), (mint("any2"),)]


# ── A02-F003: unguarded accept-all wildcard for unhandled head-literal types
# (reachable via runtime assertz — no fact normalization on that path) ────────


class TestF003ExoticHeadWildcard:
    def _assert_fact(self, mod, name, *args):
        # W4b-2d: the fact is a plain cell, not a class instance.
        solve_mod._query_cache.clear()
        list(call("assertz", (name, *args), module=mod))

    def test_control_date_true_positive(self, mod, moddict):
        self._assert_fact(mod, "dyn_date", datetime.date(2026, 1, 1), 1)
        R = Var()
        assert (1,) in collect(mod, "dyn_date", datetime.date(2026, 1, 1), R, outv=[R])

    def test_date_mismatch_must_fail(self, mod, moddict):
        self._assert_fact(mod, "dyn_date", datetime.date(2026, 1, 1), 1)
        R = Var()
        assert collect(mod, "dyn_date", datetime.date(1999, 9, 9), R, outv=[R]) == []

    def test_date_output_mode_binds(self, mod, moddict):
        self._assert_fact(mod, "dyn_date", datetime.date(2026, 1, 1), 1)
        X, R = Var(), Var()
        sols = collect(mod, "dyn_date", X, R, outv=[X, R])
        assert (datetime.date(2026, 1, 1), 1) in sols

    def test_tuple_mismatch_must_fail(self, mod, moddict):
        self._assert_fact(mod, "dyn_tuple", (1, 2), 100)
        R = Var()
        assert collect(mod, "dyn_tuple", (9, 9), R, outv=[R]) == []

    def test_set_mismatch_must_fail(self, mod, moddict):
        self._assert_fact(mod, "dyn_set", {3, 4}, 200)
        R = Var()
        assert collect(mod, "dyn_set", {5, 6}, R, outv=[R]) == []

    def test_decimal_mismatch_must_fail(self, mod, moddict):
        self._assert_fact(mod, "dyn_dec", Decimal("2.5"), 9)
        R = Var()
        assert collect(mod, "dyn_dec", Decimal("7.7"), R, outv=[R]) == []


# ── A02-F004: multi-star guard, trailing fixed after the last star ───────────


class TestF004MultiStarTrailingFixed:
    # controls: no trailing fixed after the last star — all fine
    def test_control_fixed_between_stars(self, mod):
        A, B = Var(), Var()
        assert collect(mod, "ms", [1, mint("x"), 2], A, B, outv=[A, B]) == [([1], [2])]

    def test_control_enumerates_splits(self, mod):
        A, B = Var(), Var()
        assert collect(mod, "ms", [mint("x"), mint("x")], A, B, outv=[A, B]) == [([], [mint("x")]), ([mint("x")], [])]

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
        # A STRING caller destructures into char atoms; the head's trailing
        # ``"d"`` is the ATOM d, which is what the last char atom is.  The
        # star binds the remaining char list, promoted back to a string.
        assert collect(mod, "ssok", chars("xd"), A, outv=[A]) == [(chars("x"),)]

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
        assert collect(mod, "mchr", chars("xayb"), A, B, outv=[A, B]) == [(chars("x"), chars("y"))]


# ── Regression guards: confirmed-correct behaviour ────────────────────────────


class TestIndexedDispatchGuards:
    def test_bool_and_float_callers_share_int_bucket(self, mod):
        # hash-equal cross-type keys (True/1.0 vs 1) stay consistent with unify
        R = Var()
        assert collect(mod, "kind4", True, R, outv=[R]) == [(mint("one"),)]
        R = Var()
        assert collect(mod, "kind4", 1.0, R, outv=[R]) == [(mint("one"),)]

    def test_ground_charlist_no_longer_reaches_str_bucket(self, mod):
        # P3-1 Task 5 (§1b): a GROUND char-list caller no longer reaches
        # a str-literal head either (formerly asserting [("A",)]).
        R = Var()
        assert collect(mod, "strs4", [mint("a"), mint("b"), mint("c")], R, outv=[R]) == []

    def test_ground_codelist_reaches_bytes_bucket(self, mod):
        R = Var()
        assert collect(mod, "byt4", [97, 98], R, outv=[R]) == [(mint("AB"),)]

    def test_clause_order_preserved_in_bucket(self, mod):
        R = Var()
        assert collect(mod, "ord6", 1, R, outv=[R]) == [
            (mint("s1"),), (mint("v1"),), (mint("s2"),), (mint("v2"),), (mint("s3"),),
        ]

    def test_clause_order_preserved_var_caller(self, mod):
        X, R = Var(), Var()
        assert collect(mod, "ord6", X, R, outv=[R]) == [
            (mint("s1"),), (mint("v1"),), (mint("s2"),), (mint("other"),), (mint("v2"),), (mint("s3"),),
        ]

    def test_str_charlist_heads_no_longer_coalesce_for_list_caller(self, mod):
        """P3-1 Task 5 / P3-2 Task 4 (§1b, R8): ``coll`` has BOTH a
        str-literal fact (``coll("abc", "s")``) and a list-literal fact
        (``coll(["a","b","c"], "l")``).

        Fully symmetric now: each caller reaches only its own-type fact.

        Until P3-2 Task 4 the str caller ALSO reached the list-literal
        fact -- a residual asymmetry that survived P3-1 Task 5's retirement
        of the ``_variables.c`` do_unify cons rule (a direct
        ``unify("abc", [...], trail)`` was already confirmed False).  Traced
        (not guessed) to a level deeper: the arg-index default-clause merge
        put the list-literal fact into the str fact's own bucket (its key is
        ``_INDEX_VAR`` -- unindexable), and ``_lift_clause_at_pos`` then
        lifted it into a head sequence PATTERN, whose runtime destructuring
        helper (``_head_list_unify_input_py`` / its C twin) still implements
        the pre-P3-1 "a string is a list of its chars" contract for
        HEAD-PATTERN matching -- untouched by the do_unify retirement.
        ``_lift_clause_at_pos`` (list_dispatch.py) now also skips lifting a
        ground list literal, closing this. See
        ``todo/done/first-arg-indexing-str-caller-still-reaches-list-fact-2026-09-04.md``.

        (Formerly ``test_str_charlist_heads_coalesce_to_one_bucket``,
        asserting BOTH callers reached both facts.)
        """
        R = Var()
        assert collect(mod, "coll", mint("abc"), R, outv=[R]) == [(mint("s"),)]
        R = Var()
        assert collect(mod, "coll", [mint("a"), mint("b"), mint("c")], R, outv=[R]) == [(mint("l"),)]

    def test_call_site_specialisation(self, mod):
        R = Var()
        assert collect(mod, "usek", R, outv=[R]) == [(mint("one"),)]
        # P3-1 Task 5 (§1b): usekl's body calls kind4(["x"], UR2) -- a
        # 1-element list caller against kind4's str-literal head "x".
        # Retired: no longer matches (formerly [("ex",)]).
        R = Var()
        assert collect(mod, "usekl", R, outv=[R]) == []

    def test_binding_not_leaked_by_failed_bucket_clause(self, mod):
        solve_mod._query_cache.clear()
        R = Var()
        assert list(call("st4", 1, R, module=mod)) == []
        assert is_var(deref(R))

    def test_assertz_reindexes_new_key(self, mod):
        solve_mod._query_cache.clear()
        list(call("addk", module=mod))
        R = Var()
        assert collect(mod, "dynk", 5, R, outv=[R]) == [(mint("five"),)]
        R = Var()
        assert collect(mod, "dynk", 1, R, outv=[R]) == [(mint("one"),)]
        X, R = Var(), Var()
        assert len(collect(mod, "dynk", X, R, outv=[R])) == 5


class TestJointAndSecondaryDispatchGuards:
    def test_strategies_actually_fired(self, mod):
        # protects the F001 joint/secondary xfails from silently probing the
        # wrong strategy if thresholds ever change
        assert mod.db.row("jnt2", 3).index_plans_joint
        assert mod.db.row("sec2", 3).index_plans_hierarchical

    def test_joint_modes(self, mod):
        R = Var()
        assert collect(mod, "jnt2", mint("aa"), 2, R, outv=[R]) == [([mint("a2")],)]
        R = Var()
        assert collect(mod, "jnt2", mint("aa"), Var(), R, outv=[R]) == [
            ([mint("a1")],), ([mint("a2")],), ([mint("a3")],), ([mint("a4")],)]
        R = Var()
        assert collect(mod, "jnt2", Var(), 2, R, outv=[R]) == [([mint("a2")],), ([mint("b2")],)]
        assert len(collect(mod, "jnt2", Var(), Var(), Var())) == 8
        assert collect(mod, "jnt2", mint("zz"), 9, Var()) == []

    def test_secondary_modes(self, mod):
        R = Var()
        assert collect(mod, "sec2", mint("a"), 1, R, outv=[R]) == [([mint("sa1")],), ([mint("sav")],)]
        R = Var()
        assert collect(mod, "sec2", mint("a"), Var(), R, outv=[R]) == [
            ([mint("sa1")],), ([mint("sa2")],), ([mint("sav")],)]
        assert len(collect(mod, "sec2", Var(), 1, Var())) == 8
        assert collect(mod, "sec2", mint("zz"), 1, Var()) == []

    def test_secondary_partial_at_level1_consistent(self, mod):
        # [X] cannot unify an int column: only the var-at-pos1 clause matches
        X, R = Var(), Var()
        assert collect(mod, "sec2", mint("a"), [X], R, outv=[R]) == [([mint("sav")],)]


class TestCompoundAtomIndexGuards:
    def test_compound_key_input_and_partial(self, mod, moddict):
        # P3-2 Task 2 (THE FLIP, R6): ``fc`` is a data functor -- its name
        # binds the interned spelling, and the term is the cell.
        assert moddict["fc"] == mint("fc")
        fc = lambda *args: ("fc", *args)
        R = Var()
        assert collect(mod, "cmq4", fc(1), R, outv=[R]) == [([mint("f1")],)]
        X, R = Var(), Var()
        assert collect(mod, "cmq4", fc(X), R, outv=[X, R]) == [
            (1, [mint("f1")]), (2, [mint("f2")]), (3, [mint("f3")])]

    def test_compound_output_mode(self, mod):
        R = Var()
        assert collect(mod, "cmq4", Var(), R, outv=[R]) == [
            ([mint("f1")],), ([mint("f2")],), ([mint("f3")],), ([mint("g9")],)]

    def test_atom_key_input_and_output(self, mod, moddict):
        R = Var()
        assert collect(mod, "col4", moddict["red"], R, outv=[R]) == [(1,)]
        A, R = Var(), Var()
        sols = collect(mod, "col4", A, R, outv=[A, R])
        assert sols == [(mint("red"), 1), (mint("green"), 2),
                        (mint("blue"), 3), (mint("yellow"), 4)]

    def test_atom_rule_head_output_mode(self, mod):
        A, R = Var(), Var()
        sols = collect(mod, "colr", A, R, outv=[A, R])
        assert sols == [(mint("red"), mint("atomrule"))]

    def test_tro_across_buckets(self, mod):
        R = Var()
        assert collect(mod, "cds", 3, R, outv=[R]) == [(mint("zero"),)]
        R = Var()
        # bucket 9 holds cds(9,"nine") plus the recursive default clause
        assert collect(mod, "cds", 9, R, outv=[R]) == [(mint("nine"),), (mint("zero"),)]


class TestHeadPatternGuards:
    def test_scalar_and_singleton_rule_heads_output_mode(self, mod):
        F = Var()
        assert collect(mod, "fine_int", 50, F, outv=[F]) == [(20000,)]
        F = Var()
        assert collect(mod, "flag_t", 5, F, outv=[F]) == [(True,)]

    def test_negative_literal_heads_both_modes(self, mod):
        R = Var()
        assert collect(mod, "negf", -5, R, outv=[R]) == [(mint("ok"),)]
        X, R = Var(), Var()
        assert collect(mod, "negf", X, R, outv=[X, R]) == [(-5, mint("ok"))]
        X, R = Var(), Var()
        assert collect(mod, "negr", X, R, outv=[X, R]) == [(-7, mint("rok"))]

    def test_str_rule_head_no_longer_honours_strings_as_lists(self, mod):
        """P3-1 Task 5 (§1b): ``shr("abc", SR) <- (SR is 1)`` is a RULE
        with a str-literal head. A list caller no longer matches
        (formerly [(1,)] under the retired cons rule); output-mode
        construction (an unbound caller binding to "abc") is unaffected
        — that's same-type reconstruction, not cross-type unification.
        """
        R = Var()
        assert collect(mod, "shr", [mint("a"), mint("b"), mint("c")], R, outv=[R]) == []
        X, R = Var(), Var()
        assert collect(mod, "shr", X, R, outv=[X, R]) == [(mint("abc"), 1)]

    def test_bytes_rule_head_honours_bytes_as_lists(self, mod):
        R = Var()
        assert collect(mod, "bhr", [97, 98], R, outv=[R]) == [(2,)]
        X, R = Var(), Var()
        assert collect(mod, "bhr", X, R, outv=[X, R]) == [(b"ab", 2)]

    def test_tuple_rule_head_all_modes(self, mod):
        R = Var()
        assert collect(mod, "tup", (1, 2), R, outv=[R]) == [(mint("t"),)]
        assert collect(mod, "tup", (9, 9), Var()) == []
        X, R = Var(), Var()
        assert collect(mod, "tup", X, R, outv=[X, R]) == [((1, 2), mint("t"))]

    def test_dict_head_all_modes(self, mod):
        from clausal.terms import DictTerm
        V = Var()
        assert collect(mod, "dh", {mint("k"): 5}, V, outv=[V]) == [(5,)]
        V = Var()
        assert collect(mod, "dh", DictTerm({mint("k"): 7}), V,
                       outv=[V]) == [(7,)]
        D = Var()
        assert collect(mod, "dh", D, 9,
                       outv=[D]) == [(DictTerm({mint("k"): 9}),)]

    def test_set_head_all_modes(self, mod):
        from clausal.terms import SetTerm
        R = Var()
        assert collect(mod, "sth", {1, 2}, R, outv=[R]) == [(mint("set"),)]
        assert collect(mod, "sth", {1, 3}, Var()) == []
        S, R = Var(), Var()
        assert collect(mod, "sth", S, R, outv=[S, R]) == [(SetTerm({1, 2}), mint("set"))]

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
        assert collect(mod, "nst", [[1, 2, 3], mint("t")], A, B, C, outv=[A, B, C]) == [
            (1, [2, 3], [mint("t")])]
        L = Var()
        assert collect(mod, "nst", L, 1, [2], [mint("t")], outv=[L]) == [([[1, 2], mint("t")],)]
        assert collect(mod, "nst", [[], mint("t")], Var(), Var(), Var()) == []
        # inner pattern against a str element
        A, B, C = Var(), Var(), Var()
        assert collect(mod, "nst", [chars("ab"), mint("t")], A, B, C,
                       outv=[A, B, C]) == [
            (char_atom("a"), chars("b"), [mint("t")])]

    def test_multi_star_str_caller_and_output_construction(self, mod):
        A, B = Var(), Var()
        assert collect(mod, "ms", chars("axb"), A, B, outv=[A, B]) == [(chars("a"), chars("b"))]
        L = Var()
        assert collect(mod, "ms", L, [1], [2], outv=[L]) == [([1, mint("x"), 2],)]

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
        assert collect(mod, "iffu", 5, A, outv=[A]) == [(mint("big"),)]
        A = Var()
        assert collect(mod, "iffu", 1, A, outv=[A]) == [(mint("small"),)]
        A = Var()
        assert collect(mod, "iffu", Var(), A, outv=[A]) == [(mint("big"),), (mint("small"),)]

    def test_if_with_list_unify_test(self, mod):
        A = Var()
        assert collect(mod, "iffl", [1], A, outv=[A]) == [(mint("one"),)]
        A = Var()
        assert collect(mod, "iffl", [2], A, outv=[A]) == [(mint("other"),)]

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
