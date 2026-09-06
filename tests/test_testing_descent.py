"""Stage-4 descent diagnostics + rung-2 examples for ``python -m clausal.testing``.

Rung 3 ("no solution for ANY arguments") used to carry no value — measured
0/29 recovery in a measured authoring study.  See
``docs/superpowers/specs/2026-07-30-assertion-diagnostic-descent-design.md``.
"""

from __future__ import annotations

import textwrap

from clausal.logic.atoms import char_atom, mint
from clausal.testing import main


def write(tmp_path, name, src):
    p = tmp_path / name
    p.write_text(textwrap.dedent(src).lstrip())
    return p


# ── rung 2: satisfiable, but 2+ arguments differ ─────────────────────────────

PAIR_SRC = """
pairx("a", 1),
pairx("b", 2),

Test("both arguments differ") <- (
    pairx("c", 3)
),
"""


def test_two_plus_args_differ_shows_example_solutions(capsys, tmp_path):
    p = write(tmp_path, "pair.clausal", PAIR_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "two or more arguments differ" in out   # old sentence survives
    assert "it does have:" in out                  # new suffix
    assert "pairx(a, 1)" in out                  # an actual solution, rendered


# ── rung 3: descent into the failing predicate ───────────────────────────────

GUARD_SRC = """
chk_range(PCT) <- (
    PCT >= 0,
    PCT > 100,
    PCT <= 100
),

Test("contradictory guards") <- (
    chk_range(50)
),
"""


def test_contradictory_guard_named_with_value(capsys, tmp_path):
    p = write(tmp_path, "guard.clausal", GUARD_SRC)
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
-private([small, big])

classify(X, small) <- (X < 10, X < 0, X > 100),
classify(X, big) <- (X > 10, X < 0),

Test("two routes both fail") <- (
    classify(5, _KIND)
),
"""


def test_each_clause_route_gets_a_leaf(capsys, tmp_path):
    p = write(tmp_path, "routes.clausal", TWO_ROUTES_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "X < 0" in out    # clause 1's first failing conjunct (5 < 10 passed)
    assert "X > 10" in out   # clause 2's
    assert "X = 5" in out


DYN_SRC = """
-dynamic(dynp/1)

Test("zero-clause predicate") <- (
    dynp(1)
),
"""


def test_zero_clause_predicate_keeps_old_message(capsys, tmp_path):
    p = write(tmp_path, "dyn.clausal", DYN_SRC)
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
inner_rule(N) <- (N > 100, N < 0),
outer_rule(N) <- (inner_rule(N)),

Test("nested failure") <- (
    outer_rule(5)
),
"""


def test_descends_through_intermediate_predicate(capsys, tmp_path):
    p = write(tmp_path, "nested.clausal", NESTED_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "N > 100" in out   # the inner predicate's conjunct, not inner_rule(N)
    assert "N = 5" in out


def test_cross_module_descent(capsys, tmp_path, monkeypatch):
    import sys as _sys
    monkeypatch.syspath_prepend(str(tmp_path))
    _sys.modules.pop("descent_lib", None)
    write(tmp_path, "descent_lib.clausal", """
        -module(descent_lib, [lib_check(N)])

        lib_check(N) <- (N > 100, N < 0)
    """)
    p = write(tmp_path, "use.clausal", """
        -import_from(descent_lib, [lib_check])

        Test("cross-module") <- (
            lib_check(5)
        ),
    """)
    try:
        assert main([str(p)]) == 1
        out = capsys.readouterr().out
        assert "no clause body survives" in out
        assert "N > 100" in out
        assert "N = 5" in out
        assert "descent_lib.clausal:" in out   # leaf names the DEFINING file
    finally:
        _sys.modules.pop("descent_lib", None)


# Same unsatisfiability requirement as NESTED_SRC (contradictory `N > 100,
# N < 0`), so the chain lvl1->lvl2->lvl3 reaches descent instead of rung 1.
# Descent caps at depth 2: lvl1's leaf lvl2(N) recurses to lvl2, whose leaf
# lvl3(N) is a Call at depth 2 and is rendered as-is — lvl3's body is never
# entered, so `N > 100` never surfaces.
DEEP_SRC = """
lvl3(N) <- (N > 100, N < 0),
lvl2(N) <- (lvl3(N)),
lvl1(N) <- (lvl2(N)),

Test("three levels") <- (
    lvl1(5)
),
"""


def test_depth_cap_stops_at_two_levels(capsys, tmp_path):
    p = write(tmp_path, "deep.clausal", DEEP_SRC)
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
-private([work])

wk_totals([], 0) <- (1 > 2),
wk_totals([MINS, STATUS] | REST, TOTAL) <- (
    TOTAL == MINS,
    1 > 2
),

Test("cons head never matches") <- (
    wk_totals([[2880, work]], 2880)
),
"""


def test_all_heads_fail_lists_the_heads(capsys, tmp_path):
    p = write(tmp_path, "cons.clausal", CONS_SRC)
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
-private([work])

wkn_totals([], 0) <- (1 > 2),
wkn_totals([MINS, STATUS] | REST, TOTAL) <- (
    TOTAL == MINS,
    1 > 2
),

wkn_check(WEEKS) <- (
    wkn_totals(WEEKS, _TOTAL)
),

Test("nested cons head") <- (
    wkn_check([[2880, work]])
),
"""


def test_head_listing_attaches_beneath_parent_leaf(capsys, tmp_path):
    p = write(tmp_path, "consn.clausal", CONS_NESTED_SRC)
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
-private([r1, r2, r3, r4, r5, r6])

sixway(N, r1) <- (N > 100, N < 0),
sixway(N, r2) <- (N > 100, N < 0),
sixway(N, r3) <- (N > 100, N < 0),
sixway(N, r4) <- (N > 100, N < 0),
sixway(N, r5) <- (N > 100, N < 0),
sixway(N, r6) <- (N > 100, N < 0),

Test("six clauses") <- (
    sixway(5, _R)
),
"""


def test_clause_cap_is_applied_and_noted(capsys, tmp_path):
    p = write(tmp_path, "six.clausal", SIX_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert out.count("N > 100") == 4          # DIAG_MAX_DESCENT_CLAUSES leaves
    assert "first 4 of 6 clauses" in out      # the truncation is stated


# The DIAG_MAX_DESCENT_LEAVES cap bounds TOTAL findings across the whole
# descent, INCLUDING fan-out: one clause route that recurses into a deeper
# predicate can produce several findings (design §Flat leaves: "one clause
# route can fan out into several leaves — the flat list is leaves, not
# routes").  Here 4 outer clauses each recurse into ``inner`` (2 failing
# routes), so descent produces 4 x 2 = 8 findings — over the cap of 6.  Neither
# the outer (4 clauses) nor the inner (2 clauses) predicate trips the
# per-predicate clause cap (DIAG_MAX_DESCENT_CLAUSES=4), so this exercises the
# leaves cap in isolation.  Same unsatisfiability requirement as the other
# rung-3 fixtures (contradictory pairs, see the note on TWO_ROUTES_SRC): each
# inner route pairs a one-sided lower bound with ``N < 0`` so the all-holes
# probe fails and rung 3 descends; at N = 5, ``N > 100`` / ``N > 200`` is the
# FIRST failing conjunct of its route, so it is the leaf rendered.  Verified
# against the live engine: 8 findings, capped to 6 (3x each conjunct).
FANOUT_SRC = """
-private([a, b, c, d])

inner(N) <- (N > 100, N < 0),
inner(N) <- (N > 200, N < 0),

fanout(N, a) <- (inner(N)),
fanout(N, b) <- (inner(N)),
fanout(N, c) <- (inner(N)),
fanout(N, d) <- (inner(N)),

Test("fan out") <- (
    fanout(5, _R)
),
"""


def test_leaves_cap_bounds_total_findings_across_fanout(capsys, tmp_path):
    p = write(tmp_path, "fanout.clausal", FANOUT_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    # 8 findings fan out; exactly DIAG_MAX_DESCENT_LEAVES=6 are rendered.
    findings = out.count("N > 100") + out.count("N > 200")
    assert findings == 6
    # ...and the truncation is stated, counting findings not routes/clauses.
    assert "only the first 6 of 8 descent findings are shown" in out


# When the head listing itself is truncated by the clause cap, the headline must
# not claim ALL heads mismatch — only the first DIAG_MAX_DESCENT_CLAUSES (=4)
# were examined.  Same rung-3 requirement as the other head-listing fixtures:
# each head carries a DISTINCT atom literal so no head unifies with the concrete
# goal atom ``zzz``, and each body is a non-recursive ``1 > 2`` so the all-holes
# probe fails cleanly (rung 2 does not intercept) and descent runs.  Verified
# against the live engine: softened headline + cap note, only 4 heads listed.
SIX_HEADS_SRC = """
-private([a, b, c, d, e, f, zzz])

sixhead(a, N) <- (1 > 2),
sixhead(b, N) <- (1 > 2),
sixhead(c, N) <- (1 > 2),
sixhead(d, N) <- (1 > 2),
sixhead(e, N) <- (1 > 2),
sixhead(f, N) <- (1 > 2),

Test("six clause heads all mismatch") <- (
    sixhead(zzz, 5)
),
"""


def test_capped_head_listing_softens_headline_and_notes_cap(capsys, tmp_path):
    p = write(tmp_path, "sixhead.clausal", SIX_HEADS_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    # Softened headline bounds the claim to the first N heads examined.
    assert "no clause head among the first 4 unifies" in out
    # ...and the unsoftened "ALL heads mismatch" wording is NOT used here.
    assert "no clause head unifies with these arguments" not in out
    # The truncation is stated as a note.
    assert "first 4 of 6 clauses" in out
    # Only the first 4 heads are listed (5th/6th were never examined).
    assert "sixhead(a, N)" in out
    assert "sixhead(d, N)" in out
    assert "sixhead(e, N)" not in out


# ── degenerate rung-1/2 solutions descend (todo D) ───────────────────────────

# A rung-1 near-miss that leaves the freed argument NON-GROUND (unbound holes
# in it) carries no value: it shows a clause-head pattern, not a counter-value.
# A measured authoring study's shape — a `[H|T]`-as-BitOr head plus a
# base-case fact — was intercepted at rung 1 with exactly such a near-miss
# (`BitOr(None, [2880, _], [])`), and the head listing that names the real bug
# never fired.  See
# `todo/done/D-rung2-unbound-arg-solutions-weaken-diagnosis.md`.
CONS_PINNED_SRC = """
-private([work])

wtq_totals([], 0, 0),
wtq_totals([WORKED_MINUTES, STATUS] | REST_WEEKS, TOTAL, N) <- (
    wtq_totals(REST_WEEKS, T0, N0),
    TOTAL == T0 + WORKED_MINUTES,
    N == N0 + 1
),

Test("totals over one week, pinned") <- (
    wtq_totals([[2880, work]], 2880, 1)
),
"""


def test_unbound_near_miss_descends_to_head_listing(capsys, tmp_path):
    p = write(tmp_path, "wtq.clausal", CONS_PINNED_SRC)
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
classify(X, "small") <- (X < 10, X < 0),
classify(X, "big") <- (X > 10, X < 0),

Test("lone one-sided bounds") <- (
    classify(5, _KIND)
),
"""


def test_unbound_near_miss_descends_to_clause_leaves(capsys, tmp_path):
    p = write(tmp_path, "lone.clausal", LONE_BOUND_SRC)
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
-private([work])

wto_totals([], 0, 0),
wto_totals([WORKED_MINUTES, STATUS] | REST_WEEKS, TOTAL, N) <- (
    wto_totals(REST_WEEKS, T0, N0),
    TOTAL == T0 + WORKED_MINUTES,
    N == N0 + 1
),

Test("totals over one week, outputs free") <- (
    wto_totals([[2880, work]], TOTAL, N),
    TOTAL == 2880
),
"""


def test_ground_base_case_near_miss_keeps_rung_1(capsys, tmp_path):
    p = write(tmp_path, "wto.clausal", CONS_OUTPUT_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "argument 1 differs" in out
    assert "wto_totals([], TOTAL, N)" in out   # the ground [] base-case match
    assert "no clause head unifies" not in out


def test_ground_fact_near_miss_keeps_rung_1(capsys, tmp_path):
    p = write(tmp_path, "gpair.clausal", """
        gpair("a", 1),
        gpair("b", 2),

        Test("one argument differs") <- (
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
pairq(A, B, A, B),

Test("both couplings differ") <- (
    pairq(1, 2, 3, 4)
),
"""


def test_degenerate_rung2_examples_descend(capsys, tmp_path):
    p = write(tmp_path, "pairq.clausal", COUPLED_FACT_SRC)
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
    p = write(tmp_path, "fallback.clausal", LONE_BOUND_SRC)
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
mixf(A | B, 7),
mixf([1, 2], 8),

Test("later concrete slot wins") <- (
    mixf([1, 2], 7)
),
"""


def test_concrete_near_miss_in_a_later_slot_wins_over_degenerate(
        capsys, tmp_path):
    p = write(tmp_path, "mixf.clausal", MIXED_SLOTS_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "argument 2 differs" in out
    assert "mixf([1, 2], 8)" in out
    assert "no clause head unifies" not in out
    assert "none binds" not in out


# The keyword-argument slot path builds its own label; the degenerate intro
# must carry it through to the descent headline.
KWARG_DEG_SRC = """
kdeg(R=A | B),

Test("kwarg degenerate") <- (
    kdeg(R=[1, 2])
),
"""


def test_degenerate_keyword_argument_descends_with_kw_label(capsys, tmp_path):
    p = write(tmp_path, "kdeg.clausal", KWARG_DEG_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert ("solutions with keyword argument 'R' freed, but none binds "
            "keyword argument 'R' to a concrete value") in out
    assert "no clause head unifies" in out


def test_degenerate_rung2_falls_back_when_descent_finds_nothing(
        capsys, tmp_path, monkeypatch):
    # Rung-2 analogue of the rung-1 fallback: the anonymised examples are
    # weak, but they must survive when the descent has nothing better.
    import clausal.testing as _t
    monkeypatch.setattr(_t, "_descend", lambda *a, **k: ([], "none"))
    p = write(tmp_path, "pairq_fb.clausal", COUPLED_FACT_SRC)
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
positivep(1),
positivep(2),
positivep(4),
positivep(5),

Test("all positive") <- (
    forall(SUBJECT in [1, 2, 3, 4, 5], positivep(SUBJECT))
),
"""


def test_forall_names_the_single_failing_element(capsys, tmp_path):
    p = write(tmp_path, "fa_one.clausal", FORALL_ONE_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    # The headline states how many of how many failed, and by which name.
    assert "failed for 1 of 5 elements" in out
    assert "SUBJECT = 3" in out           # the one element with no solution
    # The bare rung-3 non-answer must NOT be what the reader sees.
    assert "no solution for ANY arguments" not in out


FORALL_MANY_SRC = """
positivem(2),
positivem(4),

Test("all positive, several fail") <- (
    forall(SUBJECT in [1, 2, 3, 4, 5], positivem(SUBJECT))
),
"""


def test_forall_names_every_failing_element_within_the_bound(capsys, tmp_path):
    p = write(tmp_path, "fa_many.clausal", FORALL_MANY_SRC)
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
noneofthem(_X) <- (1 > 2),

Test("long list, all fail") <- (
    forall(N in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10], noneofthem(N))
),
"""


def test_forall_bounds_the_number_of_named_elements(capsys, tmp_path):
    from clausal.testing import DIAG_MAX_DESCENT_LEAVES

    p = write(tmp_path, "fa_long.clausal", FORALL_LONG_SRC)
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
Test("all in range") <- (
    forall(V in [0, 1, 7, 2], (V >= 0, V <= 3))
),
"""


def test_forall_names_element_with_conjunction_body(capsys, tmp_path):
    p = write(tmp_path, "fa_conj.clausal", FORALL_CONJ_SRC)
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

Test("max additional days is 90") <- (
    max_additional_days(MAX),
    MAX == 90
),
"""


def test_findall_collapse_behind_wrong_value_is_named(capsys, tmp_path):
    p = write(tmp_path, "window_rule.clausal", WINDOW_SHAPE_SRC)
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

Test("score is 90") <- (
    score(MAX),
    MAX == 90
),
"""


def test_findall_collapse_via_nested_producer(capsys, tmp_path):
    p = write(tmp_path, "score.clausal", NESTED_PRODUCER_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "MAX == 90" in out
    # Descent went through the wrapper `score` into `inner_score`'s findall.
    assert "window_days_used(bad_atom, D)" in out


# A findall whose body DOES solve for at least one candidate is not blamed:
# the collapse sentinel is specific to a body that failed for EVERY candidate.
HEALTHY_FINDALL_SRC = """
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

Test("good max is 90") <- (
    good_max(MAX),
    MAX == 90
),
"""


def test_healthy_findall_is_not_blamed(capsys, tmp_path):
    p = write(tmp_path, "good.clausal", HEALTHY_FINDALL_SRC)
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
cand(9),
big(X) <- (X > 10),

Test("forall over collapsed findall") <- (
    forall(K in [1, 2], (
        findall(A, (cand(A), big(A)), XS),
        XS == [K]
    ))
),
"""


def test_forall_over_collapsed_findall_composes_element_first(capsys, tmp_path):
    p = write(tmp_path, "fa_findall.clausal", FORALL_COLLAPSED_FINDALL_SRC)
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

Test("maxdays is 3") <- (
    maxdays(MAX),
    MAX == 3
),
"""


def test_one_trivial_solution_collapse_is_named(capsys, tmp_path):
    p = write(tmp_path, "trivial.clausal", TRIVIAL_COLLAPSE_SRC)
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
    write(tmp_path, "verdict_lib.clausal", """
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
    p = write(tmp_path, "dotted.clausal", """
        -import_from(verdict_lib, [eligible, assess])

        Test("dotted atom comparison") <- (
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
usable2(0),

maxdays2(MAX) <- (
    findall(L, (between(0, 3, L), usable2(L)), LS),
    max_list(LS, MAX)
),

w3(M) <- (maxdays2(M)),
w2(M) <- (w3(M)),
w1(M) <- (w2(M)),

Test("deep wrapper chain") <- (
    w1(MAX),
    MAX == 3
),
"""


def test_collapse_scan_descends_past_failing_call_depth_bound(capsys, tmp_path):
    p = write(tmp_path, "deepwrap.clausal", DEEP_WRAPPER_SRC)
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

Test("overdeep wrapper chain") <- (
    v1(MAX),
    MAX == 3
),
"""


def test_collapse_scan_depth_exhaustion_is_noted(capsys, tmp_path):
    from clausal.testing import DIAG_MAX_COLLAPSE_DEPTH

    p = write(tmp_path, "overdeep.clausal", OVERDEEP_WRAPPER_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    # The findall is one level beyond the bound: no finding is possible...
    assert "silently collapsed to [0]" not in out
    # ...but the exhaustion is STATED, never silent.
    assert (f"stopped at its {DIAG_MAX_COLLAPSE_DEPTH}-level depth bound"
            in out)
