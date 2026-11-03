"""Stage-4 descent diagnostics + rung-2 examples for ``python -m clausal.testing``.

Rung 3 ("no solution for ANY arguments") used to carry no value — measured
0/29 recovery in a measured authoring study.  See
``docs/superpowers/specs/2026-07-30-assertion-diagnostic-descent-design.md``.
"""

from __future__ import annotations

import textwrap

from clausal.testing import main
from tests._suffix import SEAM


def write(tmp_path, name, src):
    p = tmp_path / name
    p.write_text(textwrap.dedent(src).lstrip())
    return p


# ── rung 2: satisfiable, but 2+ arguments differ ─────────────────────────────

PAIR_SRC = """
-double_quotes(atom)
pairx("a", 1),
pairx("b", 2),

test("both arguments differ") <- (
    pairx("c", 3)
),
"""


def test_two_plus_args_differ_shows_example_solutions(capsys, tmp_path):
    p = write(tmp_path, f"pair{SEAM}", PAIR_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "two or more arguments differ" in out   # old sentence survives
    assert "it does have:" in out                  # new suffix
    assert "pairx(a, 1)" in out                  # an actual solution, rendered


# ── rung 3: descent into the failing predicate ───────────────────────────────

GUARD_SRC = """
-double_quotes(atom)
chk_range(PCT) <- (
    PCT >= 0,
    PCT > 100,
    PCT <= 100
),

test("contradictory guards") <- (
    chk_range(50)
),
"""


def test_contradictory_guard_named_with_value(capsys, tmp_path):
    p = write(tmp_path, f"guard{SEAM}", GUARD_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "no clause body survives" in out
    assert "PCT > 100" in out       # the failing conjunct, source-faithful
    assert "PCT = 50" in out        # ...with the head binding that dooms it


# Each route's constraints must be UNSATISFIABLE even with the argument free,
# or the whole-argument-hole probe (rung 2) finds a degenerate solution and
# descent never runs: the clausal constraint solver leaves a lone one-sided
# bound (`X < 0`) satisfiable with X unbound, so a contradictory pair
# (`X < 0, X > 100`) is what forces rung 3.  X = 5 still makes each clause fail
# at the asserted conjunct.
TWO_ROUTES_SRC = """
-double_quotes(atom)
-private([small, big])

classify(X, small) <- (X < 10, X < 0, X > 100),
classify(X, big) <- (X > 10, X < 0),

test("two routes both fail") <- (
    classify(5, _KIND)
),
"""


def test_each_clause_route_gets_a_leaf(capsys, tmp_path):
    p = write(tmp_path, f"routes{SEAM}", TWO_ROUTES_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "X < 0" in out    # clause 1's first failing conjunct (5 < 10 passed)
    assert "X > 10" in out   # clause 2's
    assert "X = 5" in out


DYN_SRC = """
-double_quotes(atom)
-dynamic(dynp/1)

test("zero-clause predicate") <- (
    dynp(1)
),
"""


def test_zero_clause_predicate_keeps_old_message(capsys, tmp_path):
    p = write(tmp_path, f"dyn{SEAM}", DYN_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "no solution for ANY arguments" in out
    assert "no clause body survives" not in out


# ── recursion ────────────────────────────────────────────────────────────────

# inner_rule's body must be UNSATISFIABLE with N free, or the outer predicate
# is satisfiable and _report_nearest stops at rung 1 ("argument 1 differs")
# before descent ever runs (see the constraint-solver note on TWO_ROUTES_SRC).
# The contradictory pair `N > 100, N < 0` forces descent; N = 5 still fails at
# the first conjunct, `N > 100`.
NESTED_SRC = """
-double_quotes(atom)
inner_rule(N) <- (N > 100, N < 0),
outer_rule(N) <- (inner_rule(N)),

test("nested failure") <- (
    outer_rule(5)
),
"""


def test_descends_through_intermediate_predicate(capsys, tmp_path):
    p = write(tmp_path, f"nested{SEAM}", NESTED_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "N > 100" in out   # the inner predicate's conjunct, not inner_rule(N)
    assert "N = 5" in out


def test_cross_module_descent(capsys, tmp_path, monkeypatch):
    import sys as _sys
    monkeypatch.syspath_prepend(str(tmp_path))
    _sys.modules.pop("descent_lib", None)
    write(tmp_path, f"descent_lib{SEAM}", """
        -module(descent_lib, [lib_check(N)])

        lib_check(N) <- (N > 100, N < 0)
    """)
    p = write(tmp_path, f"use{SEAM}", """
        -double_quotes(atom)
        -import_from(descent_lib, [lib_check])

        test("cross-module") <- (
            lib_check(5)
        ),
    """)
    try:
        assert main([str(p)]) == 1
        out = capsys.readouterr().out
        assert "no clause body survives" in out
        assert "N > 100" in out
        assert "N = 5" in out
        assert f"descent_lib{SEAM}:" in out   # leaf names the DEFINING file
    finally:
        _sys.modules.pop("descent_lib", None)


# Same unsatisfiability requirement as NESTED_SRC (contradictory `N > 100,
# N < 0`), so the chain lvl1->lvl2->lvl3 reaches descent instead of rung 1.
# Descent caps at depth 2: lvl1's leaf lvl2(N) recurses to lvl2, whose leaf
# lvl3(N) is a Call at depth 2 and is rendered as-is — lvl3's body is never
# entered, so `N > 100` never surfaces.
DEEP_SRC = """
-double_quotes(atom)
lvl3(N) <- (N > 100, N < 0),
lvl2(N) <- (lvl3(N)),
lvl1(N) <- (lvl2(N)),

test("three levels") <- (
    lvl1(5)
),
"""


def test_depth_cap_stops_at_two_levels(capsys, tmp_path):
    p = write(tmp_path, f"deep{SEAM}", DEEP_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "lvl3(" in out          # depth-2 leaf is the lvl3 CALL...
    assert "N > 100" not in out    # ...not lvl3's body — depth cap held


# ── no clause head matches ───────────────────────────────────────────────────

# The head listing fires only once descent runs, and descent runs only after the
# all-holes probe (rung 2) proves the predicate unsatisfiable with every argument
# free.  The brief's cons fixtures assumed the base case `wk_totals([], 0)` would
# leave the probe unsatisfiable — but on the live engine a hole (a Var) unifies
# with `[]`, so the base case satisfies the all-holes probe and rung 2 intercepts
# before descent (verified against the engine during this task).  Worse, a
# genuinely recursive body over the `[H|T]`-as-BitOr head recurses forever when
# the first argument is a hole, hanging the probe.  Minimal adaptation, keeping
# every stated assertion: each clause keeps its exact head source (`[]` and the
# BitOr `[MINS, STATUS] | REST`, both rendered source-faithfully) but is given a
# body that FAILS with holes and does not recurse — so the all-holes probe fails
# cleanly, descent runs, and every clause head still mismatches the concrete
# non-empty-list goal, yielding the head listing.
CONS_SRC = """
-double_quotes(atom)
-private([work])

wk_totals([], 0) <- (1 > 2),
wk_totals([MINS, STATUS] | REST, TOTAL) <- (
    TOTAL == MINS,
    1 > 2
),

test("cons head never matches") <- (
    wk_totals([[2880, work]], 2880)
),
"""


def test_all_heads_fail_lists_the_heads(capsys, tmp_path):
    p = write(tmp_path, f"cons{SEAM}", CONS_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "no clause head unifies" in out
    assert "| REST" in out               # the BitOr head, source-faithful
    assert "wk_totals([], 0)" in out     # the base case is listed too


# Same adaptation as CONS_SRC (see the note above): the base case + recursive
# BitOr body would otherwise leave the OUTER `wkn_check` all-holes probe
# satisfiable (or hang it), so rung 3 would never descend into `wkn_totals`.  The
# non-recursive failing bodies make the outer probe fail cleanly; descent then
# reaches the `wkn_totals(WEEKS, _TOTAL)` leaf, where every clause head mismatches
# the concrete WEEKS and the head listing attaches beneath the leaf.
CONS_NESTED_SRC = """
-double_quotes(atom)
-private([work])

wkn_totals([], 0) <- (1 > 2),
wkn_totals([MINS, STATUS] | REST, TOTAL) <- (
    TOTAL == MINS,
    1 > 2
),

wkn_check(WEEKS) <- (
    wkn_totals(WEEKS, _TOTAL)
),

test("nested cons head") <- (
    wkn_check([[2880, work]])
),
"""


def test_head_listing_attaches_beneath_parent_leaf(capsys, tmp_path):
    p = write(tmp_path, f"consn{SEAM}", CONS_NESTED_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "wkn_totals(WEEKS, _TOTAL)" in out   # the parent leaf conjunct
    assert "no clause head unifies" in out
    assert "| REST" in out
    assert "WEEKS = [[2880, work]]" in out


# ── caps are noted, never silent ─────────────────────────────────────────────

# Same unsatisfiability requirement as the other rung-3 fixtures (see the
# constraint-solver note on TWO_ROUTES_SRC): a lone one-sided bound `N > 100`
# is deferred by the solver and stays satisfiable with N free, so the all-holes
# probe (rung 2) intercepts before descent runs.  Each clause body is given the
# contradictory pair `(N > 100, N < 0)` to force rung 3; at N = 5, `N > 100` is
# still the FIRST failing conjunct of every clause, so it is the leaf rendered
# for each of the 4 walked clauses -> `out.count("N > 100") == 4` holds (the
# other two clauses are truncated by the cap and never walked).
SIX_SRC = """
-double_quotes(atom)
-private([r1, r2, r3, r4, r5, r6])

sixway(N, r1) <- (N > 100, N < 0),
sixway(N, r2) <- (N > 100, N < 0),
sixway(N, r3) <- (N > 100, N < 0),
sixway(N, r4) <- (N > 100, N < 0),
sixway(N, r5) <- (N > 100, N < 0),
sixway(N, r6) <- (N > 100, N < 0),

test("six clauses") <- (
    sixway(5, _R)
),
"""


def test_clause_cap_is_applied_and_noted(capsys, tmp_path):
    p = write(tmp_path, f"six{SEAM}", SIX_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert out.count("N > 100") == 4          # DIAG_MAX_DESCENT_CLAUSES leaves
    # The truncation is stated; all six heads unify, so no "in all" count.
    assert ("descent walked only the first 4 of 6 clauses of sixway whose "
            "heads unify with these arguments\n") in out


# DIAG_MAX_DESCENT_LEAVES bounds how many findings, across the whole descent
# INCLUDING fan-out, are printed IN FULL; every further one is still listed by
# its first line: one clause route that recurses into a deeper
# predicate can produce several findings (design §Flat leaves: "one clause
# route can fan out into several leaves — the flat list is leaves, not
# routes").  Here 4 outer clauses each recurse into ``inner`` (2 failing
# routes), so descent produces 4 x 2 = 8 findings — over the bound of 6.  Neither
# the outer (4 clauses) nor the inner (2 clauses) predicate trips the
# per-predicate clause cap (DIAG_MAX_DESCENT_CLAUSES=4), so this exercises the
# leaves cap in isolation.  Same unsatisfiability requirement as the other
# rung-3 fixtures (contradictory pairs, see the note on TWO_ROUTES_SRC): each
# inner route pairs a one-sided lower bound with ``N < 0`` so the all-holes
# probe fails and rung 3 descends; at N = 5, ``N > 100`` / ``N > 200`` is the
# FIRST failing conjunct of its route, so it is the leaf rendered.  Verified
# against the live engine: 8 findings, capped to 6 (3x each conjunct).
FANOUT_SRC = """
-double_quotes(atom)
-private([a, b, c, d])

inner(N) <- (N > 100, N < 0),
inner(N) <- (N > 200, N < 0),

fanout(N, a) <- (inner(N)),
fanout(N, b) <- (inner(N)),
fanout(N, c) <- (inner(N)),
fanout(N, d) <- (inner(N)),

test("fan out") <- (
    fanout(5, _R)
),
"""


def test_every_finding_is_listed_past_the_detail_bound(capsys, tmp_path):
    p = write(tmp_path, f"fanout{SEAM}", FANOUT_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    # 8 findings fan out; all 8 are listed (none is dropped) ...
    findings = out.count("N > 100") + out.count("N > 200")
    assert findings == 8
    # ... the first DIAG_MAX_DESCENT_LEAVES=6 with their bindings, the rest by
    # their first line, and the report says which.
    assert out.count("N = 5") == 1                       # printed in full once
    assert out.count("N = (same as above)") == 5         # findings 2..6
    assert "note: 2 more findings, shown by their first line only" in out
    # Each finding names the clauses it came through, so the four outer
    # routes into the same inner clause stay apart.
    for line in (7, 8, 9, 10):         # fanout clauses; inner is at 4 and 5
        assert f"(via fanout{SEAM}:{line} → 4)" in out
        assert f"(via fanout{SEAM}:{line} → 5)" in out


# A head listing over more than DIAG_MAX_DESCENT_CLAUSES (=4) clauses: every
# head WAS checked (the cap bounds only the body walk), so the headline is the
# exact claim and all six heads are listed.  (It used to say "no clause head
# among the first 4 unifies" and list four: only 4 heads were checked.)
# Same rung-3 requirement as the other head-listing fixtures: each head
# carries a DISTINCT atom literal so no head unifies with the concrete goal
# atom ``zzz``, and each body is a non-recursive ``1 > 2`` so the all-holes
# probe fails cleanly (rung 2 does not intercept) and descent runs.
SIX_HEADS_SRC = """
-double_quotes(atom)
-private([a, b, c, d, e, f, zzz])

sixhead(a, N) <- (1 > 2),
sixhead(b, N) <- (1 > 2),
sixhead(c, N) <- (1 > 2),
sixhead(d, N) <- (1 > 2),
sixhead(e, N) <- (1 > 2),
sixhead(f, N) <- (1 > 2),

test("six clause heads all mismatch") <- (
    sixhead(zzz, 5)
),
"""


def test_capped_head_listing_states_every_head_was_checked(capsys, tmp_path):
    p = write(tmp_path, f"sixhead{SEAM}", SIX_HEADS_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert ("no clause head unifies with these arguments "
            "— the heads are:") in out
    # Nothing was left unchecked, so there is no cap note and no bound claim.
    assert "descent walked" not in out
    assert "among the first" not in out
    # Every head is listed.
    for atom in "abcdef":
        assert f"sixhead({atom}, N)" in out
    assert "more head" not in out


# ── degenerate rung-1/2 solutions descend (todo D) ───────────────────────────

# A rung-1 near-miss that leaves the freed argument NON-GROUND (unbound holes
# in it) carries no value: it shows a clause-head pattern, not a counter-value.
# A measured authoring study's shape — a `[H|T]`-as-BitOr head plus a
# base-case fact — was intercepted at rung 1 with exactly such a near-miss
# (`BitOr(None, [2880, _], [])`), and the head listing that names the real bug
# never fired.  See
# `todo/done/D-rung2-unbound-arg-solutions-weaken-diagnosis.md`.
CONS_PINNED_SRC = """
-double_quotes(atom)
-private([work])

wtq_totals([], 0, 0),
wtq_totals([WORKED_MINUTES, STATUS] | REST_WEEKS, TOTAL, N) <- (
    wtq_totals(REST_WEEKS, T0, N0),
    TOTAL == T0 + WORKED_MINUTES,
    N == N0 + 1
),

test("totals over one week, pinned") <- (
    wtq_totals([[2880, work]], 2880, 1)
),
"""


def test_unbound_near_miss_descends_to_head_listing(capsys, tmp_path):
    p = write(tmp_path, f"wtq{SEAM}", CONS_PINNED_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "none binds argument 1 to a concrete value" in out
    assert "no clause head unifies" in out
    assert "| REST_WEEKS" in out          # the money line: the BitOr head
    assert "BitOr(" not in out            # the unbound near-miss is dropped
    assert "DID have a solution" not in out


# A lone one-sided bound (`X < 0`) is deferred by the constraint solver and
# stays satisfiable with X unbound, so the rung-1 probe finds a solution whose
# freed argument is a bare hole (`classify(_, _K)`), and descent never used to
# run — the fixtures above had to force rung 3 with contradictory pairs.  The
# degenerate near-miss now descends instead and names the failing conjunct
# with its concrete binding.
LONE_BOUND_SRC = """
-double_quotes(atom)
classify(X, "small") <- (X < 10, X < 0),
classify(X, "big") <- (X > 10, X < 0),

test("lone one-sided bounds") <- (
    classify(5, _KIND)
),
"""


def test_unbound_near_miss_descends_to_clause_leaves(capsys, tmp_path):
    p = write(tmp_path, f"lone{SEAM}", LONE_BOUND_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "none binds argument 1 to a concrete value" in out
    assert "no clause body survives" in out
    assert "X < 0" in out     # clause 1's first failing conjunct (5 < 10 passed)
    assert "X > 10" in out    # clause 2's
    assert "X = 5" in out
    assert "DID have a solution" not in out


# A GROUND near-miss genuinely carries a value and must stay at rung 1 — even
# when it is only a trivial base-case match.  Deliberate design boundary
# (todo D): any cheap "trivial match" discriminator regresses fact-table
# predicates, where a ground near-miss is exactly the right diagnosis.
CONS_OUTPUT_SRC = """
-double_quotes(atom)
-private([work])

wto_totals([], 0, 0),
wto_totals([WORKED_MINUTES, STATUS] | REST_WEEKS, TOTAL, N) <- (
    wto_totals(REST_WEEKS, T0, N0),
    TOTAL == T0 + WORKED_MINUTES,
    N == N0 + 1
),

test("totals over one week, outputs free") <- (
    wto_totals([[2880, work]], TOTAL, N),
    TOTAL == 2880
),
"""


def test_ground_base_case_near_miss_keeps_rung_1(capsys, tmp_path):
    p = write(tmp_path, f"wto{SEAM}", CONS_OUTPUT_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "argument 1 differs" in out
    assert "wto_totals([], TOTAL, N)" in out   # the ground [] base-case match
    assert "no clause head unifies" not in out


def test_ground_fact_near_miss_keeps_rung_1(capsys, tmp_path):
    p = write(tmp_path, f"gpair{SEAM}", """
        -double_quotes(atom)
        gpair("a", 1),
        gpair("b", 2),

        test("one argument differs") <- (
            gpair("c", 1)
        ),
    """)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "argument 1 differs" in out
    assert "gpair(a, 1)" in out
    assert "no clause head unifies" not in out


# Rung 2's all-holes examples can be degenerate the same way: a var-coupled
# fact satisfies the probe with every hole left unbound (`pairq(_, _, _, _)`),
# which says nothing.  When NO example binds every argument, descend; the head
# listing shows the coupling that the anonymous-hole render hid.
COUPLED_FACT_SRC = """
-double_quotes(atom)
pairq(A, B, A, B),

test("both couplings differ") <- (
    pairq(1, 2, 3, 4)
),
"""


def test_degenerate_rung2_examples_descend(capsys, tmp_path):
    p = write(tmp_path, f"pairq{SEAM}", COUPLED_FACT_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "none binds every argument to a concrete value" in out
    assert "no clause head unifies" in out
    assert "pairq(A, B, A, B)" in out
    assert "pairq(_, _, _, _)" not in out    # the degenerate example is dropped
    assert "it does have:" not in out


def test_degenerate_near_miss_falls_back_when_descent_finds_nothing(
        capsys, tmp_path, monkeypatch):
    # If the descent has nothing to say (unresolvable predicate, every clause
    # skipped), the weak rung-1 rendering is still better than silence.
    import clausal.testing as _t
    monkeypatch.setattr(_t, "_descend", lambda *a, **k: ([], "none"))
    p = write(tmp_path, f"fallback{SEAM}", LONE_BOUND_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "DID have a solution" in out
    assert "argument 1 differs" in out
    assert "no clause body survives" not in out


# The scan continues PAST a degenerate slot: freeing argument 1 matches the
# BitOr-headed fact with the hole left non-ground, but freeing argument 2
# finds the concrete `8` — a genuine counter-value, reported exactly as
# before.  The degenerate hit must neither win nor leave its (never-final)
# rendering behind.
MIXED_SLOTS_SRC = """
-double_quotes(atom)
mixf(A | B, 7),
mixf([1, 2], 8),

test("later concrete slot wins") <- (
    mixf([1, 2], 7)
),
"""


def test_concrete_near_miss_in_a_later_slot_wins_over_degenerate(
        capsys, tmp_path):
    p = write(tmp_path, f"mixf{SEAM}", MIXED_SLOTS_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "argument 2 differs" in out
    assert "mixf([1, 2], 8)" in out
    assert "no clause head unifies" not in out
    assert "none binds" not in out


# The keyword-argument slot path builds its own label; the degenerate intro
# must carry it through to the descent headline.
KWARG_DEG_SRC = """
-double_quotes(atom)
kdeg(R=A | B),

test("kwarg degenerate") <- (
    kdeg(R=[1, 2])
),
"""


def test_a_degenerate_keyword_argument_is_refused_at_load(capsys, tmp_path):
    """The keyword-argument LABEL path is unreachable from source.

    It used to be pinned through a degenerate intro ("solutions with keyword
    argument 'R' freed, but none binds …"), because that label is built by its
    own branch.  A term is built positionally since 2026-09-19, so the source
    that reached the branch no longer loads; the branch goes with the keyword
    machinery in P4, and this is the reminder that nothing reaches it.
    """
    p = write(tmp_path, f"kdeg{SEAM}", KWARG_DEG_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "keyword arguments" in out and "kdeg/1" in out


def test_degenerate_rung2_falls_back_when_descent_finds_nothing(
        capsys, tmp_path, monkeypatch):
    # Rung-2 analogue of the rung-1 fallback: the anonymised examples are
    # weak, but they must survive when the descent has nothing better.
    import clausal.testing as _t
    monkeypatch.setattr(_t, "_descend", lambda *a, **k: ([], "none"))
    p = write(tmp_path, f"pairq_fb{SEAM}", COUPLED_FACT_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "it does have:" in out
    assert "pairq(_, _, _, _)" in out
    assert "no clause head unifies" not in out


# ── forall(X in LIST, Body): name the failing element(s) ─────────────────────
#
# A ``forall(X in LIST, Body)`` reaches ``_report_nearest`` as an ordinary
# ``Call(forall, ...)`` whose "predicate" has no clauses, so it used to fall
# straight through to the bare rung-3 "no solution for ANY arguments" line and
# never name WHICH element of LIST broke Body.  Candidate 1 (see
# ``todo/done/forall-failure-names-no-failing-binding-2026-08-02.md``): on
# failure, re-run Body per element (bounded) and report the elements for which
# Body has no solution, by name.
FORALL_ONE_SRC = """
-double_quotes(atom)
positivep(1),
positivep(2),
positivep(4),
positivep(5),

test("all positive") <- (
    forall(SUBJECT in [1, 2, 3, 4, 5], positivep(SUBJECT))
),
"""


def test_forall_names_the_single_failing_element(capsys, tmp_path):
    p = write(tmp_path, f"fa_one{SEAM}", FORALL_ONE_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    # The headline states how many of how many failed, and by which name.
    assert "failed for 1 of 5 elements" in out
    assert "SUBJECT = 3" in out           # the one element with no solution
    # The bare rung-3 non-answer must NOT be what the reader sees.
    assert "no solution for ANY arguments" not in out


FORALL_MANY_SRC = """
-double_quotes(atom)
positivem(2),
positivem(4),

test("all positive, several fail") <- (
    forall(SUBJECT in [1, 2, 3, 4, 5], positivem(SUBJECT))
),
"""


def test_forall_names_every_failing_element_within_the_bound(capsys, tmp_path):
    p = write(tmp_path, f"fa_many{SEAM}", FORALL_MANY_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "failed for 3 of 5 elements" in out
    assert "SUBJECT = 1" in out
    assert "SUBJECT = 3" in out
    assert "SUBJECT = 5" in out


# The per-element re-run is bounded the same way descent is (reusing
# $CLAUSAL_TEST_DIAG_BUDGET) — a long LIST reports only the first
# DIAG_MAX_DESCENT_LEAVES failing elements and states the truncation, rather
# than walking (and re-solving Body over) an unbounded list.
FORALL_LONG_SRC = """
-double_quotes(atom)
noneofthem(_X) <- (1 > 2),

test("long list, all fail") <- (
    forall(N in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10], noneofthem(N))
),
"""


def test_forall_bounds_the_number_of_named_elements(capsys, tmp_path):
    from clausal.testing import DIAG_MAX_DESCENT_LEAVES

    p = write(tmp_path, f"fa_long{SEAM}", FORALL_LONG_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    # All ten elements fail, but only the first N are named...
    assert out.count("N = ") == DIAG_MAX_DESCENT_LEAVES
    assert (
        f"failed for at least {DIAG_MAX_DESCENT_LEAVES} of 10 elements" in out
    )
    # ...and the truncation is stated rather than silently dropped.
    assert (
        f"more than {DIAG_MAX_DESCENT_LEAVES} of the 10 elements failed" in out
    )


# The failing element is named even when Body is an inline conjunction (the
# measured incident's shape: ``forall(SUBJECT in LIST, (...))``); the headline
# still identifies the culprit element rather than the whole list.
FORALL_CONJ_SRC = """
-double_quotes(atom)
test("all in range") <- (
    forall(V in [0, 1, 7, 2], (V >= 0, V <= 3))
),
"""


def test_forall_names_element_with_conjunction_body(capsys, tmp_path):
    p = write(tmp_path, f"fa_conj{SEAM}", FORALL_CONJ_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "failed for 1 of 4 elements" in out
    assert "V = 7" in out


# ── wrong-value / findall-collapse descent ───────────────────────────────────
#
# The measured incident class: a goal SUCCEEDS with the WRONG value because a
# `findall` inside it silently collapsed to [] — every candidate's body failed
# on a wrong-type / unbound argument — and `max_list` then returned 0.  The
# top-level report only saw the downstream `MAX == 90`
# comparison fail; the failing conjunct is not a predicate call, so the pre-
# existing rung-3 descent never fired and nothing named the findall's body.
#
# The fix: when the failing conjunct is not a Call (a comparison / unify) but
# its variables were bound by an EARLIER successful predicate call, descend into
# that producer, and inside the descent name a `findall` whose body never had a
# solution — reusing the same _first_failing / leaf-line / leaf-binding
# machinery the ordinary descent already uses.

WINDOW_SHAPE_SRC = """
-double_quotes(atom)
-private([bad_atom])

# window_days_used wants its first argument as a list [Y, M, D]; the caller
# hands it a bare atom, so the head never matches and the body FAILS for every
# candidate.  findall still SUCCEEDS, collapsing to [], and max_list_or_zero
# returns 0.
window_days_used([Y, M, D], DAYS) <- (
    DAYS == Y
),

candidate(10),
candidate(20),

max_additional_days(MAX) <- (
    findall(D, (candidate(_C), window_days_used(bad_atom, D)), DAYS),
    max_list_or_zero(DAYS, MAX)
),

max_list_or_zero([], 0),
max_list_or_zero([H, *T], M) <- (
    max_list([H, *T], M)
),

test("max additional days is 90") <- (
    max_additional_days(MAX),
    MAX == 90
),
"""


def test_findall_collapse_behind_wrong_value_is_named(capsys, tmp_path):
    p = write(tmp_path, f"window_rule{SEAM}", WINDOW_SHAPE_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    # The downstream comparison is still the failing conjunct...
    assert "MAX == 90" in out
    assert "MAX = 0" in out
    # ...but now the report also blames the producer's collapsed findall and
    # names the body goal that failed for every candidate, with its binding.
    assert "findall" in out
    assert "window_days_used(bad_atom, D)" in out


# The producer's collapsed findall is reached by descending into the earlier
# SUCCESSFUL call that bound the wrong value.  Here the producer is a WRAPPER
# (`score`) that itself calls the findall-bearing predicate (`inner_score`), so
# the descent must go one level deeper than the direct case above to reach the
# findall — exercising the recursive `_descend` step, not just the top clause.
NESTED_PRODUCER_SRC = """
-double_quotes(atom)
-private([bad_atom])

window_days_used([Y, M, D], DAYS) <- (
    DAYS == Y
),

candidate(10),

inner_score(MAX) <- (
    findall(D, (candidate(_C), window_days_used(bad_atom, D)), DAYS),
    max_list_or_zero(DAYS, MAX)
),

score(MAX) <- (
    inner_score(MAX)
),

max_list_or_zero([], 0),
max_list_or_zero([H, *T], M) <- (
    max_list([H, *T], M)
),

test("score is 90") <- (
    score(MAX),
    MAX == 90
),
"""


def test_findall_collapse_via_nested_producer(capsys, tmp_path):
    p = write(tmp_path, f"score{SEAM}", NESTED_PRODUCER_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "MAX == 90" in out
    # Descent went through the wrapper `score` into `inner_score`'s findall.
    assert "window_days_used(bad_atom, D)" in out


# A findall whose body DOES solve for at least one candidate is not blamed:
# the collapse sentinel is specific to a body that failed for EVERY candidate.
HEALTHY_FINDALL_SRC = """
-double_quotes(atom)
candidate(10),
candidate(20),

widen(X, DAYS) <- (DAYS == X),

good_max(MAX) <- (
    findall(D, (candidate(C), widen(C, D)), DAYS),
    max_list_or_zero(DAYS, MAX)
),

max_list_or_zero([], 0),
max_list_or_zero([H, *T], M) <- (
    max_list([H, *T], M)
),

test("good max is 90") <- (
    good_max(MAX),
    MAX == 90
),
"""


def test_healthy_findall_is_not_blamed(capsys, tmp_path):
    p = write(tmp_path, f"good{SEAM}", HEALTHY_FINDALL_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    # findall produced [10, 20]; max is 20, not 90.  The findall did its job —
    # the sentinel must NOT fabricate a collapse finding.
    assert "MAX == 90" in out
    assert "MAX = 20" in out
    assert "every candidate" not in out


# ── composition: forall over a body that hides a collapsed findall ───────────
#
# When BOTH new diagnostics could speak — the outer goal is a
# forall(X in LIST, ...) AND its body hides a findall that collapsed to [] —
# the forall interception runs first and OWNS the report: the failure is
# attributed per element ("failed for N of M elements:"), and the
# findall-collapse sentinel does not interleave a second narrative into the
# same failure block.  Outermost first: the element identity is the fact the
# repair loop needs at this level, and a repair that binds the element and
# re-runs will meet the collapse sentinel one level down.
FORALL_COLLAPSED_FINDALL_SRC = """
-double_quotes(atom)
cand(9),
big(X) <- (X > 10),

test("forall over collapsed findall") <- (
    forall(K in [1, 2], (
        findall(A, (cand(A), big(A)), XS),
        XS == [K]
    ))
),
"""


def test_forall_over_collapsed_findall_composes_element_first(capsys, tmp_path):
    p = write(tmp_path, f"fa_findall{SEAM}", FORALL_COLLAPSED_FINDALL_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    # One coherent forall report: every element named...
    assert "failed for 2 of 2 elements" in out
    assert "K = 1" in out
    assert "K = 2" in out
    # ...and no second, interleaved findall-collapse narrative in the block.
    assert "every candidate" not in out
    assert "the value it compares was produced by" not in out


# ── the measured `[0]` shape: a ONE-trivial-solution collapse ────────────────
#
# The measured incident's findall did NOT collapse to []: the LENGTH=0 probe
# succeeds trivially, so the bag is `[0]`, `max_list([0]) = 0`, and the verdict
# flips.  A collapse gate of "body has no solution" lets that escape — the body
# HAS a solution, just only the trivial one.  The fix re-walks the body with a
# `template is not 0` disequality injected after the candidate generator, and
# names the first NON-trivial failure; when that failing conjunct consumes a
# second findall's empty bag (the same nesting pattern: `length(DS, L)` with
# `DS = []`), the inner collapse is named beneath it as well.
TRIVIAL_COLLAPSE_SRC = """
-double_quotes(atom)
hit(99),

usable(0),
usable(L) <- (
    L > 0,
    findall(D, (between(1, 3, D), hit(D)), DS),
    length(DS, L)
),

maxdays(MAX) <- (
    findall(L, (between(0, 3, L), usable(L)), LS),
    max_list(LS, MAX)
),

test("maxdays is 3") <- (
    maxdays(MAX),
    MAX == 3
),
"""


def test_one_trivial_solution_collapse_is_named(capsys, tmp_path):
    p = write(tmp_path, f"trivial{SEAM}", TRIVIAL_COLLAPSE_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "MAX == 3" in out
    assert "MAX = 0" in out
    # The [0] shape is stated as such, not mistaken for a healthy findall...
    assert "silently collapsed to [0]" in out
    assert "the first non-trivial candidate fails at" in out
    # ...the first non-trivial candidate's failing conjunct is named with its
    # binding, and the chain continues into the nested empty-bag collapse.
    assert "usable(L)" in out
    assert "L = 1" in out
    assert "length(DS, L)" in out
    assert "hit(D)" in out


# A dotted / module-qualified atom on the comparison's right side (the measured
# `STATUS is eu.<package>.eligible` shape) must still reach the wrong-value
# bridge: the producer is found by Var identity on the LEFT side, so the
# qualified-atom node shape on the right must not derail the report.
def test_dotted_atom_comparison_reaches_producer(capsys, tmp_path, monkeypatch):
    import sys as _sys
    monkeypatch.syspath_prepend(str(tmp_path))
    _sys.modules.pop("verdict_lib", None)
    write(tmp_path, f"verdict_lib{SEAM}", """
        -module(verdict_lib, [eligible, ineligible, assess(S, V)])

        ok_len(0),

        assess(_S, V) <- (
            findall(L, (between(0, 3, L), ok_len(L)), LS),
            max_list(LS, MAX),
            verdict(MAX, V)
        ),

        verdict(MAX, eligible) <- (MAX > 0),
        verdict(MAX, ineligible) <- (MAX <= 0)
    """)
    p = write(tmp_path, f"dotted{SEAM}", """
        -double_quotes(atom)
        -import_from(verdict_lib, [eligible, assess])

        test("dotted atom comparison") <- (
            assess("subject", STATUS),
            STATUS is eligible
        ),
    """)
    try:
        assert main([str(p)]) == 1
        out = capsys.readouterr().out
        assert "STATUS is" in out
        # The bridge fired despite the non-Call comparison shape...
        assert "the value it compares was produced by" in out
        # ...and traced the wrong value to the [0]-collapse inside assess.
        assert "silently collapsed to [0]" in out
        assert "ok_len(L)" in out
        assert "L = 1" in out
    finally:
        _sys.modules.pop("verdict_lib", None)


# The wrong value rides a chain of SUCCEEDING wrappers before the collapsing
# findall (assess → decide → stay_eligibility → max_additional_days in the
# incident).  The collapse scan follows satisfiable calls beyond the 2-level
# failing-call descent bound — up to DIAG_MAX_COLLAPSE_DEPTH levels.
DEEP_WRAPPER_SRC = """
-double_quotes(atom)
usable2(0),

maxdays2(MAX) <- (
    findall(L, (between(0, 3, L), usable2(L)), LS),
    max_list(LS, MAX)
),

w3(M) <- (maxdays2(M)),
w2(M) <- (w3(M)),
w1(M) <- (w2(M)),

test("deep wrapper chain") <- (
    w1(MAX),
    MAX == 3
),
"""


def test_collapse_scan_descends_past_failing_call_depth_bound(capsys, tmp_path):
    p = write(tmp_path, f"deepwrap{SEAM}", DEEP_WRAPPER_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    # The findall sits FOUR call levels below the failing comparison's
    # producer; the old DIAG_MAX_DESCENT_DEPTH=2 scan went silent here.
    assert "the value it compares was produced by w1(...)" in out
    assert "silently collapsed to [0]" in out
    assert "usable2(L)" in out


# When the chain is deeper than DIAG_MAX_COLLAPSE_DEPTH, the scan must not go
# SILENT (the original bug's failure mode): it stops, and says that it stopped.
OVERDEEP_WRAPPER_SRC = """
-double_quotes(atom)
usable3(0),

maxdays3(MAX) <- (
    findall(L, (between(0, 3, L), usable3(L)), LS),
    max_list(LS, MAX)
),

v5(M) <- (maxdays3(M)),
v4(M) <- (v5(M)),
v3(M) <- (v4(M)),
v2(M) <- (v3(M)),
v1(M) <- (v2(M)),

test("overdeep wrapper chain") <- (
    v1(MAX),
    MAX == 3
),
"""


def test_collapse_scan_depth_exhaustion_is_noted(capsys, tmp_path):
    from clausal.testing import DIAG_MAX_COLLAPSE_DEPTH

    p = write(tmp_path, f"overdeep{SEAM}", OVERDEEP_WRAPPER_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    # The findall is one level beyond the bound: no finding is possible...
    assert "silently collapsed to [0]" not in out
    # ...but the exhaustion is STATED, never silent.
    assert (f"stopped at its {DIAG_MAX_COLLAPSE_DEPTH}-level depth bound"
            in out)


# ── head listings state exactly what was checked; heads keep their arguments ──
#
# A downstream harness feeds these lines to a model as feedback.  It used to
# be told "no clause head unifies with these arguments" for a call whose
# matching clause was the 7th: the descent looked only at the first
# DIAG_MAX_DESCENT_CLAUSES heads, and printed each as ``engagement(_, _)``
# because the native front end hoists a structural head argument
# (``met(a)``) into the body.  Head unification is now checked for EVERY
# clause (it is cheap; the cap bounds the recursive descent), the descent
# walks the clauses whose heads unify, and a head is printed from its source,
# bounded in depth and length.

from clausal._suffixes import CLAUSAL_PROLOG_SUFFIXES  # noqa: E402

CP = CLAUSAL_PROLOG_SUFFIXES[0]

# Lines 1..8 are the clauses of engagement/2; the 7th is the only one whose
# head unifies with engagement(5, unmet).  Every body is a contradictory pair,
# so the all-holes probe fails and rung 3 descends.
ENGAGEMENT_CP = textwrap.dedent("""\
    engagement(P, met(a)) :- P > 100, P < 0.
    engagement(P, met(b)) :- P > 100, P < 0.
    engagement(P, met(c)) :- P > 100, P < 0.
    engagement(P, met(d)) :- P > 100, P < 0.
    engagement(P, met(e)) :- P > 100, P < 0.
    engagement(P, met(f)) :- P > 100, P < 0.
    engagement(P, unmet) :- P > 200, P < 0.
    engagement(P, open(x)) :- P > 300, P < 0.
    decide(P, ok) :- engagement(P, unmet).
    decide_other(P) :- engagement(P, other).
""")


def _cp(tmp_path, name, tests):
    p = tmp_path / f"{name}{CP}"
    p.write_text(ENGAGEMENT_CP + textwrap.dedent(tests))
    return p


def test_matching_clause_beyond_the_cap_is_walked_top_level(capsys, tmp_path):
    p = _cp(tmp_path, "eng_top", "test(top) :- engagement(5, unmet).\n")
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "no clause head" not in out and "none of the" not in out
    assert ("    the predicate has no solution for ANY arguments at this "
            "point; no clause body survives:\n"
            f"      eng_top{CP}:7  P > 200  (via eng_top{CP}:7)\n"
            "          P = 5\n") in out
    assert "descent walked" not in out       # one route: nothing was capped


def test_matching_clause_beyond_the_cap_is_walked_nested(capsys, tmp_path):
    p = _cp(tmp_path, "eng_nest", "test(nested) :- decide(5, ok).\n")
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "no clause head" not in out and "none of the" not in out
    assert (f"      eng_nest{CP}:7  P > 200  (via eng_nest{CP}:9 → 7)\n"
            "          P = 5\n") in out


CAPPED_LISTING = (
    "no clause head unifies with these arguments — the heads are:\n"
    "{i}eng_{n}{cp}:1  engagement(P, met(a))\n"
    "{i}eng_{n}{cp}:2  engagement(P, met(b))\n"
    "{i}eng_{n}{cp}:3  engagement(P, met(c))\n"
    "{i}eng_{n}{cp}:4  engagement(P, met(d))\n"
    "{i}eng_{n}{cp}:5  engagement(P, met(e))\n"
    "{i}eng_{n}{cp}:6  engagement(P, met(f))\n"
    "{i}eng_{n}{cp}:7  engagement(P, unmet)\n"
    "{i}eng_{n}{cp}:8  engagement(P, open(x))\n"
)


def test_capped_listing_states_all_heads_checked_top_level(capsys, tmp_path):
    p = _cp(tmp_path, "eng_none", "test(none) :- engagement(5, other).\n")
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert ("    the predicate has no solution for ANY arguments at this "
            "point; " + CAPPED_LISTING.format(i="      ", n="none", cp=CP)
            ) in out
    assert "descent walked" not in out       # every head WAS checked


def test_capped_listing_states_all_heads_checked_nested(capsys, tmp_path):
    p = _cp(tmp_path, "eng_nnest", "test(none) :- decide_other(5).\n")
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert (f"      eng_nnest{CP}:10  engagement(P, other)  "
            f"(via eng_nnest{CP}:10)\n"
            "          P = 5\n"
            "          " + CAPPED_LISTING.format(
                i="            ", n="nnest", cp=CP)) in out
    assert "descent walked" not in out


def test_uncapped_listing_wording_matches_top_level_and_nested(
        capsys, tmp_path):
    p = tmp_path / f"few{CP}"
    p.write_text(textwrap.dedent("""\
        few(P, met(a)) :- P > 100, P < 0.
        few(P, met(b)) :- P > 100, P < 0.
        few_caller(P) :- few(P, other).
        test(top) :- few(5, other).
        test(nested) :- few_caller(5).
    """))
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    listing = ("no clause head unifies with these arguments — the heads are:\n"
               "{i}few{cp}:1  few(P, met(a))\n"
               "{i}few{cp}:2  few(P, met(b))\n")
    assert ("point; " + listing.format(i="      ", cp=CP)) in out
    assert ("          P = 5\n"
            "          " + listing.format(i="            ", cp=CP)) in out


def test_descent_cap_counts_the_routes_whose_heads_unify(capsys, tmp_path):
    # Six of eight heads unify with engagement(5, met(_)); four are walked.
    p = _cp(tmp_path, "eng_cap", "test(capped) :- engagement(5, met(_)).\n")
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert ("note: descent walked only the first 4 of 6 clauses of "
            "engagement whose heads unify with these arguments "
            "(8 clauses in all)") in out
    assert out.count("P > 100") == 4


def test_long_and_deep_head_arguments_are_truncated(capsys, tmp_path):
    long_atom = "x" * 200
    p = tmp_path / f"deep{CP}"
    p.write_text(textwrap.dedent(f"""\
        deep(f(g(h(i(j(k)))))) :- 1 > 2.
        deep({long_atom}) :- 1 > 2.
        test(deep) :- deep(zz).
    """))
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert f"      deep{CP}:1  deep(f(g(h(i(…)))))\n" in out
    from clausal.testing import DIAG_MAX_HEAD_CHARS
    expected = ("deep(" + long_atom)[:DIAG_MAX_HEAD_CHARS - 1] + "…"
    assert f"      deep{CP}:2  {expected}\n" in out
    assert long_atom not in out


def test_bound_text_helper():
    from clausal.testing import _bound_text
    assert _bound_text("p(a, b)", max_chars=80, max_depth=2) == "p(a, b)"
    assert _bound_text("p(f(g(x)), [1, [2, [3]]])", max_chars=80,
                       max_depth=2) == "p(f(g(…)), [1, […]])"
    # Brackets inside quoted atoms and strings do not count as depth.
    assert _bound_text("p('a(b(c', \"[[\")", max_chars=80,
                       max_depth=1) == "p('a(b(c', \"[[\")"
    # 0'( is a character code, not a bracket.
    assert _bound_text("p(0'(, x)", max_chars=80, max_depth=1) == "p(0'(, x)"
    assert _bound_text("p(abcdefgh)", max_chars=6, max_depth=4) == "p(abc…"


def test_heads_clash_is_conservative():
    # Only certainly-different terms clash; anything unsure is left to the
    # query probe, so the cheap check can never make a head look refused.
    from clausal.logic.variables import Var
    from clausal.pythonic_ast.nodes import Unify
    from clausal.testing import _heads_clash

    def clash(a, b):
        return _heads_clash([Unify(left=a, right=b)], [])

    assert clash("a", "b") and clash(1, 2) and clash("a", 1)
    assert clash(("met", "a"), "unmet") and clash(("f", 1), ("g", 1))
    assert clash(("f", 1), ("f", 1, 2)) and clash(("f", "a"), ("f", "b"))
    assert not clash("a", "a") and not clash(Var(), "a")
    assert not clash(1, 1.0) and not clash([], "[]")
    assert not clash(("$chars", "ab"), "ab") and not clash(True, 1)
    # A hoisted head argument is compared with the goal argument it meets.
    v = Var()
    assert _heads_clash([Unify(left=v, right="unmet")],
                        [Unify(left=v, right=("met", "a"))])
    assert not _heads_clash([Unify(left=v, right=Var())],
                            [Unify(left=v, right=("met", "a"))])


def test_fact_table_head_listing_checks_every_fact(capsys, tmp_path):
    # outer/1 has no solution at all, so rung 3 descends into fact/2, a
    # 300-fact table no head of which unifies with fact(5, zz).
    p = tmp_path / f"facts{CP}"
    p.write_text("\n".join(f"fact({i}, v{i})." for i in range(300)) + "\n"
                 + "outer(X) :- X > 100, X < 0.\n"
                 + "outer(X) :- fact(X, zz).\n"
                 + "test(hit) :- outer(5).\n")
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    heads = "".join(f"            facts{CP}:{i + 1}  fact({i}, v{i})\n"
                    for i in range(12))
    assert (f"      facts{CP}:302  fact(X, zz)  (via facts{CP}:302)\n"
            "          X = (same as above)\n"
            "          none of the 300 clause heads unifies with these "
            "arguments — the heads are:\n"
            + heads +
            "            and 288 more heads\n") in out
    assert "descent walked" not in out


# A goal with a partial-list argument (`[Key-Value|AccIn]`) printed no
# bindings at all: the reader spells the list as a '.' cons chain, the
# runtime as a list ending in a tail splat, and the native pairing refused
# the '.' term, so every variable of the goal went unnamed.
PARTIAL_LIST_CP = textwrap.dedent("""\
    pg(_, k, v).
    cpairs(Profile, [Key|Keys], Pairs) :-
        pg(Profile, Key, Value),
        cpairs(Keys, [Key-Value|AccIn], Pairs),
        AccIn = [].
    cpairs(_Profile, [], Pairs) :- Pairs = z, 1 > 2.
    outer(P) :- cpairs(P, [k], _), 1 > 2.
    test(t) :- outer(p).
""")


def test_partial_list_goal_keeps_its_bindings(capsys, tmp_path):
    p = tmp_path / f"cpairs{CP}"
    p.write_text(PARTIAL_LIST_CP)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert (f"      cpairs{CP}:4  cpairs(Keys, [Key-Value|AccIn], Pairs)  "
            f"(via cpairs{CP}:7 → 2)\n"
            "          Keys = []\n"
            "          Key = k\n"
            "          Value = v\n") in out


# ── each binding printed once; notes once; an empty binding list said ─────

# Three findings under one test, each binding the same 1-element input.  The
# first prints it, the others say "(same as above)"; a different value under
# the same name prints in full.
REPEAT_CP = textwrap.dedent("""\
    r(In, a) :- In = [N], N > 100, N < 0.
    r(In, b) :- In = [N], N > 200, N < 0.
    r(In, c) :- In = [N], N > 300, N < 0.
    s(In) :- r(In, _).
    test(rep) :- s([5]).
""")


def test_a_repeated_binding_prints_same_as_above(capsys, tmp_path):
    p = tmp_path / f"rep{CP}"
    p.write_text(REPEAT_CP)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert out.count("N = 5") == 1
    assert out.count("N = (same as above)") == 2


def test_binding_dedupe_compares_printed_text_per_name():
    from clausal.testing import GoalDiagnostic
    d = GoalDiagnostic(
        index=1, total=1, bindings=[("P", "[1]")],
        descent=["f.clausal:1  g(P)", "    P = [1]", "    Q = [1]",
                 "f.clausal:2  h(P)", "    P = [2]", "    P = [2]",
                 "    P = [1]"],
        notes=["n1", "n2", "n1"])
    text = "\n".join(d.lines())
    assert ("          P = (same as above)\n"
            "          Q = [1]\n") in text
    # Compared with the value last printed under the name: after P = [2],
    # P = [1] is printed in full again, never "(same as above)".
    assert ("          P = [2]\n"
            "          P = (same as above)\n"
            "          P = [1]\n") in text
    assert text.count("note: n1") == 1 and text.endswith("note: n2")


def test_a_leaf_without_bound_variables_says_no_bindings(capsys, tmp_path):
    p = tmp_path / f"nob{CP}"
    p.write_text(textwrap.dedent("""\
        q(_) :- 1 > 2.
        nob(_) :- q(_Y), 1 > 2.
        test(t) :- nob(1).
    """))
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    # The descent reaches q/1's body: `1 > 2` has no variables at all.
    assert (f"      nob{CP}:1  1 > 2  (via nob{CP}:2 → 1)\n"
            "          no bindings\n") in out


def test_route_suffix_and_more_findings_note():
    from clausal.testing import _cap_leaves, _route_suffix, _RoutedLine
    assert _route_suffix((("a.clausal", 455), ("a.clausal", 234))) == \
        "(via a.clausal:455 → 234)"
    # A file is named again only when the route changes file.
    assert _route_suffix((("a.clausal", 9), ("b.clausal", 3),
                          ("b.clausal", 7))) == "(via a.clausal:9 → b.clausal:3 → 7)"
    line = _RoutedLine("a.clausal:2  g(X)")
    line.route = (("a.clausal", 1),)
    groups = [[line, "    X = 1"]] + [[f"a.clausal:{i}  h", "    no bindings"]
                                       for i in range(6)]
    notes = []
    out = _cap_leaves(groups, notes)
    assert out[0] == ["a.clausal:2  g(X)  (via a.clausal:1)", "    X = 1"]
    assert out[6] == ["a.clausal:5  h"]               # 7th: first line only
    assert notes == ["1 more finding, shown by its first line only"]


def test_unavailable_bindings_wording():
    from clausal.testing import BINDINGS_UNAVAILABLE
    assert BINDINGS_UNAVAILABLE == ("bindings unavailable — the goal's "
                                    "variable names could not be read from "
                                    "the source")
