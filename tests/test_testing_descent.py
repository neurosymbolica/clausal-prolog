"""Stage-4 descent diagnostics + rung-2 examples for ``python -m clausal.testing``.

Rung 3 ("no solution for ANY arguments") used to carry no value — measured
0/29 recovery in study 13.  See
``docs/superpowers/specs/2026-07-30-assertion-diagnostic-descent-design.md``.
"""

from __future__ import annotations

import textwrap

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
    assert "pairx('a', 1)" in out                  # an actual solution, rendered


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
